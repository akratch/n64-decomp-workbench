"""Layered object comparison oracles."""

from __future__ import annotations

import collections
import difflib
import hashlib
import re
from pathlib import Path

from .model import Comparison, Instruction, display_path
from .objdump import dump_object


REGISTER_RE = re.compile(
    r"\$(?:f\d+|zero|at|v[01]|a[0-3]|t\d|s\d|k[01]|gp|sp|fp|ra)\b"
)
FP_REGISTER_RE = re.compile(r"\$f\d+\b")
STACK_OFFSET_RE = re.compile(r"(-?(?:0x[0-9a-fA-F]+|\d+))\(\$?sp\)")
FRAME_RE = re.compile(
    r"(?:addiu|daddiu)\s+\$?sp\s*,\s*\$?sp\s*,\s*(-?(?:0x[0-9a-fA-F]+|\d+))"
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


def positional_mismatches(left: list[str], right: list[str]) -> int:
    """Count unequal aligned items plus the length difference."""

    return sum(a != b for a, b in zip(left, right)) + abs(
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
        match
        for instruction in instructions
        for match in FP_REGISTER_RE.findall(instruction.assembly)
    )
    return dict(sorted(counts.items(), key=lambda item: int(item[0][2:])))


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
    for expected, actual in zip(target, candidate):
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


def compare_instructions(
    target: list[Instruction],
    candidate: list[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None,
    target_text: str = "",
    candidate_text: str = "",
) -> Comparison:
    """Compare parsed instruction streams."""

    raw_target_words = [item.word for item in target]
    raw_candidate_words = [item.word for item in candidate]
    target_words, candidate_words, unknown_relocations = (
        relocation_aware_words(target, candidate)
    )
    target_opcodes = [item.opcode for item in target]
    candidate_opcodes = [item.opcode for item in candidate]
    target_normalized = [normalize_instruction(item.assembly) for item in target]
    candidate_normalized = [
        normalize_instruction(item.assembly) for item in candidate
    ]

    register_bad: list[int] = []
    fp_bad: list[int] = []
    register_diff: list[dict[str, object]] = []
    for index, (expected, actual) in enumerate(zip(target, candidate)):
        expected_registers = REGISTER_RE.findall(expected.assembly)
        actual_registers = REGISTER_RE.findall(actual.assembly)
        expected_fp = FP_REGISTER_RE.findall(expected.assembly)
        actual_fp = FP_REGISTER_RE.findall(actual.assembly)
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
    raw_mismatches = positional_mismatches(
        raw_target_words, raw_candidate_words
    )
    relocation_mismatches = positional_mismatches(
        [relocation_signature(item) for item in target],
        [relocation_signature(item) for item in candidate],
    )
    candidate_payload = "".join(raw_candidate_words).encode("ascii")
    return Comparison(
        candidate=candidate_name,
        target=target_name,
        symbol=symbol,
        target_instructions=len(target),
        candidate_instructions=len(candidate),
        instruction_delta=len(candidate) - len(target),
        raw_word_mismatches=raw_mismatches,
        word_mismatches=exact_mismatches,
        relocation_metadata_mismatches=relocation_mismatches,
        unknown_relocations=unknown_relocations,
        opcode_mismatches=positional_mismatches(
            target_opcodes, candidate_opcodes
        ),
        normalized_distance=sequence_distance(
            target_normalized, candidate_normalized
        ),
        register_mismatches=register_count,
        fp_register_mismatches=fp_count,
        register_mismatch_ranges=mismatch_ranges(register_bad),
        fp_mismatch_ranges=mismatch_ranges(fp_bad),
        target_frame_size=frame_size(
            "\n".join(item.assembly for item in target)
        ),
        candidate_frame_size=frame_size(
            "\n".join(item.assembly for item in candidate)
        ),
        candidate_fp_register_uses=fp_uses(candidate),
        candidate_stack_offsets=stack_offsets(candidate),
        candidate_sha1=hashlib.sha1(candidate_payload).hexdigest()[:12],
        candidate_sha256=hashlib.sha256(candidate_payload).hexdigest(),
        exact=(
            exact_mismatches == 0
            and relocation_mismatches == 0
            and not unknown_relocations
        ),
        register_diff=register_diff,
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

    target_text, target_instructions = dump_object(
        target, objdump=objdump, symbol=symbol, section=section
    )
    candidate_text, candidate_instructions = dump_object(
        candidate, objdump=objdump, symbol=symbol, section=section
    )
    return compare_instructions(
        target_instructions,
        candidate_instructions,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        target_text=target_text,
        candidate_text=candidate_text,
    )
