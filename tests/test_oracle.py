"""Oracle plans are phase-complete, measured, and explicitly diagnostic."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.globalcolor import parse_globalcolor_trace
from decomp_workbench.model import CompileResult, Instruction
from decomp_workbench.oracle import oracle_diff, oracle_plan, run_oracle_campaign
from decomp_workbench.source_stamp import STAMP_KEY, stamp_sources

TRACE = """
[CDX] webdetail proc=7 web=9 role=target dtype=13 bb=4 defbb=4 usebbs=5 line=20
[CDX] p1cost phase=p1 proc=7 web=9 color=1 cost=1
[CDX] p1cost phase=p1 proc=7 web=9 color=2 cost=2
[CDX] p1dec phase=p1 proc=7 web=9 bestcolor=1 forbidden0=0x40000000 forbidden1=0
[CDX] webdetail proc=7 web=55 role=target dtype=13 bb=8 defbb=8 usebbs=9 line=40
[CDX] p2cost phase=p2 proc=7 web=55 color=1 cost=1
[CDX] p2cost phase=p2 proc=7 web=55 color=2 cost=2
[CDX] p2dec phase=p2 proc=7 web=55 bestcolor=2 forbidden0=0 forbidden1=0
"""


class OracleTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_plan_reports_both_phases_and_omits_forbidden_colors(self) -> None:
        report = oracle_plan(parse_globalcolor_trace(TRACE))
        forces = {item["force"] for item in report["forces"]}
        self.assertTrue(report["both_phases_reported"])
        self.assertEqual(report["coverage"]["p1"]["webs"], 1)
        self.assertEqual(report["coverage"]["p2"]["webs"], 1)
        self.assertNotIn("p1:w9=c1", forces)
        self.assertIn("p1:w9=c2", forces)
        self.assertIn("p1:w9=s", forces)
        self.assertIn("p2:w55=c1", forces)

    def test_absent_phase_is_visible_instead_of_silently_exonerated(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] p1cost proc=3 web=9 color=1 cost=1\n"
            "[CDX] p1dec proc=3 web=9 bestcolor=1 forbidden0=0 forbidden1=0\n"
        )
        report = oracle_plan(trace)
        self.assertEqual(report["coverage"]["p2"]["webs"], 0)
        self.assertIn("p2: 0 allocator webs recorded", report["warnings"])

    def test_plan_with_only_run_local_trace_evidence_withholds_source_advice(
        self,
    ) -> None:
        report = oracle_plan(parse_globalcolor_trace(TRACE))
        attribution = report["source_attribution"]
        self.assertEqual(attribution["classification"], "run-local-unattributed")
        self.assertEqual(attribution["source_experiment_recommendations"], [])
        self.assertIn("source_semantic", attribution["next_gate"])
        self.assertTrue(
            all(
                row["source_attribution"]["classification"] == "run-local-unattributed"
                for row in report["forces"]
            )
        )

    def test_plan_recommends_source_experiment_only_for_direct_semantic(
        self,
    ) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=7 phase=p1 web=9 snapshot=preselect "
            "source_semantic=local:flag semantic_reason=ir-local\n"
            "[CDX] provenance_web proc=7 phase=p1 web=9 snapshot=postselect "
            "source_semantic=local:flag semantic_reason=ir-local\n" + TRACE
        )
        report = oracle_plan(trace)
        recommendations = report["source_attribution"][
            "source_experiment_recommendations"
        ]
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["source_semantic"], "local:flag")

    def test_semantic_diff_does_not_align_on_numeric_web_id(self) -> None:
        target = parse_globalcolor_trace(TRACE)
        candidate = parse_globalcolor_trace(
            TRACE.replace("web=55", "web=155").replace(
                "bestcolor=2 forbidden0=0",
                "bestcolor=1 forbidden0=0",
            )
        )
        report = oracle_diff(target, candidate, proc=7)
        self.assertEqual(report["difference_count"], 1)
        row = report["semantic"]["differences"][0]
        self.assertIn("assigned_color", row["changed"])
        self.assertNotEqual(
            row["target"]["numeric_web"],
            row["candidate"]["numeric_web"],
        )

    def test_sweep_reuses_campaign_truth_and_labels_force_exact_as_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "candidate.c"
            target = root / "target.o"
            source.write_text("int demo;\n", encoding="utf-8")
            target.write_bytes(b"target")
            compiler = root / "compile.py"
            compiler.write_text(
                "import os, pathlib, sys\n"
                "value = b'exact' if os.environ.get('CDX_FORCE') == "
                "'p2:w55=c2' else b'baseline'\n"
                "pathlib.Path(sys.argv[2]).write_bytes(value)\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "obj = next(pathlib.Path(arg) for arg in sys.argv[1:] "
                "if pathlib.Path(arg).suffix == '.o')\n"
                "value = obj.read_bytes()\n"
                "print('00000000 <demo>:')\n"
                "if value in {b'target', b'exact'}:\n"
                " print('   0: 03e00008  jr $ra')\n"
                "else:\n"
                " print('   0: 00001021  move $v0,$zero')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            plan = {
                **oracle_plan(parse_globalcolor_trace(TRACE)),
                "forces": [
                    {
                        "force": "p1:w9=c2",
                        "phase": "p1",
                        "web": 9,
                        "color": 2,
                        "register": "v1",
                    },
                    {
                        "force": "p2:w55=c2",
                        "phase": "p2",
                        "web": 55,
                        "color": 2,
                        "register": "v1",
                    },
                ],
            }
            report = run_oracle_campaign(
                plan,
                source=source,
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                environment={},
                cache_dir=root / "cache",
                ledger=root / "oracle.jsonl",
                jobs=2,
                objdump=str(objdump),
                symbol="demo",
                keep_objects=root / "objects",
            )
            cached_report = run_oracle_campaign(
                plan,
                source=source,
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                environment={},
                cache_dir=root / "cache",
                ledger=root / "oracle.jsonl",
                jobs=2,
                objdump=str(objdump),
                symbol="demo",
                keep_objects=root / "objects",
            )
            ledger_records = (
                (root / "oracle.jsonl").read_text(encoding="utf-8").splitlines()
            )
        self.assertEqual(report["exact_forces"], ["p2:w55=c2"])
        self.assertEqual(report["minimum_forces_to_exact"], 1)
        self.assertEqual(report["signature"], "one-force-exact(p2:w55=c2)")
        self.assertIn("never an acceptable source match", report["proof"])
        exact_row = next(
            row for row in report["results"] if row["force"] == "p2:w55=c2"
        )
        self.assertTrue(exact_row["emitted_effect"]["available"])
        self.assertEqual(exact_row["emitted_effect"]["changed_site_count"], 1)
        self.assertIn(
            "not source_semantic",
            exact_row["emitted_effect"]["proof_boundary"],
        )
        self.assertTrue(all(row["cached"] for row in cached_report["results"]))
        self.assertTrue(cached_report["baseline"]["cached"])
        self.assertEqual(len(ledger_records), 3)

    def test_exact_force_is_withheld_without_a_nonexact_control(self) -> None:
        instruction = Instruction(0, "03e00008", "jr $ra")
        exact = compare_instructions(
            [instruction],
            [instruction],
            target_name="target",
            candidate_name="forced",
            symbol=None,
        )
        baseline = CompileResult(
            source="candidate.c",
            command=[],
            returncode=1,
            stdout="",
            stderr="baseline failed",
            object_path=None,
            comparison=None,
            experiment={"baseline": True, "force": None},
        )
        forced = CompileResult(
            source="candidate.c",
            command=[],
            returncode=0,
            stdout="",
            stderr="",
            object_path="forced.o",
            comparison=exact,
            experiment={
                "baseline": False,
                "force": "p2:w55=c2",
                "phase": "p2",
                "web": 55,
                "color": 2,
                "register": "v1",
            },
        )
        plan = {
            "schema": "decomp-workbench-oracle-plan-v1",
            "procedure": 7,
            "coverage": {},
            "forces": [
                {
                    "force": "p2:w55=c2",
                    "phase": "p2",
                    "web": 55,
                    "color": 2,
                    "register": "v1",
                }
            ],
        }
        with mock.patch(
            "decomp_workbench.oracle.run_parameterized_campaign",
            return_value=[baseline, forced],
        ):
            report = run_oracle_campaign(
                plan,
                source="candidate.c",
                target="target.o",
                template="compiler {source} {output}",
                environment={},
                cache_dir="cache",
            )
        self.assertFalse(report["control_valid"])
        self.assertEqual(report["observed_exact_forces"], ["p2:w55=c2"])
        self.assertEqual(report["exact_forces"], [])
        self.assertIsNone(report["signature"])
        self.assertIn("not causal", report["warnings"][0])

    def test_exact_force_set_reports_its_actual_cardinality(self) -> None:
        target = Instruction(0, "03e00008", "jr $ra")
        mismatch = Instruction(0, "00001021", "move $v0,$zero")
        baseline_comparison = compare_instructions(
            [target],
            [mismatch],
            target_name="target",
            candidate_name="baseline",
            symbol=None,
        )
        exact_comparison = compare_instructions(
            [target],
            [target],
            target_name="target",
            candidate_name="forced",
            symbol=None,
        )
        components = [
            {"force": "p1:w9=c2", "phase": "p1", "web": 9, "color": 2},
            {"force": "p2:w55=c1", "phase": "p2", "web": 55, "color": 1},
        ]
        baseline = CompileResult(
            source="candidate.c",
            command=[],
            returncode=0,
            stdout="",
            stderr="",
            object_path=None,
            comparison=baseline_comparison,
            experiment={"baseline": True, "force": None},
        )
        forced = CompileResult(
            source="candidate.c",
            command=[],
            returncode=0,
            stdout="",
            stderr="",
            object_path=None,
            comparison=exact_comparison,
            experiment={
                "baseline": False,
                "force": "p1:w9=c2,p2:w55=c1",
                "phase": "combined",
                "components": components,
            },
        )
        plan = {
            "schema": "decomp-workbench-oracle-plan-v1",
            "procedure": 7,
            "coverage": {},
            "forces": [
                {
                    "force": "p1:w9=c2,p2:w55=c1",
                    "phase": "combined",
                    "web": None,
                    "color": None,
                    "register": "v1,v0",
                    "components": components,
                }
            ],
        }
        with mock.patch(
            "decomp_workbench.oracle.run_parameterized_campaign",
            return_value=[baseline, forced],
        ):
            report = run_oracle_campaign(
                plan,
                source="candidate.c",
                target="target.o",
                template="compiler {source} {output}",
                environment={},
                cache_dir="cache",
            )

        self.assertEqual(report["minimum_forces_to_exact"], 2)
        self.assertEqual(report["signature"], "force-set-exact(p1:w9=c2,p2:w55=c1)")

    def test_force_cli_accepts_a_validated_multi_web_interaction(self) -> None:
        arguments = argparse.Namespace(
            trace="trace.log",
            proc=None,
            colors_p1=None,
            colors_p2=None,
            no_split=False,
            force="p1:w9=c2,p2:w55=c1",
        )
        with mock.patch(
            "decomp_workbench.oracle_cli._load",
            return_value=parse_globalcolor_trace(TRACE),
        ):
            from decomp_workbench.oracle_cli import _plan_for_compile

            selected = _plan_for_compile(arguments)
        self.assertEqual(selected["force_count"], 1)
        row = selected["forces"][0]
        self.assertEqual(row["phase"], "combined")
        self.assertEqual(len(row["components"]), 2)
        self.assertEqual(row["force"], "p1:w9=c2,p2:w55=c1")

    def test_force_cli_rejects_duplicate_phase_web_in_interaction(self) -> None:
        arguments = argparse.Namespace(
            trace="trace.log",
            proc=None,
            colors_p1=None,
            colors_p2=None,
            no_split=False,
            force="p1:w9=c2,p1:w9=s",
        )
        with mock.patch(
            "decomp_workbench.oracle_cli._load",
            return_value=parse_globalcolor_trace(TRACE),
        ):
            from decomp_workbench.oracle_cli import _plan_for_compile

            with self.assertRaisesRegex(ValueError, "same phase/web"):
                _plan_for_compile(arguments)

    def test_persisted_status_and_exclusive_html_export_need_no_toolchain(
        self,
    ) -> None:
        report = {
            "schema": "decomp-workbench-oracle-sweep-v1",
            "completed_forces": 1,
            "planned_forces": 1,
            "baseline": {"comparison": {"words": 2}},
            "results": [
                {
                    "force": "p2:w55=c2",
                    "register": "v1",
                    "returncode": 0,
                    "comparison": {
                        "exact": True,
                        "words": 0,
                        "aligned_total": 0,
                    },
                }
            ],
            "signature": "one-force-exact(p2:w55=c2)",
            "proof": "Forced compiler output is causal evidence only.",
            "state": {
                "directory": "/state/oracle/demo",
                "ledger": "/state/oracle/demo/ledger.jsonl",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "oracle-state"
            state.mkdir()
            report_path = state / "report.json"
            # A current report is stamped with the source it compiled; the
            # stamp is what lets `status`/`export` read it without a warning.
            source = root / "candidate.c"
            source.write_text("int f(void) { return 0; }\n", encoding="utf-8")
            report[STAMP_KEY] = stamp_sources([source]).as_dict()
            report_path.write_text(json.dumps(report), encoding="utf-8")
            status, stdout, stderr = self.run_cli(
                ["oracle", "status", str(state), "--json"]
            )
            output = root / "oracle.html"
            exported, _, export_stderr = self.run_cli(
                [
                    "oracle",
                    "export",
                    str(state),
                    "--output",
                    str(output),
                ]
            )
            document = output.read_text(encoding="utf-8")
            repeated, _, repeated_stderr = self.run_cli(
                [
                    "oracle",
                    "export",
                    str(state),
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout)["signature"],
            "one-force-exact(p2:w55=c2)",
        )
        self.assertEqual(exported, 0)
        self.assertEqual(export_stderr, "")
        self.assertIn("<!doctype html>", document)
        self.assertIn("Machine-readable evidence", document)
        self.assertIn('<a class="skip-link" href="#main-content">', document)
        self.assertIn('<main id="main-content">', document)
        self.assertIn("<details open>", document)
        self.assertIn("<caption>", document)
        self.assertNotIn("https://", document)
        self.assertEqual(repeated, 2)
        self.assertIn("refusing to overwrite", repeated_stderr)


class OracleSourceStampTests(unittest.TestCase):
    """Backlog item 20: a persisted force grid is refused once its source moves."""

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def write_report(self, root: Path, *, stamped: bool = True) -> tuple[Path, Path]:
        source = root / "candidate.c"
        source.write_text("int f(void) { return 1; }\n", encoding="utf-8")
        report: dict[str, object] = {
            "schema": "decomp-workbench-oracle-sweep-v1",
            "completed_forces": 0,
            "planned_forces": 0,
            "baseline": None,
            "results": [],
            "signature": None,
            "proof": "Forced compiler output is causal evidence only.",
        }
        if stamped:
            report[STAMP_KEY] = stamp_sources([source]).as_dict()
        state = root / "state"
        state.mkdir()
        (state / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return state, source

    def test_a_sweep_writes_the_digest_it_compiled_as_its_stamp(self) -> None:
        from decomp_workbench import oracle_cli

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "candidate.c"
            source.write_text("int f(void) { return 1; }\n", encoding="utf-8")
            # The identity block hashed the source before compiling; the stamp
            # must carry that digest, not a re-read taken afterwards.
            measured = "a" * 64
            state = oracle_cli.OracleStatePaths(
                root=root / "state",
                ledger=root / "state" / "ledger.jsonl",
                objects=root / "state" / "objects",
                report=root / "state" / "report.json",
                identity={"source": {"path": str(source), "sha256": measured}},
            )
            arguments = argparse.Namespace(
                env=[],
                toolchain="tc",
                source=str(source),
                target="t.o",
                compile_command="cc",
                cache_dir="c",
                jobs=1,
                objdump=None,
                symbol=None,
                section=".text",
                compile_cwd=None,
                no_keep_objects=True,
                timeout=1.0,
                stream_limit=1,
                artifact_dir=None,
                json=True,
                limit=5,
            )
            campaign = {"control_valid": True, "results": []}
            with (
                mock.patch.object(oracle_cli, "_plan_for_compile", return_value={}),
                mock.patch.object(
                    oracle_cli, "merge_toolchain_environment", return_value={}
                ),
                mock.patch.object(oracle_cli, "_state_paths", return_value=state),
                mock.patch.object(
                    oracle_cli, "run_oracle_campaign", return_value=campaign
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                oracle_cli.oracle_sweep_command(arguments)
            written = json.loads(state.report.read_text(encoding="utf-8"))
        stamp = written[STAMP_KEY]
        self.assertEqual(stamp["stamp_schema"], "decomp-workbench-source-stamp-v1")
        self.assertEqual(
            stamp["sources"],
            [{"path": str(source.resolve()), "sha256": measured}],
        )

    def test_a_fresh_report_carries_its_verdict_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state, _ = self.write_report(Path(temporary))
            status, stdout, _ = self.run_cli(["oracle", "status", str(state), "--json"])
        self.assertEqual(status, 0)
        block = json.loads(stdout)["source_freshness"]
        self.assertEqual(block["status"], "fresh")
        self.assertFalse(block["refused"])

    def test_an_edited_source_refuses_the_report_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state, source = self.write_report(Path(temporary))
            source.write_text("int f(void) { return 2; }\n", encoding="utf-8")
            status, stdout, stderr = self.run_cli(["oracle", "status", str(state)])
            json_status, json_out, _ = self.run_cli(
                ["oracle", "status", str(state), "--json"]
            )
            output = Path(temporary) / "out.html"
            exported, _, export_stderr = self.run_cli(
                ["oracle", "export", str(state), "--output", str(output)]
            )
            self.assertFalse(output.exists())
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("STALE:", stderr)
        self.assertIn("--allow-stale-source", stderr)
        self.assertEqual(json_status, 2)
        self.assertIn("STALE:", json.loads(json_out)["error"]["message"])
        self.assertEqual(exported, 2)
        self.assertIn("STALE:", export_stderr)

    def test_allow_stale_source_reads_it_and_still_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state, source = self.write_report(Path(temporary))
            source.write_text("int f(void) { return 2; }\n", encoding="utf-8")
            status, _, stderr = self.run_cli(
                ["oracle", "status", str(state), "--allow-stale-source"]
            )
            json_status, json_out, _ = self.run_cli(
                ["oracle", "status", str(state), "--allow-stale-source", "--json"]
            )
        self.assertEqual(status, 0)
        self.assertIn("WARNING: STALE:", stderr)
        self.assertEqual(json_status, 0)
        block = json.loads(json_out)["source_freshness"]
        self.assertEqual(block["status"], "stale")
        self.assertTrue(block["allowed_stale"])
        self.assertFalse(block["refused"])

    def test_a_pre_stamp_report_is_checked_through_its_recorded_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state, source = self.write_report(root, stamped=False)
            report_path = state / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["inputs"] = {
                "source": {"path": str(source), "sha256": "0" * 64},
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            status, _, stderr = self.run_cli(["oracle", "status", str(state)])
        self.assertEqual(status, 2)
        self.assertIn("STALE:", stderr)

    def test_an_unstamped_report_is_read_with_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state, _ = self.write_report(Path(temporary), stamped=False)
            status, _, stderr = self.run_cli(["oracle", "status", str(state)])
        self.assertEqual(status, 0)
        self.assertIn("carries no source stamp", stderr)

    def test_stamped_source_checks_a_moved_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state, source = self.write_report(root)
            moved = root / "elsewhere.c"
            moved.write_bytes(source.read_bytes())
            source.unlink()
            unknown, _, unknown_stderr = self.run_cli(["oracle", "status", str(state)])
            fresh, _, fresh_stderr = self.run_cli(
                ["oracle", "status", str(state), "--stamped-source", str(moved)]
            )
        self.assertEqual(unknown, 0)
        self.assertIn("cannot be read here", unknown_stderr)
        self.assertEqual(fresh, 0)
        self.assertEqual(fresh_stderr, "")


if __name__ == "__main__":
    unittest.main()
