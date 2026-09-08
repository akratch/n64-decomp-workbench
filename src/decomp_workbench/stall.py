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
from dataclasses import dataclass

__all__ = [
    "DEFAULT_THRESHOLD",
    "Attempt",
    "StallReading",
    "read_series",
]

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


@dataclass(frozen=True)
class StallReading:
    """How a series reads, and the lines that say so."""

    state: str
    stalled_for: int
    best_residual: int | None
    last_progress: int | None
    lines: tuple[str, ...]

    @property
    def should_continue(self) -> bool:
        return self.state == "improving"


def _progress_indices(attempts: Sequence[Attempt]) -> list[int]:
    """Positions that bought something: a new best residual, or an elimination."""
    progressed: list[int] = []
    best: int | None = None
    for index, attempt in enumerate(attempts):
        gained = best is None or attempt.residual < best
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
    """
    if threshold < 1:
        raise ValueError("threshold must be at least one attempt")

    progressed = _progress_indices(attempts)
    best = min((attempt.residual for attempt in attempts), default=None)
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
        lines=(
            f"continue: {stalled_for} attempt(s) since the last one that "
            f"bought something (stall at {threshold}).",
            f"  {detail}",
            "  a falling residual is progress for stopping, never grounds for "
            "adopting a nonexact candidate.",
        ),
    )
