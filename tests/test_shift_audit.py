"""Tests for the static shiftability inventory and its command.

Three tiers. The synthetic fixture below is a handcrafted map plus a
handcrafted 160-byte image -- no bytes from any ROM -- laid out so that every
confidence feature and every tier rule has exactly one word that exercises it,
which is what makes the expected tier totals readable by hand. The CLI tests
drive the real parser. The DKR conformance tests replay S0's own anchor cases
(`.workbench/shift-instrumentation/s0` in the sibling `decomp_playground`
checkout) and self-skip when that checkout is absent; the map and image are
read from there and never copied into this repository.
"""

from __future__ import annotations

import io
import json
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
from decomp_workbench.mips_refs import WhitelistEntry
from decomp_workbench.pins import (
    ARTIFACT_SUSPECT,
    AUTHENTIC_FIXED,
    DERIVED,
    ROM_OFFSET,
    SHADOWING_PIN,
    UNCLASSIFIED,
    PinCatalogue,
    boot_globals_whitelist,
    default_pin_model,
    parse_pin_text,
    parse_whitelist_text,
    read_pin_files,
)
from decomp_workbench.schema import (
    SHIFT_CENSUS_KEYS,
    SHIFT_METRICS_BY_KEY,
    explain_keys_text,
)
from decomp_workbench.shift_audit import (
    BLOB_OBJECT_RULES,
    BLOB_SOURCE_AUTO,
    BLOB_SOURCE_EXPLICIT,
    BLOB_SOURCE_NONE,
    CLUSTER_MINIMUM,
    MAP_SNIFF_BYTES,
    MOVABLE_FLOOR_MIN,
    NON_ALLOC_KIND,
    NON_ALLOC_ROM_SOURCE,
    NON_ALLOC_SECTION_FAMILIES,
    REPEAT_MINIMUM,
    RESIDENCE_SCORES,
    TIER_RULES,
    BlobRule,
    ConsistencyCheck,
    Hit,
    Region,
    ShiftAudit,
    build_region_table,
    build_shift_audit,
    check_map_image_consistency,
    movable_window,
    require_parsed_map,
    resolve_blobs,
    shift_audit_lines,
    suggest_blobs,
)

# --------------------------------------------------------------------------
# Synthetic fixture
# --------------------------------------------------------------------------

#: Five output sections covering every placement shape the region table has
#: to derive: two sections with no `AT()` whose VMA *is* their ROM offset, one
#: `AT()`'d section holding a text run followed by two data runs that must
#: merge, and a bss section that owns no image bytes at all (its huge size is
#: what puts the movable window's high bound far above the image).
SYNTHETIC_MAP = """
Linker script and memory map

.header         0x00000000       0x10
 .data          0x00000000       0x10 build/header.o

.boot           0x00000010       0x10
 .data          0x00000010       0x10 build/boot.o

.main           0x80000400       0x80 load address 0x00000020
 .text          0x80000400       0x20 build/code.o
 .text          0x80000420       0x10 build/more.o
 .data          0x80000430       0x30 build/code.o
                0x80000430                gData
                0x80000440                gTarget
                0x80000450                gOther
 .rodata        0x80000460       0x20 build/code.o

.main_bss       0x80000480    0x10020 load address 0x000000a0
 .bss           0x80000480    0x10020 build/code.o
                0x800104a0                main_BSS_END
"""

#: One word per feature. The comment beside each is the rule it exists to
#: fire; the totals asserted below are the sum of these, by hand.
SYNTHETIC_WORDS: tuple[int, ...] = (
    # .header, ROM 0x00-0x0f
    0x00000000,
    0x80000444,  # header residence, nothing else: low
    0x00000000,
    0x00000000,
    # .boot, ROM 0x10-0x1f
    0x80000440,  # points at gTarget; blob residence: medium
    0x80000444,  # blob residence, nothing else: low
    0x00000000,
    0x00000000,
    # .main .text, ROM 0x20-0x4f -- address-shaped and never scanned
    0x80000440,
    *((0x00000000,) * 11),
    # .main .data + .rodata, ROM 0x50-0x9f
    0x80000440,  # data residence, points at gTarget: high
    0x80000443,  # misaligned
    0x80010000,  # round constant (low half zero), no symbol under it
    0x80000454,  # plain in-window data word: medium
    0x80000460,  # cluster member
    0x80000464,  # cluster member
    0x80000468,  # cluster member
    0x00000000,
    0x80000474,  # repeated value
    0x80000474,
    0x80000474,
    0x80000474,
    0x80000480,  # plain in-window data word: medium (whitelisted in one test)
    *((0x00000000,) * 7),
)

SYNTHETIC_IMAGE = b"".join(struct.pack(">I", word) for word in SYNTHETIC_WORDS)


#: WB-138's shape: every family `NON_ALLOC_SECTION_FAMILIES` names, each
#: represented once, plus one ordinary `.main`/`.main_bss` pair to derive a
#: movable window against. `.mdebug` prints VMA ``0`` -- BK's own does too --
#: which is exactly what let it through as a bogus ``vma-as-rom`` region
#: before this fix.
NON_ALLOC_MAP = """
Linker script and memory map

.main           0x80000400       0x40 load address 0x00000100
 .text          0x80000400       0x40 build/code.o

.main_bss       0x80000440       0x40 load address 0x00000140
 .bss           0x80000440       0x40 build/code.o

.mdebug         0x00000000       0x20
 .mdebug        0x00000000       0x10 build/code.o
 .mdebug        0x00000010       0x10 build/other.o

.mdebug.abi32   0x00000020        0x8
 .mdebug.abi32  0x00000020        0x8 build/code.o

.pdr            0x00000028       0x10
 .pdr           0x00000028       0x10 build/code.o

.comment        0x00000038        0x8
 .comment       0x00000038        0x8 build/code.o

.gptab.sdata    0x00000040        0x8
 .gptab.sdata   0x00000040        0x8 build/code.o

.reginfo        0x00000048       0x18
 .reginfo       0x00000048       0x18 build/code.o

.options        0x00000060        0x8
 .options       0x00000060        0x8 build/code.o

.debug_info     0x00000068       0x10
 .debug_info    0x00000068       0x10 build/code.o

.line           0x00000078        0x8
 .line          0x00000078        0x8 build/code.o

.rel.text       0x00000080        0x8
 .rel.text      0x00000080        0x8 build/code.o
"""

#: The safety valve: a section named exactly like a known non-alloc family
#: member, but that declares an explicit `AT()` -- an explicit placement
#: always outranks the name-based inference.
NON_ALLOC_WITH_AT_MAP = """
Linker script and memory map

.main           0x80000400       0x10 load address 0x00000100

.comment        0x00000000       0x10 load address 0x00000200
 .comment       0x00000000       0x10 build/code.o
"""

#: WB-139's shape: two output sections sharing one VMA start, each with its
#: own distinct `AT()` load address -- the N64 overlay-group pattern BK's
#: map has fourteen of (`.CC`/`.GV`/`.MMM`/... all starting at
#: ``0x803863f0``). `.overlay_a` also carries two runs (`text` then `data`)
#: so its second run's placement has to walk forward from the *section's*
#: load address, not the record's own VMA read straight through.
OVERLAY_SIBLING_MAP = """
Linker script and memory map

.overlay_a      0x80386000       0x20 load address 0x00100000
 .text          0x80386000       0x10 build/a.o
 .data          0x80386010       0x10 build/a.o

.overlay_b      0x80386000       0x10 load address 0x00200000
 .text          0x80386000       0x10 build/b.o
"""


#: S7's shape, and it carries two features at once because one map really
#: does produce both. Three sections whose every input object is a raw binary
#: -- one per `BLOB_OBJECT_RULES` entry, plus a second suffix match -- one
#: section that mixes a `.bin.o` in with compiled objects (BK's `.core2`
#: shape, which must *not* be suggested), and one ordinary compiled section.
#: The three blob-shaped sections are also placed low, at ROM offsets rather
#: than at run-time addresses, which is pilotwings64's `.ipl3` shape and the
#: reason `movable_window` derives its floor from RAM residence.
BLOB_INPUT_MAP = """
Linker script and memory map

.header         0x00000000       0x10
 .data          0x00000000       0x10 build/header.o

.boot           0x00000010       0x10
 .data          0x00000010       0x10 build/assets/boot.bin.o

.assets         0x00000020       0x10 load address 0x00000020
 .data          0x00000020       0x10 build/assets/assets.bin.o

.filesys        0x00000030       0x10 load address 0x00000030
 .data          0x00000030       0x10 build/bin/filesys.o

.main           0x80000400       0x40 load address 0x00000040
 .text          0x80000400       0x20 build/code.o
 .data          0x80000420       0x10 build/bin/data_1000.bin.o
 .data          0x80000430       0x10 build/code.o

.main_bss       0x80000440       0x20 load address 0x00000080
 .bss           0x80000440       0x20 build/code.o
"""

#: 32 words, one per 4 bytes of the map above. Three carry the whole point:
#: ``0x00000020`` in `.header` is in-window only under the old, unfixed
#: window floor; the two ``0x8000042x`` values sit in a suggested blob and in
#: compiled data respectively, so adopting the suggestion moves exactly one
#: of them from `medium` to `low`.
BLOB_INPUT_WORDS: tuple[int, ...] = (
    0x00000020,  # .header +0x00: a ROM offset, not an address
    *((0x00000000,) * 3),
    *((0x00000000,) * 4),  # .boot
    *((0x00000000,) * 4),  # .assets
    0x80000424,  # .filesys +0x00: data residence, or blob residence under auto
    *((0x00000000,) * 3),
    *((0x00000000,) * 8),  # .main .text, never scanned
    0x80000420,  # .main .data +0x00: compiled data, medium either way
    *((0x00000000,) * 7),
)

BLOB_INPUT_IMAGE = b"".join(struct.pack(">I", word) for word in BLOB_INPUT_WORDS)


def blob_input_map() -> LdMap:
    return parse_ld_map(BLOB_INPUT_MAP, path="blobs.map")


def blob_audit(**kwargs: object) -> ShiftAudit:
    return build_shift_audit(
        ldmap=blob_input_map(),
        image=BLOB_INPUT_IMAGE,
        pins=empty_pins(),
        model=default_pin_model(),
        map_path="blobs.map",
        image_path="blobs.z64",
        **kwargs,  # type: ignore[arg-type]
    )


def synthetic_map() -> LdMap:
    return parse_ld_map(SYNTHETIC_MAP, path="synthetic.map")


def empty_pins() -> PinCatalogue:
    return PinCatalogue(entries=(), sources=())


def read_pin_text(text: str) -> PinCatalogue:
    return PinCatalogue(
        entries=parse_pin_text(text, path="pins.txt", model=default_pin_model()),
        sources=("pins.txt",),
    )


def audit(
    *,
    blobs: tuple[str, ...] = (".boot",),
    whitelist: tuple[WhitelistEntry, ...] = (),
) -> ShiftAudit:
    return build_shift_audit(
        ldmap=synthetic_map(),
        image=SYNTHETIC_IMAGE,
        pins=empty_pins(),
        model=default_pin_model(whitelist=whitelist),
        blobs=blobs,
        map_path="synthetic.map",
        image_path="synthetic.z64",
    )


def tiers(found: ShiftAudit) -> dict[str, int]:
    return {
        "high": found.scan_high,
        "medium": found.scan_medium,
        "low": found.scan_low,
    }


def hit_at(found: ShiftAudit, rom: int) -> Hit:
    return next(item for item in found.hits if item.rom == rom)


# --------------------------------------------------------------------------
# WB-140 rule A -- a map that parsed to nothing
# --------------------------------------------------------------------------


class RequireParsedMapTests(unittest.TestCase):
    """Fresh-eyes QA: any `.z64` passed as `--map` parsed to zero sections
    and produced a clean, empty, exit-0 report. `require_parsed_map` is the
    refusal."""

    def test_a_map_with_sections_is_accepted(self) -> None:
        require_parsed_map(synthetic_map(), path="synthetic.map")

    def test_the_sniff_sample_is_a_small_bounded_read(self) -> None:
        """`MAP_SNIFF_BYTES` is the whole reason the CLI's sniff never pays
        for reading a multi-megabyte swapped-in image in full."""

        self.assertGreater(MAP_SNIFF_BYTES, 0)
        self.assertLess(MAP_SNIFF_BYTES, 1_000_000)

    def test_zero_sections_is_refused(self) -> None:
        empty = parse_ld_map("not a linker map, just some prose\n")
        self.assertEqual(empty.sections, ())
        with self.assertRaises(ValueError) as raised:
            require_parsed_map(empty, path="game.z64")
        message = str(raised.exception)
        self.assertIn("game.z64", message)
        self.assertIn("parsed as no linker map", message)

    def test_a_binary_looking_sample_adds_the_swap_hint(self) -> None:
        empty = parse_ld_map("")
        with self.assertRaises(ValueError) as raised:
            require_parsed_map(empty, path="game.z64", sample=b"\x80\x37\x12\x40\x00")
        message = str(raised.exception)
        self.assertIn("--map and --image may be swapped", message)

    def test_a_text_sample_carries_no_swap_hint(self) -> None:
        empty = parse_ld_map("")
        with self.assertRaises(ValueError) as raised:
            require_parsed_map(
                empty, path="notes.txt", sample=b"just some unrelated text\n"
            )
        message = str(raised.exception)
        self.assertNotIn("swapped", message)

    def test_the_default_sample_carries_no_swap_hint(self) -> None:
        """A caller with nothing to sniff (no bytes handed in) gets the
        plain refusal rather than a guess."""

        empty = parse_ld_map("")
        with self.assertRaises(ValueError) as raised:
            require_parsed_map(empty, path="whatever")
        self.assertNotIn("swapped", str(raised.exception))


# --------------------------------------------------------------------------
# WB-140 rule C -- a typo'd --blob matches nothing
# --------------------------------------------------------------------------


