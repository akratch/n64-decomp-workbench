"""A sampled sweep may not be recorded as a closed family.

The incident: "no single fp-ring perturbation anywhere improves on 563", from a
``k = 1..1457 step 8`` sweep. One point in eight. The claim went into a ledger
as a closed family; a later exhaustive re-run happened to agree, so nothing
broke, and the statement was still not entitled to be a proof when it was made.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.coverage import SweepCoverage

COMPOSITION = {
    "schema": "decomp-workbench-composition-v1",
    "baseline": "baseline.c",
    "max_order": 3,
    "max_candidates": 64,
    "transformations": [
        {
            "id": f"t{index}",
            "family": "shape",
            "edits": [{"find": f"MARK{index}", "replace": f"done{index}"}],
        }
        for index in range(6)
    ],
}


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class SweepCoverageTests(unittest.TestCase):
    def test_a_full_sweep_may_claim_a_proof(self) -> None:
        item = SweepCoverage(basis="k=1..8", space=8, covered=8)

        self.assertTrue(item.exhaustive)
        self.assertEqual(item.vocabulary, "swept-exhaustively")
        self.assertIn("is a proof about this space", item.sentence())

    def test_one_point_in_eight_says_what_it_never_visited(self) -> None:
        item = SweepCoverage(basis="k=1..1457", space=1457, covered=183, step=8)

        self.assertFalse(item.exhaustive)
        self.assertEqual(item.vocabulary, "sampled")
        self.assertEqual(item.unvisited, 1274)
        sentence = item.sentence()
        self.assertIn("step 8", sentence)
        self.assertIn("1274 point(s) were never visited", sentence)
        self.assertIn("not a proof about the space", sentence)

    def test_deliberate_exclusions_still_count_as_covered_ground(self) -> None:
        """A rule that rejects a point has visited it; a stride has not."""

        item = SweepCoverage(basis="pairs", space=10, covered=7, excluded=3)

        self.assertTrue(item.exhaustive)
        self.assertEqual(item.unvisited, 0)

    def test_an_unbounded_space_is_never_reported_as_complete(self) -> None:
        item = SweepCoverage(basis="all source edits", space=None, covered=40)

        self.assertFalse(item.exhaustive)
        self.assertIsNone(item.fraction)
        self.assertIn("unbounded", item.sentence())


class ComposeCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "baseline.c").write_text(
            "\n".join(f"int v{index} = MARK{index};" for index in range(6)) + "\n",
            encoding="utf-8",
        )
        self.manifest = self.root / "composition.json"
        self.manifest.write_text(json.dumps(COMPOSITION), encoding="utf-8")

    def _compose(self, *extra: str) -> dict:
        status, stdout, stderr = run_cli(
            [
                "experiment",
                "compose",
                str(self.manifest),
                str(self.root / "out"),
                "--dry-run",
                "--json",
                *extra,
            ]
        )
        self.assertEqual(status, 0, stderr)
        return json.loads(stdout)

    def test_an_exhaustive_composition_says_so(self) -> None:
        coverage = self._compose()["coverage"]

        self.assertTrue(coverage["exhaustive"])
        self.assertEqual(coverage["vocabulary"], "swept-exhaustively")
        self.assertEqual(coverage["step"], 1)

    def test_a_strided_composition_reports_the_stride_and_the_remainder(self) -> None:
        coverage = self._compose("--step", "4")["coverage"]

        self.assertFalse(coverage["exhaustive"])
        self.assertEqual(coverage["step"], 4)
        self.assertGreater(coverage["unvisited"], 0)
        self.assertLess(coverage["fraction"], 0.5)
        self.assertIn("never visited", coverage["sentence"])

    def test_the_coverage_sentence_reaches_the_terminal(self) -> None:
        status, stdout, stderr = run_cli(
            [
                "experiment",
                "compose",
                str(self.manifest),
                str(self.root / "out2"),
                "--dry-run",
                "--step",
                "4",
            ]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("coverage: sampled", stdout)

    def test_a_cap_that_a_stride_would_fit_says_so(self) -> None:
        status, _stdout, stderr = run_cli(
            [
                "experiment",
                "compose",
                str(self.manifest),
                str(self.root / "out3"),
                "--dry-run",
                "--max-candidates",
                "5",
            ]
        )

        self.assertEqual(status, 2)
        self.assertIn("--step to sample the space", stderr)


if __name__ == "__main__":
    unittest.main()
