"""Synthetic metadata for the source-pinned AS1 predicate profile."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from decomp_workbench.as1_predicates import (
    compare_queries,
    decode_register_mask,
    predicate_report,
)
from decomp_workbench.instrument_as1_motion import (
    AS1_SHA256,
    MARKER,
    _function,
    _instrument_admission,
    _replace,
    instrument_as1_motion,
)

PROFILE = f"DKWB-AS1-PROFILE version=1 source_sha256={AS1_SHA256} invocation=1\n"
COMMON = "invocation=1 query=5 src=9 dst=3 "
PRED = "DKWB-AS1-PRED " + COMMON + "slot=2 site=admit-00 value=1 v0=0\n"
RESULT = "DKWB-AS1-RESULT " + COMMON + "slot=2\n"
COST = (
    "DKWB-AS1-COST " + COMMON + "outcome={outcome} src_slot=2 dst_slot=3 "
    "src_old=4 dst_old=3 src_new=3 dst_new=3 context=1\n"
)
MASK = (
    "DKWB-AS1-MASK " + COMMON + "slot=2 kind=aggregate block=0 instruction=0 "
    "candidate_def0=32768 candidate_def1=0 candidate_def2=0 "
    "path_def0=32768 path_def1=0 path_def2=0\n"
)
TRACE = (
    PROFILE
    + PRED
    + MASK
    + RESULT
    + COST.format(outcome="trial")
    + COST.format(outcome="accepted")
)


class PredicateReaderTests(unittest.TestCase):
    def test_accepted_preserves_raw_predicates_and_masks(self) -> None:
        query = predicate_report(TRACE)["queries"][0]
        self.assertEqual(query["status"], "accepted")
        self.assertEqual(query["predicates"][0]["value"], 1)
        self.assertEqual(query["masks"][0]["intersection_register_ids"], [16])

    def test_rollback_is_explicit_not_inferred_from_cost(self) -> None:
        report = predicate_report(TRACE.replace("outcome=accepted", "outcome=rollback"))
        self.assertEqual(report["queries"][0]["status"], "rollback")

    def test_no_candidate_result_is_distinct_from_rollback(self) -> None:
        report = predicate_report(PROFILE + PRED + RESULT.replace("slot=2", "slot=0"))
        self.assertEqual(report["queries"][0]["status"], "no-candidate-admitted")

    def test_no_records_is_not_absence_claim(self) -> None:
        self.assertEqual(predicate_report("unrelated\n")["queries"], [])

    def test_repeated_predicates_are_not_collapsed(self) -> None:
        query = predicate_report(TRACE.replace(PRED, PRED * 2))["queries"][0]
        self.assertEqual(len(query["predicates"]), 2)

    def test_truncations_and_out_of_order_refuse(self) -> None:
        for trace in [
            PROFILE + PRED,
            PROFILE + PRED + RESULT,
            TRACE.replace(RESULT, ""),
            TRACE + PRED,
            TRACE + RESULT,
            TRACE.replace("outcome=trial", "outcome=accepted"),
        ]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                predicate_report(trace)

    def test_wrong_profile_fields_and_interleaving_refuse(self) -> None:
        for trace in [
            TRACE.replace(AS1_SHA256, "0" * 64),
            TRACE.replace("version=1", "version=2"),
            TRACE.replace(PROFILE, ""),
            TRACE.replace(PRED, "native " + PRED),
            TRACE.replace("value=1", "value=-1"),
            TRACE.replace("value=1", "value=2"),
            TRACE.replace("site=admit-00", "site=admit-99"),
            TRACE.replace("v0=0", "unexpected=0"),
            TRACE.replace("v0=0", "v0=0 v0=0"),
            TRACE.replace(PROFILE, PROFILE * 2),
        ]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                predicate_report(trace)

    def test_endpoint_and_cost_conflicts_refuse(self) -> None:
        for trace in [
            TRACE.replace(MASK, MASK.replace("src=9", "src=8")),
            TRACE.replace(
                COST.format(outcome="accepted"),
                COST.format(outcome="accepted").replace("src_new=3", "src_new=2"),
            ),
            TRACE.replace("src_slot=2", "src_slot=3"),
        ]:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                predicate_report(trace)

    def test_register_masks_are_msb_first(self) -> None:
        self.assertEqual(
            decode_register_mask([0x4000, 0x80000000, 0x80000000]), [17, 32, 64]
        )
        for words in [[], [0, 0, -1], [0, 0, 1 << 32]]:
            with self.assertRaises(ValueError):
                decode_register_mask(words)

    def test_candidate_comparison_requires_explicit_existing_slots(self) -> None:
        query = predicate_report(TRACE)["queries"][0]
        report = compare_queries(query, query, 2, 2)
        self.assertEqual(report["left"], report["right"])
        self.assertIn("unproved", report["comparison_basis"])
        for slot in [0, 3]:
            with self.assertRaises(ValueError):
                compare_queries(query, query, slot, 2)


class InstrumentationTests(unittest.TestCase):
    def test_unknown_and_already_instrumented_source_refuse(self) -> None:
        for source in ["invented source", MARKER]:
            with self.assertRaises(ValueError):
                instrument_as1_motion(source)

    def test_synthetic_complete_profile_preserves_original_branches(self) -> None:
        def function(name: str, body: str) -> str:
            return f"static uint32_t {name}(uint32_t a0) {{\n{body}\n}}\n"

        branch = "if (v0 == 0) {\ngoto done;}\n"
        source = (
            '#include "header.h"\n'
            + function(
                "func_42a028",
                branch * 29 + "v0 = func_429928(mem, sp, a0, a1, a2, a3);\nL42a44c:\n",
            )
            + function("func_429928", branch * 30 + "L429c14:\nL429cac:\n")
            + function("f_do_xbb_opt", "return 0;")
            + function("func_42aa0c", "L42ae90:\nL42aedc:\nL42afe8:\n")
        )
        # The public API still rejects unknown source; only this synthetic test
        # replaces the expected digest, never a user-facing force option.
        with patch(
            "decomp_workbench.instrument_as1_motion.AS1_SHA256",
            hashlib.sha256(source.encode()).hexdigest(),
        ):
            result = instrument_as1_motion(source)
        self.assertEqual(len(result.predicates), 59)
        self.assertEqual(result.source.count(branch), 59)
        self.assertEqual(result.source.count("DKWB-AS1-COST"), 3)
        self.assertEqual(result.source.count("DKWB-AS1-MASK"), 2)
        self.assertIn("DKWB-AS1-PROFILE", result.source)
        self.assertIn("getenv", result.source)

    def test_unique_anchor_required(self) -> None:
        for source in ["absent", "anchor anchor"]:
            with self.assertRaises(ValueError):
                _replace(source, "anchor", "new")
        self.assertEqual(_replace("anchor", "anchor", "new"), "new")

    def test_unique_function_required(self) -> None:
        source = "static uint32_t invented(uint32_t a0) {\nreturn a0;\n}\n"
        self.assertEqual(_function(source, "invented"), (0, len(source)))
        for value in ["", source * 2]:
            with self.assertRaises(ValueError):
                _function(value, "invented")

    def test_branch_hook_reads_without_rewriting_condition(self) -> None:
        body = (
            "static uint32_t invented(uint32_t a0) {\n"
            "if (v0 == 0) {\ngoto end;}\n"
            "v0 = func_429928(mem, sp, a0, a1, a2, a3);\n"
            "L42a44c:\nreturn v0;\n}\n"
        )
        result, sites = _instrument_admission(body, expected=1)
        self.assertEqual(result.count("if (v0 == 0) {"), 1)
        self.assertIn("dkwb_as1_selected", result)
        self.assertEqual(sites[0]["condition"], "v0 == 0")
        self.assertEqual(sites[0]["operands"], ["v0"])
        with self.assertRaises(ValueError):
            _instrument_admission(body, expected=2)
        for expression in ["evil(v0) == 0", "v0++ == 0", "v0 = 0"]:
            with self.assertRaises(ValueError):
                _instrument_admission(body.replace("v0 == 0", expression), expected=1)


if __name__ == "__main__":
    unittest.main()
