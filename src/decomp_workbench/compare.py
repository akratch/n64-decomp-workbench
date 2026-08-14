"""Layered object comparison oracles."""

from __future__ import annotations

import collections
import difflib
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from .commutative import CommutativeFinding, commutative_findings
from .elf_instructions import true_instruction_count as elf_true_instruction_count
from .field_guide import (
    AMBIGUOUS_PLAYBOOK_FAMILIES,
    COARSE_ALLOCATION_LEAD_IN,
    VERDICT_PLAYBOOKS,
    next_steps,
)
from .literal_pool import PoolReport
from .model import Comparison, Instruction, Relocation, display_path
from .objdump import (
    cross_function_warning,
    dump_object,
    symbol_labels,
    true_instruction_count,
)

REGISTER_RE = re.compile(
    r"(?<![A-Za-z0-9_$])\$?(?:f\d+|zero|at|v[01]|a[0-3]|t\d|s\d|k[01]|gp|sp|fp|ra)\b"
)
FP_REGISTER_RE = re.compile(r"(?<![A-Za-z0-9_$])\$?f\d+\b")
SYMBOLIZED_ADDRESS_RE = re.compile(r"\b[0-9a-fA-F]+\s+<[^>]+>")
STACK_OFFSET_RE = re.compile(r"(-?(?:0x[0-9a-fA-F]+|\d+))\(\$?sp\)")
FRAME_RE = re.compile(
    r"(?:addiu|daddiu)\s+\$?sp\s*,\s*\$?sp\s*,\s*(-?(?:0x[0-9a-fA-F]+|\d+))"
)
SAVE_SLOT_RE = re.compile(
    r"^(?P<opcode>sw|sd|sdc1)\s+"
    r"\$?(?P<register>s[0-8]|fp|ra|gp|f(?:20|22|24|26|28|30))\s*,\s*"
    r"(?P<offset>-?(?:0x[0-9a-fA-F]+|\d+))\(\$?sp\)"
)

# Bits supplied or adjusted by the linker for relocations commonly emitted in
# MIPS code sections. Unknown relocation kinds are deliberately *not* masked:
# silently guessing would turn the exact oracle into a false positive.
RELOCATION_FIELD_MASKS = {
    "R_MIPS_16": 0x0000FFFF,
    "R_MIPS_PC16": 0x0000FFFF,
    "R_MIPS_GPREL16": 0x0000FFFF,
    "R_MIPS_LITERAL": 0x0000FFFF,
    "R_MIPS_GOT16": 0x0000FFFF,
    "R_MIPS_CALL16": 0x0000FFFF,
    "R_MIPS_HI16": 0x0000FFFF,
    "R_MIPS_LO16": 0x0000FFFF,
    "R_MIPS_HIGHER": 0x0000FFFF,
    "R_MIPS_HIGHEST": 0x0000FFFF,
    "R_MIPS_GOT_DISP": 0x0000FFFF,
    "R_MIPS_GOT_PAGE": 0x0000FFFF,
    "R_MIPS_GOT_OFST": 0x0000FFFF,
    "R_MIPS_GOT_HI16": 0x0000FFFF,
    "R_MIPS_GOT_LO16": 0x0000FFFF,
    "R_MIPS_CALL_HI16": 0x0000FFFF,
    "R_MIPS_CALL_LO16": 0x0000FFFF,
    "R_MIPS_TLS_GD": 0x0000FFFF,
    "R_MIPS_TLS_LDM": 0x0000FFFF,
    "R_MIPS_DTPREL_HI16": 0x0000FFFF,
    "R_MIPS_DTPREL_LO16": 0x0000FFFF,
    "R_MIPS_GOTTPREL": 0x0000FFFF,
    "R_MIPS_TPREL_HI16": 0x0000FFFF,
    "R_MIPS_TPREL_LO16": 0x0000FFFF,
    "R_MIPS_26": 0x03FFFFFF,
    "R_MIPS_32": 0xFFFFFFFF,
    "R_MIPS_REL32": 0xFFFFFFFF,
    "R_MIPS_64": 0xFFFFFFFF,
}


def normalize_instruction(assembly: str) -> str:
    """Remove unstable addresses, immediates, and stack offsets."""

    value = re.sub(r"\b[0-9a-fA-F]+\s+<[^>]+>", "ADDR", assembly)
    value = re.sub(r"-?(?:0x[0-9a-fA-F]+|\d+)\(\$?sp\)", "OFF(sp)", value)
    value = re.sub(
        r"(?<![A-Za-z0-9_])-?(?:0x[0-9a-fA-F]+|\d+)\b",
        "IMM",
        value,
    )
    return value.replace("$", "")


