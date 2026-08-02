"""Toolchain microcases and cross-revision lineage stay redistributable."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.fingerprint import (
    compare_fingerprint_reports,
    cross_rom_lineage,
    instruction_fingerprint,
    run_toolchain_fingerprint,
)
from decomp_workbench.model import Instruction


class FingerprintTests(unittest.TestCase):
    def test_computed_jump_excludes_return_register_in_both_objdump_dialects(
        self,
    ) -> None:
        instructions = [
            Instruction(0, "01c00008", "jr\tt6"),
            Instruction(4, "03e00008", "jr\t$ra"),
        ]

        features = instruction_fingerprint(instructions)

        self.assertTrue(features["computed_jump"])
        self.assertEqual(features["computed_jumps"], ["jr\tt6"])

    def make_tools(self, root: Path) -> tuple[Path, Path]:
        compiler = root / "compile.py"
        compiler.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[2]).write_bytes("
            "pathlib.Path(sys.argv[1]).read_bytes())\n",
            encoding="utf-8",
        )
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "for name in ('dkwb_fp_control_flow', 'dkwb_fp_stack_home', "
            "'dkwb_fp_schedule', 'dkwb_fp_allocation', "
            "'dkwb_fp_dense_switch_4', 'dkwb_fp_dense_switch_5'):\n"
            " print('00000000 <%s>:' % name)\n"
            " print('   0: 27bdffe0  addiu $sp,$sp,-32')\n"
            " print('   4: 03e00008  jr $ra')\n"
            " print('   8: 00000000  nop')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        return compiler, objdump

    def test_bundled_microcases_produce_a_stable_feature_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, objdump = self.make_tools(root)
            report = run_toolchain_fingerprint(
                f"{sys.executable} {compiler} {{source}} {{output}}",
                compile_cwd=root,
                environment={},
                objdump=str(objdump),
                timeout=10,
            )
        self.assertEqual(len(report["cases"]), 6)
        self.assertEqual(len(report["fingerprint"]), 64)
        self.assertTrue(
            all(case["features"]["instructions"] == 3 for case in report["cases"])
        )
        self.assertIn("not a claim", report["proof"])
        self.assertEqual(len(report["suite"]), 64)
        dispatch = {
            case["name"]: case["features"]["computed_jump"]
            for case in report["cases"]
            if case["name"].startswith("dense-switch-")
        }
        self.assertEqual(dispatch, {"dense-switch-4": False, "dense-switch-5": False})
        self.assertTrue(compare_fingerprint_reports(report, report)["identical"])

        older_suite = dict(report)
        older_suite["suite"] = "0" * 64
        comparison = compare_fingerprint_reports(report, older_suite)
        self.assertFalse(comparison["compatible"])
        self.assertFalse(comparison["identical"])

    def test_lineage_records_hashes_without_reading_rom_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, objdump = self.make_tools(root)
            us = root / "us.o"
            jp = root / "jp.o"
            us.write_bytes(b"us")
            jp.write_bytes(b"jp")
            report = cross_rom_lineage(
                {"us": us, "jp": jp},
                objdump=str(objdump),
                symbol="dkwb_fp_control_flow",
                rom_hashes={"us": "a" * 64, "jp": "b" * 64},
            )
            with self.assertRaisesRegex(ValueError, "no matching revision"):
                cross_rom_lineage(
                    {"us": us, "jp": jp},
                    objdump=str(objdump),
                    symbol="dkwb_fp_control_flow",
                    rom_hashes={"eu": "c" * 64},
                )
            with self.assertRaisesRegex(ValueError, "64 hexadecimal"):
                cross_rom_lineage(
                    {"us": us, "jp": jp},
                    objdump=str(objdump),
                    symbol="dkwb_fp_control_flow",
                    rom_hashes={"us": "not-a-sha256"},
                )
        self.assertEqual(len(report["pairs"]), 1)
        self.assertTrue(report["pairs"][0]["exact"])
        self.assertEqual(
            report["revisions"]["us"]["rom_sha256"],
            "a" * 64,
        )
        self.assertIn("never reads", report["proof"])


if __name__ == "__main__":
    unittest.main()
