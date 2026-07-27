"""Tests for trace parsing and logical FIFO reconstruction."""

from __future__ import annotations

import unittest

from decomp_workbench.trace import (
    alias_trace_summary,
    parse_register,
    parse_trace,
    replay_fifo,
    trace_summary,
)


TRACE = """\
noise from the compiler
CODEX-UGEN-APPEND line=182 list=10019da4 reg=14
CODEX-UGEN-APPEND line=182 list=10019da4 reg=15
CODEX-UGEN-ALLOC serial=1 line=700 reg=14
CODEX-UGEN-ALLOC serial=2 line=701 reg=15
CODEX-UGEN-APPEND line=702 list=10019da4 reg=14
CODEX-UGEN-ALLOC serial=3 line=703 reg=14
CODEX-UGEN-APPEND line=704 list=10019da4 reg=15
CODEX-UGEN-APPEND line=705 list=10019da4 reg=14
"""


class TraceTests(unittest.TestCase):
    def test_parses_historical_trace(self) -> None:
        events = parse_trace(TRACE)
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0].action, "append")
        self.assertEqual(events[0].list_address, 0x10019DA4)
        self.assertEqual(events[2].serial, 1)
        self.assertEqual(events[2].register, 14)

    def test_reconstructs_logical_values(self) -> None:
        report = replay_fifo(parse_trace(TRACE))
        self.assertTrue(report.valid, report.violations)
        self.assertEqual(report.initial_queue, [14, 15])
        self.assertEqual(report.allocations, [14, 15, 14])
        self.assertEqual(report.final_queue, [15, 14])
        self.assertEqual(report.max_live, 2)
        self.assertEqual(
            [(item.action, item.value) for item in report.logical_events],
            [
                ("allocate", 1),
                ("allocate", 2),
                ("free", 1),
                ("allocate", 3),
                ("free", 2),
                ("free", 3),
            ],
        )

    def test_reports_fifo_violation(self) -> None:
        report = replay_fifo(
            parse_trace(TRACE.replace("serial=1 line=700 reg=14", "serial=1 line=700 reg=15"))
        )
        self.assertFalse(report.valid)
        self.assertIn("FIFO head was t6", report.violations[0])

    def test_summary_and_register_names(self) -> None:
        summary = trace_summary(parse_trace(TRACE))
        self.assertEqual(summary["actions"], {"allocate": 3, "append": 5})
        self.assertEqual(parse_register("$t6"), 14)
        self.assertEqual(parse_register("14"), 14)

    def test_summarizes_alias_profile(self) -> None:
        events = parse_trace(
            "DKWB-BASE ordinal=0 reg=16 kind=3 type=isvar sym=7 "
            "addr=4096 hadbase=0 path=fresh\n"
            "DKWB-ALIAS-QUERY ordinal=0 reg=16 result=no-alias "
            "left_kind=3 left_type=isvar left_sym=7 left_addr=4096 "
            "right_kind=1 right_type=islda right_sym=8 right_addr=8192\n"
        )
        report = alias_trace_summary(events)
        self.assertEqual([event.action for event in events], ["base", "alias-query"])
        self.assertEqual(report["base_paths"], {"fresh": 1})
        self.assertEqual(report["query_results"], {"no-alias": 1})
        self.assertEqual(report["registers"], {"s0": 2})


if __name__ == "__main__":
    unittest.main()
