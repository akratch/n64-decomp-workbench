"""Tests for trace parsing and logical FIFO reconstruction."""

from __future__ import annotations

import unittest
from typing import Any, cast

from decomp_workbench.trace import (
    EMISSION_MAP_SCHEMA,
    alias_trace_summary,
    parse_emission_map,
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
            parse_trace(
                TRACE.replace(
                    "serial=1 line=700 reg=14",
                    "serial=1 line=700 reg=15",
                )
            )
        )
        self.assertFalse(report.valid)
        self.assertIn("FIFO head was t6", report.violations[0])

    def test_list_filter_keeps_allocations_and_matching_appends(self) -> None:
        events = parse_trace(
            "CODEX-UGEN-APPEND list=0x1000 reg=14\n"
            "CODEX-UGEN-APPEND list=0x2000 reg=15\n"
            "CODEX-UGEN-ALLOC serial=1 reg=14\n"
            "CODEX-UGEN-APPEND reg=14\n"
            "CODEX-UGEN-APPEND list=0x1000 reg=14\n"
        )
        report = replay_fifo(events, list_address=0x1000)
        self.assertTrue(report.valid, report.violations)
        self.assertEqual(report.initial_queue, [14])
        self.assertEqual(report.allocations, [14])
        self.assertEqual(report.final_queue, [14])
        self.assertEqual(report.ignored_events, 2)

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

    def test_normalizes_generic_freelist_events(self) -> None:
        events = parse_trace(
            "DKWB-FREELIST ALLOC reg=8\n"
            "DKWB-FREELIST ADD reg=9\n"
            "DKWB-FREELIST FREE reg=10\n"
            "DKWB-FREELIST FORCE_FREE reg=11\n"
            "DKWB-FREELIST REMOVE reg=12\n"
            "DKWB-FREELIST MOVE_END reg=13\n"
        )
        self.assertEqual(
            [event.action for event in events],
            [
                "allocate",
                "append",
                "append",
                "append",
                "remove",
                "move-end",
            ],
        )

    def test_joins_fifo_events_to_emitted_rows_and_source(self) -> None:
        events = parse_trace(
            "DKWB-FREELIST ADD reg=14 emitted=257\n"
            "DKWB-FREELIST ALLOC reg=14 emitted=258\n"
            "DKWB-FREELIST FREE reg=14 emitted=259\n"
        )
        emission_map = parse_emission_map(
            {
                "schema": EMISSION_MAP_SCHEMA,
                "entries": [
                    {
                        "emitted_index": 258,
                        "object_row": 700,
                        "source_file": "camera.c",
                        "source_line": 412,
                        "instruction": "sll t0,t1,2",
                    },
                    {
                        "emitted_index": 259,
                        "object_row": 701,
                        "source_file": "camera.c",
                        "source_line": 412,
                    },
                ],
            }
        )

        report = replay_fifo(events, emission_map=emission_map)

        self.assertTrue(report.valid, report.violations)
        allocation = report.logical_events[0]
        self.assertEqual(allocation.emitted_index, 258)
        self.assertEqual(allocation.object_row, 700)
        self.assertEqual(allocation.source_file, "camera.c")
        self.assertEqual(allocation.source_line, 412)
        self.assertEqual(allocation.instruction, "sll t0,t1,2")
        join = cast(dict[str, Any], report.as_dict()["emission_join"])
        self.assertTrue(join["complete"])
        self.assertEqual(join["with_instruction"], 1)

    def test_emitted_index_is_not_inferred_to_be_an_object_row(self) -> None:
        report = replay_fifo(
            parse_trace(
                "DKWB-FREELIST ADD reg=14 emitted=257\n"
                "DKWB-FREELIST ALLOC reg=14 emitted=258\n"
            )
        )
        event = report.logical_events[0]
        self.assertEqual(event.emitted_index, 258)
        self.assertIsNone(event.object_row)
        join = cast(dict[str, Any], report.as_dict()["emission_join"])
        self.assertTrue(join["calibration_required"])

    def test_emission_map_refuses_duplicate_ordinals(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicated"):
            parse_emission_map(
                {
                    "schema": EMISSION_MAP_SCHEMA,
                    "entries": [
                        {"emitted_index": 1, "object_row": 2},
                        {"emitted_index": 1, "object_row": 3},
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
