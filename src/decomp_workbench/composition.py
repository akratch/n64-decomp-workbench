"""Bounded, text-exact composition of independently observed source mechanisms."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMPOSITION_SCHEMA = "decomp-workbench-composition-v1"
SOURCE_INSPECTION_SCHEMA = "decomp-workbench-source-inspection-v1"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STATIC_LOCAL_RE = re.compile(r"^\s+static\s+[^;]+;\s*$")
EMPTY_CONTROL_RE = re.compile(r"\b(if|for|while)\s*\([^;{}]*\)\s*\{\s*\}\s*;?\s*$")
ZERO_ARITHMETIC_RE = re.compile(
    r"(?:\b[A-Za-z_]\w*\s*[*&]\s*0\b|\b0\s*[*&]\s*[A-Za-z_]\w*\b)"
)
SELF_CANCEL_RE = re.compile(r"\b(?P<left>[A-Za-z_]\w*)\s*(?:-|\^)\s*(?P=left)\b")


@dataclass(frozen=True)
class TextEdit:
    find: str
    replace: str
    occurrences: int


@dataclass(frozen=True)
class Transformation:
    identifier: str
    family: str
    description: str
    edits: tuple[TextEdit, ...]
    conflicts: frozenset[str]
    requires: frozenset[str]


@dataclass(frozen=True)
class CompositionSpec:
    path: Path
    baseline: Path
    transformations: tuple[Transformation, ...]
    max_order: int
    max_candidates: int


def _read_source(path: Path) -> str:
    """Read UTF-8 source without normalizing line endings."""

    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def _write_source(path: Path, source: str) -> None:
    """Write generated source without platform newline translation."""

    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(source)


def _resolve(root: Path, value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"composition {field} must be a non-empty path")
    path = Path(value).expanduser()
    return (root / path if not path.is_absolute() else path).resolve()


def load_composition(path: str | Path) -> CompositionSpec:
    manifest_path = Path(path).expanduser().resolve()
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != COMPOSITION_SCHEMA:
        raise ValueError(f"composition schema must be {COMPOSITION_SCHEMA}")
    baseline = _resolve(manifest_path.parent, value.get("baseline"), field="baseline")
    if not baseline.is_file():
        raise FileNotFoundError(f"composition baseline does not exist: {baseline}")
    raw_transformations = value.get("transformations")
    if not isinstance(raw_transformations, list) or not raw_transformations:
        raise ValueError("composition transformations must be a non-empty list")
    transformations = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_transformations):
        if not isinstance(raw, dict):
            raise ValueError(f"composition transformation {index} must be an object")
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError(
                f"composition transformation {index} id must be filename-safe"
            )
        if identifier in identifiers:
            raise ValueError(
                f"composition transformation id is duplicated: {identifier}"
            )
        identifiers.add(identifier)
        family = raw.get("family")
        if not isinstance(family, str) or not family.strip():
            raise ValueError(f"composition transformation {identifier} needs a family")
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise ValueError(
                f"composition transformation {identifier} description must be text"
            )
        raw_edits = raw.get("edits")
        if not isinstance(raw_edits, list) or not raw_edits:
            raise ValueError(
                f"composition transformation {identifier} needs at least one edit"
            )
        edits = []
        for edit_index, raw_edit in enumerate(raw_edits):
            if not isinstance(raw_edit, dict):
                raise ValueError(
                    f"composition transformation {identifier} edit {edit_index} "
                    "must be an object"
                )
            find = raw_edit.get("find")
            replace = raw_edit.get("replace", "")
            occurrences = raw_edit.get("occurrences", 1)
            if not isinstance(find, str) or not find:
                raise ValueError(
                    f"composition transformation {identifier} edit {edit_index} "
                    "find must be non-empty text"
                )
            if not isinstance(replace, str):
                raise ValueError(
                    f"composition transformation {identifier} edit {edit_index} "
                    "replace must be text"
                )
            if not isinstance(occurrences, int) or occurrences < 1:
                raise ValueError(
                    f"composition transformation {identifier} edit {edit_index} "
                    "occurrences must be a positive integer"
                )
            edits.append(TextEdit(find, replace, occurrences))
        conflicts = raw.get("conflicts", [])
        requires = raw.get("requires", [])
        if not isinstance(conflicts, list) or not all(
            isinstance(item, str) for item in conflicts
        ):
            raise ValueError(
                f"composition transformation {identifier} conflicts must be ids"
            )
        if not isinstance(requires, list) or not all(
            isinstance(item, str) for item in requires
        ):
            raise ValueError(
                f"composition transformation {identifier} requires must be ids"
            )
        transformations.append(
            Transformation(
                identifier=identifier,
                family=family,
                description=description,
                edits=tuple(edits),
                conflicts=frozenset(conflicts),
                requires=frozenset(requires),
            )
        )
    known = {item.identifier for item in transformations}
    for item in transformations:
        unknown = (item.conflicts | item.requires) - known
        if unknown:
            raise ValueError(
                f"composition transformation {item.identifier} references unknown "
                f"id(s): {', '.join(sorted(unknown))}"
            )
    max_order = value.get("max_order", 2)
    max_candidates = value.get("max_candidates", 256)
    if not isinstance(max_order, int) or not 1 <= max_order <= len(transformations):
        raise ValueError("composition max_order must be between 1 and transform count")
    if not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("composition max_candidates must be a positive integer")
    return CompositionSpec(
        path=manifest_path,
        baseline=baseline,
        transformations=tuple(transformations),
        max_order=max_order,
        max_candidates=max_candidates,
    )


def _valid_combination(items: tuple[Transformation, ...]) -> bool:
    selected = {item.identifier for item in items}
    return all(
        not (item.conflicts & selected) and item.requires <= selected for item in items
    )


def _apply(text: str, items: tuple[Transformation, ...]) -> str:
    result = text
    for transformation in items:
        for edit in transformation.edits:
            observed = result.count(edit.find)
            if observed != edit.occurrences:
                raise ValueError(
                    f"{transformation.identifier}: expected {edit.occurrences} "
                    f"occurrence(s), found {observed}: {edit.find!r}"
                )
            result = result.replace(edit.find, edit.replace, edit.occurrences)
    return result


def compose_sources(
    spec: CompositionSpec,
    output: str | Path,
    *,
    max_order: int | None = None,
    max_candidates: int | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Generate a bounded interaction set and a campaign-compatible manifest."""

    order = spec.max_order if max_order is None else max_order
    cap = spec.max_candidates if max_candidates is None else max_candidates
    if not 1 <= order <= len(spec.transformations):
        raise ValueError("--max-order must be between 1 and transform count")
    planned = sum(
        math.comb(len(spec.transformations), size) for size in range(1, order + 1)
    )
    if planned > cap:
        raise ValueError(
            f"composition plans {planned} combinations, above cap {cap}; "
            "lower --max-order or raise --max-candidates explicitly"
        )
    output_path = Path(output).expanduser().resolve()
    if write and output_path.exists():
        if not output_path.is_dir() or any(output_path.iterdir()):
            raise FileExistsError(f"composition output is not empty: {output_path}")
    baseline_text = _read_source(spec.baseline)
    baseline_lines = len(baseline_text.splitlines())
    baseline_bytes = len(baseline_text.encode())
    suffix = spec.baseline.suffix or ".c"
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    excluded = 0
    combinations = itertools.chain.from_iterable(
        itertools.combinations(spec.transformations, size)
        for size in range(1, order + 1)
    )
    for items in combinations:
        if not _valid_combination(items):
            excluded += 1
            continue
        identifiers = [item.identifier for item in items]
        try:
            source = _apply(baseline_text, items)
        except ValueError as error:
            rejected.append({"transformations": identifiers, "error": str(error)})
            continue
        candidates.append(
            {
                "transformations": identifiers,
                "families": sorted({item.family for item in items}),
                "source_text": source,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "source_bytes": len(source.encode()),
                "byte_delta": len(source.encode()) - baseline_bytes,
                "line_delta": len(source.splitlines()) - baseline_lines,
            }
        )
    if not candidates:
        detail = (
            f"; {len(rejected)} combination(s) failed exact edits" if rejected else ""
        )
        raise ValueError(
            "composition produced no valid candidates; review max_order, "
            f"requires, and conflicts{detail}"
        )
    if write:
        output_path.mkdir(parents=True, exist_ok=True)
        baseline_name = f"baseline{suffix}"
        shutil.copyfile(spec.baseline, output_path / baseline_name)
        experiment_candidates = []
        for index, item in enumerate(candidates, 1):
            tag = "+".join(item["transformations"])
            name = f"{index:03d}-{tag}{suffix}"
            _write_source(output_path / name, item["source_text"])
            item["source"] = name
            experiment_candidates.append(
                {
                    "source": name,
                    "parameters": {
                        transformation.identifier: (
                            transformation.identifier in item["transformations"]
                        )
                        for transformation in spec.transformations
                    },
                }
            )
        experiment = {
            "schema": "decomp-workbench-experiment-v1",
            "family": "bounded-mechanism-composition",
            "baseline": baseline_name,
            "parameters": {
                transformation.identifier: [False, True]
                for transformation in spec.transformations
            },
            "candidates": experiment_candidates,
            "composition_source": str(spec.path),
        }
        (output_path / "experiment.json").write_text(
            json.dumps(experiment, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    cross_family = sum(len(item["families"]) > 1 for item in candidates)
    return {
        "schema": COMPOSITION_SCHEMA,
        "spec": str(spec.path),
        "baseline": str(spec.baseline),
        "baseline_sha256": hashlib.sha256(baseline_text.encode()).hexdigest(),
        "baseline_bytes": baseline_bytes,
        "output": str(output_path) if write else None,
        "planned_output": str(output_path),
        "write": write,
        "max_order": order,
        "candidate_cap": cap,
        "planned_combinations": planned,
        "excluded_by_constraints": excluded,
        "rejected_combinations": rejected,
        "generated_candidates": len(candidates),
        "cross_family_candidates": cross_family,
        "candidates": [
            {key: value for key, value in item.items() if key != "source_text"}
            for item in candidates
        ],
        "proof": (
            "Exact literal edits were composed in declared order. No source "
            "semantics, compiler effect, function exactness, or plausibility "
            "is inferred until the generated candidates are compiled."
        ),
        "next_steps": [
            (
                f"decomp-workbench experiment validate "
                f"{output_path / 'experiment.json'}"
                if write
                else "Re-run without --dry-run to write the candidate set."
            ),
            (
                "Run decomp-workbench campaign with the stock compiler and "
                "--no-stop-on-exact."
            ),
            "Keep only candidates that pass raw-word, relocation-target, frame, "
            "and translation-unit collateral gates.",
        ],
    }


def inspect_source(path: str | Path) -> dict[str, Any]:
    """Inventory suspicious fake-match constructs without claiming deadness."""

    source_path = Path(path).expanduser().resolve()
    text = _read_source(source_path)
    findings = []
    seen_lines: dict[str, list[int]] = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        kinds = []
        if STATIC_LOCAL_RE.match(line):
            kinds.append("function-scope-static-candidate")
        if EMPTY_CONTROL_RE.search(line):
            kinds.append("empty-control")
            seen_lines.setdefault(stripped.rstrip(";"), []).append(number)
        if ZERO_ARITHMETIC_RE.search(line):
            kinds.append("zero-arithmetic")
        if SELF_CANCEL_RE.search(line):
            kinds.append("self-cancelling-arithmetic")
        for kind in kinds:
            findings.append(
                {
                    "line": number,
                    "kind": kind,
                    "source": stripped,
                    "claim": "syntactic-candidate-only",
                }
            )
    duplicates = [
        {"source": source, "lines": lines, "count": len(lines)}
        for source, lines in sorted(seen_lines.items())
        if len(lines) > 1
    ]
    return {
        "schema": SOURCE_INSPECTION_SCHEMA,
        "source": str(source_path),
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "finding_count": len(findings),
        "findings": findings,
        "duplicate_empty_controls": duplicates,
        "proof": (
            "Conservative syntax inventory only. A finding may be intentional, "
            "load-bearing, or historically correct; removal is never implied."
        ),
        "next_gate": (
            "Group declarations with their uses, encode deletion/substitution "
            "mechanisms in a composition manifest, then compile every candidate "
            "against exact binary and collateral gates."
        ),
    }
