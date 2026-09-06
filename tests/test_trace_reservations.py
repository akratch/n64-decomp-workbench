"""Synthetic initialization transitions versus conditional entry requests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from decomp_workbench.trace import (
    TraceEvent,
    infer_initial_queue,
    parse_trace,
    replay_fifo,
)


def events(lines: list[str]) -> list[TraceEvent]:
    return parse_trace("\n".join("DKWB-FREELIST " + line for line in lines))


class InitializationTests(unittest.TestCase):
    def test_initial_remove_absent_remove_and_readd_are_ordered(self) -> None:
        trace = events(
            [
                "ADD proc=1 reg=14",
                "ADD proc=1 reg=15",
                "ADD proc=1 reg=13",
                "REMOVE proc=1 reg=2",
                "REMOVE proc=1 reg=13",
                "REMOVE proc=1 reg=13",
                "ADD proc=1 reg=13",
                "REMOVE proc=1 reg=15",
                "ALLOC_GP_RESULT proc=1 reg=14",
                "ALLOC_GP_RESULT proc=1 reg=13",
            ]
        )
        self.assertEqual(infer_initial_queue(trace), [14, 13])
        report = replay_fifo(trace)
        self.assertTrue(report.valid, report.violations)
        self.assertEqual(report.initial_queue, [14, 13])
        self.assertEqual(report.allocations, [14, 13])

    def test_reserved_unallocated_member_is_retained_in_prefix_evidence(self) -> None:
        trace = events(
            [
                "ADD proc=1 reg=14",
                "ADD proc=1 reg=13",
                "REMOVE proc=1 reg=13",
                "ALLOC_GP_RESULT proc=1 reg=14",
            ]
        )
        self.assertEqual(replay_fifo(trace).initial_queue, [14])

    def test_incomplete_or_duplicate_initialization_is_not_valid(self) -> None:
        for control in ("ADD proc=1 reg=14", "REMOVE proc=1", "FREE proc=1"):
            with self.subTest(control=control):
                report = replay_fifo(
                    events(
                        ["ADD proc=1 reg=14", control, "ALLOC_GP_RESULT proc=1 reg=14"]
                    )
                )
                self.assertFalse(report.valid)

    def test_runtime_remove_and_explicit_add_are_not_dropped(self) -> None:
        trace = events(
            [
                "ADD proc=1 reg=14",
                "ADD proc=1 reg=15",
                "ALLOC_GP_RESULT proc=1 reg=14",
                "REMOVE proc=1 reg=15",
                "ADD proc=1 reg=15",
                "ALLOC_GP_RESULT proc=1 reg=15",
            ]
        )
        report = replay_fifo(trace)
        self.assertTrue(report.valid, report.violations)
        self.assertIn("remove", [item.action for item in report.logical_events])

    def test_modern_free_requests_do_not_manufacture_appends(self) -> None:
        for event in ("FREE", "FORCE_FREE"):
            with self.subTest(event=event):
                trace = events(
                    [
                        "ADD proc=1 reg=14",
                        "ALLOC_GP_RESULT proc=1 reg=14",
                        f"{event} proc=1 reg=14",
                    ]
                )
                report = replay_fifo(trace)
                self.assertFalse(report.valid)
                self.assertEqual(report.final_queue, [])
                self.assertEqual(report.unresolved_free_requests, 1)
                self.assertIn(
                    "requires transition evidence", " ".join(report.violations)
                )

    def test_unknown_preallocation_free_is_not_complete_initial_state(self) -> None:
        report = replay_fifo(
            events(
                [
                    "ADD proc=1 reg=14",
                    "FREE proc=1 reg=13",
                    "ALLOC_GP_RESULT proc=1 reg=14",
                ]
            )
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.initialization_basis, "unresolved-prefix")

    def test_wrong_or_mixed_procedure_is_rejected(self) -> None:
        trace = events(
            [
                "ADD proc=1 reg=14",
                "REMOVE proc=2 reg=14",
                "ALLOC_GP_RESULT proc=1 reg=14",
            ]
        )
        with self.assertRaises(ValueError):
            replay_fifo(trace)
        with self.assertRaises(ValueError):
            replay_fifo(trace, procedure=3)

    def test_unknown_queue_control_is_not_silent(self) -> None:
        trace = events(
            [
                "ADD proc=1 reg=14",
                "MOVE_END proc=1 reg=14",
                "ALLOC_GP_RESULT proc=1 reg=14",
            ]
        )
        # Only the authenticated producer's known used-list operation is exempt.
        trace[1] = replace(trace[1], action="move-end")
        report = replay_fifo(trace)
        self.assertFalse(report.valid)

    def test_known_used_list_request_leaves_free_fifo_unchanged(self) -> None:
        for scope in ("proc=1", "proc=2", ""):
            with self.subTest(scope=scope):
                trace = parse_trace(
                    "CODEX-UGEN-APPEND proc=1 reg=14\n"
                    "CODEX-UGEN-ALLOC proc=1 reg=14\n"
                    f"DKWB-FREELIST MOVE_END {scope} reg=14\n"
                    "CODEX-UGEN-APPEND proc=1 reg=14\n"
                )
                report = replay_fifo(trace, procedure=1)
                self.assertTrue(report.valid, report.violations)
                self.assertEqual(report.initial_queue, [14])
                self.assertEqual(report.final_queue, [14])
                self.assertEqual(report.allocations, [14])
                self.assertEqual(trace[2].action, "used-list-request")
                with self.assertRaises(ValueError):
                    replay_fifo(trace, procedure=2)

    def test_explicit_procedure_does_not_discard_unscoped_controls(self) -> None:
        for control in ("REMOVE", "FREE", "FORCE_FREE"):
            with self.subTest(control=control):
                trace = events(
                    [
                        "ADD proc=0 reg=14",
                        f"{control} reg=14",
                        "ALLOC_GP_RESULT proc=0 reg=14",
                    ]
                )
                with self.assertRaises(ValueError):
                    replay_fifo(trace, procedure=0)


if __name__ == "__main__":
    unittest.main()
