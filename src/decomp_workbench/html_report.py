"""Self-contained, accessible HTML reports built from reduced evidence."""

from __future__ import annotations

import html
import json
from typing import Any

from .model import Comparison
from .view import MechanismView

STYLE = """
:root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
body { max-width: 92rem; margin: 2rem auto; padding: 0 1rem 4rem; line-height: 1.45; }
h1, h2 { line-height: 1.15; }
.summary { display: flex; flex-wrap: wrap; gap: .5rem; }
.chip { border: 1px solid #8888; border-radius: 999px; padding: .2rem .65rem; }
.proof {
  border-left: .25rem solid #b76b20;
  padding: .4rem 1rem;
  background: #b76b2012;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }
th, td {
  border-bottom: 1px solid #8885;
  padding: .42rem;
  text-align: left;
  vertical-align: top;
}
th { position: sticky; top: 0; background: Canvas; }
code, pre { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
pre { overflow: auto; padding: 1rem; background: #8881; }
tr[data-class="match"] { opacity: .62; }
tr:not([data-class="match"]) { background: #d77b1610; }
@media print { details { display: block; } th { position: static; } }
"""


def _document(title: str, body: str, payload: dict[str, Any]) -> str:
    serialized = html.escape(json.dumps(payload, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLE}</style>
</head>
<body>
{body}
<details><summary>Machine-readable evidence</summary>
<pre id="report">{serialized}</pre>
</details>
</body>
</html>
"""


def render_diagnosis_html(
    view: MechanismView,
    *,
    comparison: Comparison | None = None,
    report_regs: bool = False,
) -> str:
    """Render the aligned view and optional exact comparator in one file."""

    view_payload = view.as_dict(report_regs=report_regs)
    payload: dict[str, Any] = {
        "schema": "decomp-workbench-html-diagnosis-v1",
        "view": view_payload,
        "comparison": comparison.as_dict() if comparison else None,
    }
    rows = "\n".join(
        "<tr "
        f'data-class="{html.escape(row.classification)}">'
        f"<td>{row.index}</td>"
        f"<td>{html.escape(row.classification)}</td>"
        f"<td><code>{html.escape(row.target or '-')}</code></td>"
        f"<td><code>{html.escape(row.candidate or '-')}</code></td>"
        "</tr>"
        for row in view.rows
    )
    guidance = "".join(f"<li>{html.escape(line)}</li>" for line in view.guidance)
    chips = "".join(
        f'<span class="chip">{html.escape(name)}={count}</span>'
        for name, count in view.counts.items()
        if count
    )
    exact = comparison.exact if comparison else view.verdict == "exact"
    proof = (
        "Function-level exact object evidence. Whole-project link, ROM, and "
        "collateral verification still remain."
        if exact
        else "Diagnostic evidence only; this report does not claim a source match."
    )
    body = f"""
<h1>{html.escape(view.symbol or "Aligned function diagnosis")}</h1>
<p><code>{html.escape(view.target)}</code> ↔
<code>{html.escape(view.candidate)}</code></p>
<div class="summary">
<span class="chip">verdict={html.escape(view.verdict)}</span>{chips}
</div>
<p class="proof">{html.escape(proof)}</p>
<h2>Aligned instructions</h2>
<table>
<thead><tr><th>#</th><th>Class</th><th>Target</th><th>Candidate</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>Next actions</h2><ol>{guidance}</ol>
"""
    return _document("decomp-workbench diagnosis", body, payload)
