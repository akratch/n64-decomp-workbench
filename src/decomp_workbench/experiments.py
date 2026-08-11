"""Project-neutral experiment manifests and selected-region constraints."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPERIMENT_SCHEMA_V1 = "decomp-workbench-experiment-v1"
EXPERIMENT_SCHEMA_V2 = "decomp-workbench-experiment-v2"
EXPERIMENT_SCHEMA = EXPERIMENT_SCHEMA_V1
EXPERIMENT_SCHEMAS = frozenset({EXPERIMENT_SCHEMA_V1, EXPERIMENT_SCHEMA_V2})

SIGNAL_KINDS = frozenset(
    {"target-rows-exact", "target-region-exact", "metrics", "residual-classes"}
)
RESIDUAL_CLASS_NAMES = frozenset(
    {"structural", "schedule", "register", "constant", "commutative"}
)


@dataclass(frozen=True)
class SignalSpec:
    """One declarative predicate over an existing selected-function comparison."""

    id: str
    kind: str
    required: bool
    config: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "required": self.required,
            **self.config,
        }


@dataclass(frozen=True)
class ControlSpec:
    """One absolute or differential canary compiled before ordinary work."""

    id: str
    kind: str
    candidates: tuple[Path, ...]
    expect: dict[str, Any]
    required: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "required": self.required,
            "expect": self.expect,
        }
        if self.kind == "absolute":
            payload["candidate"] = str(self.candidates[0])
        else:
            payload["candidates"] = [str(item) for item in self.candidates]
        return payload


@dataclass(frozen=True)
class RegionConstraint:
    """A half-open instruction-index range that a campaign should preserve."""

    start: int
    end: int
    name: str = "selected"

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                "selected_region requires 0 <= start < end instruction indices"
            )

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "start": self.start, "end": self.end}


@dataclass(frozen=True)
class ExperimentManifest:
    """Validated transformation-family metadata from an external generator."""

    path: Path
    schema: str
    family: str
    baseline: Path
    parameter_space: dict[str, list[Any]]
    candidates: dict[Path, dict[str, Any]]
    homologous_parameters: tuple[tuple[str, ...], ...]
    region: RegionConstraint | None
    signals: tuple[SignalSpec, ...]
    controls: tuple[ControlSpec, ...]
    coverage: dict[str, Any]
    raw: dict[str, Any]

    def metadata_for(self, source: str | Path) -> dict[str, Any]:
        resolved = Path(source).expanduser().resolve()
        payload = {
            "schema": self.schema,
            "family": self.family,
            "parameters": self.candidates.get(resolved, {}),
            "parameter_space": self.parameter_space,
            "baseline": str(self.baseline),
            "manifest": str(self.path),
            "homologous_parameters": [
                list(group) for group in self.homologous_parameters
            ],
        }
        if self.schema == EXPERIMENT_SCHEMA_V2:
            payload["signals"] = [signal.id for signal in self.signals]
        return payload

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "path": str(self.path),
            "family": self.family,
            "baseline": str(self.baseline),
            "parameters": self.parameter_space,
            "candidates": [
                {"source": str(source), "parameters": parameters}
                for source, parameters in sorted(
                    self.candidates.items(), key=lambda item: str(item[0])
                )
            ],
            "homologous_parameters": [
                list(group) for group in self.homologous_parameters
            ],
            "selected_region": self.region.as_dict() if self.region else None,
        }
        if self.schema == EXPERIMENT_SCHEMA_V2:
            payload.update(
                signals=[signal.as_dict() for signal in self.signals],
                controls=[control.as_dict() for control in self.controls],
                coverage=self.coverage,
            )
        return payload

    def identity_receipt(self) -> dict[str, Any]:
        """Return the normalized definition that participates in run identity."""

        payload = self.as_dict()
        if self.schema == EXPERIMENT_SCHEMA_V2:
            sources = {
                self.baseline,
                *self.candidates,
                *(source for control in self.controls for source in control.candidates),
            }
            payload["input_sha256"] = {
                str(source): hashlib.sha256(source.read_bytes()).hexdigest()
                for source in sorted(sources, key=str)
            }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return {
            "schema": self.schema,
            "path": str(self.path),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }


def _resolve(root: Path, value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"experiment {field} must be a non-empty path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _parse_region(value: object) -> RegionConstraint | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("experiment selected_region must be an object")
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            "experiment selected_region requires integer start and end"
        ) from None
    name = value.get("name", "selected")
    if not isinstance(name, str) or not name:
        raise ValueError("experiment selected_region name must be a string")
    return RegionConstraint(start=start, end=end, name=name)


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"experiment {field} must be a non-empty string")
    normalized = value.strip()
    if not all(character.isalnum() or character in "._-" for character in normalized):
        raise ValueError(f"experiment {field} contains unsupported characters")
    return normalized


def _parse_signal(value: object, *, index: int) -> SignalSpec:
    if not isinstance(value, dict):
        raise ValueError(f"experiment signal {index} must be an object")
    allowed = {
        "id",
        "kind",
        "required",
        "rows",
        "ranges",
        "start",
        "end",
        "name",
        "comparison",
        "equals",
        "minimum",
        "maximum",
        "allowed",
        "forbidden",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(
            f"experiment signal {index} has unknown field(s): "
            + ", ".join(sorted(unknown))
        )
    signal_id = _identifier(value.get("id"), field=f"signal {index} id")
    kind = value.get("kind")
    if kind not in SIGNAL_KINDS:
        raise ValueError(
            f"experiment signal {signal_id!r} kind must be one of: "
            + ", ".join(sorted(SIGNAL_KINDS))
        )
    required = value.get("required", False)
    if not isinstance(required, bool):
        raise ValueError(f"experiment signal {signal_id!r} required must be boolean")
    config = {
        key: item
        for key, item in value.items()
        if key not in {"id", "kind", "required"}
    }
    fields_by_kind = {
        "target-rows-exact": {"rows", "ranges", "comparison"},
        "target-region-exact": {"start", "end", "name", "comparison"},
        "metrics": {"equals", "minimum", "maximum"},
        "residual-classes": {"allowed", "forbidden"},
    }
    irrelevant = set(config) - fields_by_kind[str(kind)]
    if irrelevant:
        raise ValueError(
            f"experiment signal {signal_id!r} has field(s) invalid for "
            f"{kind}: " + ", ".join(sorted(irrelevant))
        )
    if kind == "target-rows-exact":
        rows = config.get("rows", [])
        ranges = config.get("ranges", [])
        if not isinstance(rows, list) or not all(
            isinstance(row, int) and row >= 0 for row in rows
        ):
            raise ValueError(
                f"experiment signal {signal_id!r} rows must be non-negative integers"
            )
        if not isinstance(ranges, list):
            raise ValueError(f"experiment signal {signal_id!r} ranges must be a list")
        for item in ranges:
            if (
                not isinstance(item, dict)
                or set(item) != {"start", "end"}
                or not isinstance(item["start"], int)
                or not isinstance(item["end"], int)
                or item["start"] < 0
                or item["end"] <= item["start"]
            ):
                raise ValueError(
                    f"experiment signal {signal_id!r} has an invalid half-open range"
                )
        if not rows and not ranges:
            raise ValueError(f"experiment signal {signal_id!r} requires rows or ranges")
        mode = config.get("comparison", "relocation-aware")
        if mode not in {"raw", "relocation-aware"}:
            raise ValueError(
                f"experiment signal {signal_id!r} comparison must be raw or "
                "relocation-aware"
            )
        config["comparison"] = mode
    elif kind == "target-region-exact":
        try:
            region = RegionConstraint(
                int(config["start"]),
                int(config["end"]),
                str(config.get("name", signal_id)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"experiment signal {signal_id!r} requires valid start/end"
            ) from error
        mode = config.get("comparison", "relocation-aware")
        if mode not in {"raw", "relocation-aware"}:
            raise ValueError(
                f"experiment signal {signal_id!r} comparison must be raw or "
                "relocation-aware"
            )
        config = {**region.as_dict(), "comparison": mode}
    elif kind == "metrics":
        predicates = [
            name for name in ("equals", "minimum", "maximum") if name in config
        ]
        if not predicates:
            raise ValueError(
                f"experiment signal {signal_id!r} requires a metric predicate"
            )
        from .schema import METRICS_BY_KEY

        for predicate in predicates:
            values = config[predicate]
            if not isinstance(values, dict) or not values:
                raise ValueError(
                    f"experiment signal {signal_id!r} {predicate} must be an object"
                )
            unknown_metrics = set(values) - set(METRICS_BY_KEY)
            if unknown_metrics:
                raise ValueError(
                    f"experiment signal {signal_id!r} has unknown metric(s): "
                    + ", ".join(sorted(unknown_metrics))
                )
    else:
        allowed_classes = config.get("allowed", list(RESIDUAL_CLASS_NAMES))
        forbidden = config.get("forbidden", [])
        for field, classes in (("allowed", allowed_classes), ("forbidden", forbidden)):
            if not isinstance(classes, list) or not all(
                isinstance(item, str) for item in classes
            ):
                raise ValueError(
                    f"experiment signal {signal_id!r} {field} must be a list"
                )
            unknown_classes = set(classes) - RESIDUAL_CLASS_NAMES
            if unknown_classes:
                raise ValueError(
                    f"experiment signal {signal_id!r} has unknown residual class(es): "
                    + ", ".join(sorted(unknown_classes))
                )
        config = {"allowed": allowed_classes, "forbidden": forbidden}
    return SignalSpec(signal_id, str(kind), required, config)


def parse_signal_specs(values: object) -> tuple[SignalSpec, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise ValueError("experiment signals must be a list")
    signals = tuple(
        _parse_signal(value, index=index) for index, value in enumerate(values)
    )
    ids = [signal.id for signal in signals]
    if len(ids) != len(set(ids)):
        raise ValueError("experiment signal ids must be unique")
    return signals


def _parse_controls(root: Path, values: object) -> tuple[ControlSpec, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise ValueError("experiment controls must be a list")
    controls: list[ControlSpec] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"experiment control {index} must be an object")
        unknown = set(value) - {
            "id",
            "kind",
            "candidate",
            "candidates",
            "expect",
            "required",
        }
        if unknown:
            raise ValueError(
                f"experiment control {index} has unknown field(s): "
                + ", ".join(sorted(unknown))
            )
        control_id = _identifier(value.get("id"), field=f"control {index} id")
        kind = value.get("kind", "absolute")
        if kind not in {"absolute", "differential"}:
            raise ValueError(
                f"experiment control {control_id!r} kind must be absolute or "
                "differential"
            )
        raw_candidates = (
            [value.get("candidate")] if kind == "absolute" else value.get("candidates")
        )
        if not isinstance(raw_candidates, list) or len(raw_candidates) != (
            1 if kind == "absolute" else 2
        ):
            raise ValueError(
                f"experiment control {control_id!r} requires "
                f"{'one candidate' if kind == 'absolute' else 'two candidates'}"
            )
        candidates = tuple(
            _resolve(root, item, field=f"control {control_id} candidate")
            for item in raw_candidates
        )
        if len(set(candidates)) != len(candidates):
            raise ValueError(
                f"experiment control {control_id!r} candidates must be distinct"
            )
        for candidate in candidates:
            if not candidate.is_file():
                raise FileNotFoundError(
                    f"experiment control candidate does not exist: {candidate}"
                )
        expect = value.get("expect", {})
        if not isinstance(expect, dict) or not expect:
            raise ValueError(
                f"experiment control {control_id!r} expect must be a non-empty object"
            )
        required = value.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(
                f"experiment control {control_id!r} required must be boolean"
            )
        controls.append(
            ControlSpec(control_id, str(kind), candidates, expect, required)
        )
    ids = [control.id for control in controls]
    if len(ids) != len(set(ids)):
        raise ValueError("experiment control ids must be unique")
    return tuple(controls)


def load_experiment(path: str | Path) -> ExperimentManifest:
    """Load a deterministic, non-mutating experiment sidecar."""

    manifest_path = Path(path).expanduser().resolve()
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") not in EXPERIMENT_SCHEMAS:
        raise ValueError(
            "experiment schema must be one of: " + ", ".join(sorted(EXPERIMENT_SCHEMAS))
        )
    schema = str(value["schema"])
    if schema == EXPERIMENT_SCHEMA_V1 and any(
        name in value for name in ("signals", "controls", "coverage")
    ):
        raise ValueError(
            f"experiment signals, controls, and coverage require {EXPERIMENT_SCHEMA_V2}"
        )
    family = value.get("family")
    if not isinstance(family, str) or not family.strip():
        raise ValueError("experiment family must be a non-empty string")
    baseline = _resolve(manifest_path.parent, value.get("baseline"), field="baseline")
    if not baseline.is_file():
        raise FileNotFoundError(f"experiment baseline does not exist: {baseline}")
    parameters = value.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("experiment parameters must be an object of value lists")
    parameter_space: dict[str, list[Any]] = {}
    for name, choices in parameters.items():
        if not isinstance(name, str) or not name:
            raise ValueError("experiment parameter names must be non-empty strings")
        if not isinstance(choices, list) or not choices:
            raise ValueError(f"experiment parameter {name!r} must be a non-empty list")
        parameter_space[name] = choices
    candidates_value = value.get("candidates", [])
    if not isinstance(candidates_value, list):
        raise ValueError("experiment candidates must be a list")
    candidates: dict[Path, dict[str, Any]] = {}
    seen_parameter_sets: set[str] = set()
    for index, candidate in enumerate(candidates_value):
        if not isinstance(candidate, dict):
            raise ValueError(f"experiment candidate {index} must be an object")
        source = _resolve(
            manifest_path.parent,
            candidate.get("source"),
            field=f"candidate {index} source",
        )
        if not source.is_file():
            raise FileNotFoundError(f"experiment candidate does not exist: {source}")
        assignment = candidate.get("parameters", {})
        if not isinstance(assignment, dict):
            raise ValueError(
                f"experiment candidate {index} parameters must be an object"
            )
        unknown = set(assignment) - set(parameter_space)
        if unknown:
            raise ValueError(
                f"experiment candidate {index} has unknown parameter(s): "
                + ", ".join(sorted(unknown))
            )
        if schema == EXPERIMENT_SCHEMA_V2 and set(assignment) != set(parameter_space):
            missing = set(parameter_space) - set(assignment)
            raise ValueError(
                f"experiment-v2 candidate {index} must assign every declared "
                "parameter; missing: " + ", ".join(sorted(missing))
            )
        for name, selected in assignment.items():
            if selected not in parameter_space[name]:
                raise ValueError(
                    f"experiment candidate {index} selects {name}={selected!r}, "
                    "which is outside the declared parameter space"
                )
        serialized = json.dumps(assignment, sort_keys=True, separators=(",", ":"))
        if serialized in seen_parameter_sets:
            raise ValueError(
                f"experiment parameter assignment is duplicated: {assignment}"
            )
        seen_parameter_sets.add(serialized)
        if source in candidates:
            raise ValueError(f"experiment candidate source is duplicated: {source}")
        candidates[source] = dict(assignment)
    invariants = value.get("invariants", {})
    if not isinstance(invariants, dict):
        raise ValueError("experiment invariants must be an object")
    region_value = value.get("selected_region", invariants.get("selected_region"))
    region = _parse_region(region_value)
    homologous_value = value.get("homologous_parameters", [])
    if not isinstance(homologous_value, list):
        raise ValueError("experiment homologous_parameters must be a list")
    homologous: list[tuple[str, ...]] = []
    claimed: set[str] = set()
    for index, group_value in enumerate(homologous_value):
        if (
            not isinstance(group_value, list)
            or len(group_value) < 2
            or not all(isinstance(name, str) and name for name in group_value)
        ):
            raise ValueError(
                f"experiment homologous_parameters group {index} must contain "
                "at least two parameter names"
            )
        group = tuple(group_value)
        if len(set(group)) != len(group):
            raise ValueError(
                f"experiment homologous_parameters group {index} contains duplicates"
            )
        unknown_homologs = set(group) - set(parameter_space)
        if unknown_homologs:
            raise ValueError(
                f"experiment homologous_parameters group {index} has unknown "
                "parameter(s): " + ", ".join(sorted(unknown_homologs))
            )
        overlap = claimed & set(group)
        if overlap:
            raise ValueError(
                "experiment homologous_parameters groups overlap at: "
                + ", ".join(sorted(overlap))
            )
        choices = [parameter_space[name] for name in group]
        if any(options != choices[0] for options in choices[1:]):
            raise ValueError(
                f"experiment homologous_parameters group {index} must share "
                "the same declared choices"
            )
        claimed.update(group)
        homologous.append(group)
    if homologous and baseline not in candidates:
        raise ValueError(
            "experiment baseline must appear in candidates with a parameter "
            "assignment when homologous_parameters are declared"
        )
    if homologous:
        baseline_assignment = candidates[baseline]
        missing_homologs = {name for group in homologous for name in group} - set(
            baseline_assignment
        )
        if missing_homologs:
            raise ValueError(
                "experiment baseline assignment is missing homologous "
                "parameter(s): " + ", ".join(sorted(missing_homologs))
            )
    signals = parse_signal_specs(value.get("signals"))
    controls = _parse_controls(manifest_path.parent, value.get("controls"))
    signal_ids = {signal.id for signal in signals}
    from .schema import METRICS_BY_KEY

    for control in controls:
        if control.kind == "absolute":
            allowed_expect = {
                "signals",
                "metrics",
                "object_sha256",
                "returncode",
                *METRICS_BY_KEY,
            }
            unknown_expect = set(control.expect) - allowed_expect
            if unknown_expect:
                raise ValueError(
                    f"experiment control {control.id!r} has unknown expectation(s): "
                    + ", ".join(sorted(unknown_expect))
                )
            if "returncode" in control.expect and not isinstance(
                control.expect["returncode"], int
            ):
                raise ValueError(
                    f"experiment control {control.id!r} returncode must be an integer"
                )
            object_hash = control.expect.get("object_sha256")
            if object_hash is not None and (
                not isinstance(object_hash, str)
                or len(object_hash) != 64
                or any(character not in "0123456789abcdef" for character in object_hash)
            ):
                raise ValueError(
                    f"experiment control {control.id!r} object_sha256 must be "
                    "64 lowercase hexadecimal characters"
                )
            signal_expect = control.expect.get("signals", {})
            metric_expect = control.expect.get("metrics", {})
            if not isinstance(signal_expect, dict) or not isinstance(
                metric_expect, dict
            ):
                raise ValueError(
                    f"experiment control {control.id!r} signals/metrics "
                    "expectations must be objects"
                )
            unknown_signals = set(signal_expect) - signal_ids
            if unknown_signals:
                raise ValueError(
                    f"experiment control {control.id!r} references unknown signal(s): "
                    + ", ".join(sorted(unknown_signals))
                )
            invalid_statuses = {str(status) for status in signal_expect.values()} - {
                "PASS",
                "FAIL",
                "UNKNOWN",
            }
            if invalid_statuses:
                raise ValueError(
                    f"experiment control {control.id!r} signal statuses must "
                    "be PASS, FAIL, or UNKNOWN"
                )
            unknown_metrics = set(metric_expect) - set(METRICS_BY_KEY)
            if unknown_metrics:
                raise ValueError(
                    f"experiment control {control.id!r} references unknown metric(s): "
                    + ", ".join(sorted(unknown_metrics))
                )
        else:
            if set(control.expect) != {"different"}:
                raise ValueError(
                    f"experiment differential control {control.id!r} expect "
                    "must contain only different"
                )
            paths = control.expect["different"]
            if (
                not isinstance(paths, list)
                or not paths
                or not all(isinstance(item, str) for item in paths)
            ):
                raise ValueError(
                    f"experiment differential control {control.id!r} different "
                    "must be a non-empty string list"
                )
            for path_value in paths:
                prefix, separator, key = path_value.partition(".")
                valid = path_value == "object_sha256" or (
                    separator
                    and (
                        (prefix == "metrics" and key in METRICS_BY_KEY)
                        or (prefix == "signals" and key in signal_ids)
                    )
                )
                if not valid:
                    raise ValueError(
                        f"experiment differential control {control.id!r} has "
                        f"invalid evidence path {path_value!r}"
                    )
    coverage_value = value.get("coverage", {})
    if not isinstance(coverage_value, dict):
        raise ValueError("experiment coverage must be an object")
    unknown_coverage = set(coverage_value) - {
        "method",
        "excluded",
        "exclusion_reason",
        "sampling",
    }
    if unknown_coverage:
        raise ValueError(
            "experiment coverage has unknown field(s): "
            + ", ".join(sorted(unknown_coverage))
        )
    excluded = coverage_value.get("excluded", 0)
    if not isinstance(excluded, int) or excluded < 0:
        raise ValueError("experiment coverage excluded must be a non-negative integer")
    declared = (
        math.prod(len(choices) for choices in parameter_space.values())
        if parameter_space
        else 1
    )
    if excluded > declared:
        raise ValueError(
            "experiment coverage excluded cannot exceed the declared parameter space"
        )
    if excluded + len(candidates) > declared:
        raise ValueError(
            "experiment coverage exclusions and candidate assignments overlap "
            "or exceed the declared parameter space"
        )
    method = coverage_value.get("method", "explicit-candidates")
    if not isinstance(method, str) or not method.strip():
        raise ValueError("experiment coverage method must be a non-empty string")
    exclusion_reason = coverage_value.get("exclusion_reason")
    if exclusion_reason is not None and (
        not isinstance(exclusion_reason, str) or not exclusion_reason.strip()
    ):
        raise ValueError(
            "experiment coverage exclusion_reason must be a non-empty string"
        )
    if excluded and exclusion_reason is None:
        raise ValueError(
            "experiment coverage exclusion_reason is required when assignments "
            "are excluded"
        )
    sampling = coverage_value.get("sampling")
    if sampling is not None and not isinstance(sampling, (str, dict)):
        raise ValueError("experiment coverage sampling must be a string or object")
    coverage = {
        "method": method.strip(),
        "excluded": excluded,
        "exclusion_reason": exclusion_reason,
        "sampling": sampling,
    }
    return ExperimentManifest(
        path=manifest_path,
        schema=schema,
        family=family,
        baseline=baseline,
        parameter_space=parameter_space,
        candidates=candidates,
        homologous_parameters=tuple(homologous),
        region=region,
        signals=signals,
        controls=controls,
        coverage=coverage,
        raw=value,
    )


def expected_parameter_combinations(manifest: ExperimentManifest) -> int:
    """Return the declared Cartesian parameter-space size."""

    return (
        math.prod(len(choices) for choices in manifest.parameter_space.values())
        if manifest.parameter_space
        else 1
    )


def validate_campaign_sources(
    manifest: ExperimentManifest,
    sources: list[str | Path],
) -> None:
    """Refuse a sidecar that cannot account for supplied candidate sources."""

    resolved = {Path(source).expanduser().resolve() for source in sources}
    accounted = set(manifest.candidates) | {manifest.baseline}
    missing = resolved - accounted
    if missing:
        raise ValueError(
            "experiment manifest does not describe supplied source(s): "
            + ", ".join(str(item) for item in sorted(missing))
        )
