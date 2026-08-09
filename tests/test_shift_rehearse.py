"""Tests for the differential-shift referee and its command.

Three tiers, the same shape `test_shift_audit` uses. The synthetic fixture
below is a handcrafted pair of linker maps plus a handcrafted 256-byte base
image and its relinked twin -- no bytes from any ROM -- built so that every
census class has exactly one word, every checksum-rule outcome has exactly one
pair, and every cell of the tier x moved matrix that can be populated by hand
is. The CLI tests drive the real parser and a fake build wrapper. The DKR
conformance tests replay S0's own rehearsal (`.workbench/shift-instrumentation/
s0` in the sibling `decomp_playground` checkout) and self-skip when that
checkout is absent; the maps and images are read from there and never copied
into this repository.

The fixture is parameterised by delta because the campaign's own gate is that
two independent deltas agree: S0 measured identical class counts at 0x10 and
0x40, and `orchestrate`'s cross-delta check is only meaningful if the fixture
can produce both.
"""

from __future__ import annotations

import io
import json
import os
import stat
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import ClassVar

from test_ldmap import build_elf

from decomp_workbench.cli import main
from decomp_workbench.ldmap import (
    SHN_ABS,
    LdMap,
    parse_elf_symbols,
    parse_ld_map,
    read_elf_symbols,
    read_ld_map,
)
from decomp_workbench.pins import boot_globals_whitelist, default_pin_model
from decomp_workbench.schema import (
    SHIFT_CENSUS_KEYS,
    SHIFT_METRICS_BY_KEY,
    explain_keys_text,
)
from decomp_workbench.shift_rehearse import (
    CHECKSUM_RULES,
    MERGE_TIERS,
    SHADOWING_PIN,
    SHIFT_REHEARSE_SCHEMA,
    SYMBOL_RULES,
    SYMBOL_STALE,
    Rehearsal,
    build_rehearsal,
    cross_delta_disagreements,
    derive_anchor,
    pad_ld_script,
    rehearse_lines,
    symbol_census,
    symbol_extent,
)

# --------------------------------------------------------------------------
# Synthetic fixture
# --------------------------------------------------------------------------

#: The VRAM the pad is inserted at: `entrypoint` stays put, everything from
#: `func_a` up moves. Auto-derivation has to find exactly this address.
INSERTION_VRAM = 0x80000410
INSERTION_ROM = 0x50

#: Text symbols, and whether the insertion moves them. `fn_*` are the four
#: checksum-protected functions, one per rule outcome.
TEXT_SYMBOLS: tuple[tuple[str, int], ...] = (
    ("entrypoint", 0x80000400),
    ("func_a", 0x80000410),
    ("fn_inert", 0x80000430),
    ("fn_tracked", 0x80000438),
    ("fn_stale", 0x80000440),
    ("fn_orphan", 0x80000448),
)

DATA_SYMBOLS: tuple[tuple[str, int], ...] = (
    ("gData", 0x80000460),
    ("gPointerTable", 0x80000470),
    ("gTail", 0x80000480),
    ("gLater", 0x80000490),
    ("gInertSum", 0x800004A0),
    ("gTrackedSum", 0x800004A4),
    ("gStaleSum", 0x800004A8),
    ("gOrphanSum", 0x800004AC),
)

BSS_SYMBOLS: tuple[tuple[str, int], ...] = (("main_BSS_END", 0x80000500),)

CHECKSUM_PAIRS: tuple[tuple[str, str], ...] = (
    ("fn_inert", "gInertSum"),
    ("fn_tracked", "gTrackedSum"),
    ("fn_stale", "gStaleSum"),
    ("fn_orphan", "gOrphanSum"),
)

CRC_WORDS: tuple[int, ...] = (0x10, 0x14)

BLOBS: tuple[str, ...] = (".boot",)


def render_map(delta: int, *, anomaly: str | None = None) -> str:
    """Render one linker map for a build shifted by `delta`.

    Symbols at or above `INSERTION_VRAM` move by `delta`; everything below
    stays. `anomaly`, when given, names one symbol that moves by half the
    delta instead -- the third value S0's movement audit proved never occurs,
    and which this command reports rather than raises on.
    """

    def placed(name: str, address: int) -> int:
        if address < INSERTION_VRAM:
            return address
        if name == anomaly:
            return address + delta // 2
        return address + delta

    lines = [
        "",
        "Linker script and memory map",
        "",
        ".header         0x00000000       0x20",
        " .data          0x00000000       0x20 build/header.o",
        "",
        ".boot           0x00000020       0x20",
        " .data          0x00000020       0x20 build/boot.o",
        "",
        f".main           0x80000400       0x{0xC0 + delta:x} load address 0x00000040",
        f" .text          0x80000400       0x{0x60 + delta:x} build/entry.o",
    ]
    for name, address in TEXT_SYMBOLS:
        lines.append(
            f"                0x{placed(name, address):08x}                {name}"
        )
    lines.append(f" .data          0x{0x80000460 + delta:08x}       0x60 build/code.o")
    for name, address in DATA_SYMBOLS:
        lines.append(
            f"                0x{placed(name, address):08x}                {name}"
        )
    lines.extend(
        (
            "",
            f".main_bss       0x{0x800004C0 + delta:08x}       0x40",
            f" .bss           0x{0x800004C0 + delta:08x}       0x40 build/code.o",
        )
    )
    for name, address in BSS_SYMBOLS:
        lines.append(
            f"                0x{placed(name, address):08x}                {name}"
        )
    lines.append("")
    return "\n".join(lines)


