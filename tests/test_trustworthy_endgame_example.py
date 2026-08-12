"""The asset-free endgame example is a tested product journey."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class TrustworthyEndgameExampleTests(unittest.TestCase):
    def test_walkthrough_runs_to_a_passing_receipt(self) -> None:
        process = subprocess.run(
            [sys.executable, "examples/trustworthy-endgame/run.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertEqual(
            json.loads(process.stdout),
            {
                "schema": "decomp-workbench-trustworthy-endgame-walkthrough-v1",
                "scratch_truth": "scratch-mismatch",
                "controls": "PASS",
                "coverage": "exhaustive-over-declared-space",
                "finish": "PASS",
                "package": "PASS",
                "compiler_envelope": "PASS",
                "network_used": False,
                "proprietary_assets_used": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
