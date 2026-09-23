"""The promotion audit: bare cross-module names and duplicated jump-table pools.

Every object here is built by hand from `elf_fixtures`. The shapes are the
two faults backlog item 25 records -- a data reference spelled with the
other module's own name, and a switch table left in an object's `.rodata` --
with synthetic names and synthetic words. No game bytes, no toolchain.
"""

from __future__ import annotations

import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from elf_fixtures import (
    R_MIPS_26,
    R_MIPS_32,
    R_MIPS_HI16,
    R_MIPS_LO16,
    STB_GLOBAL,
    STB_LOCAL,
    STT_FUNC,
    RelocSpec,
    SymbolSpec,
    build_relocatable,
    words,
)

from decomp_workbench import promotion_audit as pa
from decomp_workbench import reloc_surface as rs
from decomp_workbench.cli import main
from decomp_workbench.elf import parse_elf

STT_SECTION = 3

JAL = 0x0C000000
LUI = 0x3C010000
LW = 0x8C210000
ADDIU = 0x24210000
NOP = 0x00000000

MODULE_START = 0x1000
TEXT_OFFSET = 0x40
RODATA_OFFSET = 0x800
VMA = 0xF0000000

#: The resident side of the link, as a splat-style symbol list.
RESIDENT = "residentTable = 0x80123456; // type:data\nresidentHelper = 0x80001000;\n"

PATTERN = r"_o[0-9]+Reloc$"


def module_object(
    *,
    data_symbol: str = "residentTable",
    call_symbol: str = "residentHelper_o1Reloc",
    pointer_table: bool = False,
) -> bytes:
    """One function that calls out, loads resident data, and switches.

    `.rodata` holds a three-entry jump table whose words are `.text`-relative
    case addresses, relocated against the `.text` section symbol -- the shape
    a compiled `switch` leaves behind. With ``pointer_table`` the entries name
    a function instead, which is a pointer table, not a switch.
    """

    text = words(
        JAL,  # 0x00 call out
        NOP,
        LUI,  # 0x08 %hi(data)
        LW,  # 0x0C %lo(data)
        LUI,  # 0x10 %hi(table)
        ADDIU,  # 0x14 %lo(table)
        NOP,
        NOP,
    )
    table_target = "overlayFn" if pointer_table else ".text"
    rodata = words(0x08, 0x0C, 0x10) if not pointer_table else words(0, 0, 0)
    return build_relocatable(
        {".text": text, ".rodata": rodata},
        [
            SymbolSpec(".text", 0, 0, STT_SECTION, STB_LOCAL, ".text"),
            SymbolSpec(".rodata", 0, 0, STT_SECTION, STB_LOCAL, ".rodata"),
            SymbolSpec("overlayFn", 0, 0x20, STT_FUNC, STB_GLOBAL, ".text"),
            SymbolSpec(call_symbol),
            SymbolSpec(data_symbol),
        ],
        [
            RelocSpec(".text", 0x00, call_symbol, R_MIPS_26),
            RelocSpec(".text", 0x08, data_symbol, R_MIPS_HI16),
            RelocSpec(".text", 0x0C, data_symbol, R_MIPS_LO16),
            RelocSpec(".text", 0x10, ".rodata", R_MIPS_HI16),
            RelocSpec(".text", 0x14, ".rodata", R_MIPS_LO16),
            RelocSpec(".rodata", 0x0, table_target, R_MIPS_32),
            RelocSpec(".rodata", 0x4, table_target, R_MIPS_32),
            RelocSpec(".rodata", 0x8, table_target, R_MIPS_32),
        ],
    )


def module_map(*, place_rodata: bool = False) -> rs.ModuleMap:
    placements: list[dict[str, object]] = [
        {"object": "tu.c.o", "section": ".text", "offset": hex(TEXT_OFFSET)}
    ]
    if place_rodata:
        placements.append(
            {"object": "tu.c.o", "section": ".rodata", "offset": hex(RODATA_OFFSET)}
        )
    return rs.parse_module_map(
        {
            "schema": rs.MODULE_MAP_SCHEMA,
            "module": {
                "name": "m1",
                "image_start": hex(MODULE_START),
                "image_end": "0x2000",
                "synthetic_vma": hex(VMA),
                "sections": {
                    ".text": {"offset": 0, "size": 0x800},
                    ".rodata": {"offset": RODATA_OFFSET, "size": 0x100},
                },
                "text_placement": placements,
            },
        }
    )


def shipped_image(*, corrupt: bool = False) -> bytes:
    """The shipped pool: each entry is its case's module address at the VMA."""

    image = bytearray(0x2000)
    start = MODULE_START + RODATA_OFFSET
    for index, case in enumerate((0x08, 0x0C, 0x10)):
        value = VMA + TEXT_OFFSET + case + (4 if corrupt and index == 1 else 0)
        struct.pack_into(">I", image, start + 4 * index, value)
    return bytes(image)


