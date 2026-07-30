"""Persistent campaign cockpit behavior."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.campaign_state import bounded_export_status
from decomp_workbench.cli import main


class CampaignStateTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def make_tools(self, root: Path) -> tuple[Path, Path]:
        compiler = root / "compile.py"
        compiler.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
            encoding="utf-8",
        )
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "print('00000000 <demo>:')\n"
            "print('   0: 03e00008  jr $ra')\n"
            "print('   4: 00000000  nop')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        return compiler, objdump

    def test_campaign_creates_default_manifest_ledger_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            target = root / "target.o"
            source = root / "candidate.c"
            target.write_bytes(b"target")
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler, objdump = self.make_tools(root)
            status, stdout, stderr = self.run_cli(
                [
                    "campaign",
                    str(target),
                    str(source),
                    "--compile-command",
                    f"{sys.executable} {compiler} {{source}} {{output}}",
                    "--objdump",
                    str(objdump),
                    "--symbol",
                    "demo",
                    "--cache-dir",
                    str(root / "cache"),
                    "--state-dir",
                    str(state),
                    "--json-summary",
                ]
            )
            payload = json.loads(stdout)
            manifest = Path(payload["manifest"])
            ledger = Path(payload["ledger"])
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(manifest.is_file())
            self.assertTrue(ledger.is_file())

            status, stdout, stderr = self.run_cli(
                ["campaign", "status", str(manifest.parent), "--json"]
            )
        report = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(report["schema"], "decomp-workbench-campaign-status-v1")
        self.assertEqual(report["recorded_candidates"], 1)
        self.assertEqual(report["object_basins"][0]["variant_count"], 1)

    def test_campaign_note_survives_as_handoff_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            target = root / "target.o"
            source = root / "candidate.c"
            target.write_bytes(b"target")
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler, objdump = self.make_tools(root)
            _, stdout, _ = self.run_cli(
                [
                    "campaign",
                    str(target),
                    str(source),
                    "--compile-command",
                    f"{sys.executable} {compiler} {{source}} {{output}}",
                    "--objdump",
                    str(objdump),
                    "--symbol",
                    "demo",
                    "--cache-dir",
                    str(root / "cache"),
                    "--state-dir",
                    str(state),
                    "--json-summary",
                ]
            )
            manifest = Path(json.loads(stdout)["manifest"])
            status, _, stderr = self.run_cli(
                [
                    "campaign",
                    "note",
                    "padding loop line markers remain the active hypothesis",
                    str(manifest),
                ]
            )
            _, stdout, _ = self.run_cli(["campaign", "status", str(manifest), "--json"])
        report = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            report["hypothesis"],
            "padding loop line markers remain the active hypothesis",
        )

    def test_campaign_export_is_self_contained_html(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            target = root / "target.o"
            source = root / "candidate.c"
            target.write_bytes(b"target")
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler, objdump = self.make_tools(root)
            _, stdout, _ = self.run_cli(
                [
                    "campaign",
                    str(target),
                    str(source),
                    "--compile-command",
                    f"{sys.executable} {compiler} {{source}} {{output}}",
                    "--objdump",
                    str(objdump),
                    "--symbol",
                    "demo",
                    "--cache-dir",
                    str(root / "cache"),
                    "--state-dir",
                    str(state),
                    "--json-summary",
                ]
            )
            manifest = Path(json.loads(stdout)["manifest"])
            output = root / "report.html"
            status, _, stderr = self.run_cli(
                [
                    "campaign",
                    "export",
                    str(manifest),
                    "--output",
                    str(output),
                ]
            )
            document = output.read_text(encoding="utf-8")
            second_status, _, second_stderr = self.run_cli(
                [
                    "campaign",
                    "export",
                    str(manifest),
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("<!doctype html>", document)
        self.assertIn("Machine-readable evidence", document)
        self.assertNotIn("https://", document)
        self.assertEqual(second_status, 2)
        self.assertIn("refusing to overwrite", second_stderr)

    def test_shareable_export_bounds_long_histories_explicitly(self) -> None:
        status = {
            "trajectory": [{"record": index} for index in range(2101)],
            "basin_transitions": [{"record": index} for index in range(2102)],
            "failures": [{"source": str(index)} for index in range(300)],
            "object_basins": [
                {
                    "candidate_sha256": "a" * 64,
                    "variant_count": 300,
                    "sources": [f"candidate-{index}.c" for index in range(300)],
                }
            ],
        }
        bounded = bounded_export_status(status)
        self.assertEqual(len(bounded["trajectory"]), 2000)
        self.assertEqual(bounded["trajectory"][0]["record"], 0)
        self.assertEqual(bounded["trajectory"][-1]["record"], 2100)
        self.assertEqual(len(bounded["basin_transitions"]), 2000)
        self.assertEqual(len(bounded["failures"]), 256)
        self.assertEqual(len(bounded["object_basins"][0]["sources"]), 256)
        self.assertTrue(bounded["object_basins"][0]["sources_truncated"])
        self.assertEqual(
            bounded["export_bounds"]["object_basin_sources"],
            {"total": 300, "included": 256, "truncated": True},
        )

    def test_resume_preserves_an_exact_stop_unless_explicitly_continued(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            target = root / "target.o"
            target.write_bytes(b"target")
            sources = []
            for index in range(2):
                source = root / f"candidate-{index}.c"
                source.write_text(f"int candidate = {index};\n", encoding="utf-8")
                sources.append(source)
            compiler, objdump = self.make_tools(root)
            _, stdout, _ = self.run_cli(
                [
                    "campaign",
                    str(target),
                    *(str(source) for source in sources),
                    "--compile-command",
                    f"{sys.executable} {compiler} {{source}} {{output}}",
                    "--objdump",
                    str(objdump),
                    "--symbol",
                    "demo",
                    "--jobs",
                    "1",
                    "--cache-dir",
                    str(root / "cache"),
                    "--state-dir",
                    str(state),
                    "--json-summary",
                ]
            )
            manifest = Path(json.loads(stdout)["manifest"])
            ledger = Path(json.loads(stdout)["ledger"])
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)

            status, stdout, stderr = self.run_cli(["campaign", "resume", str(manifest)])
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)
            self.assertIn("exact result already recorded", stdout)

            continued, _, continued_stderr = self.run_cli(
                [
                    "campaign",
                    "resume",
                    str(manifest),
                    "--continue-after-exact",
                ]
            )
            final_records = ledger.read_text(encoding="utf-8").splitlines()
            _, final_stdout, _ = self.run_cli(
                ["campaign", "status", str(manifest), "--json"]
            )
            final_status = json.loads(final_stdout)["status"]
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(continued, 0)
        self.assertEqual(continued_stderr, "")
        self.assertEqual(len(final_records), 2)
        self.assertEqual(final_status, "exact")


if __name__ == "__main__":
    unittest.main()
