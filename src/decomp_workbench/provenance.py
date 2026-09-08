"""Whether a result may be read as a match, or only as a reachability proof.

Every comparison in this package reports the same shape of score whether the
object came from the stock compiler or from a run with allocator forcing
enabled. Zero differing words means two very different things in those two
cases, and only one of them is a match.

`oracle` already states the rule -- "web IDs and forced objects are never
source-match evidence" -- but it states it as prose inside a `proof` string. A
consumer reading `exact` and a differing-word count has nothing structural
telling it which kind of run produced them.

That gap has a measured cost. During a Mickey's Speedway USA campaign on
2026-09-08 a supervising agent read `0/403`, `0/146`, `0/131` and `0/22` from
forced diagnostic runs and reported four exact matches to its operator. None
were matches; every one of those lanes went on to file a plateau. The score
was correct, the reading was wrong, and nothing in the data could have
corrected it.

So the classification is data, in the shape `field_guide.next_steps` and
`stall.read_series` already use: the caller supplies what it knows about how
the object was built, and this returns what may be claimed from it. It does
not inspect objects, run compilers, or guess. A caller that cannot say how the
object was built gets `unknown`, which is never promotable -- guessing `stock`
would recreate exactly the false positive this exists to stop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "FORCING_ENVIRONMENT",
    "Claim",
    "classify_environment",
    "read_result",
]

#: Environment variables whose presence means the allocator was steered. A run
#: with any of these set is diagnostic regardless of what it scored.
FORCING_ENVIRONMENT = (
    "CDX_FORCE",
    "CDX_COLOR_TABLE",
    "CDX_MAX_COLOR",
    "CDX_MAX_FORCE_ENTRY",
    "CDX_COST",
)


@dataclass(frozen=True)
class Claim:
    """What a result supports, and the lines that say so."""

    provenance: str
    claim: str
    lines: tuple[str, ...]

    @property
    def is_match(self) -> bool:
        return self.claim == "match"


def classify_environment(env: Mapping[str, str] | None) -> str:
    """Return `forced`, `stock`, or `unknown` for a build environment.

    `None` means the caller does not know what environment produced the object,
    which is not the same as knowing it was clean.
    """
    if env is None:
        return "unknown"
    if any(name in env for name in FORCING_ENVIRONMENT):
        return "forced"
    return "stock"


def read_result(*, exact: bool, provenance: str) -> Claim:
    """Return what an exact-or-not result may be claimed as."""
    if provenance not in {"stock", "forced", "unknown"}:
        raise ValueError(f"unknown provenance {provenance!r}")

    if not exact:
        return Claim(
            provenance,
            "no-claim",
            ("the candidate differs; nothing to claim beyond the measured residual.",),
        )

    if provenance == "forced":
        return Claim(
            provenance,
            "reachability-proof",
            (
                "NOT A MATCH: zero differing words under allocator forcing.",
                "  this proves the target's allocation is reachable in this web "
                "graph, which is a statement about the allocator, not the source.",
                "  a match needs the same result from the stock compiler; "
                "re-run without the forcing environment before claiming one.",
            ),
        )

    if provenance == "unknown":
        return Claim(
            provenance,
            "unverified",
            (
                "NOT CLAIMABLE: zero differing words, but the build environment "
                "was not supplied.",
                "  a forced run scores identically to a stock one, so this cannot "
                "be told apart from a reachability proof.",
                "  record the environment and re-read before claiming a match.",
            ),
        )

    return Claim(
        provenance,
        "match",
        (
            "match: zero differing words from stock compiler output.",
            "  the ordinary acceptance proofs still apply -- exact owned bytes, "
            "exact relocation identities, and a linked byte comparison.",
        ),
    )
