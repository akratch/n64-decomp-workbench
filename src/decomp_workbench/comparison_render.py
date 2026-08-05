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


def scratch_score_acceptance(item: Comparison) -> tuple[bool, str]:
    """Return the raw-object acceptance used by a decomp.me scratch.

    Normal comparison masks linker-controlled relocation fields, so two
    objects can be function-exact while decomp.me still gives a non-zero
    score. The local proxy requires every pre-link instruction word and
    relocation symbol/addend target to agree.
    """

    if item.raw_word_mismatches:
        return False, "raw-instruction-word-mismatch"
    if item.relocation_target_mismatches:
        return False, "relocation-target-mismatch"
    if not item.exact:
        return False, "linked-function-mismatch"
    return True, "local-score-proxy-exact"


def scratch_comparison_payload(item: Comparison) -> dict[str, object]:
    """Render comparison evidence with both linked and scratch acceptance."""

    score_exact, basis = scratch_score_acceptance(item)
    payload = comparison_payload(item, cross_rom=False)
    payload.update(
        accepted=score_exact,
        acceptance_basis=basis,
        decomp_me_score_proxy_exact=score_exact,
        linked_function_exact=item.exact,
        raw_instruction_words_exact=item.raw_word_mismatches == 0,
        relocation_targets_exact=item.relocation_target_mismatches == 0,
    )
    return payload


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
    if (
        item.target_frame_size is not None
        and item.candidate_frame_size is not None
        and item.target_frame_size != item.candidate_frame_size
    ):
        difference = abs(item.candidate_frame_size - item.target_frame_size)
        lines.append(
            "frame mismatch: "
            f"target={item.target_frame_size} "
            f"candidate={item.candidate_frame_size} "
            f"({difference}-byte difference)"
        )
        target_layout = item.target_frame_layout
        candidate_layout = item.candidate_frame_layout
        if target_layout and candidate_layout:
            lines.append(
                "frame evidence: "
                f"save-slots={target_layout['observed_save_bytes']}->"
                f"{candidate_layout['observed_save_bytes']} bytes; "
                f"non-save={target_layout['non_save_frame_bytes']}->"
                f"{candidate_layout['non_save_frame_bytes']} bytes"
            )
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
