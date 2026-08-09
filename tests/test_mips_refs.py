"""Tests for %hi/%lo arithmetic, the raw-word decoder, and the shift census.

The synthetic tests pin down every decoder shape and every census label by
hand-built words, because a census that silently reclassified a shape would
be worse than one that errored -- it would just print a wrong number with
total confidence. The live-conformance tests replay S0's hand-rolled spike
(see the shift-instrumentation campaign's S0-RESULT.md and its census.py)
against the actual DKR images it was run against, and self-skip when those
images are not present on disk: this module must never ship ROM-derived
bytes as a fixture, so the only way to check it against real data is to read
the real data, when it happens to be there.
"""

from __future__ import annotations

import struct
import unittest
from pathlib import Path

from decomp_workbench.mips_refs import (
    OPCODE_J,
    OPCODE_JAL,
    OPCODE_LUI,
    GeneratedSpec,
    RangeModel,
    RegionSpec,
    WhitelistEntry,
    _classify_text_word,
    alignment,
    build_word_census,
    compose,
    decode_word,
    default_n64_windows,
    hi16_for,
    lo16_for,
)

# ---------------------------------------------------------------------------
# Live-conformance fixture locations. S0's campaign artifacts, external to
# this repository -- see the module docstring for why nothing here is copied
# into a fixture file.
# ---------------------------------------------------------------------------
S0_DIR = (
    Path.home()
    / "Desktop"
    / "dev"
    / "decomp_playground"
    / ".workbench"
    / "shift-instrumentation"
    / "s0"
)
BASE_IMAGE = S0_DIR / "nm-base" / "dkr.us.v77.z64"
SHIFT_IMAGE = S0_DIR / "shift-0x10" / "dkr.us.v77.z64"

#: DKR's main overlay VRAM/ROM anchor: `main_TEXT_START = 0x80000400` maps
#: to ROM `0x1000` (the header + boot blob precede it). Every ROM<->VRAM
#: conversion below is `vram - MAIN_VRAM + MAIN_ROM`.
MAIN_VRAM = 0x80000400
MAIN_ROM = 0x1000

#: `main_TEXT_END` read off the base map -- the boundary S0-RESULT.md calls
#: "classify by section first": everything before it decodes as MIPS text,
#: everything from it onward (data, rodata, bss-shaped) is value-first.
MAIN_TEXT_END_VRAM = 0x800D0CE0
TEXT_END_ROM = MAIN_TEXT_END_VRAM - MAIN_VRAM + MAIN_ROM

#: `main_BSS_END` read off the base map -- the far edge of the region the
#: cascade insertion moves, and therefore the far edge of the moved-VRAM
#: range a stale-candidate value must fall inside.
MAIN_BSS_END_VRAM = 0x80122610

INSERTION_ROM = 0x1050  # MAIN_ROM + entrypoint.s.o(.text) size (0x50)
INSERTION_VRAM = 0x80000450
DELTA = 0x10

#: The four `calc_func_checksums` targets S0's dossier names, as ROM
#: offsets computed the same way as every other VRAM address here.
CHECKSUM_SYMBOL_VRAM = {
    "gRaceCheckFinishChecksum": 0x800D1DB0,
    "gRenderSceneChecksum": 0x800D5C80,
    "gObjLoopGoldenBalloonChecksum": 0x800D6410,
    "gViewportFuncChecksum": 0x800D3030,
}


def _skip_unless_images_present(test: unittest.TestCase) -> None:
    if not (BASE_IMAGE.is_file() and SHIFT_IMAGE.is_file()):
        test.skipTest(
            f"S0 campaign images not found under {S0_DIR}; live-conformance "
            "tests only run when a developer has the shift-instrumentation "
            "campaign checked out locally"
        )