class BlobNameValidationTests(unittest.TestCase):
    """Every `--blob` name must be an output section the map actually has."""

    def test_a_real_section_name_is_accepted(self) -> None:
        build_region_table(
            synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=(".boot",)
        )

    def test_a_typo_is_refused_before_any_region_is_derived(self) -> None:
        with self.assertRaises(ValueError) as raised:
            build_region_table(
                synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=(".boot1",)
            )
        message = str(raised.exception)
        self.assertIn(
            "--blob names a section this map does not have: .boot1", message
        )
        self.assertIn(
            "map sections: .header, .boot, .main, .main_bss", message
        )

    def test_multiple_typos_are_all_named(self) -> None:
        with self.assertRaises(ValueError) as raised:
            build_region_table(
                synthetic_map(),
                image_size=len(SYNTHETIC_IMAGE),
                blobs=(".boot", ".nope", ".alsonope"),
            )
        message = str(raised.exception)
        self.assertIn(".nope", message)
        self.assertIn(".alsonope", message)
        # `.boot` is real and was not one of the ones refused.
        self.assertNotIn("map does not have: .boot,", message)

    def test_the_list_of_available_sections_is_capped(self) -> None:
        text = "Linker script and memory map\n\n" + "".join(
            f".sec{index:03d}      0x{index * 0x10:08x}       0x10\n"
            for index in range(30)
        )
        with self.assertRaises(ValueError) as raised:
            build_region_table(
                parse_ld_map(text), image_size=0x300, blobs=(".missing",)
            )
        message = str(raised.exception)
        self.assertIn("more)", message)


class RegionDerivationTests(unittest.TestCase):
    """The region table is read off the map, never configured by hand."""

    def setUp(self) -> None:
        self.regions = build_region_table(
            synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=(".boot",)
        )

    def test_one_region_per_kind_run(self) -> None:
        self.assertEqual(
            [(item.output_section, item.kind) for item in self.regions],
            [
                (".header", "header"),
                (".boot", "blob"),
                (".main", "text"),
                (".main", "data"),
                (".main_bss", "bss"),
            ],
        )

    def test_unlike_data_runs_merge_and_text_does_not_join_them(self) -> None:
        """`.data` and `.rodata` are one data run; `.text` stays its own."""

        text = next(item for item in self.regions if item.kind == "text")
        data = next(item for item in self.regions if item.kind == "data")
        self.assertEqual((text.vram, text.size), (0x80000400, 0x30))
        self.assertEqual((data.vram, data.size), (0x80000430, 0x50))

    def test_an_at_section_takes_its_rom_from_the_load_address(self) -> None:
        data = next(item for item in self.regions if item.kind == "data")
        self.assertEqual(data.rom, 0x50)
        self.assertEqual(data.rom_source, "load-address")

    def test_a_section_without_at_is_placed_by_its_vma_and_says_so(self) -> None:
        header = self.regions[0]
        self.assertEqual(header.rom, 0x00)
        self.assertEqual(header.rom_source, "vma-as-rom")

    def test_a_bss_section_owns_no_image_bytes_and_is_not_scanned(self) -> None:
        bss = next(item for item in self.regions if item.kind == "bss")
        self.assertFalse(bss.scanned)
        self.assertEqual(bss.rom_source, "not-resident")

    def test_text_is_placed_but_still_not_scanned(self) -> None:
        text = next(item for item in self.regions if item.kind == "text")
        self.assertEqual(text.rom, 0x20)
        self.assertFalse(text.scanned)

    def test_a_blob_designation_replaces_the_derived_kind(self) -> None:
        plain = build_region_table(
            synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=()
        )
        self.assertEqual(plain[1].kind, "data")
        self.assertEqual(self.regions[1].kind, "blob")

    def test_a_region_past_the_end_of_the_image_is_reported_unplaced(self) -> None:
        short = build_region_table(synthetic_map(), image_size=0x30, blobs=())
        unplaced = [item for item in short if item.rom_source == "unplaced"]
        self.assertTrue(unplaced)
        self.assertTrue(all(not item.scanned for item in unplaced))


class MovableWindowTests(unittest.TestCase):
    """The window comes from the map's own extent, not from a constant."""

    def test_the_window_runs_from_the_first_movable_start_to_the_last_bss_end(
        self,
    ) -> None:
        regions = build_region_table(
            synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=(".boot",)
        )
        window = movable_window(regions)
        self.assertEqual((window.lo, window.hi), (0x80000400, 0x800104A0))
        self.assertEqual(window.lo_section, ".main")
        self.assertEqual(window.hi_section, ".main_bss")

    def test_the_window_ignores_blobs_and_the_header(self) -> None:
        """A DMA'd segment's VMA is a load target, not a place code lives."""

        regions = build_region_table(
            synthetic_map(), image_size=len(SYNTHETIC_IMAGE), blobs=(".boot", ".header")
        )
        window = movable_window(regions)
        self.assertEqual(window.lo, 0x80000400)


# --------------------------------------------------------------------------
# S7 feature 1 -- the map already knows which sections are opaque
# --------------------------------------------------------------------------


class BlobRuleTests(unittest.TestCase):
    """The published raw-binary path shapes, as data."""

    def rule(self, name: str) -> BlobRule:
        return next(item for item in BLOB_OBJECT_RULES if item.name == name)

    def test_the_suffix_rule_matches_an_object_named_after_a_bin_file(self) -> None:
        rule = self.rule("bin-object-suffix")
        self.assertTrue(rule.matches("build/assets/boot.bin.o"))
        self.assertFalse(rule.matches("build/src/boot.c.o"))

    def test_the_directory_rule_matches_a_component_not_a_prefix(self) -> None:
        """`build/binaries/x.o` is not `build/bin/x.o`, and a file called
        `bin` is not a directory called `bin`."""

        rule = self.rule("bin-directory")
        self.assertTrue(rule.matches("build/bin/filesys.o"))
        self.assertTrue(rule.matches("build/us.v10/bin/core2/data_DC600.bin.o"))
        self.assertFalse(rule.matches("build/binaries/filesys.o"))
        self.assertFalse(rule.matches("build/src/bin"))

    def test_every_rule_carries_its_evidence(self) -> None:
        for rule in BLOB_OBJECT_RULES:
            with self.subTest(rule=rule.name):
                self.assertIn(rule.match, ("suffix", "directory"))
                self.assertTrue(rule.evidence)
                self.assertEqual(
                    set(rule.as_dict()), {"name", "pattern", "match", "evidence"}
                )


class BlobSuggestionTests(unittest.TestCase):
    """What the map's own input records say, before any caller says anything."""

    def setUp(self) -> None:
        self.suggestions = suggest_blobs(blob_input_map())

    def test_the_suggestion_is_every_all_raw_binary_section_in_map_order(
        self,
    ) -> None:
        self.assertEqual(
            [item.output_section for item in self.suggestions],
            [".boot", ".assets", ".filesys"],
        )

    def test_a_section_with_one_compiled_input_is_never_suggested(self) -> None:
        """BK's `.core2` holds three `.bin.o` objects among 398 compiled
        ones. A section with any compiled input has words worth attributing
        to symbols, which is the one thing `--blob` turns off."""

        self.assertNotIn(".main", [item.output_section for item in self.suggestions])

    def test_a_wholly_compiled_section_is_never_suggested(self) -> None:
        self.assertNotIn(".header", [item.output_section for item in self.suggestions])

    def test_a_section_with_no_input_records_is_never_suggested(self) -> None:
        """"Every input is a raw binary" is vacuously true of no inputs, and
        would make a blob out of every headerless section in a map."""

        empty = parse_ld_map(
            "Linker script and memory map\n\n.nothing        0x00000000       0x10\n",
            path="empty.map",
        )
        self.assertEqual(suggest_blobs(empty), ())

    def test_each_suggestion_carries_the_evidence_it_rests_on(self) -> None:
        found = {item.output_section: item for item in self.suggestions}
        self.assertEqual(found[".boot"].rule, "bin-object-suffix")
        self.assertEqual(found[".boot"].objects, ("build/assets/boot.bin.o",))
        self.assertEqual(found[".filesys"].rule, "bin-directory")
        self.assertEqual(found[".filesys"].objects, ("build/bin/filesys.o",))
        self.assertEqual(found[".filesys"].input_records, 1)
        self.assertEqual(found[".filesys"].vram, 0x30)
        self.assertEqual(found[".filesys"].size, 0x10)


class ResolveBlobsTests(unittest.TestCase):
    """`--blob`, `--blobs auto` and `--no-blob`, and how they compose."""

    def setUp(self) -> None:
        self.ldmap = blob_input_map()

    def test_naming_nothing_applies_nothing_and_still_reports_the_suggestion(
        self,
    ) -> None:
        plan = resolve_blobs(self.ldmap)
        self.assertEqual(plan.applied, ())
        self.assertEqual(plan.source, BLOB_SOURCE_NONE)
        self.assertEqual(plan.suggested, (".boot", ".assets", ".filesys"))
        self.assertEqual(plan.unadopted, (".boot", ".assets", ".filesys"))

    def test_explicit_names_are_applied_and_say_so(self) -> None:
        plan = resolve_blobs(self.ldmap, blobs=(".assets",))
        self.assertEqual(plan.applied, (".assets",))
        self.assertEqual(plan.source, BLOB_SOURCE_EXPLICIT)
        self.assertEqual(plan.unadopted, (".boot", ".filesys"))

    def test_auto_adopts_exactly_the_suggestion(self) -> None:
        plan = resolve_blobs(self.ldmap, auto=True)
        self.assertEqual(plan.applied, (".boot", ".assets", ".filesys"))
        self.assertEqual(plan.source, BLOB_SOURCE_AUTO)
        self.assertEqual(plan.unadopted, ())

    def test_blob_still_adds_on_top_of_auto(self) -> None:
        plan = resolve_blobs(self.ldmap, blobs=(".header",), auto=True)
        self.assertEqual(plan.applied, (".header", ".boot", ".assets", ".filesys"))
        self.assertEqual(plan.source, BLOB_SOURCE_AUTO)

    def test_no_blob_subtracts_from_auto(self) -> None:
        """pilotwings64's exact shape: the derivation is right about five of
        its six sections."""

        plan = resolve_blobs(self.ldmap, auto=True, excluded=(".boot",))
        self.assertEqual(plan.applied, (".assets", ".filesys"))
        self.assertEqual(plan.excluded, (".boot",))
        self.assertEqual(plan.unadopted, (".boot",))

    def test_naming_a_section_both_ways_is_refused_not_resolved(self) -> None:
        with self.assertRaises(ValueError) as raised:
            resolve_blobs(self.ldmap, blobs=(".assets",), excluded=(".assets",))
        message = str(raised.exception)
        self.assertIn("--blob and --no-blob name the same section", message)
        self.assertIn(".assets", message)

    def test_a_no_blob_typo_is_refused_the_same_way_a_blob_typo_is(self) -> None:
        with self.assertRaises(ValueError) as raised:
            resolve_blobs(self.ldmap, auto=True, excluded=(".asset",))
        self.assertIn(
            "--no-blob names a section this map does not have: .asset",
            str(raised.exception),
        )

    def test_subtracting_everything_reports_no_source_rather_than_auto(self) -> None:
        plan = resolve_blobs(
            self.ldmap, auto=True, excluded=(".boot", ".assets", ".filesys")
        )
        self.assertEqual(plan.applied, ())
        self.assertEqual(plan.source, BLOB_SOURCE_NONE)

    def test_the_plan_travels_as_json_with_its_rules(self) -> None:
        payload = resolve_blobs(self.ldmap, auto=True).as_dict()
        self.assertEqual(payload["blobs"], [".boot", ".assets", ".filesys"])
        self.assertEqual(payload["blob_source"], BLOB_SOURCE_AUTO)
        self.assertEqual(payload["suggested_blobs"], [".boot", ".assets", ".filesys"])
        self.assertEqual(payload["blobs_excluded"], [])
        self.assertEqual(
            [item["name"] for item in payload["blob_rules"]],
            [item.name for item in BLOB_OBJECT_RULES],
        )
        first = payload["blob_suggestions"][0]
        self.assertEqual(
            set(first),
            {"output_section", "rule", "objects", "input_records", "vram", "size"},
        )
        json.dumps(payload)


class AutoBlobEquivalenceTests(unittest.TestCase):
    """Adopting the suggestion has to be the same run as naming it by hand."""

    def test_auto_and_the_explicit_flags_agree_on_every_number(self) -> None:
        auto = blob_audit(auto_blobs=True).as_dict(limit=10)
        explicit = blob_audit(blobs=(".boot", ".assets", ".filesys")).as_dict(limit=10)
        auto.pop("blob_source"), explicit.pop("blob_source")
        # The only remaining difference is the order the two spellings name
        # the set in: `--blob` keeps the caller's order, `auto` keeps the
        # map's.
        self.assertEqual(sorted(auto.pop("blobs")), sorted(explicit.pop("blobs")))
        self.assertEqual(auto, explicit)

    def test_adopting_the_suggestion_demotes_the_word_inside_the_blob(self) -> None:
        """The suggestion is not cosmetic: a word in an opaque segment scores
        at the blob noise floor rather than as compiled data."""

        self.assertEqual(hit_at(blob_audit(), 0x30).tier, "medium")
        self.assertEqual(hit_at(blob_audit(auto_blobs=True), 0x30).tier, "low")
        self.assertEqual(hit_at(blob_audit(auto_blobs=True), 0x60).tier, "medium")


# --------------------------------------------------------------------------
# S7 feature 4 -- the movable window's floor
# --------------------------------------------------------------------------


class MovableWindowFloorTests(unittest.TestCase):
    """S5's pilotwings64 finding: a ROM-space section is not a floor.

    That project's IPL3 arrives as `build/bin/ipl3.o`, derives as an ordinary
    `data` region at VMA `0x00000040` (a boot block is placed at its ROM
    offset; it has no run-time address), and used to drag the window's low
    bound down with it -- a window two gigabytes wider at the bottom than the
    layout it describes.
    """

    def test_a_rom_space_region_never_sets_the_floor(self) -> None:
        window = movable_window(build_region_table(blob_input_map(), image_size=0x80))
        self.assertEqual(window.lo, 0x80000400)
        self.assertEqual(window.lo_section, ".main")

    def test_the_floor_is_residence_not_the_callers_blob_list(self) -> None:
        """Excluding the low section by *kind* would need the caller to have
        named it `--blob` first, which is the discovery problem, not the fix."""

        named = movable_window(
            build_region_table(
                blob_input_map(),
                image_size=0x80,
                blobs=(".boot", ".assets", ".filesys"),
            )
        )
        derived = movable_window(
            build_region_table(blob_input_map(), image_size=0x80)
        )
        self.assertEqual(named.lo, derived.lo)
        self.assertEqual(named.lo_section, derived.lo_section)

    def test_the_high_bound_is_untouched(self) -> None:
        window = movable_window(build_region_table(blob_input_map(), image_size=0x80))
        self.assertEqual(window.hi, 0x80000460)
        self.assertEqual(window.hi_section, ".main_bss")

    def test_a_map_with_no_ram_resident_region_keeps_the_old_answer(self) -> None:
        """Not a real N64 link -- but inventing an empty window for one would
        hide the map rather than describe it."""

        regions = (
            region(".low", "data", vram=0x40, size=0x10, rom=0x40),
            region(".lower", "data", vram=0x20, size=0x10, rom=0x20),
        )
        window = movable_window(regions)
        self.assertEqual(window.lo, 0x20)
        self.assertEqual(window.lo_section, ".lower")

    def test_the_floor_is_the_shared_ram_boundary(self) -> None:
        self.assertEqual(MOVABLE_FLOOR_MIN, 0x80000000)

    def test_the_fix_narrows_the_scan_to_the_layout(self) -> None:
        """The header word holding `0x00000020` was an in-window hit only
        because the window started at `0x00000010`."""

        found = blob_audit()
        self.assertEqual(found.scan_total, 2)
        self.assertEqual([item.rom for item in found.hits], [0x30, 0x60])


