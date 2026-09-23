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
    "BUILD_PROVENANCE_SCHEMA",
    "BUILD_VALUES",
    "FORCING_ENVIRONMENT",
    "TRACING_ENVIRONMENT",
    "BuildProvenance",
    "Claim",
    "ProvenanceRefusal",
    "classify_build",
    "classify_environment",
    "read_result",
    "resolve_build_provenance",
]

BUILD_PROVENANCE_SCHEMA = "decomp-workbench-build-provenance-v1"

#: Environment variables whose presence means the allocator was steered. A run
#: with any of these set is diagnostic regardless of what it scored.
FORCING_ENVIRONMENT = (
    "CDX_FORCE",
    "CDX_COLOR_TABLE",
    "CDX_MAX_COLOR",
    "CDX_MAX_FORCE_ENTRY",
    "CDX_COST",
)

#: Variables that turn an instrumented compiler's tracing on. A traced build is
#: stock code generation only if the fidelity gate says so, and a campaign
#: shell that still exports them is the shell a forced run was made in.
TRACING_ENVIRONMENT = (
    "CDX_LOG",
    "CDX_OUT",
    "CDX_DETAIL_WEB",
    "CDX_LINEAGE_TABLES",
    "CDX_SYMTAB",
    "CDX_PROC",
    "DKWB_UGEN_TRACE",
    "DKWB_UGEN_SCHED",
    "DKWB_UOPT_ALIAS_TRACE",
)

#: Every build provenance a report can carry.
BUILD_VALUES = ("stock", "forced", "instrumented", "unknown")


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


def classify_build(env: Mapping[str, str] | None) -> str:
    """Return `forced`, `instrumented`, `stock`, or `unknown` for a build.

    Finer than :func:`classify_environment`: a build with tracing on but no
    force is `instrumented`, which is not `stock` until an instrument gate has
    shown that tracing leaves code generation alone.
    """
    if env is None:
        return "unknown"
    if any(name in env for name in FORCING_ENVIRONMENT):
        return "forced"
    if any(name in env for name in TRACING_ENVIRONMENT):
        return "instrumented"
    return "stock"


class ProvenanceRefusal(ValueError):
    """A comparison was asked to read an object whose build it cannot state."""


@dataclass(frozen=True)
class BuildProvenance:
    """How the object a comparison read was built, and how that is known.

    `basis` is `declared` (the caller said so), `environment-file` (read from
    the environment the object was built with), or `undeclared` (nothing was
    said and the shell carries no forcing or tracing variable). An undeclared
    build is `unknown`: never promotable, and never silently `stock`.
    """

    provenance: str
    basis: str
    variables: tuple[str, ...] = ()

    def claim(self, *, exact: bool) -> Claim:
        return read_result(exact=exact, provenance=self.provenance)

    def lines(self, *, exact: bool) -> tuple[str, ...]:
        if self.basis == "undeclared":
            head = (
                "build: undeclared -- this shell sets no forcing or tracing "
                "variable; pass --build-env stock to make an exact result "
                "claimable"
            )
        else:
            source = (
                "declared" if self.basis == "declared" else "from the build environment"
            )
            detail = f" ({', '.join(self.variables)})" if self.variables else ""
            head = f"build: {self.provenance}, {source}{detail}"
        if not exact or self.provenance == "stock" or self.basis == "undeclared":
            return (head,)
        return (head, *self.claim(exact=True).lines)

    def as_dict(self, *, exact: bool) -> dict[str, object]:
        claim = self.claim(exact=exact)
        return {
            "provenance": self.provenance,
            "basis": self.basis,
            "variables": list(self.variables),
            "claim": claim.claim,
            "claim_lines": list(claim.lines),
        }


def resolve_build_provenance(
    *,
    declared: str | None,
    build_environment: Mapping[str, str] | None,
    process_environment: Mapping[str, str],
) -> BuildProvenance:
    """Decide what a comparison may say about how its object was built.

    Precedence: a declaration, then the environment the object was built
    with. With neither, a shell that exports a forcing or tracing variable is
    a refusal: the object in hand may be the forced build, or the stock
    rebuild a project script made over it, and the two score identically. A
    Mickey's Speedway USA lane read the same score for twelve different forces
    before noticing its scorer had rebuilt the unforced object each time.
    """

    if declared is not None and build_environment is not None:
        raise ProvenanceRefusal(
            "pass --build-env or --build-env-file, not both; they are two "
            "answers to one question"
        )
    if declared is not None:
        if declared not in BUILD_VALUES:
            raise ProvenanceRefusal(f"unknown --build-env {declared!r}")
        return BuildProvenance(declared, "declared")
    if build_environment is not None:
        variables = tuple(
            sorted(
                name
                for name in (*FORCING_ENVIRONMENT, *TRACING_ENVIRONMENT)
                if name in build_environment
            )
        )
        return BuildProvenance(
            classify_build(build_environment), "environment-file", variables
        )
    present = tuple(
        sorted(
            name
            for name in (*FORCING_ENVIRONMENT, *TRACING_ENVIRONMENT)
            if name in process_environment
        )
    )
    if present:
        raise ProvenanceRefusal(
            "this shell exports "
            + ", ".join(present)
            + ", so the object being read may be a forced or traced build, or "
            "a stock rebuild made over it -- they score identically. Say which "
            "with --build-env stock|forced|instrumented, or pass the build's "
            "environment with --build-env-file"
        )
    return BuildProvenance("unknown", "undeclared")


def read_result(*, exact: bool, provenance: str) -> Claim:
    """Return what an exact-or-not result may be claimed as."""
    if provenance not in set(BUILD_VALUES):
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

    if provenance == "instrumented":
        return Claim(
            provenance,
            "unverified",
            (
                "NOT YET CLAIMABLE: zero differing words from an instrumented "
                "compiler with tracing on.",
                "  tracing leaves code generation alone only where an instrument "
                "gate has shown it; re-score the stock compiler's object before "
                "claiming a match.",
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