def audit(
    obj: bytes | None = None, *, map_: rs.ModuleMap | None = None, **options: object
) -> pa.PromotionAudit:
    elf = parse_elf(obj if obj is not None else module_object())
    return pa.promotion_audit(
        [("tu.c.o", elf)],
        map_ if map_ is not None else module_map(),
        **options,  # type: ignore[arg-type]
    )


class ReferenceTests(unittest.TestCase):
    def test_a_bare_resident_data_name_is_refused_even_when_calls_are_rebound(
        self,
    ) -> None:
        """The whale's fault: calls went through the surface, data did not."""

        result = audit(
            resident=pa.resident_names_from_text(RESIDENT), surface_pattern=PATTERN
        )
        by_name = {item.name: item for item in result.references}
        data = by_name["residentTable"]
        self.assertEqual(data.kind, pa.KIND_DATA)
        self.assertEqual(data.verdict, pa.REF_RESIDENT_OVERRIDE)
        self.assertTrue(data.refused)
        self.assertEqual(len(data.sites), 2)
        call = by_name["residentHelper_o1Reloc"]
        self.assertEqual(call.kind, pa.KIND_CALL)
        self.assertEqual(call.verdict, pa.REF_SURFACE)
        self.assertFalse(result.passed)
        self.assertTrue(any("residentTable" in item for item in result.refusals))

    def test_a_bare_resident_call_is_refused_too(self) -> None:
        result = audit(
            module_object(call_symbol="residentHelper"),
            resident=pa.resident_names_from_text(RESIDENT),
        )
        by_name = {item.name: item for item in result.references}
        self.assertEqual(by_name["residentHelper"].verdict, pa.REF_RESIDENT_OVERRIDE)

    def test_a_name_off_the_placeholder_spelling_is_refused_as_bare(self) -> None:
        result = audit(
            module_object(data_symbol="unknownDatum"), surface_pattern=PATTERN
        )
        by_name = {item.name: item for item in result.references}
        self.assertEqual(by_name["unknownDatum"].verdict, pa.REF_BARE)
        self.assertIn("placeholder spelling", by_name["unknownDatum"].message)

    def test_the_rebound_form_passes(self) -> None:
        result = audit(
            module_object(data_symbol="residentTable_o1Reloc"),
            resident=pa.resident_names_from_text(RESIDENT),
            surface_pattern=PATTERN,
            map_=module_map(place_rodata=True),
            image=shipped_image(),
        )
        self.assertTrue(result.passed, result.refusals)

    def test_a_block_line_for_a_resident_name_is_the_override_itself(self) -> None:
        block = "/* tu.c.o */\nresidentTable = 0x00000010;\nother_o1Reloc = 0x4;\n"
        result = audit(
            resident=pa.resident_names_from_text(RESIDENT), linker_block=block
        )
        self.assertEqual(
            [item.name for item in result.block_overrides], ["residentTable"]
        )
        by_name = {item.name: item for item in result.references}
        self.assertEqual(by_name["residentTable"].block_value, "0x00000010")
        self.assertIn("already assigns it", by_name["residentTable"].message)

    def test_nothing_declared_lists_rather_than_judges(self) -> None:
        result = audit(map_=module_map(place_rodata=True))
        self.assertTrue(
            all(item.verdict == pa.REF_UNCLASSIFIED for item in result.references)
        )
        self.assertTrue(result.passed)
        self.assertTrue(any("--resident" in item for item in result.warnings))

    def test_resident_names_are_read_from_an_elf(self) -> None:
        resident = build_relocatable(
            {".text": words(NOP), ".data": words(0)},
            [
                SymbolSpec("residentHelper", 0, 4, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("residentTable", 0, 4, 1, STB_GLOBAL, ".data"),
                SymbolSpec("staticThing", 0, 4, 1, STB_LOCAL, ".data"),
                SymbolSpec("undefinedThere"),
            ],
        )
        names = pa.resident_names_from_elf(parse_elf(resident))
        self.assertEqual(names, {"residentHelper", "residentTable"})


class JumpTableTests(unittest.TestCase):
    def test_an_unplaced_switch_table_duplicates_the_shipped_pool(self) -> None:
        result = audit()
        self.assertEqual(len(result.tables), 1)
        table = result.tables[0]
        self.assertEqual(table.entries, 3)
        self.assertEqual(table.offset, 0)
        self.assertEqual(table.verdict, pa.POOL_DUPLICATE)
        self.assertEqual([item.function for item in table.referenced_by], ["overlayFn"])
        self.assertFalse(result.passed)
        self.assertIn("12 bytes", table.message)

    def test_back_to_back_tables_split_where_code_loads_them(self) -> None:
        """Two switches' tables are contiguous; contiguity is not one table."""

        text = words(LUI, ADDIU, LUI, ADDIU, NOP, NOP, NOP, NOP)
        obj = build_relocatable(
            {
                ".text": text[:12] + words(ADDIU | 0x0C) + text[16:],
                ".rodata": words(0x08, 0x0C, 0x10, 0x14, 0x18),
            },
            [
                SymbolSpec(".text", 0, 0, STT_SECTION, STB_LOCAL, ".text"),
                SymbolSpec(".rodata", 0, 0, STT_SECTION, STB_LOCAL, ".rodata"),
                SymbolSpec("first", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("second", 8, 0x18, STT_FUNC, STB_GLOBAL, ".text"),
            ],
            [
                RelocSpec(".text", 0x0, ".rodata", R_MIPS_HI16),
                RelocSpec(".text", 0x4, ".rodata", R_MIPS_LO16),
                RelocSpec(".text", 0x8, ".rodata", R_MIPS_HI16),
                RelocSpec(".text", 0xC, ".rodata", R_MIPS_LO16),
                *(
                    RelocSpec(".rodata", 4 * index, ".text", R_MIPS_32)
                    for index in range(5)
                ),
            ],
        )
        result = audit(obj)
        self.assertEqual(
            [(table.offset, table.entries) for table in result.tables],
            [(0, 3), (0xC, 2)],
        )
        self.assertEqual(
            [
                [user.function for user in table.referenced_by]
                for table in result.tables
            ],
            [["first"], ["second"]],
        )

    def test_a_placed_table_is_read_against_the_shipped_words(self) -> None:
        result = audit(map_=module_map(place_rodata=True), image=shipped_image())
        table = result.tables[0]
        self.assertEqual(table.verdict, pa.POOL_PLACED)
        self.assertEqual((table.agree, table.disagree), (3, 0))
        self.assertTrue(result.passed)

    def test_a_placed_table_that_disagrees_is_refused(self) -> None:
        result = audit(
            map_=module_map(place_rodata=True), image=shipped_image(corrupt=True)
        )
        table = result.tables[0]
        self.assertEqual(table.verdict, pa.POOL_PLACED_DISAGREES)
        self.assertEqual((table.agree, table.disagree), (2, 1))
        self.assertFalse(result.passed)

    def test_a_pointer_table_is_not_a_switch_but_its_bytes_are_reported(
        self,
    ) -> None:
        result = audit(module_object(pointer_table=True))
        self.assertEqual(result.tables, ())
        self.assertEqual(len(result.unplaced_rodata), 1)
        self.assertEqual(result.unplaced_rodata[0]["size"], 12)


class CliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def write(self, root: Path, *, place_rodata: bool) -> list[str]:
        (root / "tu.c.o").write_bytes(module_object())
        placements: list[dict[str, object]] = [
            {"object": "tu.c.o", "section": ".text", "offset": hex(TEXT_OFFSET)}
        ]
        if place_rodata:
            placements.append(
                {
                    "object": "tu.c.o",
                    "section": ".rodata",
                    "offset": hex(RODATA_OFFSET),
                }
            )
        document = {
            "schema": rs.MODULE_MAP_SCHEMA,
            "module": {
                "name": "m1",
                "image_start": hex(MODULE_START),
                "image_end": "0x2000",
                "synthetic_vma": hex(VMA),
                "sections": {
                    ".text": {"offset": 0, "size": 0x800},
                    ".rodata": {"offset": RODATA_OFFSET, "size": 0x100},
                },
                "text_placement": placements,
            },
        }
        (root / "module.json").write_text(json.dumps(document), encoding="utf-8")
        (root / "resident.txt").write_text(RESIDENT, encoding="utf-8")
        (root / "image.bin").write_bytes(shipped_image())
        return [
            "promotion-audit",
            str(root / "tu.c.o"),
            "--module-map",
            str(root / "module.json"),
            "--resident",
            str(root / "resident.txt"),
            "--surface-pattern",
            PATTERN,
            "--image",
            str(root / "image.bin"),
        ]

    def test_refusals_name_the_file_and_exit_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.write(Path(directory), place_rodata=False)
            status, stdout, _ = self.run_cli(arguments)
            json_status, json_out, _ = self.run_cli([*arguments, "--json"])
        self.assertEqual(status, 1)
        self.assertIn("REFUSED (2)", stdout)
        self.assertIn("tu.c.o", stdout)
        self.assertIn("residentTable", stdout)
        self.assertIn("jump table", stdout)
        self.assertEqual(json_status, 1)
        payload = json.loads(json_out)
        self.assertEqual(payload["schema"], "decomp-workbench-promotion-audit-v1")
        self.assertFalse(payload["pass"])
        self.assertEqual(payload["refusal_count"], 2)

    def test_a_missing_module_map_is_an_error_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.write(Path(directory), place_rodata=True)
            arguments[3] = str(Path(directory) / "absent.json")
            status, _, stderr = self.run_cli(arguments)
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)


if __name__ == "__main__":
    unittest.main()
