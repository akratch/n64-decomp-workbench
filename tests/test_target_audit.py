"""Tests for `target audit`: the static target-object scope check (W4).

Every object here is hand-built by `target_audit_fixtures.build_target_object`
-- no bytes from any game or ROM. The fixture reproduces the *shape* the real
cef4c objects (see `docs/target-audit.md`) were found to have: a `.rel.rodata`
entry per jump table word pointing at the `.text` section symbol, and an FP
literal loaded through `lwc1 %lo(sym)($at)` binding to an `SHN_UNDEF` symbol.
"""

from __future__ import annotations

import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from target_audit_fixtures import PoolSymbol, build_target_object

from decomp_workbench.cli import main
from decomp_workbench.elf import ElfFormatError, parse_elf
from decomp_workbench.target_audit import (
    DEFECT,
    INFO,
    WARNING,
    TargetAudit,
    audit_target,
    target_audit_lines,
)


def _write(data: bytes, name: str = "obj.o") -> Path:
    directory = Path(tempfile.mkdtemp())
    path = directory / name
    path.write_bytes(data)
    return path


def _codes(audit: TargetAudit, severity: str | None = None) -> list[str]:
    return [
        item.code
        for item in audit.findings
        if severity is None or item.severity == severity
    ]


class LiteralPoolHeuristicTests(unittest.TestCase):
    def test_truncated_pool_is_a_defect(self) -> None:
        # .rodata ends exactly at the jump table's own end: the cef4c shape.
        data = build_target_object(
            jump_table_words=10,
            rodata_extra_bytes=0,
            pool_symbols=[
                PoolSymbol("D_ovl0_800D6120", hi_offset=0x100, lo_offset=0x104),
                PoolSymbol("D_ovl0_800D6124", hi_offset=0x108, lo_offset=0x10C),
                PoolSymbol("D_ovl0_800D6128", hi_offset=0x110, lo_offset=0x114),
                PoolSymbol("D_ovl0_800D612C", hi_offset=0x118, lo_offset=0x11C),
            ],
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "defects")
        self.assertIn("literal-pool-truncated-at-jump-table", _codes(audit, DEFECT))
        self.assertEqual(audit.data_scope["jump_table_words"], 10)
        self.assertEqual(audit.data_scope["jump_table_end"], 40)
        self.assertEqual(audit.data_scope["bytes_after_jump_table"], 0)

    def test_pool_present_past_the_table_is_ok(self) -> None:
        # The fixed shape: 16 bytes (4 literals) survive past the table.
        data = build_target_object(
            jump_table_words=10,
            rodata_extra_bytes=16,
            pool_symbols=[
                PoolSymbol("D_ovl0_800D6120", hi_offset=0x100, lo_offset=0x104),
                PoolSymbol("D_ovl0_800D6124", hi_offset=0x108, lo_offset=0x10C),
            ],
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "ok")
        self.assertIn("literal-pool-present", _codes(audit, INFO))
        self.assertEqual(audit.data_scope["bytes_after_jump_table"], 16)

    def test_decoy_load_through_non_at_register_is_excluded(self) -> None:
        # The section still ends exactly at the table boundary, but the only
        # undefined-symbol load goes through $v0, not $at -- not a pool site,
        # and must not trigger the truncation defect. Mirrors the real
        # cef4c object's D_ovl0_800D639C site (rs=$a1, excluded the same way).
        data = build_target_object(
            jump_table_words=5,
            rodata_extra_bytes=0,
            pool_symbols=[],
            include_decoy=True,
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "ok")
        self.assertEqual(_codes(audit), [])
        # The decoy is still visible in the data-scope report.
        self.assertEqual(audit.data_scope["undef_data_symbol_count"], 1)
        self.assertIn("D_decoy", audit.data_scope["undef_data_symbols"])

    def test_no_jump_table_context_is_a_warning(self) -> None:
        # $at-loaded undefined symbols exist, but .rel.rodata carries no
        # jump-table entries to check the boundary against at all.
        data = build_target_object(
            jump_table_words=0,
            rodata_extra_bytes=0,
            pool_symbols=[
                PoolSymbol("D_thing", hi_offset=0x0, lo_offset=0x4),
            ],
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "warnings")
        self.assertIn("fp-literal-undef-no-jump-table-context", _codes(audit, WARNING))
        self.assertIsNone(audit.data_scope["jump_table_end"])

    def test_ldc1_and_lw_opcodes_are_also_recognised(self) -> None:
        data = build_target_object(
            jump_table_words=4,
            rodata_extra_bytes=0,
            pool_symbols=[
                PoolSymbol("D_a", hi_offset=0x0, lo_offset=0x4, opcode=0x35),  # ldc1
                PoolSymbol("D_b", hi_offset=0x8, lo_offset=0xC, opcode=0x23),  # lw
            ],
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "defects")
        finding = next(
            item
            for item in audit.findings
            if item.code == "literal-pool-truncated-at-jump-table"
        )
        self.assertEqual(
            sorted(finding.evidence["distinct_undef_symbols"]), ["D_a", "D_b"]
        )


