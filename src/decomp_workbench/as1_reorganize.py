"""IDO 5.3 `as1 -R`: the scheduler trace the assembler already ships.

`instrument-scheduler` exists because the workbench assumed a scheduler trace
had to be patched in: a project-owned, hash-pinned profile against generated
`as1` C, behind five calibration gates. For IDO 5.3 that whole apparatus is
unnecessary. `as1` carries its own list-scheduler trace behind the `-R`
(reorganize) option -- option-table index 13 of the 106-entry table `f_which_opt`
reads -- and `cc` forwards it:

```
cc -Wa,-R ...          # trace on stderr, object byte-identical
```

It is print-only. The campaign that found it gated the claim rather than
asserting it: an object built with `-Wa,-R` was `cmp`-identical to the same
object built without it, whole file, not merely section-scoped. There is no
instrumented binary to hash-pin because there is no patch.

The trace is *richer* than `DKWB-SCHED-V1`, which is why this module reads it
natively and converts rather than the other way round. It carries the whole
per-block DAG -- `before`, `aftercycles`, `maxhazard`, successor latencies --
where the schema carries one selection per line. The schema also has no field
for the **losing** candidates, so `tie=` cannot be read out of it; it has to be
computed here, from the key chain, while the losers are still in hand.

The key chain, decoded from the selection driver and confirmed against 2688
recorded selections:

    ( start_time, -aftercycles, -latency, node->addr, node->lineno,
      ready-list position )

lexicographic minimum, each step a strict accept / not-equal reject. The fifth
key is a **source physical line number**, which is the whole reason this reader
is worth having: it makes statement folding a codegen lever.

Two honest gaps, both reported rather than papered over:

* **`node->addr` is not in the trace per candidate** -- only the chosen node's
  `at %x`. In the calibrated compile it was 0 for every node in the translation
  unit, so the chain reduced to five keys; this reader evaluates those five and
  says so in the report's `proof`.
* **as1 has no cycle counter in the record.** `cycle=` here is the selection
  ordinal within the block, which is what the schema aligns two traces on.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .scheduler import TRACE_PREFIX, SchedulerEvent

__all__ = [
    "AS1_R_GRAMMAR",
    "Candidate",
    "Selection",
    "mips_mnemonic",
    "parse_as1_reorganize_trace",
    "to_dkwb_records",
]

#: The record shapes, as the format strings read in `as1`'s own rodata. A
#: reader with a different IDO revision can check compatibility against this
#: table without running anything.
AS1_R_GRAMMAR: tuple[str, ...] = (
    "BASIC BLOCK: %d",
    "Node %3u: inst %.8x, relocation %u, lineno %u",
    "        before %u, aftercycles %u, maxhazard %u",
    "        afternodes: %u/%d ...",
    "Initial nodes: <ids>",
    "  node %u (INST %d), time = %u, aftercycles = %u, latency = %u, besttime = %d",
    "Picking node %u (INST %d), at %x, best_addr = %x",
)

_BLOCK_RE = re.compile(r"^\s*BASIC BLOCK:\s*(-?\d+)")
_NODE_RE = re.compile(
    r"^\s*Node\s+(\d+):\s*inst\s+([0-9a-fA-F]+),\s*relocation\s+(\d+),"
    r"\s*lineno\s+(\d+)"
)
_INITIAL_RE = re.compile(r"^\s*Initial nodes:")
_CANDIDATE_RE = re.compile(
    r"^\s*node\s+(\d+)\s*\(INST\s+(-?\d+)\),\s*time\s*=\s*(\d+),"
    r"\s*aftercycles\s*=\s*(\d+),\s*latency\s*=\s*(\d+),"
    r"\s*besttime\s*=\s*(-?\d+)"
)
_PICKING_RE = re.compile(
    r"^\s*Picking node\s+(\d+)\s*\(INST\s+(-?\d+)\),\s*at\s+([0-9a-fA-F]+),"
    r"\s*best_addr\s*=\s*([0-9a-fA-F]+)"
)

#: The key chain, in order, as `(name, value)` selectors. `addr` is absent from
#: the record and therefore absent here; see the module docstring.
_KEYS: tuple[tuple[str, str, bool], ...] = (
    ("start-time", "time", False),
    ("aftercycles", "aftercycles", True),
    ("latency", "latency", True),
    ("lineno", "lineno", False),
)

_PRIMARY_OPCODES: dict[int, str] = {
    0x02: "j",
    0x03: "jal",
    0x04: "beq",
    0x05: "bne",
    0x06: "blez",
    0x07: "bgtz",
    0x08: "addi",
    0x09: "addiu",
    0x0A: "slti",
    0x0B: "sltiu",
    0x0C: "andi",
    0x0D: "ori",
    0x0E: "xori",
    0x0F: "lui",
    0x11: "cop1",
    0x14: "beql",
    0x15: "bnel",
    0x16: "blezl",
    0x17: "bgtzl",
    0x18: "daddi",
    0x19: "daddiu",
    0x1A: "ldl",
    0x1B: "ldr",
    0x20: "lb",
    0x21: "lh",
    0x22: "lwl",
    0x23: "lw",
    0x24: "lbu",
    0x25: "lhu",
    0x26: "lwr",
    0x27: "lwu",
    0x28: "sb",
    0x29: "sh",
    0x2A: "swl",
    0x2B: "sw",
    0x2C: "sdl",
    0x2D: "sdr",
    0x2E: "swr",
    0x31: "lwc1",
    0x35: "ldc1",
    0x37: "ld",
    0x39: "swc1",
    0x3D: "sdc1",
    0x3F: "sd",
}

_SPECIAL_FUNCTS: dict[int, str] = {
    0x00: "sll",
    0x02: "srl",
    0x03: "sra",
    0x04: "sllv",
    0x06: "srlv",
    0x07: "srav",
    0x08: "jr",
    0x09: "jalr",
    0x0C: "syscall",
    0x0D: "break",
    0x10: "mfhi",
    0x11: "mthi",
    0x12: "mflo",
    0x13: "mtlo",
    0x18: "mult",
    0x19: "multu",
    0x1A: "div",
    0x1B: "divu",
    0x1C: "dmult",
    0x1D: "dmultu",
    0x1E: "ddiv",
    0x1F: "ddivu",
    0x20: "add",
    0x21: "addu",
    0x22: "sub",
    0x23: "subu",
    0x24: "and",
    0x25: "or",
    0x26: "xor",
    0x27: "nor",
    0x2A: "slt",
    0x2B: "sltu",
    0x2C: "dadd",
    0x2D: "daddu",
    0x2E: "dsub",
    0x2F: "dsubu",
}


def mips_mnemonic(word: int) -> str:
    """Name one instruction word, honestly, without inventing operands.

    Only the mnemonic. `DKWB-SCHED-V1` carries the whole word beside it, so a
    reader who needs the registers has them; a decoder that guessed at
    operand spellings would be a second disassembler to keep correct.
    """

    word &= 0xFFFFFFFF
    primary = (word >> 26) & 0x3F
    if primary == 0:
        funct = word & 0x3F
        if word == 0:
            return "nop"
        return _SPECIAL_FUNCTS.get(funct, f"special.{funct:#04x}")
    if primary == 0x01:
        return "regimm"
    return _PRIMARY_OPCODES.get(primary, f"op.{primary:#04x}")


@dataclass(frozen=True)
class Candidate:
    """One node considered at one selection."""

    node: int
    inst: int
    time: int
    aftercycles: int
    latency: int
    besttime: int
    position: int
    lineno: int | None
    word: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "inst": self.inst,
            "time": self.time,
            "aftercycles": self.aftercycles,
            "latency": self.latency,
            "besttime": self.besttime,
            "position": self.position,
            "lineno": self.lineno,
            "word": None if self.word is None else f"0x{self.word:08x}",
        }


@dataclass(frozen=True)
class Selection:
    """One `Picking node` decision, with the candidates it beat."""

    block: int
    ordinal: int
    chosen: int
    addr: int
    best_addr: int
    candidates: tuple[Candidate, ...]
    tie: str

    @property
    def winner(self) -> Candidate | None:
        for item in self.candidates:
            if item.node == self.chosen:
                return item
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "block": self.block,
            "ordinal": self.ordinal,
            "chosen": self.chosen,
            "addr": self.addr,
            "best_addr": self.best_addr,
            "tie": self.tie,
            "candidates": [item.as_dict() for item in self.candidates],
        }


def _deciding_key(candidates: Iterable[Candidate], chosen: int) -> str:
    """Name the first key of the chain on which exactly one candidate wins."""

    remaining = list(candidates)
    if len(remaining) == 1:
        return "sole-candidate"
    for name, attribute, maximise in _KEYS:
        values = [getattr(item, attribute) for item in remaining]
        if any(value is None for value in values):
            continue
        best = max(values) if maximise else min(values)
        winners = [item for item in remaining if getattr(item, attribute) == best]
        if len(winners) == 1:
            return name if winners[0].node == chosen else f"{name}-disagrees"
        remaining = winners
    return "list-order"


def parse_as1_reorganize_trace(
    text: str, *, proc: int = 0
) -> tuple[list[Selection], list[SchedulerEvent], list[str]]:
    """Parse one `cc -Wa,-R` trace into selections and schema events.

    Returns the native selections, the same decisions in the workbench's
    stable schema, and the diagnostic lines that were not part of a selection
    -- the assembler prints a great deal else, and discarding it silently
    would hide a truncated capture.
    """

    selections: list[Selection] = []
    events: list[SchedulerEvent] = []
    ignored: list[str] = []
    linenos: dict[int, int] = {}
    words: dict[int, int] = {}
    block: int | None = None
    fallback_block = 0
    # Selection ordinals accumulate per block rather than resetting with the
    # header: `as1` dumps a block again after reorganizing it, and a reset
    # would mint two selections with the same (block, cycle) key.
    ordinals: dict[int, int] = {}
    pending: list[Candidate] = []
    seen_block_header = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        match = _BLOCK_RE.match(line)
        if match is not None:
            block = int(match.group(1))
            seen_block_header = True
            linenos.clear()
            words.clear()
            pending.clear()
            continue
        match = _NODE_RE.match(line)
        if match is not None:
            node = int(match.group(1))
            words[node] = int(match.group(2), 16)
            linenos[node] = int(match.group(4))
            continue
        if _INITIAL_RE.match(line) is not None:
            if not seen_block_header:
                # No `BASIC BLOCK:` header in this capture: number the blocks
                # by the order their DAGs appear, and say so in the report.
                block = fallback_block
                fallback_block += 1
            pending.clear()
            continue
        match = _CANDIDATE_RE.match(line)
        if match is not None:
            node = int(match.group(1))
            pending.append(
                Candidate(
                    node=node,
                    inst=int(match.group(2)),
                    time=int(match.group(3)),
                    aftercycles=int(match.group(4)),
                    latency=int(match.group(5)),
                    besttime=int(match.group(6)),
                    position=len(pending),
                    lineno=linenos.get(node),
                    word=words.get(node),
                )
            )
            continue
        match = _PICKING_RE.match(line)
        if match is not None:
            chosen = int(match.group(1))
            candidates = tuple(pending)
            pending = []
            if not candidates:
                # A pick whose candidate list was not captured. Keeping it as
                # a one-candidate selection would invent a `sole-candidate`
                # tie that the trace never showed.
                ignored.append(raw)
                continue
            current_block = block if block is not None else 0
            ordinal = ordinals.get(current_block, 0)
            ordinals[current_block] = ordinal + 1
            selection = Selection(
                block=current_block,
                ordinal=ordinal,
                chosen=chosen,
                addr=int(match.group(3), 16),
                best_addr=int(match.group(4), 16),
                candidates=candidates,
                tie=_deciding_key(candidates, chosen),
            )
            selections.append(selection)
            winner = selection.winner
            word = (winner.word if winner else None) or 0
            events.append(
                SchedulerEvent(
                    proc=proc,
                    block=current_block,
                    cycle=ordinal,
                    word=word,
                    opcode=mips_mnemonic(word),
                    line=(winner.lineno if winner and winner.lineno else 0),
                    ready=len(candidates),
                    chosen=f"n{chosen}",
                    tie=selection.tie,
                )
            )
            continue
        ignored.append(raw)
    return selections, events, ignored


def to_dkwb_records(events: Iterable[SchedulerEvent]) -> str:
    """Render parsed selections as `DKWB-SCHED-V1` lines.

    A campaign that keeps the converted artifact keeps something every other
    trace command already reads, and does not have to keep the assembler.
    """

    lines = []
    for event in events:
        lines.append(
            f"{TRACE_PREFIX} proc={event.proc} block={event.block} "
            f"cycle={event.cycle} word=0x{event.word:08x} "
            f"opcode={event.opcode} line={event.line} ready={event.ready} "
            f"chosen={event.chosen} tie={event.tie}"
        )
    return "\n".join(lines) + ("\n" if lines else "")
