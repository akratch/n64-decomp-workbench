"""Project-neutral experiment manifests and selected-region constraints."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPERIMENT_SCHEMA = "decomp-workbench-experiment-v1"


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
    family: str
    baseline: Path
    parameter_space: dict[str, list[Any]]
    candidates: dict[Path, dict[str, Any]]
    region: RegionConstraint | None
    raw: dict[str, Any]

    def metadata_for(self, source: str | Path) -> dict[str, Any]:
        resolved = Path(source).expanduser().resolve()
        return {
            "schema": EXPERIMENT_SCHEMA,
            "family": self.family,
            "parameters": self.candidates.get(resolved, {}),
            "parameter_space": self.parameter_space,
            "baseline": str(self.baseline),
            "manifest": str(self.path),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPERIMENT_SCHEMA,
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
            "selected_region": self.region.as_dict() if self.region else None,
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


def load_experiment(path: str | Path) -> ExperimentManifest:
    """Load a deterministic, non-mutating experiment sidecar."""

    manifest_path = Path(path).expanduser().resolve()
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != EXPERIMENT_SCHEMA:
        raise ValueError(f"experiment schema must be {EXPERIMENT_SCHEMA}")
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
    return ExperimentManifest(
        path=manifest_path,
        family=family,
        baseline=baseline,
        parameter_space=parameter_space,
        candidates=candidates,
        region=region,
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