class DataScopeTests(unittest.TestCase):
    def test_addend_structure_is_reported_per_symbol(self) -> None:
        data = build_target_object(
            jump_table_words=2,
            rodata_extra_bytes=8,
            pool_symbols=[
                PoolSymbol("D_shared", hi_offset=0x0, lo_offset=0x4),
                PoolSymbol("D_shared", hi_offset=0x8, lo_offset=0xC),
            ],
        )
        audit = audit_target(_write(data))
        # Both sites bind the same symbol at addend 0 -- one entry, two rows.
        self.assertEqual(audit.data_scope["undef_data_symbols"]["D_shared"], [0, 0])
        self.assertEqual(audit.data_scope["undef_data_symbol_count"], 1)


class ElfSanityTests(unittest.TestCase):
    def test_missing_symtab_is_a_defect(self) -> None:
        data = build_target_object(
            jump_table_words=2,
            rodata_extra_bytes=8,
            pool_symbols=[],
            include_symtab=False,
        )
        audit = audit_target(_write(data))
        self.assertEqual(audit.verdict, "defects")
        self.assertIn("missing-symtab", _codes(audit, DEFECT))

    def test_reloc_entsize_mismatch_is_a_defect(self) -> None:
        data = build_target_object(
            jump_table_words=2,
            rodata_extra_bytes=8,
            pool_symbols=[
                PoolSymbol("D_x", hi_offset=0x0, lo_offset=0x4),
            ],
            rel_text_entsize=4,  # Elf32_Rel is 8 bytes; this is malformed.
        )
        audit = audit_target(_write(data))
        self.assertIn("reloc-section-malformed", _codes(audit, DEFECT))

    def test_bad_magic_raises_elf_format_error(self) -> None:
        with self.assertRaises(ElfFormatError):
            parse_elf(b"not an elf file at all")


