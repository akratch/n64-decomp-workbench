"""Read a *series* of attempts, so stopping is measured rather than counted.

Every other verdict in this package describes one comparison. Nothing read a
series, so the question a matching campaign actually asks between builds --
"should the next attempt happen at all?" -- fell to the host, and hosts reach
for the same proxy: a fixed attempt count.

A Mickey's Speedway USA wave on 2026-09-08 broke that proxy in both directions
in one day. A 719-word structural reconstruction improved monotonically across
its series, 692 then 619 then 538 differing words, and was stopped at the count
while it was still gaining. In the same wave a target whose committed handoff
already recorded the flag lattice exhausted and the adjacent mechanism flat in
three isolated forms would have been granted nine further attempts by that same
count, whose only possible result was re-deriving a known-flat answer. The
correct number there was zero, and the correct number for the first was more.

So the reading is over the series, and it is data in, verdict out, exactly like
`field_guide.next_steps`: the host supplies attempts it has already measured,
and this returns how to read them. It deliberately does not own or schedule the
attempt loop. Only the project knows what an attempt is, how to build one, and
what it eliminated -- the same reason the staleness work refused to discover a
build chain it could only have guessed.

One distinction is load-bearing. A falling residual counts as progress *for a
stopping decision*, because a search that keeps moving the number is still
learning. It is not thereby evidence *for adoption*: a nonexact candidate is
never adopted because its score improved, and nothing here changes that. The
two questions are different, and conflating them would license the grinding
this module exists to end.

A stall is also not a reachability claim. "This search stopped learning" and
"no source reaches this" are different statements; the second needs the
permuter or a force proof.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

__all__ = [
    "DEFAULT_THRESHOLD",
    "SERIES_SCHEMA",
    "STALL_SCHEMA",
    "Attempt",
    "StallReading",
    "load_series",
    "read_series",
    "stall_payload",
]

#: The host's input: an ordered list of already-measured attempts.
SERIES_SCHEMA = "decomp-workbench-attempt-series-v1"
#: The reading `campaign stall` emits.
STALL_SCHEMA = "decomp-workbench-stall-v1"

#: Consecutive attempts that must buy nothing before a series reads `stalled`.
#: Three, because two can be a pair of probes around one hypothesis; the third
#: is the first that cannot be.
DEFAULT_THRESHOLD = 3


@dataclass(frozen=True)
class Attempt:
    """One already-measured attempt.

    `residual` is the attempt's best measured distance in whatever unit the
    host files a plateau in (differing words, throughout Mickey). Lower is
    closer; this module never compares residuals across functions, only within
    one series.

    `eliminated` says whether the attempt ruled a recorded hypothesis out. An
    attempt that neither moved the residual nor eliminated anything bought
    nothing, and that -- not its ordinal -- is what makes it a stall.
    """

    residual: int
    eliminated: bool = False
    label: str = ""
    #: How the measured object was built, in `provenance.classify_environment`
    #: vocabulary. Only a `stock` residual is a source attempt's distance; a
    #: forced or unknown build's number is a statement about the allocator or
    #: about nothing, and it never counts as residual progress. It can still
    #: eliminate a hypothesis, which is what a force experiment is for.
    provenance: str = "stock"


@dataclass(frozen=True)
class StallReading:
    """How a series reads, and the lines that say so."""

    state: str
    stalled_for: int
    best_residual: int | None
    last_progress: int | None
    lines: tuple[str, ...]
    excluded: int = 0

    @property
    def should_continue(self) -> bool:
        return self.state == "improving"


def _progress_indices(attempts: Sequence[Attempt]) -> list[int]:
    """Positions that bought something: a new best residual, or an elimination."""
    progressed: list[int] = []
    best: int | None = None
    for index, attempt in enumerate(attempts):
        counts = attempt.provenance == "stock"
        gained = counts and (best is None or attempt.residual < best)
        if gained:
            best = attempt.residual
        if gained or attempt.eliminated:
            progressed.append(index)
    return progressed


def read_series(
    attempts: Sequence[Attempt],
    *,
    threshold: int = DEFAULT_THRESHOLD,
    closed_by_evidence: bool = False,
) -> StallReading:
    """Return how this series reads.

    `closed_by_evidence` is the host's statement that the target's own recorded
    history already rules out every mechanism still available to this worker.
    It wins over the series, including an empty one: zero attempts is the right
    number when the answer is already written down.

    An attempt whose object was not built by the stock compiler never moves
    the residual; its number is kept out of `best_residual` and the reading
    says how many were set aside.
    """
    reading = _read_series(
        attempts, threshold=threshold, closed_by_evidence=closed_by_evidence
    )
    if not reading.excluded:
        return reading
    return replace(
        reading,
        lines=(
            *reading.lines,
            f"  {reading.excluded} attempt(s) were measured under force or with "
            "an unknown build: their residuals are not source distances and "
            "counted only if they eliminated a hypothesis.",
        ),
    )


def _read_series(
    attempts: Sequence[Attempt],
    *,
    threshold: int = DEFAULT_THRESHOLD,
    closed_by_evidence: bool = False,
) -> StallReading:
    """The reading before the provenance note; see `read_series`."""
    if threshold < 1:
        raise ValueError("threshold must be at least one attempt")

    for attempt in attempts:
        if attempt.provenance not in {"stock", "forced", "unknown"}:
            raise ValueError(f"unknown attempt provenance {attempt.provenance!r}")
    excluded = sum(1 for attempt in attempts if attempt.provenance != "stock")
    progressed = _progress_indices(attempts)
    best = min(
        (attempt.residual for attempt in attempts if attempt.provenance == "stock"),
        default=None,
    )
    last_progress = progressed[-1] if progressed else None
    stalled_for = (
        len(attempts) - 1 - last_progress
        if last_progress is not None
        else len(attempts)
    )

    if closed_by_evidence:
        return StallReading(
            state="closed-by-evidence",
            stalled_for=stalled_for,
            best_residual=best,
            last_progress=last_progress,
            excluded=excluded,
            lines=(
                "stop: the target's recorded history already rules out the "
                "mechanisms still available here.",
                "  verifying exhaustion is a result; re-deriving a known-flat "
                "answer is not.",
                "  file the plateau against the existing evidence, and say the "
                "resumption bar was tested and not met.",
            ),
        )

    if stalled_for >= threshold:
        moved = (
            f"attempt {last_progress + 1}"
            if last_progress is not None
            else "no attempt in this series"
        )
        return StallReading(
            state="stalled",
            stalled_for=stalled_for,
            best_residual=best,
            last_progress=last_progress,
            excluded=excluded,
            lines=(
                f"stop: {stalled_for} consecutive attempts moved neither the "
                "residual nor the hypothesis set.",
                f"  last attempt that bought something: {moved}.",
                "  record that as the stopping evidence, not the attempt count.",
                "  a stall is not a reachability claim: for 'no source reaches "
                "this', use the permuter or a force proof.",
            ),
        )

    if last_progress is not None and stalled_for == 0 and len(attempts) > 1:
        detail = "the series is still moving; the wall clock is the limit, not a count."
    else:
        detail = "no stall yet; keep going while attempts still buy something."
    return StallReading(
        state="improving",
        stalled_for=stalled_for,
        best_residual=best,
        last_progress=last_progress,
        excluded=excluded,
        lines=(
            f"continue: {stalled_for} attempt(s) since the last one that "
            f"bought something (stall at {threshold}).",
            f"  {detail}",
            "  a falling residual is progress for stopping, never grounds for "
            "adopting a nonexact candidate.",
        ),
    )


def load_series(payload: object) -> tuple[list[Attempt], bool, int]:
    """Read a `decomp-workbench-attempt-series-v1` document.

    Returns the attempts, the host's closed-by-evidence statement, and the
    threshold. Every attempt must carry an integer `residual`; `eliminated`,
    `label` and `provenance` are optional, and an attempt without
    `provenance` is refused rather than assumed stock, because a series that
    mixes forced and stock numbers without saying which is the failure the
    field exists to prevent.
    """

    if not isinstance(payload, dict) or payload.get("schema") != SERIES_SCHEMA:
        raise ValueError(f"expected a {SERIES_SCHEMA} document")
    rows = payload.get("attempts")
    if not isinstance(rows, list):
        raise ValueError("the series has no `attempts` list")
    attempts: list[Attempt] = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("residual"), int):
            raise ValueError(f"attempt {number} has no integer `residual`")
        provenance = row.get("provenance")
        if provenance not in {"stock", "forced", "unknown"}:
            raise ValueError(
                f"attempt {number} does not say how its object was built: "
                "`provenance` must be stock, forced or unknown. A forced score "
                "and a stock score look identical, so the series refuses to "
                "guess"
            )
        attempts.append(
            Attempt(
                residual=row["residual"],
                eliminated=bool(row.get("eliminated", False)),
                label=str(row.get("label", "")),
                provenance=provenance,
            )
        )
    threshold = payload.get("threshold", DEFAULT_THRESHOLD)
    if not isinstance(threshold, int):
        raise ValueError("`threshold` must be an integer")
    return attempts, bool(payload.get("closed_by_evidence", False)), threshold


def stall_payload(
    reading: StallReading, attempts: Sequence[Attempt]
) -> dict[str, object]:
    """The versioned JSON form of one reading."""

    return {
        "schema": STALL_SCHEMA,
        "state": reading.state,
        "should_continue": reading.should_continue,
        "stalled_for": reading.stalled_for,
        "best_residual": reading.best_residual,
        "last_progress": (
            reading.last_progress + 1 if reading.last_progress is not None else None
        ),
        "last_progress_label": (
            attempts[reading.last_progress].label or None
            if reading.last_progress is not None
            else None
        ),
        "attempts": len(attempts),
        "excluded_from_residual": reading.excluded,
        "lines": list(reading.lines),
    }
