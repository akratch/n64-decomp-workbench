"""A sweep's own record, not verdict prose, assigns the wall class.

Nothing here runs decomp-permuter: the classifier reads the summary the
sweep already writes, so the fixtures are JSON documents.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.permute import output_fraction
from decomp_workbench.permute_classify import (
    CLASSIFY_SCHEMA,
    IMPORT_FAULT,
    MATCHED,
    P_STUCK_DESCENDING,
    P_STUCK_FLAT,
    classify_payload,
    classify_row,
    classify_summary,
    render_markdown,
)

FIXTURE = Path(__file__).resolve().parents[1] / "examples/fixtures/permute-summary.json"


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "function": "func_80012574",
        "source": "src/game/track.c",
        "ok": True,
        "base_score": 40,
        "best_score": 30,
        "extended": False,
        "flags_recovered": True,
        "hit_cap": True,
        "seconds": 1200.0,
        "window_seconds": 1200.0,
        "best_output_mtime_fraction": 0.9,
        "error": None,
    }
    base.update(overrides)
    return base


class ClassifyTests(unittest.TestCase):
    def test_a_scratch_score_of_zero_is_matched_and_not_promoted(self) -> None:
        result = classify_row(row(best_score=0))
        self.assertEqual(result.wall_class, MATCHED)
        self.assertEqual(result.delta, 40)
        self.assertIn("real build has not confirmed", result.reason)

    def test_a_late_best_candidate_is_still_descending(self) -> None:
        result = classify_row(row(best_output_mtime_fraction=0.9))
        self.assertEqual(result.wall_class, P_STUCK_DESCENDING)
        self.assertEqual(result.delta, 10)

    def test_an_earned_extension_is_descending_whatever_the_timing(self) -> None:
        """The extension only fires on a run that was still improving."""

        result = classify_row(row(extended=True, best_output_mtime_fraction=0.1))
        self.assertEqual(result.wall_class, P_STUCK_DESCENDING)
        self.assertIn("earned its extension", result.reason)

    def test_an_early_best_candidate_that_then_sat_is_flat(self) -> None:
        result = classify_row(row(best_output_mtime_fraction=0.1))
        self.assertEqual(result.wall_class, P_STUCK_FLAT)
        self.assertIn("10%", result.reason)

    def test_no_improvement_at_all_is_flat(self) -> None:
        never = classify_row(row(best_score=None, best_output_mtime_fraction=None))
        worse = classify_row(row(best_score=44))
        self.assertEqual(never.wall_class, P_STUCK_FLAT)
        self.assertEqual(never.delta, 0)
        self.assertEqual(worse.wall_class, P_STUCK_FLAT)

    def test_a_failed_scratch_measured_nothing(self) -> None:
        """A scratch that never scored the base is not evidence of a wall.

        Calling it flat is the mistake that funds an instrumentation build
        for a function nobody ever searched.
        """

        failed = classify_row(row(ok=False, base_score=None, error="import.py failed"))
        no_score = classify_row(row(base_score=None))
        self.assertEqual(failed.wall_class, IMPORT_FAULT)
        self.assertIn("import.py failed", failed.reason)
        self.assertIsNone(failed.delta)
        self.assertEqual(no_score.wall_class, IMPORT_FAULT)

    def test_an_error_outranks_a_score_that_was_also_recorded(self) -> None:
        result = classify_row(row(best_score=0, error="the run was killed"))
        self.assertEqual(result.wall_class, IMPORT_FAULT)

    def test_a_summary_without_the_timing_field_is_not_called_flat(self) -> None:
        """Old summaries predate the field; absent evidence is not evidence."""

        result = classify_row(row(best_output_mtime_fraction=None))
        self.assertEqual(result.wall_class, P_STUCK_DESCENDING)
        self.assertIn("does not record when", result.reason)


class SummaryTests(unittest.TestCase):
    def test_both_summary_spellings_are_read(self) -> None:
        rows = [row(function="a"), row(function="b", best_score=0)]
        self.assertEqual(len(classify_summary({"results": rows})), 2)
        self.assertEqual(len(classify_summary(rows)), 2)

    def test_a_summary_that_is_not_a_list_of_results_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            classify_summary({"results": 3})

    def test_the_payload_totals_every_class_including_the_empty_ones(self) -> None:
        payload = classify_payload(
            [classify_row(row(best_score=0)), classify_row(row())],
            source="summary.json",
        )
        self.assertEqual(payload["schema"], CLASSIFY_SCHEMA)
        self.assertEqual(payload["totals"][MATCHED], 1)
        self.assertEqual(payload["totals"][P_STUCK_DESCENDING], 1)
        self.assertEqual(payload["totals"][P_STUCK_FLAT], 0)
        self.assertEqual(payload["totals"][IMPORT_FAULT], 0)
        self.assertIn(MATCHED, payload["routing"])
        self.assertEqual(payload["functions"][0]["class"], MATCHED)

    def test_a_fallback_search_is_flagged_but_a_failed_one_is_not(self) -> None:
        """A fallback-flags class describes the scratch, not the function.

        An IMPORT_FAULT row never got as far as flags, so listing it there
        would be pointing at the wrong problem.
        """

        text = "\n".join(
            render_markdown(
                [
                    classify_row(row(function="wrong_isa", flags_recovered=False)),
                    classify_row(
                        row(
                            function="broken",
                            ok=False,
                            base_score=None,
                            flags_recovered=False,
                            error="import.py failed",
                        )
                    ),
                ]
            )
        )
        self.assertIn("fallback flags", text)
        self.assertIn("`wrong_isa`", text.split("fallback flags")[1])
        self.assertNotIn("`broken`", text.split("fallback flags")[1])

    def test_the_markdown_is_a_table_a_triage_page_can_paste(self) -> None:
        text = render_markdown([classify_row(row())], source="summary.json")
        self.assertEqual(text[0], "Sweep: `summary.json`")
        self.assertTrue(text[2].startswith("| function | class |"))
        self.assertTrue(any("P_STUCK_DESCENDING" in line for line in text))
        self.assertTrue(any(line.startswith("| class |") for line in text))


class ClassifyCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_shipped_fixture_classifies_every_class(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["permute-classify", str(FIXTURE), "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(payload["schema"], CLASSIFY_SCHEMA)
        self.assertEqual(payload["totals"][MATCHED], 1)
        self.assertEqual(payload["totals"][P_STUCK_DESCENDING], 1)
        self.assertEqual(payload["totals"][P_STUCK_FLAT], 2)
        self.assertEqual(payload["totals"][IMPORT_FAULT], 1)

    def test_one_class_can_be_asked_for_on_its_own(self) -> None:
        status, stdout, _stderr = self.run_cli(
            ["permute", "classify", str(FIXTURE), "--class", P_STUCK_FLAT]
        )
        self.assertEqual(status, 0)
        self.assertIn("synth_plateaued", stdout)
        self.assertNotIn("synth_still_descending", stdout)

    def test_a_summary_that_is_not_there_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, _stdout, stderr = self.run_cli(
                ["permute-classify", str(Path(temporary) / "absent.json")]
            )
        self.assertEqual(status, 2)
        self.assertTrue(stderr.startswith("error: "))


class OutputFractionTests(unittest.TestCase):
    def test_the_fraction_places_the_best_candidate_in_the_window(self) -> None:
        self.assertEqual(output_fraction(elapsed=1200.0, best_age=0.0), 1.0)
        self.assertEqual(output_fraction(elapsed=1200.0, best_age=1200.0), 0.0)
        self.assertAlmostEqual(
            output_fraction(elapsed=1200.0, best_age=300.0) or 0.0, 0.75
        )

    def test_an_unmeasurable_window_is_none_rather_than_a_guess(self) -> None:
        self.assertIsNone(output_fraction(elapsed=1200.0, best_age=None))
        self.assertIsNone(output_fraction(elapsed=0.0, best_age=1.0))

    def test_a_clock_skew_cannot_push_the_fraction_outside_the_window(self) -> None:
        self.assertEqual(output_fraction(elapsed=10.0, best_age=-5.0), 1.0)
        self.assertEqual(output_fraction(elapsed=10.0, best_age=99.0), 0.0)


if __name__ == "__main__":
    unittest.main()
