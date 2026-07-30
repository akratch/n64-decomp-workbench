"""Combined verdict and mechanism diagnosis contracts."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.diagnosis import diagnose_objects
from decomp_workbench.objdump import parse_disassembly

TARGET = """
00000000 <demo>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 012a4021  addu $t0,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

CANDIDATE = """
00000000 <demo>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 012a5821  addu $t3,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
"""


class DiagnosisTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def write_dumps(self, root: Path) -> tuple[Path, Path]:
        target = root / "target.objdump"
        candidate = root / "candidate.objdump"
        target.write_text(TARGET, encoding="utf-8")
        candidate.write_text(CANDIDATE, encoding="utf-8")
        return target, candidate

    def test_diagnose_disassembles_each_object_once(self) -> None:
        target_items = parse_disassembly(TARGET, symbol="demo")
        candidate_items = parse_disassembly(CANDIDATE, symbol="demo")
        with mock.patch(
            "decomp_workbench.diagnosis.dump_object",
            side_effect=[
                ("target dump", target_items),
                ("candidate dump", candidate_items),
            ],
        ) as dump:
            result = diagnose_objects("target.o", "candidate.o", symbol="demo")
        self.assertEqual(dump.call_count, 2)
        self.assertEqual(result.comparison.aligned_register, 1)
        self.assertEqual(result.view.counts["register"], 1)

    def test_json_contains_both_versioned_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.write_dumps(Path(temporary))
            status, stdout, stderr = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-diagnosis-v1")
        self.assertEqual(payload["comparison"]["aligned_register"], 1)
        self.assertEqual(payload["view"]["register"], 1)

    def test_human_default_is_one_decisive_hunk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.write_dumps(Path(temporary))
            status, stdout, _ = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--color",
                    "never",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("COMPARISON", stdout)
        self.assertIn("MECHANISM", stdout)
        self.assertIn("HUNK 1", stdout)
        self.assertNotIn("HUNK 2", stdout)

    def test_fail_and_census_exit_contracts_are_shared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.write_dumps(Path(temporary))
            arguments = [
                "diagnose-dumps",
                str(target),
                str(candidate),
                "--function",
                "demo",
                "--fail-on-mismatch",
            ]
            self.assertEqual(self.run_cli(arguments)[0], 1)
            self.assertEqual(
                self.run_cli([*arguments, "--census", "aligned_register=1"])[0],
                1,
            )
            self.assertEqual(
                self.run_cli(
                    [
                        "diagnose-dumps",
                        str(target),
                        str(target),
                        "--function",
                        "demo",
                        "--fail-on-mismatch",
                    ]
                )[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
