"""Run a batch of pipeline variants and cluster them by output bytes.

A compiler-era sweep once produced eleven differently-labeled outputs that
were byte-identical, because unknown flags fell back silently to defaults
(stderr was suppressed downstream) -- and a wrong "this axis is exhausted"
conclusion followed from it. Output-hash clustering into **attractors** was
the analytical device that later caught this class of mistake in the SSB64
drawbitmap campaign: dozens of pipeline variants collapsed into just two
distinct outputs, which is what proved the residue was not compiler-era
dependent.

`run_matrix` is the automated version of that device: run every variant, hash
each one's scored function bytes (never discarding stderr), and group
identical hashes into lettered attractors ordered by score. Two
differently-labeled variants landing in the same attractor is reported
plainly; every variant landing in the same attractor is reported as an
explicit caution, because that shape is exactly the one that produced a wrong
conclusion before.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .score import (
    ScoreError,
    ScoreReport,
    ScoreSpec,
    score_report,
    score_spec_from_dict,
)

#: Substituted with the per-variant output object path before the command runs.
OUTPUT_PLACEHOLDER = "$OUTPUT"

#: The human-factors core of `matrix`: a flag that silently fell back to a
#: default usually still says so on stderr, just not loudly. Matched
#: case-insensitively against every stderr line captured per variant.
SILENT_FALLBACK_RE = re.compile(r"unknown option|ignored|unrecognized", re.IGNORECASE)

#: Printed verbatim once every variant lands in the same attractor. Wording
#: chosen to name the exact prior failure, per the campaign postmortem.
ALL_COLLAPSED_CAUTION = (
    "every variant produced identical bytes -- verify the flags are actually "
    "accepted (this exact failure produced a wrong conclusion in the SSB64 "
    "drawbitmap campaign)."
)


@dataclass(frozen=True)
class Variant:
    label: str
    command: str


@dataclass(frozen=True)
class VariantResult:
    """The full record of one variant's run: never discards stderr."""

    label: str
    command: str
    returncode: int | None
    stdout: str
    stderr: str
    output_path: str | None
    output_exists: bool
    duration_seconds: float
    error: str | None
    score: ScoreReport | None
    candidate_sha256: str | None
    stderr_warning: str | None
    stdout_log: str
    stderr_log: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "command": self.command,
            "returncode": self.returncode,
            "output_exists": self.output_exists,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "stderr_warning": self.stderr_warning,
            "candidate_sha256": self.candidate_sha256,
            "score": self.score.as_dict() if self.score is not None else None,
            "stdout_log": self.stdout_log,
            "stderr_log": self.stderr_log,
        }


@dataclass(frozen=True)
class Attractor:
    """One group of variants that produced byte-identical scored functions."""

    letter: str
    candidate_sha256: str
    diff_words: int
    relocation_floor: int
    members: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "attractor": self.letter,
            "candidate_sha256": self.candidate_sha256,
            "diff_words": self.diff_words,
            "relocation_floor": self.relocation_floor,
            "members": list(self.members),
        }


@dataclass(frozen=True)
class MatrixReport:
    run_dir: str
    variants: tuple[VariantResult, ...]
    attractors: tuple[Attractor, ...]
    collapsed_attractors: tuple[Attractor, ...]
    all_collapsed: bool
    caution: str | None
    silent_fallback_warnings: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "variants": [item.as_dict() for item in self.variants],
            "attractors": [item.as_dict() for item in self.attractors],
            "collapsed_attractors": [item.letter for item in self.collapsed_attractors],
            "all_collapsed": self.all_collapsed,
            "caution": self.caution,
            "silent_fallback_warnings": [
                {"label": label, "line": line}
                for label, line in self.silent_fallback_warnings
            ],
        }


def load_matrix_spec(path: str | Path) -> tuple[list[Variant], ScoreSpec]:
    """Load and validate a `matrix` JSON spec file."""

    spec_path = Path(path)
    if not spec_path.is_file():
        raise ScoreError(f"matrix spec does not exist: {spec_path}")
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScoreError(
            f"matrix spec could not be read: {spec_path} ({error})"
        ) from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ScoreError(
            f"matrix spec is not valid JSON: {spec_path} ({error})"
        ) from error
    if not isinstance(data, dict):
        raise ScoreError(f"matrix spec must be a JSON object: {spec_path}")
    raw_variants = data.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ScoreError(
            f"matrix spec {spec_path} must have a non-empty 'variants' array"
        )
    variants: list[Variant] = []
    seen_labels: set[str] = set()
    for index, item in enumerate(raw_variants):
        if (
            not isinstance(item, dict)
            or not item.get("label")
            or not item.get("command")
        ):
            raise ScoreError(
                f"variant #{index} in {spec_path} needs non-empty 'label' and "
                "'command' strings"
            )
        label = str(item["label"])
        if label in seen_labels:
            raise ScoreError(f"duplicate variant label {label!r} in {spec_path}")
        seen_labels.add(label)
        variants.append(Variant(label=label, command=str(item["command"])))
    score_data = data.get("score")
    if not isinstance(score_data, dict):
        raise ScoreError(f"matrix spec {spec_path} must have a 'score' object")
    spec = score_spec_from_dict(score_data)
    return variants, spec


