"""Bounded source-mechanism composition and cleanup inventory."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.composition import (
    compose_sources,
    inspect_source,
    load_composition,
)
from decomp_workbench.experiments import load_experiment


class CompositionTests(unittest.TestCase):
    def make_spec(self, root: Path) -> Path:
        (root / "base.c").write_text("int f(void) { return A + B; }\n")
        spec = root / "composition.json"
        spec.write_text(
            json.dumps(
                {
                    "schema": "decomp-workbench-composition-v1",
                    "baseline": "base.c",
                    "max_order": 2,
                    "transformations": [
                        {
                            "id": "left",
                            "family": "operand",
                            "edits": [{"find": "A", "replace": "X"}],
                        },
                        {
                            "id": "right",
                            "family": "carrier",
                            "edits": [{"find": "B", "replace": "Y"}],
                        },
                    ],
                }
            )
            + "\n"
        )
        return spec

    def test_generates_singletons_cross_family_pair_and_valid_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = load_composition(self.make_spec(root))
            output = root / "generated"

            report = compose_sources(spec, output)
            experiment = load_experiment(output / "experiment.json")
            composed = (output / "003-left+right.c").read_text()

        self.assertEqual(report["generated_candidates"], 3)
        self.assertEqual(report["cross_family_candidates"], 1)
        self.assertEqual(report["candidates"][2]["line_delta"], 0)
        self.assertEqual(report["candidates"][2]["byte_delta"], 0)
        self.assertEqual(len(experiment.candidates), 3)
        self.assertIn("X + Y", composed)
        self.assertIn(str(output / "experiment.json"), report["next_steps"][0])

    def test_dry_run_does_not_create_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = load_composition(self.make_spec(root))
            output = root / "generated"

            report = compose_sources(spec, output, write=False)

            self.assertFalse(output.exists())
        self.assertIsNone(report["output"])

    def test_generation_preserves_crlf_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.make_spec(root)
            (root / "base.c").write_bytes(b"int f(void) {\r\n return A + B;\r\n}\r\n")

            compose_sources(load_composition(path), root / "generated", max_order=1)

            generated = (root / "generated" / "001-left.c").read_bytes()
        self.assertEqual(generated, b"int f(void) {\r\n return X + B;\r\n}\r\n")

    def test_candidate_cap_stops_accidental_combinatorial_growth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = load_composition(self.make_spec(root))
            with self.assertRaisesRegex(ValueError, "above cap 2"):
                compose_sources(spec, root / "generated", max_candidates=2)

    def test_constraints_that_eliminate_every_candidate_fail_before_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.make_spec(root)
            value = json.loads(path.read_text())
            value["max_order"] = 1
            value["transformations"][0]["requires"] = ["right"]
            value["transformations"][1]["requires"] = ["left"]
            path.write_text(json.dumps(value) + "\n")
            output = root / "generated"

            with self.assertRaisesRegex(ValueError, "no valid candidates"):
                compose_sources(load_composition(path), output)

            self.assertFalse(output.exists())

    def test_source_inspection_is_explicitly_syntactic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "candidate.c"
            source.write_text(
                "void f(void) {\n"
                "    static int carrier;\n"
                "    if (width == height) {}\n"
                "    if (width == height) {}\n"
                "    value += carrier * 0;\n"
                "}\n"
            )
            report = inspect_source(source)

        self.assertEqual(report["finding_count"], 4)
        self.assertEqual(report["duplicate_empty_controls"][0]["count"], 2)
        self.assertEqual(report["inventory_by_kind"]["empty-control"], 2)
        self.assertTrue(
            all(not item["safe_automatic_removal"] for item in report["findings"])
        )
        self.assertTrue(all(item["review_question"] for item in report["findings"]))
        self.assertIn("object collateral", report["cleanup_gates"][-1])
        self.assertIn("syntax inventory only", report["proof"])
