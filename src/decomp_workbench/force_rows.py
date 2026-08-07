"""Join an allocator force control to the object rows it moved.

There is no static map from a uopt web to the instructions it produced. Web
numbers index a run-local table that does not survive into the object, and a
recorded campaign measured that neither "ucode record index implies program
position" nor "allocator event order implies emission order" holds: a change
confined to 16 records 18% into the intermediate stream first moved the object
at instruction 94.

So the join is not read, it is *measured*. Build the candidate twice, once with
one force control set, and the rows that moved are -- by construction -- the
rows that control owns. This module owns the measurement half of that: two
already-built objects in, runs of moved rows out, in the row vocabulary
`compare --json` and `window` already publish.

It deliberately does **not** build anything. The prototype this generalizes
(`webrows.py` in the `ge007-object-interaction` campaign) hard-coded one
campaign's build script, one instrumented compiler, and one force grammar
extension that the shipped profile does not have. What is portable is the join,
and the join needs no compiler at all.

Two corrections over the prototype, both of which change results:

* the prototype zipped the two disassemblies by position, so a force that
  changed the instruction *count* silently reported every row after the first
  insertion as moved. This aligns the two builds, so an insertion is one run
  and not a thousand;
* the prototype indexed the target by the same raw position, so its "target
  instruction at this row" was wrong wherever the candidate had drifted from
  the target. The optional target join here goes through the same LCS
  alignment `compare` uses, so a run's `compare_row` is the number a dossier
  quotes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .model import Instruction
from .view import MechanismView, build_view

#: The `force-rows` report vocabulary. Run row keys are the aligned-row numbers
#: `compare --json` publishes, so a run and a window name the same rows.
FORCE_ROWS_SCHEMA = "decomp-workbench-force-rows-v1"

#: Matched rows tolerated inside one run before it is split in two. The
#: prototype used three and it is kept: an allocator force typically moves a
#: load, leaves the following instruction alone, and moves the use.
DEFAULT_GAP = 3

INERT_NOTE = (
    "no row moved: under this force the two builds are instruction-identical. "
    "That is evidence, not a failed run -- the control reached the pass and "
    "changed no emitted instruction, so this web owns no object row here"
)

LENGTH_WARNING = (
    "the force changed the instruction count ({baseline} -> {forced}); runs "
    "are reported over the alignment of the two builds, not by position"
)


@dataclass(frozen=True)
class MovedRun:
    """One contiguous run of rows that the force control moved."""

    run: int
    start: int
    end: int
    rows: int
    classes: tuple[str, ...]
    baseline_start: int | None
    baseline_end: int | None
    compare_start: int | None
    compare_end: int | None
    baseline_text: str | None
    target_text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run": self.run,
            "start": self.start,
            "end": self.end,
            "rows": self.rows,
            "classes": list(self.classes),
            "baseline_start": self.baseline_start,
            "baseline_end": self.baseline_end,
            "compare_start": self.compare_start,
            "compare_end": self.compare_end,
            "baseline_text": self.baseline_text,
            "target_text": self.target_text,
        }


@dataclass(frozen=True)
class ForceRows:
    """The measured web-to-row join for one force control."""

    force: str
    baseline: str
    forced: str
    target: str | None
    symbol: str | None
    gap: int
    aligned_rows: int
    moved_rows: int
    runs: tuple[MovedRun, ...]
    warnings: tuple[str, ...]

    @property
    def inert(self) -> bool:
        """Whether the control moved no instruction at all."""

        return self.moved_rows == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": FORCE_ROWS_SCHEMA,
            "force": self.force,
            "baseline": self.baseline,
            "forced": self.forced,
            "target": self.target,
            "symbol": self.symbol,
            "gap": self.gap,
            "aligned_rows": self.aligned_rows,
            "moved_rows": self.moved_rows,
            "inert": self.inert,
            "runs": [run.as_dict() for run in self.runs],
            "warnings": list(self.warnings),
        }


def group_moved_runs(
    view: MechanismView, *, gap: int = DEFAULT_GAP
) -> list[tuple[int, int]]:
    """Group non-matching rows into runs, tolerating ``gap`` matched rows.

    A gap of zero reports strictly contiguous runs. Anything larger merges
    across short matched stretches, which is what makes a 40-row report
    readable as six sites instead of forty.
    """

    if gap < 0:
        raise ValueError("--gap cannot be negative")
    moved = [row.index for row in view.rows if not row.matched]
    if not moved:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = moved[0]
    for index in moved[1:]:
        # `gap` counts matched rows *between* two moved rows, so adjacent
        # moved rows are one run at every gap including zero.
        if index > previous + gap + 1:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return runs


def _compare_rows(view: MechanismView | None) -> dict[int, int]:
    """Map each candidate instruction index to its aligned row in ``view``."""

    if view is None:
        return {}
    return {
        row.candidate_index: row.index
        for row in view.rows
        if row.candidate_index is not None
    }


def _target_text(view: MechanismView | None, row: int | None) -> str | None:
    if view is None or row is None or not 0 <= row < len(view.rows):
        return None
    return view.rows[row].target


def build_force_rows(
    baseline: Sequence[Instruction],
    forced: Sequence[Instruction],
    *,
    force: str,
    baseline_name: str,
    forced_name: str,
    target: Sequence[Instruction] | None = None,
    target_name: str | None = None,
    symbol: str | None = None,
    gap: int = DEFAULT_GAP,
    warnings: Sequence[str] = (),
) -> ForceRows:
    """Measure which rows one force control moved, and where they sit.

    ``baseline`` and ``forced`` are the *same source* built twice: without the
    control and with it. ``target`` is optional and only supplies the second
    join -- the aligned row number a `compare`/`window` reader already has.
    """

    perturbation = build_view(
        baseline,
        forced,
        target_name=baseline_name,
        candidate_name=forced_name,
        symbol=symbol,
    )
    comparison = (
        build_view(
            target,
            baseline,
            target_name=target_name or "target",
            candidate_name=baseline_name,
            symbol=symbol,
        )
        if target is not None
        else None
    )
    rows = _compare_rows(comparison)
    collected: list[str] = list(warnings)
    if len(baseline) != len(forced):
        collected.append(
            LENGTH_WARNING.format(baseline=len(baseline), forced=len(forced))
        )

    runs: list[MovedRun] = []
    moved_rows = 0
    for number, (low, high) in enumerate(
        group_moved_runs(perturbation, gap=gap), start=1
    ):
        selected = perturbation.rows[low : high + 1]
        moved_rows += sum(1 for row in selected if not row.matched)
        classes: dict[str, None] = {}
        for row in selected:
            if not row.matched:
                classes.setdefault(row.classification, None)
        # The baseline side of the perturbation view is its `target` side: the
        # baseline build is the reference the forced build is measured against.
        indices = [row.target_index for row in selected if row.target_index is not None]
        baseline_start = indices[0] if indices else None
        baseline_end = indices[-1] if indices else None
        compare_start = rows.get(baseline_start) if baseline_start is not None else None
        compare_end = rows.get(baseline_end) if baseline_end is not None else None
        runs.append(
            MovedRun(
                run=number,
                start=low,
                end=high,
                rows=len(selected),
                classes=tuple(classes),
                baseline_start=baseline_start,
                baseline_end=baseline_end,
                compare_start=compare_start,
                compare_end=compare_end,
                baseline_text=selected[0].target if selected else None,
                target_text=_target_text(comparison, compare_start),
            )
        )
    return ForceRows(
        force=force,
        baseline=baseline_name,
        forced=forced_name,
        target=target_name,
        symbol=symbol,
        gap=gap,
        aligned_rows=perturbation.aligned_rows,
        moved_rows=moved_rows,
        runs=tuple(runs),
        warnings=tuple(collected),
    )


def force_rows_lines(result: ForceRows) -> list[str]:
    """Render the join for a terminal, evidence first."""

    lines = [f"warning: {warning}" for warning in result.warnings]
    lines.append(
        f"force={result.force} aligned_rows={result.aligned_rows} "
        f"moved={result.moved_rows} runs={len(result.runs)}"
    )
    if result.inert:
        lines.append(f"BYTE-INERT  {INERT_NOTE}")
        return lines
    for run in result.runs:
        head = (
            f"  run {run.run:3d}  rows {run.start}-{run.end}"
            f"  moved={run.rows}  classes={','.join(run.classes) or '-'}"
        )
        if run.compare_start is not None:
            head += f"  compare_row={run.compare_start}"
        lines.append(head)
        if run.baseline_text:
            lines.append(f"        baseline: {run.baseline_text}")
        if run.target_text:
            lines.append(f"        target:   {run.target_text}")
    return lines
