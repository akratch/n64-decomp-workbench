"""Tests for the GNU ``ld -Map`` reader.

Two tiers. The synthetic fixtures below are small, handcrafted excerpts --
not derived from any real project's map -- that each isolate one shape this
module has to parse: a section with and without ``AT()``, an input-section
record whose own name differs from the output section that swallows it, a
plain symbol next to a linker assignment, a wrapped section name, and the
overlapping-VMA case a DMA'd asset segment produces. The DKR conformance
tests below them replay the same assertions against the real ``us.v77``
shift-instrumentation maps produced by S0 (``.workbench/shift-instrumentation``
in the sibling ``decomp_playground`` checkout) and self-skip when that
checkout is not present -- the maps themselves are never copied into this
repository.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from decomp_workbench.ldmap import (
    InputSection,
    LdMap,
    LinkerSymbol,
    MovementAudit,
    OutputSection,
    SymbolMovement,
    TilingGap,
    audit_symbol_movement,
    audit_tiling,
    parse_ld_map,
    read_ld_map,
)

# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

#: Two output sections, one with `AT()` and one without, each carrying input
#: records whose own name differs from the output section they land in --
#: the shape a cascade linker script produces by concatenating unlike input
#: sections (`.text`, `.data`, ...) into one output section.
SECTIONS_MAP = """
Linker script and memory map

LOAD build/code.o
LOAD build/other.o

.boot           0x00000000       0x40
 FILL mask 0x00000000
 build/code.o(.text)
 .text          0x00000000       0x40 build/code.o

.main           0x80000400    0x1000 load address 0x00001000
 FILL mask 0x00000000
 build/code.o(.text)
 .text          0x80000400       0x20 build/code.o
 .text          0x80000428       0x18 build/other.o
 .data          0x80000440       0x10 build/code.o

OUTPUT(build/game.elf elf32-tradbigmips)
"""

#: Plain symbols, a linker assignment, a location-counter update (must be
#: dropped), and nothing else -- one output section is enough context.
SYMBOLS_MAP = """
Linker script and memory map

.main           0x80000400     0x100

                0x80000400                        main_TEXT_START = .
                0x80000400                start_function
                0x80000420                helper_function
                0x80000430                        gSomeChecksum = 0xdeadbeef
                0x80000440                        . = ALIGN (., 0x10)
                0x80000450                        main_TEXT_END = .
                0x80000460                weird thing here
"""

#: A section name and an input-section name each too wide for their column,
#: wrapped onto their own line the way `ld` really does it (see
#: `.MIPS.abiflags` in any real map).
WRAPPED_MAP = """
Linker script and memory map

.a_very_long_output_section_name_that_wraps
                0x80010000       0x40 load address 0x00002000
 .MIPS.abiflags
                0x80010000       0x18 build/code.o
"""

#: No "Linker script and memory map" heading at all.
NO_HEADER_MAP = """.tiny           0x80020000       0x10

 .text          0x80020000       0x10 build/code.o
                0x80020000                tiny_symbol
"""

#: `.header` carries no `AT()`; `.small_lut` and `.big_blob` share a VMA
#: start the way DKR's `.assets_lut`/`.assets` do (a DMA target segment
#: whose VMA is nominal, not simultaneously resident with the smaller
#: segment sharing its start).
LOOKUP_MAP = """
Linker script and memory map

.header         0x00000000       0x40

.main           0x80000400      0x100 load address 0x00001000
 .text          0x80000400       0x40 build/code.o
                0x80000400                entry_point
                0x80000420                middle_function

.small_lut      0x80001000        0x8 load address 0x00002000
 .data          0x80001000        0x8 build/lut.o

.big_blob       0x80001000     0x8000 load address 0x00002008
 .data          0x80001000     0x8000 build/blob.o
"""

#: Four input-section records: a.o/b.o leave a real gap, b.o/c.o tile
#: exactly (no finding), c.o/d.o overlap, and e.o is zero-size (excluded).
TILING_MAP = """
Linker script and memory map

.main           0x80000400      0x100
 .text          0x80000400       0x10 build/a.o
 .text          0x80000420       0x10 build/b.o
 .text          0x80000430       0x10 build/c.o
 .text          0x80000438       0x10 build/d.o
 .text          0x80000440        0x0 build/e.o
