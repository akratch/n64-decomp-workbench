"""Composition of guarded instrumentation profiles for IDO 5.3 uopt."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from .instrument_alias import instrument_uopt_alias
from .instrument_uopt import IDO_53_V12_SHA256, instrument_uopt_globalcolor


SUPPORTED_PROFILES = ("alias", "globalcolor")


@dataclass(frozen=True)
class UoptProfilesResult:
    """Instrumented source and the profiles applied to it."""

    source: str
    input_sha256: str
    profiles: tuple[str, ...]
    trace_points: int
    profile: str = "ido-5.3-static-recomp-v12"


def instrument_uopt_profiles(
    source: str,
    profiles: Iterable[str],
    *,
    allow_unverified_source: bool = False,
) -> UoptProfilesResult:
    """Apply one or more compatible profiles after one input validation."""

    requested = tuple(dict.fromkeys(profiles))
    if not requested:
        raise ValueError("select at least one uopt instrumentation profile")
    unknown = sorted(set(requested) - set(SUPPORTED_PROFILES))
    if unknown:
        raise ValueError(
            "unknown uopt profile(s): "
            + ", ".join(unknown)
            + "; expected alias or globalcolor"
        )

    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if not allow_unverified_source and digest != IDO_53_V12_SHA256:
        raise ValueError(
            "source SHA-256 is not the pinned IDO 5.3 static-recomp profile "
            f"({digest}); pass --allow-unverified-source only after reviewing "
            "every anchor and running a disabled-instrumentation fidelity test"
        )

    # A fixed order makes repeated invocations and source diffs reproducible.
    ordered = tuple(
        profile for profile in SUPPORTED_PROFILES if profile in requested
    )
    instrumented = source
    trace_points = 0
    for profile in ordered:
        if profile == "alias":
            result = instrument_uopt_alias(
                instrumented, allow_unverified_source=True
            )
        else:
            result = instrument_uopt_globalcolor(
                instrumented, allow_unverified_source=True
            )
        instrumented = result.source
        trace_points += result.trace_points

    return UoptProfilesResult(
        source=instrumented,
        input_sha256=digest,
        profiles=ordered,
        trace_points=trace_points,
    )
