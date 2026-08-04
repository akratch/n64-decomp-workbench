"""Allocator reports align semantic provenance and explain stack ownership."""

from __future__ import annotations

import unittest

from decomp_workbench.allocator_analysis import (
    compare_semantic_webs,
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
    def test_numeric_renumbering_does_not_change_fingerprints(self) -> None:
        target = semantic_webs(parse_globalcolor_trace(TARGET), proc=2)
        candidate = semantic_webs(parse_globalcolor_trace(CANDIDATE), proc=2)
        self.assertEqual(
            [item.fingerprint for item in target],
            [item.fingerprint for item in candidate],
        )
        self.assertEqual(sorted(item.decision.web for item in target), [15, 16])
        self.assertEqual(sorted(item.decision.web for item in candidate), [25, 26])

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

    def test_stack_homes_name_virtual_ownership_without_inventing_layout(
        self,
    ) -> None:
        report = stack_home_report(parse_globalcolor_trace(TARGET), proc=2)
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


if __name__ == "__main__":
    unittest.main()