class NonAllocSectionTests(unittest.TestCase):
    """WB-138: a non-alloc section (debug info, symbol-table metadata GNU ld
    still prints VMA and all) must never become a scannable region, must
    never enter the movable window, and must never contribute a
    ``vma-as-rom`` placement at whatever VMA it happens to print -- but it
    must still show up in the region table, not vanish silently."""

    NAMES = (
        ".mdebug",
        ".mdebug.abi32",
        ".pdr",
        ".comment",
        ".gptab.sdata",
        ".reginfo",
        ".options",
        ".debug_info",
        ".line",
        ".rel.text",
    )

    def setUp(self) -> None:
        self.regions = build_region_table(
            parse_ld_map(NON_ALLOC_MAP), image_size=0x200, blobs=()
        )
        self.by_section = {item.output_section: item for item in self.regions}

    def test_every_known_family_member_is_recognized(self) -> None:
        self.assertEqual(
            {name for name, _ in NON_ALLOC_SECTION_FAMILIES},
            {".mdebug", ".pdr", ".comment", ".gptab", ".reginfo", ".options",
             ".debug", ".line", ".rel."},
        )

    def test_every_known_family_member_is_excluded(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                region = self.by_section[name]
                self.assertEqual(region.kind, NON_ALLOC_KIND)
                self.assertIsNone(region.rom)
                self.assertEqual(region.rom_source, NON_ALLOC_ROM_SOURCE)
                self.assertFalse(region.scanned)

    def test_excluded_regions_never_contribute_a_vma_as_rom_placement(self) -> None:
        """`.mdebug` really does print VMA 0 -- the shape that let it become
        a bogus `rom_source=vma-as-rom` region at ROM offset 0 before this
        fix, indistinguishable from the ROM's own base."""

        mdebug = self.by_section[".mdebug"]
        self.assertEqual(mdebug.vram, 0)
        self.assertIsNone(mdebug.rom)
        self.assertNotEqual(mdebug.rom_source, "vma-as-rom")

    def test_excluded_regions_are_still_visible_in_the_region_table(self) -> None:
        """Never a silent drop: every excluded section keeps its own row,
        with the reason machine-readable in `kind`/`rom_source`."""

        present = {item.output_section for item in self.regions}
        for name in self.NAMES:
            self.assertIn(name, present)

    def test_the_window_ignores_every_excluded_section(self) -> None:
        window = movable_window(self.regions)
        self.assertEqual(window.lo, 0x80000400)
        self.assertEqual(window.lo_section, ".main")

    def test_a_family_match_with_an_explicit_load_address_is_not_excluded(self) -> None:
        """An explicit `AT()` always outranks the name-based inference --
        the same rule `decomp_workbench.ldmap` applies to every address it
        resolves."""

        regions = build_region_table(
            parse_ld_map(NON_ALLOC_WITH_AT_MAP), image_size=0x300, blobs=()
        )
        comment = next(item for item in regions if item.output_section == ".comment")
        self.assertNotEqual(comment.kind, NON_ALLOC_KIND)
        self.assertEqual(comment.rom, 0x200)
        self.assertEqual(comment.rom_source, "load-address")


class OverlaySiblingRegionTests(unittest.TestCase):
    """WB-139 regression: several output sections sharing one VMA (an N64
    overlay group) must each resolve their own ROM placement from their own
    section's own load address -- never another sibling's, and never by
    looking the shared VMA back up. Confirms `build_region_table` was
    already positional (keyed off the specific `OutputSection` object the
    parser attached each input record to), not the address-lookup the
    original hypothesis suspected."""

    def setUp(self) -> None:
        self.regions = build_region_table(
            parse_ld_map(OVERLAY_SIBLING_MAP), image_size=0x300000, blobs=()
        )
        self.by_key = {(item.output_section, item.kind): item for item in self.regions}

    def test_each_sibling_resolves_through_its_own_load_address(self) -> None:
        a_text = self.by_key[(".overlay_a", "text")]
        b_text = self.by_key[(".overlay_b", "text")]
        self.assertEqual(a_text.rom, 0x100000)
        self.assertEqual(b_text.rom, 0x200000)
        self.assertEqual(a_text.rom_source, "load-address")
        self.assertEqual(b_text.rom_source, "load-address")

    def test_a_later_run_in_the_same_section_walks_from_that_sections_load_address(
        self,
    ) -> None:
        """`.overlay_a`'s `.data` run starts mid-section: its placement is
        `.overlay_a`'s own load address plus its own offset into the
        section, not `.overlay_b`'s address at all."""

        a_data = self.by_key[(".overlay_a", "data")]
        self.assertEqual(a_data.rom, 0x100010)
        self.assertEqual(a_data.rom_source, "load-address")


# --------------------------------------------------------------------------
# WB-140 rule B -- does this image match this map?
# --------------------------------------------------------------------------


def region(
    output_section: str,
    kind: str,
    *,
    vram: int = 0,
    size: int,
    rom: int | None,
    rom_source: str = "load-address",
) -> Region:
    return Region(
        output_section=output_section,
        kind=kind,
        vram=vram,
        size=size,
        rom=rom,
        rom_source=rom_source,
    )


class ConsistencyCheckTests(unittest.TestCase):
    """`check_map_image_consistency` against hand-built region tables --
    the same shapes S0's real DKR artifacts exercise, isolated so each rule
    has exactly one scenario driving it."""

    def test_an_exact_match_reports_zero_padding_and_zero_unplaced(self) -> None:
        regions = (region(".data", "data", size=0x40, rom=0x00),)
        found = check_map_image_consistency(regions, bytes(0x40))
        self.assertEqual(found.max_placed_extent, 0x40)
        self.assertEqual(found.padding_bytes, 0)
        self.assertEqual(found.regions_unplaced_past_eof, 0)

    def test_zero_fill_excess_is_accepted_as_padding(self) -> None:
        regions = (region(".data", "data", size=0x40, rom=0x00),)
        image = bytes(0x40) + bytes(0x10)  # 16 zero bytes past the extent
        found = check_map_image_consistency(regions, image)
        self.assertEqual(found.padding_bytes, 0x10)

    def test_0xff_fill_excess_is_accepted_as_padding(self) -> None:
        """The real-world case: a retail cart padded to its rounded size."""

        regions = (region(".data", "data", size=0x40, rom=0x00),)
        image = bytes(0x40) + (b"\xff" * 0x10)
        found = check_map_image_consistency(regions, image)
        self.assertEqual(found.padding_bytes, 0x10)

    def test_a_short_repeating_pattern_is_accepted_as_padding(self) -> None:
        regions = (region(".data", "data", size=0x40, rom=0x00),)
        image = bytes(0x40) + (b"\xab\xcd" * 8)
        found = check_map_image_consistency(regions, image)
        self.assertEqual(found.padding_bytes, 0x10)

    def test_a_non_uniform_excess_is_a_hard_error_naming_both_numbers(self) -> None:
        """Rule (2)'s core case: real content past the map's own extent,
        not padding -- QA's exact repro shape (S0 nm-base map, shift-0x10
        image), reproduced by hand here."""

        regions = (region(".data", "data", size=0x40, rom=0x00),)
        image = bytes(0x40) + bytes.fromhex("030f05ac0fee028c15f0007402fb0c13")
        with self.assertRaises(ValueError) as raised:
            check_map_image_consistency(regions, image)
        message = str(raised.exception)
        self.assertIn("extends 16 bytes past the map's placed extent", message)
        self.assertIn("not uniform padding", message)
        self.assertIn("different builds", message)
        self.assertIn("image_bytes=80", message)
        self.assertIn("map_placed_extent=64", message)

    def test_the_error_names_the_map_and_image_paths_when_given(self) -> None:
        regions = (region(".data", "data", size=0x40, rom=0x00),)
        image = bytes(0x40) + bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
        with self.assertRaises(ValueError) as raised:
            check_map_image_consistency(
                regions, image, map_path="game.map", image_path="game.z64"
            )
        message = str(raised.exception)
        self.assertIn("game.map", message)
        self.assertIn("game.z64", message)

    def test_a_minority_of_regions_past_eof_is_reported_not_refused(self) -> None:
        """Rule (3): some truncation is common enough (an overlay simply
        not linked into this particular image) to report rather than
        refuse. One of three placeable regions lands past EOF."""

        regions = (
            region(".a", "data", size=0x10, rom=0x00),
            region(".b", "data", size=0x10, rom=0x10),
            region(".c", "data", size=0x10, rom=0x20),
        )
        found = check_map_image_consistency(regions, bytes(0x28))  # 8 bytes short
        self.assertEqual(found.max_placed_extent, 0x30)
        self.assertIsNone(found.padding_bytes)
        self.assertEqual(found.regions_unplaced_past_eof, 1)

    def test_a_majority_of_regions_past_eof_is_the_wrong_image(self) -> None:
        """Rule (3)'s hard-error branch: more than half of the map's placed
        regions land past the end of the image."""

        regions = (
            region(".a", "data", size=0x10, rom=0x00),
            region(".b", "data", size=0x10, rom=0x10),
            region(".c", "data", size=0x10, rom=0x20),
        )
        with self.assertRaises(ValueError) as raised:
            check_map_image_consistency(regions, bytes(0x18))  # only .a fully fits
        message = str(raised.exception)
        self.assertIn("2 of 3 placed regions land past the end", message)
        self.assertIn("not an overlay quirk", message)
        self.assertIn("that is the wrong image", message)

    def test_a_region_whose_start_fits_but_whose_tail_overruns_still_counts(
        self,
    ) -> None:
        """`_placement` only ever refuses a region whose *start* is past the
        image -- a region that starts inside the image but is truncated by
        a short image keeps its ordinary `rom_source` (`load-address`), and
        would look unremarkable in the region table on its own. This is
        exactly the row `regions_unplaced_past_eof` exists to catch."""

        regions = (
            region(".a", "data", size=0x10, rom=0x00),
            region(".b", "data", size=0x20, rom=0x10, rom_source="load-address"),
        )
        found = check_map_image_consistency(regions, bytes(0x18))  # cuts .b short
        self.assertEqual(found.regions_unplaced_past_eof, 1)

    def test_bss_and_non_alloc_regions_never_count_toward_the_ratio(self) -> None:
        """Neither kind ever claims image bytes (`rom` is always `None`),
        so neither should inflate `regions_unplaced_past_eof` or its
        denominator -- only `SCANNED_KINDS`-adjacent placed kinds do."""

        regions = (
            region(".a", "data", size=0x10, rom=0x00),
            region(".bss", "bss", size=0x1000, rom=None, rom_source="not-resident"),
            region(
                ".mdebug",
                NON_ALLOC_KIND,
                size=0x2000,
                rom=None,
                rom_source=NON_ALLOC_ROM_SOURCE,
            ),
        )
        found = check_map_image_consistency(regions, bytes(0x10))
        self.assertEqual(found.max_placed_extent, 0x10)
        self.assertEqual(found.regions_unplaced_past_eof, 0)
        self.assertEqual(found.padding_bytes, 0)

    def test_the_dataclass_round_trips_through_as_dict(self) -> None:
        found = ConsistencyCheck(
            max_placed_extent=0x10, padding_bytes=4, regions_unplaced_past_eof=0
        )
        self.assertEqual(
            found.as_dict(),
            {
                "max_placed_extent": 0x10,
                "padding_bytes": 4,
                "regions_unplaced_past_eof": 0,
            },
        )


class ScanFeatureTests(unittest.TestCase):
    """Every confidence feature, one word each."""

    def setUp(self) -> None:
        self.audit = audit()

    def test_text_words_are_counted_but_never_scanned(self) -> None:
        self.assertEqual(self.audit.text_words, 12)
        self.assertEqual(self.audit.text_regions, 1)
        self.assertEqual(
            [item.rom for item in self.audit.hits if item.rom < 0x50],
            [0x04, 0x10, 0x14],
        )

    def test_the_scan_covers_data_blob_and_header_regions(self) -> None:
        self.assertEqual(self.audit.scanned_words, 28)
        self.assertEqual(self.audit.scan_total, 15)

    def test_alignment_is_recorded_and_demotes(self) -> None:
        hit = hit_at(self.audit, 0x54)
        self.assertEqual(hit.alignment, 3)
        self.assertEqual(hit.rule, "misaligned")
        self.assertEqual(hit.tier, "low")

    def test_pointing_at_a_symbol_start_elevates(self) -> None:
        hit = hit_at(self.audit, 0x50)
        self.assertTrue(hit.points_at_symbol_start)
        self.assertEqual(hit.target_symbol, "gTarget")
        self.assertEqual(hit.target_offset, 0)
        self.assertEqual(hit.tier, "high")

    def test_pointing_into_the_middle_of_a_symbol_does_not(self) -> None:
        hit = hit_at(self.audit, 0x5C)
        self.assertFalse(hit.points_at_symbol_start)
        self.assertEqual(hit.target_symbol, "gOther")
        self.assertEqual(hit.target_offset, 4)
        self.assertEqual(hit.tier, "medium")

    def test_blob_residence_demotes_the_same_value_that_data_elevates(self) -> None:
        self.assertEqual(hit_at(self.audit, 0x10).value, hit_at(self.audit, 0x50).value)
        self.assertEqual(hit_at(self.audit, 0x10).tier, "medium")
        self.assertEqual(hit_at(self.audit, 0x50).tier, "high")

    def test_a_blob_hit_is_not_attributed_to_a_symbol(self) -> None:
        """S0's own dump read asset bytes through `.main`'s ROM mapping and
        labelled them `gAudioHeapStack+0x...`. A blob's VMA is a DMA target,
        so residence is reported as the section and nothing more."""

        self.assertIsNone(hit_at(self.audit, 0x10).resident_symbol)
        self.assertEqual(hit_at(self.audit, 0x10).region, ".boot")
        self.assertEqual(hit_at(self.audit, 0x50).resident_symbol, "gData")
        self.assertEqual(hit_at(self.audit, 0x54).resident_offset, 4)

    def test_a_constant_stride_arithmetic_progression_is_one_cluster(self) -> None:
        members = [item for item in self.audit.hits if item.cluster is not None]
        self.assertEqual([item.rom for item in members], [0x60, 0x64, 0x68])
        self.assertEqual({item.cluster for item in members}, {0})
        self.assertEqual({item.rule for item in members}, {"progression-cluster"})
        self.assertEqual({item.tier for item in members}, {"low"})
        self.assertGreaterEqual(len(members), CLUSTER_MINIMUM)

    def test_a_repeated_value_is_counted_and_demoted_but_not_dropped(self) -> None:
        repeats = [item for item in self.audit.hits if item.value == 0x80000474]
        self.assertEqual(len(repeats), REPEAT_MINIMUM)
        self.assertEqual({item.repeats for item in repeats}, {REPEAT_MINIMUM})
        self.assertEqual({item.rule for item in repeats}, {"repeated-value"})
        self.assertEqual({item.tier for item in repeats}, {"low"})

    def test_a_repeat_is_not_reported_as_a_cluster(self) -> None:
        """A progression whose difference is zero is a repeat, and the repeat
        rule is the one that names it; two rules for one family would double
        count it in the rule tally."""

        self.assertTrue(
            all(item.cluster is None for item in self.audit.hits if item.repeats > 1)
        )

    def test_a_round_value_with_no_symbol_under_it_is_a_constant(self) -> None:
        hit = hit_at(self.audit, 0x58)
        self.assertEqual(hit.rule, "round-constant")
        self.assertEqual(hit.tier, "low")

    def test_a_whitelisted_value_is_demoted_with_the_reason_attached(self) -> None:
        whitelisted = audit(
            whitelist=(WhitelistEntry(0x80000480, 0x80000481, "the caller says so"),)
        )
        hit = hit_at(whitelisted, 0x80)
        self.assertEqual(hit.rule, "whitelisted")
        self.assertEqual(hit.tier, "low")
        self.assertTrue(hit.whitelisted)
        self.assertEqual(hit.reason, "the caller says so")
        self.assertEqual(hit_at(audit(), 0x80).tier, "medium")


class TierTotalTests(unittest.TestCase):
    """The totals are the sum of the fixture's per-word comments."""

    def test_the_synthetic_totals_are_readable_by_hand(self) -> None:
        found = audit()
        self.assertEqual(tiers(found), {"high": 1, "medium": 3, "low": 11})
        self.assertEqual(sum(tiers(found).values()), found.scan_total)

    def test_dropping_the_blob_designation_promotes_the_boot_words(self) -> None:
        """Both boot words move up one tier, and nothing else changes."""

        found = audit(blobs=())
        self.assertEqual(tiers(found), {"high": 2, "medium": 3, "low": 10})

    def test_the_rule_tally_partitions_the_scan(self) -> None:
        found = audit()
        self.assertEqual(sum(found.scan_rules.values()), found.scan_total)
        self.assertEqual(
            found.scan_rules,
            {
                "misaligned": 1,
                "progression-cluster": 3,
                "repeated-value": 4,
                "round-constant": 1,
                "scored": 6,
            },
        )

    def test_every_rule_a_hit_can_carry_is_in_the_published_table(self) -> None:
        published = {item.name for item in TIER_RULES} | {"scored"}
        found = audit(
            whitelist=(WhitelistEntry(0x80000480, 0x80000481, "the caller says so"),)
        )
        self.assertLessEqual({item.rule for item in found.hits}, published)
        self.assertEqual(set(RESIDENCE_SCORES), {"data", "header", "blob"})


class ReportShapeTests(unittest.TestCase):
    """The JSON contract, and the human report the same numbers render to."""

    def setUp(self) -> None:
        self.audit = audit()
        self.payload = self.audit.as_dict(limit=4)

    def test_the_census_keys_are_top_level_scalars(self) -> None:
        for key in (
            "pins_total",
            "pins_derived",
            "pins_authentic",
            "pins_artifact",
            "pins_unclassified",
            "scan_total",
            "scan_high",
            "scan_medium",
            "scan_low",
            "scanned_words",
            "text_words",
            "text_regions",
            "region_count",
            "image_bytes",
            "window_lo",
            "window_hi",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.payload)
                self.assertIsInstance(self.payload[key], int | str)

    def test_the_detail_lists_name_their_own_cap(self) -> None:
        self.assertEqual(self.payload["limit"], 4)
        self.assertEqual(self.payload["hits_shown"], 4)
        self.assertEqual(len(self.payload["hits"]), 4)
        self.assertEqual(self.payload["scan_total"], 15)

    def test_hits_are_ranked_before_they_are_capped(self) -> None:
        tiers_shown = [item["tier"] for item in self.payload["hits"]]
        self.assertEqual(tiers_shown[0], "high")
        self.assertEqual(tiers_shown[1:4], ["medium", "medium", "medium"])

    def test_the_rules_are_data_and_travel_with_the_report(self) -> None:
        names = [item["name"] for item in self.payload["rules"]]
        self.assertIn("misaligned", names)
        self.assertIn("progression-cluster", names)
        for rule in self.payload["rules"]:
            self.assertEqual(set(rule), {"name", "tier", "evidence"})
        self.assertEqual(self.payload["residence_scores"]["blob"], 0)
        self.assertEqual(self.payload["tier_thresholds"]["high"], 3)

    def test_the_region_table_travels_with_the_report(self) -> None:
        names = [
            (item["output_section"], item["kind"]) for item in self.payload["regions"]
        ]
        self.assertIn((".main", "text"), names)
        self.assertIn((".main_bss", "bss"), names)
        self.assertEqual(self.payload["region_count"], 5)

    def test_the_payload_is_plain_json(self) -> None:
        json.dumps(self.payload)

    def test_every_json_key_the_report_emits_is_registered(self) -> None:
        """`--explain-keys` has to reach every key, nested ones included."""

        def keys(value: object) -> set[str]:
            if isinstance(value, dict):
                found: set[str] = set()
                for key, item in value.items():
                    found.add(key)
                    found |= keys(item)
                return found
            if isinstance(value, list):
                return {name for item in value for name in keys(item)}
            return set()

        # `schema` is registered; the scan/rule tallies are keyed by rule and
        # region name rather than by metric, so their own keys are values.
        emitted = keys(self.payload) - {"schema"}
        emitted -= set(self.payload["scan_rules"])
        emitted -= set(self.payload["scan_by_region"])
        emitted -= set(self.payload["residence_scores"])
        emitted -= set(self.payload["tier_thresholds"])
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))
        text = explain_keys_text()
        for key in emitted:
            with self.subTest(key=key):
                self.assertIn(key, text)

    def test_every_printed_label_is_one_of_those_keys(self) -> None:
        """The house rule: a printed label and its JSON key are one string.

        Table headers are checked because they are where a report drifts: a
        column called `placed by` reads well and cannot be looked up.
        """

        registered = set(SHIFT_METRICS_BY_KEY)
        headers = (
            "output_section kind vram size rom rom_source words scanned",
            "name value window source line",
            "rule count",
            "region count",
            "rom value tier rule region resident_symbol target_symbol",
        )
        for row in headers:
            for label in row.split():
                with self.subTest(label=label):
                    self.assertIn(label, registered)
        # Rendered with a pin catalogue, so the suspect table is present too.
        with_pins = build_shift_audit(
            ldmap=synthetic_map(),
            image=SYNTHETIC_IMAGE,
            pins=read_pin_text("D_B0000574 = 0xB0000574;\n"),
            model=default_pin_model(),
            blobs=(".boot",),
        )
        text = "\n".join(shift_audit_lines(with_pins, limit=4))
        for row in headers:
            with self.subTest(row=row):
                self.assertTrue(
                    any(line.split() == row.split() for line in text.splitlines()),
                    f"no table in the report has the header {row!r}",
                )

    def test_the_census_registry_is_exactly_the_shift_vocabulary(self) -> None:
        self.assertEqual(set(SHIFT_CENSUS_KEYS), set(SHIFT_METRICS_BY_KEY))

    def test_the_human_report_prints_the_same_numbers(self) -> None:
        lines = shift_audit_lines(self.audit, limit=4)
        text = "\n".join(lines)
        self.assertIn("scan_total", text)
        self.assertIn("15", text)
        self.assertIn("0x80000400", text)
        self.assertIn("shift rehearse", text)
        # No silent truncation: the cap is printed beside the total.
        self.assertIn("4 of 15", text)

    def test_the_human_report_says_what_the_text_words_are_for(self) -> None:
        text = "\n".join(shift_audit_lines(self.audit, limit=4))
        self.assertIn("12", text)
        self.assertIn("not scanned", text)


