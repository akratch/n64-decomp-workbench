"""Shared human and JSON rendering for comparison evidence."""

from __future__ import annotations

from collections.abc import Sequence

from .census import CensusResult
from .compare import ALIGNED_CLASS_KEYS
from .model import Comparison
from .schema import summary_line
from .terminal import Painter

#: Commutative sites quoted on the terminal before the rest are deferred to
#: ``--json``. Each one is five lines; a screen full of them stops being a
#: lever list and becomes a dump.
COMMUTATIVE_SITES = 5


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


def relocation_symbol_caution_lines(item: Comparison) -> list[str]:
    """Announce different-symbol relocation targets ahead of the counters.

    Word masking removes a relocation-filled field from ``word_mismatches``,
    which is right when the two sides name the same object at a different
    addend and wrong when they name different objects. On a pair where the
    target reads one global and the candidate reads another, the masked
    counters read ``words=0 opcodes=0 gaps=0`` while the candidate is
    semantically a different function. One campaign scored such a pair as a
    potential exact match on those three numbers alone.

    So this prints before them, in the same position as `warning_lines`, and
    says what the zeroes do not cover.
    """

    count = item.relocation_symbol_mismatches
    if not count:
        return []
    noun, verb = ("site", "names") if count == 1 else ("sites", "name")
    lines = [
        f"relocation-symbol caution: {count} relocation {noun} {verb} a "
        "different symbol in each object.",
        "                           Masking excludes those words, so "
        f"words={item.word_mismatches} is a floor, not the residual: a "
        "different",
        "                           symbol at the same site is a different "
        "variable being read, and no link resolves it.",
    ]
    if any(
        difference.get("candidate_section_symbol")
        for difference in item.relocation_target_differences
    ):
        lines.append(
            "                           At least one site reaches an "
            "anonymous section offset where the target names an object: "
            "check"
        )
        lines.append(
            "                           the translation unit does not "
            "already define it, or the linked layout shifts."
        )
    return lines


def comparison_acceptance(item: Comparison, *, cross_rom: bool) -> tuple[bool, str]:
    """Return command acceptance independently from the evidence verdict."""

    # `exact` means the masked words and the relocation *kinds* agree, which
    # deliberately says nothing about which symbol each relocation names. A
    # candidate that reads a different global is not the target function, so
    # acceptance takes the symbol identity that exactness leaves out rather
    # than reporting a pass a reader has to retract from the verdict line.
    if item.relocation_symbol_mismatches:
        return False, "relocation-symbol-mismatch"
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
        acceptance_summary=scratch_acceptance_line(item),
        exact_scope="linked-function-after-relocation-field-masking",
        decomp_me_score_proxy_exact=score_exact,
        linked_function_exact=item.exact,
        raw_instruction_words_exact=item.raw_word_mismatches == 0,
        relocation_targets_exact=item.relocation_target_mismatches == 0,
    )
    return payload


def scratch_acceptance_line(item: Comparison) -> str:
    """Return the unambiguous first line for scratch acceptance."""

    accepted, _ = scratch_score_acceptance(item)
    if accepted:
        return "ACCEPTED — raw instruction words and relocation targets agree"
    reasons: list[str] = []
    if item.raw_word_mismatches:
        count = item.raw_word_mismatches
        noun = "word" if count == 1 else "words"
        verb = "differs" if count == 1 else "differ"
        reasons.append(f"{count} raw instruction {noun} {verb}")
    elif item.exact:
        reasons.append("instruction text exact")
    if item.relocation_target_mismatches:
        count = item.relocation_target_mismatches
        noun = "target" if count == 1 else "targets"
        verb = "differs" if count == 1 else "differ"
        reasons.append(f"{count} relocation {noun} {verb}")
    if not item.exact and not item.raw_word_mismatches:
        reasons.append("linked function differs")
    return "NOT ACCEPTED — " + "; ".join(reasons)


def relocation_target_difference_lines(item: Comparison) -> list[str]:
    """Render target/candidate relocation details without requiring objdump."""

    if not item.relocation_target_differences:
        return []
    lines = [
        f"relocation target differences: {len(item.relocation_target_differences)}"
    ]

    def side(value: object) -> str:
        if not isinstance(value, dict):
            return "<missing>"
        symbol = value.get("symbol") or "<none>"
        addend = int(value.get("addend", 0))
        suffix = f"{addend:+#x}" if addend else ""
        return (
            f"offset=0x{int(value['offset']):x} type={value['kind']} "
            f"symbol={symbol}{suffix}"
        )

    for difference in item.relocation_target_differences:
        # `difference` names which half of the target moved. Only `addend` is
        # the linker-controlled half; the reader needs that on the row, not
        # inferred by eye from two symbol spellings.
        classification = str(difference.get("difference", "symbol"))
        if difference.get("candidate_section_symbol"):
            classification += ", candidate reaches an anonymous section offset"
        lines.append(
            f"  instruction {difference['instruction_index']} "
            f"relocation {difference['relocation_index']} "
            f"({classification})"
        )
        lines.append(f"    target    {side(difference.get('target'))}")
        lines.append(f"    candidate {side(difference.get('candidate'))}")
    return lines


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


