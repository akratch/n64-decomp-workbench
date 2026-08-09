"""Bounded, text-exact composition of independently observed source mechanisms."""

from __future__ import annotations

import collections
import difflib
import hashlib
import itertools
import json
import math
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coverage import SweepCoverage

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
    step: int = 1,
    write: bool = True,
) -> dict[str, Any]:
    """Generate a bounded interaction set and a campaign-compatible manifest.

    ``step`` samples the combination space, visiting every ``step``-th
    combination. It exists so a space larger than the cap can be *sampled*
    rather than abandoned -- and, because the record it produces carries the
    stride and the covered fraction, so nobody can later read a sampled
    negative result as a proof about the whole space. One campaign closed a
    family on a one-in-eight sweep whose record said nothing about the other
    seven eighths.
    """

    order = spec.max_order if max_order is None else max_order
    cap = spec.max_candidates if max_candidates is None else max_candidates
    if not 1 <= order <= len(spec.transformations):
        raise ValueError("--max-order must be between 1 and transform count")
    if step < 1:
        raise ValueError(f"--step must be at least 1, got {step}")
    planned = sum(
        math.comb(len(spec.transformations), size) for size in range(1, order + 1)
    )
    sampled = len(range(0, planned, step))
    if sampled > cap:
        raise ValueError(
            f"composition plans {planned} combinations"
            + (f" ({sampled} at step {step})" if step > 1 else "")
            + f", above cap {cap}; lower --max-order, raise --step to sample "
            "the space, or raise --max-candidates explicitly"
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
    combinations: Iterator[tuple[Transformation, ...]] = itertools.chain.from_iterable(
        itertools.combinations(spec.transformations, size)
        for size in range(1, order + 1)
    )
    if step > 1:
        combinations = itertools.islice(combinations, 0, None, step)
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
    coverage = SweepCoverage(
        basis=(
            f"subsets of {len(spec.transformations)} transformation(s) up to "
            f"order {order}"
        ),
        space=planned,
        covered=len(candidates) + len(rejected),
        step=step,
        excluded=excluded,
    )
    return {
        "coverage": coverage.as_dict(),
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


# ---------------------------------------------------------------------------
# Mutation review: the gate between "scores well" and "is the same program".
#
# An automated source-mutation sweep proposes edits by shape, not by meaning.
# A recorded sweep grouped one local's occurrences by line proximity and
# renamed a whole group; a group holding only *reads* -- the definitions were
# 130 lines earlier -- became a read of an uninitialized variable. It compiled,
# it scored better than its baseline, and it was not the same program. The
# winner was adopted before anyone diffed it.
#
# What follows is a text analysis, and its limits are part of its output: it
# does not parse or execute C, so it can never certify a variant. It surfaces
# the diff a reviewer owes the winner, and it names the two shapes that
# produced the recorded failure. Everything else is the reviewer's job, and the
# report says so.
# ---------------------------------------------------------------------------

MUTATION_REVIEW_SCHEMA = "decomp-workbench-mutation-review-v1"

#: C identifiers that are not struct or union member selections: `sp4A0`
#: matches, the `count` of `header->count` does not. A member name is owned by
#: a type, so it can never be the local whose definition went missing.
_IDENTIFIER_RE = re.compile(r"(?<![\w.])(?<!->)[A-Za-z_]\w*")

#: Words that are never a local whose definition could go missing.
_REVIEW_KEYWORDS = frozenset(
    """
    auto break case char const continue default do double else enum extern
    float for goto if inline int long register restrict return short signed
    sizeof static struct switch typedef union unsigned void volatile while
    NULL
    """.split()
)

#: `name =` but not `name ==`, and the compound assignments. A write to the
#: identifier, as far as text can tell.
_ASSIGN_TEMPLATE = r"(?<![\w.>])%s\s*(?:\[[^\];]*\])?\s*(?:=(?!=)|[-+*/%%&|^]=|<<=|>>=)"

#: `&name`, `name++`, `--name`: not a plain read, so not evidence of a missing
#: definition. Treated as "may define" rather than "defines".
_MAY_DEFINE_TEMPLATE = r"(?:&\s*%s\b|\+\+\s*%s\b|%s\s*\+\+|--\s*%s\b|%s\s*--)"

#: A declaration of the identifier: a type, then the name, then `;` or `=` or
#: `,`. Used only to find where a local is introduced, never to type it.
_DECLARE_TEMPLATE = (
    r"^\s*(?:[A-Za-z_]\w*\s*[\w*\s]*?)\b%s\s*(?:\[[^\]]*\])?\s*(?:[;,=](?!=))"
)


def _identifiers(line: str) -> collections.Counter[str]:
    return collections.Counter(
        name
        for name in _IDENTIFIER_RE.findall(line)
        if name not in _REVIEW_KEYWORDS and not name.isdigit()
    )


def _defines(line: str, name: str) -> bool:
    """Whether `line` writes `name`, as far as the text can say."""

    quoted = re.escape(name)
    if re.search(_ASSIGN_TEMPLATE % quoted, line):
        return True
    if re.search(_MAY_DEFINE_TEMPLATE % ((quoted,) * 5), line):
        return True
    return bool(re.search(_DECLARE_TEMPLATE % quoted, line))


def _declares_without_initializer(line: str, name: str) -> bool:
    quoted = re.escape(name)
    if not re.search(_DECLARE_TEMPLATE % quoted, line):
        return False
    return not re.search(_ASSIGN_TEMPLATE % quoted, line)


def _declaration_line(lines: list[str], name: str) -> int | None:
    """Where `name` is declared, or `None` if this file never declares it.

    Everything below is restricted to identifiers this file declares. A call to
    an external function and a read of a project global are both identifiers
    with no visible write, and neither is the failure being looked for; asking
    for a declaration first is what keeps the report about locals.
    """

    quoted = re.escape(name)
    pattern = re.compile(_DECLARE_TEMPLATE % quoted)
    for number, line in enumerate(lines, 1):
        if pattern.search(line):
            return number
    return None


def _definition_lines(lines: list[str], name: str) -> list[int]:
    return [
        number
        for number, line in enumerate(lines, 1)
        if not _declares_without_initializer(line, name) and _defines(line, name)
    ]


def _first_definition(lines: list[str], name: str) -> int | None:
    written = _definition_lines(lines, name)
    return written[0] if written else None


def _first_use(lines: list[str], name: str) -> int | None:
    """The first line that uses `name` as a value.

    A bare declaration is skipped: `f32 var_f12_5;` mentions the identifier
    without reading it, and counting it as the first use makes every local
    whose declaration precedes its first store look like a read of an
    uninitialized variable -- which is the exact finding this module exists to
    report, so a false one would make the whole report worthless.
    """

    for number, line in enumerate(lines, 1):
        if name not in _identifiers(line):
            continue
        if _declares_without_initializer(line, name):
            continue
        return number
    return None


def _review_finding(
    code: str,
    severity: str,
    identifier: str,
    line: int | None,
    message: str,
    action: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "identifier": identifier,
        "line": line,
        "message": message,
        "action": action,
        "claim": "textual-candidate-only",
    }


def _changed_lines(
    base_lines: list[str], variant_lines: list[str]
) -> tuple[list[str], list[str]]:
    """Return the removed and added lines of the two files' line diff."""

    matcher = difflib.SequenceMatcher(None, base_lines, variant_lines, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed.extend(base_lines[i1:i2])
        added.extend(variant_lines[j1:j2])
    return removed, added


def review_mutation(
    baseline: str | Path,
    variant: str | Path,
    *,
    context: int = 3,
) -> dict[str, Any]:
    """Surface a mutation's diff and the two shapes that invalidate one.

    The report is the diff plus findings. It never says a variant is valid --
    no text analysis can -- and it says so in `proof`.
    """

    if context < 0:
        raise ValueError("context must not be negative")
    baseline_path = Path(baseline).expanduser().resolve()
    variant_path = Path(variant).expanduser().resolve()
    baseline_text = _read_source(baseline_path)
    variant_text = _read_source(variant_path)
    base_lines = baseline_text.splitlines()
    variant_lines = variant_text.splitlines()

    diff = list(
        difflib.unified_diff(
            base_lines,
            variant_lines,
            fromfile=str(baseline_path),
            tofile=str(variant_path),
            lineterm="",
            n=context,
        )
    )
    removed, added = _changed_lines(base_lines, variant_lines)
    before = collections.Counter[str]()
    after = collections.Counter[str]()
    for line in removed:
        before.update(_identifiers(line))
    for line in added:
        after.update(_identifiers(line))

    findings: list[dict[str, Any]] = []

    # The one check, stated as a regression rather than as a property.
    #
    # An identifier whose first *use* precedes its first *write* is the shape
    # both recorded failures take: a renamed group holding only reads becomes a
    # read of an uninitialized local, and a deleted store leaves the surviving
    # reads with nothing reaching them. Reporting the property outright would
    # flood the output, because plenty of correct code reads a local textually
    # above the branch that writes it. What is reportable is that the mutation
    # *introduced* the shape: the baseline is checked the same way, and a pair
    # that was already like this is the reviewer's existing code, not this
    # mutation's doing.
    for name in sorted(set(before) | set(after)):
        if _declaration_line(variant_lines, name) is None:
            continue
        variant_use = _first_use(variant_lines, name)
        if variant_use is None:
            continue
        variant_definition = _first_definition(variant_lines, name)
        if variant_definition is not None and variant_definition <= variant_use:
            continue
        base_use = _first_use(base_lines, name)
        base_definition = _first_definition(base_lines, name)
        if base_use is not None and (
            base_definition is None or base_definition > base_use
        ):
            continue
        introduced = after.get(name, 0) > before.get(name, 0)
        where = (
            f" (the first write is line {variant_definition})"
            if variant_definition is not None
            else ", and the variant never writes to it"
        )
        was = (
            "the baseline wrote it before using it"
            if base_use is not None
            else "the baseline never used it"
        )
        findings.append(
            _review_finding(
                "read-before-definition" if introduced else "definition-removed",
                "error",
                name,
                variant_use,
                (
                    "the mutation "
                    + ("introduces" if introduced else "leaves")
                    + f" a use of {name!r} at line {variant_use} that no "
                    f"earlier line writes to{where}; {was}"
                ),
                (
                    "start the renamed group at a definition, restore the "
                    "removed write, or drop the variant: a read that reaches "
                    "no definition compiles and scores without being the same "
                    "program"
                ),
            )
        )

    # A write that left, where text cannot say whether it was live.
    #
    # The recorded sweep's top-scoring winner renamed a local's *first* store
    # and left a later conditional store and two reads in place. Textually the
    # remaining store still precedes the reads, so the check above is silent
    # and correct to be silent: whether a path reaches those reads without
    # passing the surviving store is a control-flow question, and this module
    # does not build a control-flow graph. What it can say is that the mutation
    # deleted a write to a value that is still read, which is the fact the
    # reviewer of that winner needed and did not have.
    reported = {str(item["identifier"]) for item in findings}
    for name in sorted(set(before) | set(after)):
        if name in reported or _declaration_line(variant_lines, name) is None:
            continue
        if _first_use(variant_lines, name) is None:
            continue
        base_writes = _definition_lines(base_lines, name)
        variant_writes = _definition_lines(variant_lines, name)
        if len(variant_writes) >= len(base_writes):
            continue
        findings.append(
            _review_finding(
                "write-removed",
                "warning",
                name,
                variant_writes[0] if variant_writes else None,
                (
                    f"the mutation removes {len(base_writes) - len(variant_writes)} "
                    f"of {len(base_writes)} write(s) to {name!r}, which is still "
                    "read; whether a path now reaches a read without passing a "
                    "write is a control-flow question this check cannot answer"
                ),
                (
                    "confirm by hand that every surviving read is dominated by "
                    "a surviving write before adopting"
                ),
            )
        )

    # A mutation that touches more than the identifiers it claims. Not an
    # error; a reason to read the diff rather than the summary.
    if len(added) > len(removed):
        findings.append(
            _review_finding(
                "statement-count-changed",
                "warning",
                "",
                None,
                (
                    f"the mutation adds {len(added) - len(removed)} more "
                    "line(s) than it removes, so it is not a pure substitution"
                ),
                "justify the added statements line by line before adopting",
            )
        )
    elif len(removed) > len(added):
        findings.append(
            _review_finding(
                "statement-count-changed",
                "warning",
                "",
                None,
                (
                    f"the mutation removes {len(removed) - len(added)} more "
                    "line(s) than it adds, so it is not a pure substitution"
                ),
                "justify the removed statements line by line before adopting",
            )
        )

    errors = sum(1 for item in findings if item["severity"] == "error")
    warnings = len(findings) - errors
    return {
        "schema": MUTATION_REVIEW_SCHEMA,
        "baseline": str(baseline_path),
        "variant": str(variant_path),
        "baseline_sha256": hashlib.sha256(baseline_text.encode()).hexdigest(),
        "variant_sha256": hashlib.sha256(variant_text.encode()).hexdigest(),
        "changed_lines_removed": len(removed),
        "changed_lines_added": len(added),
        "identifiers_introduced": sorted(
            name for name in after if after[name] > before.get(name, 0)
        ),
        "identifiers_withdrawn": sorted(
            name for name in before if before[name] > after.get(name, 0)
        ),
        "errors": errors,
        "warnings": warnings,
        "finding_count": len(findings),
        "findings": findings,
        "diff": diff,
        "reviewed": not findings,
        "proof": (
            "Textual review only. This does not parse, type, or execute C, so "
            "it cannot certify that a variant is the same program: a clean "
            "report means the two named shapes were not found, not that the "
            "mutation is valid."
        ),
        "next_gate": (
            "Read the printed diff and justify every changed line before "
            "adopting the variant, then re-run the exact binary, frame, and "
            "translation-unit collateral gates on it."
        ),
    }
