"""Shared human and JSON rendering for comparison evidence."""

from __future__ import annotations

from collections.abc import Sequence

from .census import CensusResult
from .compare import ALIGNED_CLASS_KEYS
from .model import Comparison
from .schema import summary_line
from .terminal import Painter


def comparison_line(item: Comparison, painter: Painter | None = None) -> str:
    """Render the summary line from the shared metric registry.

    The verdict is the reason the line exists, and it was the only plain token
    on a screen where a downstream explanatory sentence rendered bold red. The
    key is bolded and the value takes its family's colour, so a scrolled batch
    of reports is separable by hue before any of it is read.
    """

    line = summary_line(item)
    if painter is None or not painter.enabled:
        return line
    token = f"verdict={item.verdict}"
    if not line.startswith(token):
        return line
    return painter.bold("verdict=") + painter.verdict(item.verdict) + line[len(token) :]


def warning_lines(warnings: Sequence[str]) -> list[str]:
    """Render input warnings as the first thing a reader sees.

    Ahead of the verdict, not beside the evidence: these say the comparison
    answered a different question than the one that was asked, and a reader who
    meets one after the numbers has already believed the numbers.
    """

    return [f"warning: {warning}" for warning in warnings]


def comparison_acceptance(item: Comparison, *, cross_rom: bool) -> tuple[bool, str]:
    """Return command acceptance independently from the evidence verdict."""

    if item.exact:
        return True, "function-exact"
    if cross_rom and item.structural_exact:
        return True, "cross-rom-structural"
    return False, "mismatch"


def comparison_payload(
    item: Comparison,
    *,
    cross_rom: bool,
    census: Sequence[CensusResult] = (),
) -> dict[str, object]:
    """Add command-level acceptance context to a comparison JSON result."""

    accepted, basis = comparison_acceptance(item, cross_rom=cross_rom)
    payload: dict[str, object] = {
        **item.as_dict(),
        "accepted": accepted,
        "acceptance_basis": basis,
    }
    if census:
        payload["census"] = [result.as_dict() for result in census]
    return payload


def comparison_explanation_lines(
    item: Comparison,
    *,
    cross_rom: bool,
    guidance: bool = True,
) -> list[str]:
    """Return compact, action-oriented explanation lines.

    `guidance=False` returns the evidence without the `next:` footer, for
    `diagnose`, which renders the aligned view's richer footer instead and
    would otherwise print two lever blocks for one residual.
    """

    lines: list[str] = []
    aligned = ", ".join(
        f"{key}={getattr(item, key)}"
        for key in ALIGNED_CLASS_KEYS
        if getattr(item, key)
    )
    if aligned:
        lines.append(f"aligned residual classes: {aligned}")
    breakdown = ", ".join(
        f"{name}={count}" for name, count in item.raw_difference_breakdown.items()
    )
    if breakdown:
        lines.append(f"raw difference classes: {breakdown}")
    if item.diff_sites:
        classes = ", ".join(
            f"{name}={count}" for name, count in item.diff_site_classes.items()
        )
        lines.append(f"diff_sites={len(item.diff_sites)} ({classes})")
    # One footer, indented like `view`'s: the guidance is now several lines
    # long (levers, then the command, then the instrumentation branch), and
    # repeating `next:` on each of them read as several unrelated instructions.
    if guidance:
        lines.extend(
            ("next: " if position == 0 else "      ") + entry
            for position, entry in enumerate(item.guidance)
        )
    accepted, basis = comparison_acceptance(item, cross_rom=cross_rom)
    if basis == "cross-rom-structural":
        lines.append(
            "acceptance: PASS (cross-ROM structural evidence only; exact=false)"
        )
    elif not accepted and cross_rom:
        lines.append("acceptance: FAIL (cross-ROM structure also differs)")
    return lines


def diff_site_lines(item: Comparison) -> list[str]:
    """Return every differing site, grouped by class."""

    lines: list[str] = []
    for name in item.diff_site_classes:
        for site in item.diff_sites:
            if site["class"] != name:
                continue
            lines.extend(
                (
                    f"\n[{site['index']:4d}] {name}",
                    f"       target    {site['target_word']}  {site['target']}",
                    f"       candidate {site['candidate_word']}  {site['candidate']}",
                )
            )
    return lines
