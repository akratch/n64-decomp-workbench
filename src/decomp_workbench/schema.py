"""One registry of comparison metric identities.

Human output and JSON output are rendered from the same tuple, so a printed
label can never drift from the JSON key that carries the same number. Two
recorded campaigns lost debugging cycles to ``words=`` in the terminal versus
``word_mismatches`` in ``--json``; naming both from one entry makes that
divergence structurally impossible.

The canonical name of a metric is its printed label *and* its JSON key. Where
a JSON key used to be spelled differently, the old spelling remains available
as a deprecated alias emitted alongside the canonical key for one release.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Any, Literal

RenderKind = Literal["integer", "text"]


@dataclass(frozen=True)
class Metric:
    """One reported value with a single name for humans and machines."""

    key: str
    """Canonical name: the printed label and the JSON key."""

    attribute: str
    """The :class:`~decomp_workbench.model.Comparison` attribute holding it."""

    description: str
    """One line explaining what the value means and what it is good for."""

    summary: bool = False
    """Whether the value appears on the one-line human summary."""

    width: int = 0
    """Field width used on the summary line."""

    kind: RenderKind = "text"

    @property
    def deprecated_keys(self) -> tuple[str, ...]:
        """Return JSON keys retained for compatibility with older consumers."""

        return () if self.attribute == self.key else (self.attribute,)

    def render(self, value: Any) -> str:
        """Render one value exactly as the summary line prints it."""

        if self.kind == "integer" and isinstance(value, int):
            return f"{value:{self.width}d}"
        return f"{value!s:>{self.width}s}" if self.width else str(value)


METRICS: tuple[Metric, ...] = (
    Metric(
        "verdict",
        "verdict",
        "mechanism class that explains the residual",
        summary=True,
    ),
    Metric(
        "aligned_total",
        "aligned_total",
        "LCS-aligned differing rows a source change controls; the ranking "
        "metric, and the sum of the aligned_* class counts below",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "words",
        "word_mismatches",
        "positional word differences after masking known linker-controlled "
        "fields; the function-level matching oracle, and the tiebreaker "
        "between two candidates of the same aligned shape",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "aligned_structural",
        "aligned_structural",
        "aligned rows with an opcode or operand shape difference",
    ),
    Metric(
        "aligned_schedule",
        "aligned_schedule",
        "aligned rows in a pure reordering hunk",
    ),
    Metric(
        "aligned_register",
        "aligned_register",
        "aligned rows differing only in register allocation",
    ),
    Metric(
        "aligned_constant",
        "aligned_constant",
        "aligned rows differing only in an immediate",
    ),
    Metric(
        "aligned_commutative",
        "aligned_commutative",
        "aligned rows with a swapped commutative operand pair",
    ),
    Metric(
        "raw",
        "raw_word_mismatches",
        "positional 32-bit word differences before masking; literal identity "
        "evidence, not a matching score",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "opcodes",
        "opcode_mismatches",
        "positional mnemonic differences; the honest signal that two objects "
        "have different instruction shapes and their aligned rows count "
        "different things",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "gaps",
        "aligned_gaps",
        "aligned rows the aligner filled on one side only; any gap makes "
        "aligned_total incomparable with another candidate's",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "norm",
        "normalized_distance",
        "edit distance after masking addresses, immediates, and stack "
        "offsets; search guidance only",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "regs",
        "register_mismatches",
        "positional register-operand differences",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "fp",
        "fp_register_mismatches",
        "positional differences involving $fN registers",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "insns",
        "candidate_instructions",
        "instructions compared in the candidate function",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "frame",
        "candidate_frame_size",
        "first addiu sp,sp,N adjustment in the candidate",
        summary=True,
        width=5,
    ),
    Metric(
        "sha1",
        "candidate_sha1",
        "short hash of the candidate's compared instruction words",
        summary=True,
    ),
    Metric(
        "target_insns",
        "target_instructions",
        "instructions compared in the target function",
    ),
    Metric(
        "insn_delta",
        "instruction_delta",
        "candidate instruction count minus target instruction count",
    ),
    Metric(
        "target_true_insns",
        "target_true_instructions",
        "target's real instruction count, blind to .text's 16-byte padding; "
        "what `objdump -d obj.o | grep -c` measures by hand",
    ),
    Metric(
        "candidate_true_insns",
        "candidate_true_instructions",
        "candidate's real instruction count, blind to .text's 16-byte padding",
    ),
    Metric(
        "true_insn_delta",
        "true_instruction_delta",
        "candidate_true_instructions minus target_true_instructions; the "
        "padding-safe instruction_delta -- can differ from insn_delta when "
        "the padded counts agree but the real lengths do not",
    ),
    Metric(
        "insn_count_verified",
        "instruction_count_verified",
        "whether both true instruction counts were read from the objects' "
        "own ELF .text sections rather than derived from disassembly text",
    ),
    Metric(
        "aligned_insertions",
        "aligned_insertions",
        "aligned rows present only in the candidate",
    ),
    Metric(
        "aligned_deletions",
        "aligned_deletions",
        "aligned rows present only in the target",
    ),
    Metric(
        "alignment_comparable",
        "alignment_comparable",
        "whether aligned_total may be compared with another candidate's; "
        "false once the aligner inserted gaps or the opcode streams diverged",
    ),
    Metric(
        "alignment_caution",
        "alignment_caution",
        "the one-line caution printed when aligned counts are not comparable "
        "across candidates, or null",
    ),
    Metric(
        "pool_resolution",
        "pool_resolution",
        "how literal-pool accesses were resolved before classing: absolute, "
        "anchor-correspondence, unresolved, or null",
    ),
    Metric(
        "pool_matches",
        "pool_matches",
        "aligned rows reading the same pool slot through a differently named "
        "anchor; not counted as differences",
    ),
    Metric(
        "pool_layout_mismatches",
        "pool_layout_mismatches",
        "aligned rows whose pool accesses resolve to different slots or widths",
    ),
    Metric(
        "target_pool_slots",
        "target_pool_slots",
        "distinct literal-pool slots the target references",
    ),
    Metric(
        "candidate_pool_slots",
        "candidate_pool_slots",
        "distinct literal-pool slots the candidate references",
    ),
    Metric(
        "relocs",
        "relocation_metadata_mismatches",
        "positional relocation-kind differences; prevents an exact verdict",
    ),
    Metric(
        "relocation_targets",
        "relocation_target_mismatches",
        "positional relocation symbol/addend differences; required by the "
        "local decomp.me score proxy but not by linked-function exactness",
    ),
    Metric(
        "unknown_relocations",
        "unknown_relocations",
        "relocation kinds without a precise field mask; prevents an exact "
        "verdict rather than guessing",
    ),
    Metric(
        "target_frame",
        "target_frame_size",
        "first addiu sp,sp,N adjustment in the target",
    ),
    Metric(
        "target_frame_layout",
        "target_frame_layout",
        "observed target save slots and the remaining non-save frame bytes",
    ),
    Metric(
        "candidate_frame_layout",
        "candidate_frame_layout",
        "observed candidate save slots and the remaining non-save frame bytes",
    ),
    Metric(
        "sha256",
        "candidate_sha256",
        "full hash of the candidate's compared instruction words; the "
        "object-basin identity",
    ),
    Metric(
        "exact",
        "exact",
        "masked words and relocation-kind layout agree for this function",
    ),
    Metric(
        "structural_exact",
        "structural_exact",
        "opcode sequence, normalized shape, registers, frame, and count "
        "agree; cross-ROM/lineage evidence only",
    ),
    Metric(
        "diff_sites",
        "diff_sites",
        "every differing site with its class; never filtered by the verdict",
    ),
    Metric(
        "diff_site_classes",
        "diff_site_classes",
        "count of differing sites per class",
    ),
    Metric(
        "aligned_diff_sites",
        "aligned_diff_sites",
        "LCS-aligned residual sites anchored to target instruction indices",
    ),
    Metric(
        "commutative_findings",
        "commutative_findings",
        "commutative operand pairs with the source edit each one names, "
        "including the pairs whose arithmetic row matches and whose two "
        "operand loads are crossed one row earlier",
    ),
    Metric(
        "raw_difference_breakdown",
        "raw_difference_breakdown",
        "why literal words differ: instruction bits, relocation layout, or "
        "relocation-controlled fields",
    ),
    Metric(
        "register_mismatch_ranges",
        "register_mismatch_ranges",
        "inclusive index ranges of register-operand differences",
    ),
    Metric(
        "fp_mismatch_ranges",
        "fp_mismatch_ranges",
        "inclusive index ranges of $fN operand differences",
    ),
    Metric(
        "register_diff",
        "register_diff",
        "register-differing sites only; a subset of diff_sites",
    ),
    Metric(
        "candidate_fp_register_uses",
        "candidate_fp_register_uses",
        "histogram of candidate $fN operands",
    ),
    Metric(
        "candidate_stack_offsets",
        "candidate_stack_offsets",
        "histogram of candidate N(sp) operands; spill and local-home evidence",
    ),
    Metric("guidance", "guidance", "the next useful action for this verdict"),
    Metric(
        "warnings",
        "warnings",
        "conditions that make this verdict answer a different question",
    ),
    Metric("symbol", "symbol", "selected function, or null for a whole section"),
    Metric("target", "target", "reference object or dump"),
    Metric("candidate", "candidate", "candidate object, dump, or source path"),
    Metric("error", "error", "why this comparison could not be produced"),
)

# Campaign-level report keys. They describe a run rather than one comparison,
# so they are listed separately, but `--explain-keys` must still explain every
# key a campaign emits.
CAMPAIGN_METRICS: tuple[Metric, ...] = (
    Metric("schema", "schema", "report schema identity"),
    Metric(
        "unique_candidates",
        "unique_candidates",
        "candidates that were compiled and compared in this run",
    ),
    Metric(
        "prepared_candidates",
        "prepared_candidates",
        "candidates resolved and deduplicated before the run started",
    ),
    Metric(
        "source_files",
        "source_files",
        "source paths supplied, before deduplication by cache key",
    ),
    Metric(
        "stopped_on_exact",
        "stopped_on_exact",
        "whether an exact match ended the run before every prepared candidate "
        "was submitted; candidates already running were still recorded",
    ),
    Metric(
        "timeout_seconds",
        "timeout_seconds",
        "per-candidate compiler deadline; timed-out process groups are ended",
    ),
    Metric(
        "object_basins",
        "object_basins",
        "distinct compared-function bytes, with the variants that reached each",
    ),
    Metric(
        "manifest",
        "manifest",
        "durable campaign identity and resume state, or null with --no-ledger",
    ),
    Metric(
        "ledger",
        "ledger",
        "append-only per-candidate evidence, or null with --no-ledger",
    ),
    Metric(
        "experiment",
        "experiment",
        "transformation family, parameter space, and selected-region invariant",
    ),
    Metric("results", "results", "per-candidate records, best rank first"),
)

# Aligned mechanism view keys (``view`` / ``view-dumps``). The view reports
# aligned rows rather than positional words, so it is its own vocabulary: a few
# spellings it shares with the comparison registry (``target_instructions``,
# ``candidate_frame_size``) are canonical here and deprecated there, and that is
# the point -- an aligned count and a positional count are different numbers and
# must not be read through one name. Every key here is already its own printed
# label, so none of them carries a deprecated alias.
VIEW_METRICS: tuple[Metric, ...] = (
    Metric("symbol", "symbol", "function selected from both inputs"),
    Metric("target", "target", "reference input name"),
    Metric("candidate", "candidate", "candidate input name"),
    Metric(
        "register_profile",
        "register_profile",
        "compiler era whose register class table the lanes use",
    ),
    Metric(
        "register_profile_evidence",
        "register_profile_evidence",
        "what that table is made of: a probe of a named release, or the "
        "pre-probe default carried for unmeasured ones",
    ),
    Metric(
        "target_instructions",
        "target_instructions",
        "instructions parsed from the target",
    ),
    Metric(
        "candidate_instructions",
        "candidate_instructions",
        "instructions parsed from the candidate",
    ),
    Metric("aligned_rows", "aligned_rows", "rows in the LCS alignment"),
    Metric("target_frame_size", "target_frame_size", "target stack frame adjustment"),
    Metric(
        "candidate_frame_size",
        "candidate_frame_size",
        "candidate stack frame adjustment",
    ),
    Metric("match", "match", "aligned rows whose instructions are identical"),
    Metric(
        "displacement",
        "displacement",
        "aligned rows differing only in an alignment-controlled branch offset",
    ),
    Metric(
        "structural",
        "structural",
        "aligned rows with an opcode or operand shape difference",
    ),
    Metric("schedule", "schedule", "aligned rows in a pure reordering hunk"),
    Metric(
        "register", "register", "aligned rows differing only in register allocation"
    ),
    Metric("constant", "constant", "aligned rows differing only in an immediate"),
    Metric(
        "commutative",
        "commutative",
        "aligned rows with a swapped commutative operand pair",
    ),
    Metric(
        "relocation",
        "relocation",
        "aligned rows differing only in linker-controlled fields",
    ),
    Metric(
        "pool",
        "pool",
        "aligned rows reading the same literal-pool slot through a "
        "differently named anchor",
    ),
    Metric(
        "pool_layout",
        "pool_layout",
        "aligned rows whose literal-pool accesses resolve to different slots",
    ),
    Metric(
        "pool_resolution",
        "pool_resolution",
        "how literal-pool accesses were resolved: absolute, "
        "anchor-correspondence, or unresolved",
    ),
    Metric(
        "pool_slots",
        "pool_slots",
        "distinct literal-pool slots each object references",
    ),
    Metric("verdict", "verdict", "cheapest mechanism that explains the residual"),
    Metric("playbook", "playbook", "named lever family for the verdict"),
    Metric("signature", "signature", "orthogonal modifiers attached to the verdict"),
    Metric(
        "prefix_exact",
        "prefix_exact",
        "first aligned row whose instruction words differ",
    ),
    Metric("hunks", "hunks", "contiguous runs of non-matching aligned rows"),
    Metric("lanes", "lanes", "per-class register assignment sequences"),
    Metric("webs", "webs", "consistent register substitutions, grouped"),
    Metric("next", "next", "lever guidance for the dominant class"),
    Metric(
        "warnings",
        "warnings",
        "conditions that make this verdict answer a different question",
    ),
    Metric(
        "register_report",
        "register_report",
        "per aligned row register operands, matches included",
    ),
    Metric("hunk", "hunk", "hunk number"),
    Metric("class", "class", "classification label"),
    Metric("classes", "classes", "per-class row counts inside a hunk"),
    Metric("rows", "rows", "aligned row range"),
    Metric("target_bytes", "target_bytes", "target section offsets covered"),
    Metric("candidate_bytes", "candidate_bytes", "candidate section offsets covered"),
    Metric("index", "index", "aligned row index"),
    Metric(
        "slot",
        "slot",
        "first lane position where the two sides differ",
    ),
    Metric(
        "aligned_row",
        "aligned_row",
        "aligned row holding a lane divergence; the same unit as aligned_rows",
    ),
    Metric(
        "rotation",
        "rotation",
        "cyclic offset that maps the target lane tail onto the candidate",
    ),
    Metric("slots", "slots", "lane slots rendered out of the total"),
    Metric("web", "web", "web identifier"),
    Metric("count", "count", "number of sites"),
)

# Shiftability inventory keys (``shift audit``). A third namespace, for the
# same reason the view has a second: these count *words in an image* and
# *pins in a linker script*, and a spelling shared with either registry above
# (``value``, ``reason``, ``window``, ``score``) means something else entirely
# here. Nested keys -- the fields inside `regions`, `pins`, `hits` and
# `rules` -- are listed with the rest, because a key nobody explains is the
# defect this registry exists to prevent.
SHIFT_METRICS: tuple[Metric, ...] = (
    Metric("schema", "schema", "report schema identity"),
    Metric("map", "map", "the linked `ld -Map` file the report was read from"),
    Metric("image", "image", "the linked image the map describes"),
    Metric("image_bytes", "image_bytes", "size of that image"),
    Metric(
        "window_lo",
        "window_lo",
        "first VRAM address an insertion would move; derived from the map's "
        "own lowest movable section, never hardcoded",
    ),
    Metric(
        "window_hi",
        "window_hi",
        "one past the last VRAM address an insertion would move; the end of "
        "the map's last bss section",
    ),
    Metric(
        "window_lo_section",
        "window_lo_section",
        "the output section that set the window's low bound",
    ),
    Metric(
        "window_hi_section",
        "window_hi_section",
        "the output section that set the window's high bound",
    ),
    Metric("region_count", "region_count", "regions derived from the map"),
    Metric(
        "regions",
        "regions",
        "the derived region table: one row per run of like input records, "
        "plus one per section the caller declared a blob",
    ),
    Metric(
        "scanned_words",
        "scanned_words",
        "image words read by the scan; data, blob and header regions only",
    ),
    Metric(
        "text_words",
        "text_words",
        "instruction words counted and deliberately not scanned; their "
        "address arithmetic needs `shift rehearse`, not a value test",
    ),
    Metric("text_regions", "text_regions", "text regions the map yielded"),
    Metric(
        "scan_total",
        "scan_total",
        "scanned words holding a value inside the movable window; an upper "
        "bound on the region's hardcoded-pointer suspects, not a count of them",
    ),
    Metric(
        "scan_high",
        "scan_high",
        "hits most confidently a real address reference: compiled data "
        "pointing at a symbol's start",
    ),
    Metric(
        "scan_medium",
        "scan_medium",
        "hits with one of the two elevating signals but not both",
    ),
    Metric(
        "scan_low",
        "scan_low",
        "hits a suppressor explained away, or with neither elevating signal",
    ),
    Metric("scan_rules", "scan_rules", "how many hits each rule accounted for"),
    Metric("scan_by_region", "scan_by_region", "hits per output section"),
    Metric("hits", "hits", "the ranked hit list, capped at --limit"),
    Metric("hits_shown", "hits_shown", "rows the hit list actually carries"),
    Metric(
        "rules",
        "rules",
        "the published suppressor table: every rule a hit can name, with the "
        "evidence behind it",
    ),
    Metric(
        "residence_scores",
        "residence_scores",
        "what a hit's region kind is worth when it is scored",
    ),
    Metric(
        "symbol_start_bonus",
        "symbol_start_bonus",
        "what landing exactly on a symbol's start address is worth",
    ),
    Metric("tier_thresholds", "tier_thresholds", "the score each tier needs"),
    Metric("pin_sources", "pin_sources", "the pin files read, in the order given"),
    Metric("pins_total", "pins_total", "linker assignments parsed from those files"),
    Metric(
        "pins_derived",
        "pins_derived",
        "pins whose right-hand side names a symbol: healthy by construction",
    ),
    Metric(
        "pins_authentic",
        "pins_authentic",
        "absolute pins the console or the caller's whitelist fixes: hardware "
        "registers, boot globals",
    ),
    Metric(
        "pins_artifact",
        "pins_artifact",
        "absolute pins in a window the project itself owns: bare kseg0 RAM, "
        "or the cart domain",
    ),
    Metric(
        "pins_unclassified",
        "pins_unclassified",
        "pins in no named window, or whose expression did not fold; reported "
        "rather than guessed",
    ),
    Metric("pins", "pins", "the ranked pin list, suspects first, capped at --limit"),
    Metric("pins_shown", "pins_shown", "rows the pin list actually carries"),
    Metric("limit", "limit", "the cap every detail list in this report was built with"),
    # Nested: one region row.
    Metric(
        "output_section", "output_section", "the map output section a row belongs to"
    ),
    Metric(
        "kind",
        "kind",
        "how a region's words are read: text, data, blob, header, or bss",
    ),
    Metric("vram", "vram", "run-time address"),
    Metric("size", "size", "bytes covered"),
    Metric("rom", "rom", "offset into the image"),
    Metric(
        "rom_source",
        "rom_source",
        "how that offset was derived: load-address, vma-as-rom, unplaced, or "
        "not-resident",
    ),
    Metric("words", "words", "32-bit words covered"),
    Metric("scanned", "scanned", "whether the scan read this region's words"),
    # Nested: one pin row.
    Metric("name", "name", "the symbol a pin or a rule is named by"),
    Metric("expression", "expression", "the pin's right-hand side, as written"),
    Metric(
        "form",
        "form",
        "absolute, derived, or unresolved: what the right-hand side turned out to be",
    ),
    Metric("classification", "classification", "the pin class this entry landed in"),
    Metric("value", "value", "the 32-bit value a pin holds or a word contains"),
    Metric("references", "references", "symbols a derived pin's expression names"),
    Metric("source", "source", "the file an entry was read from"),
    Metric("line", "line", "the line it was written on"),
    Metric("comment", "comment", "prose written beside the entry"),
    Metric("context", "context", "the standalone comment heading the block it sits in"),
    Metric("attributes", "attributes", "splat `key:value` attributes from the comment"),
    # Nested: one hit row.
    Metric("region", "region", "the output section a hit lives in"),
    Metric("residence", "residence", "the kind of region a hit lives in"),
    Metric(
        "resident_symbol", "resident_symbol", "the symbol a hit sits inside, or null"
    ),
    Metric("resident_offset", "resident_offset", "how far into that symbol it sits"),
    Metric("target_symbol", "target_symbol", "the symbol the hit's value points into"),
    Metric("target_offset", "target_offset", "how far past that symbol's start"),
    Metric("alignment", "alignment", "the value modulo 4; anything but 0 rules it out"),
    Metric(
        "points_at_symbol_start",
        "points_at_symbol_start",
        "whether the value lands exactly on a symbol's address",
    ),
    Metric("repeats", "repeats", "how many hits share this exact value"),
    Metric("cluster", "cluster", "arithmetic-progression family id, or null"),
    Metric(
        "window",
        "window",
        "the named address window a value falls in: cart, kseg1, kseg0, "
        "segmented, or null",
    ),
    Metric(
        "whitelisted",
        "whitelisted",
        "whether the caller declared this address authentic",
    ),
    Metric(
        "reason",
        "reason",
        "why a classification or a whitelist entry says what it says",
    ),
    Metric("score", "score", "residence plus symbol-start bonus, for a scored hit"),
    Metric("rule", "rule", "the rule that decided this hit's tier"),
    Metric("tier", "tier", "high, medium, or low address-reference confidence"),
    Metric("evidence", "evidence", "what one published rule is based on"),
    Metric("count", "count", "how many entries one tally row holds"),
    # ------------------------------------------------------------------
    # The rehearsal (``shift rehearse``). The audit reads one image and the
    # rehearsal reads two, so its vocabulary is about the *difference*: what
    # changed, what should have changed and did not, and which build step
    # wrote the words neither the compiler nor the linker did. Keys shared
    # with the audit above (``vram``, ``tier``, ``rule``, ``region``) mean the
    # same thing in both, because both read them off the same region table.
    # ------------------------------------------------------------------
    Metric("mode", "mode", "analyze (one relink pair) or orchestrate (a driver run)"),
    Metric("base_map", "base_map", "the unshifted build's `ld -Map` file"),
    Metric("base_image", "base_image", "the unshifted build's linked image"),
    Metric("shifted_map", "shifted_map", "the relinked build's `ld -Map` file"),
    Metric("shifted_image", "shifted_image", "the relinked build's linked image"),
    Metric(
        "delta",
        "delta",
        "bytes the pad inserted; also, on one movement row, how far that "
        "symbol actually moved",
    ),
    Metric("base_image_bytes", "base_image_bytes", "size of the unshifted image"),
    Metric(
        "shifted_image_bytes",
        "shifted_image_bytes",
        "size of the relinked image; it must exceed the base by exactly delta",
    ),
    Metric(
        "anchor_vram",
        "anchor_vram",
        "the VRAM the pad went in at: everything from here up moves",
    ),
    Metric(
        "anchor_rom", "anchor_rom", "that address as a ROM offset in the base image"
    ),
    Metric(
        "anchor_source",
        "anchor_source",
        "auto (derived from the two maps) or symbol (the caller named one)",
    ),
    Metric("anchor_symbol", "anchor_symbol", "a symbol placed exactly at the anchor"),
    Metric(
        "anchor_highest_unmoved",
        "anchor_highest_unmoved",
        "the highest in-window VRAM a shared symbol kept; with "
        "anchor_lowest_moved it brackets the true insertion point",
    ),
    Metric(
        "anchor_lowest_moved",
        "anchor_lowest_moved",
        "the lowest in-window VRAM a shared symbol moved delta from",
    ),
    Metric(
        "generated_spans",
        "generated_spans",
        "ROM spans a build step writes rather than the compiler: CRC header "
        "words and checksum storage, recognised before any decode or value test",
    ),
    Metric("start", "start", "first ROM offset one span covers"),
    Metric("end", "end", "one past the last ROM offset one span covers"),
    Metric("label", "label", "the class or span name a row was given"),
    Metric("total_words", "total_words", "32-bit words the pairing compared"),
    Metric(
        "differing_total",
        "differing_total",
        "paired words whose value changed; the sum of every class count",
    ),
    Metric("classes", "classes", "per-class counts for every differing word"),
    Metric(
        "unexplained_changed",
        "unexplained_changed",
        "changed words no class accounts for: the gate, and zero on a "
        "controlled relink",
    ),
    Metric(
        "unexplained_shown", "unexplained_shown", "rows the unexplained list carries"
    ),
    Metric(
        "unexplained", "unexplained", "the unexplained-word list, capped at --limit"
    ),
    Metric("offset", "offset", "ROM offset of one differing word in the base image"),
    Metric("old", "old", "the word's value in the base image"),
    Metric("new", "new", "the word's value in the relinked image"),
    Metric(
        "stale_total",
        "stale_total",
        "words that held a value inside the moved range and did not move",
    ),
    Metric(
        "stale_confirmed",
        "stale_confirmed",
        "the headline: words the audit ranked high that this relink did not "
        "move -- the strongest available evidence for a hardcoded pointer",
    ),
    Metric(
        "stale_review",
        "stale_review",
        "unmoved words at medium confidence: worth a look, not an alarm",
    ),
    Metric(
        "stale_noise",
        "stale_noise",
        "unmoved words a suppressor already explained away: the measured "
        "false-positive floor",
    ),
    Metric(
        "stale_unattributed",
        "stale_unattributed",
        "stale candidates the static scan never saw, because they sit in a "
        "region it does not scan; reported rather than absorbed",
    ),
    Metric("stale_shown", "stale_shown", "rows the stale list carries"),
    Metric("stale", "stale", "the ranked unmoved-word list, capped at --limit"),
    Metric("shifted_value", "shifted_value", "what the relinked image holds there"),
    Metric(
        "verdict",
        "verdict",
        "what the relink did to one word: moved, unmoved, or changed-other",
    ),
    Metric(
        "outcome",
        "outcome",
        "what that verdict means at that tier: tracks, stale-confirmed, "
        "stale-review, noise, or changed-other",
    ),
    Metric(
        "merge_tiers",
        "merge_tiers",
        "the published merge: what an unmoved word is called at each confidence tier",
    ),
    Metric(
        "tier_verdicts",
        "tier_verdicts",
        "the tier by movement matrix: every static hit inside the moved "
        "range, counted by what the relink did to it",
    ),
    Metric(
        "reconciled_total",
        "reconciled_total",
        "static hits judged against the relink",
    ),
    Metric("moved_total", "moved_total", "of those, the ones that moved by delta"),
    Metric("unmoved_total", "unmoved_total", "of those, the ones that did not move"),
    Metric(
        "changed_other_total",
        "changed_other_total",
        "of those, the ones that changed by something other than delta",
    ),
    Metric("movement_shared", "movement_shared", "symbols both maps define"),
    Metric(
        "movement_anomaly_total",
        "movement_anomaly_total",
        "shared symbols that moved by neither 0 nor delta; a rigid layout has none",
    ),
    Metric(
        "movement_anomaly_shown",
        "movement_anomaly_shown",
        "rows the movement-anomaly list carries",
    ),
    Metric("movement", "movement", "the movement-anomaly list, capped at --limit"),
    Metric(
        "movement_only_in_base",
        "movement_only_in_base",
        "symbols the base map defines and the relink lost",
    ),
    Metric(
        "movement_only_in_shifted",
        "movement_only_in_shifted",
        "symbols the relink gained",
    ),
    Metric("base_address", "base_address", "one symbol's address in the base map"),
    Metric(
        "shifted_address",
        "shifted_address",
        "the same symbol's address after the relink",
    ),
    Metric("checksum_total", "checksum_total", "FUNCTION=VARIABLE pairs checked"),
    Metric("checksum_pass", "checksum_pass", "pairs the consistency rule held for"),
    Metric(
        "checksum_findings",
        "checksum_findings",
        "pairs that did not hold, or could not be resolved",
    ),
    Metric("checksums", "checksums", "one row per checked pair, always all of them"),
    Metric(
        "checksum_rules",
        "checksum_rules",
        "the published outcome table for the checksum-consistency rule",
    ),
    Metric("function", "function", "the checksum-protected function"),
    Metric("variable", "variable", "the variable its byte-sum is patched into"),
    Metric("function_vram", "function_vram", "where that function starts"),
    Metric("function_rom", "function_rom", "that start as a ROM offset"),
    Metric(
        "function_size",
        "function_size",
        "bytes to the next symbol the map places: the same extent the "
        "project's own post-link patcher derives",
    ),
    Metric("body_words", "body_words", "words compared inside that extent"),
    Metric("body_changed", "body_changed", "how many of them the relink changed"),
    Metric("variable_rom", "variable_rom", "the checksum word's ROM offset"),
    Metric("variable_base", "variable_base", "its value in the base image"),
    Metric("variable_shifted", "variable_shifted", "its value in the relinked image"),
    Metric("variable_changed", "variable_changed", "whether the two differ"),
    Metric(
        "status",
        "status",
        "pass, checksum-stale, checksum-orphan, or unresolved",
    ),
    Metric(
        "basis",
        "basis",
        "why a pair passed: inert (nothing changed) or tracked (both did)",
    ),
    Metric("note", "note", "why a pair could not be resolved, when it could not"),
    Metric(
        "findings",
        "findings",
        "unexplained words plus confirmed stale words plus movement "
        "anomalies plus checksum findings",
    ),
    Metric("wrapper", "wrapper", "the relink script the driver invoked"),
    Metric("ld_script", "ld_script", "the linker script a run was linked with"),
    Metric(
        "anchor_object",
        "anchor_object",
        "the object path the pad line was inserted after",
    ),
    Metric("workdir", "workdir", "where the driver wrote scripts and build outputs"),
    Metric(
        "image_name",
        "image_name",
        "the file name the wrapper must leave the image under",
    ),
    Metric(
        "map_name", "map_name", "the file name the wrapper must leave the map under"
    ),
    Metric("deltas", "deltas", "the shift amounts the driver rehearsed"),
    Metric("runs", "runs", "one row per wrapper invocation, base first"),
    Metric("out_dir", "out_dir", "the directory one run was told to write to"),
    Metric("exit_status", "exit_status", "what the wrapper exited with"),
    Metric("analyses", "analyses", "one analyze report per delta"),
    Metric(
        "classes_agree",
        "classes_agree",
        "whether every delta reported the same counts; a shift census is a "
        "property of the layout, not of how far it moved",
    ),
    Metric("disagreements", "disagreements", "every count the deltas differed on"),
    Metric("values", "values", "that count, per delta"),
)

# Keys a command wraps around a report rather than measures. They answer
# "what did this invocation decide", not "what do these two objects look like",
# which is why they are not in the comparison registry -- but a key nobody
# explains is the defect the registry exists to prevent, so they are registered
# and ``--explain-keys`` prints them too.
COMMAND_METRICS: tuple[Metric, ...] = (
    Metric(
        "accepted",
        "accepted",
        "whether this invocation satisfies --fail-on-mismatch",
    ),
    Metric(
        "acceptance_basis",
        "acceptance_basis",
        "function-exact, cross-rom-structural, or the local scratch-score "
        "proxy result: why the command accepted or rejected the comparison",
    ),
    Metric(
        "decomp_me_score_proxy_exact",
        "decomp_me_score_proxy_exact",
        "whether pre-link instruction words, relocation targets, and known "
        "relocation layout agree; a local proxy, not a site result",
    ),
    Metric(
        "raw_instruction_words_exact",
        "raw_instruction_words_exact",
        "whether every compared pre-link instruction word agrees",
    ),
    Metric(
        "relocation_targets_exact",
        "relocation_targets_exact",
        "whether relocation kind and symbol/addend targets agree positionally",
    ),
    Metric(
        "linked_function_exact",
        "linked_function_exact",
        "whether relocation-normalized function instructions and known "
        "relocation layout agree",
    ),
    Metric(
        "census",
        "census",
        "--census predicate results; exit 3 when any of them fails, which is "
        "distinct from the exit 1 of --fail-on-mismatch",
    ),
    Metric("key", "key", "the metric one census predicate asked about"),
    Metric("expected", "expected", "the value a census predicate was written with"),
    Metric("actual", "actual", "the value the report carried for that key"),
    Metric("pass", "pass", "whether one census predicate held"),
)

METRICS_BY_KEY: dict[str, Metric] = {
    item.key: item for item in (*METRICS, *CAMPAIGN_METRICS)
}
#: The view report is a separate namespace, so it gets a separate lookup: the
#: two registries share spellings that mean different numbers.
VIEW_METRICS_BY_KEY: dict[str, Metric] = {item.key: item for item in VIEW_METRICS}
SUMMARY_METRICS: tuple[Metric, ...] = tuple(item for item in METRICS if item.summary)
DEPRECATED_KEYS: dict[str, str] = {
    alias: item.key for item in METRICS for alias in item.deprecated_keys
}
#: Spellings ``--census`` accepts on a comparison, mapped to the report key
#: each one reads. The deprecated aliases are accepted for as long as the JSON
#: still emits them: a predicate should not stop working one release before the
#: key it names does.
COMPARISON_CENSUS_KEYS: dict[str, str] = {
    **{item.key: item.key for item in METRICS},
    **DEPRECATED_KEYS,
}
#: Spellings ``--census`` accepts on the aligned view. The view has no
#: compatibility spellings, so its keys are exactly its own.
VIEW_CENSUS_KEYS: dict[str, str] = {item.key: item.key for item in VIEW_METRICS}
#: The shift registry's own lookup and census spellings. Same rule as the
#: view's: its keys are exactly its own, and it never borrows a meaning from
#: the comparison namespace.
SHIFT_METRICS_BY_KEY: dict[str, Metric] = {item.key: item for item in SHIFT_METRICS}
SHIFT_CENSUS_KEYS: dict[str, str] = {item.key: item.key for item in SHIFT_METRICS}


def summary_line(item: Any) -> str:
    """Render the one-line human summary from the registry."""

    fields = " ".join(
        f"{metric.key}={metric.render(getattr(item, metric.attribute))}"
        for metric in SUMMARY_METRICS
    )
    return f"{fields} {item.candidate}"


def canonical_fields(item: Any) -> dict[str, Any]:
    """Return the canonical JSON keys whose spelling changed."""

    return {
        metric.key: getattr(item, metric.attribute)
        for metric in METRICS
        if metric.deprecated_keys
    }


def selected_fields(item: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Return canonical and deprecated JSON keys for selected metrics."""

    payload: dict[str, Any] = {}
    for key in keys:
        metric = METRICS_BY_KEY[key]
        value = getattr(item, metric.attribute)
        payload[metric.key] = value
        for alias in metric.deprecated_keys:
            payload[alias] = value
    return payload


