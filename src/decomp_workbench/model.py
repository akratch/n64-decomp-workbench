"""Data models shared by the workbench commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .schema import canonical_fields


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
    aligned_total: int
    aligned_structural: int
    aligned_schedule: int
    aligned_register: int
    aligned_constant: int
    aligned_commutative: int
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
    aligned_diff_sites: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return the report keyed by the schema registry.

        Canonical keys are the same strings the terminal prints. The older
        long-form keys are emitted beside them as deprecated aliases so
        existing consumers keep working for one release.
        """

        payload = asdict(self)
        payload.update(canonical_fields(self))
        return payload

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, int, int, str]:
        """Rank on the aligned residual, with the positional count as a tiebreak.

        Positional word counts misranked candidates in six recorded campaigns:
        an inserted instruction shifts everything after it, so the candidate one
        edit away sorts below a candidate with a dozen unrelated allocation
        differences. The aligned residual is the ranking number; ``words`` still
        separates two candidates of the same aligned shape, where it is exactly
        the right question.
        """

        return (
            self.aligned_total,
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
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    artifacts: dict[str, str] = field(default_factory=dict)
    experiment: dict[str, Any] | None = None
    region: dict[str, Any] | None = None

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
