"""What a sweep is entitled to claim, given what it actually visited.

A campaign stage reported "no single fp-ring perturbation anywhere improves on
563". The sweep behind that sentence ran ``k = 1..1457 step 8`` -- one point in
eight, an eighth of the space -- and the claim went into the ledger as a closed
family. A later exhaustive re-run of 707 builds happened to agree, so nothing
broke; the statement was still not entitled to be a proof when it was made, and
the record it came from said nothing about the seven points in eight it never
visited.

The fix is a record, not a rule: every sweep that reports a result also reports
the size of the space it is about, how many points it visited, and the stride
if it took one. From those three numbers the vocabulary follows -- **swept
exhaustively** when every point was visited, **sampled** otherwise -- and a
negative result from a sampled sweep prints with the number of unvisited points
attached to it, so nobody has to remember to ask.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["SweepCoverage"]


@dataclass(frozen=True)
class SweepCoverage:
    """How much of a space one sweep visited, and what that permits."""

    #: What the space is, in words: "subsets of 8 transformations up to
    #: order 2", "ring rotations k=1..1457". Printed, so a reader can see what
    #: the fraction is a fraction *of*.
    basis: str
    #: Points in the space. ``None`` when the space is genuinely unbounded or
    #: unknown, which is itself worth printing rather than implying totality.
    space: int | None
    #: Points the sweep actually visited.
    covered: int
    #: Sampling stride, when the sweep took one. ``None`` means consecutive.
    step: int | None = None
    #: Points the sweep declined to visit for a stated reason -- a conflict
    #: rule, a failed edit -- as opposed to points a stride skipped.
    excluded: int = 0

    @property
    def exhaustive(self) -> bool:
        """Whether every point in the space was visited or deliberately excluded."""

        if self.space is None:
            return False
        return self.covered + self.excluded >= self.space

    @property
    def unvisited(self) -> int | None:
        if self.space is None:
            return None
        return max(0, self.space - self.covered - self.excluded)

    @property
    def fraction(self) -> float | None:
        """Visited points as a fraction of the space, or ``None`` when unknown."""

        if not self.space:
            return None
        return self.covered / self.space

    @property
    def vocabulary(self) -> str:
        """``swept-exhaustively`` or ``sampled`` -- the two are not the same claim."""

        return "swept-exhaustively" if self.exhaustive else "sampled"

    def sentence(self) -> str:
        """One line stating the coverage and what a negative result may claim."""

        if self.space is None:
            return (
                f"coverage: {self.covered} point(s) of an unbounded space "
                f"({self.basis}); this is a sample, and a negative result here "
                "is evidence, not a proof"
            )
        stride = f", step {self.step}" if self.step and self.step > 1 else ""
        excluded = f", {self.excluded} excluded" if self.excluded else ""
        headline = (
            f"coverage: {self.vocabulary} -- {self.covered} of {self.space} "
            f"point(s){stride}{excluded} ({self.basis})"
        )
        if self.exhaustive:
            return headline + "; a negative result here is a proof about this space"
        return (
            f"{headline}; {self.unvisited} point(s) were never visited, so a "
            "negative result here is evidence about the sample and not a proof "
            "about the space"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "space": self.space,
            "covered": self.covered,
            "step": self.step,
            "excluded": self.excluded,
            "unvisited": self.unvisited,
            "exhaustive": self.exhaustive,
            "fraction": self.fraction,
            "vocabulary": self.vocabulary,
            "sentence": self.sentence(),
        }
