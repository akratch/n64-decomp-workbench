"""Tests for the linker-pin catalogue.

Two tiers, the same shape `test_ldmap` uses. The synthetic fixtures below are
handcrafted excerpts -- not copied from any project -- that each isolate one
shape the parser has to survive: an absolute pin, a derived one, a derived one
with arithmetic, a block comment used as a section heading, a trailing comment
used as prose, a splat ``symbol_addrs`` line whose trailing comment is
attributes rather than prose, and a location-counter assignment that is not a
pin at all. The DKR conformance tests at the bottom replay the campaign's
stated expectations against the real ``ver/symbols/undefined_syms.txt`` in the
sibling ``decomp_playground`` checkout, and self-skip when it is absent -- the
file is never copied into this repository.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

# The handcrafted-ELF builder lives beside the reader it exercises; this is
# the same bare-module import `test_line_probe_cli` uses to borrow a fixture.
from test_ldmap import build_elf

from decomp_workbench.ldmap import SHN_ABS, parse_elf_symbols
from decomp_workbench.mips_refs import NamedRange, RangeModel, WhitelistEntry
from decomp_workbench.pins import (
    ARTIFACT_SUSPECT,
    AUTHENTIC_FIXED,
    CLASSIFICATIONS,
    DERIVED,
    ROM_OFFSET,
    SHADOWING_PIN,
    UNCLASSIFIED,
    WHITELIST_REVIEW_MARKER,
    WHITELIST_TEMPLATE_RULES,
    Pin,
    PinCatalogue,
    boot_globals_whitelist,
    classify_absolute,
    default_pin_model,
    parse_pin_text,
    parse_whitelist_text,
    read_pin_files,
    reclassify_rom_offsets,
    reclassify_shadowing_pins,
    whitelist_candidates,
    whitelist_template_text,
)

# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

UNDEFINED_SYMS = """/* Fake symbols until things are matched */

D_B0000574 = 0xB0000574;
D_B0000578 = 0xB0000578;

/* Symbols related to the end of the ROM */

gMainMemoryPool = main_BSS_END;   /* available at the end of BSS */
__RAM_TO_ROM = main_VRAM - 0x1000; /* used by calc_func_checksums.py */
__SIZE = ABSOLUTE (0x40 + 0x10);

