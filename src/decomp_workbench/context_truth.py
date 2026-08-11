"""Project, scratch, and site truth kept as independent evidence layers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .comparison_render import scratch_score_acceptance
from .model import Comparison
from .scratch_check import ScratchPackage
from .view import MechanismView

CALL_TARGET_RE = re.compile(r"<(?P<name>[A-Za-z_][A-Za-z0-9_]*)[^>]*>")
DECLARATION_RE = re.compile(
    r"(?m)^\s*(?:extern\s+)?(?P<type>void|int|signed\s+int|unsigned\s+int)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*;"
)


def _acceptance(comparison: Comparison | None) -> tuple[str, int | None]:
    if comparison is None:
        return "UNKNOWN", None
    accepted, _ = scratch_score_acceptance(comparison)
    return ("PASS" if accepted else "FAIL"), comparison.raw_word_mismatches


def _declarations(text: str) -> dict[str, str]:
    return {
        match.group("name"): " ".join(match.group("type").split()).casefold()
        for match in DECLARATION_RE.finditer(text)
    }


def _scratch_source(package: ScratchPackage) -> str:
    return "\n".join(
        package.text(name) for name in ("ctx.c", "code.c") if name in package.files
    )


def _c89_capable(frontend: dict[str, str | None]) -> bool:
    language = (frontend.get("language") or "").casefold()
    family = (frontend.get("frontend") or "").casefold()
    return (
        "++" not in language
        and "++" not in family
        and language
        in {
            "c",
            "c89",
            "c90",
            "gnu89",
        }
    )


def call_contract_hypotheses(
    *,
    package: ScratchPackage,
    scratch: Comparison | None,
    view: MechanismView | None,
    project: Comparison | None,
    project_source: str | Path | None,
    frontend: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Return a tightly gated unused-return occupancy probe.

    The detector deliberately recognizes one measured shape, not the general
    fact that a mismatch follows a call.  It requires a coherent v0/v1 pool
    substitution late in an otherwise shape-stable function, an explicit void
    declaration in the scratch, and a C frontend where an implicit-int probe
    is meaningful.  Its output says ``test`` because object shape is not proof
    of historical source spelling.
    """

    if (
        scratch is None
        or view is None
        or scratch.exact
        or not _c89_capable(frontend)
        or view.verdict != "register-permutation"
        or scratch.aligned_register == 0
        or any(
            (
                scratch.aligned_structural,
                scratch.aligned_schedule,
                scratch.aligned_constant,
                scratch.aligned_commutative,
            )
        )
        or len(view.webs) != 1
    ):
        return []
    web = view.webs[0]
    if {web.target.removeprefix("$"), web.candidate.removeprefix("$")} != {
        "v0",
        "v1",
    }:
        return []
    first_row = min(web.rows, default=-1)
    if first_row < 0 or first_row < max(1, view.aligned_rows * 2 // 3):
        return []

    preceding_call: tuple[int, str] | None = None
    for row in view.rows:
        if row.index >= first_row:
            break
        assembly = row.candidate or row.target or ""
        opcode = assembly.split(maxsplit=1)[0].casefold() if assembly else ""
        match = CALL_TARGET_RE.search(assembly)
        if opcode in {"jal", "bal"} and match is not None:
            preceding_call = (row.index, match.group("name"))
    if preceding_call is None or first_row - preceding_call[0] > 24:
        return []

    call_row, callee = preceding_call
    scratch_declarations = _declarations(_scratch_source(package))
    if scratch_declarations.get(callee) != "void":
        return []

    project_status, _ = _acceptance(project)
    project_category: str | None = None
    if project_source is not None:
        source_path = Path(project_source).expanduser().resolve()
        source_declarations = _declarations(source_path.read_text(encoding="utf-8"))
        project_category = source_declarations.get(callee, "not-visible")

    evidence = [
        "scratch residual is register-only and opcode/temp-shape stable",
        f"one coherent {web.target}->{web.candidate} pool web spans {web.count} row(s)",
        f"the web begins after direct call {callee} at aligned row {call_row}",
        f"scratch context declares {callee} with return category void",
    ]
    if project_status == "PASS":
        evidence.append("the supplied project object is target-exact")
    if project_category is not None:
        evidence.append(f"project source declaration category is {project_category}")

    return [
        {
            "kind": "unused-call-return-occupancy",
            "status": "HYPOTHESIS",
            "confidence": (
                "measured-shape-and-context"
                if project_status == "PASS" and project_category is not None
                else "measured-shape"
            ),
            "callee": callee,
            "scratch_return_category": "void",
            "project_return_category": project_category,
            "register_web": web.as_dict(),
            "evidence": evidence,
            "action": (
                f"Test one scratch-only `int {callee}();` declaration variant; "
                "do not edit the project or infer the historical prototype "
                "unless the object result confirms it."
            ),
        }
    ]


def build_truth_stack(
    *,
    external_score: dict[str, Any] | None,
    scratch: Comparison | None,
    project: Comparison | None,
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the concise three-layer truth report used by terminal and JSON."""

    scratch_status, scratch_words = _acceptance(scratch)
    project_status, project_words = _acceptance(project)
    context_only = project_status == "PASS" and scratch_status == "FAIL"
    classification = (
        "context-only"
        if context_only
        else "both-exact"
        if project_status == scratch_status == "PASS"
        else "source-or-project-mismatch"
        if project_status == "FAIL"
        else "scratch-mismatch"
        if scratch_status == "FAIL"
        else "unmeasured"
    )
    return {
        "classification": classification,
        "layers": [
            {
                "id": "site-metadata",
                "status": "CONTEXT" if external_score is not None else "NOT RUN",
                "score": external_score,
            },
            {
                "id": "scratch-object",
                "status": scratch_status,
                "raw_words": scratch_words,
            },
            {
                "id": "project-object",
                "status": project_status if project is not None else "NOT RUN",
                "raw_words": project_words,
            },
        ],
        "context_differential": (
            {
                "status": "MEASURED",
                "classification": "context-only",
                "raw_words": scratch_words,
                "aligned_register": scratch.aligned_register if scratch else None,
                "aligned_structural": scratch.aligned_structural if scratch else None,
            }
            if context_only
            else {
                "status": "UNKNOWN"
                if project is None or scratch is None
                else "MEASURED",
                "classification": classification,
            }
        ),
        "context_hypotheses": hypotheses,
        "next_action": hypotheses[0]["action"] if hypotheses else None,
    }


def truth_stack_lines(report: dict[str, Any]) -> list[str]:
    """Render the compact truth stack before expert comparison details."""

    lines = [f"truth: {report['classification']}"]
    labels = {
        "site-metadata": "site metadata",
        "scratch-object": "scratch object",
        "project-object": "project object",
    }
    for layer in report["layers"]:
        detail = ""
        if layer["id"] == "site-metadata" and layer.get("score"):
            score = layer["score"]
            detail = f" score={score['score']:g}/{score['max_score']:g}"
        elif layer.get("raw_words") is not None:
            detail = f" raw words={layer['raw_words']}"
        lines.append(f"  {labels[layer['id']]:15} {layer['status']}{detail}")
    for hypothesis in report.get("context_hypotheses", []):
        lines.append(
            "context hypothesis: unused call return occupancy "
            f"({hypothesis['callee']}, confidence={hypothesis['confidence']})"
        )
        lines.append(f"next: {hypothesis['action']}")
    return lines