def base_words() -> list[int]:
    """The 64 words of the base image, laid out by ROM offset."""

    words = [0x00000000] * 64

    def put(offset: int, value: int) -> None:
        words[offset // 4] = value

    # .header
    put(0x00, 0x80371240)
    put(0x04, 0x0000000F)
    put(0x10, 0xA1B2C3D4)  # CRC word 1
    put(0x14, 0xE5F60718)  # CRC word 2
    put(0x18, 0x80000460)  # relocated header reference: tracks, high tier
    # .boot (an opaque blob)
    put(0x20, 0x80000474)  # in-window, mid-symbol, blob: low tier, never moves
    put(0x24, 0x80000470)  # in-window, symbol start, blob: medium, never moves
    # .main .text
    put(0x40, 0x3C088000)
    put(0x44, 0x24080010)
    put(0x48, 0x0C000104)  # jal func_a, below the insertion
    # -- insertion point, ROM 0x50 --
    put(0x50, 0x3C088000)  # lui %hi(gData): unchanged either side of the shift
    put(0x54, 0x25080460)  # addiu %lo(gData)
    put(0x58, 0x3C018000)  # lui whose %hi carries across the shift
    put(0x5C, 0x8C22FFF0)  # lw whose %lo wraps the sign boundary
    put(0x60, 0x11223344)  # explained by nothing
    put(0x78, 0x0C000110)  # fn_tracked's body: jal fn_stale
    put(0x80, 0x0C000104)  # fn_stale's body: jal func_a
    # .main .data
    put(0xA0, 0x80000470)  # pointer at a symbol start: high tier, tracks
    put(0xA4, 0x80000474)  # mid-symbol pointer that does not move
    put(0xA8, 0x80000490)  # symbol-start pointer that does not move
    put(0xB0, 0x80000480)  # pointer at a symbol start: high tier, tracks
    put(0xE0, 0x00001111)  # gInertSum
    put(0xE4, 0x00002222)  # gTrackedSum
    put(0xE8, 0x00003333)  # gStaleSum
    put(0xEC, 0x00004444)  # gOrphanSum
    return words


def shifted_words(delta: int, *, extra_unexplained: bool = False) -> list[int]:
    """The relinked image's words, before the pad is spliced in."""

    words = base_words()

    def put(offset: int, value: int) -> None:
        words[offset // 4] = value

    put(0x10, 0x11223344)  # the CRC is recomputed post-link
    put(0x14, 0x55667788)
    put(0x18, 0x80000460 + delta)
    put(0x48, 0x0C000104 + delta // 4)
    put(0x54, 0x25080460 + delta)
    put(0x58, 0x3C018001)
    put(0x5C, 0x8C220000 | ((0xFFF0 + delta) & 0xFFFF))
    put(0x60, 0x55667788)
    put(0x78, 0x0C000110 + delta // 4)
    put(0x80, 0x0C000104 + delta // 4)
    put(0xA0, 0x80000470 + delta)
    put(0xB0, 0x80000480 + delta)
    put(0xE4, 0x00002233)  # the patcher rewrote fn_tracked's checksum
    put(0xEC, 0x00004455)  # ... and gOrphanSum, whose function never changed
    if extra_unexplained:
        put(0x64, 0xDEADBEEF)
    return words


def pack(words: list[int]) -> bytes:
    return b"".join(struct.pack(">I", word) for word in words)


def base_image() -> bytes:
    return pack(base_words())


def shifted_image(delta: int, *, extra_unexplained: bool = False) -> bytes:
    """The base image with `delta` pad bytes spliced in at the insertion."""

    words = shifted_words(delta, extra_unexplained=extra_unexplained)
    split = INSERTION_ROM // 4
    padded = words[:split] + [0x00000000] * (delta // 4) + words[split:]
    return pack(padded)


def base_map() -> LdMap:
    return parse_ld_map(render_map(0), path="base.map")


def shifted_map(delta: int, *, anomaly: str | None = None) -> LdMap:
    return parse_ld_map(render_map(delta, anomaly=anomaly), path="shifted.map")


def rehearse(
    delta: int = 0x10,
    *,
    anchor: str | None = None,
    anomaly: str | None = None,
    extra_unexplained: bool = False,
    checksum_pairs: tuple[tuple[str, str], ...] = CHECKSUM_PAIRS,
    crc_words: tuple[int, ...] = CRC_WORDS,
) -> Rehearsal:
    return build_rehearsal(
        base_ldmap=base_map(),
        base_image=base_image(),
        shifted_ldmap=shifted_map(delta, anomaly=anomaly),
        shifted_image=shifted_image(delta, extra_unexplained=extra_unexplained),
        delta=delta,
        anchor=anchor,
        blobs=BLOBS,
        crc_words=crc_words,
        checksum_pairs=checksum_pairs,
        model=default_pin_model(),
        base_map_path="base.map",
        base_image_path="base.z64",
        shifted_map_path="shifted.map",
        shifted_image_path="shifted.z64",
    )


def status_for(found: Rehearsal, function: str) -> str:
    return next(item.status for item in found.checksums if item.function == function)


# --------------------------------------------------------------------------
# WB-140 rule C -- shared with `shift audit` via `build_region_table`
# --------------------------------------------------------------------------


class BlobNameValidationTests(unittest.TestCase):
    """`build_rehearsal` derives its region table through the same
    `build_region_table` `shift audit` does (see `shift_rehearse.
    build_rehearsal`'s own docstring: "the region table ... come[s] from the
    *base* map (`shift_audit`'s derivation, reused rather than re-derived")
    -- so WB-140 rule C's blob-name check, added to that one shared
    function, covers `shift rehearse --blob` for free. This confirms it
    does rather than assuming it."""

    def test_a_real_blob_name_is_accepted(self) -> None:
        rehearse()  # BLOBS = (".boot",), a real section in `render_map`

    def test_a_typo_d_blob_name_is_refused_before_any_census_runs(self) -> None:
        with self.assertRaises(ValueError) as raised:
            build_rehearsal(
                base_ldmap=base_map(),
                base_image=base_image(),
                shifted_ldmap=shifted_map(0x10),
                shifted_image=shifted_image(0x10),
                delta=0x10,
                blobs=(".boot1",),
                model=default_pin_model(),
            )
        message = str(raised.exception)
        self.assertIn(
            "--blob names a section this map does not have: .boot1", message
        )


# --------------------------------------------------------------------------
# Anchor derivation
# --------------------------------------------------------------------------


class AnchorTests(unittest.TestCase):
    """Where the pad went in, derived rather than typed."""

    def test_auto_derivation_finds_the_lowest_moved_symbol(self) -> None:
        found = rehearse()
        self.assertEqual(found.anchor.vram, INSERTION_VRAM)
        self.assertEqual(found.anchor.rom, INSERTION_ROM)
        self.assertEqual(found.anchor.source, "auto")
        self.assertEqual(found.anchor.symbol, "func_a")

    def test_auto_derivation_reports_the_boundary_it_straddles(self) -> None:
        """Both sides of the boundary travel, so a reader can see the gap."""

        anchor = rehearse().anchor
        self.assertEqual(anchor.highest_unmoved, 0x80000400)
        self.assertEqual(anchor.lowest_moved, INSERTION_VRAM)

    def test_a_named_symbol_overrides_the_derivation(self) -> None:
        found = rehearse(anchor="func_a")
        self.assertEqual(found.anchor.source, "symbol")
        self.assertEqual(found.anchor.vram, INSERTION_VRAM)

    def test_a_named_symbol_that_is_not_in_the_map_is_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            rehearse(anchor="nope")
        self.assertIn("nope", str(raised.exception))

    def test_size_symbols_outside_the_window_never_become_the_anchor(self) -> None:
        """`main_TEXT_SIZE` grows by delta too, and is not an address.

        DKR's cascade script assigns a dozen ABSOLUTE size symbols that move
        by exactly delta while living nowhere near VRAM. Deriving the anchor
        from the raw symbol stream picks one of those; deriving it inside the
        map's own movable window picks the insertion point.
        """

        base = parse_ld_map(
            render_map(0) + "                0x000d08e0                main_TEXT_SIZE\n"
        )
        shifted = parse_ld_map(
            render_map(0x10)
            + "                0x000d08f0                main_TEXT_SIZE\n"
        )
        anchor = derive_anchor(
            base,
            shifted,
            delta=0x10,
            window_lo=0x80000400,
            window_hi=0x80000500,
        )
        self.assertEqual(anchor.vram, INSERTION_VRAM)

    def test_a_delta_no_symbol_moved_by_is_refused_with_the_evidence(self) -> None:
        with self.assertRaises(ValueError) as raised:
            derive_anchor(
                base_map(),
                shifted_map(0x10),
                delta=0x20,
                window_lo=0x80000400,
                window_hi=0x80000500,
            )
        self.assertIn("0x20", str(raised.exception))


# --------------------------------------------------------------------------
# Movement audit
# --------------------------------------------------------------------------


class MovementTests(unittest.TestCase):
    """Every shared symbol moves 0 or delta -- and a third value is evidence."""

    def test_a_clean_relink_reports_no_anomaly(self) -> None:
        found = rehearse()
        self.assertEqual(found.movement_anomalies, ())
        self.assertEqual(found.movement.only_in_base, ())
        self.assertEqual(found.movement.only_in_shifted, ())

    def test_a_symbol_that_moved_by_a_third_value_is_a_finding(self) -> None:
        found = rehearse(anomaly="gTail")
        names = [item.name for item in found.movement_anomalies]
        self.assertEqual(names, ["gTail"])
        self.assertEqual(found.movement_anomalies[0].delta, 0x8)

    def test_an_anomaly_is_reported_and_does_not_stop_the_census(self) -> None:
        found = rehearse(anomaly="gTail")
        self.assertEqual(found.census.differing_total, 14)
        self.assertGreaterEqual(found.findings, 1)


# --------------------------------------------------------------------------
# Census classes
# --------------------------------------------------------------------------


class CensusClassTests(unittest.TestCase):
    """One word per class, so the totals are readable by hand."""

    def setUp(self) -> None:
        self.found = rehearse()

    def test_every_class_the_fixture_was_built_for_is_populated(self) -> None:
        self.assertEqual(
            self.found.census.counts,
            {
                "abs32-tracks": 3,
                "checksum-gen": 2,
                "crc-header": 2,
                "hi16-adjust": 1,
                "j26-tracks": 3,
                "lo16-tracks": 2,
                "unexplained": 1,
            },
        )

    def test_the_headline_counts_the_one_unexplained_word(self) -> None:
        self.assertEqual(self.found.unexplained_changed, 1)
        self.assertEqual(self.found.census.unexplained[0].offset, 0x60)

    def test_the_totals_add_up(self) -> None:
        census = self.found.census
        self.assertEqual(census.differing_total, sum(census.counts.values()))
        self.assertEqual(census.total_words, 64)

    def test_the_generated_spans_are_published_with_the_report(self) -> None:
        labels = {item.label for item in self.found.generated}
        self.assertEqual(labels, {"crc-header", "checksum-gen"})
        starts = sorted(item.start for item in self.found.generated)
        self.assertEqual(starts, [0x10, 0x14, 0xE0, 0xE4, 0xE8, 0xEC])

    def test_the_second_delta_agrees_word_class_for_word_class(self) -> None:
        """S0's rigidity proof: identical class counts at 0x10 and 0x40."""

        self.assertEqual(rehearse(0x40).census.counts, self.found.census.counts)


# --------------------------------------------------------------------------
# The stale merge
# --------------------------------------------------------------------------


class StaleMergeTests(unittest.TestCase):
    """Static confidence x empirical movement: the tier x moved matrix."""

    def setUp(self) -> None:
        self.found = rehearse()

    def test_the_matrix_partitions_every_reconciled_hit(self) -> None:
        self.assertEqual(
            self.found.tier_verdicts,
            {
                "high": {"moved": 3, "unmoved": 1, "changed-other": 0},
                "medium": {"moved": 0, "unmoved": 2, "changed-other": 0},
                "low": {"moved": 0, "unmoved": 1, "changed-other": 0},
            },
        )
        self.assertEqual(self.found.reconciled_total, 7)

    def test_a_high_confidence_word_that_did_not_move_is_the_headline(self) -> None:
        self.assertEqual(self.found.stale_confirmed, 1)
        confirmed = [
            item
            for item in self.found.reconciliation
            if item.outcome == "stale-confirmed"
        ]
        self.assertEqual([item.rom for item in confirmed], [0xA8])
        self.assertEqual(confirmed[0].target_symbol, "gLater")

    def test_low_confidence_unmoved_words_are_counted_as_noise(self) -> None:
        self.assertEqual(self.found.stale_noise, 1)
        self.assertEqual(self.found.stale_review, 2)

    def test_a_word_that_moved_is_never_a_stale_finding(self) -> None:
        moved = [item for item in self.found.reconciliation if item.verdict == "moved"]
        self.assertEqual(sorted(item.rom for item in moved), [0x18, 0xA0, 0xB0])
        self.assertEqual({item.outcome for item in moved}, {"tracks"})

    def test_the_census_stale_total_reconciles_with_the_audit(self) -> None:
        """Every stale candidate is attributed, or the shortfall is printed."""

        self.assertEqual(self.found.census.stale_total, 4)
        self.assertEqual(self.found.unmoved_total, 4)
        self.assertEqual(self.found.stale_unattributed, 0)

    def test_the_merge_table_travels_with_the_report(self) -> None:
        self.assertEqual(MERGE_TIERS["high"], "stale-confirmed")
        self.assertEqual(MERGE_TIERS["low"], "noise")
        payload = self.found.as_dict(limit=4)
        self.assertEqual(payload["merge_tiers"], dict(MERGE_TIERS))


# --------------------------------------------------------------------------
# The checksum-consistency rule
# --------------------------------------------------------------------------


class ChecksumRuleTests(unittest.TestCase):
    """The cursed-audio rule: a changed body demands a changed checksum."""

    def setUp(self) -> None:
        self.found = rehearse()

    def test_a_function_no_shift_touched_passes_without_a_finding(self) -> None:
        verdict = next(
            item for item in self.found.checksums if item.function == "fn_inert"
        )
        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.basis, "inert")
        self.assertEqual(verdict.body_changed, 0)
        self.assertFalse(verdict.variable_changed)

    def test_a_repatched_checksum_passes_and_says_why(self) -> None:
        verdict = next(
            item for item in self.found.checksums if item.function == "fn_tracked"
        )
        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.basis, "tracked")
        self.assertEqual(verdict.body_changed, 1)
        self.assertTrue(verdict.variable_changed)

    def test_a_changed_body_with_a_frozen_checksum_is_the_2021_bug(self) -> None:
        verdict = next(
            item for item in self.found.checksums if item.function == "fn_stale"
        )
        self.assertEqual(verdict.status, "checksum-stale")
        self.assertEqual(verdict.body_changed, 1)
        self.assertFalse(verdict.variable_changed)

    def test_a_changed_checksum_over_an_untouched_body_is_reported(self) -> None:
        verdict = next(
            item for item in self.found.checksums if item.function == "fn_orphan"
        )
        self.assertEqual(verdict.status, "checksum-orphan")
        self.assertEqual(verdict.body_changed, 0)
        self.assertTrue(verdict.variable_changed)

    def test_every_pair_reports_a_status_rather_than_staying_silent(self) -> None:
        self.assertEqual(len(self.found.checksums), 4)
        self.assertEqual(self.found.checksum_pass, 2)
        self.assertEqual(self.found.checksum_findings, 2)

    def test_a_pair_naming_an_absent_symbol_is_unresolved_not_a_crash(self) -> None:
        found = rehearse(checksum_pairs=(("nope", "gInertSum"), ("fn_inert", "nope2")))
        self.assertEqual([item.status for item in found.checksums], ["unresolved"] * 2)
        self.assertIn("nope", found.checksums[0].note or "")

    def test_the_extent_is_the_next_symbol_the_map_places(self) -> None:
        """The same approximation DKR's own post-link patcher makes.

        `calc_func_checksums.py` derives a function's length from the map by
        subtracting its address from the next label's; a linker map carries no
        symbol sizes, so there is no better answer available to either of us.
        """

        self.assertEqual(
            symbol_extent(base_map(), "fn_stale"), (0x80000440, 0x80000448)
        )
        self.assertEqual(
            symbol_extent(base_map(), "fn_orphan"), (0x80000448, 0x80000460)
        )
        self.assertIsNone(symbol_extent(base_map(), "absent"))

    def test_the_rules_are_data_and_name_every_status_a_pair_can_carry(self) -> None:
        published = {item.name for item in CHECKSUM_RULES}
        self.assertEqual(
            published, {"pass", "checksum-stale", "checksum-orphan", "unresolved"}
        )
        for item in CHECKSUM_RULES:
            self.assertTrue(item.evidence)


# --------------------------------------------------------------------------
# Report shape
# --------------------------------------------------------------------------


class ReportShapeTests(unittest.TestCase):
    """The JSON contract, and the human report the same numbers render to."""

    def setUp(self) -> None:
        self.found = rehearse()
        self.payload = self.found.as_dict(limit=3)

    def test_the_headline_pair_is_two_top_level_scalars(self) -> None:
        self.assertEqual(self.payload["unexplained_changed"], 1)
        self.assertEqual(self.payload["stale_confirmed"], 1)

    def test_the_census_keys_are_top_level_scalars(self) -> None:
        for key in (
            "delta",
            "anchor_vram",
            "anchor_rom",
            "total_words",
            "differing_total",
            "unexplained_changed",
            "stale_total",
            "stale_confirmed",
            "stale_review",
            "stale_noise",
            "movement_shared",
            "movement_anomaly_total",
            "checksum_total",
            "checksum_pass",
            "checksum_findings",
            "findings",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.payload)
                self.assertIsInstance(self.payload[key], int)

    def test_the_detail_lists_name_their_own_cap(self) -> None:
        self.assertEqual(self.payload["limit"], 3)
        self.assertEqual(self.payload["stale_shown"], 3)
        self.assertEqual(len(self.payload["stale"]), 3)

    def test_the_stale_list_is_ranked_before_it_is_capped(self) -> None:
        tiers = [item["tier"] for item in self.payload["stale"]]
        self.assertEqual(tiers[0], "high")

    def test_the_payload_is_plain_json_and_stable(self) -> None:
        json.dumps(self.payload)
        self.assertEqual(
            json.dumps(self.payload, sort_keys=True),
            json.dumps(rehearse().as_dict(limit=3), sort_keys=True),
        )

    def test_every_json_key_the_report_emits_is_registered(self) -> None:
        """`--explain-keys` has to reach every key, nested ones included."""

        emitted = walk_keys(self.payload) - {"schema"}
        emitted -= set(self.payload["classes"])
        emitted -= set(self.payload["merge_tiers"])
        emitted -= set(self.payload["tier_verdicts"])
        for row in self.payload["tier_verdicts"].values():
            emitted -= set(row)
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))
        text = explain_keys_text()
        for key in sorted(emitted):
            with self.subTest(key=key):
                self.assertIn(key, text)

    def test_every_printed_label_is_one_of_those_keys(self) -> None:
        registered = set(SHIFT_METRICS_BY_KEY)
        headers = (
            "name base_address shifted_address delta",
            "label count",
            "start end label",
            "function variable status basis body_words body_changed",
            "tier verdict count outcome",
            "rom value tier rule outcome region target_symbol",
            "offset old new label",
        )
        text = "\n".join(rehearse_lines(self.found, limit=8))
        for row in headers:
            for label in row.split():
                with self.subTest(label=label):
                    self.assertIn(label, registered)
            with self.subTest(row=row):
                self.assertTrue(
                    any(line.split() == row.split() for line in text.splitlines()),
                    f"no table in the report has the header {row!r}",
                )

    def test_the_human_report_prints_the_headline_and_the_caps(self) -> None:
        text = "\n".join(rehearse_lines(self.found, limit=1))
        self.assertIn("unexplained_changed=1", text)
        self.assertIn("stale_confirmed=1", text)
        self.assertIn("1 of 4", text)

    def test_the_human_report_says_what_a_tier_does_and_does_not_mean(self) -> None:
        text = "\n".join(rehearse_lines(self.found, limit=4))
        self.assertIn("checksum-stale", text)
        self.assertIn("did not move", text)

    def test_the_census_registry_is_exactly_the_shift_vocabulary(self) -> None:
        self.assertEqual(set(SHIFT_CENSUS_KEYS), set(SHIFT_METRICS_BY_KEY))


def walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in value.items():
            found.add(key)
            found |= walk_keys(item)
        return found
    if isinstance(value, list):
        return {name for item in value for name in walk_keys(item)}
    return set()


# --------------------------------------------------------------------------
# Padded linker-script generation
# --------------------------------------------------------------------------

LD_SCRIPT = """SECTIONS
{
    .main 0x80000400 : AT(main_ROM_START) SUBALIGN(16)
    {
        main_TEXT_START = .;
        build/src/hasm/entrypoint.s.o(.text);
        build/src*.o(.text);
    }
}
"""


class PaddedScriptTests(unittest.TestCase):
    """The rehearsal primitive: one line inserted after a named object."""

    def test_the_pad_lands_directly_after_the_anchor_line(self) -> None:
        padded = pad_ld_script(
            LD_SCRIPT, anchor_object="build/src/hasm/entrypoint.s.o", delta=0x10
        )
        lines = padded.text.splitlines()
        index = lines.index("        build/src/hasm/entrypoint.s.o(.text);")
        self.assertEqual(lines[index + 1], "        . += 0x10;")
        self.assertEqual(padded.line, index + 1)

    def test_the_pad_keeps_the_anchor_lines_own_indentation(self) -> None:
        padded = pad_ld_script(
            "  build/a.o(.text);\n", anchor_object="build/a.o", delta=0x40
        )
        self.assertEqual(padded.text, "  build/a.o(.text);\n  . += 0x40;\n")

    def test_an_anchor_that_matches_nothing_fails_loudly(self) -> None:
        with self.assertRaises(ValueError) as raised:
            pad_ld_script(LD_SCRIPT, anchor_object="build/absent.o", delta=0x10)
        self.assertIn("build/absent.o", str(raised.exception))
        self.assertIn("no line", str(raised.exception))

    def test_an_anchor_that_matches_twice_fails_loudly(self) -> None:
        text = LD_SCRIPT + "        build/src/hasm/entrypoint.s.o(.data);\n"
        with self.assertRaises(ValueError) as raised:
            pad_ld_script(
                text, anchor_object="build/src/hasm/entrypoint.s.o", delta=0x10
            )
        message = str(raised.exception)
        self.assertIn("2 lines", message)
        self.assertIn("6", message)


# --------------------------------------------------------------------------
# Cross-delta consistency
# --------------------------------------------------------------------------


class CrossDeltaTests(unittest.TestCase):
    """Identical class counts across deltas is the rigidity proof."""

    def test_two_agreeing_deltas_report_no_disagreement(self) -> None:
        self.assertEqual(
            cross_delta_disagreements([rehearse(0x10), rehearse(0x40)]), ()
        )

    def test_a_class_count_that_differs_is_a_finding(self) -> None:
        found = cross_delta_disagreements(
            [rehearse(0x10), rehearse(0x40, extra_unexplained=True)]
        )
        names = [item.name for item in found]
        self.assertIn("unexplained", names)
        row = next(item for item in found if item.name == "unexplained")
        self.assertEqual(row.values, {"0x10": 1, "0x40": 2})

    def test_a_headline_that_differs_is_a_finding(self) -> None:
        found = cross_delta_disagreements(
            [rehearse(0x10), rehearse(0x40, extra_unexplained=True)]
        )
        self.assertIn("unexplained_changed", [item.name for item in found])

    def test_one_delta_cannot_disagree_with_itself(self) -> None:
        self.assertEqual(cross_delta_disagreements([rehearse(0x10)]), ())


# --------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class AnalyzeCommandTests(unittest.TestCase):
    """Argument handling, exit codes, and the JSON envelope."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base_map = self.root / "base.map"
        self.base_image = self.root / "base.z64"
        self.shifted_map = self.root / "shifted.map"
        self.shifted_image = self.root / "shifted.z64"
        self.base_map.write_text(render_map(0), encoding="utf-8")
        self.base_image.write_bytes(base_image())
        self.shifted_map.write_text(render_map(0x10), encoding="utf-8")
        self.shifted_image.write_bytes(shifted_image(0x10))

    def arguments(self) -> list[str]:
        return [
            "shift",
            "rehearse",
            "analyze",
            "--base-map",
            str(self.base_map),
            "--base-image",
            str(self.base_image),
            "--shifted-map",
            str(self.shifted_map),
            "--shifted-image",
            str(self.shifted_image),
            "--delta",
            "0x10",
            "--blob",
            ".boot",
            "--crc-words",
            "0x10,0x14",
            *[
                argument
                for function, variable in CHECKSUM_PAIRS
                for argument in ("--checksum-pair", f"{function}={variable}")
            ],
        ]

    def test_the_command_runs_and_prints_the_headline(self) -> None:
        status, stdout, _ = run_cli(self.arguments())
        self.assertEqual(status, 0)
        self.assertIn("shift rehearse", stdout)
        self.assertIn("stale_confirmed=1", stdout)

    def test_json_carries_the_schema_identity(self) -> None:
        status, stdout, _ = run_cli([*self.arguments(), "--json"])
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], SHIFT_REHEARSE_SCHEMA)
        self.assertEqual(payload["mode"], "analyze")
        self.assertEqual(payload["unexplained_changed"], 1)
        self.assertEqual(payload["stale_confirmed"], 1)

    def test_the_anchor_defaults_to_auto_and_says_so(self) -> None:
        _, stdout, _ = run_cli([*self.arguments(), "--json"])
        payload = json.loads(stdout)
        self.assertEqual(payload["anchor_source"], "auto")
        self.assertEqual(payload["anchor_vram"], INSERTION_VRAM)

    def test_a_named_anchor_is_accepted(self) -> None:
        _, stdout, _ = run_cli([*self.arguments(), "--anchor", "func_a", "--json"])
        self.assertEqual(json.loads(stdout)["anchor_source"], "symbol")

    def test_a_checksum_pair_without_an_equals_sign_is_refused(self) -> None:
        status, _, stderr = run_cli([*self.arguments(), "--checksum-pair", "oops"])
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_wb_140_an_unknown_blob_name_is_refused(self) -> None:
        """`--blob` shares the same typo shape `shift audit` does, and the
        same fix: both derive their region table through the shared
        `build_region_table`."""

        arguments = [*self.arguments(), "--blob", ".nope"]
        status, _, stderr = run_cli(arguments)
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn(
            "--blob names a section this map does not have: .nope", stderr
        )

    def test_a_missing_image_is_a_usage_failure_not_a_traceback(self) -> None:
        status, _, stderr = run_cli(
            [
                *self.arguments()[:-10],
                "--shifted-image",
                str(self.root / "absent.z64"),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_a_delta_that_does_not_match_the_images_is_reported(self) -> None:
        status, _, stderr = run_cli(
            [
                *self.arguments()[:11],
                "--delta",
                "0x20",
                "--blob",
                ".boot",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_census_passes_and_fails_with_the_house_exit_codes(self) -> None:
        passing, _, _ = run_cli(
            [*self.arguments(), "--census", "unexplained_changed=1"]
        )
        self.assertEqual(passing, 0)
        failing, stdout, _ = run_cli(
            [*self.arguments(), "--census", "unexplained_changed=0"]
        )
        self.assertEqual(failing, 3)
        self.assertIn("census: FAIL", stdout)

    def test_an_unknown_census_key_is_refused_before_reading_anything(self) -> None:
        status, _, stderr = run_cli(
            [
                "shift",
                "rehearse",
                "analyze",
                "--base-map",
                "absent.map",
                "--base-image",
                "absent.z64",
                "--shifted-map",
                "absent.map",
                "--shifted-image",
                "absent.z64",
                "--delta",
                "0x10",
                "--census",
                "x=1",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("unknown census key 'x'", stderr)

    def test_explain_keys_covers_the_shift_vocabulary(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            run_cli(["shift", "rehearse", "analyze", "--explain-keys"])
        self.assertEqual(raised.exception.code, 0)

    def test_naming_no_operation_prints_the_group_listing(self) -> None:
        status, stdout, _ = run_cli(["shift", "rehearse"])
        self.assertEqual(status, 0)
        self.assertIn("analyze", stdout)
        self.assertIn("orchestrate", stdout)

    def test_the_shift_group_now_lists_rehearse(self) -> None:
        status, stdout, _ = run_cli(["shift"])
        self.assertEqual(status, 0)
        self.assertIn("rehearse", stdout)


# --------------------------------------------------------------------------
# Orchestrate
# --------------------------------------------------------------------------

#: A stand-in for a project's relink script. It reads the delta straight out
#: of the padded linker script it is handed -- exactly the one fact a real
#: wrapper does not need, but the only way a fake one can know which
#: prebuilt fixture to hand back.
FAKE_WRAPPER = """#!/usr/bin/env python3
import pathlib
import re
import shutil
import sys

script, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
match = re.search(r"\\. \\+= (0x[0-9a-fA-F]+);", script.read_text())
delta = match.group(1) if match else "base"
source = pathlib.Path(__file__).parent / "fixtures" / delta
out.mkdir(parents=True, exist_ok=True)
shutil.copy(source / "image", out / "image")
shutil.copy(source / "map", out / "map")
"""

FAILING_WRAPPER = """#!/usr/bin/env python3
import sys

sys.stderr.write("relink failed: no toolchain\\n")
raise SystemExit(3)
"""


@unittest.skipIf(os.name == "nt", "the fake wrapper is invoked by its shebang")
class OrchestrateCommandTests(unittest.TestCase):
    """The thin driver: generate, relink, analyze, compare."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixtures = self.root / "fixtures"
        self.write_fixture("base", 0, base_image())
        self.write_fixture("0x10", 0x10, shifted_image(0x10))
        self.write_fixture("0x40", 0x40, shifted_image(0x40))
        self.ld_script = self.root / "project.ld"
        self.ld_script.write_text(LD_SCRIPT, encoding="utf-8")
        self.wrapper = self.write_script("relink.py", FAKE_WRAPPER)
        self.workdir = self.root / "work"

    def write_fixture(self, name: str, delta: int, image: bytes) -> None:
        directory = self.fixtures / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "image").write_bytes(image)
        (directory / "map").write_text(render_map(delta), encoding="utf-8")

    def write_script(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return path

    def arguments(self) -> list[str]:
        return [
            "shift",
            "rehearse",
            "orchestrate",
            "--wrapper",
            str(self.wrapper),
            "--ld-script",
            str(self.ld_script),
            "--anchor-object",
            "build/src/hasm/entrypoint.s.o",
            "--deltas",
            "0x10,0x40",
            "--workdir",
            str(self.workdir),
            "--blob",
            ".boot",
            "--crc-words",
            "0x10,0x14",
            *[
                argument
                for function, variable in CHECKSUM_PAIRS
                for argument in ("--checksum-pair", f"{function}={variable}")
            ],
        ]

    def test_the_driver_builds_every_delta_and_analyzes_each(self) -> None:
        status, stdout, stderr = run_cli([*self.arguments(), "--json"])
        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["mode"], "orchestrate")
        self.assertEqual(payload["deltas"], ["0x10", "0x40"])
        self.assertEqual(len(payload["analyses"]), 2)
        self.assertEqual(payload["analyses"][0]["unexplained_changed"], 1)

    def test_the_padded_scripts_are_written_where_a_reader_can_read_them(
        self,
    ) -> None:
        run_cli(self.arguments())
        script = (self.workdir / "shifted-0x10.ld").read_text(encoding="utf-8")
        self.assertIn("        . += 0x10;", script)

    def test_the_wrapper_contract_is_documented_in_the_help(self) -> None:
        with self.assertRaises(SystemExit):
            run_cli(["shift", "rehearse", "orchestrate", "--help"])

    def test_agreeing_deltas_report_a_consistent_rehearsal(self) -> None:
        _, stdout, _ = run_cli([*self.arguments(), "--json"])
        payload = json.loads(stdout)
        self.assertTrue(payload["classes_agree"])
        self.assertEqual(payload["disagreements"], [])

    def test_a_delta_that_disagrees_is_reported_as_a_finding(self) -> None:
        self.write_fixture("0x40", 0x40, shifted_image(0x40, extra_unexplained=True))
        _, stdout, _ = run_cli([*self.arguments(), "--json"])
        payload = json.loads(stdout)
        self.assertFalse(payload["classes_agree"])
        names = [item["name"] for item in payload["disagreements"]]
        self.assertIn("unexplained", names)

    def test_an_anchor_object_that_matches_nothing_fails_before_building(
        self,
    ) -> None:
        status, _, stderr = run_cli(
            [
                *self.arguments()[:5],
                "--ld-script",
                str(self.ld_script),
                "--anchor-object",
                "build/absent.o",
                "--deltas",
                "0x10",
                "--workdir",
                str(self.workdir),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("build/absent.o", stderr)
        self.assertFalse((self.workdir / "delta-0x10").exists())

    def test_a_wrapper_that_fails_is_reported_with_its_exit_status(self) -> None:
        failing = self.write_script("broken.py", FAILING_WRAPPER)
        arguments = self.arguments()
        arguments[arguments.index(str(self.wrapper))] = str(failing)
        status, _, stderr = run_cli(arguments)
        self.assertEqual(status, 2)
        self.assertIn("exit", stderr)

    def test_wb_140_an_unknown_blob_name_is_refused(self) -> None:
        """The same shared `build_region_table` check, reached from
        `orchestrate` after the (cheap, fake) relink runs but before its
        report is produced."""

        status, _, stderr = run_cli([*self.arguments(), "--blob", ".nope"])
        self.assertEqual(status, 2)
        self.assertIn(
            "--blob names a section this map does not have: .nope", stderr
        )

    def test_the_run_table_names_every_artifact_it_produced(self) -> None:
        _, stdout, _ = run_cli([*self.arguments(), "--json"])
        payload = json.loads(stdout)
        labels = [item["label"] for item in payload["runs"]]
        self.assertEqual(labels, ["base", "0x10", "0x40"])
        for run in payload["runs"]:
            self.assertTrue(Path(run["image"]).is_file())
            self.assertTrue(Path(run["map"]).is_file())

    def test_every_json_key_the_driver_emits_is_registered(self) -> None:
        _, stdout, _ = run_cli([*self.arguments(), "--json"])
        payload = json.loads(stdout)
        emitted = walk_keys(payload) - {"schema"}
        emitted -= set(payload["analyses"][0]["classes"])
        emitted -= set(payload["analyses"][0]["merge_tiers"])
        emitted -= set(payload["analyses"][0]["tier_verdicts"])
        for analysis in payload["analyses"]:
            for row in analysis["tier_verdicts"].values():
                emitted -= set(row)
        for row in payload["disagreements"]:
            emitted -= set(row["values"])
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))


# --------------------------------------------------------------------------
# DKR conformance -- skips when the sibling playground checkout is absent
# --------------------------------------------------------------------------

PLAYGROUND = Path(__file__).resolve().parents[2] / "decomp_playground"
S0_DIR = PLAYGROUND / ".workbench" / "shift-instrumentation" / "s0"
DKR_BASE_MAP = S0_DIR / "nm-base" / "dkr.us.v77.map"
DKR_BASE_IMAGE = S0_DIR / "nm-base" / "dkr.us.v77.z64"

DKR_BLOBS = (".assets", ".assets_lut", ".boot")
DKR_CHECKSUM_PAIRS = (
    ("race_check_finish", "gRaceCheckFinishChecksum"),
    ("render_scene", "gRenderSceneChecksum"),
    ("obj_loop_goldenballoon", "gObjLoopGoldenBalloonChecksum"),
    ("viewport_rsp_set", "gViewportFuncChecksum"),
)


def dkr_rehearsal(delta: int) -> Rehearsal:
    directory = S0_DIR / f"shift-0x{delta:x}"
    return build_rehearsal(
        base_ldmap=read_ld_map(DKR_BASE_MAP),
        base_image=DKR_BASE_IMAGE.read_bytes(),
        shifted_ldmap=read_ld_map(directory / "dkr.us.v77.map"),
        shifted_image=(directory / "dkr.us.v77.z64").read_bytes(),
        delta=delta,
        blobs=DKR_BLOBS,
        crc_words=(0x10, 0x14),
        checksum_pairs=DKR_CHECKSUM_PAIRS,
        model=default_pin_model(whitelist=(boot_globals_whitelist(),)),
        base_map_path=str(DKR_BASE_MAP),
        base_image_path=str(DKR_BASE_IMAGE),
    )


@unittest.skipUnless(
    DKR_BASE_MAP.is_file()
    and DKR_BASE_IMAGE.is_file()
    and (S0_DIR / "shift-0x10" / "dkr.us.v77.z64").is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrRehearseConformanceTests(unittest.TestCase):
    """S0's own rehearsal, replayed through the referee that replaced it.

    Every number below was measured on these exact artifacts. The two that
    matter most are the headline pair: `unexplained_changed` is S0's gate, and
    `stale_confirmed` is this stage's -- a reference implementation that comes
    out clean at high confidence is the positive control the whole campaign
    rests on. Both deltas are asserted, because a single delta can agree by
    coincidence (S2's bug class 3) and two cannot.
    """

    at10: ClassVar[Rehearsal]
    at40: ClassVar[Rehearsal]

    @classmethod
    def setUpClass(cls) -> None:
        cls.at10 = dkr_rehearsal(0x10)
        cls.at40 = dkr_rehearsal(0x40)

    def test_the_anchor_is_derived_from_the_two_maps(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.anchor.vram, 0x80000450)
                self.assertEqual(found.anchor.rom, 0x1050)
                self.assertEqual(found.anchor.source, "auto")
                self.assertEqual(found.anchor.highest_unmoved, 0x80000400)

    def test_the_movable_window_is_the_one_the_audit_derives(self) -> None:
        self.assertEqual(self.at10.window.lo, 0x80000400)
        self.assertEqual(self.at10.window.hi, 0x80122610)

    def test_no_symbol_moved_by_a_third_value(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.movement_anomalies, ())
                self.assertEqual(len(found.movement.movements), 3_889)

    def test_the_measured_census(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.census.differing_total, 20_687)
                self.assertEqual(
                    found.census.counts,
                    {
                        "abs32-tracks": 1_942,
                        "crc-header": 2,
                        "j26-tracks": 8_101,
                        "lo16-tracks": 10_642,
                    },
                )

    def test_the_gate_no_changed_word_is_unexplained(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(
                    found.unexplained_changed,
                    0,
                    "\n".join(
                        f"rom=0x{item.offset:06x} {item.old:08x}->{item.new:08x}"
                        for item in found.census.unexplained
                    ),
                )

    def test_the_positive_control_nothing_lands_stale_confirmed(self) -> None:
        """The campaign's own gate: a matched reference build comes out clean.

        `stale_confirmed` is a high-confidence address word that a real shift
        left behind. On a build known to be correct there must be none; if
        there is one, the merge is over-eager and the dump below says where.
        """

        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                confirmed = [
                    item
                    for item in found.reconciliation
                    if item.outcome == "stale-confirmed"
                ]
                self.assertEqual(
                    found.stale_confirmed,
                    0,
                    "\n".join(
                        f"rom=0x{item.rom:06x} vram=0x{item.vram:08x} "
                        f"value=0x{item.value:08x} region={item.region} "
                        f"resident={item.resident_symbol} "
                        f"target={item.target_symbol}"
                        for item in confirmed
                    ),
                )

    def test_the_stale_set_is_s0s_and_reconciles_against_the_audit(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.census.stale_total, 1_501)
                self.assertEqual(found.unmoved_total, 1_501)
                self.assertEqual(found.stale_unattributed, 0)

    def test_the_measured_tier_by_movement_matrix(self) -> None:
        expected = {
            "high": {"moved": 38, "unmoved": 0, "changed-other": 0},
            "medium": {"moved": 650, "unmoved": 7, "changed-other": 0},
            "low": {"moved": 1_254, "unmoved": 1_494, "changed-other": 0},
        }
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.tier_verdicts, expected)
                self.assertEqual(found.stale_review, 7)
                self.assertEqual(found.stale_noise, 1_494)

    def test_the_four_protected_functions_are_measured_not_assumed(self) -> None:
        """S0 read these as shift-insensitive. They are not, and it matters.

        S0-RESULT.md records the four `calc_func_checksums` variables as
        having "unchanged values" because "the protected functions contain no
        shift-sensitive words". The first half is true and the second is not:
        every one of the four bodies carries relocated references, and all
        four change under both deltas (`viewport_rsp_set` alone moves a `jal`
        and four `%lo` displacements). What did not happen is the repatch --
        DKR's `calc_func_checksums.py` runs on the `verify` target only, and
        these rehearsal images were linked without it, so the stored sums are
        the frozen source literals in every build.

        That is precisely the cursed-audio precondition: a protected function
        whose bytes moved and whose checksum did not. The rule is supposed to
        fire here, and asserting that it does is what makes it a rule rather
        than a decoration.
        """

        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(len(found.checksums), 4)
                self.assertEqual(
                    [item.status for item in found.checksums],
                    ["checksum-stale"] * 4,
                )
                self.assertEqual(found.checksum_findings, 4)
                self.assertEqual(found.checksum_pass, 0)
                for item in found.checksums:
                    self.assertGreater(item.body_changed, 0)
                    self.assertFalse(item.variable_changed)

    def test_the_two_deltas_agree_on_every_class(self) -> None:
        self.assertEqual(cross_delta_disagreements([self.at10, self.at40]), ())


# --------------------------------------------------------------------------
# WB-142: an assignment names a boundary; only an object names a byte
# --------------------------------------------------------------------------

#: One map shape, rendered at two shifts. Everything at or above
#: `0x80000400` moves by `delta`. The only in-window symbol *below* the first
#: object-backed one is `pre_VRAM_END`, a linker-script assignment placed in a
#: section that declared no ``AT()`` -- which is exactly S6's pilotwings64
#: shape: splat writes `<seg>_ROM_START`/`_ROM_END` for every segment, they
#: move by the delta like everything else, and they translate to no ROM offset
#: at all.
def wb142_map(delta: int) -> str:
    return "\n".join(
        (
            "",
            "Linker script and memory map",
            "",
            ".header         0x00000000       0x40",
            " .data          0x00000000       0x40 build/header.o",
            "",
            f".pre_bss        0x{0x80000380 + delta:08x}       0x80",
            f" .bss           0x{0x80000380 + delta:08x}       0x80 build/pre.o",
            f"                0x{0x80000380 + delta:08x}                "
            f"pre_VRAM_END = 0x{0x80000380 + delta:08x}",
            "",
            f".main           0x{0x80000400 + delta:08x}       0x100 "
            "load address 0x00000040",
            f" .text          0x{0x80000400 + delta:08x}       0x100 build/code.o",
            f"                0x{0x80000400 + delta:08x}                "
            f"main_TEXT_START = 0x{0x80000400 + delta:08x}",
            f"                0x{0x80000410 + delta:08x}                func_a",
            f"                0x{0x80000440 + delta:08x}                func_b",
            "",
        )
    )


class Wb142AnchorDerivationTests(unittest.TestCase):
    """The anchor is a byte the pad moved, so only an object can name it.

    S6 hit this on pilotwings64 (`PW64-SHIFT-CONFIG.md` 3.3): `--anchor auto`
    refused with *"the anchor VRAM 0x00001050 has no ROM placement in the base
    map"*, having followed `entry_ROM_END` -- an unconditional splat output
    whose value is a ROM offset, not an address -- out of the layout. S7's
    movable-window floor has since put values that low out of reach, so the
    fix here is one level down and general: an assignment names a *boundary*,
    an object names a *byte*, and an anchor is a byte.
    """

    def setUp(self) -> None:
        self.base = parse_ld_map(wb142_map(0), path="base.map")
        self.shifted = parse_ld_map(wb142_map(0x10), path="shifted.map")

    def test_auto_derives_the_first_object_backed_symbol(self) -> None:
        found = derive_anchor(
            self.base,
            self.shifted,
            delta=0x10,
            window_lo=0x80000380,
            window_hi=0x80000500,
        )
        self.assertEqual(found.vram, 0x80000410)
        self.assertEqual(found.symbol, "func_a")
        self.assertEqual(found.source, "auto")
        self.assertEqual(found.lowest_moved, 0x80000410)

    def test_the_anchor_translates_to_a_rom_offset(self) -> None:
        """The half S6's refusal was actually about: the derived VRAM has to
        sit inside a section that declared `AT()`, and an assignment's
        does not have to."""

        found = derive_anchor(
            self.base,
            self.shifted,
            delta=0x10,
            window_lo=0x80000380,
            window_hi=0x80000500,
        )
        self.assertEqual(found.rom, 0x50)
        self.assertIsNone(self.base.rom_for_vram(0x80000380))

    def test_the_unrestricted_minimum_is_the_assignment_and_is_lower(self) -> None:
        """The bug, stated as an assertion rather than as prose.

        `pre_VRAM_END` moves by exactly the delta and sits below every object
        symbol, so an unrestricted derivation picks it -- and then correctly
        refuses to translate it, because no `AT()` section covers it. Both
        halves are asserted so that a future change that re-admits assignment
        symbols fails here rather than in a live conformance run.
        """

        moved = sorted(
            self.base.symbol(name).address
            for name in self.base.symbol_names() & self.shifted.symbol_names()
            if 0x80000380 <= self.base.symbol(name).address < 0x80000500
            and self.shifted.symbol(name).address
            - self.base.symbol(name).address
            == 0x10
        )
        self.assertEqual(moved[0], 0x80000380)
        self.assertTrue(self.base.symbol("pre_VRAM_END").is_assignment)
        self.assertFalse(self.base.symbol("func_a").is_assignment)

    def test_highest_unmoved_is_deliberately_not_restricted(self) -> None:
        """It answers a different question, and narrowing it would hide the
        one shape worth seeing -- an absolute pin above the insertion that
        never moves. See `Anchor.highest_unmoved`."""

        found = derive_anchor(
            self.base,
            self.shifted,
            delta=0x10,
            window_lo=0x00000000,
            window_hi=0x80000500,
        )
        self.assertEqual(found.vram, 0x80000410)

    def test_a_map_with_only_assignments_refuses_and_says_why(self) -> None:
        text = "\n".join(
            (
                "",
                "Linker script and memory map",
                "",
                ".main           0x80000400       0x100 load address 0x00000040",
                " .text          0x80000400       0x100 build/code.o",
                "                0x80000400                "
                "main_TEXT_START = 0x80000400",
                "",
            )
        )
        shifted_text = text.replace("0x80000400 ", "0x80000410 ").replace(
            "= 0x80000400", "= 0x80000410"
        )
        with self.assertRaises(ValueError) as caught:
            derive_anchor(
                parse_ld_map(text),
                parse_ld_map(shifted_text),
                delta=0x10,
                window_lo=0x80000000,
                window_hi=0x80001000,
            )
        message = str(caught.exception)
        self.assertIn("object-backed", message)
        self.assertIn("WB-142", message)
        self.assertIn("--anchor", message)


# --------------------------------------------------------------------------
# WB-143a: the symbol-side census
# --------------------------------------------------------------------------

CENSUS_SECTIONS = (
    (".text", 0x80000400, 0x100, 0x6),
    (".bss", 0x80000500, 0x80, 0x3),
)


def census_elf(delta: int) -> bytes:
    """One link's symbols, at a shift of `delta`.

    Six symbols covering every case the census has to separate: the boundary
    the pad went in at, an object that tracks, an absolute pin that shadowed
    an object definition (the size is the evidence), an absolute pin with
    nothing behind it, an absolute pin at the window's own top bound, and one
    below the insertion that correctly does not move.
    """

    def moved(address: int) -> int:
        return address + delta if address >= 0x80000410 else address

    return build_elf(
        sections=[
            (name, moved(address) if address >= 0x80000410 else address, size, flags)
            for name, address, size, flags in CENSUS_SECTIONS
        ],
        symbols=[
            ("below_pad", 0x80000404, 0x4, 1, 1, 1),
            ("func_a", moved(0x80000410), 0x40, 2, 1, 1),
            ("gTracked", moved(0x80000500), 0x4, 1, 1, 2),
            ("D_80000510", 0x80000510, 0x8, 1, 1, SHN_ABS),
            ("D_80000520", 0x80000520, 0x0, 0, 1, SHN_ABS),
            ("D_80000580", 0x80000580, 0x0, 0, 1, SHN_ABS),
        ],
    )


class SymbolCensusTests(unittest.TestCase):
    """Every rule the symbol side applies, one symbol apiece."""

    def setUp(self) -> None:
        self.census = symbol_census(
            parse_elf_symbols(census_elf(0), path="base.elf"),
            parse_elf_symbols(census_elf(0x10), path="shifted.elf"),
            delta=0x10,
            anchor_vram=0x80000410,
            window_hi=0x80000580,
        )

    def test_a_symbol_at_the_insertion_is_excluded_and_counted(self) -> None:
        """Both answers are correct at that one address at once -- see
        `symbol_census`. Counting it beats absorbing it."""

        self.assertEqual(self.census.boundary_symbols, 1)
        self.assertNotIn(
            "func_a", [item.name for item in self.census.findings]
        )

    def test_a_symbol_below_the_insertion_is_not_judged(self) -> None:
        self.assertNotIn(
            "below_pad", [item.name for item in self.census.findings]
        )

    def test_an_object_backed_symbol_that_tracked_is_a_pass(self) -> None:
        self.assertEqual(self.census.checked, 4)
        self.assertEqual(self.census.moved, 1)

    def test_the_shadowing_pin_is_named_apart_from_the_stale_ones(self) -> None:
        self.assertEqual(self.census.shadowing_pins, 1)
        self.assertEqual(self.census.symbol_stale, 2)
        found = {item.name: item.classification for item in self.census.findings}
        self.assertEqual(found["D_80000510"], SHADOWING_PIN)
        self.assertEqual(found["D_80000520"], SYMBOL_STALE)

    def test_the_top_bound_is_inclusive(self) -> None:
        """`window_hi` is one past the last movable byte, and the symbol
        naming that boundary moves with it. A half-open bound would drop
        exactly the pin sitting on it."""

        self.assertIn("D_80000580", [item.name for item in self.census.findings])

    def test_every_finding_names_the_section_that_owns_its_address(self) -> None:
        found = {item.name: item.owning_section for item in self.census.findings}
        self.assertEqual(found["D_80000510"], ".bss")
        self.assertEqual(found["D_80000520"], ".bss")
        self.assertIsNone(found["D_80000580"])

    def test_findings_are_ranked_free_wins_first(self) -> None:
        self.assertEqual(self.census.findings[0].name, "D_80000510")

    def test_the_rules_travel_with_the_report(self) -> None:
        payload = self.census.as_dict(limit=10)
        self.assertEqual(
            [item["name"] for item in payload["symbol_rules"]],
            [item.name for item in SYMBOL_RULES],
        )
        self.assertEqual(payload["symbol_range_lo"], 0x80000410)
        self.assertEqual(payload["symbol_range_hi"], 0x80000580)


class SymbolCensusWiringTests(unittest.TestCase):
    """The census is off unless both ELFs arrive, and says which zero it is."""

    def analysis(self, **extra: object) -> Rehearsal:
        return build_rehearsal(
            base_ldmap=base_map(),
            base_image=base_image(),
            shifted_ldmap=shifted_map(0x10),
            shifted_image=shifted_image(0x10),
            delta=0x10,
            blobs=BLOBS,
            crc_words=CRC_WORDS,
            **extra,  # type: ignore[arg-type]
        )

    def test_off_by_default(self) -> None:
        found = self.analysis()
        self.assertIsNone(found.symbols)
        self.assertEqual(found.symbol_stale, 0)
        payload = found.as_dict(limit=5)
        self.assertFalse(payload["symbol_census"])
        self.assertNotIn("symbol_stale", payload)

    def test_the_report_says_how_to_turn_it_on(self) -> None:
        text = "\n".join(rehearse_lines(self.analysis(), limit=5))
        self.assertIn("symbol_census=off", text)
        self.assertIn("--base-elf", text)

    def test_one_elf_alone_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.analysis(base_elf=parse_elf_symbols(census_elf(0)))
        self.assertIn("go together", str(caught.exception))

    def test_both_elfs_turn_it_on_and_it_counts_toward_findings(self) -> None:
        found = self.analysis(
            base_elf=parse_elf_symbols(census_elf(0), path="base.elf"),
            shifted_elf=parse_elf_symbols(census_elf(0x10), path="shifted.elf"),
        )
        assert found.symbols is not None
        payload = found.as_dict(limit=5)
        self.assertTrue(payload["symbol_census"])
        self.assertEqual(payload["base_elf"], "base.elf")
        self.assertEqual(
            found.findings,
            found.unexplained_changed
            + found.stale_confirmed
            + len(found.movement_anomalies)
            + found.checksum_findings
            + found.symbol_stale
            + found.shadowing_pins,
        )

    def test_every_emitted_key_is_registered(self) -> None:
        payload = self.analysis(
            base_elf=parse_elf_symbols(census_elf(0)),
            shifted_elf=parse_elf_symbols(census_elf(0x10)),
        ).as_dict(limit=5)
        emitted = set(payload)
        for row in payload["symbol_findings"]:
            emitted |= set(row)
        for row in payload["symbol_rules"]:
            emitted |= set(row)
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))


