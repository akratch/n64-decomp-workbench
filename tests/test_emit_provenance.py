"""Tests for the ugen DKWB-EMIT-V1 emit-order provenance decoder."""

from __future__ import annotations

import unittest

from decomp_workbench.emit_provenance import (
    EmitEvent,
    emit_report,
    format_emit_report,
    line_order_conflicts,
    parse_emit_trace,
)

# The shape recorded from a real capture of `overlay40UpdateEntries`: an
# address materialisation at the assignment's line, a loop-count initialiser
# one line later, and the loop-invariant address hoisted into the preheader
# carrying the *loop header's* line rather than its own use site's.
PREHEADER = """\
DKWB-EMIT-V1 proc=0 block=0 emit=1 op=28 line=39 buffer=fwd fn=f_emit_dir2
DKWB-EMIT-V1 proc=0 block=0 emit=2 op=28 line=44 buffer=fwd fn=f_emit_dir2
DKWB-EMIT-V1 proc=0 block=0 emit=3 op=36 line=44 buffer=fwd fn=f_emit_ra
DKWB-EMIT-V1 proc=0 block=0 emit=4 op=28 line=45 buffer=fwd fn=f_emit_dir2
DKWB-EMIT-V1 proc=0 block=0 emit=5 op=41 line=45 buffer=fwd fn=f_emit_ri_
DKWB-EMIT-V1 proc=0 block=0 emit=6 op=28 line=46 buffer=fwd fn=f_emit_dir2
DKWB-EMIT-V1 proc=0 block=0 emit=7 op=36 line=46 buffer=fwd fn=f_emit_ra
DKWB-EMIT-V1 proc=0 block=1 emit=8 op=32 line=46 buffer=fwd fn=f_define_label
DKWB-EMIT-V1 proc=0 block=1 emit=9 op=37 line=47 buffer=fwd fn=f_emit_rab
"""


class ParseEmitTraceTest(unittest.TestCase):
    def test_parses_every_record_and_keeps_other_diagnostics(self) -> None:
        events, ignored = parse_emit_trace(
            "ugen: warning: line 45: something\n" + PREHEADER
        )
        self.assertEqual(len(events), 9)
        self.assertEqual(ignored, ["ugen: warning: line 45: something"])
        self.assertEqual(events[2].fn, "f_emit_ra")
        self.assertEqual(events[2].line, 44)
        self.assertEqual(events[2].buffer, "fwd")

    def test_finds_records_embedded_in_an_interleaved_line(self) -> None:
        # ugen's stderr is unbuffered and interleaves with the driver's, so a
        # record can start part-way through a line. Dropping those would
        # silently lose emits from exactly the busiest procedures.
        events, _ = parse_emit_trace(
            "cc: Warning: DKWB-EMIT-V1 proc=1 block=2 emit=3 op=4 line=5 "
            "buffer=fwd fn=f_emit_rr\n"
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].proc, 1)
        self.assertEqual(events[0].emit, 3)

    def test_backward_buffer_records_are_not_instructions(self) -> None:
        events, _ = parse_emit_trace(
            "DKWB-EMIT-V1 proc=0 block=0 emit=64999 op=4 line=71 "
            "buffer=back fn=f_demit_dir1\n"
        )
        self.assertFalse(events[0].is_instruction)

    def test_directive_emitters_are_not_instructions(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        by_emit = {event.emit: event for event in events}
        self.assertFalse(by_emit[2].is_instruction)
        self.assertFalse(by_emit[8].is_instruction)
        self.assertTrue(by_emit[3].is_instruction)

    def test_rejects_an_unknown_buffer(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown buffer"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 line=1 "
                "buffer=sideways fn=f_emit_rr\n"
            )

    def test_rejects_a_missing_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing field\\(s\\): line"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 buffer=fwd fn=f_emit_rr\n"
            )

    def test_rejects_an_unsupported_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): slot"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 line=1 buffer=fwd "
                "fn=f_emit_rr slot=3\n"
            )

    def test_rejects_a_repeated_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "repeats field\\(s\\): line"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 line=1 line=2 "
                "buffer=fwd fn=f_emit_rr\n"
            )

    def test_rejects_a_malformed_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed token"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 line=1 buffer=fwd f_emit_rr\n"
            )

    def test_rejects_a_negative_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative field 'line'"):
            parse_emit_trace(
                "DKWB-EMIT-V1 proc=0 block=0 emit=1 op=1 line=-1 buffer=fwd "
                "fn=f_emit_rr\n"
            )


