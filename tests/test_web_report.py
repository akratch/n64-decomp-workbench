"""Tests for `trace web-report`, the per-web allocator report.

Nothing here compiles. `examples/traces/web-report.log` is a hand-written
synthetic capture for `examples/fixtures/web-report-mini.c`; its numbers are
illustrative and are chosen so each of the report's four readings has a case
to get right:

1. the per-reference breakdown sums back to gross, net is gross minus the
   charges, and net is the decision's totalsave -- the breakdown is the
   decision's own arithmetic, not a reconstruction;
2. a forbidden-seed bit is attributed to the web pinned in that block, a value
   held over its range, or to no web at all, and a web's own colour in a block
   is never counted against it;
3. every growth verdict is re-checked against the L161 rule, the first refused
   block is named, and a verdict the rule does not explain is flagged rather
   than silently believed;
4. a log without the CDX_WEBREPORT records is refused by name rather than
   printed as an empty report.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.web_report import (
    RECORD_GRAMMAR,
    WEB_REPORT_SCHEMA,
    Namer,
    build_web_report,
    choose_procedure,
    colour_name,
    parse_records,
    web_report_payload,
)

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "examples" / "traces" / "web-report.log"
SOURCE = ROOT / "examples" / "fixtures" / "web-report-mini.c"
NAMER = Namer({-28: ["col"], -32: ["index"], -36: ["sum"]}, {0: "grid"})


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def payload(**options: Any) -> dict[str, Any]:
    records = parse_records(TRACE.read_text(encoding="utf-8"))
    report = build_web_report(records, 0)
    source = SOURCE.read_text(encoding="utf-8").splitlines()
    return web_report_payload(report, NAMER, source=source, **options)


def decision(web: int, order: int | None = None) -> dict[str, Any]:
    items: list[dict[str, Any]] = [
        item
        for item in payload()["decisions"]
        if item["web"] == web and (order is None or item["order"] == order)
    ]
    return items[0]


class NamingTests(unittest.TestCase):
    def test_expressions_render_over_the_procedures_own_names(self) -> None:
        bare = Namer()
        expression = "op1(op4(var:-28:1:4,const:7),const:9)"
        self.assertEqual(bare.render(expression), "((auto[-28] & 7) + 9)")
        self.assertEqual(NAMER.render(expression), "((col & 7) + 9)")
        self.assertEqual(NAMER.render("op54(var:0:2:4,@12)"), "*(grid + 12)")
        self.assertEqual(NAMER.render("var:2:3:4"), "$v0")
        self.assertEqual(NAMER.render("var:32:3:4"), "$f0")
        self.assertEqual(NAMER.variables(expression), ["col"])

    def test_an_unparseable_expression_is_returned_verbatim(self) -> None:
        self.assertEqual(NAMER.render("op4(var:-28:1:4"), "op4(var:-28:1:4")

    def test_colours_use_the_pinned_register_table(self) -> None:
        self.assertEqual(colour_name(1), "v0")
        self.assertEqual(colour_name(16), "s2")
        self.assertEqual(colour_name(31), "c31")


class ProcedureTests(unittest.TestCase):
    def test_the_procedure_is_chosen_by_its_definition_span(self) -> None:
        records = parse_records(TRACE.read_text(encoding="utf-8"))
        self.assertEqual(choose_procedure(records, (7, 20)), 0)
        self.assertEqual(choose_procedure(records, (22, 24)), 1)
        self.assertIsNone(choose_procedure(records, None))

    def test_every_record_in_the_fixture_is_in_the_grammar(self) -> None:
        kinds = {kind for kind, _ in parse_records(TRACE.read_text(encoding="utf-8"))}
        self.assertEqual(kinds - set(RECORD_GRAMMAR), {"globalcolor"})


class ReferenceTests(unittest.TestCase):
    def test_the_breakdown_is_the_decisions_own_arithmetic(self) -> None:
        item = decision(3)
        references = item["references"]
        assert isinstance(references, dict)
        self.assertEqual([row["term"] for row in references["rows"]], [500.0, 100.0])
        self.assertTrue(references["terms_sum_to_gross"])
        self.assertTrue(references["net_is_gross_minus_charges"])
        self.assertTrue(references["net_is_totalsave"])
        self.assertEqual(item["rendered"], "(col & 7)")
        self.assertEqual(item["register"], "s0")

    def test_charges_are_subtracted_before_the_totalsave_check(self) -> None:
        references = decision(7)["references"]
        assert isinstance(references, dict)
        self.assertEqual(references["net"], 240.0)
        self.assertTrue(references["net_is_totalsave"])

    def test_reference_rows_name_the_source_lines_that_mention_the_web(self) -> None:
        references = decision(5, order=3)["references"]
        assert isinstance(references, dict)
        rows = {row["block"]: row for row in references["rows"]}
        self.assertEqual(rows[1]["naming_lines"], [13])
        self.assertEqual(rows[3]["naming_lines"], [15, 16])
        self.assertEqual(rows[3]["flags"], ["nl"])


class ForbiddenSeedTests(unittest.TestCase):
    def test_each_seed_bit_names_what_put_it_there(self) -> None:
        forbidden = decision(3)["forbidden"]
        assert isinstance(forbidden, dict)
        self.assertEqual(forbidden["seed"], "0x54000000")
        self.assertEqual(forbidden["at_decision"], "0x54010000")
        self.assertEqual(forbidden["neighbours_add"], ["s1"])
        sources = {item["register"]: item["blocks"] for item in forbidden["sources"]}
        self.assertEqual(sources["v0"], [{"block": 4, "source": "web 9 $v0"}])
        self.assertEqual(
            sources["a0"], [{"block": 4, "source": "col held over its range"}]
        )
        self.assertIn("no web", sources["a2"][0]["source"])

    def test_a_webs_own_colour_is_not_counted_against_it(self) -> None:
        forbidden = decision(3)["forbidden"]
        assert isinstance(forbidden, dict)
        self.assertNotIn("s0", {item["register"] for item in forbidden["sources"]})


class GrowthTests(unittest.TestCase):
    def test_every_verdict_is_checked_against_the_rule(self) -> None:
        growth = decision(5, order=3)["growth"]
        assert isinstance(growth, dict)
        (piece,) = growth["pieces"]
        self.assertEqual(piece["piece_web"], 5)
        self.assertEqual(piece["piece_register"], "a1")
        verdicts = [
            (t["block"], t["accepted"], t["rule_agrees"]) for t in piece["tests"]
        ]
        self.assertEqual(
            verdicts, [(2, True, True), (3, False, True), (5, False, False)]
        )
        self.assertEqual(growth["first_refused"], {"block": 3, "live_range": "L3"})

    def test_an_unsplit_web_has_no_growth(self) -> None:
        self.assertIsNone(decision(3)["growth"])


class CommandTests(unittest.TestCase):
    def test_the_text_report_reads_end_to_end(self) -> None:
        status, output, error = run_cli(
            [
                "trace",
                "web-report",
                str(TRACE),
                "--lines",
                "7-20",
                "--source",
                str(SOURCE),
                "--local",
                "-28=col",
                "--local",
                "-32=index",
                "--param",
                "0=grid",
            ]
        )
        self.assertEqual(status, 0, error)
        self.assertIn("web 3 p1  (col & 7)", output)
        self.assertIn("naming col: 16", output)
        self.assertIn("first refused block: bb3", output)
        self.assertIn("(rule disagrees: read the record)", output)
        self.assertIn("v0 from bb4 <- web 9 $v0", output)

    def test_block_filter_keeps_only_that_blocks_rows(self) -> None:
        status, output, _ = run_cli(
            ["web-report", str(TRACE), "--proc", "0", "--web", "3", "--block", "4"]
        )
        self.assertEqual(status, 0)
        self.assertIn("bb4: weight 1, lines 18, pinned registers v0", output)
        self.assertIn("bb4", output)
        self.assertNotIn("bb3 ", output)

    def test_json_carries_the_schema(self) -> None:
        status, output, _ = run_cli(["web-report", str(TRACE), "--proc", "0", "--json"])
        self.assertEqual(status, 0)
        data = json.loads(output)
        self.assertEqual(data["schema"], WEB_REPORT_SCHEMA)
        self.assertEqual(data["decision_count"], 5)
        self.assertEqual(data["missing_records"], [])

    def test_a_log_without_webreport_records_is_refused_by_name(self) -> None:
        log = ROOT / "examples" / "traces" / "split-growth.log"
        status, output, error = run_cli(["web-report", str(log)])
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("CDX_WEBREPORT", error)

    def test_an_ambiguous_procedure_asks_for_proc(self) -> None:
        status, _, error = run_cli(["web-report", str(TRACE)])
        self.assertEqual(status, 2)
        self.assertIn("--proc", error)
        self.assertIn("[0, 1]", error)

    def test_a_malformed_name_is_an_argument_error(self) -> None:
        with (
            self.assertRaises(SystemExit) as raised,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            main(["web-report", str(TRACE), "--local", "col"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