osTvType = 0x80000300;
entrypoint = 0x80000400;
SP_STATUS_REG = 0xA4040010;
. = ALIGN (0x10);
"""

SYMBOL_ADDRS = """// audio.c .text
audio_init = 0x80000450;
aspMainTextStart = 0x800D7600; // size:0xEC0 name_end:aspMainTextEnd
thread30_bgload = 0x800C74A0; // type:func
D_DD138 = 0xDD138;
"""


def catalogue(text: str, *, model: RangeModel | None = None) -> PinCatalogue:
    """Parse one fixture into a catalogue under the standard N64 model."""

    entries = parse_pin_text(
        text, path="fixture.txt", model=model or default_pin_model()
    )
    return PinCatalogue(entries=entries, sources=("fixture.txt",))


class ParsingShapeTests(unittest.TestCase):
    """Every assignment shape the reference files actually contain."""

    def setUp(self) -> None:
        self.pins = {item.name: item for item in catalogue(UNDEFINED_SYMS).entries}

    def test_the_location_counter_is_not_a_pin(self) -> None:
        """``. = ALIGN(...)`` shares the shape and is not a name."""

        self.assertNotIn(".", self.pins)
        self.assertEqual(len(self.pins), 8)

    def test_an_absolute_pin_carries_its_value(self) -> None:
        pin = self.pins["D_B0000574"]
        self.assertEqual(pin.form, "absolute")
        self.assertEqual(pin.value, 0xB0000574)
        self.assertEqual(pin.references, ())

    def test_a_derived_pin_names_what_it_derives_from(self) -> None:
        pin = self.pins["gMainMemoryPool"]
        self.assertEqual(pin.form, "derived")
        self.assertIsNone(pin.value)
        self.assertEqual(pin.references, ("main_BSS_END",))
        self.assertEqual(pin.classification, DERIVED)

    def test_arithmetic_on_a_symbol_is_still_derived(self) -> None:
        pin = self.pins["__RAM_TO_ROM"]
        self.assertEqual(pin.form, "derived")
        self.assertEqual(pin.references, ("main_VRAM",))
        self.assertEqual(pin.expression, "main_VRAM - 0x1000")

    def test_arithmetic_on_constants_folds_to_one_absolute_value(self) -> None:
        """``ABSOLUTE`` is a linker builtin, not a symbol reference."""

        pin = self.pins["__SIZE"]
        self.assertEqual(pin.form, "absolute")
        self.assertEqual(pin.value, 0x50)
        self.assertEqual(pin.references, ())

    def test_a_trailing_comment_is_kept_as_context(self) -> None:
        self.assertEqual(
            self.pins["gMainMemoryPool"].comment, "available at the end of BSS"
        )

    def test_a_standalone_comment_becomes_the_heading_of_what_follows(self) -> None:
        self.assertEqual(
            self.pins["gMainMemoryPool"].context,
            "Symbols related to the end of the ROM",
        )
        self.assertEqual(
            self.pins["D_B0000574"].context, "Fake symbols until things are matched"
        )

    def test_every_pin_records_where_it_was_written(self) -> None:
        self.assertEqual(self.pins["D_B0000574"].source, "fixture.txt")
        self.assertEqual(self.pins["D_B0000574"].line, 3)
        self.assertEqual(self.pins["osTvType"].line, 12)


class SplatAttributeTests(unittest.TestCase):
    """splat ``symbol_addrs`` files put machine attributes in the comment."""

    def setUp(self) -> None:
        self.pins = {item.name: item for item in catalogue(SYMBOL_ADDRS).entries}

    def test_attribute_comments_parse_into_pairs(self) -> None:
        pin = self.pins["aspMainTextStart"]
        self.assertEqual(
            dict(pin.attributes), {"size": "0xEC0", "name_end": "aspMainTextEnd"}
        )
        self.assertIsNone(pin.comment)

    def test_a_single_attribute_still_parses(self) -> None:
        self.assertEqual(
            dict(self.pins["thread30_bgload"].attributes), {"type": "func"}
        )

    def test_prose_is_not_mistaken_for_attributes(self) -> None:
        self.assertEqual(self.pins["audio_init"].context, "audio.c .text")
        self.assertEqual(self.pins["audio_init"].attributes, ())

    def test_a_line_comment_ends_at_the_line(self) -> None:
        self.assertEqual(self.pins["D_DD138"].value, 0xDD138)
        self.assertIsNone(self.pins["D_DD138"].comment)


class WindowClassificationTests(unittest.TestCase):
    """The window a value lands in is the whole classification argument."""

    def classify(self, value: int, *, model: RangeModel | None = None) -> Pin:
        text = f"NAME = 0x{value:X};\n"
        return catalogue(text, model=model).entries[0]

    def test_cart_domain_is_an_artifact_suspect(self) -> None:
        pin = self.classify(0xB0000574)
        self.assertEqual(pin.classification, ARTIFACT_SUSPECT)
        self.assertEqual(pin.window, "cart")
        self.assertIn("cart", str(pin.reason))

    def test_hardware_registers_are_authentic_fixed(self) -> None:
        pin = self.classify(0xA4040010)
        self.assertEqual(pin.classification, AUTHENTIC_FIXED)
        self.assertEqual(pin.window, "kseg1")

    def test_a_plain_kseg0_address_is_an_artifact_suspect(self) -> None:
        pin = self.classify(0x800D7600)
        self.assertEqual(pin.classification, ARTIFACT_SUSPECT)
        self.assertEqual(pin.window, "kseg0")

    def test_the_boot_globals_whitelist_rescues_the_kseg0_pins(self) -> None:
        model = default_pin_model(whitelist=(boot_globals_whitelist(),))
        for value in (0x80000300, 0x8000031C, 0x80000400):
            with self.subTest(value=value):
                pin = self.classify(value, model=model)
                self.assertEqual(pin.classification, AUTHENTIC_FIXED)
                self.assertIn("boot", str(pin.reason))

    def test_the_whitelist_high_bound_is_inclusive(self) -> None:
        """``entrypoint = 0x80000400`` is the reason this is written down.

        A half-open reading of the boot-globals range would leave the one
        address every N64 project pins by hand outside it.
        """

        self.assertEqual(boot_globals_whitelist().hi, 0x80000404)

    def test_a_value_in_no_named_window_is_unclassified_not_guessed(self) -> None:
        pin = self.classify(0x0FFFFFFF)
        self.assertEqual(pin.classification, UNCLASSIFIED)
        self.assertIsNone(pin.window)


class UnresolvedExpressionTests(unittest.TestCase):
    """An expression this reader cannot fold is reported, never guessed."""

    def test_the_location_counter_cannot_be_folded_and_says_so(self) -> None:
        """``. + 0x10`` has a value only the linker knows."""

        pin = catalogue("NAME = . + 0x10;\n").entries[0]
        self.assertEqual(pin.form, "unresolved")
        self.assertEqual(pin.classification, UNCLASSIFIED)
        self.assertIsNone(pin.value)
        self.assertEqual(pin.expression, ". + 0x10")

    def test_a_builtin_this_reader_does_not_model_is_unresolved(self) -> None:
        pin = catalogue("NAME = DATA_SEGMENT_ALIGN(0x1000, 0x100);\n").entries[0]
        self.assertEqual(pin.form, "unresolved")
        self.assertEqual(pin.references, ())

    def test_a_linker_builtin_alone_is_not_a_symbol_reference(self) -> None:
        pin = catalogue("NAME = ALIGN(0x10);\n").entries[0]
        self.assertEqual(pin.references, ())

    def test_a_builtin_wrapping_a_symbol_still_reports_the_symbol(self) -> None:
        pin = catalogue("NAME = ABSOLUTE (main_BSS_END - main_BSS_START);\n").entries[0]
        self.assertEqual(pin.form, "derived")
        self.assertEqual(pin.references, ("main_BSS_END", "main_BSS_START"))


class WhitelistFileTests(unittest.TestCase):
    """``--whitelist`` is the only way a caller says "this one is real"."""

    def test_an_exact_address_and_a_range_both_parse(self) -> None:
        entries = parse_whitelist_text(
            "# comment\n"
            "0x80100400 CIC-6103 boot address\n"
            "0x80000300-0x80000400 boot globals\n"
            "\n"
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            entries[0], WhitelistEntry(0x80100400, 0x80100401, "CIC-6103 boot address")
        )
        self.assertEqual(
            entries[1], WhitelistEntry(0x80000300, 0x80000401, "boot globals")
        )

    def test_a_reason_is_required(self) -> None:
        with self.assertRaises(ValueError) as raised:
            parse_whitelist_text("0x80100400\n")
        self.assertIn("reason", str(raised.exception))

    def test_a_backwards_range_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            parse_whitelist_text("0x80000400-0x80000300 backwards\n")


class CatalogueTests(unittest.TestCase):
    """Counts, ordering, and the JSON shape a report is rendered from."""

    def setUp(self) -> None:
        model = default_pin_model(whitelist=(boot_globals_whitelist(),))
        self.catalogue = catalogue(UNDEFINED_SYMS, model=model)

    def test_counts_partition_the_catalogue(self) -> None:
        counts = self.catalogue.counts
        self.assertEqual(sum(counts.values()), len(self.catalogue.entries))
        self.assertEqual(counts[DERIVED], 2)
        self.assertEqual(counts[ARTIFACT_SUSPECT], 2)
        self.assertEqual(counts[AUTHENTIC_FIXED], 3)
        self.assertEqual(counts[UNCLASSIFIED], 1)

    def test_suspects_are_listed_before_the_healthy_classes(self) -> None:
        """A capped list has to spend its budget on the interesting end."""

        ordered = [item.classification for item in self.catalogue.ranked()]
        self.assertEqual(ordered[:2], [ARTIFACT_SUSPECT, ARTIFACT_SUSPECT])
        self.assertEqual(ordered[-2:], [DERIVED, DERIVED])

    def test_the_json_shape_names_its_own_cap(self) -> None:
        payload = self.catalogue.as_dict(limit=3)
        self.assertEqual(payload["pins_total"], 8)
        self.assertEqual(payload["pins_shown"], 3)
        self.assertEqual(payload["limit"], 3)
        self.assertEqual(len(payload["pins"]), 3)
        self.assertEqual(payload["pins_artifact"], 2)
        self.assertEqual(payload["pins_derived"], 2)
        self.assertEqual(payload["pins_authentic"], 3)
        self.assertEqual(payload["pins_unclassified"], 1)
        self.assertEqual(payload["pin_sources"], ["fixture.txt"])

    def test_every_entry_field_survives_the_json_round_trip(self) -> None:
        entry = next(
            item for item in self.catalogue.entries if item.name == "gMainMemoryPool"
        )
        payload = entry.as_dict()
        self.assertEqual(payload["name"], "gMainMemoryPool")
        self.assertEqual(payload["form"], "derived")
        self.assertEqual(payload["references"], ["main_BSS_END"])
        self.assertIsNone(payload["value"])
        self.assertEqual(payload["attributes"], {})


# --------------------------------------------------------------------------
# S7: the ROM-offset class
# --------------------------------------------------------------------------

#: The shape splat projects pin by the dozen and this model had no name for:
#: a raw cartridge offset. Banjo-Kazooie's `rzip_dummy_addrs.us.v10.txt`
#: writes the first two and its level tables the third; the last two are the
#: boundaries the class must *not* swallow.
ROM_OFFSET_PINS = """boot_core1_rzip_ROM_START = 0xF19250;
boot_core1_rzip_ROM_END = 0xF55960;
D_5E90 = 0x5E90;
past_the_end = 0x2000000;
gHeapBase = 0x80280000;
"""


class RomOffsetClassificationTests(unittest.TestCase):
    """A small absolute inside the ROM the map placed is its own class."""

    def setUp(self) -> None:
        self.model = default_pin_model()
        self.extent = 0x10BCD40  # a plausible 17 MB linked extent

    def classify(self, value: int, *, extent: int | None) -> str:
        return classify_absolute(value, model=self.model, rom_extent=extent)[0]

    def test_a_small_value_inside_the_placed_extent_is_a_rom_offset(self) -> None:
        self.assertEqual(self.classify(0xF19250, extent=self.extent), ROM_OFFSET)
        self.assertEqual(self.classify(0x5E90, extent=self.extent), ROM_OFFSET)

    def test_a_value_past_the_placed_extent_stays_unclassified(self) -> None:
        """Half the evidence is not the evidence: small alone says nothing."""

        self.assertEqual(self.classify(0x2000000, extent=self.extent), UNCLASSIFIED)

    def test_naming_no_extent_keeps_the_answer_this_function_gave_before(
        self,
    ) -> None:
        """A caller with no map cannot bound the ROM and is not asked to."""

        self.assertEqual(self.classify(0xF19250, extent=None), UNCLASSIFIED)

    def test_a_ram_window_always_answers_first(self) -> None:
        """kseg0/kseg1/cart are decided before the extent is consulted, so a
        huge extent can never turn a RAM address into a ROM offset."""

        big = 0xFFFFFFFF
        self.assertEqual(self.classify(0x80280000, extent=big), ARTIFACT_SUSPECT)
        self.assertEqual(self.classify(0xA4040010, extent=big), AUTHENTIC_FIXED)
        self.assertEqual(self.classify(0xB0000574, extent=big), ARTIFACT_SUSPECT)

    def test_the_whitelist_still_wins_outright(self) -> None:
        model = default_pin_model(
            whitelist=(WhitelistEntry(0x5E90, 0x5E91, "the caller says so"),)
        )
        classification, _, reason = classify_absolute(
            0x5E90, model=model, rom_extent=self.extent
        )
        self.assertEqual(classification, AUTHENTIC_FIXED)
        self.assertEqual(reason, "the caller says so")

    def test_the_floor_comes_from_the_models_own_ram_windows(self) -> None:
        """A model whose lowest RAM window sits higher than kseg0 moves the
        ceiling with it -- the bound is derived, not written down twice."""

        model = RangeModel(windows=(NamedRange("high", 0x90000000, 0xA0000000),))
        self.assertEqual(
            classify_absolute(0x88000000, model=model, rom_extent=0xFFFFFFFF)[0],
            ROM_OFFSET,
        )

    def test_the_reason_names_the_remediation(self) -> None:
        _, _, reason = classify_absolute(
            0xF19250, model=self.model, rom_extent=self.extent
        )
        assert reason is not None
        self.assertIn("_ROM_START", reason)
        self.assertIn("raw ROM offset", reason)

    def test_the_class_is_reported_and_ordered_between_suspect_and_unknown(
        self,
    ) -> None:
        self.assertIn(ROM_OFFSET, CLASSIFICATIONS)
        self.assertLess(
            CLASSIFICATIONS.index(ARTIFACT_SUSPECT), CLASSIFICATIONS.index(ROM_OFFSET)
        )
        self.assertLess(
            CLASSIFICATIONS.index(ROM_OFFSET), CLASSIFICATIONS.index(UNCLASSIFIED)
        )

    def test_parsing_with_an_extent_classifies_in_one_pass(self) -> None:
        entries = parse_pin_text(
            ROM_OFFSET_PINS, path="pins.txt", model=self.model, rom_extent=self.extent
        )
        by_name = {item.name: item.classification for item in entries}
        self.assertEqual(by_name["boot_core1_rzip_ROM_START"], ROM_OFFSET)
        self.assertEqual(by_name["boot_core1_rzip_ROM_END"], ROM_OFFSET)
        self.assertEqual(by_name["D_5E90"], ROM_OFFSET)
        self.assertEqual(by_name["past_the_end"], UNCLASSIFIED)
        self.assertEqual(by_name["gHeapBase"], ARTIFACT_SUSPECT)


class RomOffsetReclassificationTests(unittest.TestCase):
    """The second pass `shift audit` runs once the map's extent is known."""

    def setUp(self) -> None:
        self.model = default_pin_model()
        self.catalogue = PinCatalogue(
            entries=parse_pin_text(
                ROM_OFFSET_PINS + UNDEFINED_SYMS, path="pins.txt", model=self.model
            ),
            sources=("pins.txt",),
        )

    def test_before_the_pass_every_rom_offset_is_unclassified(self) -> None:
        self.assertEqual(self.catalogue.counts[ROM_OFFSET], 0)
        self.assertEqual(self.catalogue.counts[UNCLASSIFIED], 5)

    def test_the_pass_moves_exactly_the_rom_offsets(self) -> None:
        found = reclassify_rom_offsets(
            self.catalogue, model=self.model, rom_extent=0x10BCD40
        )
        counts = found.counts
        # Four, not the three `ROM_OFFSET_PINS` names: `UNDEFINED_SYMS`'s
        # `__SIZE = ABSOLUTE (0x40 + 0x10)` folds to 0x50, which is below
        # every RAM window and inside the extent, and reads as a ROM offset
        # too. See `test_a_small_size_constant_reads_as_an_offset_and_says_so`
        # -- one image cannot tell a size from an offset, and the class is
        # named after the shape it can see.
        self.assertEqual(counts[ROM_OFFSET], 4)
        # `past_the_end` (0x2000000, outside the extent) is the only survivor.
        self.assertEqual(counts[UNCLASSIFIED], 1)
        self.assertEqual(sum(counts.values()), len(found.entries))

    def test_a_small_size_constant_reads_as_an_offset_and_says_so(self) -> None:
        """The class's honest edge, filed rather than papered over.

        A folded *size* (`__SIZE = ABSOLUTE (0x40 + 0x10)`) has exactly the
        shape of a small ROM offset, and nothing in one linker map
        distinguishes them -- the same ambiguity `shift audit`'s tiers are
        built around. The reason attached to the entry is a remediation to
        consider, not a defect report, and a reader who follows it finds a
        size and moves on.
        """

        found = reclassify_rom_offsets(
            self.catalogue, model=self.model, rom_extent=0x10BCD40
        )
        entry = next(item for item in found.entries if item.name == "__SIZE")
        self.assertEqual(entry.classification, ROM_OFFSET)
        self.assertEqual(entry.value, 0x50)

    def test_nothing_a_window_already_named_can_move(self) -> None:
        before = {item.name: item.classification for item in self.catalogue.entries}
        after = {
            item.name: item.classification
            for item in reclassify_rom_offsets(
                self.catalogue, model=self.model, rom_extent=0xFFFFFFFF
            ).entries
        }
        moved = {name for name in before if before[name] != after[name]}
        self.assertTrue(all(before[name] == UNCLASSIFIED for name in moved))

    def test_an_unresolved_expression_is_left_alone(self) -> None:
        """No value, nothing to bound: `unresolved` stays `unclassified`."""

        catalogue = PinCatalogue(
            entries=parse_pin_text(
                "mystery = 1 ? 2 : 3;\n", path="pins.txt", model=self.model
            ),
            sources=("pins.txt",),
        )
        self.assertEqual([item.form for item in catalogue.entries], ["unresolved"])
        found = reclassify_rom_offsets(catalogue, model=self.model, rom_extent=0x1000)
        self.assertEqual(found.counts[UNCLASSIFIED], len(found.entries))

    def test_the_sources_survive_the_pass(self) -> None:
        found = reclassify_rom_offsets(
            self.catalogue, model=self.model, rom_extent=0x10BCD40
        )
        self.assertEqual(found.sources, self.catalogue.sources)

    def test_the_count_reaches_the_json_payload(self) -> None:
        payload = reclassify_rom_offsets(
            self.catalogue, model=self.model, rom_extent=0x10BCD40
        ).as_dict(limit=2)
        self.assertEqual(payload["pins_rom_offset"], 4)
        self.assertEqual(payload["pins_unclassified"], 1)


