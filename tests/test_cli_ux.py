"""Tests for action-oriented CLI behavior."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main


class CliUxTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_web_lookup_requires_procedure(self) -> None:
        status, _, stderr = self.run_cli(
            ["trace-globalcolor", "unused.log", "--web", "9"]
        )
        self.assertEqual(status, 2)
        self.assertIn("--web requires --proc", stderr)

    def test_missing_web_lists_available_webs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p1dec proc=3 web=9 bestcolor=17 decision=color\n",
                encoding="utf-8",
            )
            status, _, stderr = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "3",
                    "--web",
                    "10",
                ]
            )
        self.assertEqual(status, 1)
        self.assertIn("available web(s): 9", stderr)

    def test_missing_procedure_does_not_show_unscoped_live_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 adjsave=1 unk23=0\n"
                "[CDX] p1dec proc=3 web=9 bestcolor=17 decision=color\n",
                encoding="utf-8",
            )
            status, stdout, stderr = self.run_cli(
                ["trace-globalcolor", str(trace), "--proc", "4"]
            )
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("available procedure(s): 3", stderr)

    def test_cross_rom_json_states_its_acceptance_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "jp.objdump"
            candidate = root / "us.objdump"
            target.write_text(
                "0: 3c080123  lui t0,0x123\n4: 25081234  addiu t0,t0,4660\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "0: 3c084567  lui $t0,0x4567\n4: 250889ab  addiu $t0,$t0,-30293\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "compare-dumps",
                    str(target),
                    str(candidate),
                    "--cross-rom",
                    "--fail-on-mismatch",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertFalse(payload["exact"])
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["acceptance_basis"], "cross-rom-structural")

    def test_install_skill_reports_current_on_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            arguments = [
                "install-skill",
                "claude",
                "--destination",
                str(Path(temp) / "skills"),
                "--json",
            ]
            first_status, first_stdout, _ = self.run_cli(arguments)
            second_status, second_stdout, _ = self.run_cli(arguments)
        self.assertEqual(first_status, 0)
        self.assertEqual(json.loads(first_stdout)["status"], "installed")
        self.assertEqual(second_status, 0)
        self.assertEqual(json.loads(second_stdout)["status"], "current")


if __name__ == "__main__":
    unittest.main()