class BlobReportTests(unittest.TestCase):
    """The cold-start line, and the keys behind it."""

    def test_a_run_that_named_no_blob_is_told_what_the_map_thinks(self) -> None:
        text = "\n".join(shift_audit_lines(blob_audit(), limit=4))
        self.assertIn("blobs=-  blob_source=none", text)
        self.assertIn(
            "suggested_blobs (from .bin.o inputs): .boot, .assets, .filesys", text
        )
        self.assertIn("--blobs auto", text)

    def test_adopting_the_suggestion_leaves_nothing_left_to_suggest(self) -> None:
        text = "\n".join(shift_audit_lines(blob_audit(auto_blobs=True), limit=4))
        self.assertIn("blobs=.boot, .assets, .filesys  blob_source=auto", text)
        self.assertNotIn("suggested_blobs (from", text)

    def test_an_exclusion_is_printed_rather_than_silently_applied(self) -> None:
        text = "\n".join(
            shift_audit_lines(
                blob_audit(auto_blobs=True, excluded_blobs=(".boot",)), limit=4
            )
        )
        self.assertIn("blobs_excluded=.boot", text)
        self.assertIn("suggested_blobs (from .bin.o inputs): .boot", text)

    def test_every_key_a_suggesting_report_emits_is_registered(self) -> None:
        """`ReportShapeTests` reads a map with no raw-binary inputs at all,
        so the nested suggestion keys only appear here."""

        payload = blob_audit(auto_blobs=True).as_dict(limit=4)
        emitted = {
            key
            for row in payload["blob_suggestions"] + payload["blob_rules"]
            for key in row
        }
        self.assertTrue(emitted)
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))
        text = explain_keys_text()
        for key in emitted | {"blobs", "blob_source", "blobs_excluded"}:
            with self.subTest(key=key):
                self.assertIn(key, text)


# --------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------


