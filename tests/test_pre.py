"""PRE provenance names the optimization decision before allocator effects."""

from __future__ import annotations

import hashlib
import unittest

from decomp_workbench.pre import (
    PROFILE_SCHEMA,
    compare_pre_traces,
    instrument_pre_source,
    parse_pre_trace,
    pre_report,
)

TRACE = (
    "noise\n"
    "[DKWB-PRE-V1] proc=2 block=7 expression=e41 decision=hoist "
    "reason=fully_available line=80 candidate=header availability=all cost=3\n"
    "[DKWB-PRE-V1] proc=2 block=9 expression=e52 decision=reject "
    "reason=unsafe_edge line=84 candidate=preheader availability=partial\n"
)


class PreTraceTests(unittest.TestCase):
    def test_parser_keeps_named_decisions_and_ignores_noise(self) -> None:
        events, ignored = parse_pre_trace(TRACE)
        self.assertEqual(len(events), 2)
        self.assertEqual(ignored, ["noise"])
        self.assertEqual(events[0].decision, "hoist")
        self.assertEqual(events[0].cost, 3)
        report = pre_report(events, proc=2)
        self.assertEqual(report["decisions"], {"hoist": 1, "reject": 1})

    def test_diff_aligns_by_procedure_block_and_expression(self) -> None:
        target, _ = parse_pre_trace(TRACE)
        candidate, _ = parse_pre_trace(
            TRACE.replace(
                "decision=hoist reason=fully_available", "decision=reject reason=cost"
            )
        )
        report = compare_pre_traces(target, candidate)
        self.assertEqual(report["difference_count"], 1)
        self.assertEqual(report["differences"][0]["changed"], ["decision", "reason"])

    def test_duplicate_identity_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "repeats proc/block/expression"):
            parse_pre_trace(TRACE + TRACE.splitlines()[1] + "\n")

    def test_unknown_decision_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported decision"):
            parse_pre_trace(TRACE.replace("decision=hoist", "decision=maybe"))

    def test_unparsed_tokens_and_unknown_fields_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed token"):
            parse_pre_trace(TRACE.replace("proc=2", "proc=2 garbage", 1))
        with self.assertRaisesRegex(ValueError, "unsupported field"):
            parse_pre_trace(TRACE.replace("proc=2", "proc=2 surprise=yes", 1))

    def test_negative_coordinates_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative field"):
            parse_pre_trace(TRACE.replace("block=7", "block=-1", 1))


class PreInstrumentationTests(unittest.TestCase):
    def test_profile_is_hash_pinned_and_all_required_fields_are_present(self) -> None:
        source = "static void optimize(void) {\n    choose();\n}\n"
        record = (
            'fprintf(stderr, "[DKWB-PRE-V1] proc=%d block=%d '
            'expression=%s decision=%s reason=%s line=%d\\n", '
            "proc, block, expression, decision, reason, line);\n"
        )
        profile = {
            "schema": PROFILE_SCHEMA,
            "name": "synthetic-pre",
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "injections": [
                {"anchor": "    choose();\n", "position": "before", "text": record}
            ],
        }
        instrumented, report = instrument_pre_source(source, profile)
        self.assertIn("[DKWB-PRE-V1]", instrumented)
        self.assertEqual(report["injections"], 1)
        self.assertIn("tracing-off section identity", report["calibration_required"])

    def test_profile_refuses_changed_source(self) -> None:
        source = "void f(void) {}\n"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            instrument_pre_source(
                source,
                {
                    "schema": PROFILE_SCHEMA,
                    "source_sha256": "0" * 64,
                    "injections": [{}],
                },
            )

    def test_required_tokens_must_come_from_the_injection(self) -> None:
        required = " ".join(
            [
                "[DKWB-PRE-V1]",
                "proc=",
                "block=",
                "expression=",
                "decision=",
                "reason=",
                "line=",
            ]
        )
        source = f"/* {required} */\nvoid f(void) {{}}\n"
        profile = {
            "schema": PROFILE_SCHEMA,
            "name": "empty-record",
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "injections": [
                {"anchor": "void f", "position": "before", "text": "/* no trace */\n"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "does not emit required token"):
            instrument_pre_source(source, profile)


if __name__ == "__main__":
    unittest.main()
