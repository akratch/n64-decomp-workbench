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

from decomp_workbench.mips_refs import RangeModel, WhitelistEntry, default_n64_windows
from decomp_workbench.pins import (
    ARTIFACT_SUSPECT,
    AUTHENTIC_FIXED,
    DERIVED,
    UNCLASSIFIED,
    Pin,
    PinCatalogue,
    boot_globals_whitelist,
    default_pin_model,
    parse_pin_text,
    parse_whitelist_text,
    read_pin_files,
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

    entries = parse_pin_text(text, path="fixture.txt", model=model or default_pin_model())
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
            self.pins["gMainMemoryPool"].context, "Symbols related to the end of the ROM"
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
        self.assertEqual(dict(self.pins["thread30_bgload"].attributes), {"type": "func"})

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
        self.assertEqual(entries[0], WhitelistEntry(0x80100400, 0x80100401, "CIC-6103 boot address"))
        self.assertEqual(entries[1], WhitelistEntry(0x80000300, 0x80000401, "boot globals"))

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
        self.assertEqual(
            [item.name for item in suspects], ["D_B0000574", "D_B0000578"]
        )
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
        pin = next(item for item in self.found.entries if item.name == "gMainMemoryPool")
        self.assertEqual(pin.references, ("main_BSS_END",))

    def test_ram_to_rom_survives_its_arithmetic(self) -> None:
        pin = next(item for item in self.found.entries if item.name == "__RAM_TO_ROM")
        self.assertEqual(pin.classification, DERIVED)
        self.assertEqual(pin.references, ("main_VRAM",))

    def test_every_hardware_register_is_authentic_fixed(self) -> None:
        registers = [
            item
            for item in self.found.entries
            if item.name.endswith("_REG")
        ]
        self.assertEqual(len(registers), 48)
        self.assertEqual(
            {item.classification for item in registers}, {AUTHENTIC_FIXED}
        )
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


if __name__ == "__main__":
    unittest.main()
