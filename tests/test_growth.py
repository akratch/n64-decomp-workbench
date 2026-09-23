"""Split growth and block sets read from synthetic globalcolor traces."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from decomp_workbench.cascade import CdxLog, block_report
from decomp_workbench.cli import main
from decomp_workbench.globalcolor import parse_globalcolor_trace
from decomp_workbench.growth import (
    GrowthError,
    GrowthTest,
    growth_report,
    index_growth,
    neighbour_report,
    parse_blocks,
    rule_census,
    rule_verdict,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "traces" / "split-growth.log"


def trace() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class RuleTests(unittest.TestCase):
    def test_the_two_clauses_of_the_strict_rule(self) -> None:
        # 185 on the documented shape: 22 against 23 -- rejected by one.
        self.assertFalse(
            rule_verdict(new=0, left_before=14, left_after=11, numintf=23, strict=1)
        )
        # the same test with one colour more survives, at margin +1
        self.assertTrue(
            rule_verdict(new=0, left_before=14, left_after=12, numintf=23, strict=1)
        )
        # the first clause alone refuses a block adding as many as are left
        self.assertFalse(
            rule_verdict(new=14, left_before=14, left_after=14, numintf=0, strict=1)
        )
        # with the strict flag clear any colour left is enough
        self.assertTrue(
            rule_verdict(new=9, left_before=2, left_after=1, numintf=40, strict=0)
        )

    def test_a_rejection_by_one_reads_as_one_whichever_clause_refused(self) -> None:
        by_pressure = GrowthTest(185, 0, 14, 11, 23, 1, False)
        by_headroom = GrowthTest(186, 14, 14, 14, 0, 1, False)
        self.assertEqual((by_pressure.margin, by_pressure.shortfall), (-1, 1))
        self.assertEqual((by_headroom.headroom, by_headroom.shortfall), (0, 1))
        self.assertTrue(by_pressure.agrees)

    def test_block_fields_decode_the_empty_marker(self) -> None:
        self.assertEqual(parse_blocks("-"), ())
        self.assertEqual(parse_blocks("3,1,2"), (3, 1, 2))


class ReaderTests(unittest.TestCase):
    def test_a_web_joins_its_piece_through_its_last_webblocks_row(self) -> None:
        report = growth_report(index_growth(parse_globalcolor_trace(trace())), 202)
        self.assertEqual(report["blocks"]["live_range"], "0x10200100")
        self.assertEqual(report["seed"], 183)
        self.assertEqual(
            [test["block"] for test in report["tests"]], [184, 190, 185, 191, 202]
        )
        self.assertEqual(report["disagreements"], [])
        self.assertEqual(report["nearest_rejection"]["block"], 185)
        self.assertEqual(report["nearest_rejection"]["shortfall"], 1)
        self.assertEqual(report["schema"], "decomp-workbench-split-growth-v1")

    def test_the_census_reports_a_disagreeing_verdict_rather_than_hiding_it(
        self,
    ) -> None:
        lying = trace().replace("bb=185 accepted=0", "bb=185 accepted=1")
        census = rule_census(index_growth(parse_globalcolor_trace(lying)))
        self.assertEqual(census["tests"], 5)
        self.assertEqual(census["agree"], 4)
        self.assertEqual([row["block"] for row in census["disagree"]], [185])

    def test_a_log_without_the_records_says_how_to_capture_them(self) -> None:
        bare = "[CDX] p1dec phase=p1 proc=0 web=1 decision=color\n"
        with self.assertRaisesRegex(GrowthError, "CDX_DETAIL_WEB"):
            growth_report(index_growth(parse_globalcolor_trace(bare)), 1)
        with self.assertRaisesRegex(GrowthError, "grow"):
            rule_census(index_growth(parse_globalcolor_trace(bare)))

    def test_neighbours_are_listed_per_decision_with_what_changed(self) -> None:
        report = neighbour_report(
            parse_globalcolor_trace(trace()), web=202, window=(183, 202)
        )
        first, second = report["decisions"]
        self.assertEqual(
            [entry["web"] for entry in first["neighbours"]], [40, 157, 251]
        )
        self.assertEqual(first["neighbours"][0]["register"], "v1")
        self.assertEqual(second["gone"], [251])
        self.assertEqual(report["schema"], "decomp-workbench-neighbours-v1")

    def test_trace_blocks_reads_the_shipped_member_sets_without_saveocc(self) -> None:
        log = CdxLog(trace(), name="split-growth.log")
        report = block_report(log, webs=[202], blocks=[])
        self.assertEqual(report["source"], "webblocks")
        self.assertEqual(report["webs"][0]["blocks"], [183, 184, 190, 191, 202])


class CommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_journey_spelling_prints_margins(self) -> None:
        status, stdout, _ = self.run_cli(
            ["trace", "growth", str(FIXTURE), "--web", "202"]
        )
        self.assertEqual(status, 0)
        self.assertIn("margin=-1  reject", stdout)
        self.assertIn("nearest rejection: bb=185 short by 1", stdout)

    def test_census_json_and_exit_status(self) -> None:
        status, stdout, _ = self.run_cli(
            ["trace-growth", str(FIXTURE), "--census", "--json"]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["agree"], payload["judged"])

    def test_a_missing_web_is_a_usage_error(self) -> None:
        status, _, stderr = self.run_cli(["trace-growth", str(FIXTURE)])
        self.assertEqual(status, 2)
        self.assertIn("--web", stderr)


if __name__ == "__main__":
    unittest.main()