# --------------------------------------------------------------------------
# pilotwings64 conformance (S6) -- the live regression for WB-142 and WB-143a
# --------------------------------------------------------------------------

S6_DIR = PLAYGROUND / ".workbench" / "shift-instrumentation" / "s6"
PW64_BASE_MAP = S6_DIR / "artifacts" / "base-symbolic.map"
PW64_BASE_IMAGE = S6_DIR / "artifacts" / "base-symbolic.z64"
PW64_BASE_ELF = S6_DIR / "scratch" / "base-symbolic.elf"

#: The five `type: bin` segments S6 marked opaque. They are DMA'd from cart,
#: so their link-time VMA is a placement artifact -- marking them is what
#: keeps 703 coincidental address-shaped words in `.filesys` classified as
#: noise instead of promoted into the finding set.
PW64_BLOBS = (".filetable", ".filesys", ".audio_seq", ".audio_ctl", ".audio_tbl")

#: S6 4.4(a): the ten pins an object already defines. Ablation B deleted all
#: ten and rebuilt to the same sha1.
PW64_SHADOWING = (
    "D_80250E80",
    "D_8034E710",
    "D_803571F0",
    "aspMainDataStart",
    "aspMainTextStart",
    "gspF3DEX_fifoDataStart",
    "gspF3DEX_fifoTextStart",
    "gspFast3DDataStart",
    "gspFast3DTextStart",
    "rspbootTextStart",
)

