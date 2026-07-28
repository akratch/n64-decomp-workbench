"""Tests for uopt globalcolor trace parsing."""

from __future__ import annotations

import json
import unittest

from decomp_workbench.globalcolor import parse_globalcolor_trace

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
        self.assertEqual(items[0].detail["line"], "5")
        self.assertEqual([cost["color"] for cost in items[0].color_costs], ["1", "2"])
        self.assertEqual(items[0].color_costs[1]["best_before"], "22.250000")
        self.assertEqual(report.allocator_webs(dtype=6), [])

    def test_ranks_nan_save_last(self) -> None:
        report = parse_globalcolor_trace(
            "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 adjsave=nan unk23=0\n"
            "CSAVE bitpos=2 kind=1 dtype=13 unk1C=1 adjsave=2.0 unk23=0\n"
        )
        self.assertEqual([item.bitpos for item in report.ranked()], [2, 1])


if __name__ == "__main__":
    unittest.main()