class LineOrderConflictTest(unittest.TestCase):
    def test_reports_the_pair_whose_lines_decide_the_order(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        conflicts = line_order_conflicts(events)
        pairs = [(item["earlier"]["emit"], item["later"]["emit"]) for item in conflicts]
        # emit=5 (the count initialiser, line 45) before emit=7 (the hoisted
        # address, line 46) is the decision the residual turns on.
        self.assertIn((5, 7), pairs)
        self.assertIn((3, 5), pairs)

    def test_ignores_directives_and_crosses_no_block_boundary(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        conflicts = line_order_conflicts(events)
        for conflict in conflicts:
            self.assertEqual(conflict["earlier"]["block"], conflict["block"])
            self.assertTrue(conflict["earlier"]["is_instruction"])
            self.assertTrue(conflict["later"]["is_instruction"])
        # emit=7 (block 0, line 46) and emit=9 (block 1, line 47) are adjacent
        # instructions in emission order but sit in different blocks.
        self.assertNotIn(
            (7, 9),
            [(item["earlier"]["emit"], item["later"]["emit"]) for item in conflicts],
        )

    def test_equal_lines_are_not_a_conflict(self) -> None:
        # The lever this decoder exists to expose is putting two records on one
        # physical line. Once they share a line, the line key stops deciding
        # and the pair must stop being reported.
        tied = PREHEADER.replace(
            "emit=5 op=41 line=45", "emit=5 op=41 line=46"
        ).replace("emit=4 op=28 line=45", "emit=4 op=28 line=46")
        events, _ = parse_emit_trace(tied)
        pairs = [
            (item["earlier"]["emit"], item["later"]["emit"])
            for item in line_order_conflicts(events)
        ]
        self.assertNotIn((5, 7), pairs)


class EmitReportTest(unittest.TestCase):
    def test_groups_by_block_and_counts_only_instructions(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        report = emit_report(events)
        self.assertEqual(report["event_count"], 9)
        self.assertEqual(report["instruction_count"], 4)
        self.assertEqual(report["procedures"], [0])
        blocks = {item["block"]: item for item in report["blocks"]}
        self.assertEqual(blocks[0]["instruction_count"], 3)
        self.assertEqual(blocks[0]["lines"], [44, 45, 46])
        self.assertEqual(blocks[1]["instruction_count"], 1)

    def test_filters_by_procedure_and_block(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        report = emit_report(events, proc=0, block=1)
        self.assertEqual([item["block"] for item in report["blocks"]], [1])
        self.assertEqual(report["event_count"], 2)
        # The procedure list stays whole-trace so a filtered report still says
        # what else was captured.
        self.assertEqual(report["procedures"], [0])

    def test_proof_refuses_to_claim_scheduler_output(self) -> None:
        report = emit_report([])
        self.assertIn("ready list", report["proof"])
        self.assertIn("as1-reorganize", report["proof"])

    def test_rendered_report_marks_instructions_and_lists_conflicts(self) -> None:
        events, _ = parse_emit_trace(PREHEADER)
        text = format_emit_report(emit_report(events, proc=0, block=0))
        self.assertIn("I emit=5", text)
        self.assertIn(". emit=4", text)
        self.assertIn("line-order conflicts: 2", text)


class EmitEventTest(unittest.TestCase):
    def test_as_dict_carries_the_derived_instruction_flag(self) -> None:
        event = EmitEvent(
            proc=0, block=0, emit=3, op=36, line=44, buffer="fwd", fn="f_emit_ra"
        )
        self.assertTrue(event.as_dict()["is_instruction"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
