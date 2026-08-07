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


def alignment_caution_lines(item: Comparison) -> list[str]:
    """Render the aligned-count comparability caution, ahead of the numbers.

    Same placement rule as `warning_lines`, for the same reason: a reader who
    meets this after `aligned_total=` has already ranked on it. One campaign
    spent 257 builds on a lever table ordered by a number this line retracts.
    """

    return [item.alignment_caution] if item.alignment_caution else []


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


def raw_versus_words_lines(item: Comparison) -> list[str]:
    """Explain a `raw=` that exceeds `words=`, once, where both are printed.

    The summary line reports both counts and never said why they differ. On a
    pair whose target names each float literal with its own `.rodata` symbol
    and whose candidate merges them into one anonymous section, the gap is
    every literal load: `words` excludes a word whose only differing bits are
    relocation-controlled, and a hand-rolled `objdump -d` diff does not. One
    campaign read the resulting 45 permanently-differing disassembly rows as
    outstanding pool work and spent about an hour attributing them.

    So the line names the number, the class, and the consequence: a raw
    disassembly diff cannot reach zero on such a pair, and `words = 0` is the
    honest gate.
    """

    controlled = item.raw_difference_breakdown.get("relocation_controlled", 0)
    if not controlled or item.raw_word_mismatches <= item.word_mismatches:
        return []
    return [
        f"raw-vs-words: raw={item.raw_word_mismatches} exceeds "
        f"words={item.word_mismatches} by {controlled} relocation-controlled "
        "word(s):",
        "              linker-filled bits no source change moves. A raw "
        "objdump text diff counts",
        "              them permanently, so words=0 is the honest gate, not a "
        "byte-identical dump.",
    ]


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
    if item.aligned_gaps:
        lines.append(
            "alignment gaps: "
            f"insertions={item.aligned_insertions} "
            f"deletions={item.aligned_deletions} "
            f"(opcodes={item.opcode_mismatches}, "
            f"words={item.word_mismatches}, raw={item.raw_word_mismatches})"
        )
    breakdown = ", ".join(
        f"{name}={count}" for name, count in item.raw_difference_breakdown.items()
    )
    if breakdown:
        lines.append(f"raw difference classes: {breakdown}")
    lines.extend(raw_versus_words_lines(item))
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