# --------------------------------------------------------------------------
# S7: the whitelist template
# --------------------------------------------------------------------------

#: One pin per drafting rule, plus two that must not be drafted: a kseg0
#: address *above* the floor (a real code address this layout owns) and a
#: derived pin (nothing to whitelist).
TEMPLATE_PINS = """SP_STATUS_REG = 0xA4040010;
osTvType = 0x80000300;
gameLoop = 0x80005000;
gMainMemoryPool = main_BSS_END;
"""


def template_catalogue(model: RangeModel) -> PinCatalogue:
    return PinCatalogue(
        entries=parse_pin_text(TEMPLATE_PINS, path="pins.txt", model=model),
        sources=("pins.txt",),
    )


class WhitelistTemplateTests(unittest.TestCase):
    """`shift audit --emit-whitelist`'s skeleton: drafted, never asserted."""

    def setUp(self) -> None:
        self.model = default_pin_model()
        self.catalogue = template_catalogue(self.model)
        self.text = whitelist_template_text(
            self.catalogue, window_lo=0x80000400, window_lo_section=".main"
        )

    def test_both_evidence_families_are_drafted(self) -> None:
        drafted = whitelist_candidates(self.catalogue, window_lo=0x80000400)
        self.assertEqual(
            [(item.name, item.rule) for item in drafted],
            [
                ("osTvType", "below-window-floor"),
                ("SP_STATUS_REG", "hardware-window"),
            ],
        )

    def test_a_kseg0_pin_above_the_floor_is_not_drafted(self) -> None:
        """It is an address this layout owns, which is the opposite of the
        claim a whitelist entry makes."""

        drafted = {
            item.name for item in whitelist_candidates(self.catalogue, window_lo=0x400)
        }
        self.assertNotIn("gameLoop", drafted)
        self.assertNotIn("osTvType", drafted)

    def test_a_pin_the_callers_whitelist_already_covers_is_not_redrafted(
        self,
    ) -> None:
        model = default_pin_model(whitelist=(boot_globals_whitelist(),))
        drafted = {
            item.name
            for item in whitelist_candidates(
                template_catalogue(model), window_lo=0x80000400
            )
        }
        self.assertNotIn("osTvType", drafted)
        self.assertIn("SP_STATUS_REG", drafted)

    def test_every_entry_is_commented_out_and_marked_for_review(self) -> None:
        self.assertIn(f"{WHITELIST_REVIEW_MARKER} osTvType (pins.txt:2)", self.text)
        self.assertIn("# 0x80000300 osTvType:", self.text)
        self.assertIn("# 0xA4040010 SP_STATUS_REG:", self.text)

    def test_the_skeleton_parses_to_no_entries_until_a_human_edits_it(self) -> None:
        """The point of the marker: a template piped straight into
        `--whitelist` declares nothing authentic."""

        self.assertEqual(parse_whitelist_text(self.text), ())

    def test_uncommenting_one_line_turns_exactly_that_entry_on(self) -> None:
        edited = self.text.replace("# 0x80000300 ", "0x80000300 ")
        entries = parse_whitelist_text(edited)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].lo, 0x80000300)
        self.assertIn("boot-globals shaped", entries[0].reason)

    def test_the_header_names_the_floor_the_second_rule_used(self) -> None:
        self.assertIn("movable window floor: 0x80000400 (.main)", self.text)
        self.assertIn("pin_sources: pins.txt", self.text)

    def test_the_drafting_rules_travel_with_the_template(self) -> None:
        for rule in WHITELIST_TEMPLATE_RULES:
            with self.subTest(rule=rule.name):
                self.assertIn(rule.name, self.text)
                self.assertIn(rule.evidence, " ".join(self.text.split()))
        self.assertIn("hardware-window (1)", self.text)
        self.assertIn("below-window-floor (1)", self.text)

    def test_a_catalogue_with_no_candidates_says_so_rather_than_emitting_nothing(
        self,
    ) -> None:
        empty = PinCatalogue(
            entries=parse_pin_text(
                "gMainMemoryPool = main_BSS_END;\n", path="pins.txt", model=self.model
            ),
            sources=("pins.txt",),
        )
        text = whitelist_template_text(empty, window_lo=0x80000400)
        self.assertIn("No pin in these files has either shape", text)
        self.assertEqual(parse_whitelist_text(text), ())


