"""Versioned JSON reports and structured command failures.

The terminal and JSON interfaces answer the same questions, but JSON has an
additional durability obligation: a caller must always receive one parseable,
schema-named document when it explicitly asks for JSON.  Command handlers stay
focused on domain behavior; :func:`run_json_handler` supplies the common
envelope without hiding programming errors or changing non-JSON behavior.
"""

from __future__ import annotations

import contextlib
import io
import json
from argparse import Namespace
from collections.abc import Callable
from typing import Any

ERROR_SCHEMA = "decomp-workbench-error-v1"

SCHEMAS: dict[str, str] = {
    "bundle-scratch": "decomp-workbench-scratch-bundle-v1",
    "align": "decomp-workbench-shift-diff-v1",
    "align-dumps": "decomp-workbench-shift-diff-v1",
    "audit-handoff": "decomp-workbench-handoff-audit-v1",
    "campaign": "decomp-workbench-campaign-v1",
    "campaign-export": "decomp-workbench-campaign-export-result-v1",
    "campaign-note": "decomp-workbench-campaign-note-v1",
    "campaign-resume": "decomp-workbench-campaign-status-v1",
    "campaign-status": "decomp-workbench-campaign-status-v1",
    "cache-prune": "decomp-workbench-cache-prune-v1",
    "cache-restore": "decomp-workbench-cache-restore-v1",
    "cache-status": "decomp-workbench-cache-status-v1",
    "check-scratch": "decomp-workbench-scratch-check-v1",
    "compare": "decomp-workbench-comparison-v1",
    "compare-dumps": "decomp-workbench-comparison-v1",
    "compile-rank": "decomp-workbench-compile-rank-v1",
    "commands": "decomp-workbench-command-map-v1",
    "context-lint": "decomp-workbench-context-lint-v1",
    "doctor": "decomp-workbench-doctor-v1",
    "experiment-validate": "decomp-workbench-experiment-v1",
    "experiment-compose": "decomp-workbench-composition-v1",
    "experiment-inspect-source": "decomp-workbench-source-inspection-v1",
    "experiment-review-mutation": "decomp-workbench-mutation-review-v1",
    "fingerprint-toolchain": "decomp-workbench-toolchain-fingerprint-v1",
    "force-rows": "decomp-workbench-force-rows-v1",
    "force-rows-dumps": "decomp-workbench-force-rows-v1",
    "fidelity": "decomp-workbench-object-fidelity-v1",
    "diagnose": "decomp-workbench-diagnosis-v1",
    "diagnose-dumps": "decomp-workbench-diagnosis-v1",
    "install-skill": "decomp-workbench-skill-install-v1",
    "instrument-scheduler": "decomp-workbench-scheduler-instrument-v1",
    "lineage": "decomp-workbench-cross-rom-lineage-v1",
    "matrix": "decomp-workbench-matrix-v1",
    "next": "decomp-workbench-next-v1",
    "next-dumps": "decomp-workbench-next-v1",
    "note-add": "decomp-workbench-note-add-v1",
    "note-list": "decomp-workbench-note-list-v1",
    "note-merge": "decomp-workbench-note-merge-v1",
    "oracle-diff": "decomp-workbench-oracle-diff-v1",
    "oracle-export": "decomp-workbench-oracle-export-v1",
    "oracle-plan": "decomp-workbench-oracle-plan-v1",
    "oracle-status": "decomp-workbench-oracle-sweep-v1",
    "oracle-sweep": "decomp-workbench-oracle-sweep-v1",
    "object-collateral": "decomp-workbench-object-collateral-v1",
    "probe-lines": "decomp-workbench-line-probe-v1",
    "rank": "decomp-workbench-rank-v1",
    "window": "decomp-workbench-window-v1",
    "window-dumps": "decomp-workbench-window-v1",
    "relocation-aliases": "decomp-workbench-relocation-aliases-v1",
    "pass-diff": "decomp-workbench-original-pass-diff-v1",
    "phase": "decomp-workbench-phase-v1",
    "phase-dumps": "decomp-workbench-phase-v1",
    "replay-as1": "decomp-workbench-pass-replay-v1",
    "score": "decomp-workbench-score-v1",
    "trace-alias": "decomp-workbench-trace-alias-v1",
    "trace-blocks": "decomp-workbench-web-blocks-v1",
    "trace-cascade": "decomp-workbench-cascade-v1",
    "trace-order": "decomp-workbench-color-order-v1",
    "trace-copy-decisions": "decomp-workbench-copy-decisions-v1",
    "trace-fifo": "decomp-workbench-trace-fifo-v1",
    "trace-globalcolor": "decomp-workbench-trace-globalcolor-v1",
    "trace-origin-probe": "decomp-workbench-origin-probe-v1",
    "trace-scheduler": "decomp-workbench-scheduler-trace-v1",
    "trace-source": "decomp-workbench-trace-source-v1",
    "trace-stack-homes": "decomp-workbench-stack-homes-v1",
    "trace-summary": "decomp-workbench-trace-summary-v1",
    "trace-webs": "decomp-workbench-allocator-webs-v2",
    "toolchain-init": "decomp-workbench-toolchain-v1",
    "toolchain-calibrate": "decomp-workbench-toolchain-v1",
    "toolchain-status": "decomp-workbench-toolchain-v1",
    "view": "decomp-workbench-view-v1",
    "view-dumps": "decomp-workbench-view-v1",
}


