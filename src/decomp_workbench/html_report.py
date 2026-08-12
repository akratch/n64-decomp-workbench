"""Self-contained, accessible HTML reports built from the same view model.

The HTML used to be a flat table of aligned rows: no lanes, no hunk grouping,
no webs, and no substitution annotations, with all four reachable only inside
the collapsed machine-readable blob. That contradicted the claim this file
exists to support -- that an exported report preserves the same evidence as the
screen -- and it dropped the one thing the terminal renderer is proud of, which
is that one bijection explains N sites.

Everything here therefore reads `view.hunks`, `view.lanes`, and `view.webs`:
the *same* view model `view_cli` consumes, so the two renderings cannot drift
into disagreeing about what the evidence is. Only presentation differs, and
HTML gets to do the two things a terminal cannot -- link a web to the hunks it
explains, and keep the verdict on screen while the reader scrolls.

Self-contained by contract: inline CSS, no script, no network. Anchors and
`<details>` carry the interactivity, so the page works with JavaScript disabled
and prints with every section expanded.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Sequence
from typing import Any

from .model import Comparison
from .view import MATCH, AlignedRow, Hunk, MechanismView

#: Web swatch hues, in the terminal painter's order, so a reader with both
#: open sees w1 as the same colour in each.
WEB_HUES = (
    "#1f8a8a",
    "#a8760a",
    "#9333a8",
    "#2f8a3c",
    "#2563c7",
    "#c0392b",
)

STYLE = """
:root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
body { max-width: 92rem; margin: 0 auto 4rem; padding: 0 1rem 2rem; line-height: 1.45; }
h1, h2, h3 { line-height: 1.15; scroll-margin-top: 6rem; }
a { color: inherit; text-underline-offset: .15em; }
a:focus-visible, summary:focus-visible {
  outline: 3px solid Highlight;
  outline-offset: 3px;
}
.skip-link {
  position: absolute;
  left: .75rem;
  top: -4rem;
  z-index: 20;
  background: Canvas;
  padding: .5rem;
}
.skip-link:focus { top: .75rem; }
.verdict-bar {
  position: sticky;
  top: 0;
  z-index: 5;
  background: Canvas;
  border-bottom: 1px solid #8886;
  padding: .75rem 0 .5rem;
  margin-bottom: 1rem;
}
.verdict { font-size: 1.15rem; font-weight: 700; margin: 0; }
.summary { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .4rem; }
.chip {
  border: 1px solid #8888;
  border-radius: 999px;
  padding: .1rem .6rem;
  font-size: .85rem;
}
.chip.score { border-color: #2f8a3c; }
.proof {
  border-left: .25rem solid #b76b20;
  padding: .4rem 1rem;
  background: #b76b2012;
}
.warning {
  border-left: .25rem solid #c0392b;
  background: #c0392b18;
  padding: .5rem 1rem;
  font-weight: 600;
}
.table-scroll { max-width: 100%; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1.5rem; }
th, td {
  border-bottom: 1px solid #8885;
  padding: .3rem .45rem;
  text-align: left;
  vertical-align: top;
}
th { background: Canvas; font-size: .85rem; }
code, pre { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
pre { overflow: auto; padding: 1rem; background: #8881; }
td.num {
  text-align: right;
  width: 4rem;
  opacity: .55;
  font-variant-numeric: tabular-nums;
}
td.asm { white-space: pre; }
tr.context td.asm { opacity: .6; }
tr.diverge { background: #d77b1614; }
tr.diverge td.num { opacity: 1; font-weight: 700; }
.hunk { margin: 0 0 2rem; }
.hunk h3 { margin-bottom: .2rem; }
.meta { font-size: .85rem; opacity: .8; margin: 0 0 .4rem; }
.lanes { overflow-x: auto; }
.lanes table { width: auto; }
.lanes td, .lanes th { border: 0; padding: .1rem .35rem; white-space: pre; }
.lanes td.slot-diverge { outline: 2px solid #c0392b; border-radius: .2rem; }
.lanes tr.caret td { font-size: .8rem; opacity: .85; }
.web { font-weight: 700; text-decoration: none; }
.swatch {
  display: inline-block;
  width: .7rem;
  height: .7rem;
  border-radius: .15rem;
  margin-right: .35rem;
}
.annot { font-size: .85rem; white-space: nowrap; }
li.lever code { background: #8881; padding: .1rem .35rem; border-radius: .2rem; }
ol li { margin-bottom: .3rem; }
@media print {
  details > * { display: block !important; }
  details > summary { display: none !important; }
  .verdict-bar { position: static; }
}
"""


def document_shell(
    title: str,
    body: str,
    payload: dict[str, Any],
    *,
    evidence_label: str = "Machine-readable evidence",
    extra_style: str = "",
) -> str:
    """Wrap one report in the shared accessible, offline document shell."""

    serialized = html.escape(json.dumps(payload, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#202124">
<title>{html.escape(title)}</title>
<style>{STYLE}\n{extra_style}</style>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to report</a>
<main id="main-content">
{body}
<details open><summary>{html.escape(evidence_label)}</summary>
<pre id="report">{serialized}</pre>
</details>
</main>
</body>
</html>
"""


def _document(title: str, body: str, payload: dict[str, Any]) -> str:
    return document_shell(title, body, payload)


def _hue(number: int) -> str:
    return WEB_HUES[(number - 1) % len(WEB_HUES)]


def _swatch(number: int) -> str:
    return (
        f'<span aria-hidden="true" class="swatch" '
        f'style="background:{_hue(number)}"></span>'
    )


def _range(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"{value[0]}..{value[1]}"


def _bytes(value: tuple[int, int] | None) -> str:
    return "none" if value is None else f"0x{value[0]:x}..0x{value[1]:x}"


def _annotation_cell(row: AlignedRow, webs: dict[tuple[str, str], int]) -> str:
    """Render the substitution labels the terminal prints after each row."""

    if row.classification == MATCH:
        return ""
    parts: list[str] = []
    for pair in row.substitutions:
        number = webs.get(pair)
        label = html.escape(f"{pair[0]}->{pair[1]}")
        if number is None:
            parts.append(f"<span>{label}</span>")
            continue
        parts.append(
            f'<a href="#web-{number}" class="web" style="color:{_hue(number)}">'
            f"{_swatch(number)}{label} [w{number}]</a>"
        )
    return " ".join(parts) or html.escape(row.classification)


def _hunk_section(
    view: MechanismView,
    hunk: Hunk,
    webs: dict[tuple[str, str], int],
    *,
    context: int,
) -> str:
    low = max(0, hunk.start - context)
    high = min(len(view.rows) - 1, hunk.end + context)
    rows: list[str] = []
    for row in view.rows[low : high + 1]:
        inside = hunk.start <= row.index <= hunk.end
        rows.append(
            f'<tr class="{"diverge" if inside else "context"}">'
            f'<td class="num">{row.index}</td>'
            f'<td class="asm"><code>{html.escape(row.target or "-")}</code></td>'
            f'<td class="asm"><code>{html.escape(row.candidate or "-")}</code></td>'
            f'<td class="annot">{_annotation_cell(row, webs)}</td>'
            "</tr>"
        )
    meta = " &middot; ".join(
        (
            f"class={html.escape(hunk.classification)}",
            f"rows={hunk.start}..{hunk.end}",
            f"target={_range(hunk.target_range)}",
            f"candidate={_range(hunk.candidate_range)}",
            f"target_bytes={_bytes(hunk.target_bytes)}",
        )
    )
    return f"""<section class="hunk" id="hunk-{hunk.hunk}">
<h3><a href="#hunk-{hunk.hunk}">Hunk {hunk.hunk}</a></h3>
<p class="meta">{meta}</p>
<div class="table-scroll"><table>
<caption>Aligned instructions for hunk {hunk.hunk}</caption>
<thead><tr>
<th scope="col">#</th><th scope="col">Target</th>
<th scope="col">Candidate</th><th scope="col">Substitution</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>
</section>"""


def _lane_cells(values: Sequence[str], total: int, diverge: int | None) -> str:
    cells: list[str] = []
    for slot in range(total):
        text = values[slot] if slot < len(values) else "-"
        mark = ' class="slot-diverge"' if slot == diverge else ""
        cells.append(f"<td{mark}>{html.escape(text)}</td>")
    return "".join(cells)


def _lanes_section(view: MechanismView) -> str:
    """Render each lane as a row of slots, marking the divergence."""

    if not view.lanes:
        return ""
    blocks: list[str] = []
    for lane in view.lanes:
        total = max(len(lane.target), len(lane.candidate), 1)
        if lane.divergence is None:
            detail = f"identical {len(lane.target)}/{total}"
        else:
            detail = f"slot={lane.divergence} aligned_row={lane.divergence_row}"
            if lane.rotation:
                detail += f" rotation=+{lane.rotation}"
        blocks.append(
            f"""<h3>{html.escape(lane.classification)}</h3>
<div class="lanes"><table>
<caption>{html.escape(lane.classification)} register lane</caption>
<tbody>
<tr><th scope="row">target</th>
{_lane_cells(lane.target, total, lane.divergence)}</tr>
<tr><th scope="row">candidate</th>
{_lane_cells(lane.candidate, total, lane.divergence)}</tr>
<tr class="caret"><th scope="row"></th>
<td colspan="{total}">{html.escape(detail)}</td></tr>
</tbody>
</table></div>"""
        )
    return (
        "<h2>Register lanes</h2>"
        '<p class="meta">Per-class assignment sequences, matching instructions '
        "included.</p>" + "".join(blocks)
    )


def _webs_section(view: MechanismView, hunk_of_row: dict[int, int]) -> str:
    """List each bijection, linking to every hunk it explains."""

    if not view.webs:
        return ""
    rows: list[str] = []
    for number, web in enumerate(view.webs, 1):
        hunks = sorted({hunk_of_row[row] for row in web.rows if row in hunk_of_row})
        links = (
            ", ".join(f'<a href="#hunk-{item}">hunk {item}</a>' for item in hunks)
            or "context only"
        )
        listed = ",".join(str(item) for item in web.rows)
        rows.append(
            f'<tr id="web-{number}">'
            f'<td class="web" style="color:{_hue(number)}">'
            f"{_swatch(number)}{html.escape(web.web)}</td>"
            f"<td><code>{html.escape(web.target)} &rarr; "
            f"{html.escape(web.candidate)}</code></td>"
            f'<td class="num">{web.count}</td>'
            f"<td>{links}</td>"
            f'<td class="annot">{html.escape(listed)}</td>'
            "</tr>"
        )
    return f"""<h2>Webs</h2>
<p class="meta">One consistent substitution may explain many sites.</p>
<div class="table-scroll"><table>
<caption>Consistent register substitutions</caption>
<thead><tr>
<th scope="col">Web</th><th scope="col">Substitution</th>
<th scope="col">Sites</th><th scope="col">Hunks</th><th scope="col">Rows</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>"""


LEVER_RE = re.compile(r"^\s*lever (\d+):\s*(.+)$")
COMMAND_RE = re.compile(r"decomp-workbench [a-z0-9 <>|\-]+")


def _guidance_item(line: str) -> str:
    """Render one footer entry, making its runnable parts look runnable.

    A `lever 19:` entry is an instruction plus an address, and in a browser the
    address should be copyable at a glance rather than buried mid-sentence.
    The snippet is rendered inline, offline: there is nowhere to link to that
    would still work from a file:// URL on a machine with no network.
    """

    lever = LEVER_RE.match(line)
    if lever is not None:
        number, action = lever.groups()
        return (
            f'<li class="lever"><code>decomp-workbench guide {number}</code> '
            f"&mdash; {html.escape(action)}</li>"
        )
    escaped = html.escape(line)
    return f"<li>{COMMAND_RE.sub(lambda m: f'<code>{m.group()}</code>', escaped)}</li>"


def _identity_chip(view: MechanismView) -> str:
    """Return an honest aligned-identity chip.

    Deliberately *not* called a decomp.me score: that number comes from the
    site's own scratch model, and printing a different number under the same
    name is how two tools come to disagree about whether a function is close.
    This is the share of aligned rows that are byte-identical, named as such.
    """

    total = view.aligned_rows
    if not total:
        return ""
    identical = view.counts.get(MATCH, 0)
    percent = 100.0 * identical / total
    return (
        f'<span class="chip score">aligned identical {identical}/{total} '
        f"({percent:.1f}%; not decomp.me&rsquo;s score)</span>"
    )


def render_diagnosis_html(
    view: MechanismView,
    *,
    comparison: Comparison | None = None,
    report_regs: bool = False,
    context: int = 2,
) -> str:
    """Render the aligned view and optional exact comparator in one file."""

    payload: dict[str, Any] = {
        "schema": "decomp-workbench-html-diagnosis-v1",
        "view": view.as_dict(report_regs=report_regs),
        "comparison": comparison.as_dict() if comparison else None,
    }
    webs: dict[tuple[str, str], int] = {
        (web.target, web.candidate): index for index, web in enumerate(view.webs, 1)
    }
    hunk_of_row = {
        row: hunk.hunk for hunk in view.hunks for row in range(hunk.start, hunk.end + 1)
    }
    guidance = "".join(_guidance_item(line) for line in view.guidance)
    chips = "".join(
        f'<span class="chip">{html.escape(name)}={count}</span>'
        for name, count in view.counts.items()
        if count
    )
    warnings = "".join(
        f'<p class="warning">warning: {html.escape(item)}</p>' for item in view.warnings
    )
    exact = comparison.exact if comparison else view.verdict == "exact"
    proof = (
        "Function-level exact object evidence. Whole-project link, ROM, and "
        "collateral verification still remain."
        if exact
        else "Diagnostic evidence only; this report does not claim a source match."
    )
    web_summary = " &middot; ".join(
        f'<a href="#web-{number}" class="web" style="color:{_hue(number)}">'
        f"{_swatch(number)}{html.escape(web.web)} "
        f"{html.escape(web.target)}&rarr;{html.escape(web.candidate)} "
        f"&times;{web.count}</a>"
        for number, web in enumerate(view.webs, 1)
    )
    hunks = "".join(
        _hunk_section(view, hunk, webs, context=context) for hunk in view.hunks
    )
    signature = html.escape(" ".join(view.signature)) or "none"
    body = f"""
<div class="verdict-bar">
<p class="verdict">verdict: {html.escape(view.verdict)}
&middot; playbook={html.escape(view.playbook)}</p>
<div class="summary">
{_identity_chip(view)}{chips}
<span class="chip">signature: {signature}</span>
</div>
</div>
<h1>{html.escape(view.symbol or "Aligned function diagnosis")}</h1>
{warnings}
<p><code>{html.escape(view.target)}</code> &harr;
<code>{html.escape(view.candidate)}</code></p>
{f'<p class="meta">webs: {web_summary}</p>' if web_summary else ""}
<p class="proof">{html.escape(proof)}</p>
{_lanes_section(view)}
<h2>Aligned hunks</h2>
{hunks or '<p class="meta">No hunks: nothing diverged.</p>'}
{_webs_section(view, hunk_of_row)}
<h2>Next actions</h2><ol>{guidance}</ol>
"""
    return _document("decomp-workbench diagnosis", body, payload)
