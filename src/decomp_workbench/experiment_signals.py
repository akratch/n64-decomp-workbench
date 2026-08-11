"""Declarative, selected-function experiment signals."""

from __future__ import annotations

from typing import Any

from .experiments import SignalSpec
from .model import Comparison

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"


def _receipt(
    spec: SignalSpec, status: str, reason: str, **evidence: Any
) -> dict[str, Any]:
    return {
        "id": spec.id,
        "kind": spec.kind,
        "required": spec.required,
        "status": status,
        "reason": reason,
        **evidence,
    }


def _requested_rows(spec: SignalSpec) -> list[int]:
    rows = {int(row) for row in spec.config.get("rows", [])}
    for interval in spec.config.get("ranges", []):
        rows.update(range(int(interval["start"]), int(interval["end"])))
    return sorted(rows)


def _rows_exact(
    spec: SignalSpec, comparison: Comparison, rows: list[int]
) -> dict[str, Any]:
    if not rows:
        return _receipt(spec, STATUS_UNKNOWN, "no target rows were requested")
    unavailable = [row for row in rows if row >= comparison.target_instructions]
    if unavailable:
        return _receipt(
            spec,
            STATUS_UNKNOWN,
            "requested target row is outside the selected function",
            requested_rows=rows,
            unavailable_rows=unavailable,
        )
    by_target = {
        int(item["target_index"]): item
        for item in comparison.aligned_row_receipts
        if item.get("target_index") is not None
    }
    missing = [row for row in rows if row not in by_target]
    if missing:
        return _receipt(
            spec,
            STATUS_UNKNOWN,
            "alignment did not produce a receipt for every requested target row",
            requested_rows=rows,
            unavailable_rows=missing,
        )
    field = (
        "raw_exact"
        if spec.config.get("comparison", "relocation-aware") == "raw"
        else "relocation_aware_exact"
    )
    failed = [row for row in rows if not bool(by_target[row].get(field))]
    status = STATUS_FAIL if failed else STATUS_PASS
    return _receipt(
        spec,
        status,
        "one or more selected target rows differ"
        if failed
        else "all selected target rows agree",
        comparison=spec.config.get("comparison", "relocation-aware"),
        requested_rows=rows,
        failed_rows=failed,
        matched_rows=len(rows) - len(failed),
    )


def _metric_signal(spec: SignalSpec, comparison: Comparison) -> dict[str, Any]:
    values = comparison.as_dict()
    observed: dict[str, Any] = {}
    failures: list[str] = []
    unavailable: list[str] = []
    for predicate in ("equals", "minimum", "maximum"):
        expected = spec.config.get(predicate, {})
        for key, wanted in expected.items():
            actual = values.get(key)
            observed[key] = actual
            if actual is None:
                unavailable.append(key)
                continue
            try:
                passed = (
                    actual == wanted
                    if predicate == "equals"
                    else actual >= wanted
                    if predicate == "minimum"
                    else actual <= wanted
                )
            except TypeError:
                unavailable.append(key)
                continue
            if not passed:
                failures.append(f"{predicate}:{key}")
    if unavailable:
        return _receipt(
            spec,
            STATUS_UNKNOWN,
            "one or more requested metrics are unavailable or incomparable",
            observed=observed,
            unavailable=sorted(set(unavailable)),
        )
    return _receipt(
        spec,
        STATUS_FAIL if failures else STATUS_PASS,
        "metric predicate failed" if failures else "all metric predicates passed",
        observed=observed,
        failed_predicates=failures,
    )


def _residual_signal(spec: SignalSpec, comparison: Comparison) -> dict[str, Any]:
    observed = {
        name: int(getattr(comparison, f"aligned_{name}"))
        for name in ("structural", "schedule", "register", "constant", "commutative")
    }
    present = {name for name, count in observed.items() if count}
    allowed = set(spec.config.get("allowed", observed))
    forbidden = set(spec.config.get("forbidden", []))
    violations = sorted((present - allowed) | (present & forbidden))
    return _receipt(
        spec,
        STATUS_FAIL if violations else STATUS_PASS,
        "residual class predicate failed"
        if violations
        else "residual classes are within the declared set",
        observed=observed,
        violations=violations,
    )


def evaluate_signal(spec: SignalSpec, comparison: Comparison | None) -> dict[str, Any]:
    """Evaluate one signal without loading any object or target text."""

    if comparison is None:
        return _receipt(spec, STATUS_UNKNOWN, "candidate comparison is unavailable")
    if spec.kind == "target-rows-exact":
        return _rows_exact(spec, comparison, _requested_rows(spec))
    if spec.kind == "target-region-exact":
        return _rows_exact(
            spec,
            comparison,
            list(range(int(spec.config["start"]), int(spec.config["end"]))),
        )
    if spec.kind == "metrics":
        return _metric_signal(spec, comparison)
    return _residual_signal(spec, comparison)


def evaluate_signals(
    specs: tuple[SignalSpec, ...], comparison: Comparison | None
) -> list[dict[str, Any]]:
    return [evaluate_signal(spec, comparison) for spec in specs]


def required_signals_pass(receipts: list[dict[str, Any]]) -> bool:
    return all(
        item.get("status") == STATUS_PASS
        for item in receipts
        if bool(item.get("required"))
    )