class CommandTests(unittest.TestCase):
    """Argument handling, exit codes, and the JSON envelope."""

    root: ClassVar[Path]

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.map_path = self.root / "synthetic.map"
        self.image_path = self.root / "synthetic.z64"
        self.map_path.write_text(SYNTHETIC_MAP, encoding="utf-8")
        self.image_path.write_bytes(SYNTHETIC_IMAGE)

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def base_arguments(self) -> list[str]:
        return [
            "shift",
            "audit",
            "--map",
            str(self.map_path),
            "--image",
            str(self.image_path),
            "--blob",
            ".boot",
        ]

    def test_the_group_spelling_runs(self) -> None:
        status, stdout, _ = self.run_cli(self.base_arguments())
        self.assertEqual(status, 0)
        self.assertIn("shift audit", stdout)

    def test_json_carries_the_schema_identity(self) -> None:
        status, stdout, _ = self.run_cli([*self.base_arguments(), "--json"])
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-shift-audit-v1")
        self.assertEqual(payload["scan_total"], 15)
        self.assertEqual(payload["scan_high"], 1)

    def test_the_blob_option_is_repeatable_and_changes_the_answer(self) -> None:
        _, plain, _ = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                str(self.map_path),
                "--image",
                str(self.image_path),
                "--json",
            ]
        )
        self.assertEqual(json.loads(plain)["scan_high"], 2)

    def test_a_pin_file_is_read_and_counted(self) -> None:
        pins = self.root / "undefined_syms.txt"
        pins.write_text(
            "/* fake */\nD_B0000574 = 0xB0000574;\ngPool = main_BSS_END;\n",
            encoding="utf-8",
        )
        status, stdout, _ = self.run_cli(
            [*self.base_arguments(), "--pins", str(pins), "--json"]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["pins_total"], 2)
        self.assertEqual(payload["pins_artifact"], 1)
        self.assertEqual(payload["pins_derived"], 1)

    def test_a_whitelist_file_reaches_both_the_pins_and_the_scan(self) -> None:
        pins = self.root / "undefined_syms.txt"
        pins.write_text("osTvType = 0x80000300;\n", encoding="utf-8")
        whitelist = self.root / "whitelist.txt"
        whitelist.write_text(
            "# the caller's claim, with its reason\n"
            "0x80000300-0x80000400 boot globals\n"
            "0x80000480 a fixed thing\n",
            encoding="utf-8",
        )
        status, stdout, _ = self.run_cli(
            [
                *self.base_arguments(),
                "--pins",
                str(pins),
                "--whitelist",
                str(whitelist),
                "--json",
            ]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["pins_authentic"], 1)
        self.assertEqual(payload["scan_medium"], 2)

    def test_a_malformed_whitelist_line_is_refused_before_any_work(self) -> None:
        whitelist = self.root / "whitelist.txt"
        whitelist.write_text("0x80000300\n", encoding="utf-8")
        status, _, stderr = self.run_cli(
            [*self.base_arguments(), "--whitelist", str(whitelist)]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_a_missing_image_is_a_usage_failure_not_a_traceback(self) -> None:
        status, _, stderr = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                str(self.map_path),
                "--image",
                str(self.root / "absent.z64"),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_a_map_that_parses_to_zero_sections_is_refused(self) -> None:
        """WB-140 rule A, through the real CLI: a binary file passed as
        `--map` (QA's repro was a `.z64` image) parses to zero sections and
        is refused, with the swap hint, rather than an empty exit-0
        report."""

        bogus_map = self.root / "not-a-map.z64"
        bogus_map.write_bytes(bytes(range(256)) * 4)  # plenty of NUL bytes
        status, _, stderr = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                str(bogus_map),
                "--image",
                str(self.image_path),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn(str(bogus_map), stderr)
        self.assertIn("parsed as no linker map", stderr)
        self.assertIn("--map and --image may be swapped", stderr)

    def test_a_mismatched_image_is_refused(self) -> None:
        """WB-140 rule B, through the real CLI: an image longer than the
        map's placed extent, by bytes that are not uniform padding."""

        mismatched = self.root / "mismatched.z64"
        mismatched.write_bytes(SYNTHETIC_IMAGE + bytes.fromhex("0102030405060708"))
        status, _, stderr = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                str(self.map_path),
                "--image",
                str(mismatched),
                "--blob",
                ".boot",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn("not uniform padding", stderr)
        self.assertIn("different builds", stderr)

    def test_an_unknown_blob_name_is_refused(self) -> None:
        status, _, stderr = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                str(self.map_path),
                "--image",
                str(self.image_path),
                "--blob",
                ".nope",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn("--blob names a section this map does not have: .nope", stderr)

    def test_census_passes_and_fails_with_the_house_exit_codes(self) -> None:
        passing, _, _ = self.run_cli(
            [*self.base_arguments(), "--census", "scan_high=1"]
        )
        self.assertEqual(passing, 0)
        failing, stdout, _ = self.run_cli(
            [*self.base_arguments(), "--census", "scan_high=99"]
        )
        self.assertEqual(failing, 3)
        self.assertIn("census: FAIL", stdout)

    def test_an_unknown_census_key_is_refused_before_reading_anything(self) -> None:
        status, _, stderr = self.run_cli(
            [
                "shift",
                "audit",
                "--map",
                "absent.map",
                "--image",
                "absent.z64",
                "--census",
                "x=1",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("unknown census key 'x'", stderr)

    def test_explain_keys_covers_the_shift_vocabulary(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(["shift", "audit", "--explain-keys"])
        self.assertEqual(raised.exception.code, 0)

    def test_naming_no_operation_prints_the_group_listing(self) -> None:
        status, stdout, _ = self.run_cli(["shift"])
        self.assertEqual(status, 0)
        self.assertIn("audit", stdout)

    def test_the_limit_is_honoured_and_named(self) -> None:
        status, stdout, _ = self.run_cli([*self.base_arguments(), "--limit", "2"])
        self.assertEqual(status, 0)
        self.assertIn("2 of 15", stdout)


class BlobCommandTests(unittest.TestCase):
    """`--blobs auto`, `--no-blob`, through argparse and the real reader."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.map_path = self.root / "blobs.map"
        self.image_path = self.root / "blobs.z64"
        self.map_path.write_text(BLOB_INPUT_MAP, encoding="utf-8")
        self.image_path.write_bytes(BLOB_INPUT_IMAGE)

    def run_json(self, extra: list[str]) -> tuple[int, dict]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(
                [
                    "shift",
                    "audit",
                    "--map",
                    str(self.map_path),
                    "--image",
                    str(self.image_path),
                    "--json",
                    *extra,
                ]
            )
        return status, (json.loads(stdout.getvalue()) if status == 0 else {})

    def test_the_suggestion_travels_even_when_nothing_adopts_it(self) -> None:
        status, payload = self.run_json([])
        self.assertEqual(status, 0)
        self.assertEqual(payload["blobs"], [])
        self.assertEqual(payload["blob_source"], "none")
        self.assertEqual(
            payload["suggested_blobs"], [".boot", ".assets", ".filesys"]
        )

    def test_auto_adopts_it(self) -> None:
        status, payload = self.run_json(["--blobs", "auto"])
        self.assertEqual(status, 0)
        self.assertEqual(payload["blobs"], [".boot", ".assets", ".filesys"])
        self.assertEqual(payload["blob_source"], "auto")

    def test_auto_and_the_explicit_flags_report_the_same_scan(self) -> None:
        _, auto = self.run_json(["--blobs", "auto"])
        _, explicit = self.run_json(
            ["--blob", ".boot", "--blob", ".assets", "--blob", ".filesys"]
        )
        for key in ("scan_total", "scan_high", "scan_medium", "scan_low"):
            with self.subTest(key=key):
                self.assertEqual(auto[key], explicit[key])

    def test_no_blob_subtracts_from_auto(self) -> None:
        status, payload = self.run_json(["--blobs", "auto", "--no-blob", ".boot"])
        self.assertEqual(status, 0)
        self.assertEqual(payload["blobs"], [".assets", ".filesys"])
        self.assertEqual(payload["blobs_excluded"], [".boot"])

    def test_naming_a_section_both_ways_is_a_usage_failure(self) -> None:
        status, _ = self.run_json(["--blob", ".assets", "--no-blob", ".assets"])
        self.assertEqual(status, 2)

    def test_a_no_blob_typo_is_refused(self) -> None:
        stderr = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            status = main(
                [
                    "shift",
                    "audit",
                    "--map",
                    str(self.map_path),
                    "--image",
                    str(self.image_path),
                    "--blobs",
                    "auto",
                    "--no-blob",
                    ".asset",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn(
            "--no-blob names a section this map does not have: .asset",
            stderr.getvalue(),
        )


class EmitWhitelistCommandTests(unittest.TestCase):
    """`--emit-whitelist`: a skeleton beside the report, never instead of it."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.map_path = self.root / "synthetic.map"
        self.image_path = self.root / "synthetic.z64"
        self.pins_path = self.root / "undefined_syms.txt"
        self.map_path.write_text(SYNTHETIC_MAP, encoding="utf-8")
        self.image_path.write_bytes(SYNTHETIC_IMAGE)
        self.pins_path.write_text(
            "SP_STATUS_REG = 0xA4040010;\nosTvType = 0x80000300;\n"
            "gameLoop = 0x80000420;\n",
            encoding="utf-8",
        )

    def run_cli(self, extra: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(
                [
                    "shift",
                    "audit",
                    "--map",
                    str(self.map_path),
                    "--image",
                    str(self.image_path),
                    "--blob",
                    ".boot",
                    "--pins",
                    str(self.pins_path),
                    *extra,
                ]
            )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_skeleton_is_written_and_the_run_continues(self) -> None:
        destination = self.root / "whitelist.txt"
        status, stdout, stderr = self.run_cli(["--emit-whitelist", str(destination)])
        self.assertEqual(status, 0)
        self.assertIn("shift audit", stdout)  # the report still printed
        self.assertIn("wrote whitelist skeleton", stderr)
        text = destination.read_text(encoding="utf-8")
        self.assertIn("# REVIEW: SP_STATUS_REG", text)
        self.assertIn("# REVIEW: osTvType", text)
        self.assertIn("movable window floor: 0x80000400 (.main)", text)

    def test_the_skeleton_declares_nothing_until_a_human_edits_it(self) -> None:
        destination = self.root / "whitelist.txt"
        self.run_cli(["--emit-whitelist", str(destination)])
        status, stdout, _ = self.run_cli(
            ["--whitelist", str(destination), "--json"]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        # Every drafted line is commented out, so the pins are classified
        # exactly as they were before the file existed.
        self.assertEqual(payload["pins_authentic"], 1)  # kseg1, by window
        self.assertEqual(payload["pins_artifact"], 2)

    def test_uncommenting_a_line_changes_the_next_run(self) -> None:
        destination = self.root / "whitelist.txt"
        self.run_cli(["--emit-whitelist", str(destination)])
        destination.write_text(
            destination.read_text(encoding="utf-8").replace(
                "# 0x80000300 ", "0x80000300 "
            ),
            encoding="utf-8",
        )
        status, stdout, _ = self.run_cli(["--whitelist", str(destination), "--json"])
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["pins_authentic"], 2)
        self.assertEqual(payload["pins_artifact"], 1)

    def test_an_existing_file_is_refused_rather_than_overwritten(self) -> None:
        destination = self.root / "whitelist.txt"
        destination.write_text("0x80000300 reviewed, by a person\n", encoding="utf-8")
        status, _, stderr = self.run_cli(["--emit-whitelist", str(destination)])
        self.assertEqual(status, 2)
        self.assertIn("refuses to overwrite", stderr)
        self.assertEqual(
            destination.read_text(encoding="utf-8"),
            "0x80000300 reviewed, by a person\n",
        )


# --------------------------------------------------------------------------
# DKR conformance -- skips when the sibling playground checkout is absent
# --------------------------------------------------------------------------

PLAYGROUND = Path(__file__).resolve().parents[2] / "decomp_playground"
S0_DIR = PLAYGROUND / ".workbench" / "shift-instrumentation" / "s0"
DKR_MAP = S0_DIR / "nm-base" / "dkr.us.v77.map"
DKR_IMAGE = S0_DIR / "nm-base" / "dkr.us.v77.z64"
DKR_PINS = PLAYGROUND / "diddy-kong-racing" / "ver" / "symbols" / "undefined_syms.txt"


def run_shift_cli(arguments: list[str]) -> tuple[int, str, str]:
    """`CommandTests.run_cli`, as a free function for the live test classes
    below (which are not `CommandTests` subclasses -- they skip as a group
    when the sibling checkout is absent)."""

    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


@unittest.skipUnless(
    DKR_MAP.is_file() and DKR_IMAGE.is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrAuditConformanceTests(unittest.TestCase):
    """S0's anchor cases, replayed through the classifier that replaced it.

    The tier totals below were measured on this exact image and are frozen
    here on purpose: they are the calibration this campaign stage claims, and
    a change in any rule has to be re-justified against the anchors rather
    than absorbed silently.

    The relationship to S0's own number is worth stating because it is not a
    discrepancy. S0 counted 1,501 *stale candidates*: words that held an
    in-window value and did **not** move across a real 0x10 shift. This audit
    has one image and cannot know what moved, so it counts every in-window
    word in the data/blob/header regions and gets 3,443. The two were
    reconciled directly against S0's shifted image: of its 1,501, exactly
    1,479 are in `.assets`, 14 in `.main`'s data run, 7 in `.boot`, 1 in
    `.header` -- and **zero** in text. So S0's whole stale set lies inside the
    regions this audit scans, and the 1,942-word difference is precisely the
    words a shift moves, which is `shift rehearse`'s question, not this
    command's.
    """

    audit: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = build_shift_audit(
            ldmap=read_ld_map(DKR_MAP),
            image=DKR_IMAGE.read_bytes(),
            pins=(
                read_pin_files(
                    [DKR_PINS],
                    model=default_pin_model(whitelist=(boot_globals_whitelist(),)),
                )
                if DKR_PINS.is_file()
                else PinCatalogue(entries=(), sources=())
            ),
            model=default_pin_model(whitelist=(boot_globals_whitelist(),)),
            blobs=(".assets", ".assets_lut", ".boot"),
            map_path=str(DKR_MAP),
            image_path=str(DKR_IMAGE),
        )

    def test_the_region_table_is_the_six_sections_of_the_cascade_script(self) -> None:
        self.assertEqual(
            [(item.output_section, item.kind) for item in self.audit.regions],
            [
                (".header", "header"),
                (".boot", "blob"),
                (".main", "text"),
                (".main", "data"),
                (".main_bss", "bss"),
                (".assets_lut", "blob"),
                (".assets", "blob"),
            ],
        )

    def test_the_movable_window_is_derived_from_the_map(self) -> None:
        window = self.audit.window
        self.assertEqual(window.lo, 0x80000400)
        self.assertEqual(window.hi, 0x80122610)
        self.assertEqual(window.lo_section, ".main")
        self.assertEqual(window.hi_section, ".main_bss")

    def test_the_text_coverage_line_counts_what_it_did_not_scan(self) -> None:
        self.assertEqual(self.audit.text_words, 213_560)
        self.assertEqual(self.audit.text_regions, 1)

    def test_the_measured_tier_totals(self) -> None:
        self.assertEqual(self.audit.scan_total, 3_443)
        self.assertEqual(self.audit.scan_high, 38)
        self.assertEqual(self.audit.scan_medium, 657)
        self.assertEqual(self.audit.scan_low, 2_748)
        self.assertEqual(
            self.audit.scan_high + self.audit.scan_medium + self.audit.scan_low,
            self.audit.scan_total,
        )

    def test_the_scan_totals_per_region_match_s0s_own_attribution(self) -> None:
        """`.assets` (1,479) and `.boot` (7) are S0's counts exactly: an
        opaque blob holds no relocated pointers, so every in-window word in
        one is a stale candidate and the two questions have one answer."""

        self.assertEqual(self.audit.scan_by_region[".assets"], 1_479)
        self.assertEqual(self.audit.scan_by_region[".boot"], 7)
        self.assertEqual(self.audit.scan_by_region[".main"], 1_955)
        self.assertEqual(self.audit.scan_by_region[".header"], 2)

    def test_the_track_select_cluster_is_demoted_whole(self) -> None:
        """S0's packed-shorts family: an arithmetic progression of packed
        fields at a constant stride, two of whose four members are also
        misaligned."""

        family = [
            hit
            for hit in self.audit.hits
            if hit.resident_symbol == "gTrackSelectBgData"
        ]
        self.assertEqual(
            [hit.value for hit in family],
            [0x80000800, 0x80001002, 0x80001804, 0x80002006],
        )
        self.assertEqual({hit.tier for hit in family}, {"low"})
        self.assertEqual(
            [hit.rule for hit in family],
            [
                "progression-cluster",
                "misaligned",
                "progression-cluster",
                "misaligned",
            ],
        )

    def test_the_sine_table_constant_is_demoted(self) -> None:
        hit = next(
            item
            for item in self.audit.hits
            if item.resident_symbol == "gSineTable" and item.resident_offset == 0x7FC
        )
        self.assertEqual(hit.value, 0x80008000)
        self.assertEqual(hit.rule, "round-constant")
        self.assertEqual(hit.tier, "low")

    def test_the_matched_garbage_in_the_asset_blob_is_demoted_by_alignment(
        self,
    ) -> None:
        """S0 labelled these `gAudioHeapStack+0x...` by reading asset ROM
        offsets through `.main`'s VRAM mapping. They are `.assets` bytes; the
        odd-valued ones cannot be pointers whatever they are called."""

        for value in (0x8007BA73, 0x8005D193):
            with self.subTest(value=value):
                hit = next(item for item in self.audit.hits if item.value == value)
                self.assertEqual(hit.region, ".assets")
                self.assertIsNone(hit.resident_symbol)
                self.assertEqual(hit.rule, "misaligned")
                self.assertEqual(hit.tier, "low")

    def test_the_symbol_start_hit_outranks_the_blob_noise(self) -> None:
        """The same value appears twice: once in compiled data and once in
        the asset blob. Both point at a symbol start, and both are ranked
        above the blob's own noise floor."""

        found = [item for item in self.audit.hits if item.value == 0x800D379C]
        self.assertEqual(len(found), 2)
        by_region = {item.region: item for item in found}
        self.assertEqual(by_region[".main"].tier, "high")
        self.assertEqual(by_region[".assets"].tier, "medium")
        for hit in found:
            self.assertTrue(hit.points_at_symbol_start)
            self.assertEqual(hit.target_symbol, "gContPakNoRoomForGhostsStrings")

    def test_the_high_tier_is_pointer_tables_not_noise(self) -> None:
        """Every high-tier hit points at a symbol start from compiled data.

        Measured against S0's real 0x10 shift: all 38 of them moved. The
        tiers rank how confidently a word is an address *reference*; whether
        a reference tracks a shift is the rehearsal's question.
        """

        highs = [item for item in self.audit.hits if item.tier == "high"]
        self.assertEqual(len(highs), 38)
        self.assertTrue(all(item.points_at_symbol_start for item in highs))
        self.assertTrue(all(item.residence in ("data", "header") for item in highs))
        self.assertIn(
            "gContPakNoRoomForGhostsStrings",
            {item.target_symbol for item in highs},
        )

    def test_the_pin_catalogue_travels_inside_the_audit(self) -> None:
        if not DKR_PINS.is_file():
            self.skipTest(f"DKR pin file not found at {DKR_PINS}")
        payload = self.audit.as_dict(limit=5)
        self.assertEqual(payload["pins_total"], 66)
        self.assertEqual(payload["pins_artifact"], 2)
        self.assertEqual(payload["pins_derived"], 7)
        self.assertEqual(payload["pins_authentic"], 57)

    def test_s7_the_map_suggests_exactly_the_blobs_this_campaign_names(
        self,
    ) -> None:
        """Every `--blob` DKR has ever been audited with, derived from the
        map alone: `build/assets/{boot,assets.lut,assets}.bin.o` are the only
        objects in the whole link that are raw binaries."""

        plan = self.audit.blobs
        self.assertEqual(plan.suggested, (".boot", ".assets_lut", ".assets"))
        self.assertEqual(
            {item.rule for item in plan.suggestions}, {"bin-object-suffix"}
        )
        self.assertEqual(plan.unadopted, ())

    def test_s7_adopting_the_suggestion_reproduces_this_scorecard(self) -> None:
        """`--blobs auto` is the same run as the three explicit flags above,
        number for number -- the frozen DKR scorecard either way."""

        auto = build_shift_audit(
            ldmap=read_ld_map(DKR_MAP),
            image=DKR_IMAGE.read_bytes(),
            pins=PinCatalogue(entries=(), sources=()),
            model=default_pin_model(whitelist=(boot_globals_whitelist(),)),
            auto_blobs=True,
            map_path=str(DKR_MAP),
            image_path=str(DKR_IMAGE),
        )
        self.assertEqual(sorted(auto.blobs.applied), sorted(self.audit.blobs.applied))
        self.assertEqual(auto.blobs.source, "auto")
        self.assertEqual(auto.scan_total, self.audit.scan_total)
        self.assertEqual(auto.scan_high, self.audit.scan_high)
        self.assertEqual(auto.scan_medium, self.audit.scan_medium)
        self.assertEqual(auto.scan_low, self.audit.scan_low)
        self.assertEqual(auto.window.as_dict(), self.audit.window.as_dict())

    def test_s7_no_dkr_pin_reclassifies_as_a_rom_offset(self) -> None:
        """The measured control for the new class. DKR already derives its
        ROM offsets from the linker (`boot_ROM_START = __romPos` and kin are
        map symbols, not pins), so its pin file holds no raw offset at all --
        the 66/7/57/2 scorecard is unchanged, and the class costs it nothing.
        """

        self.assertEqual(self.audit.pins.counts[ROM_OFFSET], 0)
        self.assertEqual(self.audit.pins.counts[UNCLASSIFIED], 0)

    def test_s7_the_window_is_unchanged_by_the_floor_rule(self) -> None:
        """DKR's lowest movable region was already RAM-resident (`.main` at
        0x80000400); the floor rule cannot move a window that never had a
        ROM-space section competing for it."""

        self.assertEqual(self.audit.window.lo, 0x80000400)
        self.assertEqual(self.audit.window.lo_section, ".main")

    def test_wb_140_the_correct_pair_passes_the_new_consistency_check(self) -> None:
        """WB-140 rule B is always on, including here -- the correct
        ``nm-base`` map+image pair every other test in this class already
        exercises. The map's placed extent matches the image exactly."""

        found = self.audit.consistency
        self.assertEqual(found.max_placed_extent, self.audit.image_bytes)
        self.assertEqual(found.padding_bytes, 0)
        self.assertEqual(found.regions_unplaced_past_eof, 0)


@unittest.skipUnless(
    DKR_MAP.is_file() and DKR_IMAGE.is_file() and DKR_PINS.is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrCommandConformanceTest(unittest.TestCase):
    """The whole command, on the real inputs, through argparse."""

    def test_the_command_reports_the_measured_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            whitelist = Path(temp) / "whitelist.txt"
            whitelist.write_text(
                "0x80000300-0x80000400 N64 boot globals and the fixed entrypoint\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "shift",
                        "audit",
                        "--map",
                        str(DKR_MAP),
                        "--image",
                        str(DKR_IMAGE),
                        "--pins",
                        str(DKR_PINS),
                        "--whitelist",
                        str(whitelist),
                        "--blob",
                        ".assets",
                        "--blob",
                        ".assets_lut",
                        "--blob",
                        ".boot",
                        "--json",
                    ]
                )
        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], "decomp-workbench-shift-audit-v1")
        self.assertEqual(payload["pins_total"], 66)
        self.assertEqual(payload["pins_artifact"], 2)
        self.assertEqual(payload["scan_total"], 3_443)
        self.assertEqual(payload["scan_high"], 38)
        self.assertEqual(payload["scan_medium"], 657)
        self.assertEqual(payload["scan_low"], 2_748)
        self.assertEqual(payload["text_words"], 213_560)
        self.assertEqual(payload["padding_bytes"], 0)
        self.assertEqual(payload["regions_unplaced_past_eof"], 0)


# --------------------------------------------------------------------------
# WB-140 live repros against the S0 artifacts -- self-skip when absent.
# --------------------------------------------------------------------------

#: QA's exact B repro: the un-shifted `nm-base` map against the real,
#: correctly-linked 0x10 relink of the same project. Not a corrupt pair --
#: exactly the mistake a caller sweeping a project's own rehearsal
#: artifacts would make.
DKR_SHIFT10_IMAGE = S0_DIR / "shift-0x10" / "dkr.us.v77.z64"

#: The retail, byte-exact matching build: a *different* map (the real
#: matching linker script, not the NM cascade script) padded to the
#: cartridge's rounded size with 0xFF -- the live case for "an image longer
#: than the map's placed extent is sometimes benign padding."
DKR_MATCHING_MAP = S0_DIR / "matching" / "dkr.us.v77.map"
DKR_MATCHING_IMAGE = S0_DIR / "matching" / "dkr.us.v77.z64"

DKR_BLOBS = (".assets", ".assets_lut", ".boot")


@unittest.skipUnless(
    DKR_MAP.is_file() and DKR_SHIFT10_IMAGE.is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrMapImageMismatchLiveTests(unittest.TestCase):
    """WB-140 rule B's live anchor: the exact QA repro. Measured directly:
    the ``nm-base`` map's placed extent is 11,263,248 bytes, the
    ``shift-0x10`` image is 11,263,264 -- a 16-byte, non-uniform excess
    (the tail of a real relink, not padding), and this is the shape that
    used to produce a full exit-0 report with ``scan_total`` ballooned from
    3,443 to 1,323,680."""

    def test_the_mismatched_pair_is_refused_not_silently_scanned(self) -> None:
        with self.assertRaises(ValueError) as raised:
            build_shift_audit(
                ldmap=read_ld_map(DKR_MAP),
                image=DKR_SHIFT10_IMAGE.read_bytes(),
                pins=PinCatalogue(entries=(), sources=()),
                model=default_pin_model(),
                blobs=DKR_BLOBS,
                map_path=str(DKR_MAP),
                image_path=str(DKR_SHIFT10_IMAGE),
            )
        message = str(raised.exception)
        self.assertIn("image extends 16 bytes past the map's placed extent", message)
        self.assertIn("not uniform padding", message)
        self.assertIn("different builds", message)
        self.assertIn("image_bytes=11,263,264", message)
        self.assertIn("map_placed_extent=11,263,248", message)

    def test_the_command_refuses_it_too(self) -> None:
        status, _, stderr = run_shift_cli(
            [
                "shift",
                "audit",
                "--map",
                str(DKR_MAP),
                "--image",
                str(DKR_SHIFT10_IMAGE),
                *[argument for name in DKR_BLOBS for argument in ("--blob", name)],
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn("not uniform padding", stderr)
        self.assertIn("different builds", stderr)


@unittest.skipUnless(
    DKR_IMAGE.is_file(), f"S0 shift-instrumentation artifacts not found under {S0_DIR}"
)
class DkrZ64AsMapLiveTests(unittest.TestCase):
    """WB-140 rule A's live anchor: QA's actual repro, a real `.z64` passed
    as `--map`."""

    def test_a_real_rom_image_as_the_map_is_refused_with_the_swap_hint(self) -> None:
        status, _, stderr = run_shift_cli(
            [
                "shift",
                "audit",
                "--map",
                str(DKR_IMAGE),
                "--image",
                str(DKR_IMAGE),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn(str(DKR_IMAGE), stderr)
        self.assertIn("parsed as no linker map", stderr)
        self.assertIn("--map and --image may be swapped", stderr)


@unittest.skipUnless(
    DKR_MATCHING_MAP.is_file() and DKR_MATCHING_IMAGE.is_file(),
    f"S0 shift-instrumentation artifacts not found under {S0_DIR}",
)
class DkrRetailPaddingLiveTests(unittest.TestCase):
    """WB-140 rule B's benign branch, measured on a real cart: DKR's
    retail-matching image is padded past its own map's placed extent with
    1,272,272 bytes of 0xFF -- accepted, reported, and does not disturb the
    exit-0 report."""

    def test_the_retail_pad_is_accepted_and_reported(self) -> None:
        audit = build_shift_audit(
            ldmap=read_ld_map(DKR_MATCHING_MAP),
            image=DKR_MATCHING_IMAGE.read_bytes(),
            pins=PinCatalogue(entries=(), sources=()),
            model=default_pin_model(),
            blobs=DKR_BLOBS,
            map_path=str(DKR_MATCHING_MAP),
            image_path=str(DKR_MATCHING_IMAGE),
        )
        self.assertEqual(audit.consistency.padding_bytes, 1_272_272)
        self.assertEqual(audit.consistency.regions_unplaced_past_eof, 0)


# --------------------------------------------------------------------------
# Banjo-Kazooie conformance (S5's first real-patient `shift audit` run,
# WB-138 and WB-139) -- skips gracefully when the sibling decomp_playground
# checkout is absent.
# --------------------------------------------------------------------------

BK_ROOT = PLAYGROUND / "banjo-kazooie" / "build" / "us.v10"
BK_MAP = BK_ROOT / "banjo.us.v10.map"
#: The *uncompressed* linked image, not the 16 MiB retail `.z64` alongside
#: it. BK compresses each segment via a post-link build step; the map's
#: `AT()` load addresses describe positions in this larger, pre-compression
#: layout (~16.74 MiB), and any overlay or `.core2` placement past 16 MiB
#: reads as out-of-bounds against the retail image -- honestly reported
#: `unplaced`, which is what the original bad `shift audit` run (WB-139)
#: actually measured. Confirming the fix means reading the image the map
#: really describes.
BK_IMAGE = BK_ROOT / "banjo.us.v10.uncompressed.z64"

_HAVE_BK = BK_MAP.is_file() and BK_IMAGE.is_file()

#: All fourteen of BK's overlay output sections. Every one starts at VMA
#: ``0x803863f0``, each with its own distinct `AT()` load address.
BK_OVERLAY_SECTIONS = (
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
)


@unittest.skipUnless(
    _HAVE_BK, f"Banjo-Kazooie build artifacts not found under {BK_ROOT}"
)
class BkAuditConformanceTests(unittest.TestCase):
    """S5's real-patient run, replayed. Confirms both filed defects against
    the actual project rather than only a synthetic fixture.

    WB-138: the bad run scanned ``.mdebug`` (vram 0x0, 3,048,492 bytes /
    762,123 words) as a ``data`` region at ``rom_source=vma-as-rom``, and the
    movable window's low bound followed it to VMA 0. WB-139: the bad run
    reported every overlay region and ``.core2``'s ``data`` subregion
    ``rom_source=unplaced``. The filed hypothesis was address-lookup
    ambiguity across the fourteen overlay sections sharing one VMA; this
    module's own `build_region_table` was already positional and needed no
    change (see `OverlaySiblingRegionTests` and the module docstring) -- the
    real cause was that the bad run read the compressed 16 MiB retail image
    against a map whose `AT()` addresses describe the larger, uncompressed
    linked layout.
    """

    audit: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = build_shift_audit(
            ldmap=read_ld_map(BK_MAP),
            image=BK_IMAGE.read_bytes(),
            pins=PinCatalogue(entries=(), sources=()),
            model=default_pin_model(),
            map_path=str(BK_MAP),
            image_path=str(BK_IMAGE),
        )

    def test_mdebug_is_excluded_from_scanning_and_the_window(self) -> None:
        mdebug = next(
            item for item in self.audit.regions if item.output_section == ".mdebug"
        )
        self.assertEqual(mdebug.kind, "non-alloc")
        self.assertFalse(mdebug.scanned)
        self.assertIsNone(mdebug.rom)
        self.assertNotEqual(self.audit.window.lo_section, ".mdebug")

    def test_the_window_starts_at_the_true_first_movable_section(self) -> None:
        """`.entry`, BK's real entrypoint, is the lowest VMA of any
        `text`/`data`/`bss` region once `.mdebug`'s bogus VMA-0 `data`
        region no longer competes for the window's low bound."""

        window = self.audit.window
        self.assertEqual(window.lo, 0x80000400)
        self.assertEqual(window.lo_section, ".entry")

    def test_the_region_count(self) -> None:
        self.assertEqual(len(self.audit.regions), 62)

    def test_the_scanned_word_count(self) -> None:
        self.assertEqual(self.audit.scanned_words, 3_994_336)

    def test_every_overlay_region_resolves_through_its_own_load_address(self) -> None:
        overlay_regions = [
            item
            for item in self.audit.regions
            if item.output_section in BK_OVERLAY_SECTIONS
        ]
        # Every overlay section tiles into exactly one `text` run and one
        # `data` run.
        self.assertEqual(len(overlay_regions), 2 * len(BK_OVERLAY_SECTIONS))
        for item in overlay_regions:
            with self.subTest(section=item.output_section, kind=item.kind):
                self.assertEqual(item.rom_source, "load-address")
                self.assertIsNotNone(item.rom)

    def test_cc_text_resolves_to_its_known_rom_offset(self) -> None:
        """Spot check: `.CC`'s map header line prints
        ``load address 0x01048560``, and this is that value, unmodified."""

        cc_text = next(
            item
            for item in self.audit.regions
            if item.output_section == ".CC" and item.kind == "text"
        )
        self.assertEqual(cc_text.rom, 0x01048560)

    def test_core2_data_is_placed(self) -> None:
        core2_data = next(
            item
            for item in self.audit.regions
            if item.output_section == ".core2" and item.kind == "data"
        )
        self.assertEqual(core2_data.rom_source, "load-address")
        self.assertIsNotNone(core2_data.rom)

    def test_wb_140_the_uncompressed_image_passes_the_new_consistency_check(
        self,
    ) -> None:
        """`setUpClass` itself already proves this (rule B is always on and
        would have raised there), but the numbers are asserted explicitly:
        BK's uncompressed image matches its map's placed extent exactly,
        with no overlay landing past the end of it."""

        found = self.audit.consistency
        self.assertEqual(found.max_placed_extent, self.audit.image_bytes)
        self.assertEqual(found.padding_bytes, 0)
        self.assertEqual(found.regions_unplaced_past_eof, 0)


# --------------------------------------------------------------------------
# S7: the two community patients' full scorecards, with pins.
# --------------------------------------------------------------------------

#: Banjo-Kazooie's four linker-input symbol files, at the repository root.
BK_PROJECT = PLAYGROUND / "banjo-kazooie"
BK_PIN_FILES = (
    BK_PROJECT / "symbol_addrs.us.v10.txt",
    BK_PROJECT / "manual_syms.us.v10.txt",
    BK_PROJECT / "rzip_dummy_addrs.us.v10.txt",
    BK_PROJECT / "level_symbols.us.v10.txt",
)

#: The blob set S5's scorecard run named by hand -- and, as of S7, exactly
#: what `--blobs auto` derives from the map.
BK_BLOBS = (
    ".crc",
    ".assets",
    ".soundfont1ctl",
    ".soundfont1tbl",
    ".soundfont2ctl",
    ".soundfont2tbl",
    ".boot",
)

_HAVE_BK_PINS = _HAVE_BK and all(item.is_file() for item in BK_PIN_FILES)


@unittest.skipUnless(
    _HAVE_BK_PINS, f"Banjo-Kazooie pin files not found under {BK_PROJECT}"
)
class BkScorecardConformanceTests(unittest.TestCase):
    """S5's banjo-kazooie scorecard, re-measured through S7's classifier.

    S5 filed one gap against this exact run: 37 pins came back
    ``unclassified``, and the note said what they were -- "small-value
    ROM-offset pins from `rzip_dummy_addrs` and the asset table -- a
    pin-classifier window the tool should grow: raw ROM offsets are their own
    class". This class is that gap closed, with the number it moved.
    """

    audit: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        model = default_pin_model()
        cls.audit = build_shift_audit(
            ldmap=read_ld_map(BK_MAP),
            image=BK_IMAGE.read_bytes(),
            pins=read_pin_files(BK_PIN_FILES, model=model),
            model=model,
            blobs=BK_BLOBS,
            map_path=str(BK_MAP),
            image_path=str(BK_IMAGE),
        )

    def test_the_37_unclassified_pins_are_rom_offsets(self) -> None:
        """S5 measured ``pins_unclassified=37``; this measures
        ``pins_rom_offset=37`` and ``pins_unclassified=0``, and the new
        number is the more truthful one for a reason the pins themselves
        make: 32 of them come from `rzip_dummy_addrs.us.v10.txt`, whose every
        line is spelled ``*_rzip_ROM_START``/``_ROM_END``, and the other 5
        are ``D_5E90``, ``D_D846C0``, ``D_D954B0``, ``D_EA3EB0`` and
        ``D_EADE60`` -- which are, byte for byte, the ``AT()`` load addresses
        this same map prints for ``.assets``, ``.soundfont1ctl``,
        ``.soundfont1tbl``, ``.soundfont2ctl`` and ``.soundfont2tbl``. Every
        one is a cartridge offset. "Unclassified" said only that this model
        had no window for them; it is not a window they were missing, it is
        a class they were.
        """

        counts = self.audit.pins.counts
        self.assertEqual(counts[ROM_OFFSET], 37)
        self.assertEqual(counts[UNCLASSIFIED], 0)

    def test_the_other_pin_classes_are_untouched(self) -> None:
        """S5's 127/6/0/84 stands: only the unclassified column moved."""

        counts = self.audit.pins.counts
        self.assertEqual(len(self.audit.pins.entries), 127)
        self.assertEqual(counts[DERIVED], 6)
        self.assertEqual(counts[AUTHENTIC_FIXED], 0)
        self.assertEqual(counts[ARTIFACT_SUSPECT], 84)
        self.assertEqual(sum(counts.values()), 127)

    def test_the_rom_offset_pins_name_their_own_remediation(self) -> None:
        offsets = self.audit.pins.by_classification(ROM_OFFSET)
        rzip = next(
            item for item in offsets if item.name == "boot_core1_rzip_ROM_START"
        )
        self.assertEqual(rzip.value, 0xF19250)
        assert rzip.reason is not None
        self.assertIn("_ROM_START", rzip.reason)
        table = next(item for item in offsets if item.name == "D_5E90")
        self.assertEqual(table.value, 0x5E90)
        assets = next(
            item for item in self.audit.regions if item.output_section == ".assets"
        )
        self.assertEqual(table.value, assets.rom)

    def test_the_report_prints_the_new_class_and_its_reading(self) -> None:
        text = "\n".join(shift_audit_lines(self.audit, limit=5))
        self.assertIn("pins_rom_offset=37", text)
        self.assertIn("rom-offset pins (5 of 37, --limit)", text)
        self.assertIn("_ROM_START/_ROM_END", text)

    def test_the_map_suggests_exactly_the_blob_set_this_scorecard_used(self) -> None:
        """S5 named seven sections by hand after reading the project's splat
        configuration. The map's own input records say the same seven."""

        self.assertEqual(sorted(self.audit.blobs.suggested), sorted(BK_BLOBS))
        self.assertEqual(
            {item.rule for item in self.audit.blobs.suggestions},
            {"bin-object-suffix"},
        )

    def test_core2_is_not_suggested_despite_holding_bin_objects(self) -> None:
        """`.core2` mixes three `.bin.o` data blobs in with 395 compiled
        objects. One compiled input is enough to keep a section attributable."""

        self.assertNotIn(
            ".core2", [item.output_section for item in self.audit.blobs.suggestions]
        )

    def test_adopting_the_suggestion_reproduces_this_scorecard(self) -> None:
        model = default_pin_model()
        auto = build_shift_audit(
            ldmap=read_ld_map(BK_MAP),
            image=BK_IMAGE.read_bytes(),
            pins=read_pin_files(BK_PIN_FILES, model=model),
            model=model,
            auto_blobs=True,
            map_path=str(BK_MAP),
            image_path=str(BK_IMAGE),
        )
        self.assertEqual(auto.blobs.source, "auto")
        self.assertEqual(auto.as_dict(limit=5), self.audit.as_dict(limit=5) | {
            "blobs": list(auto.blobs.applied),
            "blob_source": "auto",
        })

    def test_the_scan_totals_are_s5s_own(self) -> None:
        """Unchanged by all four S7 features: bk's window floor was already
        RAM-resident (`.entry` at 0x80000400), so nothing about the scan
        moved."""

        self.assertEqual(self.audit.scan_total, 11_066)
        self.assertEqual(self.audit.scan_high, 1_581)
        self.assertEqual(self.audit.scan_medium, 1_427)
        self.assertEqual(self.audit.scan_low, 8_058)
        self.assertEqual(self.audit.window.lo, 0x80000400)
        self.assertEqual(self.audit.window.lo_section, ".entry")

    def test_the_whitelist_skeleton_finds_the_one_boot_global(self) -> None:
        """bk pins exactly one address below its own window floor:
        ``osRomBase = 0x80000308``, one of the libultra boot globals the boot
        ROM writes. It is drafted, commented out, and reviewable."""

        text = self.audit.whitelist_template()
        self.assertIn("# REVIEW: osRomBase", text)
        self.assertIn("# 0x80000308 osRomBase:", text)
        self.assertIn("below-window-floor (1)", text)
        self.assertIn("hardware-window (0)", text)


# --------------------------------------------------------------------------
# pilotwings64 conformance -- S5's greenfield patient, and the window fix
# it found. Skips gracefully when the sibling checkout is absent.
# --------------------------------------------------------------------------

PW64_ROOT = PLAYGROUND / "pilotwings64"
PW64_MAP = PW64_ROOT / "build" / "pilotwings64.us.map"
PW64_IMAGE = PW64_ROOT / "build" / "pilotwings64.us.z64"
PW64_SYM = PW64_ROOT / "config" / "us" / "sym"
PW64_PIN_FILES = (
    PW64_SYM / "libultra_undefined_syms.txt",
    PW64_SYM / "hardware_regs.ld",
    PW64_SYM / "pif_syms.ld",
    PW64_SYM / "symbol_addrs_app.txt",
    PW64_SYM / "symbol_addrs_kernel.txt",
    PW64_SYM / "symbol_addrs_libultra.txt",
)

#: The five sections S5's scorecard run named `--blob` by hand.
PW64_BLOBS = (".filetable", ".filesys", ".audio_seq", ".audio_ctl", ".audio_tbl")

_HAVE_PW64 = (
    PW64_MAP.is_file()
    and PW64_IMAGE.is_file()
    and all(item.is_file() for item in PW64_PIN_FILES)
)


@unittest.skipUnless(
    _HAVE_PW64, f"pilotwings64 build artifacts not found under {PW64_ROOT}"
)
class Pw64AuditConformanceTests(unittest.TestCase):
    """S5's pilotwings64 scorecard, and the window defect it filed.

    S5's caveat read: "pw64's movable window floor sits at `.ipl3` (vma 0x40)
    -- harmless for stale detection, noted for window-derivation refinement".
    It was not harmless. `.ipl3` is a raw binary placed at its ROM offset, and
    a window starting at `0x00000040` counts every small integer in an 8 MB
    image as an in-window hit: S5 measured `scan_total=977,512`, of which
    975,000-odd were a "low-tier noise floor" from the filesystem blob. The
    floor rule (`movable_window`) is that defect fixed, and the number it
    moves is the headline of this class.
    """

    audit: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        model = default_pin_model()
        cls.audit = build_shift_audit(
            ldmap=read_ld_map(PW64_MAP),
            image=PW64_IMAGE.read_bytes(),
            pins=read_pin_files(PW64_PIN_FILES, model=model),
            model=model,
            blobs=PW64_BLOBS,
            map_path=str(PW64_MAP),
            image_path=str(PW64_IMAGE),
        )

    def test_the_window_floor_is_the_first_ram_resident_section(self) -> None:
        """S5 measured ``window_lo=0x00000040 window_lo_section=.ipl3``; this
        measures ``0x80200050`` / ``.entry``, and the new number is the more
        truthful one because it is the first address an insertion could
        actually move. `.ipl3` is a boot block: the map places it at ROM
        offset 0x40 with no ``AT()`` because it has no run-time address at
        all, and a window that starts there claims two gigabytes of address
        space the layout does not own. ``0x80200050`` is `.entry`'s VMA in
        this same map -- pilotwings64 links at 0x80200000, not 0x80000000.
        """

        self.assertEqual(self.audit.window.lo, 0x80200050)
        self.assertEqual(self.audit.window.lo_section, ".entry")
        self.assertEqual(self.audit.window.hi, 0x803805E0)
        self.assertEqual(self.audit.window.hi_section, ".app_bss")

    def test_the_scan_no_longer_counts_the_whole_low_address_space(self) -> None:
        """S5's ``scan_total=977,512 / scan_high=62`` becomes ``2,548 / 62``.
        The 974,964 words that left were never candidates: they held values
        below ``0x80200050``, which no insertion in this layout moves. The
        `high` tier is unchanged to the word, which is the check that the
        fix narrowed the window rather than the evidence.
        """

        self.assertEqual(self.audit.scan_total, 2_548)
        self.assertEqual(self.audit.scan_high, 62)
        self.assertEqual(self.audit.scan_medium, 681)
        self.assertEqual(self.audit.scan_low, 1_805)
        self.assertEqual(
            self.audit.scan_high + self.audit.scan_medium + self.audit.scan_low,
            self.audit.scan_total,
        )

    def test_the_region_table_is_unchanged(self) -> None:
        """The floor rule changes the window, never the regions: `.ipl3` is
        still a placed, scanned `data` region reported exactly as before."""

        self.assertEqual(len(self.audit.regions), 16)
        self.assertEqual(self.audit.scanned_words, 1_887_600)
        self.assertEqual(self.audit.text_words, 209_552)
        self.assertEqual(self.audit.text_regions, 3)
        ipl3 = next(
            item for item in self.audit.regions if item.output_section == ".ipl3"
        )
        self.assertEqual(
            (ipl3.kind, ipl3.vram, ipl3.rom_source), ("data", 0x40, "vma-as-rom")
        )

    def test_the_pin_scorecard_is_s5s_own(self) -> None:
        """1,825 / 0 derived / 1,724 artifact-suspect, and no ROM offsets:
        pw64 writes its pins as kseg0 code addresses, not as cartridge
        offsets, so the new class costs it nothing either."""

        counts = self.audit.pins.counts
        self.assertEqual(len(self.audit.pins.entries), 1_825)
        self.assertEqual(counts[DERIVED], 0)
        self.assertEqual(counts[AUTHENTIC_FIXED], 101)
        self.assertEqual(counts[ARTIFACT_SUSPECT], 1_724)
        self.assertEqual(counts[ROM_OFFSET], 0)
        self.assertEqual(counts[UNCLASSIFIED], 0)

    def test_the_map_suggests_six_sections_where_s5_named_five(self) -> None:
        """The sixth is `.ipl3` -- ``build/bin/ipl3.o``, the same objcopy'd
        raw binary as the other five and the same shape as banjo-kazooie's
        `.boot` (``ipl3.bin.o``), which S5 *did* name a blob. S5's five were
        the asset segments; nothing distinguishes `.ipl3` from them in the
        map, so the derivation names it too rather than special-casing a
        section by what it is called.
        """

        self.assertEqual(
            self.audit.blobs.suggested,
            (".ipl3", *PW64_BLOBS),
        )
        self.assertEqual(
            {item.rule for item in self.audit.blobs.suggestions}, {"bin-directory"}
        )

    def test_adopting_all_six_reproduces_this_scorecard_anyway(self) -> None:
        """Measured, not assumed: `.ipl3` holds no word whose value lands in
        the (now correct) movable window, so treating it as opaque changes
        nothing but the label on its region. `--blobs auto` and S5's five
        explicit flags are the same run."""

        model = default_pin_model()
        auto = build_shift_audit(
            ldmap=read_ld_map(PW64_MAP),
            image=PW64_IMAGE.read_bytes(),
            pins=read_pin_files(PW64_PIN_FILES, model=model),
            model=model,
            auto_blobs=True,
            map_path=str(PW64_MAP),
            image_path=str(PW64_IMAGE),
        )
        self.assertEqual(auto.scan_total, self.audit.scan_total)
        self.assertEqual(auto.scan_high, self.audit.scan_high)
        self.assertEqual(auto.scan_medium, self.audit.scan_medium)
        self.assertEqual(auto.scan_low, self.audit.scan_low)
        self.assertEqual(auto.window.as_dict(), self.audit.window.as_dict())
        self.assertEqual(auto.scanned_words, self.audit.scanned_words)

    def test_no_blob_brings_auto_back_to_s5s_five(self) -> None:
        """The exclusion affordance, on the case that motivated it."""

        model = default_pin_model()
        trimmed = build_shift_audit(
            ldmap=read_ld_map(PW64_MAP),
            image=PW64_IMAGE.read_bytes(),
            pins=PinCatalogue(entries=(), sources=()),
            model=model,
            auto_blobs=True,
            excluded_blobs=(".ipl3",),
            map_path=str(PW64_MAP),
            image_path=str(PW64_IMAGE),
        )
        self.assertEqual(trimmed.blobs.applied, PW64_BLOBS)
        self.assertEqual(trimmed.blobs.unadopted, (".ipl3",))

    def test_the_whitelist_skeleton_drafts_the_greenfield_boot_globals(
        self,
    ) -> None:
        """pw64's ``pif_syms.ld`` pins ``leoBootID`` and the eight libultra
        boot globals below its window floor, and ``hardware_regs.ld`` pins
        101 memory-mapped registers. All 110 are drafted, none are asserted.
        """

        text = self.audit.whitelist_template()
        self.assertIn("hardware-window (101)", text)
        self.assertIn("below-window-floor (9)", text)
        self.assertIn("# REVIEW: osTvType", text)
        self.assertIn("movable window floor: 0x80200050 (.entry)", text)
        self.assertEqual(parse_whitelist_text(text), ())


# --------------------------------------------------------------------------
# WB-143b: `--elf`, the class only the linked ELF can name
# --------------------------------------------------------------------------

PW64_ELF = (
    PLAYGROUND
    / ".workbench"
    / "shift-instrumentation"
    / "s6"
    / "scratch"
    / "base-symbolic.elf"
)
PW64_SYMBOLIC_MAP = (
    PLAYGROUND
    / ".workbench"
    / "shift-instrumentation"
    / "s6"
    / "artifacts"
    / "base-symbolic.map"
)
PW64_SYMBOLIC_IMAGE = PW64_SYMBOLIC_MAP.with_suffix(".z64")
PW64_AUTO_SYMS = (
    PW64_ROOT / "build" / "splat_out" / "us" / "undefined_syms_auto.txt"
)

_HAVE_PW64_S6_AUDIT = (
    PW64_ELF.is_file()
    and PW64_SYMBOLIC_MAP.is_file()
    and PW64_SYMBOLIC_IMAGE.is_file()
    and PW64_AUTO_SYMS.is_file()
)

#: S6 4.4(a). Ablation B deleted exactly these ten and rebuilt to the same
#: sha1, which is what makes "deleting is free" a measurement rather than an
#: argument.
PW64_ABLATED_TEN = (
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


@unittest.skipUnless(
    _HAVE_PW64_S6_AUDIT, f"S6 pilotwings64 artifacts not found near {PW64_ELF}"
)
class Pw64ShadowingPinConformanceTests(unittest.TestCase):
    """The static half of WB-143, against the ten S6 found the hard way.

    S6 identified these by relinking twice, diffing `nm -n` over both ELFs,
    counting relocations with `readelf -r` across 307 objects, and rebuilding
    twice more to prove the deletions were free. Every one of them is in the
    shipped link's own symbol table, so `shift audit --elf` finds the same ten
    from one build, no shift, and about a second of work.
    """

    audit: ClassVar[ShiftAudit]
    without_elf: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        model = default_pin_model()
        image = PW64_SYMBOLIC_IMAGE.read_bytes()
        ldmap = read_ld_map(PW64_SYMBOLIC_MAP)
        pins = read_pin_files((PW64_AUTO_SYMS,), model=model)
        cls.without_elf = build_shift_audit(
            ldmap=ldmap,
            image=image,
            pins=pins,
            model=model,
            blobs=PW64_BLOBS,
            map_path=str(PW64_SYMBOLIC_MAP),
            image_path=str(PW64_SYMBOLIC_IMAGE),
        )
        cls.audit = build_shift_audit(
            ldmap=ldmap,
            image=image,
            pins=pins,
            model=model,
            blobs=PW64_BLOBS,
            elf=read_elf_symbols(PW64_ELF),
            map_path=str(PW64_SYMBOLIC_MAP),
            image_path=str(PW64_SYMBOLIC_IMAGE),
            elf_path=str(PW64_ELF),
        )

    def test_the_pin_file_is_the_37_lines_s6_enumerated(self) -> None:
        self.assertEqual(len(self.audit.pins.entries), 37)

    def test_exactly_the_ten_ablated_pins_are_flagged(self) -> None:
        """Ten of ten, and no twenty-eighth: `D_803805E0` is the trap, since
        its `extern` declaration gives it an `object` type with no size."""

        found = self.audit.pins.by_classification(SHADOWING_PIN)
        self.assertEqual(sorted(item.name for item in found), sorted(PW64_ABLATED_TEN))
        self.assertEqual(self.audit.pins.counts[SHADOWING_PIN], 10)

    def test_d_803571f0_is_among_them(self) -> None:
        """The one word S6's rehearsal convicted, found with no shift."""

        pin = next(
            item
            for item in self.audit.pins.by_classification(SHADOWING_PIN)
            if item.name == "D_803571F0"
        )
        self.assertEqual(pin.value, 0x803571F0)
        assert pin.reason is not None
        self.assertIn("already defines", pin.reason)

    def test_without_the_elf_all_ten_hide_among_the_artifact_suspects(self) -> None:
        """What the map alone can say about them: they are kseg0 constants.
        True, and strictly weaker than "an object already defines this"."""

        self.assertEqual(self.without_elf.pins.counts[SHADOWING_PIN], 0)
        self.assertIsNone(self.without_elf.elf_path)
        suspects = {
            item.name
            for item in self.without_elf.pins.by_classification(ARTIFACT_SUSPECT)
        }
        self.assertTrue(set(PW64_ABLATED_TEN) <= suspects)

    def test_the_ten_move_out_of_the_artifact_column_and_nothing_else_does(
        self,
    ) -> None:
        before = self.without_elf.pins.counts
        after = self.audit.pins.counts
        self.assertEqual(after[ARTIFACT_SUSPECT], before[ARTIFACT_SUSPECT] - 10)
        for name in (DERIVED, AUTHENTIC_FIXED, ROM_OFFSET, UNCLASSIFIED):
            with self.subTest(classification=name):
                self.assertEqual(after[name], before[name])

    def test_the_report_prints_the_class_and_its_remediation(self) -> None:
        text = "\n".join(shift_audit_lines(self.audit, limit=10))
        self.assertIn("pins_shadowing=10", text)
        self.assertIn("shadowing pins (10 of 10, --limit)", text)
        self.assertIn("byte-identical at this layout", text)

    def test_without_an_elf_the_report_says_off_rather_than_zero(self) -> None:
        text = "\n".join(shift_audit_lines(self.without_elf, limit=10))
        self.assertIn("pins_shadowing=off", text)
        self.assertIn("--elf", text)

    def test_the_command_runs_it_end_to_end(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(
                [
                    "shift",
                    "audit",
                    "--map",
                    str(PW64_SYMBOLIC_MAP),
                    "--image",
                    str(PW64_SYMBOLIC_IMAGE),
                    "--elf",
                    str(PW64_ELF),
                    "--pins",
                    str(PW64_AUTO_SYMS),
                    *[item for blob in PW64_BLOBS for item in ("--blob", blob)],
                    "--json",
                    "--census",
                    "pins_shadowing=10",
                ]
            )
        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["pins_shadowing"], 10)
        self.assertEqual(payload["elf"], str(PW64_ELF))


BK_ELF = BK_ROOT / "banjo.us.v10.elf"


@unittest.skipUnless(
    _HAVE_BK_PINS and BK_ELF.is_file(),
    f"Banjo-Kazooie build artifacts not found under {BK_ROOT}",
)
class BkShadowingPinConformanceTests(unittest.TestCase):
    """The negative result, and it is a real one.

    Banjo-Kazooie ran a deliberate shiftability campaign: MR !52, merged two
    days after its 100% announcement and authored by the N64Recomp author,
    is titled *"Remove all undefined symbols (besides fixed address ones) and
    fix bss/data migrations to allow shifting"*. If that landed, this project
    should have no shadowing pins at all -- and it has none. The check is
    worth running precisely because it can come back empty: a classifier that
    only ever fires is not a classifier.
    """

    audit: ClassVar[ShiftAudit]

    @classmethod
    def setUpClass(cls) -> None:
        model = default_pin_model()
        cls.audit = build_shift_audit(
            ldmap=read_ld_map(BK_MAP),
            image=BK_IMAGE.read_bytes(),
            pins=read_pin_files(BK_PIN_FILES, model=model),
            model=model,
            auto_blobs=True,
            elf=read_elf_symbols(BK_ELF),
            map_path=str(BK_MAP),
            image_path=str(BK_IMAGE),
            elf_path=str(BK_ELF),
        )

    def test_no_pin_in_this_project_shadows_an_object_definition(self) -> None:
        self.assertEqual(self.audit.pins.counts[SHADOWING_PIN], 0)

    def test_the_other_classes_are_the_s7_scorecard_unchanged(self) -> None:
        """Reading the ELF adds a class; it never moves one that was already
        decided on other evidence."""

        counts = self.audit.pins.counts
        self.assertEqual(len(self.audit.pins.entries), 127)
        self.assertEqual(counts[DERIVED], 6)
        self.assertEqual(counts[ARTIFACT_SUSPECT], 84)
        self.assertEqual(counts[ROM_OFFSET], 37)
        self.assertEqual(counts[UNCLASSIFIED], 0)


class ElfAuditWiringTests(unittest.TestCase):
    """The synthetic half: the flag is optional, and off is not zero."""

    def audit(self, *, elf: object | None = None) -> ShiftAudit:
        model = default_pin_model()
        return build_shift_audit(
            ldmap=parse_ld_map(SYNTHETIC_MAP),
            image=SYNTHETIC_IMAGE,
            pins=PinCatalogue(
                entries=parse_pin_text(
                    "D_80000440 = 0x80000440;\n", path="syms.txt", model=model
                ),
                sources=("syms.txt",),
            ),
            model=model,
            elf=elf,  # type: ignore[arg-type]
            elf_path="game.elf" if elf is not None else None,
        )

    def test_no_elf_leaves_the_class_empty_and_the_path_null(self) -> None:
        found = self.audit()
        self.assertIsNone(found.elf_path)
        self.assertEqual(found.pins.counts[SHADOWING_PIN], 0)
        self.assertIsNone(found.as_dict(limit=5)["elf"])

    def test_an_elf_that_shadows_the_pin_reclassifies_it(self) -> None:
        elf = parse_elf_symbols(
            build_elf(
                sections=[(".main", 0x80000400, 0x80, 0x6)],
                symbols=[("D_80000440", 0x80000440, 0x4, 1, 1, SHN_ABS)],
            ),
            path="game.elf",
        )
        found = self.audit(elf=elf)
        self.assertEqual(found.pins.counts[SHADOWING_PIN], 1)
        self.assertEqual(found.as_dict(limit=5)["pins_shadowing"], 1)
        self.assertEqual(found.elf_path, "game.elf")

    def test_a_bad_elf_is_refused_by_the_command_not_the_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "game.map").write_text(SYNTHETIC_MAP, encoding="utf-8")
            (root / "game.z64").write_bytes(SYNTHETIC_IMAGE)
            (root / "not.elf").write_bytes(b"\x80\x37\x12\x40" + bytes(64))
            stderr = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                status = main(
                    [
                        "shift",
                        "audit",
                        "--map",
                        str(root / "game.map"),
                        "--image",
                        str(root / "game.z64"),
                        "--elf",
                        str(root / "not.elf"),
                    ]
                )
        self.assertEqual(status, 2)
        self.assertIn("not an ELF file", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
