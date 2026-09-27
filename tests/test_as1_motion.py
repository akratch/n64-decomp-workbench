"""Invented native-format traces; no compiler or game instruction payload."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.as1_motion import (
    compare_motion_traces,
    motion_report,
    parse_motion_trace,
)
from decomp_workbench.cli import main

PAIR = (
    "MOVETO bb 4 inst 2  time: old 6, new 6\n"
    "MOVEFROM bb 9, inst 1  time: old 4, new 3\n"
)
DUMPS = """----- basic block instruction moved to -----
 INST 1: !# 26
 INST 2: Line 12: 0x24020001 invented
----- basic block instruction moved from -----
 INST 1: !Line 12: 0000000000 invented
"""


class NativeMotionTests(unittest.TestCase):
    def test_actual_pair_carries_both_blocks_and_costs(self) -> None:
        row = motion_report(PAIR + DUMPS)["events"][0]
        self.assertEqual(row["source"]["block"], 9)
        self.assertEqual(row["destination"]["block"], 4)
        self.assertEqual(row["cost"]["sum_reduction"], 1)
        self.assertEqual(row["cost"]["destination_increase"], 0)
        self.assertEqual(row["moved_instruction"]["line"], 12)
        self.assertTrue(row["source_after"][0]["native_marked"])
        self.assertTrue(row["destination_after"][0]["native_marked"])

    def test_low_debug_level_has_pair_but_no_invented_instruction(self) -> None:
        row = motion_report(PAIR)["events"][0]
        self.assertIsNone(row["moved_instruction"])
        self.assertFalse(row["destination_dump_present"])

    def test_reused_block_ids_remain_separate_events(self) -> None:
        report = motion_report((PAIR + DUMPS) * 2)
        self.assertEqual([row["event"] for row in report["events"]], [0, 1])
        self.assertIn("unavailable", report["capabilities"]["procedure_and_round"])

    def test_absence_does_not_claim_no_motion(self) -> None:
        report = motion_report("Initial nodes:\n")
        self.assertEqual(report["status"], "no-native-move-records")
        self.assertIn("no event does not prove", report["capabilities"]["absence"])

    def test_truncated_and_orphan_pairs_refuse(self) -> None:
        for value in [
            PAIR.splitlines()[0],
            PAIR.splitlines()[1],
            PAIR.splitlines()[0] + "\n" + PAIR,
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_motion_trace(value)

    def test_malformed_fields_and_zero_slots_refuse(self) -> None:
        for old, new in [("inst 2", "inst 0"), ("old 6", "old x"), ("bb 4", "bb -4")]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                parse_motion_trace(PAIR.replace(old, new))

    def test_dump_without_decision_refuses(self) -> None:
        with self.assertRaises(ValueError):
            parse_motion_trace(DUMPS)

    def test_duplicate_and_missing_dump_slots_refuse(self) -> None:
        for value in [
            DUMPS.replace("INST 2", "INST 1"),
            DUMPS.replace("INST 2", "INST 3"),
            DUMPS.split(" INST 2:")[0],
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_motion_trace(PAIR + value)

    def test_duplicate_dump_refuses(self) -> None:
        with self.assertRaises(ValueError):
            parse_motion_trace(PAIR + DUMPS + DUMPS)

    def test_unknown_instruction_form_does_not_look_complete(self) -> None:
        with self.assertRaises(ValueError):
            parse_motion_trace(PAIR + DUMPS.replace("Line 12:", "Unknown 12:"))

    def test_line_filter_does_not_use_call_or_region_inference(self) -> None:
        self.assertEqual(len(motion_report(PAIR + DUMPS, line=12)["events"]), 1)
        self.assertEqual(motion_report(PAIR + DUMPS, line=13)["events"], [])
        self.assertEqual(motion_report(PAIR, line=12)["events"], [])

    def test_diff_requires_explicit_event_pair_and_keeps_identity_limit(self) -> None:
        report = compare_motion_traces(
            PAIR + DUMPS, PAIR.replace("new 3", "new 2") + DUMPS, 0, 0
        )
        self.assertEqual(report["changed"], ["source", "cost"])
        self.assertIn("identity unproved", report["comparison_basis"])
        self.assertEqual(compare_motion_traces(PAIR, PAIR, 0, 0)["changed"], [])
        for event in [-1, 1]:
            with self.assertRaises(ValueError):
                compare_motion_traces(PAIR, PAIR, event, 0)

    def test_cli_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.log"
            path.write_text(PAIR + DUMPS)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["trace-as1-motion", str(path), "--json"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["event_count"], 1)
            for extra in [
                ["--against", str(path)],
                ["--against-event", "0"],
                ["--event", "-1"],
                ["--line", "-1"],
            ]:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["trace-as1-motion", str(path), *extra]), 2)


if __name__ == "__main__":
    unittest.main()
