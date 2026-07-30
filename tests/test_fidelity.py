"""Instrumentation fidelity is section-scoped rather than whole-file guessed."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.fidelity import _section_bytes, compare_object_fidelity


class FidelityTests(unittest.TestCase):
    def make_objdump(self, root: Path) -> Path:
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "obj = pathlib.Path(sys.argv[-1])\n"
            "different = b'different' in obj.read_bytes()\n"
            "if '-s' in sys.argv:\n"
            " print('Contents of section:')\n"
            " print(' 0000 11223344' if not different else ' 0000 deadbeef')\n"
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

    def test_debug_only_file_difference_does_not_fail_meaningful_sections(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            stock = root / "stock.o"
            instrumented = root / "instrumented.o"
            stock.write_bytes(b"file-a")
            instrumented.write_bytes(b"file-b")
            report = compare_object_fidelity(
                stock,
                instrumented,
                objdump=str(objdump),
            )
        self.assertTrue(report["pass"])
        self.assertFalse(report["file_identical"])

    def test_meaningful_section_difference_fails_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            objdump = self.make_objdump(root)
            stock = root / "stock.o"
            instrumented = root / "instrumented.o"
            stock.write_bytes(b"file-a")
            instrumented.write_bytes(b"different")
            report = compare_object_fidelity(
                stock,
                instrumented,
                objdump=str(objdump),
            )
        self.assertFalse(report["pass"])
        self.assertFalse(report["gates"][".text"])

    def test_section_parser_keeps_short_tail_and_stops_before_ascii(self) -> None:
        parsed = _section_bytes(
            ' 0000 11223344 55667788 99aabbcc ddee  ."3DUfw.......\n'
            " 0010 deadbeef  dead\n"
        )
        self.assertEqual(
            parsed,
            bytes.fromhex("112233445566778899aabbccddeedeadbeef"),
        )


if __name__ == "__main__":
    unittest.main()
