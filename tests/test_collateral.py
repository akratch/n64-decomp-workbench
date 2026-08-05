"""Translation-unit collateral remains distinct from function exactness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.collateral import compare_object_collateral


class CollateralTests(unittest.TestCase):
    def make_objdump(self, root: Path) -> Path:
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "obj = pathlib.Path(sys.argv[-1])\n"
            "changed = b'changed' in obj.read_bytes()\n"
            "partial = b'partial' in obj.read_bytes()\n"
            "if '-h' in sys.argv:\n"
            " print('Idx Name Size VMA LMA File off Algn')\n"
            " text_size = '00000010' if partial else '00000008'\n"
            " print(f'  0 .text {text_size} 00000000 00000000 00000040 2**4')\n"
            " print('                  CONTENTS, ALLOC, LOAD, CODE')\n"
            " size = '00000020' if changed else '00000010'\n"
            " print(f'  1 .bss {size} 00000000 00000000 00000048 2**4')\n"
            " print('                  ALLOC')\n"
            "elif '-s' in sys.argv:\n"
            " print('Contents of section .text:')\n"
            " print(' 0000 11223344 55667788')\n"
            "elif '-r' in sys.argv:\n"
            " print('RELOCATION RECORDS FOR [.text]:')\n"
            " print('00000000 R_MIPS_26 helper')\n"
            "elif '-t' in sys.argv:\n"
            " print('SYMBOL TABLE:')\n"
            " print('00000000 g F .text 00000008 demo')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        return objdump

    def test_zero_fill_size_change_is_reported_without_section_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            reference = root / "reference.o"
            candidate = root / "candidate.o"
            reference.write_bytes(b"reference")
            candidate.write_bytes(b"changed")

            report = compare_object_collateral(
                reference, candidate, objdump=str(objdump)
            )

        self.assertTrue(report["collateral_detected"])
        self.assertEqual(report["classification"], "translation-unit-difference")
        self.assertEqual(report["section_change_count"], 1)
        self.assertEqual(report["section_changes"][0]["section"], ".bss")
        self.assertEqual(report["section_changes"][0]["size_delta"], 16)
        self.assertEqual(report["section_changes"][0]["changed"], ["size"])

    def test_incomplete_section_dump_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            reference = root / "reference.o"
            candidate = root / "candidate.o"
            reference.write_bytes(b"reference")
            candidate.write_bytes(b"partial")

            with self.assertRaisesRegex(ValueError, "returned 8 of 16 byte"):
                compare_object_collateral(reference, candidate, objdump=str(objdump))

    def test_cli_can_fail_a_collateral_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            reference = root / "reference.o"
            candidate = root / "candidate.o"
            reference.write_bytes(b"reference")
            candidate.write_bytes(b"changed")

            status = main(
                [
                    "object-collateral",
                    str(reference),
                    str(candidate),
                    "--objdump",
                    str(objdump),
                    "--fail-on-collateral",
                ]
            )

        self.assertEqual(status, 1)

    def test_exact_selected_function_classifies_remaining_changes_as_collateral(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            reference = root / "reference.o"
            candidate = root / "candidate.o"
            reference.write_bytes(b"reference")
            candidate.write_bytes(b"changed")
            comparison = SimpleNamespace(
                raw_word_mismatches=0,
                relocation_target_mismatches=0,
                exact=True,
                as_dict=lambda: {"exact": True},
            )

            with mock.patch(
                "decomp_workbench.collateral.compare_objects",
                return_value=comparison,
            ):
                report = compare_object_collateral(
                    reference,
                    candidate,
                    symbol="demo",
                    objdump=str(objdump),
                )

        self.assertTrue(report["selected_function_exact"])
        self.assertEqual(report["classification"], "outside-selected-function")