def schema_for(command: str) -> str:
    """Return the stable report schema for one command."""

    return SCHEMAS.get(command, f"decomp-workbench-{command}-v1")


def with_schema(command: str, value: Any) -> dict[str, Any]:
    """Return one top-level object carrying a schema identity.

    Existing schema-bearing payloads (campaigns and scratch bundles) retain
    their domain schema.  Historical list-valued reports are wrapped under
    ``results`` so they can finally participate in schema evolution.
    """

    if isinstance(value, dict):
        payload = dict(value)
        payload.setdefault("schema", schema_for(command))
        return payload
    return {"schema": schema_for(command), "results": value}


def classify_error(message: str, status: int) -> str:
    """Classify a user-facing failure without guessing domain internals."""

    lowered = message.casefold()
    if "timeout" in lowered or "exceeded --timeout" in lowered:
        return "timeout"
    if "does not exist" in lowered or "no such file" in lowered:
        return "not-found"
    if "failed with exit" in lowered or "objdump failed" in lowered:
        return "process-failed"
    if status == 2:
        return "usage"
    if status == 1:
        return "no-result"
    return "command-failed"


def error_report(
    command: str,
    *,
    status: int,
    message: str,
    stage: str = "command",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared error envelope."""

    error: dict[str, Any] = {
        "kind": classify_error(message, status),
        "message": message,
    }
    if details:
        error["details"] = details
    return {
        "schema": ERROR_SCHEMA,
        "command": command,
        "stage": stage,
        "status": status,
        "error": error,
    }


def render_json(value: Any) -> str:
    """Serialize a public JSON document deterministically."""

    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def run_json_handler(
    command: str,
    args: Namespace,
    handler: Callable[[Namespace], int],
) -> int:
    """Run one existing handler under the durable JSON contract.

    Handlers already render domain payloads.  Capturing only in JSON mode lets
    the compatibility terminal path remain byte-for-byte unchanged while this
    adapter adds a schema or turns stderr-only failures into a JSON document.
    An invalid success payload is a workbench defect and returns status 2
    rather than leaking non-JSON text to an automation caller.
    """

    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = handler(args)

    output = stdout.getvalue().strip()
    diagnostic = stderr.getvalue().strip()
    if output:
        try:
            value = json.loads(output)
        except json.JSONDecodeError:
            message = diagnostic or "command emitted invalid JSON"
            print(render_json(error_report(command, status=2, message=message)), end="")
            return 2
        print(render_json(with_schema(command, value)), end="")
        return status

    message = diagnostic.removeprefix("error: ").strip() or "command produced no result"
    report = error_report(command, status=status or 2, message=message)
    print(render_json(report), end="")
    return status or 2
