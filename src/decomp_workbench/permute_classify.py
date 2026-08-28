"""Turn a sweep's record into a measured wall class per function.

Wall classes were assigned by hand, from verdict prose, and the class that
says "nothing will move this" has repeatedly been wrong -- expensively so,
because it is the class that routes a function away from cheap search and
towards a bespoke instrumentation build. The permuter already produces the
evidence that would settle it: a base score, a best score, where in the
window the best candidate landed, and whether an extension was earned.

This module reads that record and assigns the class, so the routing
decision is made from measurements a sweep took rather than from how a
verdict was worded. It classifies; it does not search, promote, or judge
whether a function is matchable -- no static claim in this package can.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

CLASSIFY_SCHEMA = "decomp-workbench-permute-classify-v1"

#: The function matched in the scratch. Still a candidate, not a promotion:
#: proving it belongs to the project's authoritative build.
MATCHED = "MATCHED"

#: The search improved on the base and was still improving when the window
#: closed -- either it earned the extension, or its best candidate landed
#: late. More search time, a trace lever, or a human is the right next step.
P_STUCK_DESCENDING = "P_STUCK_DESCENDING"

#: The search did not improve at all, or improved only in the opening
#: fraction of its window and then sat. More time is not the answer here.
P_STUCK_FLAT = "P_STUCK_FLAT"

#: There is no measurement: the scratch failed to import or compile, so the
#: base has no score. Nothing about the function has been learned yet.
IMPORT_FAULT = "IMPORT_FAULT"

CLASSES = (MATCHED, P_STUCK_DESCENDING, P_STUCK_FLAT, IMPORT_FAULT)

#: A best candidate landing in the last third of the window counts as "still
#: descending". The same third `--extend-minutes` uses to decide whether a
#: second window is worth spending, for the same reason.
LATE_FRACTION = 2.0 / 3.0

#: What each class is *for*. The routing, not the definition: the point of
#: measuring the class is that each one has exactly one next action, and the
#: expensive mistake is sending a `P_STUCK_FLAT` function to a human or a
#: `P_STUCK_DESCENDING` one to a six-figure instrumentation build.
ROUTING = {
    MATCHED: "verify on the authoritative build, then promote",
    P_STUCK_DESCENDING: "trace levers or manual work; the search is still moving",
    P_STUCK_FLAT: (
        "the pool that decides whether deeper instrumentation is worth funding"
    ),
    IMPORT_FAULT: "fix the scratch (prototype conflicts, missing context, flags)",
}


@dataclass(frozen=True)
class Classification:
    """One function's measured class, and the numbers behind it."""

    function: str
    source: str
    wall_class: str
    reason: str
    base: int | None = None
    best: int | None = None
    delta: int | None = None
    elapsed: float = 0.0
    extended: bool = False
    hit_cap: bool = False
    best_output_mtime_fraction: float | None = None
    flags_recovered: bool = True
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "source": self.source,
            "class": self.wall_class,
            "reason": self.reason,
            "routing": ROUTING[self.wall_class],
            "base": self.base,
            "best": self.best,
            "delta": self.delta,
            "elapsed": round(self.elapsed, 1),
            "extended": self.extended,
            "hit_cap": self.hit_cap,
            "best_output_mtime_fraction": self.best_output_mtime_fraction,
            "flags_recovered": self.flags_recovered,
            "error": self.error,
        }


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _fraction(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def classify_row(row: dict[str, Any]) -> Classification:
    """Classify one `summary.json` result row.

    Order matters. A scratch with no base score has measured nothing, so it
    cannot be called flat -- that is the mistake that funds instrumentation
    for a function nobody ever actually searched.
    """

    function = str(row.get("function", ""))
    source = str(row.get("source", ""))
    base = _integer(row.get("base_score"))
    best = _integer(row.get("best_score"))
    elapsed = _fraction(row.get("seconds")) or 0.0
    extended = bool(row.get("extended"))
    hit_cap = bool(row.get("hit_cap"))
    fraction = _fraction(row.get("best_output_mtime_fraction"))
    flags_recovered = bool(row.get("flags_recovered"))
    error = row.get("error") if isinstance(row.get("error"), str) else None

    common: dict[str, Any] = {
        "function": function,
        "source": source,
        "base": base,
        "best": best,
        "elapsed": elapsed,
        "extended": extended,
        "hit_cap": hit_cap,
        "best_output_mtime_fraction": fraction,
        "flags_recovered": flags_recovered,
        "error": error,
    }

    if error is not None or not row.get("ok") or base is None:
        return Classification(
            wall_class=IMPORT_FAULT,
            reason=error or "the scratch produced no base score",
            delta=None,
            **common,
        )
    if best == 0:
        return Classification(
            wall_class=MATCHED,
            reason="the scratch reached score 0; the real build has not confirmed it",
            delta=base,
            **common,
        )
    reached = base if best is None else best
    delta = base - reached
    if delta <= 0:
        return Classification(
            wall_class=P_STUCK_FLAT,
            reason="no candidate ever improved on the base score",
            delta=delta,
            **common,
        )
    if extended:
        return Classification(
            wall_class=P_STUCK_DESCENDING,
            reason=(
                "the search earned its extension: it was still improving when "
                "its first window closed"
            ),
            delta=delta,
            **common,
        )
    if fraction is None:
        # An older summary, from before the sweep recorded where in the
        # window its best candidate landed. Call it descending: the flat
        # class is the one that gets an instrumentation build funded, and a
        # function routed there on absent evidence is the costlier error.
        return Classification(
            wall_class=P_STUCK_DESCENDING,
            reason=(
                "improved on the base, but this summary does not record when "
                "the best candidate landed; re-run the sweep to measure it"
            ),
            delta=delta,
            **common,
        )
    if fraction >= LATE_FRACTION:
        return Classification(
            wall_class=P_STUCK_DESCENDING,
            reason=(
                f"the best candidate landed {fraction:.0%} into the window, "
                "so the search was still descending when it stopped"
            ),
            delta=delta,
            **common,
        )
    return Classification(
        wall_class=P_STUCK_FLAT,
        reason=(
            f"the best candidate landed {fraction:.0%} into the window and "
            "nothing improved after it"
        ),
        delta=delta,
        **common,
    )


def classify_summary(payload: Any) -> list[Classification]:
    """Classify every result in a `permute-sweep` summary document."""

    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("a sweep summary must hold a list of results")
    return [classify_row(row) for row in rows if isinstance(row, dict)]


def classify_payload(
    rows: Sequence[Classification], *, source: str | None = None
) -> dict[str, Any]:
    """The JSON document, with the per-class totals a triage page needs."""

    return {
        "schema": CLASSIFY_SCHEMA,
        "summary": source,
        "totals": {
            name: sum(1 for row in rows if row.wall_class == name) for name in CLASSES
        },
        "routing": dict(ROUTING),
        "functions": [row.as_dict() for row in rows],
    }


def _cell(value: Any) -> str:
    return "-" if value is None else str(value)


def render_markdown(
    rows: Sequence[Classification], *, source: str | None = None
) -> list[str]:
    """A table that can be pasted into a triage document unedited."""

    lines: list[str] = []
    if source:
        lines.extend((f"Sweep: `{source}`", ""))
    lines.extend(
        (
            "| function | class | base | best | delta | best at | elapsed | ext |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        )
    )
    for row in rows:
        fraction = (
            "-"
            if row.best_output_mtime_fraction is None
            else f"{row.best_output_mtime_fraction:.0%}"
        )
        lines.append(
            f"| `{row.function}` | {row.wall_class} | {_cell(row.base)} | "
            f"{_cell(row.best)} | {_cell(row.delta)} | {fraction} | "
            f"{row.elapsed:.0f}s | {'yes' if row.extended else 'no'} |"
        )
    lines.append("")
    lines.append("| class | functions | routes to |")
    lines.append("|---|---:|---|")
    for name in CLASSES:
        count = sum(1 for row in rows if row.wall_class == name)
        lines.append(f"| {name} | {count} | {ROUTING[name]} |")
    # A fallback-flags search may have explored the wrong ISA, so its
    # class describes the scratch rather than the function. An
    # IMPORT_FAULT row never got as far as flags and is not that case.
    fallback = [
        row.function
        for row in rows
        if not row.flags_recovered and row.wall_class != IMPORT_FAULT
    ]
    if fallback:
        lines.extend(
            (
                "",
                "Searched with fallback flags, so their class is not evidence "
                "about the function: " + ", ".join(f"`{name}`" for name in fallback),
            )
        )
    return lines


__all__ = [
    "CLASSES",
    "CLASSIFY_SCHEMA",
    "IMPORT_FAULT",
    "LATE_FRACTION",
    "MATCHED",
    "P_STUCK_DESCENDING",
    "P_STUCK_FLAT",
    "ROUTING",
    "Classification",
    "classify_payload",
    "classify_row",
    "classify_summary",
    "render_markdown",
]
