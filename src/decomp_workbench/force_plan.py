"""Turn a register residual into the force cells that prove or refute it.

`words=0` under `CDX_FORCE` is the strongest verdict the workbench produces
for a register residual, and reaching it used to be typed by hand. On
`overlay4UpdateObjectMotion` (Mickey's Speedway USA, 2026-09-03) it took seven
builds to find that three pinned colours closed the object -- and every one of
those forces was derivable before the first build: the residual names the
registers, the colour table names their colours, and the CDX records name the
webs holding them.

This module is that derivation. For each substitution the residual shows
(candidate register -> target register) it finds the coloured webs holding the
candidate's register, pairs each with the target register's colour, and drops
any pairing whose colour is already in that web's forbidden mask, because the
pass would decline it. The cells come out in the order that attributes a
partial closure: every force alone first, then the full set last.

What it will not do is widen anything. A register no coloured web holds (a
ring temp), a target register with no allocator colour, or a register two webs
hold are reported as such, and the full set is withheld whenever a
substitution has no single eligible force -- an incomplete honest plan is the
contract `oracle plan` already keeps. And the plan's result is never a match:
a forced object is a statement about the allocator.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .cascade import CdxLog
from .globalcolor import color_for_register
from .levers import SweepRecord, sweep_records
from .oracle import PLAN_SCHEMA, _selected_proc

__all__ = [
    "FORCE_PLAN_SCHEMA",
    "plan_force_experiment",
    "substitutions_from_diagnosis",
]

FORCE_PLAN_SCHEMA = "decomp-workbench-force-plan-v1"


def substitutions_from_diagnosis(payload: Mapping[str, Any]) -> dict[str, str]:
    """Read `lever.measurements.substitutions` from a `diagnose --json` report."""

    lever = payload.get("lever")
    measurements = lever.get("measurements") if isinstance(lever, dict) else None
    found = (
        measurements.get("substitutions") if isinstance(measurements, dict) else None
    )
    if not isinstance(found, dict) or not found:
        raise ValueError(
            "the diagnosis carries no lever.measurements.substitutions; run "
            "`diagnose --json` on a register residual (a pool lever), or name "
            "the substitutions with --substitute CANDIDATE=TARGET"
        )
    return {str(key): str(value) for key, value in found.items()}


def _atom(record: SweepRecord, color: int) -> str:
    return f"{record.phase}:w{record.web}=c{color}"


def _row(record: SweepRecord, color: int, target: str) -> dict[str, Any]:
    return {
        "force": _atom(record, color),
        "phase": record.phase,
        "web": record.web,
        "color": color,
        "register": target,
        "held_register": record.register,
        "save": record.save,
    }


def plan_force_experiment(
    log: CdxLog,
    substitutions: Mapping[str, str],
    *,
    proc: int | None = None,
) -> dict[str, Any]:
    """Return the minimal force plan for one residual's substitutions."""

    if not substitutions:
        raise ValueError("no substitutions to plan; the residual names none")
    proc = _selected_proc(log.trace, proc)
    records = sweep_records(log, proc=proc)
    if not records:
        raise ValueError(
            f"the capture records no coloured web for proc {proc}; capture "
            "with CDX_LOG=1 CDX_OUT=<file> and a numeric CDX_PROC"
        )
    entries: list[dict[str, Any]] = []
    chosen: list[dict[str, Any]] = []
    complete = True
    for candidate, target in sorted(substitutions.items()):
        candidate_reg = candidate.removeprefix("$")
        target_reg = target.removeprefix("$")
        color = color_for_register(target_reg)
        holders = [record for record in records if record.register == candidate_reg]
        entry: dict[str, Any] = {
            "candidate": candidate_reg,
            "target": target_reg,
            "target_color": color,
            "holders": [record.as_dict() for record in holders],
            "forces": [],
            "declined": [],
            "status": "",
        }
        if color is None:
            entry["status"] = "target-register-uncoloured"
            entry["reason"] = (
                f"{target_reg} has no allocator colour in the pinned table, so "
                "no force names it; the target's value there is not a "
                "coloured web in this graph"
            )
        elif not holders:
            entry["status"] = "no-coloured-holder"
            entry["reason"] = (
                f"no coloured web holds {candidate_reg}; the candidate's value "
                "there is a ring temp or uncoloured, which no colour force "
                "reaches"
            )
        else:
            for record in holders:
                if color in record.forbidden:
                    entry["declined"].append(
                        {
                            "force": _atom(record, color),
                            "reason": (
                                f"c{color} is in w{record.web}'s forbidden mask; "
                                "the pass declines it"
                            ),
                        }
                    )
                else:
                    entry["forces"].append(_row(record, color, target_reg))
            if not entry["forces"]:
                entry["status"] = "all-forbidden"
                entry["reason"] = (
                    "every web holding the candidate register forbids the "
                    "target's colour: interference, not priority"
                )
            elif len(entry["forces"]) > 1:
                entry["status"] = "ambiguous-holder"
                entry["reason"] = (
                    f"{len(entry['forces'])} coloured webs hold {candidate_reg}; "
                    "each is planned alone and none is chosen for the full set"
                )
            else:
                entry["status"] = "planned"
                chosen.append(entry["forces"][0])
        if entry["status"] != "planned":
            complete = False
        entries.append(entry)

    singletons: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for row in entry["forces"]:
            singletons.setdefault(row["force"], row)
    cells = [{**row, "components": [row]} for row in singletons.values()]
    webs = [(row["phase"], row["web"]) for row in chosen]
    full_set = None
    withheld = None
    if len(chosen) >= 2 and complete and len(set(webs)) == len(webs):
        full_set = {
            "force": ",".join(row["force"] for row in chosen),
            "phase": "combined",
            "web": None,
            "color": None,
            "register": ",".join(row["register"] for row in chosen),
            "components": chosen,
        }
        cells.append(full_set)
    elif len(chosen) >= 2 or not complete:
        withheld = (
            "the full set is withheld: "
            + (
                "two substitutions name the same web"
                if len(set(webs)) != len(webs)
                else "a substitution has no single eligible force"
            )
            + "; the singletons still attribute what each force closes"
        )
    return {
        "schema": FORCE_PLAN_SCHEMA,
        "evidence": "diagnostic-force-plan",
        "procedure": proc,
        "substitutions": entries,
        "cells": [cell["force"] for cell in cells],
        "complete": complete,
        "full_set": full_set["force"] if full_set else None,
        "withheld": withheld,
        "oracle_plan": {
            "schema": PLAN_SCHEMA,
            "evidence": "diagnostic-oracle-plan",
            "procedure": proc,
            "coverage": {
                "source": "force-plan",
                "substitutions": len(entries),
                "cells": len(cells),
            },
            "forces": cells,
            "force_count": len(cells),
            "restriction": "force-plan",
        },
        "proof": (
            "A plan of compiler-decision probes, singletons first so a partial "
            "closure is attributed to one force. words=0 under the full set "
            "proves the target's colours are legal in this web graph; it is "
            "never a source match."
        ),
    }
