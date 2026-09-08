"""A forced result and a stock result score identically; only one is a match.

The case behind these tests is real: a supervising agent read four `0/N`
scores from forced diagnostic runs during a Mickey's Speedway USA campaign and
reported four exact matches. Every one of those lanes went on to file a
plateau. The score was right and the reading was wrong, so the reading is what
this module makes checkable.
"""

from __future__ import annotations

import unittest

from decomp_workbench.provenance import (
    FORCING_ENVIRONMENT,
    classify_environment,
    read_result,
)


class ClassifyEnvironmentTests(unittest.TestCase):
    def test_any_forcing_variable_marks_the_run_forced(self) -> None:
        for name in FORCING_ENVIRONMENT:
            with self.subTest(name=name):
                self.assertEqual(classify_environment({name: "1"}), "forced")

    def test_clean_environment_is_stock(self) -> None:
        self.assertEqual(classify_environment({"PATH": "/usr/bin"}), "stock")

    def test_empty_environment_is_stock(self) -> None:
        self.assertEqual(classify_environment({}), "stock")

    def test_absent_environment_is_unknown_not_stock(self) -> None:
        # Guessing "stock" here would recreate the false positive.
        self.assertEqual(classify_environment(None), "unknown")


class ReadResultTests(unittest.TestCase):
    def test_forced_exact_is_a_reachability_proof_not_a_match(self) -> None:
        claim = read_result(exact=True, provenance="forced")
        self.assertEqual(claim.claim, "reachability-proof")
        self.assertFalse(claim.is_match)
        self.assertIn("NOT A MATCH", "\n".join(claim.lines))

    def test_unknown_exact_is_not_claimable(self) -> None:
        claim = read_result(exact=True, provenance="unknown")
        self.assertEqual(claim.claim, "unverified")
        self.assertFalse(claim.is_match)

    def test_stock_exact_is_a_match_and_still_names_the_proofs(self) -> None:
        claim = read_result(exact=True, provenance="stock")
        self.assertEqual(claim.claim, "match")
        self.assertTrue(claim.is_match)
        self.assertIn("relocation identities", "\n".join(claim.lines))

    def test_no_provenance_makes_a_nonexact_result_a_match(self) -> None:
        for provenance in ("stock", "forced", "unknown"):
            with self.subTest(provenance=provenance):
                claim = read_result(exact=False, provenance=provenance)
                self.assertEqual(claim.claim, "no-claim")
                self.assertFalse(claim.is_match)

    def test_unrecognised_provenance_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_result(exact=True, provenance="probably-fine")

    def test_the_four_readings_that_were_misreported(self) -> None:
        # 0/403, 0/146, 0/131, 0/22 -- all forced, none matches.
        for _words in (403, 146, 131, 22):
            claim = read_result(exact=True, provenance="forced")
            self.assertFalse(claim.is_match)


if __name__ == "__main__":
    unittest.main()
