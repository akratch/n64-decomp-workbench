"""Tests for uopt globalcolor trace parsing."""

from __future__ import annotations

import json
import unittest

from decomp_workbench.globalcolor import (
    ALLOCATOR_COLOR_REGISTERS,
    COLOR_REGISTERS,
    FP_LOCAL_RING,
    color_for_register,
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

    def test_filters_pre_globalcolor_lineage_by_procedure_and_table(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] lineage_range proc=0 event=0 table=1004 chain=0 "
            "type=4 dtype=6\n"
            "[CDX] lineage_member proc=0 event=1 table=1004 chain=0 "
            "bb=10 line=2 flags=0,0,0,0,0,0\n"
            "[CDX] lineage_range proc=1 event=0 table=688 chain=0 "
            "type=3 dtype=6\n"
        )
        selected = report.lineage_for(0, tables={1004})
        self.assertEqual(
            [item.phase for item in selected],
            ["lineage_range", "lineage_member"],
        )
        self.assertEqual(report.lineage_for(0, tables={688}), [])
        self.assertEqual(len(report.lineage_for()), 3)

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

    def test_excludes_ido_unavailable_cost_sentinel(self) -> None:
        report = parse_globalcolor_trace(
            "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 adjsave=1 unk23=0\n"
            "CUP bitpos=1 reg=12 cs=1 "
            "cost=100000002004087734272.000000\n"
            "CUP bitpos=1 reg=18 cs=2 cost=5.5\n"
        )
        item = report.live_ranges[1]
        self.assertEqual([entry.register for entry in item.finite_costs], [12, 18])
        self.assertEqual([entry.register for entry in item.eligible_costs], [18])
        self.assertFalse(item.color_costs[0].as_dict()["eligible"])

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

    def test_phase_less_detail_is_withheld_when_web_number_is_ambiguous(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] webdetail proc=2 role=target web=15 dtype=13 line=5\n"
            "[CDX] p1dec phase=p1 proc=2 web=15 bestcolor=1 decision=color\n"
            "[CDX] p2dec phase=p2 proc=2 web=15 bestcolor=2 decision=color\n"
        )
        items = report.allocator_webs(proc=2, web=15)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item.detail == {} for item in items))

    def test_provenance_snapshots_join_only_when_unique_and_consistent(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=preselect "
            "source_semantic=local:pending-flag semantic_reason=ir-local\n"
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=postselect "
            "source_semantic=local:pending-flag semantic_reason=ir-local\n"
            "[CDX] p2dec phase=p2 proc=2 web=62 bestcolor=2 decision=color\n"
        )
        detail = trace.allocator_webs(proc=2, web=62)[0].detail
        self.assertEqual(detail["source_semantic"], "local:pending-flag")
        self.assertEqual(detail["semantic_reason"], "ir-local")

    def test_ambiguous_provenance_is_withheld(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=preselect "
            "source_semantic=local:first\n"
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=preselect "
            "source_semantic=local:first\n"
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=postselect "
            "source_semantic=local:second\n"
            "[CDX] p2dec phase=p2 proc=2 web=62 bestcolor=2 decision=color\n"
        )
        self.assertEqual(trace.allocator_webs(proc=2, web=62)[0].detail, {})

    def test_forced_assignment_preserves_owner_and_reports_actual_color(self) -> None:
        trace = parse_globalcolor_trace(
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=preselect "
            "selected_color=12 selected_reg=t5 owner_sym=62 owner_type=3\n"
            "[CDX] p2dec proc=2 phase=p2 web=62 bestcolor=12 bestreg=t5 "
            "decision=color forced=18\n"
            "[CDX] p2color proc=2 phase=p2 web=62 color=18 reg=s4 forced=18\n"
            "[CDX] provenance_web proc=2 phase=p2 web=62 snapshot=postselect "
            "selected_color=18 selected_reg=s4 owner_sym=62 owner_type=3\n"
        )
        item = trace.allocator_webs(proc=2, web=62)[0]
        self.assertEqual(item.natural_color, 12)
        self.assertEqual(item.assigned_color, 18)
        self.assertEqual(item.assigned_register, "s4")
        self.assertEqual(item.detail["owner_sym"], "62")
        self.assertEqual(item.detail["preselect_selected_color"], "12")
        self.assertEqual(item.detail["postselect_selected_color"], "18")
        self.assertEqual(item.as_dict()["natural_register"], "t5")

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
        self.assertIsNone(item.natural_color)
        self.assertIsNone(item.assigned_color)
        self.assertEqual(item.as_dict()["forbidden_colors"], [1, 2, 3, 4, 5, 6, 7, 8])

    def test_a_decision_without_a_mask_claims_nothing(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=46 web=240 bestcolor=17 decision=color\n"
        )
        self.assertEqual(report.allocator_webs(proc=46)[0].forbidden_colors, [])

    def test_mincost_tie_colors_decodes_available_not_forbidden(self) -> None:
        """WB-65: `available0`/`1` is the minimum-cost TIE SET, not "free colors".

        `available0=0x1c` was recorded on a real campaign web
        (`ge007-object-interaction` l4c/RESULT.md) and independently
        cross-checked there as `{c27, c28, c29}` -- both colours 27 and 29
        are 1 bit apart from 28 in the same 32-bit word (`1 << (31-color)`),
        confirming this is the same forbidden0-style mask convention applied
        to a different field. The instrumented pass keeps this pair at
        `sp+212`/`sp+216`, resetting on a strictly lower cost and OR-ing on an
        exact tie -- it is the set tied for cheapest, not the allocator's
        free/candidate set, which is why the property is not named
        `available_colors`.
        """

        report = parse_globalcolor_trace(
            "[CDX] p1dec phase=p1 proc=0 web=3097 sym=3097 class=1 save=2.0 "
            "nocs=2 totalsave=4.0 bestcost=0.0 bestcolor=26 bestreg=t3 "
            "forbidden0=0xd3 forbidden1=0x00000000 regsleft=7 numintf=10 "
            "available0=0x1c available1=0x00000000 decision=color\n"
        )
        item = report.allocator_webs(proc=0, web=3097)[0]
        self.assertEqual(item.mincost_tie_colors, [27, 28, 29])
        self.assertEqual(item.fields["available0"], "0x1c")
        self.assertEqual(item.as_dict()["mincost_tie_colors"], [27, 28, 29])

    def test_a_decision_without_an_available_mask_claims_no_tie_set(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec proc=46 web=240 bestcolor=17 decision=color\n"
        )
        self.assertEqual(report.allocator_webs(proc=46)[0].mincost_tie_colors, [])

    def test_desired_register_barrier_names_interfering_owner(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=0 web=100 bestcolor=18 "
            "forbidden0=0x00080000 decision=color\n"
            "[CDX] intf phase=p2 proc=0 web=100 other=60 assigned=12\n"
            "[CDX] webdetail phase=p2 proc=0 role=neighbor web=60 "
            "dtype=6 type=4 table=1004\n"
        )
        barrier = report.allocator_webs(proc=0, web=100)[0].color_barrier(12)
        self.assertEqual(barrier["status"], "desired-forbidden")
        self.assertEqual(
            barrier["blocking_neighbors"],
            [
                {
                    "phase": "p2",
                    "web": 60,
                    "force_key": "p2:w60",
                    "assigned_color": 12,
                    "assigned_register": "t5",
                    "detail": {
                        "phase": "p2",
                        "proc": "0",
                        "role": "neighbor",
                        "web": "60",
                        "dtype": "6",
                        "type": "4",
                        "table": "1004",
                    },
                }
            ],
        )
        self.assertIn("p2:w60", str(barrier["advice"]))

    def test_desired_register_barrier_names_ineligible_sentinel(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2cost phase=p2 proc=3 web=0 color=12 reg=t5 "
            "kind=caller cost=100000002004087734272.000000\n"
            "[CDX] p2cost phase=p2 proc=3 web=0 color=14 reg=s0 "
            "kind=callee cost=4.5\n"
            "[CDX] p2dec phase=p2 proc=3 web=0 bestcolor=14 "
            "forbidden0=0x00000000 decision=color\n"
        )
        barrier = report.allocator_webs(proc=3, web=0)[0].color_barrier(12)
        self.assertEqual(barrier["status"], "desired-ineligible")
        self.assertTrue(barrier["desired_ineligible"])
        self.assertIsNone(barrier["cost_gap"])
        self.assertIn("unavailable-cost sentinel", str(barrier["advice"]))

    def test_barrier_recognizes_an_already_natural_color(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2cost phase=p2 proc=3 web=0 color=12 reg=t5 "
            "kind=caller cost=4.5\n"
            "[CDX] p2dec phase=p2 proc=3 web=0 bestcolor=12 "
            "forbidden0=0x00000000 decision=color\n"
        )

        item = report.allocator_webs(proc=3, web=0)[0]
        barrier = item.color_barrier(12)

        self.assertEqual(barrier["status"], "already-natural")
        self.assertIn("already", str(barrier["advice"]))
        self.assertEqual(item.as_dict()["decision_trace_ordinal"], 1)

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

    def test_the_float_color_map_is_the_corrected_one(self) -> None:
        # WB-80: four campaign stages ran on `c24=$f8 c25=$f10`, correct only
        # from c26 up, and a tool written *after* the correction still carried
        # the old dict. One shared table, so there is no second copy to miss.
        self.assertEqual(register_for_color(24), "$f0")
        self.assertEqual(register_for_color(25), "$f2")
        self.assertEqual(register_for_color(26), "$f12")
        self.assertEqual(register_for_color(29), "$f18")
        # `$f4`-`$f10` are ugen's local ring and are never a p1 colour (L38),
        # in either direction: naming one of them proves the map is wrong.
        for ring_register in FP_LOCAL_RING:
            self.assertIsNone(color_for_register(ring_register))
            self.assertNotIn(ring_register, ALLOCATOR_COLOR_REGISTERS.values())
        self.assertEqual(color_for_register("$f14"), 27)
        self.assertEqual(color_for_register("f14"), 27)

    def test_the_generated_instrument_table_stays_integer_only(self) -> None:
        # The float names are a reader-side correction. Widening the table
        # compiled into the pass would change what a pinned instrument build
        # emits, for names the pass has no way to check.
        self.assertEqual(max(COLOR_REGISTERS), 23)
        self.assertNotIn(24, COLOR_REGISTERS)

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


