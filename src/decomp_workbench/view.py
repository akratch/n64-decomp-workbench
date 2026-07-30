"""Aligned mechanism view: LCS alignment, class lanes, and hunk taxonomy.

Positional diffing lies.  One upstream register-role swap on a live campaign
function turned into roughly 76 phantom scattered differences under positional
comparison; the LCS-aligned truth was roughly 43 hunks.  Every count produced
here is therefore an *aligned* count, never a positional one.

The pipeline is two passes of ``difflib.SequenceMatcher`` (``autojunk=False``
is mandatory: instruction streams are full of repeats that the junk heuristic
would discard), plus a classification step:

1. Anchor on the normalized instruction *text*.  Identical text is
   interchangeable, so these anchors carry no ambiguity.
2. Inside each unmatched region, pair by *opcode*, so an operand-level
   difference is classified rather than shown as a deletion beside an
   insertion.  Anything left unpaired is structure or schedule.
3. Classify every pair: register, commutative-order, constant, relocation,
   displacement, or match.

The ad-hoc aligners three campaigns built in one day ran the opcode pass
first.  That order cannot resolve a run of repeated opcodes -- eight ``addu``
instructions with one inserted among them align position by position, and four
correct instructions are then reported as register differences beside a
phantom insertion -- so the text pass anchors first here.

Register lanes are extracted from the *whole* aligned stream, including the
instructions that match.  That is not an optimization: the decisive signal in
the modLoadAnimActual campaign was in the temps that matched, and a view that
only shows mismatched instructions hides the queue.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .compare import (
    frame_size,
    is_commutative_swap,
    register_operands,
    relocation_field_mask,
)
from .field_guide import next_steps
from .model import Instruction
from .schema import VIEW_METRICS_BY_KEY

__all__ = [
    "DEFAULT_REGISTER_PROFILE",
    "REGISTER_CLASS_PROFILES",
    "AlignedRow",
    "Hunk",
    "Lane",
    "MechanismView",
    "Web",
    "aligned_class_counts",
    "build_view",
    "classify_pair",
    "destination_register",
    "schema_keys",
]


# ---------------------------------------------------------------------------
# Schema: one vocabulary, two renderings.
#
# Human output prints ``key=value`` using these exact keys, and JSON output
# uses the same keys, so the two audiences can never drift apart again.  List
# valued keys render as a count in the human header and as the list in JSON.
# The names live in the shared metric registry beside the comparison and
# campaign keys, so ``--explain-keys`` explains this command too and there is
# one place a key can be added.
# ---------------------------------------------------------------------------


def schema_keys() -> frozenset[str]:
    """Return every key the human and JSON renderings are allowed to print."""

    return frozenset(VIEW_METRICS_BY_KEY)


# ---------------------------------------------------------------------------
# Register class tables (per-toolchain profile data, not hardcoded policy).
#
# The IDO 5.3 tables come from black-box pool probing during the
# rarezipUncompress campaign and were confirmed by the ugen deep dive: the
# coloring pool hands out v0/v1/a0-a3/t0-t5, while a separate rotation serves
# expression temps.
# ---------------------------------------------------------------------------

REGISTER_CLASS_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "ido53": {
        "pool": (
            "v0",
            "v1",
            "a0",
            "a1",
            "a2",
            "a3",
            "t0",
            "t1",
            "t2",
            "t3",
            "t4",
            "t5",
        ),
        "temp": ("t6", "t7", "t8", "t9", "s8"),
    },
}
DEFAULT_REGISTER_PROFILE = "ido53"

# Opcodes whose first register operand is a source, not a destination.  A lane
# records definitions only: a store or a branch reads its registers and would
# otherwise inject phantom slots into the sequence.
NO_DESTINATION_OPCODES = frozenset(
    {
        "b",
        "bal",
        "bc1f",
        "bc1fl",
        "bc1t",
        "bc1tl",
        "beq",
        "beql",
        "beqz",
        "bgez",
        "bgezal",
        "bgezl",
        "bgtz",
        "bgtzl",
        "blez",
        "blezl",
        "bltz",
        "bltzal",
        "bltzl",
        "bne",
        "bnel",
        "bnez",
        "break",
        "cache",
        "ctc1",
        "ddiv",
        "ddivu",
        "div",
        "divu",
        "dmtc1",
        "dmult",
        "dmultu",
        "j",
        "jal",
        "jalr",
        "jr",
        "mtc0",
        "mtc1",
        "mthi",
        "mtlo",
        "mult",
        "multu",
        "nop",
        "sb",
        "sc",
        "scd",
        "sd",
        "sdc1",
        "sdc2",
        "sdl",
        "sdr",
        "sh",
        "sw",
        "swc1",
        "swc2",
        "swl",
        "swr",
        "sync",
        "syscall",
        "teq",
        "tne",
    }
)

SYMBOL_OPERAND_RE = re.compile(r"\b([0-9a-fA-F]+)\s+<([^>]+)>")
IMMEDIATE_RE = re.compile(r"(?<![A-Za-z0-9_$.])-?(?:0x[0-9a-fA-F]+|\d+)\b")
SELF_BRANCH_OPCODES = frozenset({"b", "j", "bal"})
#: Placeholder written in place of a branch destination that resolves inside
#: the function, so destinations compare by aligned row instead of by address.
ALIGNED_TARGET = "@row"

MATCH = "match"
DISPLACEMENT = "displacement"
STRUCTURAL = "structural"
SCHEDULE = "schedule"
REGISTER = "register"
CONSTANT = "constant"
COMMUTATIVE = "commutative"
RELOCATION = "relocation"

#: Classes in report order.  ``match`` is deliberately first: the header leads
#: with how much already agrees.
CLASS_ORDER: tuple[str, ...] = (
    MATCH,
    DISPLACEMENT,
    STRUCTURAL,
    SCHEDULE,
    REGISTER,
    CONSTANT,
    COMMUTATIVE,
    RELOCATION,
)

#: Precedence for composite verdicts.  Constants cascade, so they are fixed
#: first; register classes are last because they are usually downstream.
MIXED_PRECEDENCE: tuple[str, ...] = (
    CONSTANT,
    STRUCTURAL,
    SCHEDULE,
    COMMUTATIVE,
    REGISTER,
)

#: The classes a source change controls, and therefore the ones a residual
#: count may include.  ``match`` is agreement; ``displacement`` is an encoded
#: branch offset that moved because something was inserted elsewhere; and
#: ``relocation`` is a linker-supplied field.  None of the three is a number a
#: candidate should be ranked on, and counting them would re-introduce exactly
#: the phantom volume the alignment exists to remove.
RESIDUAL_CLASSES: tuple[str, ...] = (
    STRUCTURAL,
    SCHEDULE,
    REGISTER,
    CONSTANT,
    COMMUTATIVE,
)


@dataclass(frozen=True)
class AlignedRow:
    """One row of the LCS alignment, with its operand-level classification."""

    index: int
    classification: str
    target_index: int | None = None
    candidate_index: int | None = None
    target: str | None = None
    candidate: str | None = None
    target_address: int | None = None
    candidate_address: int | None = None
    target_registers: tuple[str, ...] = ()
    candidate_registers: tuple[str, ...] = ()
    substitutions: tuple[tuple[str, str], ...] = ()

    @property
    def matched(self) -> bool:
        """Whether the two sides are byte-identical."""

        return self.classification == MATCH

    @property
    def reported(self) -> bool:
        """Whether this row belongs in a hunk.

        A displacement row differs in bytes but not in anything a source change
        controls, so it is counted and annotated in context without opening a
        hunk of its own.
        """

        return self.classification not in {MATCH, DISPLACEMENT}


@dataclass(frozen=True)
class Hunk:
    """A contiguous run of non-matching aligned rows."""

    hunk: int
    classification: str
    start: int
    end: int
    target_range: tuple[int, int] | None
    candidate_range: tuple[int, int] | None
    target_bytes: tuple[int, int] | None
    candidate_bytes: tuple[int, int] | None
    classes: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "hunk": self.hunk,
            "class": self.classification,
            "rows": [self.start, self.end],
            "target": list(self.target_range) if self.target_range else None,
            "candidate": list(self.candidate_range) if self.candidate_range else None,
            "target_bytes": _byte_range(self.target_bytes),
            "candidate_bytes": _byte_range(self.candidate_bytes),
            "classes": dict(self.classes),
        }


@dataclass(frozen=True)
class Lane:
    """A per-class register assignment sequence, matching instructions included."""

    classification: str
    target: tuple[str, ...]
    candidate: tuple[str, ...]
    target_rows: tuple[int, ...]
    candidate_rows: tuple[int, ...]
    divergence: int | None
    divergence_row: int | None
    rotation: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "class": self.classification,
            "target": list(self.target),
            "candidate": list(self.candidate),
            "rows": list(self.target_rows),
            # `slot` and `aligned_row` are two different units, and spelling
            # them `divergence` and `index` made them read as one coordinate
            # pair. The screen and the payload rename together: one vocabulary
            # is the whole point of the metric registry.
            "slot": self.divergence,
            "aligned_row": self.divergence_row,
            "rotation": self.rotation,
        }


@dataclass(frozen=True)
class Web:
    """One consistent register substitution across the aligned stream."""

    web: str
    target: str
    candidate: str
    count: int
    rows: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "web": self.web,
            "target": self.target,
            "candidate": self.candidate,
            "count": self.count,
            "rows": list(self.rows),
        }


@dataclass(frozen=True)
class MechanismView:
    """The aligned mechanism view of one target/candidate pair."""

    symbol: str | None
    target: str
    candidate: str
    register_profile: str
    target_instructions: int
    candidate_instructions: int
    target_frame_size: int | None
    candidate_frame_size: int | None
    counts: dict[str, int]
    verdict: str
    playbook: str
    signature: tuple[str, ...]
    prefix_exact: int | None
    rows: tuple[AlignedRow, ...]
    hunks: tuple[Hunk, ...]
    lanes: tuple[Lane, ...]
    webs: tuple[Web, ...]
    guidance: tuple[str, ...]
    #: Reasons not to trust the verdict, as opposed to findings about the
    #: code. Rendered ahead of everything else by the commands that own the
    #: screen; carried here so `--json` consumers see them too.
    warnings: tuple[str, ...] = ()

    @property
    def aligned_rows(self) -> int:
        return len(self.rows)

    @property
    def register_first_divergence(self) -> bool:
        """Whether the first divergence is a register-class divergence.

        Two disassembly streams are the only evidence this command has, so a
        state divergence that leaves the bytes alone is not observable here:
        anything that changes a lane also changes an instruction.  What *is*
        observable, and what redirected a campaign that had spent 13 variants
        on the visible block, is that the first divergence is a register-class
        divergence rather than a structural one -- which says the decision was
        made upstream even though it surfaces here.  Proving where upstream
        needs a pool trace, which this command does not read.
        """

        return "register-first-divergence" in self.signature

    def register_report(self) -> list[dict[str, Any]]:
        """Per aligned row register operands, including the matching rows.

        This is the readout a campaign agent otherwise reconstructs by running
        objdump and a regular expression once per variant.
        """

        return [
            {
                "index": row.index,
                "class": row.classification,
                "target": list(row.target_registers),
                "candidate": list(row.candidate_registers),
            }
            for row in self.rows
        ]

    def as_dict(self, *, report_regs: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "target": self.target,
            "candidate": self.candidate,
            "register_profile": self.register_profile,
            "target_instructions": self.target_instructions,
            "candidate_instructions": self.candidate_instructions,
            "aligned_rows": self.aligned_rows,
            "target_frame_size": self.target_frame_size,
            "candidate_frame_size": self.candidate_frame_size,
            "verdict": self.verdict,
            "playbook": self.playbook,
            "signature": list(self.signature),
            "prefix_exact": self.prefix_exact,
            "hunks": [item.as_dict() for item in self.hunks],
            "lanes": [item.as_dict() for item in self.lanes],
            "webs": [item.as_dict() for item in self.webs],
            "next": list(self.guidance),
            "warnings": list(self.warnings),
        }
        for name in CLASS_ORDER:
            payload[name] = self.counts.get(name, 0)
        if report_regs:
            payload["register_report"] = self.register_report()
        return payload


def _byte_range(value: tuple[int, int] | None) -> list[str] | None:
    return None if value is None else [f"0x{value[0]:x}", f"0x{value[1]:x}"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _address_index(instructions: Sequence[Instruction]) -> dict[int, int]:
    return {item.address: index for index, item in enumerate(instructions)}


def normalized_text(
    instruction: Instruction,
    *,
    address_index: dict[int, int],
    row_of_index: dict[int, int],
) -> str:
    """Return comparison text with alignment-relative branch destinations.

    A symbolized operand is rewritten to the *aligned row* of its destination
    when it resolves inside this function, so inserting an instruction does not
    turn every later branch into a phantom difference.  Relocated operands are
    never resolved that way: their address field is linker-supplied, and
    ``jal 0 <helper>`` would otherwise resolve to row 0.
    """

    relocated = bool(instruction.relocations)
    opcode = instruction.opcode

    def replace(match: re.Match[str]) -> str:
        name = match.group(2)
        if relocated:
            return f"<{name.split('+')[0]}>"
        if opcode not in SELF_BRANCH_OPCODES and not opcode.startswith("b"):
            return f"<{name.split('+')[0]}>"
        index = address_index.get(int(match.group(1), 16))
        if index is None:
            return f"<{name}>"
        row = row_of_index.get(index)
        return f"{ALIGNED_TARGET}{row}" if row is not None else f"@insn{index}"

    return SYMBOL_OPERAND_RE.sub(replace, instruction.assembly).replace("$", "")


def _relocation_signature(
    instruction: Instruction,
) -> tuple[tuple[str, str | None], ...]:
    return tuple((item.kind, item.symbol) for item in instruction.relocations)


def _relocation_kind_signature(instruction: Instruction) -> tuple[str, ...]:
    """Return the relocation layout used by the object-exact comparator."""

    return tuple(item.kind for item in instruction.relocations)


def _relocation_equivalent(target: Instruction, candidate: Instruction) -> bool:
    """Return whether the two words agree outside linker-controlled bits."""

    target_mask, target_unknown = relocation_field_mask(target)
    candidate_mask, candidate_unknown = relocation_field_mask(candidate)
    if target_unknown or candidate_unknown:
        return False
    keep = ~(target_mask | candidate_mask) & 0xFFFFFFFF
    return (target.word_value & keep) == (candidate.word_value & keep)


def _immediates(text: str) -> list[str]:
    return IMMEDIATE_RE.findall(SYMBOL_OPERAND_RE.sub("SYM", text))


def destination_register(assembly: str) -> str | None:
    """Return the register an instruction defines, or ``None``.

    Lane extraction records definitions in emission order; stores, branches and
    jumps read their operands and must not add slots.
    """

    if not assembly:
        return None
    opcode = assembly.split(maxsplit=1)[0]
    if opcode in NO_DESTINATION_OPCODES or opcode.startswith("c."):
        return None
    operands = register_operands(assembly)
    return operands[0] if operands else None


def classify_pair(
    target: Instruction,
    candidate: Instruction,
    *,
    target_text: str,
    candidate_text: str,
) -> str:
    """Classify one aligned instruction pair by the cheapest explanation."""

    if target_text == candidate_text:
        if target.word == candidate.word and _relocation_signature(
            target
        ) == _relocation_signature(candidate):
            return MATCH
        if ALIGNED_TARGET in target_text:
            # A branch to the same aligned row whose encoded displacement moved
            # because something was inserted between here and there.  Treating
            # it as a source difference would re-introduce the phantom cascade
            # the alignment removes, and calling it `match` would overclaim
            # byte identity, so it gets its own name.
            return DISPLACEMENT
        if _relocation_equivalent(target, candidate):
            return RELOCATION
        return STRUCTURAL
    target_registers = register_operands(target.assembly)
    candidate_registers = register_operands(candidate.assembly)
    if target_registers != candidate_registers:
        if is_commutative_swap(target, candidate):
            return COMMUTATIVE
        return REGISTER
    if _immediates(target_text) != _immediates(candidate_text):
        if _relocation_kind_signature(target) == _relocation_kind_signature(
            candidate
        ) and _relocation_equivalent(target, candidate):
            # The differing field is supplied by the linker, not by the source.
            # GNU objdump can name one side through a local jump-table symbol
            # and the other through its section symbol plus an encoded addend;
            # the object comparator deliberately compares relocation layout,
            # not those unstable spellings.
            return RELOCATION
        return CONSTANT
    return STRUCTURAL


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


def alignment_key(instruction: Instruction) -> str:
    """Return the text an instruction is anchored on during alignment.

    Symbolized operands collapse to the bare symbol: the numeric address and
    the ``+0x..`` offset both move when anything upstream changes size, and an
    anchor that moves is not an anchor.  Destinations are compared properly
    later, against the alignment this produces.
    """

    return SYMBOL_OPERAND_RE.sub(
        lambda match: f"<{match.group(2).split('+')[0]}>", instruction.assembly
    ).replace("$", "")


def _blocks(
    left: Sequence[str], right: Sequence[str]
) -> list[tuple[str, int, int, int, int]]:
    matcher = difflib.SequenceMatcher(a=list(left), b=list(right), autojunk=False)
    return list(matcher.get_opcodes())


def _skeleton(
    target: Sequence[Instruction], candidate: Sequence[Instruction]
) -> list[tuple[str, int | None, int | None]]:
    """Pair the two streams, choosing between two anchorings by evidence.

    Neither anchoring is safe alone, and both failures are real:

    * anchoring on opcodes cannot resolve a run of repeated opcodes.  Eight
      ``addu`` instructions with one inserted among them align position by
      position, and four correct instructions are then reported as register
      differences beside a phantom insertion;
    * anchoring on instruction text inherits ``difflib``'s greedy longest-block
      anchor.  On a stream whose text repeats -- a 64-instruction idiom copied
      down a long function -- the longest single common run can sit on the far
      side of the change, and the aligner throws away everything before it.

    So both are built and the one that explains more of the function as
    identical wins.  Ties go to the text anchoring, which is the one that
    cannot mispair by construction.
    """

    target_keys = [alignment_key(item) for item in target]
    candidate_keys = [alignment_key(item) for item in candidate]
    target_opcodes = [item.opcode for item in target]
    candidate_opcodes = [item.opcode for item in candidate]
    anchored = _pair(target_keys, candidate_keys, target_opcodes, candidate_opcodes)
    best = _alignment_score(anchored, target_keys, candidate_keys)
    if best[0] == min(len(target), len(candidate)):
        # Every instruction of the shorter side is already explained as
        # identical.  No alignment can beat that, so the second pass is skipped:
        # this is the common shape near the end of a campaign.
        return anchored
    alternative = _pair(target_opcodes, candidate_opcodes, target_keys, candidate_keys)
    if _alignment_score(alternative, target_keys, candidate_keys) > best:
        return alternative
    return anchored


def _alignment_score(
    rows: Sequence[tuple[str, int | None, int | None]],
    target_keys: Sequence[str],
    candidate_keys: Sequence[str],
) -> tuple[int, int]:
    """Score an alignment: identical pairs first, then compactness.

    This is the objective the greedy anchor only approximates -- explain as
    many instructions as possible as unchanged -- evaluated directly.
    """

    identical = sum(
        1
        for _, target_index, candidate_index in rows
        if target_index is not None
        and candidate_index is not None
        and target_keys[target_index] == candidate_keys[candidate_index]
    )
    return identical, -len(rows)


def _pair(
    target_primary: Sequence[str],
    candidate_primary: Sequence[str],
    target_secondary: Sequence[str],
    candidate_secondary: Sequence[str],
) -> list[tuple[str, int | None, int | None]]:
    """Align on the primary key, then pair inside each gap on the secondary."""

    rows: list[tuple[str, int | None, int | None]] = []
    for tag, target_start, target_end, candidate_start, candidate_end in _blocks(
        target_primary, candidate_primary
    ):
        if tag == "equal":
            rows.extend(
                ("equal", target_start + offset, candidate_start + offset)
                for offset in range(target_end - target_start)
            )
            continue
        rows.extend(
            _pair_within(
                target_secondary[target_start:target_end],
                candidate_secondary[candidate_start:candidate_end],
                target_offset=target_start,
                candidate_offset=candidate_start,
            )
        )
    return rows


def _pair_within(
    target: Sequence[str],
    candidate: Sequence[str],
    *,
    target_offset: int,
    candidate_offset: int,
) -> list[tuple[str, int | None, int | None]]:
    """Pair instructions inside one unmatched region on the secondary key.

    A pair produced here shares the secondary key but not the primary one, so
    it is exactly the population that operand-level classification exists for:
    same opcode, different registers or immediates.
    """

    rows: list[tuple[str, int | None, int | None]] = []
    for tag, target_start, target_end, candidate_start, candidate_end in _blocks(
        target, candidate
    ):
        width = (
            target_end - target_start
            if tag == "equal"
            else max(target_end - target_start, candidate_end - candidate_start)
        )
        for offset in range(width):
            target_index = target_start + offset
            candidate_index = candidate_start + offset
            rows.append(
                (
                    tag,
                    target_offset + target_index if target_index < target_end else None,
                    candidate_offset + candidate_index
                    if candidate_index < candidate_end
                    else None,
                )
            )
    return rows


def _substitutions(
    target_registers: Sequence[str], candidate_registers: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    if len(target_registers) != len(candidate_registers):
        return ()
    return tuple(
        (left, right)
        for left, right in zip(target_registers, candidate_registers, strict=True)
        if left != right
    )


# ---------------------------------------------------------------------------
# Lanes, webs, and signatures
# ---------------------------------------------------------------------------


def _register_class(register: str, profile: dict[str, tuple[str, ...]]) -> str | None:
    for name, members in profile.items():
        if register in members:
            return name
    return None


#: Evidence bar for calling a lane difference a rotation.  A constant cyclic
#: offset is findable over almost any small set of registers -- every swap of
#: two registers is trivially a rotation of a two-element cycle -- so a claim
#: this specific has to be paid for.  Both thresholds are deliberately blunt.
MINIMUM_ROTATION_CYCLE = 3
MINIMUM_ROTATION_SLOTS = 3


def _rotation_cycle(
    members: Sequence[str], observed: set[str]
) -> tuple[str, ...] | None:
    """Return the rotation cycle a lane is turning through, if there is one.

    The cycle is the observed registers in profile order, and it must be a
    *contiguous* run of the class table.  Measuring against the whole table
    would hide a real rotation whenever a function leaves one member unused
    (the IDO 5.3 temp class contains ``s8``, which no rotation visits), while
    accepting an arbitrary subset would let any two cherry-picked registers
    manufacture a cycle.  Contiguity is what a queue actually produces.
    """

    positions = [index for index, name in enumerate(members) if name in observed]
    if len(positions) < MINIMUM_ROTATION_CYCLE:
        return None
    if positions != list(range(positions[0], positions[-1] + 1)):
        return None
    return tuple(members[index] for index in positions)


def _lane_rotation(
    target: Sequence[str], candidate: Sequence[str], cycle: Sequence[str], start: int
) -> int | None:
    """Return the constant cyclic offset mapping the target tail onto the candidate.

    A temp rotation whose phase entered the block one slot early shows up as a
    single non-zero offset shared by every later slot: one upstream event, not
    N independent allocation decisions.  Fewer than
    ``MINIMUM_ROTATION_SLOTS`` diverging slots is not a phase; it is a swap
    that happens to be describable as one.
    """

    if len(target) != len(candidate) or not cycle or start >= len(target):
        return None
    if len(target) - start < MINIMUM_ROTATION_SLOTS:
        return None
    size = len(cycle)
    order = {name: index for index, name in enumerate(cycle)}
    offsets = set()
    for slot in range(start, len(target)):
        left = order.get(target[slot])
        right = order.get(candidate[slot])
        if left is None or right is None:
            return None
        offsets.add((right - left) % size)
    if len(offsets) != 1:
        return None
    offset = offsets.pop()
    return offset or None


def _build_lanes(
    rows: Sequence[AlignedRow], profile: dict[str, tuple[str, ...]]
) -> tuple[Lane, ...]:
    target_lanes: dict[str, list[tuple[str, int]]] = {name: [] for name in profile}
    candidate_lanes: dict[str, list[tuple[str, int]]] = {name: [] for name in profile}
    for row in rows:
        for assembly, bucket in (
            (row.target, target_lanes),
            (row.candidate, candidate_lanes),
        ):
            if assembly is None:
                continue
            register = destination_register(assembly)
            if register is None:
                continue
            name = _register_class(register, profile)
            if name is not None:
                bucket[name].append((register, row.index))

    lanes: list[Lane] = []
    for name in profile:
        target_slots = tuple(item[0] for item in target_lanes[name])
        candidate_slots = tuple(item[0] for item in candidate_lanes[name])
        target_rows = tuple(item[1] for item in target_lanes[name])
        candidate_rows = tuple(item[1] for item in candidate_lanes[name])
        if not target_slots and not candidate_slots:
            continue
        divergence: int | None = None
        for slot in range(max(len(target_slots), len(candidate_slots))):
            left = target_slots[slot] if slot < len(target_slots) else None
            right = candidate_slots[slot] if slot < len(candidate_slots) else None
            if left != right:
                divergence = slot
                break
        divergence_row: int | None = None
        if divergence is not None:
            candidates_rows = [
                rows_[divergence]
                for rows_ in (target_rows, candidate_rows)
                if divergence < len(rows_)
            ]
            divergence_row = min(candidates_rows) if candidates_rows else None
        cycle = _rotation_cycle(profile[name], set(target_slots) | set(candidate_slots))
        rotation = (
            None
            if divergence is None or cycle is None
            else _lane_rotation(target_slots, candidate_slots, cycle, divergence)
        )
        lanes.append(
            Lane(
                classification=name,
                target=target_slots,
                candidate=candidate_slots,
                target_rows=target_rows,
                candidate_rows=candidate_rows,
                divergence=divergence,
                divergence_row=divergence_row,
                rotation=rotation,
            )
        )
    return tuple(lanes)


def _build_webs(rows: Sequence[AlignedRow]) -> tuple[Web, ...]:
    """Group register substitutions so one swap reads as one web, not N sites."""

    order: list[tuple[str, str]] = []
    sites: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        if row.classification not in {REGISTER, COMMUTATIVE}:
            continue
        for pair in dict.fromkeys(row.substitutions):
            if pair not in sites:
                sites[pair] = []
                order.append(pair)
            sites[pair].append(row.index)
    return tuple(
        Web(
            web=f"w{number}",
            target=pair[0],
            candidate=pair[1],
            count=len(sites[pair]),
            rows=tuple(sites[pair]),
        )
        for number, pair in enumerate(order, 1)
    )


def _consistent_permutation(webs: Sequence[Web]) -> bool:
    """Return whether the register substitutions form one bijection."""

    if not webs:
        return False
    forward: dict[str, str] = {}
    backward: dict[str, str] = {}
    for web in webs:
        if forward.setdefault(web.target, web.candidate) != web.candidate:
            return False
        if backward.setdefault(web.candidate, web.target) != web.target:
            return False
    return True


def _prefix_exact(rows: Sequence[AlignedRow]) -> int | None:
    """Return the first aligned row whose instruction words differ."""

    for row in rows:
        if row.classification in {MATCH, RELOCATION, DISPLACEMENT}:
            continue
        return row.index
    return None


# ---------------------------------------------------------------------------
# Verdict and guidance
# ---------------------------------------------------------------------------


def _phase_shift(lanes: Sequence[Lane]) -> bool:
    """Return whether the lanes support a phase-shift claim.

    `phase-shift` is the most specific register verdict in the taxonomy and it
    dispatches the reader to a very particular lever (perturb the preceding
    block).  Being wrong about it is expensive, so it requires that *every*
    diverging lane is explained by a rotation.  One class turning while another
    diverges arbitrarily is two mechanisms, and the honest name for two
    mechanisms is `allocation`.
    """

    diverging = [lane for lane in lanes if lane.divergence is not None]
    if not diverging:
        return False
    return all(lane.rotation for lane in diverging)


def _verdict(
    counts: dict[str, int], lanes: Sequence[Lane], webs: Sequence[Web]
) -> tuple[str, str]:
    present = [name for name in MIXED_PRECEDENCE if counts.get(name)]
    if not present:
        if counts.get(RELOCATION) or counts.get(DISPLACEMENT):
            return "words-identical", "relocation-only"
        return "exact", "done"
    if present == [REGISTER]:
        if _phase_shift(lanes):
            return "phase-shift", "temp-fifo-phase"
        if _consistent_permutation(webs):
            return "register-permutation", "forced-color-oracle"
        return "allocation", "pool-position"
    if len(present) == 1:
        single = present[0]
        return {
            CONSTANT: ("constant", "constant-audit"),
            STRUCTURAL: ("structure", "structure-buckets"),
            SCHEDULE: ("schedule", "g0-schedule-probe"),
            COMMUTATIVE: ("commutative-order", "ast-shape"),
        }[single]
    composition = ", ".join(f"{name}:{counts[name]}" for name in present)
    _, playbook = _verdict({present[0]: counts[present[0]]}, lanes, webs)
    return f"mixed({composition})", playbook


def _primary_class(counts: dict[str, int]) -> str | None:
    for name in MIXED_PRECEDENCE:
        if counts.get(name):
            return name
    return RELOCATION if counts.get(RELOCATION) else None


def _guidance(
    verdict: str,
    counts: dict[str, int],
    lanes: Sequence[Lane],
    webs: Sequence[Web],
    hunks: Sequence[Hunk],
) -> tuple[str, ...]:
    """Return the lever family for the dominant class.

    Every line here is a field-note finding, not general advice: the point of
    the footer is to stop the next round from being spent on a dead family.

    These lines name the mechanism; they do not give the reader an address.
    `build_view` appends `field_guide.next_steps` for the playbook, which turns
    each named concept into a lever number, a one-line action, and a command to
    paste. The two are kept apart because this half is evidence-shaped -- it
    quotes counts and lanes from the run -- and that half is a fixed table.
    """

    lines: list[str] = []
    if verdict.startswith("mixed("):
        lines.append(
            "mixed residual: fix constants first (they cascade), structure "
            "second, register classes last."
        )
    primary = _primary_class(counts)
    if primary is None:
        return (
            "aligned instructions and relocation layout are identical for this "
            "function.",
            "run the project's normal collateral and full-output verification.",
        )
    if primary == RELOCATION:
        return (
            "every aligned difference is a linker-controlled relocation field.",
            "do not mutate source; verify with the project's link or ROM check.",
        )
    if primary == CONSTANT:
        lines.extend(
            [
                "audit the flag, enum, or literal against the target assembly "
                "FIRST: the assembly encodes the truth.",
                "one wrong identifier can present as a large structural cascade "
                "(183 words from a single flag mix-up).",
                "after fixing a constant, re-derive any fakes: they may have "
                "been fitted to the wrong body.",
                "a literal search is outside decomp_permuter's mutation space; "
                "this is hand work.",
            ]
        )
    elif primary == STRUCTURAL:
        first = hunks[0].hunk if hunks else 1
        lines.extend(
            [
                f"work the largest hunk first (hunk {first} is the earliest); "
                "bucket by region above ~500 instructions.",
                "if a hunk starts at a constant materialization (lui/andi/li), "
                "audit that constant before anything else.",
                "hold allocator experiments until the instruction count and "
                "opcode schedule stabilize.",
            ]
        )
    elif primary == SCHEDULE:
        lines.extend(
            [
                "equal instruction multiset in a different order: this is late "
                "scheduling, not allocation.",
                "recompile the candidate with -g0 as an ownership probe. A "
                "collapse proves debug line metadata constrains the -g3 "
                "schedule and that as1 can reach the target ordering.",
                "a -g0 collapse does not prove source correctness: a freer "
                "scheduler can rescue a non-original expression or statement "
                "shape. Compare topology and line tags before ending source "
                "search.",
                "statement and expression grouping is the source lever; "
                "replay-as1 tests whether as1 owns the ordering.",
            ]
        )
    elif primary == COMMUTATIVE:
        lines.extend(
            [
                "same opcode and operand multiset with the pair swapped: front-end "
                "AST shape, not allocation.",
                "`a | b` versus `b | a` canonicalizes identically (dead family); "
                "`x |= y` is a distinct AST and flips the emitted operand order.",
                "do not trace the allocator for this residual.",
            ]
        )
    elif verdict == "phase-shift":
        lane = next(
            (item for item in lanes if item.rotation and item.divergence is not None),
            None,
        )
        where = ""
        if lane is not None and lane.divergence is not None:
            where = (
                f" ({lane.classification} lane, slot {lane.divergence}, "
                f"aligned row {lane.divergence_row}, rotation +{lane.rotation})"
            )
        lines.extend(
            [
                f"one upstream event, not {counts.get(REGISTER, 0)} sites{where}.",
                "perturb the PRECEDING block: hoist a call-argument expression "
                "into a named local, which reorders value deaths.",
                "or materialize a phantom pool get with `(x == C) != 0` inside a "
                "real `if`; a bare discarded expression is dropped with no "
                "codegen effect.",
                "do not fix the divergent sites individually; declaration-order "
                "permutation is a dead family here.",
            ]
        )
    elif verdict == "register-permutation":
        mapping = ", ".join(f"{web.target}->{web.candidate}" for web in webs)
        lines.extend(
            [
                f"all register differences form one bijection ({mapping}): report "
                "it as a single decision, not N sites.",
                "callee-saved tie-breaks resist source search; prefer a forced "
                "color probe on an instrumented toolchain over more variants.",
            ]
        )
    else:
        lines.extend(
            [
                "register allocation differs with no consistent permutation. "
                "Name the family before searching:",
                "  temp-queue phase: perturb the preceding block, since value "
                "deaths set the phase entering it.",
                "  pool position: dead-web placement (`if (g) {}`) takes the NEXT "
                "FREE slot and cannot reach past a live web.",
                "  coalescing: return type (void versus implicit int) or CSE "
                "multiplicity.",
                "capture a globalcolor or ugen pool trace only if an instrumented "
                "toolchain is already configured.",
            ]
        )
    return tuple(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _hunks(rows: Sequence[AlignedRow]) -> tuple[Hunk, ...]:
    hunks: list[Hunk] = []
    current: list[AlignedRow] = []

    def flush() -> None:
        if not current:
            return
        classes: dict[str, int] = {}
        for row in current:
            classes[row.classification] = classes.get(row.classification, 0) + 1
        if len(classes) == 1:
            label = next(iter(classes))
        else:
            label = (
                "mixed("
                + ", ".join(
                    f"{name}:{classes[name]}" for name in CLASS_ORDER if name in classes
                )
                + ")"
            )
        target_indexes = [
            row.target_index for row in current if row.target_index is not None
        ]
        candidate_indexes = [
            row.candidate_index for row in current if row.candidate_index is not None
        ]
        target_addresses = [
            row.target_address for row in current if row.target_address is not None
        ]
        candidate_addresses = [
            row.candidate_address
            for row in current
            if row.candidate_address is not None
        ]
        hunks.append(
            Hunk(
                hunk=len(hunks) + 1,
                classification=label,
                start=current[0].index,
                end=current[-1].index,
                target_range=(
                    (min(target_indexes), max(target_indexes))
                    if target_indexes
                    else None
                ),
                candidate_range=(
                    (min(candidate_indexes), max(candidate_indexes))
                    if candidate_indexes
                    else None
                ),
                target_bytes=(
                    (min(target_addresses), max(target_addresses))
                    if target_addresses
                    else None
                ),
                candidate_bytes=(
                    (min(candidate_addresses), max(candidate_addresses))
                    if candidate_addresses
                    else None
                ),
                classes=classes,
            )
        )
        current.clear()

    for row in rows:
        if row.reported:
            current.append(row)
        else:
            flush()
    flush()
    return tuple(hunks)


def _runs(labels: Sequence[str]) -> list[tuple[int, int]]:
    """Return inclusive ranges of consecutive rows that need reporting.

    ``match``, ``displacement``, and ``relocation`` rows do not start a run:
    none is a source difference. Letting an alignment-controlled branch offset
    open a run would scatter one insertion across every branch that spans it;
    letting a relocated row open one would relabel linker metadata as schedule.
    """

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, label in enumerate(labels):
        if label in {MATCH, DISPLACEMENT, RELOCATION}:
            if start is not None:
                runs.append((start, index - 1))
                start = None
        elif start is None:
            start = index
    if start is not None:
        runs.append((start, len(labels) - 1))
    return runs


def _relabel_reorderings(
    labels: list[str],
    skeleton: Sequence[tuple[str, int | None, int | None]],
    target_keys: Sequence[str],
    candidate_keys: Sequence[str],
) -> None:
    """Promote pure reorderings from ``structural`` to ``schedule``.

    Opcode-level LCS reports a swap of two differently-named instructions as an
    adjacent delete and insert, which reads as new structure by volume.  A run
    whose two sides carry the same instructions in a different order is a late
    scheduling decision. Keys mask linker-controlled relocation fields, so
    unrelated jump-table addends elsewhere in the function cannot hide that
    fact.
    """

    def sides(start: int, end: int) -> tuple[list[str], list[str]]:
        left = [
            target_keys[index]
            for _, index, _ in skeleton[start : end + 1]
            if index is not None
        ]
        right = [
            candidate_keys[index]
            for _, _, index in skeleton[start : end + 1]
            if index is not None
        ]
        return sorted(left), sorted(right)

    runs = _runs(labels)
    if runs and sorted(target_keys) == sorted(candidate_keys) and target_keys:
        # Whole-function reordering: equal instruction multiset, different order.
        # The run labels are irrelevant here.  Two same-opcode instructions that
        # swapped places pair up as register differences, not as a delete beside
        # an insert, and counting those as allocation sends the reader to the
        # allocator for a scheduling decision.
        for start, end in runs:
            for index in range(start, end + 1):
                labels[index] = SCHEDULE
        return
    for start, end in runs:
        left, right = sides(start, end)
        if left and left == right:
            for index in range(start, end + 1):
                labels[index] = SCHEDULE


def _schedule_identity(instruction: Instruction, normalized: str) -> str:
    """Return an instruction identity stable across linker-controlled fields."""

    if ALIGNED_TARGET in normalized:
        return normalized
    mask, unknown = relocation_field_mask(instruction)
    if unknown:
        return f"{instruction.word}:{normalized}"
    kept_word = instruction.word_value & (~mask & 0xFFFFFFFF)
    kinds = ",".join(_relocation_kind_signature(instruction))
    return f"{kept_word:08x}:{kinds}"


def _unknown_relocations(*streams: Sequence[Instruction]) -> list[str]:
    """Return relocation kinds with no known field mask.

    Guessing a mask would turn a linker-controlled field into a false source
    problem, or worse, excuse a real one.  The classifier stays conservative and
    the signature says so out loud.
    """

    kinds: set[str] = set()
    for stream in streams:
        for item in stream:
            kinds.update(relocation_field_mask(item)[1])
    return sorted(kinds)


def _signature(
    rows: Sequence[AlignedRow],
    lanes: Sequence[Lane],
    prefix_exact: int | None,
    unknown_relocations: Sequence[str] = (),
) -> tuple[str, ...]:
    signature: list[str] = []
    signature.append(
        "prefix-exact@all" if prefix_exact is None else f"prefix-exact@{prefix_exact}"
    )
    for lane in lanes:
        if lane.divergence is not None:
            signature.append(
                f"state-divergence@{lane.classification}:{lane.divergence}"
            )
    if prefix_exact is not None:
        row = rows[prefix_exact]
        earliest = [
            lane.divergence_row for lane in lanes if lane.divergence_row is not None
        ]
        if (
            row.classification in {REGISTER, COMMUTATIVE}
            and earliest
            and min(earliest) <= prefix_exact
        ):
            signature.append("register-first-divergence")
    signature.extend(f"unknown-relocation:{kind}" for kind in unknown_relocations)
    return tuple(signature)


def build_view(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None = None,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
    warnings: Sequence[str] = (),
) -> MechanismView:
    """Align two instruction streams and classify the residual by mechanism."""

    try:
        profile = REGISTER_CLASS_PROFILES[register_profile]
    except KeyError:
        known = ", ".join(sorted(REGISTER_CLASS_PROFILES))
        raise ValueError(
            f"unknown register profile {register_profile!r}; known profiles: {known}"
        ) from None
    if not target or not candidate:
        missing = "target" if not target else "candidate"
        raise ValueError(
            f"no instructions to align on the {missing} side; "
            "check the symbol name and the section"
        )

    skeleton = _skeleton(target, candidate)
    row_of_target = {
        target_index: row
        for row, (_, target_index, _) in enumerate(skeleton)
        if target_index is not None
    }
    row_of_candidate = {
        candidate_index: row
        for row, (_, _, candidate_index) in enumerate(skeleton)
        if candidate_index is not None
    }
    target_addresses = _address_index(target)
    candidate_addresses = _address_index(candidate)
    target_text = [
        normalized_text(
            item, address_index=target_addresses, row_of_index=row_of_target
        )
        for item in target
    ]
    candidate_text = [
        normalized_text(
            item, address_index=candidate_addresses, row_of_index=row_of_candidate
        )
        for item in candidate
    ]
    target_schedule_keys = [
        _schedule_identity(item, text)
        for item, text in zip(target, target_text, strict=True)
    ]
    candidate_schedule_keys = [
        _schedule_identity(item, text)
        for item, text in zip(candidate, candidate_text, strict=True)
    ]

    labels: list[str] = []
    for tag, target_index, candidate_index in skeleton:
        if tag == "equal" and target_index is not None and candidate_index is not None:
            labels.append(
                classify_pair(
                    target[target_index],
                    candidate[candidate_index],
                    target_text=target_text[target_index],
                    candidate_text=candidate_text[candidate_index],
                )
            )
        else:
            labels.append(STRUCTURAL)
    _relabel_reorderings(
        labels,
        skeleton,
        target_schedule_keys,
        candidate_schedule_keys,
    )

    rows: list[AlignedRow] = []
    counts: dict[str, int] = {name: 0 for name in CLASS_ORDER}
    for index, (_, target_index, candidate_index) in enumerate(skeleton):
        target_item = target[target_index] if target_index is not None else None
        candidate_item = (
            candidate[candidate_index] if candidate_index is not None else None
        )
        classification = labels[index]
        target_registers = (
            tuple(register_operands(target_item.assembly))
            if target_item is not None
            else ()
        )
        candidate_registers = (
            tuple(register_operands(candidate_item.assembly))
            if candidate_item is not None
            else ()
        )
        rows.append(
            AlignedRow(
                index=index,
                classification=classification,
                target_index=target_index,
                candidate_index=candidate_index,
                target=target_item.assembly if target_item is not None else None,
                candidate=(
                    candidate_item.assembly if candidate_item is not None else None
                ),
                target_address=(
                    target_item.address if target_item is not None else None
                ),
                candidate_address=(
                    candidate_item.address if candidate_item is not None else None
                ),
                target_registers=target_registers,
                candidate_registers=candidate_registers,
                substitutions=(
                    _substitutions(target_registers, candidate_registers)
                    if classification in {REGISTER, COMMUTATIVE}
                    else ()
                ),
            )
        )
        counts[classification] = counts.get(classification, 0) + 1

    lanes = _build_lanes(rows, profile)
    webs = _build_webs(rows)
    hunks = _hunks(rows)
    prefix_exact = _prefix_exact(rows)
    verdict, playbook = _verdict(counts, lanes, webs)
    return MechanismView(
        symbol=symbol,
        target=target_name,
        candidate=candidate_name,
        register_profile=register_profile,
        target_instructions=len(target),
        candidate_instructions=len(candidate),
        target_frame_size=frame_size(_joined(target)),
        candidate_frame_size=frame_size(_joined(candidate)),
        counts=counts,
        verdict=verdict,
        playbook=playbook,
        signature=_signature(
            rows,
            lanes,
            prefix_exact,
            _unknown_relocations(target, candidate),
        ),
        prefix_exact=prefix_exact,
        rows=tuple(rows),
        hunks=hunks,
        lanes=lanes,
        webs=webs,
        guidance=_guidance(verdict, counts, lanes, webs, hunks) + next_steps(playbook),
        warnings=tuple(warnings),
    )


def aligned_class_counts(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> dict[str, int]:
    """Return the aligned residual counts for one pair of instruction streams.

    This is the analysis :func:`build_view` already performs, reduced to the
    numbers a comparison reports.  It exists so that ``compare`` can rank on
    aligned counts without growing a second aligner: two LCS implementations of
    one idea would eventually put different numbers under the same name in two
    commands, which is the class of defect the shared commutative predicate and
    the shared metric registry were introduced to end.
    """

    view = build_view(
        target,
        candidate,
        target_name="",
        candidate_name="",
        register_profile=register_profile,
    )
    return {name: view.counts.get(name, 0) for name in RESIDUAL_CLASSES}


def _joined(instructions: Iterable[Instruction]) -> str:
    return "\n".join(item.assembly for item in instructions)
