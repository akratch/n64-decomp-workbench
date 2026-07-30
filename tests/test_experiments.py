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


if __name__ == "__main__":
    unittest.main()
