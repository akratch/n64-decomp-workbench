"""Stable scheduler records replace private unlabeled pointer dumps."""

from __future__ import annotations

import hashlib
import unittest

from decomp_workbench.scheduler import (
    PROFILE_SCHEMA,
    compare_scheduler_traces,
    instrument_scheduler_source,
    parse_scheduler_trace,
    scheduler_report,
)

TRACE = (
    "[DKWB-SCHED-V1] proc=7 block=3 cycle=4 word=0x2402002d "
    "opcode=addiu line=0x30f ready=2 chosen=n18 tie=source-line\n"
    "[DKWB-SCHED-V1] proc=7 block=3 cycle=5 word=0x2403000a "
    "opcode=addiu line=0x311 ready=1 chosen=n19 tie=only-ready\n"
)


class SchedulerTests(unittest.TestCase):
    def test_named_trace_reports_the_decisive_ready_set_tie(self) -> None:
        events, ignored = parse_scheduler_trace(TRACE)
        report = scheduler_report(events, proc=7, block=3)
        self.assertEqual(ignored, [])
        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["ready_set_ties"], 1)
        self.assertEqual(report["events"][0]["word"], "0x2402002d")
        self.assertEqual(report["events"][0]["tie"], "source-line")

    def test_diff_aligns_by_procedure_block_and_cycle(self) -> None:
        target, _ = parse_scheduler_trace(TRACE)
        candidate, _ = parse_scheduler_trace(
            TRACE.replace("chosen=n18", "chosen=n19").replace(
                "tie=source-line", "tie=scan-order"
            )
        )
        report = compare_scheduler_traces(target, candidate)
        self.assertEqual(report["difference_count"], 1)
        self.assertEqual(report["differences"][0]["changed"], ["chosen", "tie"])

    def test_parser_refuses_missing_or_duplicate_decisions(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing field"):
            parse_scheduler_trace(
                "[DKWB-SCHED-V1] proc=1 block=1 cycle=1 word=0 opcode=nop"
            )
        with self.assertRaisesRegex(ValueError, "repeats"):
            parse_scheduler_trace(TRACE + TRACE)
        with self.assertRaisesRegex(ValueError, "repeats field.*proc"):
            parse_scheduler_trace(TRACE.replace("proc=7", "proc=7 proc=8", 1))

    def test_external_profile_is_hash_and_anchor_guarded(self) -> None:
        source = "void choose(void) {\n    CHOOSE();\n}\n"
        trace = (
            '    LOG("[DKWB-SCHED-V1] proc=%d block=%d cycle=%d '
            'word=%x opcode=%s line=%d ready=%d chosen=%s tie=%s", '
            "proc, block, cycle, word, opcode, line, ready, chosen, tie);\n"
        )
        profile = {
            "schema": PROFILE_SCHEMA,
            "name": "synthetic-positive-control",
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "injections": [
                {
                    "anchor": "    CHOOSE();\n",
                    "position": "after",
                    "text": trace,
                }
            ],
        }
        instrumented, report = instrument_scheduler_source(source, profile)
        self.assertIn("[DKWB-SCHED-V1]", instrumented)
        self.assertEqual(report["injections"], 1)
        self.assertEqual(len(report["calibration_required"]), 5)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            instrument_scheduler_source(source + " ", profile)


if __name__ == "__main__":
    unittest.main()