def word(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# %hi/%lo arithmetic
# ---------------------------------------------------------------------------


class HiLoArithmeticTests(unittest.TestCase):
    """The signed-%lo incident S0 hit exactly once: 0xFFF0 -> 0x0000."""

    def test_naive_top16_would_change_but_signed_hi_does_not(self) -> None:
        """An address whose %lo is negative already carries the +1 into %hi;
        moving it across the 0x10000 boundary cancels that carry instead of
        adding a new one, so %hi is unchanged both before and after."""

        old_addr = 0x8000FFF0
        new_addr = old_addr + 0x10

        self.assertEqual(old_addr & 0xFFFF, 0xFFF0)
        self.assertEqual(new_addr & 0xFFFF, 0x0000)
        self.assertEqual(hi16_for(old_addr), hi16_for(new_addr))
        # And it is not the naive split's answer for the *old* address.
        self.assertNotEqual(hi16_for(old_addr), (old_addr >> 16) & 0xFFFF)

    def test_crossing_into_negative_lo_bumps_hi(self) -> None:
        """The mirror case: a positive %lo pushed across 0x8000 by the shift
        turns negative, and %hi must absorb the +1 it did not need before."""

        old_addr = 0x80007FF8
        new_addr = old_addr + 0x10

        self.assertEqual(old_addr & 0xFFFF, 0x7FF8)
        self.assertEqual(new_addr & 0xFFFF, 0x8008)
        self.assertEqual(hi16_for(new_addr), hi16_for(old_addr) + 1)

    def test_lo16_for_is_the_signed_value_not_the_raw_field(self) -> None:
        self.assertEqual(lo16_for(0x8000FFF0), -0x10)
        self.assertEqual(lo16_for(0x80010000), 0)
        self.assertEqual(lo16_for(0x80007FF8), 0x7FF8)

    def test_compose_round_trips_hi16_for_and_lo16_for(self) -> None:
        for addr in (
            0x80000450,
            0x8000FFF0,
            0x80010000,
            0x80007FF8,
            0x80008008,
            0x00000000,
            0xFFFFFFFF,
            0x800D1DB0,
        ):
            hi = hi16_for(addr)
            lo = lo16_for(addr) & 0xFFFF
            self.assertEqual(compose(hi, lo), addr & 0xFFFFFFFF, hex(addr))

    def test_compose_sign_extends_the_raw_lo_field(self) -> None:
        # hi=0x8001, lo=0xFFF0 (raw field) -> the negative %lo interpretation,
        # not 0x8001FFF0.
        self.assertEqual(compose(0x8001, 0xFFF0), 0x8000FFF0)


# ---------------------------------------------------------------------------
# Minimal raw-word reference decoder
# ---------------------------------------------------------------------------


class DecodeWordTests(unittest.TestCase):
    def test_j_decodes_the_26_bit_target_and_composes_with_region(self) -> None:
        ref = decode_word((OPCODE_J << 26) | 0x123456)

        self.assertEqual(ref.kind, "j")
        self.assertEqual(ref.opcode, OPCODE_J)
        self.assertEqual(ref.target26, 0x123456)
        self.assertEqual(ref.target(region=0x80000000), 0x80000000 | (0x123456 << 2))
        # Only the high nibble of `region` is read.
        self.assertEqual(
            ref.target(region=0x8048D158), ref.target(region=0x80000000)
        )

    def test_jal_decodes_the_same_shape_as_j(self) -> None:
        ref = decode_word((OPCODE_JAL << 26) | 0x000204)

        self.assertEqual(ref.kind, "jal")
        self.assertEqual(ref.target26, 0x204)
        self.assertEqual(ref.target(region=0x80000000), 0x80000810)

    def test_lui_decodes_rt_and_imm16(self) -> None:
        ref = decode_word((OPCODE_LUI << 26) | (8 << 16) | 0x8012)

        self.assertEqual(ref.kind, "lui")
        self.assertEqual(ref.rt, 8)
        self.assertEqual(ref.imm16, 0x8012)
        self.assertIsNone(ref.target26)

    def test_imm16_bearing_op_decodes_rs_rt_and_signed_immediate(self) -> None:
        # addiu $t0, $sp, -16
        ref = decode_word((0x09 << 26) | (29 << 21) | (8 << 16) | 0xFFF0)

        self.assertEqual(ref.kind, "imm16")
        self.assertEqual(ref.rs, 29)
        self.assertEqual(ref.rt, 8)
        self.assertEqual(ref.imm16, 0xFFF0)
        self.assertEqual(ref.simm16, -16)

    def test_special_opcode_is_other_not_imm16(self) -> None:
        """SPECIAL's low bits are a funct/shamt field, not an address --
        decoding it as imm16 would manufacture a fake immediate."""

        ref = decode_word((0 << 26) | (8 << 21) | (9 << 16) | (10 << 11) | 0x20)

        self.assertEqual(ref.kind, "other")
        self.assertIsNone(ref.imm16)
        self.assertIsNone(ref.target26)

    def test_target_is_none_off_a_non_jump_word(self) -> None:
        ref = decode_word((OPCODE_LUI << 26) | 0x8000)
        self.assertIsNone(ref.target(region=0x80000000))

    def test_as_dict_is_json_ready(self) -> None:
        ref = decode_word((OPCODE_J << 26) | 0x10)
        payload = ref.as_dict()
        self.assertEqual(payload["kind"], "j")
        self.assertEqual(payload["target26"], 0x10)


# ---------------------------------------------------------------------------
# Address-shape model
# ---------------------------------------------------------------------------


class RangeModelTests(unittest.TestCase):
    def test_narrower_window_listed_first_wins(self) -> None:
        model = RangeModel(windows=default_n64_windows())

        window, whitelisted, reason = model.classify_value(0xB0001234)
        self.assertEqual(window, "cart")
        self.assertFalse(whitelisted)
        self.assertIsNone(reason)

    def test_kseg1_hardware_outside_the_cart_domain(self) -> None:
        model = RangeModel(windows=default_n64_windows())
        window, _, _ = model.classify_value(0xA4001234)
        self.assertEqual(window, "kseg1")

    def test_kseg0_ram(self) -> None:
        model = RangeModel(windows=default_n64_windows())
        window, _, _ = model.classify_value(0x80123456)
        self.assertEqual(window, "kseg0")

    def test_segmented_is_a_heuristic_low_window(self) -> None:
        model = RangeModel(windows=default_n64_windows())
        window, _, _ = model.classify_value(0x06000000)
        self.assertEqual(window, "segmented")

    def test_value_outside_every_window_reports_none(self) -> None:
        model = RangeModel(windows=default_n64_windows())
        window, whitelisted, _reason = model.classify_value(0xD0000000)
        self.assertIsNone(window)
        self.assertFalse(whitelisted)

    def test_exact_whitelist_entry(self) -> None:
        model = RangeModel(
            whitelist=(
                WhitelistEntry.exact(0x80100400, reason="CIC-6103 boot address"),
            )
        )
        _window, whitelisted, reason = model.classify_value(0x80100400)
        self.assertTrue(whitelisted)
        self.assertEqual(reason, "CIC-6103 boot address")
        # One address off is not whitelisted.
        self.assertFalse(model.classify_value(0x80100401)[1])

    def test_ranged_whitelist_entry(self) -> None:
        model = RangeModel(
            whitelist=(
                WhitelistEntry(
                    lo=0x80100000, hi=0x80101000, reason="ucode data blob"
                ),
            )
        )
        _, whitelisted, reason = model.classify_value(0x80100400)
        self.assertTrue(whitelisted)
        self.assertEqual(reason, "ucode data blob")

    def test_whitelist_and_window_are_independent_answers(self) -> None:
        model = RangeModel(
            windows=default_n64_windows(),
            whitelist=(
                WhitelistEntry.exact(0x80100400, reason="CIC-6103 boot address"),
            ),
        )
        window, whitelisted, reason = model.classify_value(0x80100400)
        self.assertEqual(window, "kseg0")
        self.assertTrue(whitelisted)
        self.assertEqual(reason, "CIC-6103 boot address")

    def test_alignment_is_value_mod_4(self) -> None:
        self.assertEqual(alignment(0x80000450), 0)
        # S0's matched-garbage archaeology example: an unaligned "pointer"
        # that is retail build-machine leftovers, not a live reference.
        self.assertEqual(alignment(0x8007BA73), 3)


# ---------------------------------------------------------------------------
# Two-image pairing + word census -- synthetic
# ---------------------------------------------------------------------------


class WordCensusSyntheticTests(unittest.TestCase):
    """One tiny hand-built image pair exercising every class at once.

    Twelve words, laid out so each offset isolates exactly one shape: a
    generated CRC span that must win before any decode is attempted, a
    header pointer tracked by value, an equal pair that is and is not a
    stale candidate, every text decode class, a text word that only the
    abs32 fallback explains, and one genuinely unexplained word in each of
    text and data.
    """

    DELTA = 0x10

    def setUp(self) -> None:
        old = {
            # 0x00: generated span ("crc-header"). If this were decoded
            # instead, its top 6 bits (0x11 >> ...) would not match any
            # tracked shape and it would misreport as unexplained -- the
            # precedence test is that it does not.
            0x00: 0x11111111,
            # 0x04: header kind (non-text => value-first), abs32-tracks.
            0x04: 0x80000100,
            # 0x08: blob kind, equal pair, VRAM-shaped and inside the moved
            # range -> stale candidate.
            0x08: 0x80000450,
            # 0x0C: blob kind, equal pair, outside the moved range -> not
            # a stale candidate at all.
            0x0C: 0x00000001,
            # 0x10: text kind, j26-tracks.
            0x10: (OPCODE_J << 26) | 0x100,
            # 0x14: text kind, j26-tracks via jal.
            0x14: (OPCODE_JAL << 26) | 0x200,
            # 0x18: text kind, lo16-tracks, no sign wrap.
            0x18: (0x23 << 26) | (29 << 21) | (8 << 16) | 0x0010,
            # 0x1C: text kind, lo16-tracks, the sign-wrap shape.
            0x1C: (0x23 << 26) | (29 << 21) | (9 << 16) | 0xFFF0,
            # 0x20: text kind, hi16-adjust (a lui bumped by the carry).
            0x20: (OPCODE_LUI << 26) | (8 << 16) | 0x8000,
            # 0x24: text kind, decode fails (opcode itself carries), so
            # only the abs32 fallback explains it.
            0x24: (0x01 << 26) | 0x3FFFFF8,
            # 0x28: text kind, genuinely unexplained.
            0x28: 0x12345678,
            # 0x2C: data kind, genuinely unexplained.
            0x2C: 0xDEADBEEF,
        }
        new = dict(old)
        new[0x00] = 0xAAAAAAAA
        new[0x04] = old[0x04] + self.DELTA
        new[0x10] = (OPCODE_J << 26) | 0x104
        new[0x14] = (OPCODE_JAL << 26) | 0x204
        new[0x18] = (0x23 << 26) | (29 << 21) | (8 << 16) | 0x0020
        new[0x1C] = (0x23 << 26) | (29 << 21) | (9 << 16) | 0x0000
        new[0x20] = (OPCODE_LUI << 26) | (8 << 16) | 0x8001
        new[0x24] = old[0x24] + self.DELTA
        new[0x28] = 0x87654321
        new[0x2C] = 0xCAFEBABE

        span = 12 * 4  # 0x30
        base = bytearray(span)
        shifted_body = bytearray(span)
        for offset, value in old.items():
            base[offset : offset + 4] = word(value)
        for offset, value in new.items():
            shifted_body[offset : offset + 4] = word(value)

        self.base = bytes(base)
        # Insertion sits after every word this fixture defines, so the
        # pairing is purely positional and `shifted` just needs to be
        # DELTA bytes longer.
        self.shifted = bytes(shifted_body) + bytes(self.DELTA)
        self.insertion_offset = span

        self.regions = [
            RegionSpec(0x00, 0x08, "header"),
            RegionSpec(0x08, 0x10, "blob"),
            RegionSpec(0x10, 0x30, "text"),
        ]
        self.generated = [GeneratedSpec(0x00, 0x04, "crc-header")]
        self.moved_range = (0x80000400, 0x80001000)

    def census(self, **overrides):
        kwargs = dict(
            insertion_offset=self.insertion_offset,
            delta=self.DELTA,
            regions=self.regions,
            generated=self.generated,
            moved_range=self.moved_range,
        )
        kwargs.update(overrides)
        return build_word_census(self.base, self.shifted, **kwargs)

    def test_every_class_is_counted_once(self) -> None:
        result = self.census()

        self.assertEqual(
            result.counts,
            {
                "abs32-tracks": 2,  # 0x04 header + 0x24 text fallback
                "crc-header": 1,
                "hi16-adjust": 1,
                "j26-tracks": 2,
                "lo16-tracks": 2,
                "unexplained": 2,
            },
        )
        self.assertEqual(result.differing_total, 10)
        self.assertEqual(result.unexplained_total, 2)

    def test_generated_span_wins_before_any_decode(self) -> None:
        result = self.census()
        # 0x00's old/new bit patterns do not look like any tracked shape;
        # it is only explained because the generated span was checked first.
        self.assertNotIn(
            (0x00, 0x11111111, 0xAAAAAAAA),
            [(w.offset, w.old, w.new) for w in result.unexplained],
        )

    def test_equal_pair_inside_moved_range_is_stale(self) -> None:
        result = self.census()

        self.assertEqual(result.stale_total, 1)
        stale = result.stale[0]
        self.assertEqual(stale.offset, 0x08)
        self.assertEqual(stale.value, 0x80000450)
        self.assertEqual(stale.alignment, 0)

    def test_equal_pair_outside_moved_range_is_not_stale(self) -> None:
        result = self.census()
        self.assertNotIn(0x0C, [item.offset for item in result.stale])

    def test_stale_candidates_carry_range_model_features(self) -> None:
        model = RangeModel(windows=default_n64_windows())
        result = self.census(range_model=model)

        stale = result.stale[0]
        self.assertEqual(stale.window, "kseg0")
        self.assertFalse(stale.whitelisted)

    def test_unexplained_words_are_the_ones_no_class_covers(self) -> None:
        result = self.census()
        offsets = sorted(item.offset for item in result.unexplained)
        self.assertEqual(offsets, [0x28, 0x2C])

    def test_detail_cap_limits_samples_but_not_the_total_count(self) -> None:
        result = self.census(detail_cap=1)
        self.assertEqual(len(result.unexplained), 1)
        self.assertEqual(result.unexplained_total, 2)

    def test_as_dict_is_plain_json_ready_structures(self) -> None:
        result = self.census()
        payload = result.as_dict()
        self.assertIsInstance(payload["counts"], dict)
        self.assertIsInstance(payload["unexplained"], list)
        self.assertIsInstance(payload["stale"], list)
        self.assertEqual(payload["differing_total"], 10)

    def test_length_mismatch_against_declared_delta_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_word_census(
                self.base,
                self.shifted + b"\x00\x00\x00\x00",
                insertion_offset=self.insertion_offset,
                delta=self.DELTA,
            )

    def test_offset_outside_every_region_falls_back_to_default_kind(self) -> None:
        # Drop the text region so 0x10 (a j26-shaped word) is only covered
        # by `default_kind`; value-first still explains it because its
        # value happens to move by delta/4 in the wrong units, so it must
        # NOT be explained -- proving the fallback kind actually took over
        # rather than silently still decoding as text.
        result = build_word_census(
            self.base,
            self.shifted,
            insertion_offset=self.insertion_offset,
            delta=self.DELTA,
            regions=[RegionSpec(0x00, 0x08, "header")],
            generated=self.generated,
            default_kind="data",
        )
        self.assertIn(0x10, [item.offset for item in result.unexplained])


# ---------------------------------------------------------------------------
# Two-image pairing + word census -- live conformance against S0's ROMs
# ---------------------------------------------------------------------------


class WordCensusLiveConformanceTests(unittest.TestCase):
    """Replay S0's spike through this module's section-aware classifier.

    Region-aware, decode-first-in-text classification splits labels
    differently from S0's value-first spike (see the module docstring): a
    `%lo` immediate whose displacement did not sign-wrap moves by the same
    amount as a data pointer would, and the spike's value-first pass folded
    both into one `abs32-tracks` bucket. Decoding text before comparing
    values pulls those words out into `lo16-tracks` instead, so this test
    asserts the INVARIANTS the campaign specified rather than the spike's
    exact per-class split: differing total 20,687, unexplained 0, stale
    1,501, and every differing word accounted for by exactly one label.
    """

    @classmethod
    def setUpClass(cls) -> None:
        _skip_unless_images_present(cls)
        cls.base = BASE_IMAGE.read_bytes()
        cls.shifted = SHIFT_IMAGE.read_bytes()

    def build(self) -> object:
        regions = [
            RegionSpec(0x0, 0x40, "header"),
            RegionSpec(0x40, MAIN_ROM, "blob"),
            RegionSpec(MAIN_ROM, TEXT_END_ROM, "text"),
            RegionSpec(TEXT_END_ROM, len(self.base), "data"),
        ]
        generated = [GeneratedSpec(0x10, 0x18, "crc-header")]
        for vram in CHECKSUM_SYMBOL_VRAM.values():
            rom = vram - MAIN_VRAM + MAIN_ROM
            generated.append(GeneratedSpec(rom, rom + 4, "checksum-gen"))

        return build_word_census(
            self.base,
            self.shifted,
            insertion_offset=INSERTION_ROM,
            delta=DELTA,
            regions=regions,
            generated=generated,
            moved_range=(INSERTION_VRAM, MAIN_BSS_END_VRAM),
            detail_cap=200,
        )

    def test_image_grows_by_exactly_delta(self) -> None:
        self.assertEqual(len(self.shifted) - len(self.base), DELTA)

    def test_differing_total_matches_the_campaign_gate(self) -> None:
        result = self.build()
        self.assertEqual(result.differing_total, 20687)

    def test_zero_unexplained_words(self) -> None:
        result = self.build()
        self.assertEqual(result.unexplained_total, 0)
        self.assertEqual(result.unexplained, ())

    def test_stale_candidate_total_matches_the_dossier(self) -> None:
        result = self.build()
        self.assertEqual(result.stale_total, 1501)

    def test_every_differing_word_is_accounted_for_by_one_label(self) -> None:
        result = self.build()
        self.assertEqual(sum(result.counts.values()), result.differing_total)
        self.assertEqual(result.differing_total, 20687)
        self.assertNotIn("unexplained", result.counts)

    def test_crc_header_words_are_caught_by_the_generated_span(self) -> None:
        result = self.build()
        self.assertEqual(result.counts.get("crc-header"), 2)

    def test_the_sign_wrap_word_classifies_lo16_not_unexplained(self) -> None:
        """`__CSPPostNextSeqEvent+0x25c`, ROM 0x0bccd8: S0's one hit of the
        signed-%lo incident the module docstring describes."""

        offset = 0x0BCCD8
        old = struct.unpack_from(">I", self.base, offset)[0]
        new = struct.unpack_from(">I", self.shifted, offset + DELTA)[0]

        self.assertEqual(old, 0x8C2EFFF0)
        self.assertEqual(new, 0x8C2E0000)
        self.assertEqual(_classify_text_word(old, new, DELTA), "lo16-tracks")

        # And the full census agrees: this offset never appears among the
        # (empty) unexplained sample.
        result = self.build()
        self.assertNotIn(offset, [item.offset for item in result.unexplained])


if __name__ == "__main__":
    unittest.main()