def mismatch_ranges(indices: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted mismatch indices into inclusive ranges."""

    if not indices:
        return []
    result: list[tuple[int, int]] = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index != previous + 1:
            result.append((start, previous))
            start = index
        previous = index
    result.append((start, previous))
    return result


def positional_mismatches(left: Sequence[object], right: Sequence[object]) -> int:
    """Count unequal aligned items plus the length difference."""

    return sum(a != b for a, b in zip(left, right, strict=False)) + abs(
        len(left) - len(right)
    )


def sequence_distance(left: list[str], right: list[str]) -> int:
    """Return an insertion/deletion/replacement distance over sequences."""

    matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
    return sum(
        max(left_end - left_start, right_end - right_start)
        for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes()
        if tag != "equal"
    )


def frame_size(disassembly: str) -> int | None:
    """Extract the first stack-frame adjustment."""

    match = FRAME_RE.search(disassembly)
    return int(match.group(1), 0) if match else None


def frame_save_layout(instructions: list[Instruction]) -> dict[str, object]:
    """Partition a frame into observed save slots and everything else.

    This is deliberately an assembly observation, not a claim that the
    remainder is all source-local storage.  ABI padding, outgoing arguments,
    spills, and compiler temporaries can all occupy non-save bytes.
    """

    adjustment = frame_size("\n".join(item.assembly for item in instructions))
    slots: dict[int, tuple[int, set[str]]] = {}
    for instruction in instructions:
        match = SAVE_SLOT_RE.match(instruction.assembly.strip())
        if match is None:
            continue
        opcode = match.group("opcode")
        register = match.group("register")
        offset = int(match.group("offset"), 0)
        size = 4 if opcode == "sw" else 8
        previous_size, registers = slots.setdefault(offset, (size, set()))
        slots[offset] = (max(previous_size, size), registers)
        registers.add(register)
    rendered: list[dict[str, object]] = []
    occupied_bytes: set[int] = set()
    for offset, (size, slot_registers) in sorted(slots.items()):
        rendered_registers = sorted(slot_registers)
        occupied_bytes.update(range(offset, offset + size))
        rendered_slot: dict[str, object] = {
            "offset": offset,
            "bytes": size,
            "registers": rendered_registers,
        }
        if len(rendered_registers) == 1:
            rendered_slot["register"] = rendered_registers[0]
        rendered.append(rendered_slot)
    save_bytes = len(occupied_bytes)
    frame_bytes = None if adjustment is None else abs(adjustment)
    exceeds_frame = frame_bytes is not None and save_bytes > frame_bytes
    non_save = (
        None if frame_bytes is None or exceeds_frame else frame_bytes - save_bytes
    )
    return {
        "frame_adjustment": adjustment,
        "observed_save_slots": rendered,
        "observed_save_slot_count": len(rendered),
        "observed_save_bytes": save_bytes,
        "non_save_frame_bytes": non_save,
        "save_bytes_exceed_frame": exceeds_frame,
        "claim_boundary": (
            "Non-save bytes are not automatically source locals; they may "
            "include ABI padding, outgoing arguments, spills, or temporaries."
        ),
    }


def stack_offsets(instructions: list[Instruction]) -> dict[int, int]:
    """Count stack-relative operands in an instruction sequence."""

    counts: collections.Counter[int] = collections.Counter()
    for instruction in instructions:
        for value in STACK_OFFSET_RE.findall(instruction.assembly):
            counts[int(value, 0)] += 1
    return dict(sorted(counts.items()))


def fp_uses(instructions: list[Instruction]) -> dict[str, int]:
    """Count floating-point register operands."""

    counts = collections.Counter(
        f"${match.lstrip('$')}"
        for instruction in instructions
        for match in FP_REGISTER_RE.findall(instruction.assembly)
    )
    return dict(sorted(counts.items(), key=lambda item: int(item[0][2:])))


def register_operands(assembly: str, *, fp_only: bool = False) -> list[str]:
    """Return canonical register names across objdump dialects.

    GNU objdump builds disagree on whether MIPS register names are prefixed
    with ``$``.  Comparisons must treat ``t0`` and ``$t0`` as the same
    operand while still detecting a real allocation difference.
    """

    pattern = FP_REGISTER_RE if fp_only else REGISTER_RE
    operands = SYMBOLIZED_ADDRESS_RE.sub("ADDR", assembly)
    return [match.lstrip("$") for match in pattern.findall(operands)]


def relocation_field_mask(instruction: Instruction) -> tuple[int, list[str]]:
    """Return linker-controlled bits and unknown relocation kinds."""

    mask = 0
    unknown: list[str] = []
    for relocation in instruction.relocations:
        if relocation.kind in {"R_MIPS_NONE", "R_MIPS_JALR"}:
            continue
        field = RELOCATION_FIELD_MASKS.get(relocation.kind)
        if field is None:
            unknown.append(relocation.kind)
        else:
            mask |= field
    return mask, unknown


def relocation_aware_words(
    target: list[Instruction], candidate: list[Instruction]
) -> tuple[list[str], list[str], list[str]]:
    """Mask the union of known relocation fields at each aligned position."""

    target_words: list[str] = []
    candidate_words: list[str] = []
    unknown: set[str] = set()
    for expected, actual in zip(target, candidate, strict=False):
        expected_mask, expected_unknown = relocation_field_mask(expected)
        actual_mask, actual_unknown = relocation_field_mask(actual)
        unknown.update(expected_unknown)
        unknown.update(actual_unknown)
        keep = (~(expected_mask | actual_mask)) & 0xFFFFFFFF
        target_words.append(f"{expected.word_value & keep:08x}")
        candidate_words.append(f"{actual.word_value & keep:08x}")
    if len(target) > len(candidate):
        target_words.extend(item.word for item in target[len(candidate) :])
    elif len(candidate) > len(target):
        candidate_words.extend(item.word for item in candidate[len(target) :])
    return target_words, candidate_words, sorted(unknown)


def relocation_signature(instruction: Instruction) -> tuple[str, ...]:
    """Return relocation kinds without symbols or addends."""

    return tuple(item.kind for item in instruction.relocations)


def relocation_target_signature(
    instruction: Instruction,
) -> tuple[tuple[str, str | None], ...]:
    """Return relocation kinds together with their object-level targets."""

    return tuple((item.kind, item.symbol) for item in instruction.relocations)


RELOCATION_ADDEND_RE = re.compile(
    r"^(?P<symbol>.*?)(?P<addend>[+-](?:0x[0-9a-fA-F]+|\d+))$"
)


def relocation_target_parts(symbol: str | None) -> tuple[str | None, int]:
    """Split GNU objdump's ``symbol+addend`` spelling for reports."""

    if symbol is None:
        return None, 0
    match = RELOCATION_ADDEND_RE.match(symbol)
    if match is None or not match.group("symbol"):
        return symbol, 0
    return match.group("symbol"), int(match.group("addend"), 0)


def relocation_symbol_signature(
    instruction: Instruction,
) -> tuple[tuple[str, str | None], ...]:
    """Return relocation kinds with the target symbol, addend discarded.

    ``relocation_target_signature`` answers "does this site resolve to the
    same place", which a link can settle. This answers the strictly narrower
    "does this site name the same object", which no link can settle: a
    different symbol at the same position is a different variable being read.
    """

    return tuple(
        (item.kind, relocation_target_parts(item.symbol)[0])
        for item in instruction.relocations
    )


#: Section symbols GNU objdump prints where a relocation targets an anonymous
#: offset into a section rather than a named object. A candidate that reaches
#: one of these where the target names an object may have manufactured its own
#: private copy of storage another translation unit owns, which shifts the
#: linked layout even though every instruction bit agrees.
SECTION_SYMBOLS = frozenset({".text", ".data", ".rodata", ".bss", ".sdata", ".sbss"})


def relocation_difference_class(
    target: dict[str, object] | None, candidate: dict[str, object] | None
) -> str:
    """Name why one relocation site differs, from the two rendered sides.

    The distinction is the whole point of the classification: an addend-only
    difference is a layout coordinate the linker resolves, while a symbol
    difference is a semantic defect that survives linking.
    """

    if target is None or candidate is None:
        return "symbol"
    if target.get("symbol") != candidate.get("symbol"):
        return "symbol"
    if target.get("kind") != candidate.get("kind"):
        return "kind"
    return "addend"


def relocation_target_differences(
    target: Sequence[Instruction], candidate: Sequence[Instruction]
) -> list[dict[str, object]]:
    """Return every positional relocation target mismatch with both sides.

    Missing instructions and missing relocation entries are represented by
    ``None`` rather than compressed into a count. Offsets are retained for
    both objects because an insertion can make the two coordinates differ.
    """

    differences: list[dict[str, object]] = []
    width = max(len(target), len(candidate))
    for index in range(width):
        expected = target[index] if index < len(target) else None
        actual = candidate[index] if index < len(candidate) else None
        expected_relocations = expected.relocations if expected is not None else ()
        actual_relocations = actual.relocations if actual is not None else ()
        relocation_width = max(len(expected_relocations), len(actual_relocations))
        for relocation_index in range(relocation_width):
            left = (
                expected_relocations[relocation_index]
                if relocation_index < len(expected_relocations)
                else None
            )
            right = (
                actual_relocations[relocation_index]
                if relocation_index < len(actual_relocations)
                else None
            )
            left_signature = None if left is None else (left.kind, left.symbol)
            right_signature = None if right is None else (right.kind, right.symbol)
            if left_signature == right_signature:
                continue

            def payload(relocation: Relocation | None) -> dict[str, object] | None:
                if relocation is None:
                    return None
                base, addend = relocation_target_parts(relocation.symbol)
                return {
                    "offset": relocation.offset,
                    "kind": relocation.kind,
                    "symbol": base,
                    "addend": addend,
                    "raw_target": relocation.symbol,
                }

            left_payload = payload(left)
            right_payload = payload(right)
            difference_class = relocation_difference_class(left_payload, right_payload)
            candidate_symbol = (
                right_payload.get("symbol") if right_payload is not None else None
            )
            target_symbol = (
                left_payload.get("symbol") if left_payload is not None else None
            )
            differences.append(
                {
                    "instruction_index": index,
                    "relocation_index": relocation_index,
                    "difference": difference_class,
                    #: True when the candidate reaches an anonymous section
                    #: offset where the target names an object. That is the
                    #: shape of a duplicated literal or a privately copied
                    #: global, not of a benign late-rodata rename.
                    "candidate_section_symbol": (
                        difference_class == "symbol"
                        and candidate_symbol in SECTION_SYMBOLS
                        and target_symbol not in SECTION_SYMBOLS
                        and target_symbol is not None
                    ),
                    "target_instruction_offset": (
                        expected.address if expected is not None else None
                    ),
                    "candidate_instruction_offset": (
                        actual.address if actual is not None else None
                    ),
                    "target": left_payload,
                    "candidate": right_payload,
                }
            )
    return differences


# Integer and floating-point operations whose two source operands are
# interchangeable.  A swap here is front-end expression shape, never register
# allocation.
COMMUTATIVE_OPCODES = frozenset(
    {
        "add",
        "addu",
        "and",
        "dadd",
        "daddu",
        "dmult",
        "dmultu",
        "mult",
        "multu",
        "nor",
        "or",
        "xor",
        "add.d",
        "add.s",
        "mul.d",
        "mul.s",
    }
)

# Instructions whose differing field is a materialized constant rather than a
# memory offset.  Stack-frame adjustments are excluded: a frame delta is spill
# evidence, not a wrong flag or enum.
CONSTANT_OPCODES = frozenset(
    {
        "addiu",
        "andi",
        "daddiu",
        "li",
        "lui",
        "ori",
        "slti",
        "sltiu",
        "xori",
    }
)


#: Report keys for the LCS-aligned residual, one per aligned class a source
#: change controls.  The spellings are prefixed because an aligned count and a
#: positional count are different numbers: ``regs`` counts positions,
#: ``aligned_register`` counts aligned rows, and reading one through the other's
#: name is the mistake the whole registry exists to prevent.
ALIGNED_CLASS_KEYS: tuple[str, ...] = (
    "aligned_structural",
    "aligned_schedule",
    "aligned_register",
    "aligned_constant",
    "aligned_commutative",
)


#: Report keys for the alignment's own edit operations.  They are not residual
#: classes: a gap is the aligner deciding that two positions do not correspond
#: at all, which is exactly the condition that makes one candidate's aligned
#: row count incomparable with another's.
ALIGNMENT_GAP_KEYS: tuple[str, ...] = ("aligned_insertions", "aligned_deletions")

#: Positional mnemonic differences tolerated before ``aligned_total`` is
#: declared incomparable across candidates.  It is deliberately small rather
#: than zero: a single ``move``/``addu`` spelling difference is routine in an
#: otherwise pure register renaming, while a schedule or structure change moves
#: mnemonics by the hundred.
OPCODE_MISMATCH_CAUTION_THRESHOLD = 2


class AlignmentProgress(TypedDict):
    """Machine-readable allocation progress extracted from one view."""

    pool_exact: bool
    pool_prefix_exact: int | None
    temp_prefix_exact: int | None
    first_temp_divergence: dict[str, object] | None
    first_divergent_row: int | None
    alignment_method: str


def alignment_caution(
    *, insertions: int, deletions: int, opcode_mismatches: int
) -> str | None:
    """Return the cross-candidate comparability caution, or ``None``.

    ``aligned_total`` answers "how much of this candidate would a source change
    have to move", which is the right question *about one candidate*.  It is
    not a quantity two candidates can be compared on once the aligner has
    inserted gaps: a differently scheduled object realigns against a different
    subsequence of the target, and its row count can fall below a strictly
    better candidate's.  One campaign built a 257-build lever table on that
    inversion -- a candidate with 2924 mismatching words and 1813 opcode
    mismatches reported fewer aligned rows than the 1865-row base it was
    supposed to improve on.  The honest invariant is that
    ``aligned_total == word_mismatches`` only when the candidate is a pure
    register renaming; past that, ``raw``/``words`` is the comparable number.
    """

    gaps = insertions + deletions
    if gaps == 0 and opcode_mismatches <= OPCODE_MISMATCH_CAUTION_THRESHOLD:
        return None
    return (
        f"caution: alignment inserted {gaps} gaps "
        f"({opcode_mismatches} opcode mismatches) -- compare candidates on "
        "positional words (words=), not aligned rows"
    )


def aligned_residual_analysis(
    target: Sequence[Instruction], candidate: Sequence[Instruction]
) -> tuple[
    dict[str, int],
    dict[str, int],
    list[dict[str, object]],
    PoolReport | None,
    tuple[CommutativeFinding, ...],
    AlignmentProgress,
    list[dict[str, object]],
]:
    """Return aligned evidence, including late-stage prefix progress.

    Positional counting misranked candidates in six recorded campaigns: one
    inserted instruction shifts every later position, so a candidate that is one
    edit away reads as a long cascade and a candidate with a dozen scattered
    allocation differences looks closer.  The counts come from the ``view``
    analysis; nothing here re-implements the alignment.

    The gap counts come back beside them because they are the receipt for the
    counts: a row the aligner filled on one side only is a position the two
    objects do not share, and every such row is a reason not to read this
    candidate's aligned total against another candidate's.

    The fourth element is the literal-pool reading, which says how the two
    objects' pool accesses were resolved and how many slots each references.
    See :mod:`decomp_workbench.literal_pool`.

    The fifth is the commutative operand reading, which needs *every* aligned
    row and not only the reported ones: a swapped operand order in the source
    often leaves the arithmetic row byte-identical and shows up one row back,
    in the two operand loads. See :mod:`decomp_workbench.commutative`.
    """

    # ``view`` is built on top of this module, so the import is deferred rather
    # than inverting the layering for one call.
    from .view import (
        DISPLACEMENT,
        MATCH,
        POOL,
        POOL_LAYOUT,
        RELOCATION,
        RESIDUAL_CLASSES,
        Lane,
        build_view,
    )

    if not target or not candidate:
        # There is nothing to align against, so every instruction the other side
        # holds is structure.  Reporting zero would claim agreement that no
        # evidence supports.
        counts = dict.fromkeys(ALIGNED_CLASS_KEYS, 0)
        counts["aligned_structural"] = max(len(target), len(candidate))
        gaps = {
            "aligned_insertions": 0 if target else len(candidate),
            "aligned_deletions": 0 if candidate else len(target),
        }
        sites: list[dict[str, object]] = [
            {
                "index": index if target else 0,
                "target_index": index if target else None,
                "candidate_index": index if candidate else None,
                "aligned_row": index,
                "class": "structural",
                "target": target[index].assembly if target else None,
                "candidate": candidate[index].assembly if candidate else None,
            }
            for index in range(max(len(target), len(candidate)))
        ]
        empty_progress: AlignmentProgress = {
            "pool_exact": not target and not candidate,
            "pool_prefix_exact": 0,
            "temp_prefix_exact": 0,
            "first_temp_divergence": None,
            "first_divergent_row": 0,
            "alignment_method": "lcs",
        }
        return (
            counts,
            gaps,
            sites,
            None,
            (),
            empty_progress,
            [
                {
                    "aligned_row": index,
                    "target_index": index if target else None,
                    "candidate_index": index if candidate else None,
                    "class": "structural",
                    "raw_exact": False,
                    "relocation_aware_exact": False,
                }
                for index in range(max(len(target), len(candidate)))
            ],
        )
    view = build_view(
        target,
        candidate,
        target_name="",
        candidate_name="",
    )
    counts = {f"aligned_{name}": view.counts.get(name, 0) for name in RESIDUAL_CLASSES}
    gaps = {
        "aligned_insertions": sum(1 for row in view.rows if row.target_index is None),
        "aligned_deletions": sum(1 for row in view.rows if row.candidate_index is None),
    }
    next_target = len(target)
    anchors: dict[int, int] = {}
    for row in reversed(view.rows):
        if row.target_index is not None:
            next_target = row.target_index
        anchors[row.index] = next_target
    sites = [
        {
            "index": anchors[row.index],
            "target_index": row.target_index,
            "candidate_index": row.candidate_index,
            "aligned_row": row.index,
            "class": row.classification,
            "target": row.target,
            "candidate": row.candidate,
        }
        for row in view.rows
        if row.reported
    ]
    pool = (
        None
        if view.pool is None
        else PoolReport(
            resolution=view.pool.resolution,
            matches=view.counts.get(POOL, 0),
            layout_mismatches=view.counts.get(POOL_LAYOUT, 0),
            target_slots=view.pool.target_slots,
            candidate_slots=view.pool.candidate_slots,
        )
    )
    pool_lanes = [lane for lane in view.lanes if lane.classification == "pool"]
    temp_lanes = [
        lane for lane in view.lanes if lane.classification in {"temp", "fp-temp"}
    ]

    def first_lane_divergence(lanes: Sequence[Lane]) -> Lane | None:
        diverging = [lane for lane in lanes if lane.divergence_row is not None]
        return min(
            diverging,
            key=lambda lane: (
                lane.divergence_row if lane.divergence_row is not None else 1 << 30
            ),
            default=None,
        )

    first_pool = first_lane_divergence(pool_lanes)
    first_temp = first_lane_divergence(temp_lanes)
    first_temp_payload = None
    if first_temp is not None:
        assert first_temp.divergence is not None
        assert first_temp.divergence_row is not None
        slot = first_temp.divergence
        target_registers = first_temp.target
        candidate_registers = first_temp.candidate
        first_temp_payload = {
            "class": first_temp.classification,
            "slot": slot,
            "aligned_row": first_temp.divergence_row,
            "target_register": (
                target_registers[slot] if slot < len(target_registers) else None
            ),
            "candidate_register": (
                candidate_registers[slot] if slot < len(candidate_registers) else None
            ),
            "rotation": first_temp.rotation,
        }
    pool_prefix = first_pool.divergence_row if first_pool is not None else None
    temp_prefix = first_temp.divergence_row if first_temp is not None else None
    progress: AlignmentProgress = {
        "pool_exact": first_pool is None,
        "pool_prefix_exact": pool_prefix,
        "temp_prefix_exact": temp_prefix,
        "first_temp_divergence": first_temp_payload,
        "first_divergent_row": view.prefix_exact,
        "alignment_method": (
            "positional-opcode"
            if len(target) == len(candidate)
            and all(
                left.opcode == right.opcode
                for left, right in zip(target, candidate, strict=True)
            )
            else "lcs"
        ),
    }
    row_receipts: list[dict[str, object]] = [
        {
            "aligned_row": row.index,
            "target_index": row.target_index,
            "candidate_index": row.candidate_index,
            "class": row.classification,
            "raw_exact": row.classification == MATCH,
            "relocation_aware_exact": row.classification
            in {MATCH, DISPLACEMENT, RELOCATION, POOL},
        }
        for row in view.rows
    ]
    return (
        counts,
        gaps,
        sites,
        pool,
        commutative_findings(view.rows),
        progress,
        row_receipts,
    )


def aligned_residual(
    target: Sequence[Instruction], candidate: Sequence[Instruction]
) -> dict[str, int]:
    """Return the LCS-aligned residual counts, keyed for the report."""

    counts, _, _, _, _, _, _ = aligned_residual_analysis(target, candidate)
    return counts


def commutative_swap(
    opcode: str, expected: Sequence[str], actual: Sequence[str]
) -> bool:
    """Return whether two operand lists are one swap of a commutative pair.

    This is the single commutative predicate: the positional comparator and the
    aligned view both classify a site through it. Two independent copies of this
    rule disagreed about the two-operand multiply form, and a residual that is
    ``commutative-order`` under one command and ``register`` under the other
    sends the reader to the allocator for a front-end question.

    Both operand shapes are recognized: the three-operand form
    (``or rd,rs,rt``) and the two-operand form used by the multiply and
    divide-style instructions that write ``hi``/``lo`` (``mult rs,rt``).

    ``a | b`` and ``b | a`` canonicalize identically in IDO 5.3, so a residual
    of this shape is a front-end AST question (compound assignment), never an
    allocator question.
    """

    if opcode not in COMMUTATIVE_OPCODES:
        return False
    if len(expected) != len(actual):
        return False
    if len(expected) == 2:
        sources, other = tuple(expected), tuple(actual)
    elif len(expected) == 3:
        if expected[0] != actual[0]:
            return False
        sources, other = tuple(expected[1:]), tuple(actual[1:])
    else:
        return False
    return (
        sources[0] == other[1] and sources[1] == other[0] and sources[0] != sources[1]
    )


def is_commutative_swap(expected: Instruction, actual: Instruction) -> bool:
    """Return whether two instructions differ only by swapped source operands."""

    if expected.opcode != actual.opcode:
        return False
    return commutative_swap(
        expected.opcode,
        register_operands(expected.assembly),
        register_operands(actual.assembly),
    )


def is_constant_difference(expected: Instruction, actual: Instruction) -> bool:
    """Return whether two instructions differ only by a materialized constant."""

    if expected.opcode != actual.opcode or expected.opcode not in CONSTANT_OPCODES:
        return False
    if FRAME_RE.search(expected.assembly) or FRAME_RE.search(actual.assembly):
        return False
    return register_operands(expected.assembly) == register_operands(actual.assembly)


def classify_diff_site(
    expected: Instruction, actual: Instruction, *, masked_equal: bool
) -> str:
    """Name the cheapest mechanism that explains one differing site."""

    if masked_equal:
        if relocation_signature(expected) != relocation_signature(actual):
            return "relocation-layout"
        return "relocation-controlled"
    if expected.opcode != actual.opcode:
        return "opcode"
    if is_commutative_swap(expected, actual):
        return "commutative-order"
    if register_operands(expected.assembly) != register_operands(actual.assembly):
        return "register"
    if is_constant_difference(expected, actual):
        return "constant"
    return "operand"


def diff_sites(
    target: list[Instruction],
    candidate: list[Instruction],
    target_words: list[str],
    candidate_words: list[str],
) -> list[dict[str, object]]:
    """Return every differing site, classified and never filtered.

    A verdict chooses emphasis; it must never hide evidence.  A register-range
    summary once omitted a ``li v0,33`` versus ``li v0,49`` literal difference
    that the same report counted in ``raw``, and the omission cost a
    mis-scoped experiment.  Every position that differs in instruction words or
    in relocation kinds appears here, whatever the verdict says.
    """

    sites: list[dict[str, object]] = []
    aligned = min(len(target), len(candidate))
    for index in range(aligned):
        expected = target[index]
        actual = candidate[index]
        masked_equal = target_words[index] == candidate_words[index]
        if expected.word == actual.word and relocation_signature(
            expected
        ) == relocation_signature(actual):
            continue
        sites.append(
            {
                "index": index,
                "class": classify_diff_site(
                    expected, actual, masked_equal=masked_equal
                ),
                "target": expected.assembly,
                "candidate": actual.assembly,
                "target_word": expected.word,
                "candidate_word": actual.word,
            }
        )
    for index in range(aligned, max(len(target), len(candidate))):
        expected_extra = target[index] if index < len(target) else None
        actual_extra = candidate[index] if index < len(candidate) else None
        sites.append(
            {
                "index": index,
                "class": "instruction-count",
                "target": expected_extra.assembly if expected_extra else "-",
                "candidate": actual_extra.assembly if actual_extra else "-",
                "target_word": expected_extra.word if expected_extra else "-",
                "candidate_word": actual_extra.word if actual_extra else "-",
            }
        )
    return sites


def diff_site_classes(sites: list[dict[str, object]]) -> dict[str, int]:
    """Count differing sites per class in a stable order."""

    counts = collections.Counter(str(site["class"]) for site in sites)
    return dict(sorted(counts.items()))


def raw_difference_breakdown(
    target: list[Instruction],
    candidate: list[Instruction],
    target_words: list[str],
    candidate_words: list[str],
) -> dict[str, int]:
    """Classify raw differences without hiding the reason they disappeared.

    ``raw_word_mismatches`` is deliberately retained because it is useful for
    checking literal byte identity.  It should not, however, send a user back
    to source when every differing bit is linker-controlled.  The buckets are
    positional and sum to the raw mismatch count.
    """

    result = collections.Counter[str]()
    aligned = min(len(target), len(candidate))
    for index in range(aligned):
        if target[index].word == candidate[index].word:
            continue
        if target_words[index] != candidate_words[index]:
            result["instruction_bits"] += 1
        elif relocation_signature(target[index]) != relocation_signature(
            candidate[index]
        ):
            result["relocation_layout"] += 1
        else:
            result["relocation_controlled"] += 1
    result["instruction_bits"] += abs(len(target) - len(candidate))
    return {name: count for name, count in sorted(result.items()) if count}


def mixed_site_callouts(site_classes: dict[str, int]) -> list[str]:
    """Name cheaper mechanisms hiding inside a broader residual.

    A verdict summarizes the whole residual, but a constant or a commutative
    swap inside it is still the cheapest thing to fix first, and both are
    levers the summarizing verdict would otherwise send to the wrong layer.
    """

    callouts: list[str] = []
    if site_classes.get("constant"):
        callouts.append(
            "Some differing sites are constant materializations: audit the "
            "flag, enum, or constant against the assembly first, since one "
            "wrong identifier can present as a much larger residual."
        )
    if site_classes.get("commutative-order"):
        callouts.append(
            "Some differing sites are swapped sources of a commutative "
            "operation: that part is expression shape (`x |= y`), not "
            "allocation."
        )
    return callouts


def comparison_guidance(
    *,
    exact: bool,
    structural_exact: bool,
    raw_difference_breakdown: dict[str, int],
    relocation_mismatches: int,
    relocation_symbol_mismatches: int,
    unknown_relocations: list[str],
    opcode_mismatches: int,
    instruction_delta: int,
    register_mismatches: int,
    site_classes: dict[str, int],
    instruction_multiset_equal: bool,
    aligned_counts: dict[str, int],
    target_frame_size: int | None = None,
    candidate_frame_size: int | None = None,
) -> tuple[str, list[str]]:
    """Return a concise verdict, the next action, and the field-guide on-ramp.

    `_comparison_guidance` decides what is true about these two objects. This
    wrapper adds the part that is true about the *verdict* regardless of the
    inputs: which numbered levers move it, and the command that prints them.
    Appending here rather than in each branch is what keeps `compare` and
    `view` saying the same thing about the same mechanism.
    """

    verdict, guidance = _comparison_guidance(
        exact=exact,
        structural_exact=structural_exact,
        raw_difference_breakdown=raw_difference_breakdown,
        relocation_mismatches=relocation_mismatches,
        relocation_symbol_mismatches=relocation_symbol_mismatches,
        unknown_relocations=unknown_relocations,
        opcode_mismatches=opcode_mismatches,
        instruction_delta=instruction_delta,
        register_mismatches=register_mismatches,
        site_classes=site_classes,
        instruction_multiset_equal=instruction_multiset_equal,
        aligned_counts=aligned_counts,
        target_frame_size=target_frame_size,
        candidate_frame_size=candidate_frame_size,
    )
    playbook = VERDICT_PLAYBOOKS.get(verdict)
    if playbook is not None:
        lead_in = (
            (COARSE_ALLOCATION_LEAD_IN,)
            if playbook in AMBIGUOUS_PLAYBOOK_FAMILIES
            else ()
        )
        guidance.extend(next_steps(playbook, lead_in=lead_in))
    return verdict, guidance


def _comparison_guidance(
    *,
    exact: bool,
    structural_exact: bool,
    raw_difference_breakdown: dict[str, int],
    relocation_mismatches: int,
    relocation_symbol_mismatches: int,
    unknown_relocations: list[str],
    opcode_mismatches: int,
    instruction_delta: int,
    register_mismatches: int,
    site_classes: dict[str, int],
    instruction_multiset_equal: bool,
    aligned_counts: dict[str, int],
    target_frame_size: int | None = None,
    candidate_frame_size: int | None = None,
) -> tuple[str, list[str]]:
    """Return a concise verdict and the next useful user action."""

    controlled = raw_difference_breakdown.get("relocation_controlled", 0)
    if exact:
        if relocation_symbol_mismatches:
            # `exact` only means the masked words and the relocation *kinds*
            # agree. It says nothing about which symbol each site names, so
            # this branch must not reach the "no source change is indicated"
            # sentence below: the sites genuinely read different variables.
            count = relocation_symbol_mismatches
            noun = "site" if count == 1 else "sites"
            return (
                "relocation-symbol-mismatch",
                [
                    "Instruction bits and relocation kinds agree, but "
                    f"{count} relocation {noun} name a different symbol in "
                    "each object.",
                    "That is a semantic difference no link resolves: the two "
                    "objects read different variables. Masking excludes those "
                    "words, so words= understates the residual here.",
                    "Read `relocation_target_differences` (or the terminal's "
                    "relocation target table) and reconcile each symbol "
                    "before treating this as a match.",
                ],
            )
        if controlled:
            return (
                "instruction-exact",
                [
                    "Instruction-exact: raw differences are linker-controlled "
                    f"relocation fields ({controlled} word(s)), all naming the "
                    "same symbol on both sides. "
                    "No source change is indicated for a linked-project match.",
                    "This is not raw-object exact: decomp.me can still assign a "
                    "non-zero score for the relocation addend or symbol shape. "
                    "Use check-scratch when a 100% site score is the goal.",
                    "Run the project's normal link or ROM verification "
                    "for the final proof.",
                ],
            )
        return (
            "instruction-words-identical",
            [
                "Instruction words and known relocation-kind layout are "
                "identical for the selected function. "
                "Run the project's normal final verification.",
            ],
        )
    if unknown_relocations:
        return (
            "unknown-relocation",
            [
                "Known instruction evidence may match, but an unrecognized "
                "relocation prevents a safe exact verdict.",
                "Add the relocation kind with a precise field mask before "
                "trusting this comparison.",
            ],
        )
    if relocation_mismatches and not raw_difference_breakdown.get("instruction_bits"):
        return (
            "relocation-layout-mismatch",
            [
                "Instruction bits match after relocation masking, but "
                "relocation layouts differ.",
                "Check translation-unit context, symbol spelling, and "
                "linked/ROM output before changing source.",
            ],
        )
    # Linker-controlled words are reported as sites but never name the
    # mechanism: they say nothing about the source.
    classes = {
        name
        for name, count in site_classes.items()
        if count and name != "relocation-controlled"
    }
    frame_mismatch = (
        target_frame_size is not None
        and candidate_frame_size is not None
        and target_frame_size != candidate_frame_size
    )
    # A compiler-sized frame appears twice in an otherwise identical function:
    # the negative prologue adjustment and the positive epilogue adjustment.
    # Calling that pair a generic constant mismatch sent users to flags and
    # literals even when every opcode and register lane already matched.  Keep
    # this deliberately narrow; a third immediate means there is more than a
    # frame-size pair and belongs to the ordinary constant audit.
    if (
        frame_mismatch
        and aligned_counts.get("aligned_constant") == 2
        and not any(
            aligned_counts.get(name)
            for name in (
                "aligned_structural",
                "aligned_schedule",
                "aligned_register",
                "aligned_commutative",
            )
        )
        and raw_difference_breakdown.get("instruction_bits") == 2
        and not opcode_mismatches
        and not instruction_delta
        and not register_mismatches
    ):
        return (
            "frame-layout-mismatch",
            [
                "Register allocation, opcode schedule, and instruction count "
                "agree; only the symmetric stack adjustment differs "
                f"(target {target_frame_size}, candidate {candidate_frame_size}).",
                "Treat this as a stack-home/layout problem, not a literal "
                "audit: preserve the successful live-range topology while "
                "shrinking, reusing, or eliminating source-local homes.",
                "Ablate one local at a time and record both normalized residue "
                "and frame size; allocation-exact with the wrong frame is a "
                "useful intermediate, not acceptance.",
            ],
        )
    if classes == {"constant"}:
        return (
            "constant-mismatch",
            [
                "Every difference is an immediate on a constant-materializing "
                "instruction; opcodes and registers already agree.",
                "Audit the flag, enum, or constant against the target assembly "
                "first: the assembly encodes the truth, and one wrong "
                "identifier can present as a large structural difference.",
                "Re-derive any fake expressions afterwards; they may have been "
                "fitted to the wrong constant. Literal search is comparison "
                "work, not permuter work.",
            ],
        )
    if classes == {"commutative-order"}:
        return (
            "commutative-order",
            [
                "Same opcodes and same operands with the two sources of a "
                "commutative operation swapped: this is front-end expression "
                "shape, not register allocation.",
                "Reach for compound assignment. `a | b` and `b | a` "
                "canonicalize to the same object, but `x |= y` is a distinct "
                "expression tree and flips the emitted operand order.",
                "Do not trace the allocator for this residual.",
            ],
        )
    # A reordering only explains the whole residual when the two sides hold
    # the same instructions, registers included. Gating on the opcode
    # multiset alone would call a reordering that also moves a register
    # "not allocation" and send the next experiment to the wrong layer.
    aligned_schedule_only = bool(aligned_counts.get("aligned_schedule")) and not any(
        aligned_counts.get(name)
        for name in (
            "aligned_structural",
            "aligned_register",
            "aligned_constant",
            "aligned_commutative",
        )
    )
    if aligned_schedule_only or (
        instruction_multiset_equal
        and opcode_mismatches
        and not instruction_delta
        and classes <= {"opcode"}
    ):
        return (
            "schedule-mismatch",
            [
                "Instruction count and the full instruction multiset "
                "(registers included) are identical; only their order differs. "
                "This is late-pass scheduling, not allocation or control flow.",
                "Regroup expressions and statements rather than changing "
                "values or lifetimes.",
                "Ownership probe: rebuild the candidate with -g0. If the "
                "region collapses, debug line metadata constrains the -g3 "
                "schedule and the assembler can reach the target ordering.",
                "A -g0 collapse does not prove source correctness: a freer "
                "scheduler can rescue a non-original expression or statement "
                "shape. Compare source topology and line tags before declaring "
                "that search complete.",
                "`replay-as1` tests whether the final assembler pass owns the "
                "ordering.",
            ],
        )
    if opcode_mismatches or instruction_delta:
        return (
            "structure-mismatch",
            [
                *mixed_site_callouts(site_classes),
                "Instruction shape differs: work at the C/control-flow or "
                "expression-tree level first.",
                "Avoid allocator-only experiments until the instruction "
                "count and opcode schedule stabilize.",
            ],
        )
    if register_mismatches:
        frame_mismatch = (
            target_frame_size is not None
            and candidate_frame_size is not None
            and target_frame_size != candidate_frame_size
        )
        allocation_lead = (
            "Opcode schedule matches, but the stack frame differs "
            f"(target {target_frame_size}, candidate {candidate_frame_size}) "
            "alongside the register-allocation residue."
            if frame_mismatch
            else "Opcode shape matches but register allocation differs."
        )
        frame_gate = (
            [
                "Treat frame recovery as a separate acceptance gate: inspect "
                "callee-save usage, spills, and source-local stack homes. A "
                "smaller normalized register score cannot compensate for a "
                "wrong frame."
            ]
            if frame_mismatch
            else []
        )
        return (
            "allocation-mismatch",
            [
                *mixed_site_callouts(site_classes),
                allocation_lead,
                *frame_gate,
                # `compare` reports exactness; it cannot tell a temp-FIFO
                # phase from a pool position, and sending the reader to a
                # trace first inverted the documented order of work on the
                # command the README puts in front of every new user. `view`
                # answers the question this verdict raises, with no
                # instrumented toolchain, from the same two inputs.
                "Run `view` or `diagnose` on this pair next: it names the "
                "family - temp-FIFO phase, pool position, or coalescing - and "
                "the field-guide lever for it, with no instrumented toolchain "
                "required.",
                "Capture a globalcolor/UGEN trace only once the field-guide "
                "levers are exhausted AND an instrumented toolchain is already "
                "configured; it is the last step, not the first.",
            ],
        )
    if structural_exact:
        return (
            "operand-mismatch",
            [
                "Opcode, normalized instruction shape, registers, frame, "
                "and instruction count agree, but literal operands differ.",
                "Use --cross-rom only when the inputs are intentionally from "
                "different revisions; otherwise inspect the localized operands.",
            ],
        )
    return (
        "operand-mismatch",
        [
            "Instruction shape is close, but operands or immediates still "
            "differ. Inspect the localized diff.",
        ],
    )


def compare_instructions(
    target: list[Instruction],
    candidate: list[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None,
    warnings: Sequence[str] = (),
    target_true_instructions: int | None = None,
    candidate_true_instructions: int | None = None,
    instruction_count_verified: bool = False,
) -> Comparison:
    """Compare parsed instruction streams.

    `warnings` carries conditions the caller detected about the *inputs* --
    the loader knows which symbols each dump defines, and this function only
    ever sees two instruction lists -- so that one report object holds both the
    verdict and the reasons not to trust it.

    `target_true_instructions`/`candidate_true_instructions` are the real,
    unpadded instruction counts when a caller with access to the object files
    already measured them from the ELF `.text` section (see
    `elf_instructions.true_instruction_count`); `instruction_count_verified`
    says so. Omitted (the default for any `-dumps` entry point, which has no
    object file to read), both are derived here from the same trimming rule
    applied to the parsed instructions themselves -- less independent, since
    it is the same data `target_instructions`/`candidate_instructions` came
    from, but identical in method and exactly as good as the disassembly.
    """

    raw_target_words = [item.word for item in target]
    raw_candidate_words = [item.word for item in candidate]
    target_words, candidate_words, unknown_relocations = relocation_aware_words(
        target, candidate
    )
    target_opcodes = [item.opcode for item in target]
    candidate_opcodes = [item.opcode for item in candidate]
    target_normalized = [normalize_instruction(item.assembly) for item in target]
    candidate_normalized = [normalize_instruction(item.assembly) for item in candidate]

    register_bad: list[int] = []
    fp_bad: list[int] = []
    register_diff: list[dict[str, object]] = []
    for index, (expected, actual) in enumerate(zip(target, candidate, strict=False)):
        expected_registers = register_operands(expected.assembly)
        actual_registers = register_operands(actual.assembly)
        expected_fp = register_operands(expected.assembly, fp_only=True)
        actual_fp = register_operands(actual.assembly, fp_only=True)
        if expected_registers != actual_registers:
            register_bad.append(index)
            register_diff.append(
                {
                    "index": index,
                    "target": expected.assembly,
                    "candidate": actual.assembly,
                    "target_registers": expected_registers,
                    "candidate_registers": actual_registers,
                }
            )
        if expected_fp != actual_fp:
            fp_bad.append(index)

    length_extra = abs(len(target) - len(candidate))
    register_count = len(register_bad) + length_extra
    fp_count = len(fp_bad) + length_extra
    exact_mismatches = positional_mismatches(target_words, candidate_words)
    raw_mismatches = positional_mismatches(raw_target_words, raw_candidate_words)
    relocation_mismatches = positional_mismatches(
        [relocation_signature(item) for item in target],
        [relocation_signature(item) for item in candidate],
    )
    relocation_target_mismatches = positional_mismatches(
        [relocation_target_signature(item) for item in target],
        [relocation_target_signature(item) for item in candidate],
    )
    relocation_symbol_mismatches = positional_mismatches(
        [relocation_symbol_signature(item) for item in target],
        [relocation_symbol_signature(item) for item in candidate],
    )
    candidate_payload = "".join(raw_candidate_words).encode("ascii")
    target_frame = frame_size("\n".join(item.assembly for item in target))
    candidate_frame = frame_size("\n".join(item.assembly for item in candidate))
    target_frame_layout = frame_save_layout(target)
    candidate_frame_layout = frame_save_layout(candidate)
    structural_exact = (
        len(target) == len(candidate)
        and sequence_distance(target_normalized, candidate_normalized) == 0
        and positional_mismatches(target_opcodes, candidate_opcodes) == 0
        and register_count == 0
        and fp_count == 0
        and target_frame == candidate_frame
    )
    (
        aligned,
        aligned_gaps,
        aligned_sites,
        pool,
        commutative,
        progress,
        row_receipts,
    ) = aligned_residual_analysis(target, candidate)
    relocation_differences = relocation_target_differences(target, candidate)
    breakdown = raw_difference_breakdown(
        target, candidate, target_words, candidate_words
    )
    sites = diff_sites(target, candidate, target_words, candidate_words)
    site_classes = diff_site_classes(sites)
    opcode_mismatches = positional_mismatches(target_opcodes, candidate_opcodes)
    caution = alignment_caution(
        insertions=aligned_gaps["aligned_insertions"],
        deletions=aligned_gaps["aligned_deletions"],
        opcode_mismatches=opcode_mismatches,
    )
    exact = (
        exact_mismatches == 0 and relocation_mismatches == 0 and not unknown_relocations
    )
    verdict, guidance = comparison_guidance(
        exact=exact,
        structural_exact=structural_exact,
        raw_difference_breakdown=breakdown,
        relocation_mismatches=relocation_mismatches,
        relocation_symbol_mismatches=relocation_symbol_mismatches,
        unknown_relocations=unknown_relocations,
        opcode_mismatches=opcode_mismatches,
        instruction_delta=len(candidate) - len(target),
        register_mismatches=register_count,
        site_classes=site_classes,
        instruction_multiset_equal=(
            collections.Counter(target_normalized)
            == collections.Counter(candidate_normalized)
        ),
        aligned_counts=aligned,
        target_frame_size=target_frame,
        candidate_frame_size=candidate_frame,
    )
    if target_frame != candidate_frame:
        target_save_bytes = target_frame_layout["observed_save_bytes"]
        candidate_save_bytes = candidate_frame_layout["observed_save_bytes"]
        target_non_save = target_frame_layout["non_save_frame_bytes"]
        candidate_non_save = candidate_frame_layout["non_save_frame_bytes"]
        if target_save_bytes == candidate_save_bytes:
            guidance.insert(
                min(2, len(guidance)),
                "Observed save slots account for the same "
                f"{target_save_bytes} byte(s) on both sides; non-save frame "
                f"bytes differ ({target_non_save} -> {candidate_non_save}). "
                "Search ABI padding, outgoing arguments, spills, or local/temp "
                "homes rather than the saved-register set.",
            )
    resolved_target_true = (
        target_true_instructions
        if target_true_instructions is not None
        else true_instruction_count(target)
    )
    resolved_candidate_true = (
        candidate_true_instructions
        if candidate_true_instructions is not None
        else true_instruction_count(candidate)
    )
    resolved_warnings = list(warnings)
    if resolved_target_true != resolved_candidate_true:
        resolved_warnings.append(
            "true instruction count differs: target="
            f"{resolved_target_true} candidate={resolved_candidate_true} "
            f"(delta {resolved_candidate_true - resolved_target_true:+d}). "
            f".text is 16-byte padded, so target_instructions/"
            f"candidate_instructions ({len(target)}/{len(candidate)}) can "
            "agree even when the real function lengths do not -- any "
            "per-region or per-row analysis keyed on absolute position is "
            "unreliable until this is resolved."
        )
    return Comparison(
        candidate=candidate_name,
        target=target_name,
        symbol=symbol,
        target_instructions=len(target),
        candidate_instructions=len(candidate),
        instruction_delta=len(candidate) - len(target),
        raw_word_mismatches=raw_mismatches,
        word_mismatches=exact_mismatches,
        aligned_total=sum(aligned.values()),
        aligned_structural=aligned["aligned_structural"],
        aligned_schedule=aligned["aligned_schedule"],
        aligned_register=aligned["aligned_register"],
        aligned_constant=aligned["aligned_constant"],
        aligned_commutative=aligned["aligned_commutative"],
        relocation_metadata_mismatches=relocation_mismatches,
        relocation_target_mismatches=relocation_target_mismatches,
        relocation_symbol_mismatches=relocation_symbol_mismatches,
        unknown_relocations=unknown_relocations,
        opcode_mismatches=opcode_mismatches,
        normalized_distance=sequence_distance(target_normalized, candidate_normalized),
        register_mismatches=register_count,
        fp_register_mismatches=fp_count,
        register_mismatch_ranges=mismatch_ranges(register_bad),
        fp_mismatch_ranges=mismatch_ranges(fp_bad),
        target_frame_size=target_frame,
        candidate_frame_size=candidate_frame,
        candidate_fp_register_uses=fp_uses(candidate),
        candidate_stack_offsets=stack_offsets(candidate),
        candidate_sha1=hashlib.sha1(
            candidate_payload, usedforsecurity=False
        ).hexdigest()[:12],
        candidate_sha256=hashlib.sha256(candidate_payload).hexdigest(),
        exact=exact,
        structural_exact=structural_exact,
        raw_difference_breakdown=breakdown,
        verdict=verdict,
        guidance=guidance,
        register_diff=register_diff,
        diff_sites=sites,
        diff_site_classes=site_classes,
        aligned_diff_sites=aligned_sites,
        commutative_findings=[item.as_dict() for item in commutative],
        relocation_target_differences=relocation_differences,
        pool_exact=progress["pool_exact"],
        pool_prefix_exact=progress["pool_prefix_exact"],
        temp_prefix_exact=progress["temp_prefix_exact"],
        first_temp_divergence=(
            dict(progress["first_temp_divergence"])
            if isinstance(progress["first_temp_divergence"], dict)
            else None
        ),
        first_divergent_row=progress["first_divergent_row"],
        alignment_method=progress["alignment_method"],
        warnings=resolved_warnings,
        target_frame_layout=target_frame_layout,
        candidate_frame_layout=candidate_frame_layout,
        aligned_insertions=aligned_gaps["aligned_insertions"],
        aligned_deletions=aligned_gaps["aligned_deletions"],
        aligned_gaps=sum(aligned_gaps.values()),
        alignment_comparable=caution is None,
        alignment_caution=caution,
        pool_resolution=pool.resolution if pool is not None else None,
        pool_matches=pool.matches if pool is not None else 0,
        pool_layout_mismatches=pool.layout_mismatches if pool is not None else 0,
        target_pool_slots=pool.target_slots if pool is not None else 0,
        candidate_pool_slots=pool.candidate_slots if pool is not None else 0,
        target_true_instructions=resolved_target_true,
        candidate_true_instructions=resolved_candidate_true,
        true_instruction_delta=resolved_candidate_true - resolved_target_true,
        instruction_count_verified=(
            instruction_count_verified
            and target_true_instructions is not None
            and candidate_true_instructions is not None
        ),
        aligned_row_receipts=row_receipts,
    )


#: Printed once above a mixed ranking, because the ordering itself changed and
#: a reader who does not know that is reading a different table than the one
#: they ran yesterday.
MIXED_ALIGNMENT_CAUTION = (
    "caution: one or more candidates required alignment gaps -- ordered by "
    "positional words, not aligned rows"
)


def rank_comparisons(items: Sequence[Comparison]) -> tuple[list[Comparison], bool]:
    """Order candidates, and say whether positional ranking was required.

    Aligned rows are the right ranking metric only while every candidate is
    gap-free. Each gapped candidate may align against a different subsequence
    of the target; sharing the state "has gaps" does not put two such
    candidates back on one scale. Any gapped input therefore moves the whole
    set to positional word counts, and the caller is told so it can say so.
    """

    ordered = list(items)
    by_raw = any(not item.alignment_comparable for item in ordered)
    ordered.sort(key=lambda item: item.raw_sort_key if by_raw else item.sort_key)
    return ordered, by_raw


def resolve_true_instructions(
    path: str | Path, *, symbol: str | None, section: str
) -> int | None:
    """Read the true instruction count straight from the object's ELF.

    Only attempted for a whole-section comparison (``symbol is None``): the
    ELF read answers "how many real instructions are in this section",  which
    is the right question for the campaign's own single-function objects but
    a different one from "how long is the named symbol" once a section holds
    more than one function. A narrowed ``--symbol`` dump falls back to the
    disassembly-based count instead, which is already scoped to that symbol.

    Returns ``None`` on anything that stops a confident answer -- a missing
    file, a section this reader does not support -- so the caller falls back
    to the disassembly-based count rather than raising out of what is meant
    to be a cross-check, not a new way for `compare`/`diagnose` to fail.
    """

    if symbol is not None:
        return None
    try:
        return elf_true_instruction_count(path, section=section)
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class TargetObject:
    """A disassembled target retained for repeated comparison.

    Campaigns compare hundreds of candidates against one target. Holding the
    parsed target removes one objdump process and one parse per candidate.
    """

    name: str
    symbol: str | None
    instructions: list[Instruction]
    #: Every symbol the target dump defines, so a candidate can be checked
    #: against it without disassembling the target a second time.
    labels: tuple[str, ...] = ()
    text: str = ""
    #: The target's true instruction count read from its own ELF section, or
    #: ``None`` when no object file backed this target (see
    #: `resolve_true_instructions`). Held here so `compare_candidate` does not
    #: re-read the target's file for every candidate it compares.
    true_instructions: int | None = None
    #: Which section was disassembled. Carried so a comparison built from two
    #: already-loaded objects reports the same section in its warnings as one
    #: that loaded them itself.
    section: str = ".text"


def load_target(
    target: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
) -> TargetObject:
    """Disassemble the reference object once."""

    text, instructions = dump_object(
        target, objdump=objdump, symbol=symbol, section=section
    )
    return TargetObject(
        name=display_path(target),
        symbol=symbol,
        instructions=instructions,
        labels=symbol_labels(text),
        text=text,
        true_instructions=resolve_true_instructions(
            target, symbol=symbol, section=section
        ),
        section=section,
    )


def compare_loaded(target: TargetObject, candidate: TargetObject) -> Comparison:
    """Compare two already-disassembled objects.

    The form for a caller that needs the parsed instructions for something
    else as well -- `score`, which reads the same two streams a second time to
    build its screen line -- so nothing disassembles an object twice and no
    second copy of this argument list can drift from it.
    """

    warning = cross_function_warning(
        target.text,
        candidate.text,
        symbol=target.symbol,
        section=target.section,
    )
    return compare_instructions(
        target.instructions,
        candidate.instructions,
        target_name=target.name,
        candidate_name=candidate.name,
        symbol=target.symbol,
        warnings=(warning,) if warning else (),
        target_true_instructions=target.true_instructions,
        candidate_true_instructions=candidate.true_instructions,
        instruction_count_verified=(
            target.true_instructions is not None
            and candidate.true_instructions is not None
        ),
    )


def compare_candidate(
    target: TargetObject,
    candidate: str | Path,
    *,
    objdump: str | None = None,
    section: str = ".text",
) -> Comparison:
    """Compare one candidate object against an already-parsed target."""

    return compare_loaded(
        target,
        load_target(candidate, objdump=objdump, symbol=target.symbol, section=section),
    )


def compare_objects(
    target: str | Path,
    candidate: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
) -> Comparison:
    """Disassemble and compare two object files."""

    return compare_candidate(
        load_target(target, objdump=objdump, symbol=symbol, section=section),
        candidate,
        objdump=objdump,
        section=section,
    )
