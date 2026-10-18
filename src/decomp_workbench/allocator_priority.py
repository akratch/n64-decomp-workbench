"""IDO 5.3 saving arithmetic, not an allocator or a source transformation.

Input values are explicit observations, not inferred from block intersection.
Decimal trace text may already be rounded; rational arithmetic below explains
those supplied values, and does not reproduce native floating-point ties.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any


class PriorityError(ValueError):
    """The observations do not support the requested arithmetic."""


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PriorityError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PriorityError(f"{label} must be a finite number")
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise PriorityError(f"{label} must be a finite number") from error


def normalized_units(raw: int) -> int:
    """Native compute_save compression, after occurrences plus auxiliary bits."""
    raw = _integer(raw, "raw units")
    return raw if raw < 3 else 2 + (raw - 2) // 4


def raw_unit_band(units: int) -> tuple[int, int]:
    """Inclusive raw interval giving one compressed divisor."""
    units = _integer(units, "units")
    if units < 2:
        return units, units
    return (2 if units == 2 else 4 * (units - 2) + 2), 4 * (units - 2) + 5


def strict_net_window(
    lower_priority: object, upper_priority: object, units: int
) -> dict[str, str]:
    """Explain lower < net/units < upper; equality is deliberately excluded."""
    units = _integer(units, "units")
    lower = _number(lower_priority, "lower priority")
    upper = _number(upper_priority, "upper priority")
    if units == 0 or lower >= upper:
        raise PriorityError("window requires positive units and lower < upper")
    return {"net_gt": str(lower * units), "net_lt": str(upper * units)}


def priority_report(
    decisions: Sequence[Mapping[str, Any]],
    changes: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recompute every supplied role under fixed phase, graph and register costs.

    Required fields: id, phase, order, gross, charge_a, charge_b, occurrences,
    auxiliary_blocks, register_class, snapshot. One authenticated comparison
    context is required; classes or eligibility snapshots cannot mix.
    Changes admit only net_delta/raw_delta. Native observed
    order is retained separately; equal mathematical priorities stay unordered.
    """
    changes = changes or {}
    ids: set[str] = set()
    orders: set[int] = set()
    rows: list[dict[str, Any]] = []
    contexts: set[tuple[str, str, int]] = set()
    priorities: dict[str, Fraction] = {}
    for decision in decisions:
        identifier = decision.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise PriorityError("decision ids must be nonempty and unique")
        ids.add(identifier)
        register_class = decision.get("register_class")
        snapshot = decision.get("snapshot")
        if register_class not in ("gpr", "fpr"):
            raise PriorityError("register_class must be gpr or fpr")
        if not isinstance(snapshot, str) or not snapshot.strip():
            raise PriorityError(
                "snapshot must name one authenticated eligibility state"
            )
        procedure = _integer(decision.get("procedure"), "procedure")
        contexts.add((register_class, snapshot, procedure))
        if len(contexts) > 1:
            raise PriorityError(
                "cannot mix register classes, procedures or eligibility snapshots"
            )
        phase = decision.get("phase")
        if phase not in ("p1", "p2"):
            raise PriorityError("phase must be p1 or p2")
        order = _integer(decision.get("order"), "observed order")
        if order in orders:
            raise PriorityError("observed orders must be unique")
        orders.add(order)
        occurrences = _integer(decision.get("occurrences"), "occurrences")
        auxiliary = decision.get("auxiliary_blocks")
        if not isinstance(auxiliary, list):
            raise PriorityError("auxiliary_blocks must be a list")
        blocks = [_integer(block, "auxiliary block") for block in auxiliary]
        if len(set(blocks)) != len(blocks):
            raise PriorityError("auxiliary blocks must be unique")
        gross = _number(decision.get("gross"), "gross")
        charge_a = _number(decision.get("charge_a"), "charge_a")
        charge_b = _number(decision.get("charge_b"), "charge_b")
        change = changes.get(identifier, {})
        if set(change) - {"net_delta", "raw_delta"}:
            raise PriorityError("changes admit only net_delta and raw_delta")
        raw_delta = change.get("raw_delta", 0)
        if isinstance(raw_delta, bool) or not isinstance(raw_delta, int):
            raise PriorityError("raw_delta must be an integer")
        raw = occurrences + len(blocks) + raw_delta
        units = normalized_units(raw)
        net = gross - charge_a - charge_b
        delta = _number(change.get("net_delta", 0), "net_delta")
        net += delta
        band = raw_unit_band(units)
        row: dict[str, Any] = {
            "id": identifier,
            "phase": phase,
            "observed_order": order,
            "gross": str(gross),
            "charge_a": str(charge_a),
            "charge_b": str(charge_b),
            "net_delta": str(delta),
            "net": str(net),
            "occurrences": occurrences,
            "auxiliary_blocks": blocks,
            "raw_delta": raw_delta,
            "raw_units": raw,
            "units": units,
            "raw_unit_band": list(band),
            "raw_additions_to_next_unit": band[1] + 1 - raw,
            "raw_removals_to_previous_unit": raw - band[0] + 1 if units else None,
            "priority": str(net / units) if units else None,
        }
        if units:
            priorities[identifier] = net / units
        if "bestcost" in decision:
            cost = _number(decision["bestcost"], "bestcost")
            row["bestcost"] = str(cost)
            row["net_vs_bestcost"] = (
                "greater" if net > cost else "equal" if net == cost else "less"
            )
        rows.append(row)
    if set(changes) - ids:
        raise PriorityError("changes reference an unknown decision")
    rows.sort(key=lambda row: row["observed_order"])
    p1 = [row for row in rows if row["phase"] == "p1"]
    if any(row["priority"] is None for row in p1):
        raise PriorityError("phase-one priority needs positive units")
    levels = sorted({priorities[row["id"]] for row in p1}, reverse=True)
    return {
        "schema": "decomp-workbench-allocator-priority-v1",
        "comparison_context": (
            {
                "register_class": next(iter(contexts))[0],
                "snapshot": next(iter(contexts))[1],
                "procedure": next(iter(contexts))[2],
            }
            if contexts
            else None
        ),
        "rows": rows,
        "p1_priority_groups": [
            [row["id"] for row in p1 if priorities[row["id"]] == level]
            for level in levels
        ],
        "p2_observed_order": [row["id"] for row in rows if row["phase"] == "p2"],
        "allocation_proof": False,
        "assumptions": [
            "Phase, graph, eligibility, split pieces and register costs fixed.",
            "All affected roles must be supplied; no completeness is inferred.",
            "P1 groups explain priority only; ties have no inferred native order.",
            "P2 remains observed order; saving changes do not reorder it.",
            "Rational values explain supplied decimals, not native float rounding.",
            "Priority is net/units; split acceptance also needs total net and cost.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON decisions and optional changes")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(
            payload.get("decisions"), list
        ):
            raise PriorityError("input must contain a decisions list")
        if any(not isinstance(row, dict) for row in payload["decisions"]):
            raise PriorityError("decisions must be objects")
        changes = payload.get("changes", {})
        if not isinstance(changes, dict) or any(
            not isinstance(row, dict) for row in changes.values()
        ):
            raise PriorityError("changes must map ids to objects")
        result = priority_report(payload["decisions"], changes)
    except (OSError, ValueError) as error:
        parser.exit(2, f"priority report: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
