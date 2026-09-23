"""Build-provenance options shared by every command that scores an object.

`compare`, `score` and `diagnose` report the same numbers whether the object
they read came from the stock compiler or from a forced or traced run. These
options make the reading state which one it was -- on the terminal ahead of the
verdict and in JSON as a namespaced `build_provenance` block -- and refuse to
read at all from a shell that exports forcing or tracing variables when the
caller has not said how the object was built.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .provenance import (
    BUILD_PROVENANCE_SCHEMA,
    BUILD_VALUES,
    BuildProvenance,
    ProvenanceRefusal,
    resolve_build_provenance,
)

__all__ = [
    "add_build_provenance_arguments",
    "build_provenance_payload",
    "guard_build_provenance",
]


def add_build_provenance_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "build provenance",
        "How the candidate object was built. A forced or traced object scores "
        "exactly like a stock one; only a declared stock build makes an exact "
        "result a claimable match.",
    )
    group.add_argument(
        "--build-env",
        choices=BUILD_VALUES,
        help="how the candidate was built: stock, forced, instrumented, unknown",
    )
    group.add_argument(
        "--build-env-file",
        metavar="FILE",
        help=(
            "a JSON object of the environment the candidate was built with "
            "(or a document holding it under `environment`); classified the "
            "same way"
        ),
    )


def _read_environment(path: str) -> dict[str, str]:
    try:
        value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProvenanceRefusal(f"cannot read --build-env-file: {error}") from None
    if isinstance(value, dict) and isinstance(value.get("environment"), dict):
        value = value["environment"]
    if not isinstance(value, dict):
        raise ProvenanceRefusal("--build-env-file must hold a JSON object")
    return {str(key): str(item) for key, item in value.items()}


def guard_build_provenance(args: argparse.Namespace) -> BuildProvenance:
    """Resolve the candidate's build provenance, refusing an unstated mix.

    Stores the result on `args` for the rendering half and returns it. Raises
    `ProvenanceRefusal` (a `ValueError`), which every scoring command already
    reports as `error: ...` and exit 2.
    """

    path = getattr(args, "build_env_file", None)
    provenance = resolve_build_provenance(
        declared=getattr(args, "build_env", None),
        build_environment=_read_environment(path) if path else None,
        process_environment=os.environ,
    )
    args.build_provenance = provenance
    return provenance


def build_provenance_payload(
    args: argparse.Namespace, *, exact: bool
) -> dict[str, Any]:
    """The namespaced JSON block, or nothing if the guard never ran."""

    provenance = getattr(args, "build_provenance", None)
    if not isinstance(provenance, BuildProvenance):
        return {}
    return {
        "build_provenance": provenance.as_dict(exact=exact),
        "build_provenance_schema": BUILD_PROVENANCE_SCHEMA,
    }


def build_provenance_lines(args: argparse.Namespace, *, exact: bool) -> list[str]:
    provenance = getattr(args, "build_provenance", None)
    if not isinstance(provenance, BuildProvenance):
        return []
    return list(provenance.lines(exact=exact))
