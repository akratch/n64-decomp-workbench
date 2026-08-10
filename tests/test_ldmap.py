"""Tests for the linked-artifact symbol readers: the map, and the ELF.

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

The ELF half (WB-143) has the same two tiers. `build_elf` below assembles a
big-endian ELF32 byte by byte -- header, section table, ``.symtab``,
``.strtab``, ``.shstrtab`` -- so every field the reader depends on is written
by the test rather than borrowed from a build somebody else produced. The
pilotwings64 conformance test reads the real linked ELF from S6's experiment
and asserts the one fact the whole shadowing rule rests on: the ten pins that
experiment ablated carry an inherited ``st_size`` and the other twenty-seven
do not.
"""

from __future__ import annotations

import struct
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from decomp_workbench.ldmap import (
    SHN_ABS,
    SHN_UNDEF,
    ElfFormatError,
    InputSection,
    LdMap,
    LinkerSymbol,
    MovementAudit,
    OutputSection,
    SymbolMovement,
    TilingGap,
    audit_symbol_movement,
    audit_tiling,
    parse_elf_symbols,
    parse_ld_map,
    read_elf_symbols,
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

#: Three output sections sharing one VMA start with distinct `AT()` load
#: addresses -- the N64 overlay-group shape (Banjo-Kazooie's `.CC`/`.GV`/
#: `.MMM` and eleven more all start at ``0x803863f0``, each with its own
#: load address), geometrically identical to `LOOKUP_MAP`'s
#: ``.small_lut``/``.big_blob`` (same VMA start, different sizes) but a
#: different real-world shape: none of these three nests inside another as a
#: lookup table for it, and none is ever resident at the same time as
#: another -- they are mutually exclusive runtime alternatives at one shared
#: window.
OVERLAY_MAP = """
Linker script and memory map

.overlay_a      0x80386000      0x100 load address 0x00100000
 .text          0x80386000      0x100 build/a.o

.overlay_b      0x80386000       0x40 load address 0x00200000
 .text          0x80386000       0x40 build/b.o

.overlay_c      0x80386000       0x10 load address 0x00300000
 .text          0x80386000       0x10 build/c.o
"""

#: The same ambiguity, mirrored onto the ROM side: two sections whose
#: ``AT()`` load ranges share a start (``.rom_lut`` nested inside
#: ``.rom_blob``, the same shape as ``.small_lut``/``.big_blob`` above) so
#: `sections_loaded_at`/`vram_for_rom` have something to disambiguate.
OVERLAY_ROM_MAP = """
Linker script and memory map

.rom_lut        0x80400000        0x8 load address 0x00050000
 .data          0x80400000        0x8 build/lut.o

.rom_blob       0x80500000     0x1000 load address 0x00050000
 .data          0x80500000     0x1000 build/blob.o
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


class OverlayAmbiguityTests(unittest.TestCase):
    """WB-139: `sections_containing`/`sections_loaded_at` hand back every
    candidate for a shared start address instead of picking one -- the
    honest version of what `section_containing`/`rom_for_vram`/
    `vram_for_rom` still only answer partially (unchanged on purpose: see
    those tests below)."""

    def test_sections_containing_returns_every_overlay_candidate(self) -> None:
        parsed = parse_ld_map(OVERLAY_MAP)
        candidates = parsed.sections_containing(0x80386000)
        self.assertEqual(
            [item.name for item in candidates],
            [".overlay_c", ".overlay_b", ".overlay_a"],
        )

    def test_sections_containing_is_smallest_first_matching_the_single_answer(
        self,
    ) -> None:
        parsed = parse_ld_map(OVERLAY_MAP)
        candidates = parsed.sections_containing(0x80386000)
        self.assertEqual(candidates[0], parsed.section_containing(0x80386000))

    def test_sections_containing_outside_every_extent_is_empty(self) -> None:
        parsed = parse_ld_map(OVERLAY_MAP)
        self.assertEqual(parsed.sections_containing(0x90000000), ())

    def test_section_containing_still_only_answers_the_smallest_for_an_overlay_group(
        self,
    ) -> None:
        """Documented as arbitrary for this shape, not fixed to refuse: an
        existing caller (`shift rehearse`) depends on this method's return
        type staying `OutputSection | None`."""

        parsed = parse_ld_map(OVERLAY_MAP)
        section = parsed.section_containing(0x80386000)
        assert section is not None
        self.assertEqual(section.name, ".overlay_c")

    def test_rom_for_vram_resolves_through_the_smallest_overlay_candidate(self) -> None:
        parsed = parse_ld_map(OVERLAY_MAP)
        # `.overlay_c` (size 0x10) is the smallest of the three candidates at
        # this VMA, so its load address answers -- the same arbitrary pick
        # `section_containing` makes, not a refusal.
        self.assertEqual(parsed.rom_for_vram(0x80386000), 0x00300000)

    def test_sections_loaded_at_returns_every_rom_side_candidate(self) -> None:
        parsed = parse_ld_map(OVERLAY_ROM_MAP)
        candidates = parsed.sections_loaded_at(0x00050004)
        self.assertEqual([item.name for item in candidates], [".rom_lut", ".rom_blob"])

    def test_sections_loaded_at_is_smallest_first_matching_vram_for_rom(self) -> None:
        parsed = parse_ld_map(OVERLAY_ROM_MAP)
        candidates = parsed.sections_loaded_at(0x00050004)
        self.assertEqual(candidates[0].name, ".rom_lut")
        self.assertEqual(parsed.vram_for_rom(0x00050004), 0x80400004)

    def test_sections_loaded_at_outside_every_load_range_is_empty(self) -> None:
        parsed = parse_ld_map(OVERLAY_ROM_MAP)
        self.assertEqual(parsed.sections_loaded_at(0x00090000), ())


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

    def test_sections_containing_is_exactly_the_nested_pair(self) -> None:
        """DKR's own shared-VMA case is real nesting, not an overlay group:
        exactly two candidates, `.assets_lut` inside `.assets`."""

        candidates = self.base.sections_containing(0x80122650)
        self.assertEqual([item.name for item in candidates], [".assets_lut", ".assets"])


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


# --------------------------------------------------------------------------
# Banjo-Kazooie conformance (S5's first real-patient `shift audit` run) --
# skips gracefully when the sibling decomp_playground checkout is absent.
# --------------------------------------------------------------------------

BK_MAP_PATH = (
    Path(__file__).resolve().parents[2]
    / "decomp_playground"
    / "banjo-kazooie"
    / "build"
    / "us.v10"
    / "banjo.us.v10.map"
)

_HAVE_BK = BK_MAP_PATH.is_file()


@unittest.skipUnless(_HAVE_BK, f"Banjo-Kazooie map not found at {BK_MAP_PATH}")
class BkOverlayAmbiguityConformanceTest(unittest.TestCase):
    """WB-139's real evidence: BK's map places fourteen overlay sections at
    one shared VMA, ``0x803863f0``, each with its own distinct ``AT()`` load
    address -- the real-world shape `OverlayAmbiguityTests` synthesizes small.
    """

    def test_sections_containing_returns_every_real_overlay_candidate(self) -> None:
        ldmap = read_ld_map(BK_MAP_PATH)
        candidates = ldmap.sections_containing(0x803863F0)
        names = {item.name for item in candidates}
        overlay_names = {
            ".CC",
            ".GV",
            ".MMM",
            ".TTC",
            ".MM",
            ".BGS",
            ".RBB",
            ".FP",
            ".SM",
            ".cutscenes",
            ".lair",
            ".fight",
            ".CCW",
            ".emptyLvl",
        }
        self.assertLessEqual(overlay_names, names)
        # `.assets`, BK's own DMA'd asset blob (DKR calls its version by the
        # same name), also legitimately contains this address: it is a huge
        # section spanning most of the address space, not a fifteenth
        # overlay -- present here for the same reason DKR's `.assets` shows
        # up in `DkrConformanceTests`'s own `sections_containing` test.
        self.assertEqual(names - overlay_names, {".assets"})
        self.assertEqual(len(candidates), 15)
        # Smallest first, matching `section_containing`'s single answer.
        self.assertEqual(candidates[0], ldmap.section_containing(0x803863F0))


# --------------------------------------------------------------------------
# The ELF symbol reader (WB-143)
# --------------------------------------------------------------------------

#: One `Elf32_Sym`.
_SYM = struct.Struct(">IIIBBH")
#: One `Elf32_Shdr`.
_SHDR = struct.Struct(">10I")


def build_elf(
    sections: Sequence[tuple[str, int, int, int]],
    symbols: Sequence[tuple[str, int, int, int, int, int]],
    *,
    encoding: int = 2,
    elf_class: int = 1,
    with_symtab: bool = True,
) -> bytes:
    """Assemble a big-endian ELF32 with exactly the symbols named.

    ``sections`` is ``(name, address, size, flags)`` and ``symbols`` is
    ``(name, value, size, type, binding, shndx)``. Written out by hand rather
    than produced by a linker so that every field the reader keys on -- and
    the ones it must ignore -- is chosen here: an absolute symbol carrying an
    inherited size is the whole WB-143 rule, and there is no way to ask a
    toolchain for one on demand.
    """

    names = [""] + [item[0] for item in sections] + [".shstrtab", ".symtab", ".strtab"]
    shstr = b"\x00".join(item.encode() for item in names) + b"\x00"
    offsets: dict[str, int] = {}
    position = 0
    for name in names:
        offsets[name] = position
        position += len(name) + 1

    symbol_names = [""] + [item[0] for item in symbols]
    strtab = b"\x00".join(item.encode() for item in symbol_names) + b"\x00"
    string_offsets: dict[str, int] = {}
    position = 0
    for name in symbol_names:
        string_offsets.setdefault(name, position)
        position += len(name) + 1

    symtab = _SYM.pack(0, 0, 0, 0, 0, 0)
    for name, value, size, kind, binding, shndx in symbols:
        symtab += _SYM.pack(
            string_offsets[name], value, size, (binding << 4) | kind, 0, shndx
        )

    header_size = 52
    body = shstr + strtab + symtab
    body_offset = header_size
    shstr_offset = body_offset
    strtab_offset = shstr_offset + len(shstr)
    symtab_offset = strtab_offset + len(strtab)
    table_offset = symtab_offset + len(symtab)

    # Index 0 is the null section; then the caller's, then the three the
    # reader itself has to find.
    count = 1 + len(sections) + 3
    shstrtab_index = 1 + len(sections)
    symtab_index = shstrtab_index + 1
    strtab_index = symtab_index + 1

    headers = [_SHDR.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for name, address, size, flags in sections:
        headers.append(
            _SHDR.pack(offsets[name], 1, flags, address, body_offset, size, 0, 0, 1, 0)
        )
    headers.append(
        _SHDR.pack(offsets[".shstrtab"], 3, 0, 0, shstr_offset, len(shstr), 0, 0, 1, 0)
    )
    if with_symtab:
        headers.append(
            _SHDR.pack(
                offsets[".symtab"],
                2,
                0,
                0,
                symtab_offset,
                len(symtab),
                strtab_index,
                0,
                4,
                16,
            )
        )
    else:
        # A stripped link: the section is present but is not a symbol table.
        headers.append(
            _SHDR.pack(offsets[".symtab"], 1, 0, 0, symtab_offset, 0, 0, 0, 1, 0)
        )
    headers.append(
        _SHDR.pack(offsets[".strtab"], 3, 0, 0, strtab_offset, len(strtab), 0, 0, 1, 0)
    )

    identity = bytes([0x7F]) + b"ELF" + bytes([elf_class, encoding, 1]) + bytes(9)
    header = identity + struct.pack(
        ">HHIIIIIHHHHHH",
        2,  # e_type
        8,  # e_machine (MIPS)
        1,  # e_version
        0,  # e_entry
        0,  # e_phoff
        table_offset,  # e_shoff
        0,  # e_flags
        header_size,  # e_ehsize
        0,  # e_phentsize
        0,  # e_phnum
        _SHDR.size,  # e_shentsize
        count,  # e_shnum
        shstrtab_index,  # e_shstrndx
    )
    return header + body + b"".join(headers)


#: One link with every shape the reader has to tell apart: an ordinary
#: object-backed function, an absolute pin with no object behind it, an
#: absolute pin that shadowed one (the size is the evidence), an undefined
#: reference, and the two symbol kinds that name a file and a section rather
#: than an address.
SHADOW_ELF = build_elf(
    sections=[(".text", 0x80000400, 0x100, 0x6), (".bss", 0x80000500, 0x80, 0x3)],
    symbols=[
        ("func_a", 0x80000400, 0x40, 2, 1, 1),
        ("gCounter", 0x80000500, 0x4, 1, 1, 2),
        ("D_80000540", 0x80000540, 0x8, 1, 1, SHN_ABS),
        ("D_B0000574", 0xB0000574, 0x0, 0, 1, SHN_ABS),
        ("osSyncPrintf", 0x0, 0x0, 2, 1, SHN_UNDEF),
        ("code_a.c", 0x0, 0x0, 4, 0, SHN_ABS),
        (".text", 0x80000400, 0x0, 3, 0, 1),
    ],
)


class ElfSymbolReaderTests(unittest.TestCase):
    """The three facts a linker map cannot print, read off the ELF."""

    def setUp(self) -> None:
        self.elf = parse_elf_symbols(SHADOW_ELF, path="fixture.elf")

    def test_a_file_symbol_and_a_section_symbol_are_not_addresses(self) -> None:
        """Both name something other than a place a project can pin.

        A ``file`` symbol arrives absolute at value 0 and a ``section``
        symbol duplicates a section's own start; keeping either would put a
        name into a census that no pin, reference or shift can ever be about.
        """

        self.assertEqual(
            sorted(self.elf.names()),
            ["D_80000540", "D_B0000574", "func_a", "gCounter", "osSyncPrintf"],
        )

    def test_an_object_backed_symbol_names_its_own_section(self) -> None:
        symbol = self.elf.symbol("func_a")
        assert symbol is not None
        self.assertTrue(symbol.is_object_backed)
        self.assertFalse(symbol.is_absolute)
        self.assertEqual(symbol.section, ".text")
        self.assertEqual(symbol.kind, "func")
        self.assertEqual(symbol.binding, "global")
        self.assertFalse(symbol.shadows_definition)

    def test_an_absolute_symbol_is_owned_by_nothing(self) -> None:
        symbol = self.elf.symbol("D_B0000574")
        assert symbol is not None
        self.assertTrue(symbol.is_absolute)
        self.assertFalse(symbol.is_object_backed)
        self.assertIsNone(symbol.section)
        self.assertEqual(symbol.kind, "notype")

    def test_the_shadowing_rule_is_the_inherited_size(self) -> None:
        """WB-143's whole discriminator, isolated.

        ``D_80000540`` and ``D_B0000574`` are both absolute and both global.
        One carries a size and a type it could only have inherited from an
        object definition the script assignment overrode; the other never had
        an object behind it and arrives ``notype``, size 0.
        """

        shadow = self.elf.symbol("D_80000540")
        plain = self.elf.symbol("D_B0000574")
        assert shadow is not None and plain is not None
        self.assertTrue(shadow.shadows_definition)
        self.assertEqual((shadow.size, shadow.kind), (8, "object"))
        self.assertFalse(plain.shadows_definition)
        self.assertEqual((plain.size, plain.kind), (0, "notype"))

    def test_an_undefined_symbol_is_neither(self) -> None:
        symbol = self.elf.symbol("osSyncPrintf")
        assert symbol is not None
        self.assertTrue(symbol.is_undefined)
        self.assertFalse(symbol.is_object_backed)
        self.assertFalse(symbol.shadows_definition)

    def test_section_at_resolves_an_absolute_value_to_its_owner(self) -> None:
        """The remediation evidence: a pin's value lands *somewhere*."""

        owner = self.elf.section_at(0x80000540)
        assert owner is not None
        self.assertEqual(owner.name, ".bss")
        self.assertIsNone(self.elf.section_at(0xB0000574))

    def test_the_path_travels_with_the_parse(self) -> None:
        self.assertEqual(self.elf.path, "fixture.elf")


class ElfRefusalTests(unittest.TestCase):
    """Every input this reader refuses rather than mis-measuring."""

    def test_a_file_that_is_not_an_elf(self) -> None:
        with self.assertRaises(ElfFormatError) as caught:
            parse_elf_symbols(b"\x80\x37\x12\x40" + bytes(200), path="rom.z64")
        self.assertIn("not an ELF file", str(caught.exception))
        self.assertIn("rom.z64", str(caught.exception))

    def test_a_little_endian_elf(self) -> None:
        with self.assertRaises(ElfFormatError) as caught:
            parse_elf_symbols(build_elf([], [], encoding=1))
        self.assertIn("big-endian", str(caught.exception))

    def test_a_64_bit_elf(self) -> None:
        with self.assertRaises(ElfFormatError) as caught:
            parse_elf_symbols(build_elf([], [], elf_class=2))
        self.assertIn("32-bit", str(caught.exception))

    def test_a_stripped_link_says_so(self) -> None:
        """A stripped ELF cannot answer the question, and an empty census
        would be a confident wrong answer rather than no answer."""

        with self.assertRaises(ElfFormatError) as caught:
            parse_elf_symbols(build_elf([], [], with_symtab=False), path="game.elf")
        self.assertIn("stripped", str(caught.exception))

    def test_an_elf_format_error_is_a_value_error(self) -> None:
        """Every shift command funnels ValueError into one `error:` line."""

        self.assertTrue(issubclass(ElfFormatError, ValueError))

    def test_read_elf_symbols_carries_the_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.elf"
            path.write_bytes(SHADOW_ELF)
            found = read_elf_symbols(path)
        self.assertEqual(found.path, str(path))
        self.assertIn("func_a", found.names())


PW64_ELF = S0_DIR.parent / "s6" / "scratch" / "base-symbolic.elf"

#: The ten pins S6 proved redundant by ablation (`PW64-SHIFT-CONFIG.md`
#: 4.4(a)): every one is defined by an object and overridden by
#: `undefined_syms_auto.txt`.
PW64_SHADOWING_PINS = (
    "rspbootTextStart",
    "gspF3DEX_fifoTextStart",
    "gspFast3DTextStart",
    "aspMainTextStart",
    "gspF3DEX_fifoDataStart",
    "gspFast3DDataStart",
    "aspMainDataStart",
    "D_80250E80",
    "D_803571F0",
    "D_8034E710",
)

#: Three pins from the same file that no object defines: the boot stack
#: pointer, the heap base, and one of the inert leftovers. 4.4(b) and (c).
PW64_PLAIN_PINS = ("D_802C3C90", "D_803805E0", "D_8024B355")


@unittest.skipUnless(PW64_ELF.is_file(), f"S6 pilotwings64 ELF not found at {PW64_ELF}")
class Pw64ElfConformanceTests(unittest.TestCase):
    """The rule, against the link S6 measured by hand.

    S6 identified its ten shadowing pins the expensive way: `nm` over all 307
    objects, `readelf -r` for reference counts, and two ablation rebuilds to
    prove causation. Every one of them is visible in the shipped link's own
    symbol table, and this is the test that says so -- ten of ten, and no
    twenty-eighth.
    """

    elf: ClassVar[object]

    @classmethod
    def setUpClass(cls) -> None:
        cls.elf = read_elf_symbols(PW64_ELF)

    def test_the_ten_ablated_pins_all_carry_an_inherited_size(self) -> None:
        for name in PW64_SHADOWING_PINS:
            with self.subTest(pin=name):
                symbol = self.elf.symbol(name)  # type: ignore[attr-defined]
                self.assertIsNotNone(symbol, f"{name} is not in the ELF")
                assert symbol is not None
                self.assertTrue(symbol.is_absolute)
                self.assertGreater(symbol.size, 0)
                self.assertTrue(symbol.shadows_definition)

    def test_the_pins_no_object_defines_carry_none(self) -> None:
        """`D_803805E0` is the trap: an `extern` declaration in C gives it
        an ``object`` *type* with no size at all, so a type test would call
        it shadowing and the size test correctly does not. S6 4.4(b) lists
        it as live and not object-defined."""

        for name in PW64_PLAIN_PINS:
            with self.subTest(pin=name):
                symbol = self.elf.symbol(name)  # type: ignore[attr-defined]
                assert symbol is not None
                self.assertTrue(symbol.is_absolute)
                self.assertEqual(symbol.size, 0)
                self.assertFalse(symbol.shadows_definition)

    def test_the_shadowed_symbols_resolve_into_real_sections(self) -> None:
        """`D_803571F0` -- the word S6's rehearsal convicted -- points into
        `.app_bss`, which is exactly why a shift breaks it."""

        owner = self.elf.section_at(0x803571F0)  # type: ignore[attr-defined]
        assert owner is not None
        self.assertEqual(owner.name, ".app_bss")
        self.assertTrue(owner.allocated)


if __name__ == "__main__":
    unittest.main()
