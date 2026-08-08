"""Allocator reports align semantic provenance and explain stack ownership."""

from __future__ import annotations

import unittest

from decomp_workbench.allocator_analysis import (
    compare_semantic_webs,
    origin_probe_report,
    semantic_webs,
    stack_home_report,
    web_report,
)
from decomp_workbench.globalcolor import parse_globalcolor_trace

TARGET = (
    "[CDX] webdetail proc=2 role=target web=15 sym=0 type=3 dtype=13 "
    "table=4 chain=7 exprtable=2 exprchain=1 bb=3 line=5 "
    "raw10=0xffffffc0 raw14=0x04ae0102\n"
    "[CDX] webdetail proc=2 role=target web=16 sym=42 type=3 dtype=13 "
    "table=5 chain=8 exprtable=2 exprchain=2 bb=3 line=6 "
    "raw10=0xffffffb8 raw14=0x04ae0102\n"
    "[CDX] webneighbor proc=2 web=15 neighbor=16\n"
    "[CDX] p2dec phase=p2 proc=2 web=15 bestcolor=1 "
    "forbidden0=0x20000000 decision=color\n"
    "[CDX] p2dec phase=p2 proc=2 web=16 bestcolor=2 "
    "forbidden0=0 decision=color\n"
)

CANDIDATE = (
    "[CDX] webdetail proc=2 role=target web=25 sym=0 type=3 dtype=13 "
    "table=4 chain=7 exprtable=2 exprchain=1 bb=3 line=5 "
    "raw10=0xffffffc0 raw14=0x04ae0102\n"
    "[CDX] webdetail proc=2 role=target web=26 sym=42 type=3 dtype=13 "
    "table=5 chain=8 exprtable=2 exprchain=2 bb=3 line=6 "
    "raw10=0xffffffb8 raw14=0x04ae0102\n"
    "[CDX] webneighbor proc=2 web=25 neighbor=26\n"
    "[CDX] p2dec phase=p2 proc=2 web=25 bestcolor=2 "
    "forbidden0=0x20000000 decision=color\n"
    "[CDX] p2dec phase=p2 proc=2 web=26 bestcolor=2 "
    "forbidden0=0 decision=color\n"
)


