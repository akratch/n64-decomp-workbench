"""Honest handoff from register permutations to allocator oracle tooling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .view import MechanismView, uncolorable_targets

FORCE_SPEC_SCHEMA = "decomp-workbench-diagnostic-force-v1"


def force_specification(view: MechanismView) -> dict[str, Any]:
    """Describe the observed permutation without inventing allocator web IDs."""

    if view.verdict == "register-ring-only":
        named = ", ".join(
            web.target for web in uncolorable_targets(view.webs, view.register_profile)
        )
        raise ValueError(
            "--emit-force-spec cannot address this residual: every target "
            f"register in it ({named}) is outside the era's colorable set, so "
            "no forced color reaches one. A forced-color campaign here is "
            "dead on arrival. This is a web-existence question -- which "
            "values became block-local temps -- so start from "
            "`decomp-workbench guide temp-fifo-phase`."
        )
    if view.verdict != "register-permutation":
        raise ValueError("--emit-force-spec requires a register-permutation verdict")
    ring_only = {
        web.web for web in uncolorable_targets(view.webs, view.register_profile)
    }
    return {
        "schema": FORCE_SPEC_SCHEMA,
        "evidence": "diagnostic-oracle-input",
        "proof": (
            "Observed register permutation only. The wN labels are local aligned "
            "groups, not compiler allocator web IDs; join them to a calibrated "
            "trace before constructing CDX_FORCE controls."
            + (
                " Entries marked ring_only_target want a register the era's "
                "coloring pass never hands out: no force reaches those, and a "
                "probe can close only the rest."
                if ring_only
                else ""
            )
        ),
        "target": view.target,
        "candidate": view.candidate,
        "symbol": view.symbol,
        "register_profile": view.register_profile,
        "permutation": [
            {
                "aligned_web": web.web,
                # ROM-derived, like the HTML report and for the same reason:
                # this names a register in the *target*. A force specification
                # is an operator-named artifact, not an automatic one, but it
                # is still not something to commit. See ledger_redaction.
                "target_register": web.target,
                "candidate_register": web.candidate,
                "affected_indices": list(web.rows),
                "sites": web.count,
                "allocator_web": None,
                "phase": None,
                "ring_only_target": web.web in ring_only,
            }
            for web in view.webs
        ],
    }


def write_force_specification(view: MechanismView, path: str | Path) -> Path:
    """Write a diagnostic permutation handoff without overwriting a file."""

    output = Path(path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite force specification: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as destination:
        destination.write(
            json.dumps(force_specification(view), indent=2, sort_keys=True) + "\n"
        )
    return output