class RomCrossCheckTests(unittest.TestCase):
    def _defective_object(self) -> Path:
        data = build_target_object(
            jump_table_words=2,  # rodata = 8 bytes
            rodata_extra_bytes=0,
            pool_symbols=[
                PoolSymbol("D_a", hi_offset=0x0, lo_offset=0x4),
                PoolSymbol("D_b", hi_offset=0x8, lo_offset=0xC),
            ],
        )
        return _write(data)

    def test_rom_args_must_be_paired(self) -> None:
        path = self._defective_object()
        with self.assertRaises(ValueError):
            audit_target(path, rom="somewhere.z64")
        with self.assertRaises(ValueError):
            audit_target(path, rom_offset=0, va=0)

    def test_rom_confirms_the_literal_pool(self) -> None:
        path = self._defective_object()
        rom_offset = 0x100
        rodata_size = 8  # 2 jump-table words, no extra bytes
        past_offset = rom_offset + rodata_size
        # window = max(16, 4*2) = 16 bytes = 4 words; two symbols means a
        # word repeated exactly twice is a match.
        chunk = struct.pack(">IIII", 0x4422F983, 0x4422F983, 0xDEADBEEF, 0x11111111)
        rom = bytearray(past_offset + len(chunk) + 16)
        rom[past_offset : past_offset + len(chunk)] = chunk
        rom_path = _write(bytes(rom), name="rom.z64")

        audit = audit_target(path, rom=rom_path, rom_offset=rom_offset, va=0x80000100)
        self.assertEqual(audit.verdict, "defects")  # truncation still a defect
        self.assertIn("rom-confirms-literal-pool", _codes(audit, INFO))
        assert audit.rom_check is not None
        self.assertEqual(audit.rom_check["most_common_count"], 2)
        self.assertTrue(audit.rom_check["matches_undef_fp_symbol_count"])
        self.assertEqual(audit.rom_check["words"][:2], ["0x4422f983", "0x4422f983"])

    def test_rom_read_out_of_range_is_a_defect(self) -> None:
        path = self._defective_object()
        rom_path = _write(b"\x00" * 4, name="tiny.z64")
        audit = audit_target(path, rom=rom_path, rom_offset=0x1000, va=0x80001000)
        self.assertEqual(audit.verdict, "defects")
        self.assertIn("rom-read-out-of-range", _codes(audit, DEFECT))

    def test_healthy_object_is_not_penalised_by_unrelated_rom_bytes(self) -> None:
        # The fixed shape: pool already inside .rodata. Bytes further on in
        # the ROM are the *next* datum, not a repeated literal, and must not
        # produce a false warning -- see target_audit._rom_cross_check's
        # `evaluate` gate.
        data = build_target_object(
            jump_table_words=2,
            rodata_extra_bytes=16,
            pool_symbols=[
                PoolSymbol("D_a", hi_offset=0x0, lo_offset=0x4),
                PoolSymbol("D_b", hi_offset=0x8, lo_offset=0xC),
            ],
        )
        path = _write(data)
        rom_offset = 0x100
        rodata_size = 8 + 16
        past_offset = rom_offset + rodata_size
        rom = bytearray(past_offset + 32)
        struct.pack_into(">IIII", rom, past_offset, 1, 2, 3, 4)
        rom_path = _write(bytes(rom), name="rom.z64")

        audit = audit_target(path, rom=rom_path, rom_offset=rom_offset, va=0x80000100)
        self.assertEqual(audit.verdict, "ok")
        self.assertEqual(_codes(audit, WARNING), [])
        self.assertEqual(_codes(audit, DEFECT), [])


class RenderingTests(unittest.TestCase):
    def test_lines_render_without_error_and_name_the_verdict(self) -> None:
        data = build_target_object(
            jump_table_words=3,
            rodata_extra_bytes=0,
            pool_symbols=[PoolSymbol("D_x", hi_offset=0x0, lo_offset=0x4)],
        )
        audit = audit_target(_write(data))
        lines = target_audit_lines(audit)
        self.assertIn("verdict: DEFECTS (1 defect(s), 0 warning(s))", lines)


class TargetAuditCliTests(unittest.TestCase):
    def _run(self, args: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_cli_reports_defect_and_exits_2(self) -> None:
        data = build_target_object(
            jump_table_words=4,
            rodata_extra_bytes=0,
            pool_symbols=[PoolSymbol("D_x", hi_offset=0x0, lo_offset=0x4)],
        )
        path = _write(data)
        code, out, _err = self._run(["target", "audit", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("DEFECTS", out)
        self.assertIn("literal-pool-truncated-at-jump-table", out)

    def test_cli_reports_ok_and_exits_0(self) -> None:
        data = build_target_object(
            jump_table_words=4, rodata_extra_bytes=16, pool_symbols=[]
        )
        path = _write(data)
        code, out, _err = self._run(["target", "audit", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("verdict: OK", out)

    def test_cli_json_output_is_the_versioned_schema(self) -> None:
        data = build_target_object(
            jump_table_words=4, rodata_extra_bytes=16, pool_symbols=[]
        )
        path = _write(data)
        code, out, _err = self._run(["target", "audit", str(path), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-target-audit-v1")
        self.assertEqual(payload["verdict"], "ok")

    def test_cli_refuses_partial_rom_arguments(self) -> None:
        data = build_target_object(
            jump_table_words=4, rodata_extra_bytes=16, pool_symbols=[]
        )
        path = _write(data)
        code, _out, err = self._run(["target", "audit", str(path), "--rom", "x.z64"])
        self.assertEqual(code, 2)
        self.assertIn("--rom-offset", err)

    def test_cli_group_listing_exits_zero(self) -> None:
        code, out, _err = self._run(["target"])
        self.assertEqual(code, 0)
        self.assertIn("audit", out)


if __name__ == "__main__":
    unittest.main()