class AllocatorAnalysisTests(unittest.TestCase):
    def test_web_report_joins_run_local_formation_order(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] lineage_range proc=2 event=4 table=4 chain=7 "
            "type=3 dtype=13 sym=0 exprtable=2 exprchain=1\n"
            "[CDX] lineage_member proc=2 event=5 table=4 chain=7 "
            "type=3 dtype=13 sym=0 bb=8 line=5 flags=0,0,0,0,0,0\n"
            "[CDX] lineage_member proc=2 event=9 table=4 chain=7 "
            "type=3 dtype=13 sym=0 bb=11 line=5 flags=0,0,0,0,0,0\n"
            "[CDX] lineage_range proc=2 event=12 table=5 chain=8 "
            "type=3 dtype=13 sym=42 exprtable=2 exprchain=2\n"
            "[CDX] lineage_member proc=2 event=13 table=5 chain=8 "
            "type=3 dtype=13 sym=42 bb=11 line=6 flags=0,0,0,0,0,0\n" + TARGET
        )

        report = web_report(trace, proc=2)
        by_web = {item["numeric_web"]: item for item in report["webs"]}

        self.assertEqual(report["formation_captured_webs"], 2)
        self.assertEqual(by_web[15]["formation"]["range_event"], 4)
        self.assertEqual(by_web[15]["formation"]["formation_rank"], 1)
        self.assertEqual(by_web[15]["formation"]["first_member_bb"], 8)
        self.assertEqual(by_web[15]["formation"]["member_bbs"], [8, 11])
        self.assertEqual(by_web[16]["formation"]["formation_rank"], 2)
        self.assertEqual(by_web[15]["decision_trace_ordinal"], 1)
        self.assertEqual(by_web[16]["decision_trace_ordinal"], 2)
        self.assertEqual(by_web[15]["economics"], {})
        self.assertIn("construction chronology", report["formation_order_guidance"])
        self.assertIn("Economics reports", report["formation_order_guidance"])
        self.assertIn("observed p1dec/p2dec order", report["formation_order_guidance"])

    def test_web_report_exposes_the_mincost_tie_set_not_forbidden(self) -> None:
        # WB-65: `web_report`'s per-web JSON carries the correctly-named
        # `mincost_tie_colors`/`mincost_tie_registers` beside
        # `forbidden_colors`/`forbidden_registers`, sourced from the raw
        # `available0`/`1` fields but never called "available".
        trace = parse_globalcolor_trace(
            "[CDX] p1dec phase=p1 proc=2 web=15 bestcolor=26 bestreg=t3 "
            "forbidden0=0xd3 available0=0x1c decision=color\n"
        )
        report = web_report(trace, proc=2)
        item = report["webs"][0]
        self.assertEqual(item["mincost_tie_colors"], [27, 28, 29])
        self.assertEqual(
            item["mincost_tie_registers"],
            [
                {"color": 27, "register": None},
                {"color": 28, "register": None},
                {"color": 29, "register": None},
            ],
        )

    def test_web_report_requests_lineage_when_formation_is_absent(self) -> None:
        report = web_report(parse_globalcolor_trace(TARGET), proc=2)

        self.assertEqual(report["formation_captured_webs"], 0)
        self.assertEqual(report["webs"][0]["formation"]["status"], "not-captured")
        self.assertIn("CDX_LINEAGE_TABLES", report["formation_order_guidance"])

    def test_numeric_renumbering_does_not_change_fingerprints(self) -> None:
        target = semantic_webs(parse_globalcolor_trace(TARGET), proc=2)
        candidate = semantic_webs(parse_globalcolor_trace(CANDIDATE), proc=2)
        self.assertEqual(
            [item.fingerprint for item in target],
            [item.fingerprint for item in candidate],
        )
        self.assertEqual(sorted(item.decision.web for item in target), [15, 16])
        self.assertEqual(sorted(item.decision.web for item in candidate), [25, 26])

    def test_opaque_raw14_change_does_not_hide_allocator_delta(self) -> None:
        target = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=98 type=4 dtype=0 "
            "table=356 chain=0 exprtable=-1 exprchain=-1 bb=-1 "
            "raw10=0x01000000 raw14=0x10057298\n"
            "[CDX] p2dec phase=p2 proc=0 web=98 bestcolor=12 "
            "forbidden0=0x7ff3c000 decision=color\n"
        )
        candidate = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=0 web=60 bestcolor=12 "
            "forbidden0=0x7ff00000 decision=color\n"
            "[CDX] webdetail phase=p2 proc=0 role=target web=98 type=4 dtype=0 "
            "table=356 chain=0 exprtable=-1 exprchain=-1 bb=-1 "
            "raw10=0x01000000 raw14=0x10056bf8\n"
            "[CDX] intf phase=p2 proc=0 web=98 other=60 assigned=12\n"
            "[CDX] p2dec phase=p2 proc=0 web=98 bestcolor=18 "
            "forbidden0=0x7ffbc000 decision=color\n"
        )

        report = compare_semantic_webs(target, candidate, proc=0)
        pointer = next(
            row
            for row in report["differences"]
            if row["target"] and row["target"]["numeric_web"] == 98
        )
        self.assertNotIn("presence", pointer["changed"])
        self.assertEqual(
            pointer["changed"],
            ["assigned_color", "natural_color", "forbidden_colors"],
        )
        self.assertEqual(pointer["target"]["assigned_register"], "t5")
        self.assertEqual(pointer["candidate"]["assigned_register"], "s4")
        self.assertEqual(
            pointer["candidate_forbidden_causes"][0]["trace_local_neighbor"], 60
        )
        self.assertEqual(
            pointer["candidate_only_forbidden_causes"],
            [
                {
                    "color": 12,
                    "register": "t5",
                    "neighbor_fingerprint": pointer["candidate_forbidden_causes"][0][
                        "neighbor_fingerprint"
                    ],
                    "trace_local_neighbor": 60,
                }
            ],
        )
        self.assertIn("raw14", report["fingerprint_excluded_observations"])

    def test_zero_alignment_coverage_is_inconclusive_not_n_presence_claims(
        self,
    ) -> None:
        target = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=1 type=3 "
            "dtype=6 table=10 chain=0 bb=1\n"
            "[CDX] p2dec phase=p2 proc=0 web=1 bestcolor=12 decision=color\n"
        )
        candidate = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=9 type=3 "
            "dtype=6 table=99 chain=0 bb=4\n"
            "[CDX] p2dec phase=p2 proc=0 web=9 bestcolor=18 decision=color\n"
        )
        report = compare_semantic_webs(target, candidate, proc=0)
        self.assertEqual(report["alignment_status"], "no-common-fingerprints")
        self.assertEqual(report["common_fingerprints"], 0)
        self.assertEqual(report["alignment_coverage"], 0.0)
        self.assertIn("fingerprint churn", report["proof"])
        self.assertIn("trace-origin-probe", report["next_gate"])

    def test_alignment_coverage_counts_unique_webs_present_on_only_one_side(
        self,
    ) -> None:
        candidate = parse_globalcolor_trace(
            CANDIDATE + "[CDX] webdetail phase=p2 proc=2 role=target web=27 type=3 "
            "dtype=6 table=99 chain=0 bb=4\n"
            "[CDX] p2dec phase=p2 proc=2 web=27 bestcolor=3 decision=color\n"
        )

        report = compare_semantic_webs(
            parse_globalcolor_trace(TARGET), candidate, proc=2
        )

        self.assertEqual(report["common_fingerprints"], 2)
        self.assertEqual(report["alignment_denominator"], 3)
        self.assertAlmostEqual(report["alignment_coverage"], 2 / 3)
        self.assertEqual(report["alignment_status"], "partial")

    def test_distinct_webs_can_have_an_identical_decision_outcome(self) -> None:
        target = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=10 type=3 "
            "dtype=6 table=40 chain=0 bb=11\n"
            "[CDX] p2dec phase=p2 proc=0 web=10 bestcolor=15 "
            "decision=color\n"
            "[CDX] webdetail phase=p2 proc=0 role=target web=20 type=3 "
            "dtype=6 table=44 chain=0 bb=13\n"
            "[CDX] p2dec phase=p2 proc=0 web=20 bestcolor=16 "
            "decision=color\n"
        )
        candidate = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=80 type=4 "
            "dtype=6 table=140 chain=0 bb=11\n"
            "[CDX] p2dec phase=p2 proc=0 web=80 bestcolor=15 "
            "decision=color\n"
            "[CDX] webdetail phase=p2 proc=0 role=target web=90 type=4 "
            "dtype=6 table=144 chain=0 bb=13\n"
            "[CDX] p2dec phase=p2 proc=0 web=90 bestcolor=16 "
            "decision=color\n"
        )

        report = compare_semantic_webs(target, candidate, proc=0)

        self.assertEqual(report["alignment_status"], "no-common-fingerprints")
        self.assertEqual(report["outcome_schedule"]["status"], "identical")
        self.assertEqual(report["outcome_schedule"]["common_prefix"], 2)
        self.assertEqual(report["outcome_schedule"]["difference_count"], 0)
        self.assertEqual(report["outcome_schedule"]["target_phase_counts"], {"p2": 2})
        self.assertEqual(
            report["outcome_schedule"]["candidate_phase_counts"], {"p2": 2}
        )
        self.assertIn(
            "does not align semantic webs", report["outcome_schedule"]["proof"]
        )

    def test_missing_colors_cannot_claim_an_identical_outcome(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=10 type=3 "
            "dtype=6 table=40 chain=0 bb=11\n"
            "[CDX] p2dec phase=p2 proc=0 web=10 decision=color\n"
        )

        report = compare_semantic_webs(trace, trace, proc=0)

        self.assertEqual(report["outcome_schedule"]["status"], "incomplete-evidence")
        self.assertEqual(report["outcome_schedule"]["incomplete_rows"], 2)
        self.assertFalse(report["outcome_schedule"]["identical"])

    def test_decision_outcome_reports_first_divergence_and_count_changes(self) -> None:
        candidate = parse_globalcolor_trace(
            CANDIDATE + "[CDX] webdetail phase=p2 proc=2 role=target web=27 type=3 "
            "dtype=6 table=99 chain=0 bb=4\n"
            "[CDX] p2dec phase=p2 proc=2 web=27 bestcolor=3 decision=color\n"
        )

        report = compare_semantic_webs(
            parse_globalcolor_trace(TARGET), candidate, proc=2
        )["outcome_schedule"]

        self.assertEqual(report["status"], "count-mismatch")
        self.assertEqual(report["common_prefix"], 0)
        self.assertEqual(report["difference_count"], 2)

    def test_ambiguous_fingerprints_prevent_an_aligned_claim(self) -> None:
        duplicate = (
            "[CDX] p2dec phase=p2 proc=2 web=99 bestcolor=1 "
            "forbidden0=0x20000000 decision=color\n"
            "[CDX] webdetail proc=2 role=target web=99 sym=0 type=3 dtype=13 "
            "table=4 chain=7 exprtable=2 exprchain=1 bb=3 line=5 "
            "raw10=0xffffffc0 raw14=0x04ae0102\n"
        )

        report = compare_semantic_webs(
            parse_globalcolor_trace(TARGET + duplicate),
            parse_globalcolor_trace(CANDIDATE),
            proc=2,
        )

        self.assertTrue(report["ambiguous_fingerprints"])
        self.assertEqual(report["alignment_status"], "partial")
        self.assertIsNotNone(report["next_gate"])

    def test_empty_allocator_traces_report_no_evidence(self) -> None:
        empty = parse_globalcolor_trace("")

        report = compare_semantic_webs(empty, empty, proc=2)
        probe = origin_probe_report(empty, empty, proc=2, role="empty")

        self.assertEqual(report["alignment_status"], "no-evidence")
        self.assertIsNone(report["alignment_coverage"])
        self.assertEqual(probe["classification"], "no-evidence")
        self.assertEqual(probe["evidence_status"], "no-allocator-web-evidence")

    def test_semantic_diff_attributes_a_forbidden_color_to_its_neighbor(
        self,
    ) -> None:
        report = compare_semantic_webs(
            parse_globalcolor_trace(TARGET),
            parse_globalcolor_trace(CANDIDATE),
            proc=2,
        )
        changed = next(
            item
            for item in report["differences"]
            if "assigned_color" in item["changed"]
        )
        causes = changed["target_forbidden_causes"]
        self.assertEqual(causes[0]["color"], 2)
        self.assertEqual(causes[0]["register"], "v1")
        self.assertIn("neighbor_fingerprint", causes[0])

    def test_forbidproducer_records_are_joined_as_interference_causes(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=2 phase=p2 web=10 snapshot=preselect "
            "owner_sym=10 owner_type=3\n"
            "[CDX] provenance_web proc=2 phase=p2 web=10 snapshot=postselect "
            "owner_sym=10 owner_type=3\n"
            "[CDX] p2dec proc=2 phase=p2 web=10 bestcolor=2 "
            "forbidden0=0 decision=color\n"
            "[CDX] p2color proc=2 phase=p2 web=10 color=2 reg=v1\n"
            "[CDX] provenance_web proc=2 phase=p2 web=20 snapshot=preselect "
            "owner_sym=20 owner_type=4\n"
            "[CDX] provenance_web proc=2 phase=p2 web=20 snapshot=postselect "
            "owner_sym=20 owner_type=4\n"
            "[CDX] p2dec proc=2 phase=p2 web=20 bestcolor=3 "
            "forbidden0=0x20000000 decision=color\n"
            "[CDX] p2color proc=2 phase=p2 web=20 color=3 reg=a0\n"
            "[CDX] forbidproducer proc=2 phase=p2 web=20 color=2 "
            "producer_web=10 relation=direct-interference\n"
        )
        webs = semantic_webs(trace, proc=2)
        target = next(web for web in webs if web.decision.web == 20)
        self.assertEqual(target.neighbors, (10,))
        comparison = compare_semantic_webs(trace, parse_globalcolor_trace(""), proc=2)
        causes = next(
            row["target_forbidden_causes"]
            for row in comparison["differences"]
            if row["target"] and row["target"]["numeric_web"] == 20
        )
        self.assertEqual(causes[0]["register"], "v1")

    def test_stack_homes_name_virtual_ownership_without_inventing_layout(
        self,
    ) -> None:
        report = stack_home_report(parse_globalcolor_trace(TARGET), proc=2)
        self.assertEqual(report["capture_status"], "ready")
        self.assertIsNone(report["next_gate"])
        by_offset = {item["virtual_offset"]: item for item in report["homes"]}
        self.assertEqual(by_offset[-64]["kind"], "compiler-temporary")
        self.assertEqual(by_offset[-72]["kind"], "named-source-local")
        self.assertIsNone(by_offset[-64]["final_offset"])
        focused = stack_home_report(
            parse_globalcolor_trace(TARGET),
            proc=2,
            offset=-72,
        )
        self.assertEqual(focused["selected_count"], 1)
        self.assertEqual(focused["homes"][0]["symbol"], "42")

    def test_stack_homes_explain_when_profile_has_only_opaque_words(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] webdetail phase=p2 proc=0 role=target web=62 "
            "sym=62 type=3 dtype=6 raw10=0xffffffe4 raw14=0x00070102\n"
            "[CDX] p2dec phase=p2 proc=0 web=62 bestcolor=12 decision=color\n"
        )
        report = stack_home_report(trace, proc=0)
        self.assertEqual(report["allocator_web_count"], 1)
        self.assertEqual(report["home_count"], 0)
        self.assertEqual(report["capture_status"], "no-stack-home-evidence")
        self.assertIn(
            "current globalcolor profile cannot answer", str(report["next_gate"])
        )
        self.assertIn("raw10/raw14 are opaque", str(report["next_gate"]))

    def test_neighbor_identity_is_phase_qualified(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] webdetail phase=p1 proc=3 role=target web=9 "
            "dtype=1 table=1 chain=1 bb=1\n"
            "[CDX] webdetail phase=p2 proc=3 role=target web=9 "
            "dtype=2 table=2 chain=2 bb=2\n"
            "[CDX] intf phase=p1 proc=3 web=9 other=10\n"
            "[CDX] intf phase=p2 proc=3 web=9 other=11\n"
            "[CDX] p1dec phase=p1 proc=3 web=9 bestcolor=1 decision=color\n"
            "[CDX] p2dec phase=p2 proc=3 web=9 bestcolor=2 decision=color\n"
        )
        by_phase = {
            item.decision.phase_tag: item for item in semantic_webs(trace, proc=3)
        }
        self.assertEqual(by_phase["p1"].neighbors, (10,))
        self.assertEqual(by_phase["p2"].neighbors, (11,))
        self.assertEqual(by_phase["p1"].decision.dtype, 1)
        self.assertEqual(by_phase["p2"].decision.dtype, 2)

    def test_owner_line_and_lineage_do_not_claim_source_attribution(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] webdetail proc=3 role=owner web=9 dtype=13 bb=4 "
            "line=20 lineage=frontend-a owner=42\n"
            "[CDX] p1dec phase=p1 proc=3 web=9 bestcolor=1 decision=color\n"
        )
        web = semantic_webs(trace, proc=3)[0]
        self.assertEqual(
            web.source_attribution["classification"], "run-local-unattributed"
        )
        self.assertIn("source_semantic", web.source_attribution["next_gate"])
        report = web_report(trace, proc=3)
        self.assertEqual(report["run_local_unattributed_webs"], 1)
        self.assertIn("source_semantic", report["next_gate"])

    def test_unavailable_source_semantic_remains_run_local(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=3 phase=p1 web=9 snapshot=preselect "
            "source_semantic=unavailable "
            "semantic_reason=no-source-metadata-at-globalcolor owner_sym=17 "
            "owner_type=3 owner_dtype=13 primary_ichain_table=4 "
            "primary_ichain_chain=7 expr_table=2 expr_chain=1 ir_bb=9 "
            "source_span=20:24 merge_lineage=42 merge_lineage_scope=local\n"
            "[CDX] provenance_web proc=3 phase=p1 web=9 snapshot=postselect "
            "source_semantic=unavailable "
            "semantic_reason=no-source-metadata-at-globalcolor owner_sym=17 "
            "owner_type=3 owner_dtype=13 primary_ichain_table=4 "
            "primary_ichain_chain=7 expr_table=2 expr_chain=1 ir_bb=9 "
            "source_span=20:24 merge_lineage=42 merge_lineage_scope=local\n"
            "[CDX] p1dec phase=p1 proc=3 web=9 bestcolor=1 decision=color\n"
        )
        web = semantic_webs(trace, proc=3)[0]
        self.assertEqual(
            web.source_attribution["classification"], "run-local-unattributed"
        )
        self.assertIn("source_semantic", web.source_attribution["next_gate"])
        self.assertEqual(
            web.provenance,
            {
                "owner_sym": "17",
                "owner_type": "3",
                "owner_dtype": "13",
                "primary_ichain_table": "4",
                "primary_ichain_chain": "7",
                "expr_table": "2",
                "expr_chain": "1",
                "ir_bb": "9",
                "source_span": "20:24",
                "merge_lineage": "42",
                "merge_lineage_scope": "local",
                "semantic_reason": "no-source-metadata-at-globalcolor",
            },
        )
        self.assertNotIn("source_semantic", web.provenance)

    def test_direct_source_semantic_unlocks_source_attribution(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=3 phase=p2 web=62 snapshot=preselect "
            "source_semantic=local:pending-flag semantic_reason=ir-local\n"
            "[CDX] provenance_web proc=3 phase=p2 web=62 snapshot=postselect "
            "source_semantic=local:pending-flag semantic_reason=ir-local\n"
            "[CDX] p2dec phase=p2 proc=3 web=62 bestcolor=1 decision=color\n"
        )
        web = semantic_webs(trace, proc=3)[0]
        self.assertEqual(
            web.source_attribution,
            {
                "classification": "source-attributed",
                "source_semantic": "local:pending-flag",
            },
        )

    def test_direct_source_semantic_participates_in_web_identity(self) -> None:
        first = parse_globalcolor_trace(
            "[CDX] provenance_web proc=3 phase=p2 web=62 snapshot=preselect "
            "source_semantic=local:first semantic_reason=ir-local\n"
            "[CDX] provenance_web proc=3 phase=p2 web=62 snapshot=postselect "
            "source_semantic=local:first semantic_reason=ir-local\n"
            "[CDX] p2dec phase=p2 proc=3 web=62 bestcolor=1 decision=color\n"
        )
        second = parse_globalcolor_trace(
            "[CDX] provenance_web proc=3 phase=p2 web=99 snapshot=preselect "
            "source_semantic=local:second semantic_reason=ir-local\n"
            "[CDX] provenance_web proc=3 phase=p2 web=99 snapshot=postselect "
            "source_semantic=local:second semantic_reason=ir-local\n"
            "[CDX] p2dec phase=p2 proc=3 web=99 bestcolor=1 decision=color\n"
        )

        first_web = semantic_webs(first, proc=3)[0]
        second_web = semantic_webs(second, proc=3)[0]

        self.assertNotEqual(first_web.fingerprint, second_web.fingerprint)

    def test_origin_probe_classifies_one_web_removal_without_source_claim(self) -> None:
        report = origin_probe_report(
            parse_globalcolor_trace(TARGET),
            parse_globalcolor_trace(
                "[CDX] webdetail proc=2 role=target web=25 sym=0 type=3 dtype=13 "
                "table=4 chain=7 exprtable=2 exprchain=1 bb=3 line=5 "
                "raw10=0xffffffc0 raw14=0x04ae0102\n"
                "[CDX] p2dec phase=p2 proc=2 web=25 bestcolor=1 "
                "forbidden0=0x20000000 decision=color\n"
            ),
            proc=2,
            role="texture-value",
            source_semantic="local:texture-value",
            synthetic=True,
        )
        self.assertEqual(report["classification"], "isolated-removal")
        self.assertEqual(report["claim_scope"], "synthetic-calibration")
        self.assertEqual(report["counts"]["formation_removed"], 1)
        self.assertEqual(report["counts"]["producer_source_attributed_webs"], 0)
        self.assertIn("do not survive arbitrary", report["proof"])

    def test_origin_probe_with_color_cascade_is_ambiguous(self) -> None:
        report = origin_probe_report(
            parse_globalcolor_trace(TARGET),
            parse_globalcolor_trace(
                "[CDX] webdetail proc=2 role=target web=25 sym=0 type=3 dtype=13 "
                "table=4 chain=7 exprtable=2 exprchain=1 bb=3 line=5 "
                "raw10=0xffffffc0 raw14=0x04ae0102\n"
                "[CDX] p2dec phase=p2 proc=2 web=25 bestcolor=2 "
                "forbidden0=0x20000000 decision=color\n"
            ),
            proc=2,
            role="texture-value",
        )
        self.assertEqual(report["classification"], "ambiguous")
        self.assertEqual(report["counts"]["common_web_color_changes"], 1)

    def test_origin_probe_names_color_only_cascade_and_requires_object_check(
        self,
    ) -> None:
        baseline = parse_globalcolor_trace(
            "[CDX] webdetail proc=2 role=target web=25 type=3 dtype=13 "
            "table=4 chain=7 exprtable=2 exprchain=1 bb=3\n"
            "[CDX] p2dec phase=p2 proc=2 web=25 bestcolor=1 "
            "forbidden0=0x20000000 decision=color\n"
        )
        variant = parse_globalcolor_trace(
            "[CDX] webdetail proc=2 role=target web=25 type=3 dtype=13 "
            "table=4 chain=7 exprtable=2 exprchain=1 bb=3\n"
            "[CDX] p2dec phase=p2 proc=2 web=25 bestcolor=2 "
            "forbidden0=0x20000000 decision=color\n"
        )
        report = origin_probe_report(baseline, variant, proc=2, role="forced-color")
        self.assertEqual(report["classification"], "allocation-cascade-only")
        self.assertIn("forced color is diagnostic", report["cascade_warning"])
        self.assertIn("Re-compare the compiled object", report["next_gate"])

    def test_origin_probe_economics_survives_ichain_renumbering(self) -> None:
        baseline = parse_globalcolor_trace(
            "[CDX] webdetail proc=2 role=target web=62 type=3 dtype=6 "
            "table=688 chain=0 bb=11\n"
            "[CDX] p2dec phase=p2 proc=2 web=62 class=1 save=100.0 "
            "nocs=1 totalsave=100.0 numintf=19 bestcolor=12 "
            "forbidden0=0x7ff00000 decision=color\n"
        )
        variant = parse_globalcolor_trace(
            "[CDX] webdetail proc=2 role=target web=29 type=3 dtype=6 "
            "table=901 chain=4 bb=2\n"
            "[CDX] p2dec phase=p2 proc=2 web=29 class=1 save=100.0 "
            "nocs=1 totalsave=100.0 numintf=19 bestcolor=5 "
            "forbidden0=0x7a000000 decision=color\n"
        )
        report = origin_probe_report(baseline, variant, proc=2, role="induction-owner")
        self.assertEqual(report["counts"]["unique_economics_transitions"], 1)
        self.assertEqual(report["counts"]["allocation_economics_transitions"], 1)
        self.assertEqual(report["counts"]["economics_renumber_only"], 0)
        transition = report["unique_economics_transitions"][0]
        self.assertEqual(transition["baseline"]["trace_local_web"], 62)
        self.assertEqual(transition["variant"]["trace_local_web"], 29)
        self.assertEqual(transition["baseline"]["natural_register"], "t5")
        self.assertEqual(transition["variant"]["natural_register"], "a2")

    def test_origin_probe_separates_web_renumbering_from_allocation_change(
        self,
    ) -> None:
        baseline = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=2 web=62 class=1 save=100.0 "
            "nocs=1 totalsave=100.0 numintf=19 bestcolor=12 "
            "forbidden0=0x7ff00000 decision=color\n"
        )
        variant = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=2 web=29 class=1 save=100.0 "
            "nocs=1 totalsave=100.0 numintf=19 bestcolor=12 "
            "forbidden0=0x7ff00000 decision=color\n"
        )
        report = origin_probe_report(baseline, variant, proc=2, role="renumber")
        self.assertEqual(report["counts"]["unique_economics_transitions"], 1)
        self.assertEqual(report["counts"]["allocation_economics_transitions"], 0)
        self.assertEqual(report["counts"]["economics_renumber_only"], 1)
        self.assertEqual(report["allocation_economics_transitions"], [])


if __name__ == "__main__":
    unittest.main()
