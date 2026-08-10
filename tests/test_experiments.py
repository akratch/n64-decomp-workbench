"""Experiment sidecars make family, parameters, and invariants durable."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.campaign import region_score
from decomp_workbench.campaign_cli import _compact_parameter_evidence
from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.experiments import (
    EXPERIMENT_SCHEMA,
    RegionConstraint,
    expected_parameter_combinations,
    load_experiment,
)
from decomp_workbench.objdump import parse_disassembly


class ExperimentTests(unittest.TestCase):
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