#: S6 4.4(b) and (c): eleven inert leftovers plus the boot stack pointer and
#: the heap base. The thirteen the experiment's post-ablation `nm` census
#: measured by hand.
PW64_SYMBOL_STALE = (
    "D_8024B355",
    "D_8024B356",
    "D_8024B357",
    "D_802C3C90",
    "D_803509B7",
    "D_80350466",
    "D_8035046A",
    "D_8034EF33",
    "D_8034F167",
    "D_8034F8EA",
    "D_8034F98F",
    "D_803805E0",
    "env_data_00FE",
)


def pw64_rehearsal(delta: int) -> Rehearsal:
    return build_rehearsal(
        base_ldmap=read_ld_map(PW64_BASE_MAP),
        base_image=PW64_BASE_IMAGE.read_bytes(),
        shifted_ldmap=read_ld_map(S6_DIR / "artifacts" / f"shifted-{delta:x}.map"),
        shifted_image=(S6_DIR / "artifacts" / f"shifted-{delta:x}.z64").read_bytes(),
        delta=delta,
        blobs=PW64_BLOBS,
        crc_words=(0x10, 0x14),
        base_elf=read_elf_symbols(PW64_BASE_ELF),
        shifted_elf=read_elf_symbols(S6_DIR / "scratch" / f"shifted-{delta:x}.elf"),
        base_map_path=str(PW64_BASE_MAP),
        base_image_path=str(PW64_BASE_IMAGE),
    )