class ContestedAllocationTests(unittest.TestCase):
    """`regsleft=0` separates "underpriced" from "taken", and only one of
    those has a cost lever."""

    def test_a_split_with_no_registers_left_names_lever_28(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec phase=p1 proc=1 web=5 bestcolor=17 regsleft=0 decision=split\n"
        )
        item = report.allocator_webs(proc=1, web=5)[0]
        self.assertTrue(item.contested_allocation)
        self.assertEqual(item.registers_left, 0)
        self.assertIn("taken, not", item.explanation)
        self.assertIn("lever 28", item.explanation)

    def test_a_split_with_registers_left_is_an_ordinary_split(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p1dec phase=p1 proc=1 web=5 bestcolor=17 regsleft=3 decision=split\n"
        )
        item = report.allocator_webs(proc=1, web=5)[0]
        self.assertFalse(item.contested_allocation)
        self.assertNotIn("lever 28", item.explanation)

    def test_an_unrecorded_budget_claims_nothing(self) -> None:
        """A trace without `regsleft` must not be read as `regsleft=0`."""

        report = parse_globalcolor_trace(
            "[CDX] p1dec phase=p1 proc=1 web=5 bestcolor=17 decision=split\n"
        )
        item = report.allocator_webs(proc=1, web=5)[0]
        self.assertIsNone(item.registers_left)
        self.assertFalse(item.contested_allocation)

    def test_a_phase_two_denial_counts_as_contested(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=1 web=5 bestcolor=17 regsleft=0 "
            "decision=no-color\n"
        )
        self.assertTrue(report.allocator_webs(proc=1, web=5)[0].contested_allocation)

    def test_a_forbidden_desired_color_routes_to_lever_28(self) -> None:
        report = parse_globalcolor_trace(
            "[CDX] p2dec phase=p2 proc=0 web=100 bestcolor=18 "
            "forbidden0=0x00080000 decision=color\n"
            "[CDX] intf phase=p2 proc=0 web=100 other=60 assigned=12\n"
        )
        barrier = report.allocator_webs(proc=0, web=100)[0].color_barrier(12)
        self.assertEqual(barrier["status"], "desired-forbidden")
        self.assertIn("lever 28", str(barrier["advice"]))


if __name__ == "__main__":
    unittest.main()
