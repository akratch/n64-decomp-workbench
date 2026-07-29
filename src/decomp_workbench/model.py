"""Data models shared by the workbench commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Relocation:
    """One relocation attached to an instruction word."""

    offset: int
    kind: str
    symbol: str | None = None


@dataclass(frozen=True)
class Instruction:
    """One instruction parsed from objdump output."""

    address: int
    word: str
    assembly: str
    relocations: tuple[Relocation, ...] = ()

    @property
    def opcode(self) -> str:
        return self.assembly.split(maxsplit=1)[0] if self.assembly else ""

    @property
    def word_value(self) -> int:
        return int(self.word, 16)


@dataclass
class Comparison:
    """Metrics for one candidate object compared with a target object."""

    candidate: str
    target: str
    symbol: str | None
    target_instructions: int
    candidate_instructions: int
    instruction_delta: int
    raw_word_mismatches: int
    word_mismatches: int
    relocation_metadata_mismatches: int
    unknown_relocations: list[str]
    opcode_mismatches: int
    normalized_distance: int
    register_mismatches: int
    fp_register_mismatches: int
    register_mismatch_ranges: list[tuple[int, int]]
    fp_mismatch_ranges: list[tuple[int, int]]
    target_frame_size: int | None
    candidate_frame_size: int | None
    candidate_fp_register_uses: dict[str, int]
    candidate_stack_offsets: dict[int, int]
    candidate_sha1: str
    candidate_sha256: str
    exact: bool
    structural_exact: bool
    raw_difference_breakdown: dict[str, int]
    verdict: str
    guidance: list[str]
    error: str | None = None
    register_diff: list[dict[str, Any]] = field(default_factory=list)
    diff_sites: list[dict[str, Any]] = field(default_factory=list)
    diff_site_classes: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, int, str]:
        return (
            self.word_mismatches,
            len(self.unknown_relocations),
            self.relocation_metadata_mismatches,
            self.normalized_distance,
            self.register_mismatches,
            abs(self.instruction_delta),
            self.candidate,
        )


@dataclass
class CompileResult:
    """Compilation status plus an optional object comparison."""

    source: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    object_path: str | None
    comparison: Comparison | None
    cache_key: str = ""
    cached: bool = False
    duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.comparison is not None:
            result["comparison"] = self.comparison.as_dict()
        return result


def display_path(path: str | Path) -> str:
    """Return a stable, user-friendly path where possible."""

    value = Path(path)
    try:
        return str(value.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(value)