_HAVE_PW64_S6 = (
    PW64_BASE_MAP.is_file()
    and PW64_BASE_IMAGE.is_file()
    and PW64_BASE_ELF.is_file()
    and (S6_DIR / "scratch" / "shifted-10.elf").is_file()
    and (S6_DIR / "scratch" / "shifted-40.elf").is_file()
)


@unittest.skipUnless(
    _HAVE_PW64_S6, f"S6 pilotwings64 artifacts not found under {S6_DIR}"
)
class Pw64RehearseConformanceTests(unittest.TestCase):
    """S6's experiment, replayed through the two instruments it asked for.

    The experiment reached its numbers by hand: `--anchor kernel_TEXT_START`
    passed explicitly because `auto` refused, and the symbol-side blockers
    found with `nm -n` over two ELFs, `readelf -r` over 307 objects, and two
    ablation rebuilds. Both are commands now, and both must reproduce what the
    hand method measured -- not approximately, exactly.
    """

    at10: ClassVar[Rehearsal]
    at40: ClassVar[Rehearsal]

    @classmethod
    def setUpClass(cls) -> None:
        cls.at10 = pw64_rehearsal(0x10)
        cls.at40 = pw64_rehearsal(0x40)

    def test_wb142_auto_now_derives_the_anchor_s6_passed_by_hand(self) -> None:
        """S6 3.3: `--anchor kernel_TEXT_START` resolved to
        ``anchor_vram=0x802000a0 anchor_rom=0x001050`` -- "precisely the
        insertion point (entrypoint is 0x50 bytes at ROM 0x1000, so ROM
        0x1050 / VRAM 0x802000A0 is the first shifted byte)". `auto` reaches
        the same pair, and names the object that starts there rather than one
        of the five boundary assignments sharing the address.
        """

        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.anchor.vram, 0x802000A0)
                self.assertEqual(found.anchor.rom, 0x1050)
                self.assertEqual(found.anchor.source, "auto")
                self.assertEqual(found.anchor.symbol, "func_802000A0")

    def test_the_anchor_is_the_one_the_named_symbol_resolves_to(self) -> None:
        """The same pair, reached the way S6 reached it. Two routes to one
        address is what makes the derived one trustworthy."""

        named = build_rehearsal(
            base_ldmap=read_ld_map(PW64_BASE_MAP),
            base_image=PW64_BASE_IMAGE.read_bytes(),
            shifted_ldmap=read_ld_map(S6_DIR / "artifacts" / "shifted-10.map"),
            shifted_image=(S6_DIR / "artifacts" / "shifted-10.z64").read_bytes(),
            delta=0x10,
            anchor="kernel_TEXT_START",
            blobs=PW64_BLOBS,
            crc_words=(0x10, 0x14),
        )
        self.assertEqual(named.anchor.vram, self.at10.anchor.vram)
        self.assertEqual(named.anchor.rom, self.at10.anchor.rom)
        self.assertEqual(named.anchor.source, "symbol")

    def test_the_headline_s6_measured_is_reproduced(self) -> None:
        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                self.assertEqual(found.unexplained_changed, 0)
                self.assertEqual(found.stale_confirmed, 1)

    def test_the_convicted_word_is_d_803571f0(self) -> None:
        """S6 4.1: ROM `0x0d5cbc` holds `0x803571f0`, in `.app`'s `.data`,
        contributed by `src/app/code_51E30.c`."""

        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                confirmed = [
                    item
                    for item in found.reconciliation
                    if item.outcome == "stale-confirmed"
                ]
                self.assertEqual(len(confirmed), 1)
                self.assertEqual(confirmed[0].rom, 0x0D5CBC)
                self.assertEqual(confirmed[0].value, 0x803571F0)
                self.assertEqual(confirmed[0].target_symbol, "D_803571F0")

    def test_wb143_the_symbol_census_measures_s6s_thirteen(self) -> None:
        """S6 4.4: *"of 2731 shared symbols, exactly 13 in-window symbols
        still fail to move -- the 11 inert ones from (c) plus `D_802C3C90`
        and `D_803805E0` from (b). The 8 `entry_*` symbols also do not move,
        correctly, because they are below the pad."*

        Thirteen is the post-ablation number, and this pair is *pre*-ablation
        -- which is the point: the ten pins ablation B removed are still here
        and are counted apart, as `shadowing-pin`. 13 + 10 is the whole
        23-symbol population, split by whether the remediation is known.
        """

        for delta, found in ((0x10, self.at10), (0x40, self.at40)):
            with self.subTest(delta=delta):
                assert found.symbols is not None
                self.assertEqual(found.symbol_stale, 13)
                self.assertEqual(found.shadowing_pins, 10)
                self.assertEqual(
                    sorted(
                        item.name
                        for item in found.symbols.by_classification(SYMBOL_STALE)
                    ),
                    sorted(PW64_SYMBOL_STALE),
                )
                self.assertEqual(
                    sorted(
                        item.name
                        for item in found.symbols.by_classification(SHADOWING_PIN)
                    ),
                    sorted(PW64_SHADOWING),
                )

    def test_the_eight_entry_symbols_are_the_boundary_not_a_finding(self) -> None:
        """S6 counted them and set them aside; so does this, by name."""

        assert self.at10.symbols is not None
        names = [item.name for item in self.at10.symbols.findings]
        for name in ("entry_TEXT_END", "entry_RODATA_END", "entrypoint"):
            self.assertNotIn(name, names)
        self.assertGreater(self.at10.symbols.boundary_symbols, 0)

    def test_the_named_examples_s6_singled_out(self) -> None:
        """Four spot checks, one per shape S6 described in prose.

        The RSP ucode pins and `D_80250E80` are the ones S6 said the
        data-side referee *structurally could not see* -- they are consumed
        through `%hi/%lo` pairs in text -- and they are exactly the ones this
        census reaches without reading a single instruction word.
        """

        assert self.at10.symbols is not None
        found = {item.name: item for item in self.at10.symbols.findings}

        rsp = found["rspbootTextStart"]
        self.assertEqual(rsp.classification, SHADOWING_PIN)
        self.assertEqual(rsp.value, 0x80245530)
        self.assertEqual(rsp.size, 0xD0)  # src/rsp/rspboot.o's own function

        kernel_bss = found["D_80250E80"]
        self.assertEqual(kernel_bss.classification, SHADOWING_PIN)
        self.assertEqual(kernel_bss.owning_section, ".kernel_bss")

        stack = found["D_802C3C90"]  # the boot stack pointer, S6 4.4(b)
        self.assertEqual(stack.classification, SYMBOL_STALE)
        self.assertEqual(stack.size, 0)
        self.assertEqual(stack.owning_section, ".kernel_bss")

        shadow = found["D_803571F0"]
        self.assertEqual(shadow.classification, SHADOWING_PIN)
        self.assertEqual(shadow.size, 4)  # the `f32` the object declares
        self.assertEqual(shadow.owning_section, ".app_bss")

    def test_the_symbol_side_finds_more_than_the_data_side(self) -> None:
        """S6 4.5, as a number: *"on this project the symbol-side census
        found 13x more blockers"*. One data-side conviction; twenty-three
        symbol-side findings, of which the one the data side saw is a
        member."""

        assert self.at10.symbols is not None
        self.assertEqual(self.at10.stale_confirmed, 1)
        self.assertEqual(len(self.at10.symbols.findings), 23)
        self.assertIn(
            "D_803571F0", [item.name for item in self.at10.symbols.findings]
        )

    def test_the_two_deltas_agree(self) -> None:
        self.assertEqual(cross_delta_disagreements([self.at10, self.at40]), ())


if __name__ == "__main__":
    unittest.main()
