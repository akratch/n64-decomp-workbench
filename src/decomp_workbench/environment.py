"""Validation and composition for explicit compiler environments."""

from __future__ import annotations

import re
from pathlib import Path

from .instrument_uopt import parse_force_specification
from .toolchain import toolchain_environment


def parse_environment(values: list[str]) -> dict[str, str]:
    """Parse explicit NAME=VALUE entries and validate known controls."""

    result: dict[str, str] = {}
    for value in values:
        name, separator, content = value.partition("=")
        if (
            not separator
            or not name
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        ):
            raise ValueError(f"invalid environment entry: {value!r}")
        result[name] = content
    if "CDX_FORCE" in result:
        parse_force_specification(result["CDX_FORCE"])
    return result


def merge_toolchain_environment(
    environment: dict[str, str],
    toolchain: str | Path,
    *,
    require_ready: bool = False,
) -> dict[str, str]:
    """Join verified path-sensitive toolchain settings without ambiguity."""

    supplied = toolchain_environment(toolchain, require_ready=require_ready)
    for name, value in supplied.items():
        if name in environment and environment[name] != value:
            raise ValueError(
                f"--toolchain supplies {name}={value!r}, but --env supplied "
                f"{environment[name]!r}"
            )
    return {**supplied, **environment}
