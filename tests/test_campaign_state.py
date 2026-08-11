"""Persistent campaign cockpit behavior."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.campaign_state import _homologous_guidance, bounded_export_status
from decomp_workbench.cli import main


class CampaignStateTests(unittest.TestCase):
    def test_homologous_guidance_requires_measured_single_parameter_gain(
        self,
    ) -> None:
        manifest = {
            "experiment": {"homologous_parameters": [["first", "second", "third"]]}
        }
        records = [
            {
                "source": "base.c",
                "experiment": {
                    "parameters": {
                        "first": False,
                        "second": False,
                        "third": False,
                    }
                },
                "comparison": {"temp_prefix_exact": 700, "words": 58},
            },
            {
                "source": "first.c",
                "experiment": {
                    "parameters": {
                        "first": True,
                        "second": False,
                        "third": False,
                    }
                },
                # Total score regresses, but causal progress moves later.
                "comparison": {"temp_prefix_exact": 732, "words": 379},
            },
        ]

        guidance = _homologous_guidance(manifest, records)

        self.assertEqual(len(guidance), 2)
        self.assertEqual(
            {item["sibling_parameter"] for item in guidance},
            {"second", "third"},
        )
        self.assertTrue(all(item["prefix_before"] == 700 for item in guidance))
        self.assertTrue(all(item["prefix_after"] == 732 for item in guidance))

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
                    "--rank-by",
                    "temp-prefix",
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
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["execution"]["rank_by"], "temp-prefix")

            status, stdout, stderr = self.run_cli(
                ["campaign", "status", str(manifest.parent), "--json"]
            )
        report = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(report["schema"], "decomp-workbench-campaign-status-v1")
        self.assertEqual(report["rank_by"], "temp-prefix")
        self.assertEqual(report["recorded_candidates"], 1)
        self.assertEqual(report["object_basins"][0]["variant_count"], 1)

    def test_campaign_package_promotes_the_verified_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            source = root / "candidate.c"
            target_assembly = root / "target.s"
            context = root / "ctx.c"
            target.write_bytes(b"target")
            source.write_text("int candidate;\n", encoding="utf-8")
            target_assembly.write_text("jr $ra\n nop\n", encoding="utf-8")
            context.write_text("typedef int s32;\n", encoding="utf-8")
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
                    str(root / "state"),
                    "--json-summary",
                ]
            )
            manifest = Path(json.loads(stdout)["manifest"])
            output = root / "scratch"

            status, stdout, stderr = self.run_cli(
                [
                    "campaign",
                    "package",
                    str(manifest),
                    "--output",
                    str(output),
                    "--target-assembly",
                    str(target_assembly),
                    "--context",
                    str(context),
                    "--platform",
                    "n64",
                    "--compiler",
                    "IDO 5.3",
                    "--compiler-id",
                    "ido5.3",
                    "--language",
                    "C",
                    "--compiler-flags=-O2 -mips2",
                    "--diff-label",
                    "demo",
                    "--json",
                ]
            )

            payload = json.loads(stdout)
            scratch_manifest = json.loads(
                (output / "scratch.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["scratch_accepted"])
            self.assertEqual((output / "source.c").read_bytes(), source.read_bytes())
            self.assertEqual(
                scratch_manifest["provenance"]["campaign_identity"],
                json.loads(manifest.read_text(encoding="utf-8"))["identity"],
            )

    def test_campaign_finish_freshly_rebuilds_and_preserves_not_run_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            source = root / "candidate.c"
            target.write_bytes(b"target")
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler, objdump = self.make_tools(root)
            status, stdout, _ = self.run_cli(
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
                    str(root / "state"),
                    "--json-summary",
                ]
            )
            self.assertEqual(status, 0)
            manifest = Path(json.loads(stdout)["manifest"])
            receipt = root / "finish.json"
            status, _, stderr = self.run_cli(
                [
                    "campaign",
                    "finish",
                    str(manifest),
                    "--output",
                    str(receipt),
                ]
            )
            report = json.loads(receipt.read_text(encoding="utf-8"))
            timeout_script = root / "project-timeout.py"
            timeout_script.write_text(
                "import time\nprint('x' * 200, flush=True)\ntime.sleep(5)\n",
                encoding="utf-8",
            )
            timeout_receipt = root / "finish-timeout.json"
            timeout_status, _, _ = self.run_cli(
                [
                    "campaign",
                    "finish",
                    str(manifest),
                    "--output",
                    str(timeout_receipt),
                    "--project-command",
                    f"{sys.executable} {timeout_script}",
                    "--project-timeout",
                    "0.1",
                    "--stream-limit",
                    "16",
                ]
            )
            timeout_report = json.loads(timeout_receipt.read_text(encoding="utf-8"))
            timeout_artifact = Path(
                timeout_report["gates"]["project_verification"]["evidence"][
                    "artifacts"
                ]["stdout"]
            ).is_file()
            html_receipt = root / "finish.html"
            html_status, _, _ = self.run_cli(
                [
                    "campaign",
                    "finish",
                    str(manifest),
                    "--output",
                    str(html_receipt),
                    "--format",
                    "html",
                ]
            )
            html_document = html_receipt.read_text(encoding="utf-8")

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(report["ready"])
        self.assertEqual(report["gates"]["fresh_function"]["status"], "PASS")
        self.assertEqual(report["gates"]["required_signals"]["status"], "PASS")
        self.assertEqual(report["gates"]["scratch_context"]["status"], "NOT RUN")
        self.assertNotEqual(
            report["winner"]["recorded_object"],
            report["winner"].get("fresh_object"),
        )
        self.assertIsNotNone(report["winner"]["fresh_object_sha256"])
        timeout_evidence = timeout_report["gates"]["project_verification"]["evidence"]
        self.assertEqual(timeout_status, 1)
        self.assertEqual(timeout_evidence["returncode"], 124)
        self.assertTrue(timeout_evidence["stdout_truncated"])
        self.assertGreater(timeout_evidence["stdout_bytes"], 16)
        self.assertTrue(timeout_artifact)
        self.assertEqual(html_status, 0)
        self.assertIn("Machine-readable receipt", html_document)
        self.assertIn("decomp-workbench-campaign-finish-v1", html_document)
        self.assertIn("NOT RUN", html_document)

    def test_campaign_finish_refuses_a_mutated_cached_object_and_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    str(root / "state"),
                    "--json-summary",
                ]
            )
            payload = json.loads(stdout)
            manifest = Path(payload["manifest"])
            receipt = root / "finish.json"
            first_status, _, _ = self.run_cli(
                ["campaign", "finish", str(manifest), "--output", str(receipt)]
            )
            overwrite_status, _, overwrite_error = self.run_cli(
                ["campaign", "finish", str(manifest), "--output", str(receipt)]
            )
            selected_key = payload["results"][0]["cache_key"]
            (root / "cache" / f"{selected_key}.o").write_bytes(b"tampered")
            tamper_status, _, tamper_error = self.run_cli(
                [
                    "campaign",
                    "finish",
                    str(manifest),
                    "--output",
                    str(root / "second.json"),
                ]
            )

        self.assertEqual(first_status, 0)
        self.assertEqual(overwrite_status, 2)
        self.assertIn("refusing to overwrite", overwrite_error)
        self.assertEqual(tamper_status, 2)
        self.assertIn("cached object hash changed", tamper_error)

    def test_campaign_finish_keeps_project_failure_separate_from_function_pass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    str(root / "state"),
                    "--json-summary",
                ]
            )
            manifest = Path(json.loads(stdout)["manifest"])
            receipt = root / "finish-with-project.json"
            status, _, stderr = self.run_cli(
                [
                    "campaign",
                    "finish",
                    str(manifest),
                    "--output",
                    str(receipt),
                    "--project-command",
                    f"{sys.executable} -c 'raise SystemExit(7)'",
                ]
            )
            report = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertFalse(report["ready"])
        self.assertEqual(report["gates"]["fresh_function"]["status"], "PASS")
        self.assertEqual(report["gates"]["project_verification"]["status"], "FAIL")

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

    def test_resume_preserves_v2_candidate_metadata_and_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            target.write_bytes(b"target")
            baseline = root / "baseline.c"
            baseline.write_text("int baseline;\n", encoding="utf-8")
            sources = [root / "first.c", root / "second.c"]
            for index, source in enumerate(sources):
                source.write_text(f"int candidate = {index};\n", encoding="utf-8")
            experiment = root / "experiment.json"
            experiment.write_text(
                json.dumps(
                    {
                        "schema": "decomp-workbench-experiment-v2",
                        "family": "resume-v2",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["first", "second"]},
                        "candidates": [
                            {
                                "source": source.name,
                                "parameters": {"shape": source.stem},
                            }
                            for source in sources
                        ],
                        "signals": [
                            {
                                "id": "tail",
                                "kind": "target-rows-exact",
                                "rows": [1],
                                "required": True,
                            }
                        ],
                        "coverage": {"method": "exhaustive", "excluded": 0},
                    }
                ),
                encoding="utf-8",
            )
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
                    str(root / "state"),
                    "--experiment-manifest",
                    str(experiment),
                    "--json-summary",
                ]
            )
            payload = json.loads(stdout)
            manifest = Path(payload["manifest"])
            ledger = Path(payload["ledger"])
            resumed, _, stderr = self.run_cli(
                [
                    "campaign",
                    "resume",
                    str(manifest),
                    "--continue-after-exact",
                ]
            )
            records = [
                json.loads(line)
                for line in ledger.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(resumed, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(records), 2)
        self.assertEqual(
            records[1]["experiment"]["schema"],
            "decomp-workbench-experiment-v2",
        )
        self.assertEqual(records[1]["experiment"]["signals"], ["tail"])
        self.assertEqual(records[1]["signals"][0]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
