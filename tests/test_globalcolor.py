"""Tests for uopt globalcolor trace parsing."""

from __future__ import annotations

import json
import unittest

from decomp_workbench.globalcolor import (
    parse_globalcolor_trace,
    register_for_color,
)

TRACE = """\
CSAVE bitpos=279 kind=1 dtype=13 unk1C=81 adjsave=2.5 unk23=0
  UNIT bb=4 dep=2 ld=1 st=0 reg=0 fstr=0 nrl=0 nrs=0 dout=0
CUP bitpos=279 reg=24 cs=1 cost=100.0
CUP bitpos=279 reg=30 cs=2 cost=20.0
CSAVE bitpos=12 kind=1 dtype=4 unk1C=2 adjsave=1.0 unk23=1
[CDX] p1dec proc=3 web=9 sym=7 class=2 save=3.5 -> COLOR
"""


class GlobalColorTests(unittest.TestCase):
    def test_parses_and_ranks_live_ranges(self) -> None:
        report = parse_globalcolor_trace(TRACE)
        self.assertEqual(len(report.live_ranges), 2)
        item = report.live_ranges[279]
        self.assertEqual(item.total_save, 202.5)
        self.assertEqual(item.finite_costs[1].register, 30)
        self.assertEqual(report.ranked()[0].bitpos, 279)
        self.assertEqual(report.ranked(dtype=4)[0].bitpos, 12)

    def test_parses_cdx_decision(self) -> None:
        report = parse_globalcolor_trace(TRACE)
        decision = report.decisions[0]
        self.assertEqual(decision.phase, "p1dec")
        self.assertEqual(decision.fields["web"], "9")
        self.assertEqual(report.decisions_for(3), [decision])
        self.assertEqual(report.decisions_for(4), [])
        self.assertEqual(report.decisions_for(), report.decisions)
        self.assertEqual(report.decisions_for(3, web=9), [decision])
        self.assertEqual(report.decisions_for(3, web=10), [])
        self.assertEqual(report.unparsed_diagnostic_lines, [])

    def test_accepts_nonfinite_compiler_cost(self) -> None:
        report = parse_globalcolor_trace(
            "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 "
            "adjsave=1e+03 unk23=0\n"
            "CUP bitpos=1 reg=2 cs=3 cost=inf\n"
        )
        item = report.live_ranges[1]
        self.assertEqual(item.total_save, 1000.0)
        self.assertEqual(item.finite_costs, [])
        self.assertEqual(report.unparsed_diagnostic_lines, [])
        payload = report.as_dict()
        self.assertEqual(item.color_costs[0].as_dict()["cost"], "inf")
        json.dumps(payload, allow_nan=False)

    def test_joins_allocator_decision_with_web_detail(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1cost proc=2 web=15 color=1 kind=caller "
            "cost=22.250000 best_before=100000002004087734272.000000\n"
            "[CDX] p1cost proc=2 web=15 color=2 kind=caller "
            "cost=22.250000 best_before=22.250000\n"
            "[CDX] p1dec proc=2 web=15 sym=15 class=2 save=13.500000 "
            "nocs=4 totalsave=54.000000 bestcost=22.250000 bestcolor=30 "
            "forbidden0=0x000000a0 forbidden1=0x00000000 regsleft=10 "
            "numintf=13 decision=color forced=-2\n"
            "[CDX] webdetail proc=2 role=target web=15 sym=15 type=3 "
            "dtype=13 table=0 chain=0 exprtable=0 exprchain=1 bb=0 line=5 "
            "raw10=0xffffff9c raw14=0x00240102 raw18=0x04010000 "
            "raw20=0x00000000\n"
        )
        items = report.allocator_webs(proc=2, dtype=13)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0].proc, items[0].web), (2, 15))
        self.assertEqual(items[0].phase, "p1dec")
        self.assertEqual(items[0].fields["bestcolor"], "30")
        self.assertIsNone(items[0].assigned_register)
        self.assertIn("selected c30", items[0].explanation)
        self.assertEqual(items[0].detail["line"], "5")
        self.assertEqual([cost["color"] for cost in items[0].color_costs], ["1", "2"])
        self.assertEqual(items[0].color_costs[1]["best_before"], "22.250000")
        self.assertEqual(report.allocator_webs(dtype=6), [])

    def test_a_decision_names_the_colors_a_force_cannot_take(self) -> None:
        """The mask decodes to the endpoints a CDX_FORCE probe would be declined for.

        `forb=0x7f800000` was recorded on a campaign web and read there as
        "c1-c8 forbidden"; the instrumented pass now declines exactly these
        colors instead of aborting the compiler, so the two must name one set.
        """

        report = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=11 web=300 sym=300 class=1 save=1 "
            "nocs=2 totalsave=2 bestcost=0 bestcolor=-1 "
            "forbidden0=0x7f800000 forbidden1=0x00000000 decision=no-color\n"
        )
        item = report.allocator_webs(proc=11, web=300)[0]
        self.assertEqual(item.forbidden_colors, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(item.as_dict()["forbidden_colors"], [1, 2, 3, 4, 5, 6, 7, 8])

    def test_a_decision_without_a_mask_claims_nothing(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=46 web=240 bestcolor=17 decision=color\n"
        )
        self.assertEqual(report.allocator_webs(proc=46)[0].forbidden_colors, [])

    def test_names_stable_callee_saved_colors_and_filters_webs(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=46 web=240 sym=240 class=1 save=1 "
            "nocs=2 totalsave=2 bestcost=0 bestcolor=17 decision=color\n"
        )
        item = report.allocator_webs(proc=46, web=240)[0]
        self.assertEqual(item.assigned_color, 17)
        self.assertEqual(item.assigned_register, "s3")
        self.assertEqual(item.explanation, "color: selected c17 (s3)")
        self.assertEqual(report.allocator_webs(proc=46, web=241), [])

    def test_decodes_caller_saved_colors_and_phase_namespace(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=7 web=55 sym=55 class=1 save=1 "
            "nocs=2 totalsave=2 bestcost=0 bestcolor=2 bestreg=v1 "
            "decision=color\n"
        )
        item = report.allocator_webs(proc=7, web=55)[0]
        self.assertEqual(item.assigned_color, 2)
        self.assertEqual(item.assigned_register, "v1")
        self.assertEqual(item.phase_tag, "p2")
        self.assertEqual(item.force_key, "p2:w55")
        self.assertEqual(item.explanation, "color: selected c2 (v1)")

    def test_phase_namespace_falls_back_to_the_record_name(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=7 web=9 bestcolor=1 decision=color\n"
        )
        item = report.allocator_webs(proc=7, web=9)[0]
        self.assertEqual(item.phase_tag, "p1")
        self.assertEqual(item.force_key, "p1:w9")
        self.assertEqual(item.assigned_register, "v0")

    def test_unconfirmed_colors_are_not_named(self) -> None:
        self.assertIsNone(register_for_color(13))
        self.assertIsNone(register_for_color(30))
        self.assertIsNone(register_for_color(None))
        self.assertEqual(register_for_color(12), "t5")
        self.assertEqual(register_for_color(23), "ra")

    def test_ranks_nan_save_last(self) -> None:
        report = parse_globalcolor_trace(
            "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 adjsave=nan unk23=0\n"
            "CSAVE bitpos=2 kind=1 dtype=13 unk1C=1 adjsave=2.0 unk23=0\n"
        )
        self.assertEqual([item.bitpos for item in report.ranked()], [2, 1])

    def test_malformed_cdx_numbers_do_not_crash_focused_reports(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=bad web=9 totalsave=bad decision=color\n"
        )
        self.assertEqual(report.decisions_for(3, web=9), [])
        self.assertEqual(report.allocator_webs(proc=3), [])


if __name__ == "__main__":
    unittest.main()
