"""Tests for the ``--census`` report predicate and its exit-code contract.

Campaign agents rebuilt this filter at least seven times in one day. What they
needed was not a new metric but a way to ask about the metrics that already
exist without a JSON parser in the loop, and an exit status they could tell
apart from "this candidate is not a match".
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from decomp_workbench.census import (
    CENSUS_FAILURE_EXIT,
    evaluate_census,
    matches,
    parse_census,
)
from decomp_workbench.cli import main
from decomp_workbench.schema import COMPARISON_CENSUS_KEYS, VIEW_CENSUS_KEYS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures"
TARGET = str(FIXTURES / "target.objdump")
REGISTER_MISMATCH = str(FIXTURES / "register-mismatch.objdump")
RELOCATED_MATCH = str(FIXTURES / "relocated-match.objdump")
SHIFT_TARGET = str(FIXTURES / "shifted-insertion-target.objdump")
SHIFT_CANDIDATE = str(FIXTURES / "shifted-insertion-candidate.objdump")


class CensusPredicateTests(unittest.TestCase):
    """The parser refuses what it cannot answer, before any work is done."""

    def test_entries_are_comma_separated(self) -> None:
        predicates = parse_census(["words=0,frame=-32"], allowed=COMPARISON_CENSUS_KEYS)
        self.assertEqual(
            [(item.key, item.expected) for item in predicates],
            [("words", "0"), ("frame", "-32")],
        )

    def test_the_option_is_repeatable(self) -> None:
        predicates = parse_census(
            ["words=0", "frame=-32"], allowed=COMPARISON_CENSUS_KEYS
        )
        self.assertEqual([item.key for item in predicates], ["words", "frame"])

    def test_a_comma_inside_a_value_is_not_a_separator(self) -> None:
        """`mixed(constant:1, register:2)` is one verdict, not two entries."""

        predicates = parse_census(
            ["verdict=mixed(constant:1, register:2)"], allowed=VIEW_CENSUS_KEYS
        )
        self.assertEqual(len(predicates), 1)
        self.assertEqual(predicates[0].expected, "mixed(constant:1, register:2)")

    def test_a_deprecated_spelling_still_answers(self) -> None:
        """A predicate must not stop working before the key it names does."""

        predicate = parse_census(
            ["candidate_frame_size=-128"], allowed=COMPARISON_CENSUS_KEYS
        )[0]
        self.assertEqual(predicate.key, "candidate_frame_size")
        self.assertEqual(predicate.metric, "frame")

    def test_malformed_and_unknown_entries_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not KEY=VALUE"):
            parse_census(["words"], allowed=COMPARISON_CENSUS_KEYS)
        with self.assertRaisesRegex(ValueError, "not KEY=VALUE"):
            parse_census(["=0"], allowed=COMPARISON_CENSUS_KEYS)
        with self.assertRaisesRegex(ValueError, "unknown census key"):
            parse_census(["wrds=0"], allowed=COMPARISON_CENSUS_KEYS)
        with self.assertRaisesRegex(ValueError, "unknown census key"):
            # A view key is not a comparison key: the two count different
            # things and must not answer for each other.
            parse_census(["aligned_rows=8"], allowed=COMPARISON_CENSUS_KEYS)

    def test_values_compare_by_the_reported_type(self) -> None:
        self.assertTrue(matches(-128, "-128"))
        self.assertTrue(matches(-128, "-0x80"))
        self.assertTrue(matches(True, "true"))
        self.assertFalse(matches(True, "false"))
        self.assertTrue(matches(False, "0"))
        self.assertTrue(matches(None, "none"))
        self.assertTrue(matches("allocation-mismatch", "allocation-mismatch"))
        self.assertFalse(matches("allocation", "allocation-mismatch"))
        with self.assertRaisesRegex(ValueError, "not an integer"):
            matches(4, "four")
        with self.assertRaisesRegex(ValueError, "not true or false"):
            matches(True, "maybe")

    def test_a_list_or_object_key_is_refused(self) -> None:
        predicates = parse_census(["diff_sites=1"], allowed=COMPARISON_CENSUS_KEYS)
        with self.assertRaisesRegex(ValueError, "not a single value"):
            evaluate_census(predicates, {"diff_sites": [{"index": 0}]})

    def test_a_key_the_report_did_not_carry_is_refused(self) -> None:
        """Missing is not `none`: one is an absent key, the other is a value."""

        predicates = parse_census(["symbol=none"], allowed=COMPARISON_CENSUS_KEYS)
        self.assertTrue(evaluate_census(predicates, {"symbol": None})[0].passed)
        with self.assertRaisesRegex(ValueError, "not in this report"):
            evaluate_census(predicates, {"words": 0})


class CensusCommandTests(unittest.TestCase):
    """The exit status is the answer; the printed lines say which predicate."""

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_every_predicate_holding_is_exit_zero(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--census",
                "aligned_register=1,frame=-32,exact=false",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("census: PASS aligned_register=1", stdout)
        self.assertIn("census: PASS frame=-32", stdout)
        self.assertIn("census: PASS exact=false", stdout)
        self.assertNotIn("FAIL", stdout)

    def test_a_failing_predicate_is_exit_three(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--census",
                "aligned_register=0",
            ]
        )
        self.assertEqual(status, CENSUS_FAILURE_EXIT)
        self.assertEqual(status, 3)
        self.assertIn("census: FAIL aligned_register=0 (actual 1)", stdout)

    def test_every_predicate_is_reported_not_just_the_first_failure(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--census",
                "aligned_register=0",
                "--census",
                "frame=-32",
            ]
        )
        self.assertEqual(status, 3)
        self.assertIn("census: FAIL aligned_register=0", stdout)
        self.assertIn("census: PASS frame=-32", stdout)

    def test_census_failure_is_distinct_from_a_mismatch(self) -> None:
        """`--fail-on-mismatch` answers a different question, with a 1."""

        mismatch, _, _ = self.run_cli(
            ["compare-dumps", TARGET, REGISTER_MISMATCH, "--fail-on-mismatch"]
        )
        self.assertEqual(mismatch, 1)
        # The candidate is not a match and the census holds: the census is the
        # more specific question, so it does not hide the mismatch status.
        held, _, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--fail-on-mismatch",
                "--census",
                "aligned_register=1",
            ]
        )
        self.assertEqual(held, 1)
        failed, _, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--fail-on-mismatch",
                "--census",
                "aligned_register=0",
            ]
        )
        self.assertEqual(failed, 3)

    def test_an_exact_candidate_can_be_filtered_too(self) -> None:
        status, stdout, _ = self.run_cli(
            ["compare-dumps", TARGET, RELOCATED_MATCH, "--census", "exact=true,words=0"]
        )
        self.assertEqual(status, 0)
        self.assertIn("census: PASS exact=true", stdout)

    def test_json_carries_the_predicate_results(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "compare-dumps",
                TARGET,
                REGISTER_MISMATCH,
                "--json",
                "--census",
                "aligned_register=0",
            ]
        )
        self.assertEqual(status, 3)
        payload = json.loads(stdout)
        self.assertEqual(
            payload["census"],
            [
                {
                    "key": "aligned_register",
                    "expected": "0",
                    "actual": 1,
                    "pass": False,
                }
            ],
        )

    def test_json_omits_the_key_when_no_predicate_was_asked(self) -> None:
        status, stdout, _ = self.run_cli(
            ["compare-dumps", TARGET, REGISTER_MISMATCH, "--json"]
        )
        self.assertEqual(status, 0)
        self.assertNotIn("census", json.loads(stdout))

    def test_the_view_answers_its_own_keys(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "view-dumps",
                SHIFT_TARGET,
                SHIFT_CANDIDATE,
                "--symbol",
                "blockSum",
                "--color",
                "never",
                "--census",
                "structural=1,register=0,verdict=structure",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("census: PASS structural=1", stdout)
        self.assertIn("census: PASS verdict=structure", stdout)

    def test_the_view_reports_a_failure_the_same_way(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "view-dumps",
                SHIFT_TARGET,
                SHIFT_CANDIDATE,
                "--symbol",
                "blockSum",
                "--color",
                "never",
                "--json",
                "--census",
                "structural=0",
            ]
        )
        self.assertEqual(status, 3)
        payload = json.loads(stdout)
        self.assertFalse(payload["census"][0]["pass"])
        self.assertEqual(payload["census"][0]["actual"], 1)

    def test_an_unusable_predicate_is_a_usage_error(self) -> None:
        for expression, message in (
            ("bogus=1", "unknown census key"),
            ("words", "not KEY=VALUE"),
            ("diff_sites=1", "not a single value"),
            ("words=many", "not an integer"),
            ("exact=maybe", "not true or false"),
        ):
            with self.subTest(expression=expression):
                status, _, stderr = self.run_cli(
                    [
                        "compare-dumps",
                        TARGET,
                        REGISTER_MISMATCH,
                        "--census",
                        expression,
                    ]
                )
                self.assertEqual(status, 2)
                self.assertIn(message, stderr)

    def test_an_unknown_key_costs_nothing(self) -> None:
        """The keys are checked before the inputs are even read."""

        status, _, stderr = self.run_cli(
            ["compare-dumps", "missing.objdump", "gone.objdump", "--census", "bogus=1"]
        )
        self.assertEqual(status, 2)
        self.assertIn("unknown census key", stderr)


if __name__ == "__main__":
    unittest.main()