def _safe_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    return cleaned or "variant"


def run_variant(
    variant: Variant,
    *,
    run_dir: Path,
    spec: ScoreSpec,
    timeout: float,
) -> VariantResult:
    """Run one variant's command and score whatever object it produced."""

    safe = _safe_label(variant.label)
    output_path = run_dir / "objects" / f"{safe}.o"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = logs_dir / f"{safe}.stdout.log"
    stderr_log = logs_dir / f"{safe}.stderr.log"

    if OUTPUT_PLACEHOLDER not in variant.command:
        error = (
            f"variant command does not contain the {OUTPUT_PLACEHOLDER} "
            "placeholder, so no object path was substituted"
        )
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return VariantResult(
            label=variant.label,
            command=variant.command,
            returncode=None,
            stdout="",
            stderr="",
            output_path=None,
            output_exists=False,
            duration_seconds=0.0,
            error=error,
            score=None,
            candidate_sha256=None,
            stderr_warning=None,
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
        )

    rendered = variant.command.replace(OUTPUT_PLACEHOLDER, str(output_path))
    started = time.monotonic()
    run_error: str | None = None
    try:
        process = subprocess.run(
            rendered,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        returncode: int | None = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as error:
        returncode = None
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        run_error = f"variant command exceeded --timeout ({timeout:g}s)"
    duration = time.monotonic() - started

    stdout_log.write_text(stdout, encoding="utf-8")
    stderr_log.write_text(stderr, encoding="utf-8")

    stderr_warning = None
    for line in stderr.splitlines():
        if SILENT_FALLBACK_RE.search(line):
            stderr_warning = line.strip()
            break

    output_exists = output_path.is_file() and output_path.stat().st_size > 0
    failure_message = run_error
    if failure_message is None and returncode:
        failure_message = f"variant command exited {returncode}"
    elif failure_message is None and not output_exists:
        failure_message = (
            f"variant command produced no output object at {output_path} "
            f"(the {OUTPUT_PLACEHOLDER} path)"
        )

    score: ScoreReport | None = None
    candidate_sha256: str | None = None
    if output_exists and failure_message is None:
        try:
            score = score_report(output_path, spec)
            candidate_sha256 = score.function.candidate_sha256
        except (ScoreError, OSError, RuntimeError) as scoring_error:
            failure_message = f"scoring failed: {scoring_error}"

    return VariantResult(
        label=variant.label,
        command=variant.command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        output_path=str(output_path) if output_exists else None,
        output_exists=output_exists,
        duration_seconds=duration,
        error=failure_message,
        score=score,
        candidate_sha256=candidate_sha256,
        stderr_warning=stderr_warning,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )


def _letter(index: int) -> str:
    """Render 0, 1, 2, ... 25, 26 as A, B, C, ... Z, AA (spreadsheet style)."""

    index += 1
    letters: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def cluster_attractors(results: list[VariantResult]) -> tuple[Attractor, ...]:
    """Group variants with byte-identical scored functions into attractors.

    Ordered by score (fewest diff words first) so attractor A is always the
    closest to matching, whatever order the variants ran in.
    """

    groups: dict[str, list[VariantResult]] = {}
    for item in results:
        if item.score is None or item.candidate_sha256 is None:
            continue
        groups.setdefault(item.candidate_sha256, []).append(item)
    ordered = sorted(
        groups.items(),
        key=lambda pair: (
            pair[1][0].score.function.diff_words if pair[1][0].score else 0,
            pair[0],
        ),
    )
    attractors: list[Attractor] = []
    for index, (digest, members) in enumerate(ordered):
        assert members[0].score is not None
        attractors.append(
            Attractor(
                letter=_letter(index),
                candidate_sha256=digest,
                diff_words=members[0].score.function.diff_words,
                relocation_floor=members[0].score.function.relocation_floor,
                members=tuple(item.label for item in members),
            )
        )
    return tuple(attractors)


def default_run_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".decomp-workbench") / "matrix" / stamp


def run_matrix(
    spec_path: str | Path,
    *,
    run_dir: Path | None = None,
    timeout: float = 120.0,
) -> MatrixReport:
    """Run every variant in a matrix spec and cluster the results."""

    variants, spec = load_matrix_spec(spec_path)
    resolved_run_dir = run_dir if run_dir is not None else default_run_dir()
    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    results = [
        run_variant(variant, run_dir=resolved_run_dir, spec=spec, timeout=timeout)
        for variant in variants
    ]
    attractors = cluster_attractors(results)
    collapsed = tuple(item for item in attractors if len(item.members) >= 2)
    successful = [item for item in results if item.score is not None]
    all_collapsed = len(attractors) == 1 and len(successful) >= 2
    caution = ALL_COLLAPSED_CAUTION if all_collapsed else None
    warnings = tuple(
        (item.label, item.stderr_warning)
        for item in results
        if item.stderr_warning is not None
    )
    return MatrixReport(
        run_dir=str(resolved_run_dir),
        variants=tuple(results),
        attractors=attractors,
        collapsed_attractors=collapsed,
        all_collapsed=all_collapsed,
        caution=caution,
        silent_fallback_warnings=warnings,
    )
