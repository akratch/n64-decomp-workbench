"""Data models shared by the workbench commands."""

from __future__ import annotations

import os
from collections.abc import Sequence
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
    relocation_target_mismatches: int
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
    #: Commutative operand pairs, each with the edit that would fix it. The
    #: class count above says how many rows are commutative; this says which
    #: expression to change, including the case where the arithmetic row is
    #: byte-identical and only its two operand loads are crossed. See
    #: ``decomp_workbench.commutative``.
    commutative_findings: list[dict[str, Any]] = field(default_factory=list)
    #: Position-by-position relocation differences. The aggregate counts are
    #: useful gates; these records are the source-editable receipt for them.
    relocation_target_differences: list[dict[str, Any]] = field(default_factory=list)
    #: Late-stage progress metrics from the aligned register lanes. They stay
    #: visible even when a candidate's total word score gets worse while the
    #: first allocation divergence moves substantially later.
    pool_exact: bool = True
    pool_prefix_exact: int | None = None
    temp_prefix_exact: int | None = None
    first_temp_divergence: dict[str, Any] | None = None
    first_divergent_row: int | None = None
    #: ``positional-opcode`` means equal-length, positionally opcode-identical
    #: streams were deliberately kept row-for-row instead of passed through
    #: an LCS that could manufacture gaps from repeated instruction text.
    alignment_method: str = "lcs"
    #: Conditions that make the verdict itself untrustworthy, as opposed to
    #: findings about the code. A reader who ignores one of these is reading a
    #: correct answer to the wrong question, so renderers print them ahead of
    #: the verdict line rather than beside the evidence.
    warnings: list[str] = field(default_factory=list)
    target_frame_layout: dict[str, Any] = field(default_factory=dict)
    candidate_frame_layout: dict[str, Any] = field(default_factory=dict)
    #: Aligned rows the aligner filled on one side only. They are the receipt
    #: for ``aligned_total``: every gap is a position the two objects do not
    #: share, so the row counts either side of one are counts of different
    #: things and cannot be read against another candidate's.
    aligned_insertions: int = 0
    aligned_deletions: int = 0
    aligned_gaps: int = 0
    #: Whether ``aligned_total`` may be compared with another candidate's.
    alignment_comparable: bool = True
    #: The one-line caution printed when it may not be, or ``None``.
    alignment_caution: str | None = None
    #: How the two objects' literal-pool accesses were resolved before
    #: classing: ``absolute`` (both anchor on section symbols, so the byte
    #: offset inside the section is comparable), ``anchor-correspondence`` (one
    #: side names each literal, so only the one-to-one correspondence of
    #: anchors is checkable), ``unresolved``, or ``None`` when neither object
    #: relocates a data reference. See ``decomp_workbench.literal_pool``.
    pool_resolution: str | None = None
    #: Aligned rows reading the same pool slot through differently named
    #: anchors. They are not reported as differences: the anchoring is a
    #: property of the two symbol tables, decided before either object exists.
    pool_matches: int = 0
    #: Aligned rows whose pool accesses resolve to genuinely different slots.
    pool_layout_mismatches: int = 0
    #: Distinct literal-pool slots each object references.
    target_pool_slots: int = 0
    candidate_pool_slots: int = 0
    #: The real, unpadded instruction count -- what
    #: ``objdump -d obj.o | grep -c '^ *[0-9a-f]*:'`` measures by hand.
    #: ``target_instructions``/``candidate_instructions`` above can include
    #: trailing `.text` alignment padding (the section is padded to a 16-byte,
    #: 4-instruction boundary), so two functions of different real length can
    #: report the same padded count -- a probe three instructions too long
    #: passed a campaign's gate exactly this way. Read from the object's own
    #: ELF section when a real object file was available and no ``--symbol``
    #: narrowed the dump (see ``instruction_count_verified``); otherwise
    #: derived from the same trimming rule applied to the parsed disassembly.
    #: Always populated -- never ``None`` -- because the text-based fallback
    #: needs nothing but the instructions already parsed for everything else.
    target_true_instructions: int = 0
    candidate_true_instructions: int = 0
    #: ``candidate_true_instructions - target_true_instructions``. The
    #: padding-safe ``instruction_delta``: that field can read zero when the
    #: two objects' *padded* counts happen to agree while their real lengths
    #: do not.
    true_instruction_delta: int = 0
    #: Whether both true counts above were read directly from the objects'
    #: own ELF `.text` sections (ground truth, byte-exact) rather than derived
    #: from parsed disassembly text (the identical rule, but only as reliable
    #: as the disassembly it was applied to). ``False`` for retained-dump
    #: comparisons, which have no object file to read, and for any comparison
    #: narrowed with ``--symbol``, where a whole-section ELF read would answer
    #: a different question than "how long is this function".
    instruction_count_verified: bool = False

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

    @property
    def raw_sort_key(self) -> tuple[int, int, int, int, int, int, int, str]:
        """Rank on the positional word counts, with the aligned residual last.

        This is the ordering used once a candidate set stops being comparable
        on aligned rows -- see :func:`~decomp_workbench.compare.rank_comparisons`.
        A gap-heavy object realigns against a different subsequence of the
        target, so its aligned total measures a different alignment; ``words``
        measures the same thing for every candidate whatever the aligner did.
        """

        return (
            self.word_mismatches,
            self.raw_word_mismatches,
            len(self.unknown_relocations),
            self.relocation_metadata_mismatches,
            self.opcode_mismatches,
            self.aligned_total,
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


def shorten_paths(names: Sequence[str]) -> tuple[dict[str, str], str | None]:
    """Strip the directory a census's candidates share, and name it once.

    A census pads its first column to the longest candidate name. Campaign
    objects live under one long absolute directory, so that column consumed
    the whole terminal and `--width` then elided the *data* -- leaving a table
    of paths and nothing else. The shared prefix is one fact, so it is printed
    once and the rows carry only what distinguishes them.

    Returns the name-to-label mapping and the sentence naming the prefix, or
    ``None`` when there is nothing worth stripping.
    """

    if len(names) < 2:
        return {name: name for name in names}, None
    parts = [Path(name).parts for name in names]
    if any(len(item) < 2 for item in parts):
        return {name: name for name in names}, None
    shared: list[str] = []
    # Paths of different depths are the normal case, so the shortest one ends
    # the comparison: strict=False is the behaviour wanted, stated explicitly.
    for column in zip(*parts, strict=False):
        # Never strip the final component: a row must keep a name.
        if len(set(column)) != 1 or len(shared) + 1 >= min(len(item) for item in parts):
            break
        shared.append(column[0])
    if not shared:
        return {name: name for name in names}, None
    prefix = Path(*shared)
    labels = {name: str(Path(*Path(name).parts[len(shared) :])) for name in names}
    if len(set(labels.values())) != len(set(names)):  # pragma: no cover - defensive
        return {name: name for name in names}, None
    return labels, f"paths are relative to {prefix}{os.sep}"
