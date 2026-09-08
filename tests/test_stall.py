"""Stopping must be measured, not counted.

The three cases here are the three real ones that motivated the module, taken
from a single Mickey's Speedway USA wave on 2026-09-08: a series that was still
gaining when a fixed count would have stopped it, a series that had stopped
buying anything, and a target whose recorded history meant the right number of
attempts was zero.
"""

from __future__ import annotations

import unittest

from decomp_workbench.stall import DEFAULT_THRESHOLD, Attempt, read_series


class ReadSeriesTests(unittest.TestCase):
    def test_monotone_improvement_continues(self) -> None:
        # func_8000590C: 692 -> 619 -> 538 differing words, stopped at a count
        # while it was still gaining.
        reading = read_series([Attempt(692), Attempt(619), Attempt(538)])
        self.assertEqual(reading.state, "improving")
        self.assertTrue(reading.should_continue)
        self.assertEqual(reading.stalled_for, 0)
        self.assertEqual(reading.best_residual, 538)
        self.assertEqual(reading.last_progress, 2)

    def test_flat_series_stalls_at_the_threshold(self) -> None:
        reading = read_series([Attempt(41), Attempt(41), Attempt(41), Attempt(41)])
        self.assertEqual(reading.state, "stalled")
        self.assertFalse(reading.should_continue)
        self.assertEqual(reading.stalled_for, DEFAULT_THRESHOLD)
        self.assertEqual(reading.last_progress, 0)

    def test_one_short_of_the_threshold_still_continues(self) -> None:
        reading = read_series([Attempt(41), Attempt(41), Attempt(41)])
        self.assertEqual(reading.state, "improving")
        self.assertEqual(reading.stalled_for, 2)

    def test_elimination_counts_as_progress_without_moving_the_residual(self) -> None:
        # An attempt that rules a hypothesis out has bought something even
        # though the number did not move.
        reading = read_series(
            [Attempt(41), Attempt(41), Attempt(41, eliminated=True), Attempt(41)]
        )
        self.assertEqual(reading.state, "improving")
        self.assertEqual(reading.stalled_for, 1)
        self.assertEqual(reading.last_progress, 2)

    def test_a_worse_attempt_does_not_reset_the_stall(self) -> None:
        # A regression is not progress; only a new best is.
        reading = read_series([Attempt(41), Attempt(55), Attempt(60), Attempt(58)])
        self.assertEqual(reading.state, "stalled")
        self.assertEqual(reading.stalled_for, 3)
        self.assertEqual(reading.best_residual, 41)

    def test_recorded_evidence_closes_the_target_before_any_attempt(self) -> None:
        # func_overlay_092_F0000068_18D5F88: lattice exhausted, donors negative,
        # mechanism flat in three forms. Zero attempts was correct.
        reading = read_series([], closed_by_evidence=True)
        self.assertEqual(reading.state, "closed-by-evidence")
        self.assertFalse(reading.should_continue)
        self.assertIsNone(reading.best_residual)

    def test_recorded_evidence_wins_over_an_improving_series(self) -> None:
        reading = read_series([Attempt(692), Attempt(619)], closed_by_evidence=True)
        self.assertEqual(reading.state, "closed-by-evidence")

    def test_empty_series_is_not_a_stall(self) -> None:
        reading = read_series([])
        self.assertEqual(reading.state, "improving")
        self.assertIsNone(reading.best_residual)
        self.assertIsNone(reading.last_progress)

    def test_threshold_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            read_series([Attempt(1)], threshold=0)

    def test_reading_never_claims_reachability(self) -> None:
        stalled = read_series([Attempt(9)] * 4)
        text = "\n".join(stalled.lines)
        self.assertIn("not a reachability claim", text)

    def test_improving_reading_refuses_to_license_adoption(self) -> None:
        improving = read_series([Attempt(9), Attempt(8)])
        text = "\n".join(improving.lines)
        self.assertIn("never grounds for", text)


if __name__ == "__main__":
    unittest.main()