class ReadingFilesTests(unittest.TestCase):
    """More than one input file, in the order the caller named them."""

    def test_two_files_merge_into_one_catalogue_that_names_both(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "undefined_syms.txt"
            second = root / "symbol_addrs.txt"
            first.write_text(UNDEFINED_SYMS, encoding="utf-8")
            second.write_text(SYMBOL_ADDRS, encoding="utf-8")
            found = read_pin_files([first, second], model=default_pin_model())
        self.assertEqual(found.sources, (str(first), str(second)))
        self.assertEqual(len(found.entries), 12)
        self.assertEqual(
            {item.source for item in found.entries}, {str(first), str(second)}
        )


# --------------------------------------------------------------------------
# DKR conformance -- skips when the sibling playground checkout is absent
# --------------------------------------------------------------------------

DKR_SYMBOLS = (
    Path(__file__).resolve().parents[2]
    / "decomp_playground"
    / "diddy-kong-racing"
    / "ver"
    / "symbols"
)
UNDEFINED_SYMS_PATH = DKR_SYMBOLS / "undefined_syms.txt"


@unittest.skipUnless(
    UNDEFINED_SYMS_PATH.is_file(),
    f"DKR symbol files not found under {DKR_SYMBOLS}",
)
class DkrPinConformanceTests(unittest.TestCase):
    """The campaign's stated expectations for DKR's real pin file.

    Every number here was read off the file itself before it was written
    down: 66 assignments, of which 2 are the cart-window fakes, 7 derive
    from linker symbols, 9 are the libultra boot globals plus the fixed
    entrypoint, and 48 are memory-mapped hardware registers.
    """

    found: ClassVar[PinCatalogue]

    @classmethod
    def setUpClass(cls) -> None:
        cls.found = read_pin_files(
            [UNDEFINED_SYMS_PATH],
            model=default_pin_model(whitelist=(boot_globals_whitelist(),)),
        )

    def test_the_whole_file_parses(self) -> None:
        self.assertEqual(len(self.found.entries), 66)

    def test_exactly_two_absolute_pins_are_artifact_suspects(self) -> None:
        suspects = self.found.by_classification(ARTIFACT_SUSPECT)
        self.assertEqual([item.name for item in suspects], ["D_B0000574", "D_B0000578"])
        self.assertEqual([item.window for item in suspects], ["cart", "cart"])
        self.assertEqual([item.value for item in suspects], [0xB0000574, 0xB0000578])

    def test_the_suspects_carry_the_comment_that_admits_what_they_are(self) -> None:
        suspect = self.found.by_classification(ARTIFACT_SUSPECT)[0]
        self.assertIn("fake symbols", str(suspect.context).lower())

    def test_the_derived_pins_are_the_healthy_class(self) -> None:
        derived = {item.name for item in self.found.by_classification(DERIVED)}
        self.assertEqual(len(derived), 7)
        for name in (
            "gMainMemoryPool",
            "__ROM_END",
            "__RAM_TO_ROM",
            "__BSS_SECTION_START",
        ):
            with self.subTest(name=name):
                self.assertIn(name, derived)

    def test_gmainmemorypool_derives_from_the_end_of_bss(self) -> None:
        pin = next(
            item for item in self.found.entries if item.name == "gMainMemoryPool"
        )
        self.assertEqual(pin.references, ("main_BSS_END",))

    def test_ram_to_rom_survives_its_arithmetic(self) -> None:
        pin = next(item for item in self.found.entries if item.name == "__RAM_TO_ROM")
        self.assertEqual(pin.classification, DERIVED)
        self.assertEqual(pin.references, ("main_VRAM",))

    def test_every_hardware_register_is_authentic_fixed(self) -> None:
        registers = [item for item in self.found.entries if item.name.endswith("_REG")]
        self.assertEqual(len(registers), 48)
        self.assertEqual({item.classification for item in registers}, {AUTHENTIC_FIXED})
        self.assertEqual({item.window for item in registers}, {"kseg1"})
        self.assertEqual(
            next(item for item in registers if item.name == "SP_MEM_ADDR_REG").value,
            0xA4040000,
        )

    def test_the_boot_globals_and_the_entrypoint_are_authentic_fixed(self) -> None:
        by_name = {item.name: item for item in self.found.entries}
        for name in (
            "osTvType",
            "osRomType",
            "osRomBase",
            "osResetType",
            "osCicId",
            "osVersion",
            "osMemSize",
            "osAppNMIBuffer",
            "entrypoint",
        ):
            with self.subTest(name=name):
                pin = by_name[name]
                self.assertEqual(pin.classification, AUTHENTIC_FIXED)
                self.assertEqual(pin.window, "kseg0")
                self.assertIn("boot", str(pin.reason))

    def test_without_the_whitelist_the_boot_globals_read_as_suspects(self) -> None:
        """The whitelist is the caller's claim, and it is visible in the count."""

        bare = read_pin_files([UNDEFINED_SYMS_PATH], model=default_pin_model())
        self.assertEqual(bare.counts[ARTIFACT_SUSPECT], 11)
        self.assertEqual(self.found.counts[ARTIFACT_SUSPECT], 2)

    def test_the_class_counts_add_up(self) -> None:
        counts = self.found.counts
        self.assertEqual(counts[DERIVED], 7)
        self.assertEqual(counts[AUTHENTIC_FIXED], 57)
        self.assertEqual(counts[ARTIFACT_SUSPECT], 2)
        self.assertEqual(counts[UNCLASSIFIED], 0)
        self.assertEqual(sum(counts.values()), 66)


@unittest.skipUnless(
    (DKR_SYMBOLS / "symbol_addrs.us.v77.txt").is_file(),
    f"DKR symbol files not found under {DKR_SYMBOLS}",
)
class DkrSymbolAddrsConformanceTest(unittest.TestCase):
    """The splat file is the same grammar with attributes in the comments."""

    def test_the_whole_symbol_addrs_file_parses_with_its_attributes(self) -> None:
        found = read_pin_files(
            [DKR_SYMBOLS / "symbol_addrs.us.v77.txt"], model=default_pin_model()
        )
        self.assertGreater(len(found.entries), 4000)
        by_name = {item.name: item for item in found.entries}
        self.assertEqual(dict(by_name["thread30_bgload"].attributes), {"type": "func"})
        self.assertEqual(
            dict(by_name["aspMainTextStart"].attributes),
            {"size": "0xEC0", "name_end": "aspMainTextEnd"},
        )
        # Every entry in a splat symbol file is an absolute address by
        # construction, which is exactly why the file is not evidence of a
        # shiftability problem on its own -- see the module docstring.
        self.assertEqual({item.form for item in found.entries}, {"absolute"})


# --------------------------------------------------------------------------
# WB-143b: the class only the ELF can name
# --------------------------------------------------------------------------

#: One link in which `D_80000540` is an absolute pin that overrode an object
#: definition (the 8-byte size is the inherited evidence), `D_B0000574` is an
#: absolute pin with nothing behind it, and `gCounter` is an ordinary
#: object-backed symbol a pin file also happens to name.
SHADOW_LINK = build_elf(
    sections=[(".text", 0x80000400, 0x100, 0x6), (".bss", 0x80000500, 0x80, 0x3)],
    symbols=[
        ("gCounter", 0x80000500, 0x4, 1, 1, 2),
        ("D_80000540", 0x80000540, 0x8, 1, 1, SHN_ABS),
        ("D_B0000574", 0xB0000574, 0x0, 0, 1, SHN_ABS),
        ("gMainMemoryPool", 0x80000560, 0x0, 0, 1, SHN_ABS),
    ],
)

SHADOW_PINS = """
D_80000540 = 0x80000540;
D_B0000574 = 0xB0000574;
gCounter = 0x80000500;
gMainMemoryPool = main_BSS_END;
D_C0DEC0DE = 0xC0DEC0DE;
"""


class ShadowingPinTests(unittest.TestCase):
    """The pin class a linker map cannot see and one ELF can."""

    def setUp(self) -> None:
        self.model = default_pin_model()
        self.catalogue = PinCatalogue(
            entries=parse_pin_text(SHADOW_PINS, path="syms.txt", model=self.model),
            sources=("syms.txt",),
        )
        self.elf = parse_elf_symbols(SHADOW_LINK, path="game.elf")

    def test_before_the_elf_the_shadowing_pin_is_just_a_kseg0_suspect(self) -> None:
        """The whole point: no window-based classifier can reach this."""

        found = {item.name: item.classification for item in self.catalogue.entries}
        self.assertEqual(found["D_80000540"], ARTIFACT_SUSPECT)
        self.assertEqual(found["D_B0000574"], ARTIFACT_SUSPECT)

    def test_only_the_pin_with_an_inherited_size_is_reclassified(self) -> None:
        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        found = {item.name: item.classification for item in reclassified.entries}
        self.assertEqual(found["D_80000540"], SHADOWING_PIN)
        self.assertEqual(found["D_B0000574"], ARTIFACT_SUSPECT)

    def test_a_pin_naming_an_object_backed_symbol_is_not_shadowing(self) -> None:
        """`gCounter` is defined by an object *and* written down -- but the
        object's definition won, so nothing was overridden and the surviving
        symbol is section-backed rather than absolute."""

        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        found = {item.name: item.classification for item in reclassified.entries}
        self.assertEqual(found["gCounter"], ARTIFACT_SUSPECT)

    def test_a_derived_pin_is_never_reclassified(self) -> None:
        """A pin whose right-hand side names a symbol already follows the
        layout; a name collision there would be a different and much louder
        problem than this one."""

        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        found = {item.name: item.classification for item in reclassified.entries}
        self.assertEqual(found["gMainMemoryPool"], DERIVED)

    def test_a_pin_the_elf_never_heard_of_is_left_alone(self) -> None:
        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        found = {item.name: item.classification for item in reclassified.entries}
        self.assertEqual(found["D_C0DEC0DE"], UNCLASSIFIED)

    def test_the_reclassified_pin_carries_the_remediation_in_its_reason(self) -> None:
        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        pin = next(
            item for item in reclassified.entries if item.name == "D_80000540"
        )
        assert pin.reason is not None
        self.assertIn("already defines", pin.reason)
        self.assertIn("byte-identical", pin.reason)

    def test_the_counts_carry_the_new_class_at_zero_when_empty(self) -> None:
        """A class that vanishes when empty is one a reader cannot tell from
        a class the module forgot to look for."""

        self.assertIn(SHADOWING_PIN, self.catalogue.counts)
        self.assertEqual(self.catalogue.counts[SHADOWING_PIN], 0)
        self.assertIn("pins_shadowing", self.catalogue.as_dict(limit=5))

    def test_the_new_class_leads_the_report_order(self) -> None:
        """It is the only class whose remediation is proven free."""

        self.assertEqual(CLASSIFICATIONS[0], SHADOWING_PIN)
        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        self.assertEqual(reclassified.ranked()[0].name, "D_80000540")

    def test_sources_survive_the_pass(self) -> None:
        reclassified = reclassify_shadowing_pins(self.catalogue, elf=self.elf)
        self.assertEqual(reclassified.sources, ("syms.txt",))


if __name__ == "__main__":
    unittest.main()
