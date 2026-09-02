"""Decode ugen's `DKWB-EMIT-V1` emit-order provenance records.

**What this is the other half of.** IDO 5.3's instruction scheduler is not in
ugen. A full inventory of ugen's 431 named generated functions contains no
ready list, no dependence DAG, no delay-slot filler and no nop inserter; the
list scheduler that owns those decisions lives in `as1`
(`f_reorganize_bb` / `f_schedule` / `f_fill_inst` / `f_emitnop`) and is already
readable without patching, through `cc -Wa,-R`, decoded by
:mod:`decomp_workbench.as1_reorganize`. Asking ugen for a "slot" or a
"ready-list position" is asking a question its code does not contain, and this
decoder does not invent one.

**What ugen does decide**, and what these records carry, is the *order*
instruction records enter the ibuffer and the *source line* each one is
stamped with. That line matters because it is a key in as1's selection chain
(minimised: the lower line wins), and it is the only key in that chain with a
source-level lever attached. Two independent ready nodes are separated by their
lines, and their lines are assigned here.

The decisive case this decoder was built for is the **loop-invariant hoist**.
When uopt/ugen lifts a base-address materialisation into a loop preheader, the
hoisted record is stamped with the *loop header's* line, not the line of the
statement that used the address. Any initialisation written on an earlier
source line therefore carries a strictly lower line into as1 and wins the tie,
even though nothing in the data flow orders the two. Putting the initialiser on
the same physical line as the loop header removes the line difference and lets
the later key decide -- a real, source-level lever that is invisible without
these records.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

TRACE_PREFIX = "DKWB-EMIT-V1"
TRACE_SCHEMA = "decomp-workbench-ugen-emit-trace-v1"
FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)")
REQUIRED_FIELDS = ("proc", "block", "emit", "op", "line", "buffer", "fn")
BUFFERS = frozenset({"fwd", "back"})

#: Emit helpers that write something other than a machine instruction record:
#: assembler directives, symbol/alias bookkeeping, labels, and the whole
#: backward (data) buffer. They still carry a line, and the `.loc`-style
#: directive (`f_emit_dir2`) is precisely the record that hands ugen's line to
#: the assembler, so they are decoded and reported -- just not counted as
#: instructions.
DIRECTIVE_FUNCTIONS = frozenset(
    {
        "f_emit_dir0",
        "f_emit_dir1",
        "f_emit_dir2",
        "f_emit_dir_ll",
        "f_emit_alias",
        "f_emit_regmask",
        "f_emit_loopno",
        "f_emit_optimize_level",
        "f_emit_file",
        "f_emit_vers",
        "f_emit_symbol",
        "f_emit_pic",
        "f_emit_init",
        "f_emit_cpalias",
        "f_emit_cpadd",
        "f_emit_cpload",
        "f_emit_vreg",
        "f_emit_itext",
        "f_define_label",
        "f_ddefine_label",
        "f_define_exception_label",
    }
)


@dataclass(frozen=True)
class EmitEvent:
    """One ibuffer record ugen wrote, in the order it wrote it."""

    proc: int
    block: int
    emit: int
    op: int
    line: int
    buffer: str
    fn: str

    @property
    def is_instruction(self) -> bool:
        """True when this record becomes a machine instruction.

        Backward-buffer records are data and directives; the named helpers in
        :data:`DIRECTIVE_FUNCTIONS` write assembler directives, labels and
        alias bookkeeping. Everything else is an instruction record -- possibly
        a multi-word one: `f_emit_ra` writes a single record that the assembler
        expands to a HI16/LO16 pair, which is exactly why a hoisted address can
        have its two halves scheduled apart.
        """

        return self.buffer == "fwd" and self.fn not in DIRECTIVE_FUNCTIONS

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["is_instruction"] = self.is_instruction
        return value


def _integer(fields: dict[str, str], name: str, line_number: int) -> int:
    try:
        return int(fields[name], 0)
    except (KeyError, ValueError):
        raise ValueError(
            f"emit trace line {line_number} has invalid integer field {name!r}"
        ) from None


def parse_emit_trace(text: str) -> tuple[list[EmitEvent], list[str]]:
    """Parse `DKWB-EMIT-V1` records, preserving unrelated diagnostics.

    A ugen trace is interleaved with the compiler's own stderr and with the
    other DKWB record families, so anything that is not one of these records is
    returned untouched rather than dropped or guessed at.
    """

    events: list[EmitEvent] = []
    ignored: list[str] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        if TRACE_PREFIX not in raw:
            if raw.strip():
                ignored.append(raw)
            continue
        body = raw[raw.index(TRACE_PREFIX) + len(TRACE_PREFIX) :]
        pairs: list[tuple[str, str]] = []
        for token in body.split():
            match = FIELD_RE.fullmatch(token)
            if match is None:
                raise ValueError(
                    f"emit trace line {line_number} has malformed token {token!r}"
                )
            pairs.append((match.group(1), match.group(2)))
        fields = dict(pairs)
        if len(fields) != len(pairs):
            counts: dict[str, int] = {}
            for name, _value in pairs:
                counts[name] = counts.get(name, 0) + 1
            raise ValueError(
                f"emit trace line {line_number} repeats field(s): "
                + ", ".join(sorted(n for n, c in counts.items() if c > 1))
            )
        unknown = sorted(set(fields) - set(REQUIRED_FIELDS))
        if unknown:
            raise ValueError(
                f"emit trace line {line_number} has unsupported field(s): "
                + ", ".join(unknown)
            )
        missing = [name for name in REQUIRED_FIELDS if name not in fields]
        if missing:
            raise ValueError(
                f"emit trace line {line_number} is missing field(s): "
                + ", ".join(missing)
            )
        if fields["buffer"] not in BUFFERS:
            raise ValueError(
                f"emit trace line {line_number} has unknown buffer "
                f"{fields['buffer']!r}; expected one of " + ", ".join(sorted(BUFFERS))
            )
        event = EmitEvent(
            proc=_integer(fields, "proc", line_number),
            block=_integer(fields, "block", line_number),
            emit=_integer(fields, "emit", line_number),
            op=_integer(fields, "op", line_number),
            line=_integer(fields, "line", line_number),
            buffer=fields["buffer"],
            fn=fields["fn"],
        )
        for name in ("proc", "block", "emit", "op", "line"):
            if getattr(event, name) < 0:
                raise ValueError(
                    f"emit trace line {line_number} has negative field {name!r}"
                )
        events.append(event)
    return events, ignored


def _selected(
    events: Iterable[EmitEvent],
    proc: int | None,
    block: int | None,
) -> list[EmitEvent]:
    return [
        event
        for event in events
        if (proc is None or event.proc == proc)
        and (block is None or event.block == block)
    ]


def line_order_conflicts(events: Iterable[EmitEvent]) -> list[dict[str, Any]]:
    """Adjacent instruction pairs whose lines could reverse their order.

    A pair is reported when, within one basic block, ugen emits record *a*
    before record *b* and stamps *b* with a strictly **greater** source line.
    That is the precondition -- and, given as1 minimises the line key, the
    mechanism -- for the assembler's scheduler to keep *a* first even where no
    dependence edge orders the two. It is also the pair an analyst can act on:
    give *a* the same physical line as *b* and the line key stops deciding.

    Only adjacent pairs are reported. A conflict between distant records is
    mediated by everything between them, and listing every pair in a block
    would bury the one decision that matters under quadratically many that do
    not.
    """

    conflicts: list[dict[str, Any]] = []
    by_block: dict[tuple[int, int], list[EmitEvent]] = {}
    for event in events:
        if not event.is_instruction:
            continue
        by_block.setdefault((event.proc, event.block), []).append(event)
    for (proc, block), rows in sorted(by_block.items()):
        rows = sorted(rows, key=lambda item: item.emit)
        for earlier, later in pairwise(rows):
            if earlier.line < later.line:
                conflicts.append(
                    {
                        "proc": proc,
                        "block": block,
                        "earlier": earlier.as_dict(),
                        "later": later.as_dict(),
                        "line_gap": later.line - earlier.line,
                    }
                )
    return conflicts


def emit_report(
    events: list[EmitEvent],
    *,
    proc: int | None = None,
    block: int | None = None,
) -> dict[str, Any]:
    """Per-block emission order with the source line each record carries."""

    selected = _selected(events, proc, block)
    instructions = [event for event in selected if event.is_instruction]
    blocks: list[dict[str, Any]] = []
    seen: dict[tuple[int, int], list[EmitEvent]] = {}
    for event in selected:
        seen.setdefault((event.proc, event.block), []).append(event)
    for (block_proc, block_id), rows in sorted(seen.items()):
        rows = sorted(rows, key=lambda item: item.emit)
        block_instructions = [row for row in rows if row.is_instruction]
        blocks.append(
            {
                "proc": block_proc,
                "block": block_id,
                "records": [row.as_dict() for row in rows],
                "instruction_count": len(block_instructions),
                "lines": sorted({row.line for row in block_instructions}),
            }
        )
    return {
        "schema": TRACE_SCHEMA,
        "proof": (
            "ugen emission order and per-record source lines. Evidence about "
            "the scheduler's *input*, not its output: ugen contains no ready "
            "list, no dependence DAG and no delay-slot filler, so slot, "
            "priority and delay-slot occupancy are not derivable here -- read "
            "them from `cc -Wa,-R` via as1-reorganize."
        ),
        "event_count": len(selected),
        "instruction_count": len(instructions),
        "procedures": sorted({event.proc for event in events}),
        "blocks": blocks,
        "line_order_conflicts": line_order_conflicts(selected),
    }


def format_emit_report(report: dict[str, Any]) -> str:
    """Render a report as the per-block emission listing an analyst reads."""

    lines: list[str] = []
    for block in report["blocks"]:
        lines.append(
            f"proc {block['proc']} block {block['block']}  "
            f"{block['instruction_count']} instruction records  "
            f"lines {block['lines']}"
        )
        for row in block["records"]:
            mark = "I" if row["is_instruction"] else "."
            lines.append(
                f"  {mark} emit={row['emit']:<6} line={row['line']:<6} "
                f"op={row['op']:<6} {row['buffer']:<4} {row['fn']}"
            )
    conflicts = report["line_order_conflicts"]
    lines.append("")
    lines.append(f"line-order conflicts: {len(conflicts)}")
    for conflict in conflicts:
        earlier = conflict["earlier"]
        later = conflict["later"]
        lines.append(
            f"  proc {conflict['proc']} block {conflict['block']}: "
            f"emit={earlier['emit']} line={earlier['line']} ({earlier['fn']}) "
            f"before emit={later['emit']} line={later['line']} ({later['fn']}) "
            f"-- the earlier record's lower line wins as1's line key"
        )
    return "\n".join(lines)