def true_instruction_lines(item: Comparison) -> list[str]:
    """Show the true (unpadded) instruction count wherever it hides padding.

    `.text` is padded to a 16-byte, 4-instruction boundary, so
    `target_instructions`/`candidate_instructions` can include trailing pad
    words a source change never produced -- a probe three instructions too
    long once reported the same padded count as an exact-length one. Silent
    otherwise: printing this every time would bury the one comparison where it
    matters, which is exactly the reading that let the padding through.
    """

    lines: list[str] = []
    if item.target_true_instructions != item.target_instructions:
        lines.append(
            f"target padding: {item.target_instructions} reported, "
            f"{item.target_true_instructions} true "
            f"({item.target_instructions - item.target_true_instructions} "
            "pad word(s))"
        )
    if item.candidate_true_instructions != item.candidate_instructions:
        lines.append(
            f"candidate padding: {item.candidate_instructions} reported, "
            f"{item.candidate_true_instructions} true "
            f"({item.candidate_instructions - item.candidate_true_instructions} "
            "pad word(s))"
        )
    return lines


#: Moved blocks quoted on the terminal before the rest are deferred to
#: ``--json``. A permutation with more than a handful of relocated blocks is a
#: restructuring, and the count is the finding at that point, not the list.
LAYOUT_BLOCKS = 6


def layout_lines(item: Comparison) -> list[str]:
    """Render the auto-run edit script beside ``words``, or nothing.

    Placement is the whole point. ``words`` is on the summary line above; a
    reader who meets the edit script three screens down in ``--json`` has
    already ranked the candidate on a number that over-charges a permutation
    by three orders of magnitude. See
    ``decomp_workbench.compare.layout_summary``.
    """

    layout = item.layout
    if not layout:
        return []
    moved = list(layout.get("moved_blocks") or [])
    lines = [
        f"layout (shift-tolerant edit script, run automatically on {item.verdict}):",
        f"  blocks={layout['block_count']} "
        f"replaced={layout['replaced']} inserted={layout['inserted']} "
        f"deleted={layout['deleted']} "
        f"rows={layout['target_rows']}->{layout['candidate_rows']} "
        f"({int(layout['row_delta']):+d})",
        f"  rows_away={layout['rows_away']} "
        f"({layout['edit_distance']} edit + {layout['paired_mismatches']} "
        f"residual) against words={item.word_mismatches}",
    ]
    if not moved:
        lines.append(
            "  moved blocks: none -- the difference is not a permutation, so "
            "the positional counts are reading real new or changed code."
        )
        return lines
    lines.append(
        f"  moved blocks: {layout['moved_block_count']} "
        f"({layout['moved_rows']} row(s)) present in both objects at "
        "different positions"
    )
    for block in moved[:LAYOUT_BLOCKS]:
        lines.append(
            f"    {block['rows']:>5} row(s)  target "
            f"{block['target_start']}..{block['target_stop'] - 1}  ->  "
            f"candidate {block['candidate_start']}..{block['candidate_stop'] - 1}  "
            f"({int(block['displacement']):+d})"
        )
    if len(moved) > LAYOUT_BLOCKS:
        lines.append(
            f"    ... {len(moved) - LAYOUT_BLOCKS} more; the full list is in "
            "--json under layout.moved_blocks"
        )
    lines.append(
        "  A permutation is a block-order question, not a "
        f"{item.word_mismatches}-word one. Run `align` for the full script."
    )
    return lines


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
    lines.extend(true_instruction_lines(item))
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
    lines.extend(layout_lines(item))
    lines.extend(raw_versus_words_lines(item))
    lines.extend(relocation_target_difference_lines(item))
    if item.diff_sites:
        classes = ", ".join(
            f"{name}={count}" for name, count in item.diff_site_classes.items()
        )
        lines.append(f"diff_sites={len(item.diff_sites)} ({classes})")
    lines.extend(commutative_lines(item))
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


def commutative_lines(item: Comparison) -> list[str]:
    """Return the commutative operand section, or nothing.

    A count of commutative rows is not a lever. This names the expression, the
    two operands, and -- where the arithmetic row is byte-identical and only
    its operand loads are crossed -- the row the reader would otherwise have
    sent to the allocator by mistake.
    """

    findings = item.commutative_findings
    if not findings:
        return []
    crossed = sum(1 for entry in findings if entry.get("kind") == "operand-load")
    heading = f"commutative operands: {len(findings)} site(s)"
    if crossed:
        heading += f", {crossed} visible only in the operand loads"
    lines = [heading]
    for entry in findings[:COMMUTATIVE_SITES]:
        sources = ", ".join(str(name) for name in entry["sources"])
        lines.append(f"  row {entry['aligned_row']}  {entry['opcode']} ({sources})")
        lines.append(f"    target    {entry['target']}")
        lines.append(f"    candidate {entry['candidate']}")
        for definition in entry["definitions"]:
            lines.append(
                f"    defines {definition['register']} at row "
                f"{definition['aligned_row']}: {definition['target']} | "
                f"{definition['candidate']}"
            )
        lines.append(f"    lever: {entry['lever']}")
    if len(findings) > COMMUTATIVE_SITES:
        lines.append(
            f"  ... {len(findings) - COMMUTATIVE_SITES} more site(s); the full "
            "list is in --json under commutative_findings"
        )
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