EXPLAIN_WIDTH = 88


def explain_keys_text() -> str:
    """Return the printed registry: label, JSON key, and meaning."""

    header = (
        "Comparison keys. The printed label and the JSON key are the same "
        "string.\n"
        "Deprecated JSON keys are still emitted beside the canonical key for "
        "one release;\n"
        "new consumers should read the canonical key. Every key is followed "
        "by its meaning.\n"
    )
    titles = ("key", "line", "deprecated json key", "")

    def describe(metrics: tuple[Metric, ...]) -> list[tuple[str, str, str, str]]:
        return [
            (
                metric.key,
                "yes" if metric.summary else "-",
                ", ".join(metric.deprecated_keys) or "-",
                metric.description,
            )
            for metric in metrics
        ]

    rows = describe(METRICS)
    campaign_rows = describe(CAMPAIGN_METRICS)
    view_rows = describe(VIEW_METRICS)
    shift_rows = describe(SHIFT_METRICS)
    command_rows = describe(COMMAND_METRICS)
    widths = [
        max(
            len(titles[column]),
            *(
                len(row[column])
                for row in rows + campaign_rows + view_rows + shift_rows + command_rows
            ),
        )
        for column in range(3)
    ]

    def format_columns(row: tuple[str, str, str, str]) -> str:
        return "  ".join(
            row[column].ljust(widths[column]) for column in range(3)
        ).rstrip()

    def format_rows(items: list[tuple[str, str, str, str]]) -> list[str]:
        lines: list[str] = []
        for row in items:
            lines.append(format_columns(row))
            lines.extend(
                textwrap.wrap(
                    row[3],
                    EXPLAIN_WIDTH,
                    initial_indent="    ",
                    subsequent_indent="    ",
                )
            )
        return lines

    separator = "  ".join("-" * width for width in widths)
    return "\n".join(
        [
            header,
            format_columns(titles),
            separator,
            *format_rows(rows),
            "",
            "Campaign report keys (campaign --json / --json-summary).",
            "",
            format_columns(titles),
            separator,
            *format_rows(campaign_rows),
            "",
            "Aligned mechanism view keys (view / view-dumps). These count "
            "aligned rows, not",
            "positional words, so a spelling shared with the comparison "
            "registry above is a",
            "different number. Nested keys (hunks, lanes, webs) are listed "
            "with the rest.",
            "",
            format_columns(titles),
            separator,
            *format_rows(view_rows),
            "",
            "Shiftability inventory keys (shift audit). A third namespace: "
            "these count words in",
            "a linked image and pins in a linker script, so a spelling shared "
            "with either registry",
            "above is a different thing. Nested keys (regions, pins, hits, "
            "rules) are listed with",
            "the rest.",
            "",
            format_columns(titles),
            separator,
            *format_rows(shift_rows),
            "",
            "Command result keys. These describe what one invocation decided "
            "rather than what",
            "the two inputs look like: acceptance, and the --census predicate "
            "results (exit 3",
            "when any predicate fails, distinct from the exit 1 of "
            "--fail-on-mismatch).",
            "",
            format_columns(titles),
            separator,
            *format_rows(command_rows),
        ]
    )
