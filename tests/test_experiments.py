"""Experiment sidecars make family, parameters, and invariants durable."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.campaign import region_score
from decomp_workbench.campaign_cli import _compact_parameter_evidence
from decomp_workbench.campaign_state import build_status
from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.experiment_signals import evaluate_signals
from decomp_workbench.experiments import (
    EXPERIMENT_SCHEMA,
    EXPERIMENT_SCHEMA_V2,
    RegionConstraint,
    SignalSpec,
    expected_parameter_combinations,
    load_experiment,
)
from decomp_workbench.objdump import parse_disassembly


class ExperimentTests(unittest.TestCase):
    def test_v2_parses_signals_controls_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.c"
            baseline.write_text("int baseline;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA_V2,
                        "family": "controlled-family",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["base"]},
                        "candidates": [
                            {"source": "baseline.c", "parameters": {"shape": "base"}}
                        ],
                        "signals": [
                            {
                                "id": "tail",
                                "kind": "target-rows-exact",
                                "rows": [1],
                                "required": True,
                            }
                        ],
                        "controls": [
                            {
                                "id": "baseline",
                                "candidate": "baseline.c",
                                "expect": {"words": 0, "signals": {"tail": "PASS"}},
                            }
                        ],
                        "coverage": {"method": "exhaustive", "excluded": 0},
                    }
                ),
                encoding="utf-8",
            )
            manifest = load_experiment(path)
        self.assertEqual(manifest.schema, EXPERIMENT_SCHEMA_V2)
        self.assertEqual(manifest.signals[0].id, "tail")
        self.assertEqual(manifest.controls[0].kind, "absolute")
        self.assertEqual(manifest.coverage["method"], "exhaustive")

    def test_v1_rejects_v2_fields_with_a_migration_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "baseline.c").write_text("int baseline;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "wrong-version",
                        "baseline": "baseline.c",
                        "signals": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, EXPERIMENT_SCHEMA_V2):
                load_experiment(path)

    def test_v2_identity_tracks_control_source_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "baseline.c"
            source.write_text("int baseline = 1;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA_V2,
                        "family": "source-hash",
                        "baseline": "baseline.c",
                        "controls": [
                            {
                                "id": "baseline",
                                "candidate": "baseline.c",
                                "expect": {"returncode": 0},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            first = load_experiment(path).identity_receipt()
            source.write_text("int baseline = 2;\n", encoding="utf-8")
            second = load_experiment(path).identity_receipt()

        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_coverage_refuses_unexplained_or_impossible_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "baseline.c").write_text("int baseline;\n", encoding="utf-8")
            path = root / "experiment.json"
            base = {
                "schema": EXPERIMENT_SCHEMA_V2,
                "family": "coverage",
                "baseline": "baseline.c",
                "parameters": {"shape": ["a", "b"]},
            }
            for coverage, message in (
                ({"excluded": 1}, "exclusion_reason"),
                (
                    {"excluded": 3, "exclusion_reason": "impossible cells"},
                    "cannot exceed",
                ),
            ):
                path.write_text(
                    json.dumps({**base, "coverage": coverage}), encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, message):
                    load_experiment(path)

    def test_v2_coverage_requires_complete_disjoint_candidate_cells(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("baseline.c", "candidate.c"):
                (root / name).write_text("int value;\n", encoding="utf-8")
            path = root / "experiment.json"
            base = {
                "schema": EXPERIMENT_SCHEMA_V2,
                "family": "coverage-cells",
                "baseline": "baseline.c",
                "parameters": {"shape": ["a", "b"], "flag": [False, True]},
            }
            path.write_text(
                json.dumps(
                    {
                        **base,
                        "candidates": [
                            {"source": "candidate.c", "parameters": {"shape": "a"}}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "assign every"):
                load_experiment(path)

            path.write_text(
                json.dumps(
                    {
                        **base,
                        "candidates": [
                            {
                                "source": "candidate.c",
                                "parameters": {"shape": "a", "flag": False},
                            }
                        ],
                        "coverage": {
                            "excluded": 4,
                            "exclusion_reason": "declared impossible",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "overlap or exceed"):
                load_experiment(path)

    def test_coverage_labels_distinguish_sampled_exhaustive_and_interrupted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            target.write_bytes(b"target")

            def report(status: str, visited: list[str]) -> dict[str, Any]:
                ledger = root / f"{status}-{len(visited)}.jsonl"
                ledger.write_text(
                    "".join(
                        json.dumps(
                            {
                                "cache_key": value,
                                "source": f"{value}.c",
                                "experiment": {
                                    "family": "coverage",
                                    "parameters": {"shape": value},
                                    "parameter_space": {"shape": ["a", "b"]},
                                },
                                "comparison": {
                                    "candidate": value,
                                    "candidate_sha256": value * 64,
                                    "aligned_total": 0,
                                    "words": 0,
                                    "verdict": "instruction-exact",
                                },
                            }
                        )
                        + "\n"
                        for value in visited
                    ),
                    encoding="utf-8",
                )
                manifest = root / f"{status}-{len(visited)}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "schema": "decomp-workbench-campaign-manifest-v1",
                            "identity": "identity",
                            "status": status,
                            "identity_inputs": {
                                "target": {
                                    "path": str(target),
                                    "sha256": "unused",
                                },
                                "symbol": "demo",
                            },
                            "ledger": str(ledger),
                            "sources": [
                                {"path": f"{value}.c", "cache_key": value}
                                for value in ("a", "b")
                            ],
                            "experiment": {
                                "schema": EXPERIMENT_SCHEMA_V2,
                                "family": "coverage",
                                "parameters": {"shape": ["a", "b"]},
                                "coverage": {
                                    "method": "exhaustive",
                                    "excluded": 0,
                                },
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return build_status(manifest)

            sampled = report("complete", ["a"])
            exhaustive = report("complete", ["a", "b"])
            interrupted = report("interrupted", ["a"])

        self.assertEqual(sampled["conclusion_label"], "sampled-over-declared-space")
        self.assertEqual(
            exhaustive["conclusion_label"], "exhaustive-over-declared-space"
        )
        self.assertEqual(interrupted["conclusion_label"], "partial-interrupted")

    def test_target_relative_signal_survives_an_insertion_before_its_row(self) -> None:
        target = parse_disassembly(
            "0: 24020001 li $v0,1\n4: 24030002 li $v1,2\n8: 03e00008 jr $ra\n"
        )
        candidate = parse_disassembly(
            "0: 00000000 nop\n"
            "4: 24020001 li $v0,1\n"
            "8: 24030002 li $v1,2\n"
            "c: 03e00008 jr $ra\n"
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        receipts = evaluate_signals(
            (
                SignalSpec(
                    "tail",
                    "target-rows-exact",
                    True,
                    {"rows": [1, 2], "comparison": "raw"},
                ),
            ),
            comparison,
        )
        self.assertEqual(receipts[0]["status"], "PASS")
        self.assertEqual(receipts[0]["failed_rows"], [])

    def test_target_row_signal_does_not_pass_on_the_same_word_elsewhere(self) -> None:
        target = parse_disassembly(
            "0: 24020001 li $v0,1\n4: 24030002 li $v1,2\n8: 03e00008 jr $ra\n"
        )
        candidate = parse_disassembly(
            "0: 24030002 li $v1,2\n4: 24020001 li $v0,1\n8: 03e00008 jr $ra\n"
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        receipt = evaluate_signals(
            (
                SignalSpec(
                    "row-zero",
                    "target-rows-exact",
                    True,
                    {"rows": [0], "comparison": "raw"},
                ),
            ),
            comparison,
        )[0]
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["failed_rows"], [0])

    def _controlled_campaign(
        self, *, expected_words: int, baseline_fails: bool = False
    ) -> tuple[int, dict[str, Any], list[str]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            baseline = root / "baseline.c"
            candidate = root / "candidate.c"
            log = root / "compiled.log"
            target.write_bytes(b"target")
            baseline.write_text("baseline\n", encoding="utf-8")
            candidate.write_text("candidate\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "source, output, log = map(pathlib.Path, sys.argv[1:4])\n"
                "with log.open('a', encoding='utf-8') as stream:\n"
                "    stream.write(source.name + '\\n')\n"
                + (
                    "if source.name == 'baseline.c':\n    raise SystemExit(9)\n"
                    if baseline_fails
                    else ""
                )
                + "output.write_bytes(source.read_bytes())\n",
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
            experiment = root / "experiment.json"
            experiment.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA_V2,
                        "family": "controlled",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["candidate"]},
                        "candidates": [
                            {
                                "source": "candidate.c",
                                "parameters": {"shape": "candidate"},
                            }
                        ],
                        "signals": [
                            {
                                "id": "tail",
                                "kind": "target-rows-exact",
                                "rows": [1],
                                "required": True,
                            }
                        ],
                        "controls": [
                            {
                                "id": "baseline",
                                "candidate": "baseline.c",
                                "expect": {
                                    "words": expected_words,
                                    "signals": {"tail": "PASS"},
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "campaign",
                        str(target),
                        str(candidate),
                        "--compile-command",
                        f"{sys.executable} {compiler} {{source}} {{output}} {log}",
                        "--objdump",
                        str(objdump),
                        "--symbol",
                        "demo",
                        "--cache-dir",
                        str(root / "cache"),
                        "--state-dir",
                        str(root / "state"),
                        "--experiment-manifest",
                        str(experiment),
                        "--json-summary",
                    ]
                )
            payload = json.loads(stdout.getvalue())
            compiled = log.read_text(encoding="utf-8").splitlines()
        return status, payload, compiled

    def test_failed_control_schedules_zero_ordinary_candidates(self) -> None:
        status, payload, compiled = self._controlled_campaign(expected_words=1)
        self.assertEqual(status, 2)
        self.assertEqual(payload["status"], "control-invalid")
        self.assertEqual(payload["unique_candidates"], 0)
        self.assertEqual(compiled, ["baseline.c"])

    def test_passing_control_precedes_work_and_signals_reach_results(self) -> None:
        status, payload, compiled = self._controlled_campaign(expected_words=0)
        self.assertEqual(status, 0)
        self.assertEqual(payload["controls"]["status"], "PASS")
        self.assertEqual(compiled, ["baseline.c", "candidate.c"])
        self.assertEqual(payload["results"][0]["signals"][0]["status"], "PASS")

    def test_unknown_required_control_schedules_zero_ordinary_candidates(self) -> None:
        status, payload, compiled = self._controlled_campaign(
            expected_words=0, baseline_fails=True
        )
        self.assertEqual(status, 2)
        self.assertEqual(payload["controls"]["receipts"][0]["status"], "UNKNOWN")
        self.assertEqual(compiled, ["baseline.c"])

    def test_differential_control_catches_an_ignored_knob_before_scale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            left = root / "force-off.c"
            right = root / "force-on.c"
            candidate = root / "candidate.c"
            log = root / "compiled.log"
            target.write_bytes(b"target")
            for source in (left, right, candidate):
                source.write_text(source.stem + "\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "source, output, log = map(pathlib.Path, sys.argv[1:4])\n"
                "with log.open('a', encoding='utf-8') as stream:\n"
                "    stream.write(source.name + '\\n')\n"
                "output.write_bytes(b'ignored-knob')\n",
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
            experiment = root / "experiment.json"
            experiment.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA_V2,
                        "family": "ignored-force",
                        "baseline": "force-off.c",
                        "parameters": {"shape": ["candidate"]},
                        "candidates": [
                            {
                                "source": "candidate.c",
                                "parameters": {"shape": "candidate"},
                            }
                        ],
                        "controls": [
                            {
                                "id": "force-fired",
                                "kind": "differential",
                                "candidates": ["force-off.c", "force-on.c"],
                                "expect": {"different": ["object_sha256"]},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "campaign",
                        str(target),
                        str(candidate),
                        "--compile-command",
                        f"{sys.executable} {compiler} {{source}} {{output}} {log}",
                        "--objdump",
                        str(objdump),
                        "--symbol",
                        "demo",
                        "--cache-dir",
                        str(root / "cache"),
                        "--state-dir",
                        str(root / "state"),
                        "--experiment-manifest",
                        str(experiment),
                        "--json-summary",
                    ]
                )
            payload = json.loads(stdout.getvalue())
            compiled = log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(status, 2)
        self.assertEqual(payload["controls"]["receipts"][0]["status"], "FAIL")
        self.assertEqual(compiled, ["force-off.c", "force-on.c"])

    def test_homologous_parameters_are_explicit_and_share_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.c"
            baseline.write_text("int baseline;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "sibling-masks",
                        "baseline": "baseline.c",
                        "parameters": {
                            "first": [False, True],
                            "second": [False, True],
                            "third": [False, True],
                        },
                        "homologous_parameters": [["first", "second", "third"]],
                        "candidates": [
                            {
                                "source": "baseline.c",
                                "parameters": {
                                    "first": False,
                                    "second": False,
                                    "third": False,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest = load_experiment(path)

        self.assertEqual(
            manifest.homologous_parameters,
            (("first", "second", "third"),),
        )
        self.assertEqual(
            manifest.metadata_for(baseline)["homologous_parameters"],
            [["first", "second", "third"]],
        )

    def test_homology_refuses_an_unassigned_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "baseline.c").write_text("int baseline;\n", encoding="utf-8")
            (root / "variant.c").write_text("int variant;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "sibling-masks",
                        "baseline": "baseline.c",
                        "parameters": {
                            "first": [False, True],
                            "second": [False, True],
                        },
                        "homologous_parameters": [["first", "second"]],
                        "candidates": [
                            {
                                "source": "variant.c",
                                "parameters": {"first": True, "second": False},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "baseline must appear"):
                load_experiment(path)

    def test_campaign_cockpit_compacts_large_parameter_evidence(self) -> None:
        tested = [{"shape": str(index)} for index in range(64)]
        tested_text, declared_text = _compact_parameter_evidence(
            {
                "tested_parameters": tested,
                "tested_parameter_sets": 375,
                "declared_parameter_space": {
                    "shape": [str(index) for index in range(25)],
                    "type": ["int", "s16", "s32", "u16", "u32"],
                },
            }
        )
        self.assertIn("375 assignment(s)", tested_text)
        self.assertIn("+372 more", tested_text)
        self.assertNotIn("'shape': '63'", tested_text)
        self.assertEqual(declared_text, "shape=25 choice(s), type=5 choice(s)")

    def test_manifest_resolves_sources_and_parameter_space(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.c"
            variant = root / "variant.c"
            baseline.write_text("int baseline;\n", encoding="utf-8")
            variant.write_text("int variant;\n", encoding="utf-8")
            path = root / "experiment.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "statement-grouping",
                        "baseline": "baseline.c",
                        "parameters": {
                            "shape": ["split", "comma", "do-while"],
                            "site": ["pad-loop", "prefix"],
                        },
                        "candidates": [
                            {
                                "source": "variant.c",
                                "parameters": {
                                    "shape": "comma",
                                    "site": "pad-loop",
                                },
                            }
                        ],
                        "selected_region": {
                            "name": "format-body",
                            "start": 1,
                            "end": 3,
                        },
                    }
                ),
                encoding="utf-8",
            )
            manifest = load_experiment(path)
        self.assertEqual(expected_parameter_combinations(manifest), 6)
        self.assertEqual(manifest.family, "statement-grouping")
        self.assertEqual(manifest.region, RegionConstraint(1, 3, "format-body"))
        self.assertEqual(
            manifest.metadata_for(variant)["parameters"]["shape"],
            "comma",
        )

    def test_validate_command_explains_a_partial_grid_without_compiling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.c"
            candidate = root / "candidate.c"
            baseline.write_text("int baseline;\n", encoding="utf-8")
            candidate.write_text("int candidate;\n", encoding="utf-8")
            manifest = root / "experiment.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "macro-shape",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["comma", "do-while"]},
                        "candidates": [
                            {
                                "source": "candidate.c",
                                "parameters": {"shape": "comma"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["experiment", "validate", str(manifest), "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(report["declared_combinations"], 2)
        self.assertEqual(report["described_candidates"], 1)
        self.assertFalse(report["complete_grid"])

    def test_validate_summary_omits_the_full_candidate_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "baseline.c").write_text("int baseline;\n", encoding="utf-8")
            (root / "candidate.c").write_text("int candidate;\n", encoding="utf-8")
            manifest = root / "experiment.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "compact-validation",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["one"]},
                        "candidates": [
                            {
                                "source": "candidate.c",
                                "parameters": {"shape": "one"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    ["experiment", "validate", str(manifest), "--json-summary"]
                )
        report = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertNotIn("candidates", report)
        self.assertEqual(report["described_candidates"], 1)
        self.assertEqual(report["family"], "compact-validation")

    def test_selected_region_scores_inside_and_outside_separately(self) -> None:
        target = parse_disassembly(
            "0: 24020001 li $v0,1\n4: 24030002 li $v1,2\n8: 03e00008 jr $ra\n"
        )
        candidate = parse_disassembly(
            "0: 24020009 li $v0,9\n4: 24030002 li $v1,2\n8: 03e00008 jr $ra\n"
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        report = region_score(comparison, RegionConstraint(1, 3, "solved"))
        self.assertTrue(report["exact"])
        self.assertEqual(report["selected_mismatches"], 0)
        self.assertEqual(report["outside_mismatches"], 1)

    def test_insertion_before_region_does_not_create_positional_phantoms(
        self,
    ) -> None:
        target = parse_disassembly(
            "0: 24020001 li $v0,1\n4: 24030002 li $v1,2\n8: 03e00008 jr $ra\n"
        )
        candidate = parse_disassembly(
            "0: 00000000 nop\n"
            "4: 24020001 li $v0,1\n"
            "8: 24030002 li $v1,2\n"
            "c: 03e00008 jr $ra\n"
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        report = region_score(comparison, RegionConstraint(1, 3, "solved"))
        self.assertTrue(report["exact"])
        self.assertEqual(report["selected_mismatches"], 0)
        self.assertEqual(report["outside_mismatches"], 1)
        self.assertIsNone(report["outside_residual_sites"][0]["target_index"])

    def test_campaign_status_reports_family_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            source = root / "variant.c"
            baseline = root / "baseline.c"
            target.write_bytes(b"target")
            source.write_text("int variant;\n", encoding="utf-8")
            baseline.write_text("int baseline;\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
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
            experiment = root / "experiment.json"
            experiment.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "statement-grouping",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["comma"]},
                        "candidates": [
                            {
                                "source": "variant.c",
                                "parameters": {"shape": "comma"},
                            }
                        ],
                        "selected_region": {"start": 0, "end": 2},
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
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
                        "--experiment-manifest",
                        str(experiment),
                        "--json-summary",
                    ]
                )
            manifest = Path(json.loads(stdout.getvalue())["manifest"])
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["campaign", "status", str(manifest), "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(report["families"][0]["family"], "statement-grouping")
        self.assertEqual(report["families"][0]["tested_parameter_sets"], 1)
        self.assertEqual(
            report["families"][0]["tested_parameters"],
            [{"shape": "comma"}],
        )
        self.assertEqual(
            report["families"][0]["declared_parameter_space"],
            {"shape": ["comma"]},
        )
        self.assertEqual(report["families"][0]["object_basins"], 1)
        self.assertTrue(report["best"]["region"]["exact"])

    def test_status_recovers_missing_ledger_experiment_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.o"
            source = root / "variant.c"
            baseline = root / "baseline.c"
            target.write_bytes(b"target")
            source.write_text("int variant;\n", encoding="utf-8")
            baseline.write_text("int baseline;\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
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
            experiment = root / "experiment.json"
            experiment.write_text(
                json.dumps(
                    {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": "legacy-family",
                        "baseline": "baseline.c",
                        "parameters": {"shape": ["named"]},
                        "candidates": [
                            {
                                "source": "variant.c",
                                "parameters": {"shape": "named"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
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
                        "--experiment-manifest",
                        str(experiment),
                        "--json-summary",
                    ]
                )
            self.assertEqual(status, 0)
            manifest = Path(json.loads(stdout.getvalue())["manifest"])
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            ledger = Path(manifest_data["ledger"])
            record = json.loads(ledger.read_text(encoding="utf-8"))
            record["experiment"] = None
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            # Older runs could prepare with one spelling of an objdump symlink
            # and execute with another, changing the cache key while retaining
            # the absolute source path in provenance.
            manifest_data["sources"][0]["cache_key"] = "stale-preparation-key"
            manifest.write_text(json.dumps(manifest_data) + "\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["campaign", "status", str(manifest), "--json"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(report["families"][0]["family"], "legacy-family")
        self.assertEqual(
            report["families"][0]["tested_parameters"], [{"shape": "named"}]
        )
        self.assertIn("recovered experiment metadata", report["warnings"][0])


if __name__ == "__main__":
    unittest.main()