"""

#: A base/shifted pair for the movement audit: one symbol fixed, one moved
#: by the expected delta, one moved by an unexpected delta (the anomaly this
#: audit exists to catch), and one symbol unique to each side.
BASE_MOVEMENT_MAP = """
Linker script and memory map

.main           0x80000400      0x100
                0x80000400                fixed_symbol
                0x80000420                moved_symbol
                0x80000440                odd_symbol
                0x80000450                base_only_symbol
"""

SHIFTED_MOVEMENT_MAP = """
Linker script and memory map

.main           0x80000400      0x110
                0x80000400                fixed_symbol
                0x80000430                moved_symbol
                0x80000448                odd_symbol
                0x80000460                shifted_only_symbol
"""


class OutputSectionParsingTests(unittest.TestCase):
    def test_a_section_with_at_carries_its_load_address(self) -> None:
        parsed = parse_ld_map(SECTIONS_MAP)
        main = next(item for item in parsed.sections if item.name == ".main")
        self.assertEqual(main.vma, 0x80000400)
        self.assertEqual(main.size, 0x1000)
        self.assertEqual(main.load_address, 0x00001000)

    def test_a_section_without_at_has_no_load_address(self) -> None:
        parsed = parse_ld_map(SECTIONS_MAP)
        boot = next(item for item in parsed.sections if item.name == ".boot")
        self.assertEqual(boot.vma, 0x0)
        self.assertEqual(boot.size, 0x40)
        self.assertIsNone(boot.load_address)

    def test_section_end_and_contains(self) -> None:
        section = OutputSection(name=".x", vma=0x1000, size=0x10, load_address=None)
        self.assertEqual(section.end, 0x1010)
        self.assertTrue(section.contains(0x1000))
        self.assertTrue(section.contains(0x100F))
        self.assertFalse(section.contains(0x1010))

    def test_a_zero_size_section_contains_only_its_own_address(self) -> None:
        section = OutputSection(name=".empty", vma=0x2000, size=0, load_address=None)
        self.assertTrue(section.contains(0x2000))
        self.assertFalse(section.contains(0x2001))


class InputSectionParsingTests(unittest.TestCase):
    def test_input_records_carry_their_own_name_distinct_from_output_section(
        self,
    ) -> None:
        """The bug a quick DKR smoke test caught: `.data` inside `.main` is
        not the same thing as `.main` itself, and only `name` tells them
        apart when a cascade script concatenates unlike sections."""

        parsed = parse_ld_map(SECTIONS_MAP)
        data_record = next(
            item
            for item in parsed.input_sections
            if item.object_path == "build/code.o" and item.vma == 0x80000440
        )
        self.assertEqual(data_record.name, ".data")
        self.assertEqual(data_record.output_section, ".main")

    def test_two_objects_can_both_contribute_text_to_one_output_section(self) -> None:
        parsed = parse_ld_map(SECTIONS_MAP)
        text_records = [
            item
            for item in parsed.input_sections
            if item.output_section == ".main" and item.name == ".text"
        ]
        self.assertEqual(
            sorted((item.vma, item.size, item.object_path) for item in text_records),
            [
                (0x80000400, 0x20, "build/code.o"),
                (0x80000428, 0x18, "build/other.o"),
            ],
        )

    def test_boot_input_record_belongs_to_boot(self) -> None:
        parsed = parse_ld_map(SECTIONS_MAP)
        boot_text = next(
            item for item in parsed.input_sections if item.output_section == ".boot"
        )
        self.assertEqual(boot_text.name, ".text")
        self.assertEqual(boot_text.vma, 0x0)
        self.assertEqual(boot_text.size, 0x40)
        self.assertEqual(boot_text.object_path, "build/code.o")

    def test_input_section_end_and_contains(self) -> None:
        record = InputSection(
            name=".text",
            output_section=".main",
            vma=0x80000400,
            size=0x20,
            object_path="build/code.o",
        )
        self.assertEqual(record.end, 0x80000420)
        self.assertTrue(record.contains(0x80000400))
        self.assertFalse(record.contains(0x80000420))


class SymbolParsingTests(unittest.TestCase):
    def test_plain_symbols_are_not_flagged_as_assignments(self) -> None:
        parsed = parse_ld_map(SYMBOLS_MAP)
        start = parsed.symbol("start_function")
        self.assertIsNotNone(start)
        assert start is not None
        self.assertEqual(start.address, 0x80000400)
        self.assertFalse(start.is_assignment)
        self.assertIsNone(start.expression)

    def test_assignment_symbols_carry_their_expression(self) -> None:
        parsed = parse_ld_map(SYMBOLS_MAP)
        checksum = parsed.symbol("gSomeChecksum")
        self.assertIsNotNone(checksum)
        assert checksum is not None
        self.assertEqual(checksum.address, 0x80000430)
        self.assertTrue(checksum.is_assignment)
        self.assertEqual(checksum.expression, "0xdeadbeef")

    def test_location_counter_updates_are_not_symbols(self) -> None:
        parsed = parse_ld_map(SYMBOLS_MAP)
        self.assertNotIn(".", parsed.symbol_names())
        # Only the six real names below should have made it through, out of
        # seven address-prefixed lines in the fixture (the `.` update and
        # the trailing unrecognized-shape line are both dropped).
        self.assertEqual(
            parsed.symbol_names(),
            {
                "main_TEXT_START",
                "start_function",
                "helper_function",
                "gSomeChecksum",
                "main_TEXT_END",
            },
        )

    def test_an_unrecognized_address_line_shape_is_skipped_not_raised(self) -> None:
        # "weird thing here" is neither a bare name nor `NAME = expr`.
        parsed = parse_ld_map(SYMBOLS_MAP)
        self.assertNotIn("weird", parsed.symbol_names())
        self.assertEqual(len(parsed.symbols), 5)

    def test_linker_symbol_as_dict(self) -> None:
        symbol = LinkerSymbol(
            name="foo", address=0x10, is_assignment=True, expression="bar"
        )
        self.assertEqual(
            symbol.as_dict(),
            {
                "name": "foo",
                "address": 0x10,
                "is_assignment": True,
                "expression": "bar",
            },
        )


class WrappedLineParsingTests(unittest.TestCase):
    def test_a_wrapped_output_section_name_is_merged(self) -> None:
        parsed = parse_ld_map(WRAPPED_MAP)
        self.assertEqual(len(parsed.sections), 1)
        section = parsed.sections[0]
        self.assertEqual(section.name, ".a_very_long_output_section_name_that_wraps")
        self.assertEqual(section.vma, 0x80010000)
        self.assertEqual(section.size, 0x40)
        self.assertEqual(section.load_address, 0x2000)

    def test_a_wrapped_input_section_name_is_merged(self) -> None:
        parsed = parse_ld_map(WRAPPED_MAP)
        self.assertEqual(len(parsed.input_sections), 1)
        record = parsed.input_sections[0]
        self.assertEqual(record.name, ".MIPS.abiflags")
        self.assertEqual(
            record.output_section, ".a_very_long_output_section_name_that_wraps"
        )
        self.assertEqual(record.vma, 0x80010000)
        self.assertEqual(record.size, 0x18)
        self.assertEqual(record.object_path, "build/code.o")


class HeaderlessParsingTests(unittest.TestCase):
    def test_text_with_no_heading_is_read_from_the_top(self) -> None:
        parsed = parse_ld_map(NO_HEADER_MAP)
        self.assertEqual(len(parsed.sections), 1)
        self.assertEqual(parsed.sections[0].name, ".tiny")
        self.assertEqual(len(parsed.input_sections), 1)
        self.assertIsNotNone(parsed.symbol("tiny_symbol"))


class LookupApiTests(unittest.TestCase):
    def test_symbol_by_name_returns_none_when_absent(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.symbol("does_not_exist"))

    def test_symbol_containing_returns_nearest_at_or_below_with_offset(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        result = parsed.symbol_containing(0x80000430)
        self.assertIsNotNone(result)
        assert result is not None
        symbol, offset = result
        self.assertEqual(symbol.name, "middle_function")
        self.assertEqual(offset, 0x10)

    def test_symbol_containing_an_exact_address_has_zero_offset(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        result = parsed.symbol_containing(0x80000420)
        self.assertIsNotNone(result)
        assert result is not None
        symbol, offset = result
        self.assertEqual(symbol.name, "middle_function")
        self.assertEqual(offset, 0)

    def test_symbol_containing_below_every_symbol_is_none(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.symbol_containing(0x1))

    def test_symbols_sorted_is_ascending_by_address(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        addresses = [item.address for item in parsed.symbols_sorted()]
        self.assertEqual(addresses, sorted(addresses))

    def test_sections_sorted_is_ascending_by_vma(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        vmas = [item.vma for item in parsed.sections_sorted()]
        self.assertEqual(vmas, sorted(vmas))

    def test_section_containing_picks_the_smallest_overlapping_extent(self) -> None:
        """`.small_lut` and `.big_blob` share a VMA start; the more specific
        (smaller) one is the useful answer, exactly as it is for DKR's
        `.assets_lut` inside `.assets`."""

        parsed = parse_ld_map(LOOKUP_MAP)
        section = parsed.section_containing(0x80001004)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.name, ".small_lut")

    def test_section_containing_outside_every_extent_is_none(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.section_containing(0x90000000))

    def test_input_section_containing(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        record = parsed.input_section_containing(0x80000410)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.object_path, "build/code.o")

    def test_input_sections_sorted_is_ascending_by_vma(self) -> None:
        parsed = parse_ld_map(TILING_MAP)
        vmas = [item.vma for item in parsed.input_sections_sorted()]
        self.assertEqual(vmas, sorted(vmas))


class TranslationTests(unittest.TestCase):
    def test_rom_for_vram_inside_an_at_section(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertEqual(parsed.rom_for_vram(0x80000410), 0x1010)

    def test_vram_for_rom_is_the_inverse(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertEqual(parsed.vram_for_rom(0x1010), 0x80000410)

    def test_rom_for_vram_outside_every_at_section_is_none(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.rom_for_vram(0x90000000))

    def test_a_section_without_at_is_not_assumed_lma_equals_vma(self) -> None:
        """`.header` has no declared load address; a VRAM address inside it
        must not silently resolve to "ROM offset == VRAM address" -- see the
        module docstring for why that default is not safe to assume."""

        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.rom_for_vram(0x10))

    def test_rom_for_vram_prefers_the_smaller_overlapping_section(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        # 0x80001004 is inside both `.small_lut` (load 0x2000) and
        # `.big_blob` (load 0x2008); the smaller, more specific section's
        # mapping is the one returned.
        self.assertEqual(parsed.rom_for_vram(0x80001004), 0x2004)

    def test_vram_for_rom_outside_every_at_section_is_none(self) -> None:
        parsed = parse_ld_map(LOOKUP_MAP)
        self.assertIsNone(parsed.vram_for_rom(0x50000))


class TilingAuditTests(unittest.TestCase):
    def test_a_real_gap_is_reported(self) -> None:
        findings = audit_tiling(parse_ld_map(TILING_MAP))
        gaps = [item for item in findings if item.kind == "gap"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].low.object_path, "build/a.o")
        self.assertEqual(gaps[0].high.object_path, "build/b.o")
        self.assertEqual(gaps[0].gap, 0x10)

    def test_an_overlap_is_reported_with_a_negative_gap(self) -> None:
        findings = audit_tiling(parse_ld_map(TILING_MAP))
        overlaps = [item for item in findings if item.kind == "overlap"]
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0].low.object_path, "build/c.o")
        self.assertEqual(overlaps[0].high.object_path, "build/d.o")
        self.assertEqual(overlaps[0].gap, -0x8)
        self.assertEqual(overlaps[0].as_dict()["bytes"], 0x8)

    def test_an_exact_tile_produces_no_finding(self) -> None:
        # b.o ends where c.o starts: not in the findings at all.
        findings = audit_tiling(parse_ld_map(TILING_MAP))
        pairs = {(item.low.object_path, item.high.object_path) for item in findings}
        self.assertNotIn(("build/b.o", "build/c.o"), pairs)

    def test_zero_size_records_are_excluded_from_the_walk(self) -> None:
        findings = audit_tiling(parse_ld_map(TILING_MAP))
        objects = {item.low.object_path for item in findings} | {
            item.high.object_path for item in findings
        }
        self.assertNotIn("build/e.o", objects)

    def test_tiling_gap_as_dict(self) -> None:
        gap = TilingGap(
            output_section=".main",
            low=InputSection(
                name=".text",
                output_section=".main",
                vma=0,
                size=0x10,
                object_path="a.o",
            ),
            high=InputSection(
                name=".text",
                output_section=".main",
                vma=0x20,
                size=0x10,
                object_path="b.o",
            ),
            gap=0x10,
        )
        self.assertEqual(gap.kind, "gap")
        self.assertEqual(gap.as_dict()["bytes"], 0x10)
        self.assertEqual(gap.as_dict()["kind"], "gap")


class MovementAuditTests(unittest.TestCase):
    def _audit(self, *, allowed_deltas: tuple[int, ...] = (0, 0x10)) -> MovementAudit:
        base = parse_ld_map(BASE_MOVEMENT_MAP, path="base.map")
        shifted = parse_ld_map(SHIFTED_MOVEMENT_MAP, path="shifted.map")
        return audit_symbol_movement(base, shifted, allowed_deltas=allowed_deltas)

    def test_every_shared_symbol_gets_a_movement(self) -> None:
        audit = self._audit()
        names = {item.name for item in audit.movements}
        self.assertEqual(names, {"fixed_symbol", "moved_symbol", "odd_symbol"})

    def test_deltas_are_computed_correctly(self) -> None:
        audit = self._audit()
        by_name = {item.name: item.delta for item in audit.movements}
        self.assertEqual(by_name["fixed_symbol"], 0)
        self.assertEqual(by_name["moved_symbol"], 0x10)
        self.assertEqual(by_name["odd_symbol"], 0x8)

    def test_a_delta_outside_the_allowed_set_is_an_anomaly(self) -> None:
        audit = self._audit(allowed_deltas=(0, 0x10))
        self.assertEqual(audit.anomalous_names, frozenset({"odd_symbol"}))
        self.assertEqual(len(audit.anomalies), 1)
        self.assertEqual(audit.anomalies[0].name, "odd_symbol")

    def test_widening_the_allowed_set_clears_the_anomaly(self) -> None:
        audit = self._audit(allowed_deltas=(0, 0x8, 0x10))
        self.assertEqual(audit.anomalies, ())

    def test_symbols_unique_to_one_side_are_reported_separately(self) -> None:
        audit = self._audit()
        self.assertEqual(audit.only_in_base, ("base_only_symbol",))
        self.assertEqual(audit.only_in_shifted, ("shifted_only_symbol",))
        # Not counted as anomalies: they never had a shared delta to judge.
        self.assertNotIn("base_only_symbol", audit.anomalous_names)
        self.assertNotIn("shifted_only_symbol", audit.anomalous_names)

    def test_default_allowed_deltas_is_zero_only(self) -> None:
        base = parse_ld_map(BASE_MOVEMENT_MAP)
        shifted = parse_ld_map(SHIFTED_MOVEMENT_MAP)
        audit = audit_symbol_movement(base, shifted)
        self.assertEqual(
            audit.anomalous_names, frozenset({"moved_symbol", "odd_symbol"})
        )

    def test_symbol_movement_delta_property(self) -> None:
        movement = SymbolMovement(name="x", base_address=0x10, shifted_address=0x20)
        self.assertEqual(movement.delta, 0x10)

    def test_movement_audit_as_dict_summarizes_without_dumping_every_row(self) -> None:
        audit = self._audit()
        payload = audit.as_dict()
        self.assertEqual(payload["shared_symbols"], 3)
        self.assertEqual(len(payload["anomalies"]), 1)
        self.assertEqual(payload["only_in_base"], ["base_only_symbol"])
        self.assertEqual(payload["only_in_shifted"], ["shifted_only_symbol"])


class ReadLdMapTests(unittest.TestCase):
    def test_read_ld_map_reads_and_parses_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.map"
            path.write_text(NO_HEADER_MAP, encoding="utf-8")
            parsed = read_ld_map(path)
            self.assertEqual(parsed.path, str(path))
            self.assertIsNotNone(parsed.symbol("tiny_symbol"))


# --------------------------------------------------------------------------
# DKR conformance (S0 shift-instrumentation artifacts) -- skips gracefully
# when the sibling decomp_playground checkout is not present.
# --------------------------------------------------------------------------

S0_DIR = (
    Path(__file__).resolve().parents[2]
    / "decomp_playground"
    / ".workbench"
    / "shift-instrumentation"
    / "s0"
)
BASE_MAP_PATH = S0_DIR / "nm-base" / "dkr.us.v77.map"
SHIFT_10_MAP_PATH = S0_DIR / "shift-0x10" / "dkr.us.v77.map"
SHIFT_40_MAP_PATH = S0_DIR / "shift-0x40" / "dkr.us.v77.map"

_HAVE_S0 = BASE_MAP_PATH.is_file() and SHIFT_10_MAP_PATH.is_file()


@unittest.skipUnless(
    _HAVE_S0,
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrConformanceTests(unittest.TestCase):
    """Replays S0's hand-verified findings through this module's API.

    Every number here was independently confirmed against the map text with
    `grep` before being written into this test (see this campaign stage's
    hand-off notes), so a failure here means this module disagrees with the
    ground truth S0 established by hand, not a change in the fixture.
    """

    base: ClassVar[LdMap]
    shifted: ClassVar[LdMap]

    @classmethod
    def setUpClass(cls) -> None:
        cls.base = read_ld_map(BASE_MAP_PATH)
        cls.shifted = read_ld_map(SHIFT_10_MAP_PATH)

    def test_entrypoint_text_input_section_is_0x50_bytes(self) -> None:
        record = next(
            item
            for item in self.base.input_sections
            if item.name == ".text"
            and item.object_path == "build/src/hasm/entrypoint.s.o"
        )
        self.assertEqual(record.size, 0x50)

    def test_race_check_checksum_symbol_is_at_its_known_address(self) -> None:
        symbol = self.base.symbol("gRaceCheckFinishChecksum")
        self.assertIsNotNone(symbol)
        assert symbol is not None
        self.assertEqual(symbol.address, 0x800D1DB0)
        self.assertFalse(symbol.is_assignment)

    def test_main_bss_end_exists_as_a_linker_assignment(self) -> None:
        symbol = self.base.symbol("main_BSS_END")
        self.assertIsNotNone(symbol)
        assert symbol is not None
        self.assertTrue(symbol.is_assignment)

    def test_more_than_3800_symbols_parse(self) -> None:
        # Measured directly against `us.v77`'s map: 3,895 address-prefixed
        # symbol/assignment lines in the "Linker script and memory map"
        # body (3,777 plain + 118 assignment), 3,889 distinct names. That is
        # short of the >4000 the campaign plan sketched from memory, so the
        # threshold here is the real measured count with a safety margin,
        # not the sketch -- see this stage's hand-off notes for the
        # reconciliation.
        self.assertGreater(len(self.base.symbols), 3800)

    def test_movement_audit_between_base_and_shift_0x10_has_no_anomalies(self) -> None:
        audit = audit_symbol_movement(self.base, self.shifted, allowed_deltas=(0, 0x10))
        deltas = {item.delta for item in audit.movements}
        self.assertEqual(deltas, {0, 0x10})
        self.assertEqual(audit.anomalies, ())
        self.assertEqual(audit.anomalous_names, frozenset())

    def test_section_containing_prefers_assets_lut_over_assets(self) -> None:
        """The real overlapping-VMA case `LookupApiTests` synthesizes: DKR's
        `.assets_lut` and `.assets` both start at the same VMA."""

        section = self.base.section_containing(0x80122650)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(section.name, ".assets_lut")

    def test_rom_for_vram_round_trips_through_assets_lut(self) -> None:
        self.assertEqual(self.base.rom_for_vram(0x80122610), 0x000E1240)
        self.assertEqual(self.base.vram_for_rom(0x000E1240), 0x80122610)


@unittest.skipUnless(
    BASE_MAP_PATH.is_file() and SHIFT_40_MAP_PATH.is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrSecondDeltaConformanceTest(unittest.TestCase):
    """S0 ran two independent deltas (0x10 and 0x40) to rule out a
    delta-specific coincidence; this module is checked against both."""

    def test_movement_audit_between_base_and_shift_0x40_has_no_anomalies(self) -> None:
        base = read_ld_map(BASE_MAP_PATH)
        shifted = read_ld_map(SHIFT_40_MAP_PATH)
        audit = audit_symbol_movement(base, shifted, allowed_deltas=(0, 0x40))
        deltas = {item.delta for item in audit.movements}
        self.assertEqual(deltas, {0, 0x40})
        self.assertEqual(audit.anomalies, ())


if __name__ == "__main__":
    unittest.main()
