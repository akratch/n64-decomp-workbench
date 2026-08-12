"""Integrity and redistribution checks for the code-free CV64 campaign record."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
CV64 = ROOT / "examples" / "cv64"
EXPECTED_EXACT = {
    "func_800010A0_1CA0": False,
    "func_800010C8_1CC8": False,
    "func_800012C0_1EC0": True,
    "func_8013B270_BE460": True,
    "menuButton_selectNextOption": False,
}


class Cv64ExampleTests(unittest.TestCase):
    def test_recorded_results_are_self_consistent(self) -> None:
        payload = json.loads((CV64 / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "decomp-workbench-recorded-example-v1")
        self.assertEqual(payload["compiler"], "IDO 7.1")
        results = {item["symbol"]: item for item in payload["results"]}
        self.assertEqual(set(results), set(EXPECTED_EXACT))
        for symbol, exact in EXPECTED_EXACT.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(results[symbol]["exact"], exact)
                self.assertEqual(
                    results[symbol]["normalized_distance"] == 0,
                    exact,
                )

    def test_uncleared_scratch_payloads_are_absent(self) -> None:
        scratches = CV64 / "scratches"
        files = [path for path in scratches.rglob("*") if path.is_file()]
        self.assertEqual(files, [])
        forbidden_names = {"context.c", "source.c", "target.s", "SHA256SUMS"}
        self.assertEqual(
            {path.name for path in CV64.rglob("*") if path.name in forbidden_names},
            set(),
        )

    def test_notice_records_the_resolved_release_gate(self) -> None:
        notice = (CV64 / "NOTICE.md").read_text(encoding="utf-8")
        self.assertIn("does not grant a license", notice)
        self.assertIn("payloads are not present", notice)
        self.assertIn("redistribution basis", notice)


if __name__ == "__main__":
    unittest.main()
