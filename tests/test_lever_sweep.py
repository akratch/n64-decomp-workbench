"""Tests for `sweep levers`: the zero-emission lever catalogue and its oracle.

The catalogue tests run the statement parser and every lever on small
synthetic C functions written for this file. The end-to-end tests compile
through `tests/fixtures/lever_sweep/fake_cc.py`, a stand-in compiler that is
deliberately *not* a model of IDO: it emits one instruction per statement,
colours `acc` s1 only when the body holds an empty `if (n) {}` or a force asks
for it, and writes CDX records whose web numbers follow first mention -- so an
inserted statement renumbers webs, which is exactly what the oracle's
re-identification by expression and source lines has to survive.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.lever_sweep import (
    LEVERS,
    BiasEntry,
    LeverSweepError,
    bias_targets,
    dead_at,
    find_function,
    force_acceptance,
    generate_cells,
    interleave,
    oracle_label,
    oracle_status,
    oracle_targets,
    parse_bias,
    parse_forces,
)
from decomp_workbench.lever_sweep_cli import LEVER_SWEEP_SCHEMA, SweepConfig, run_sweep

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "lever_sweep"
FAKE_CC = f"{sys.executable} {FIXTURES / 'fake_cc.py'} {{source}} -o {{output}}"

SAMPLE = """\
struct node { int value; struct node *next; short tag; };
extern int table[16];
extern int global_count;

int sample(struct node *p, int n) {
    int i;
    int k;
    int sum;
    short small;
    sum = 0;
    small = n * 2;
    for (i = 0; i < n; i++) {
        sum += table[i];
    }
    k = p->value + n;
    global_count = sum;
    sum = sum + k;
    return sum + small;
}
"""


def cells_of(lever: str, source: str = SAMPLE, name: str = "sample") -> list[Any]:
    return generate_cells(find_function(source, name), [lever])


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ParserTests(unittest.TestCase):
    def test_the_definition_is_found_past_a_prototype(self) -> None:
        source = "int sample(struct node *p, int n);\n" + SAMPLE
        function = find_function(source, "sample")
        self.assertEqual(set(function.locals), {"i", "k", "sum", "small"})
        self.assertEqual(function.params["p"].ptr, 1)
        self.assertEqual(function.params["p"].type, "struct node")
        self.assertEqual(function.locals["small"].type, "short")

    def test_a_missing_function_is_an_error(self) -> None:
        with self.assertRaises(LeverSweepError):
            find_function(SAMPLE, "absent")

    def test_dead_at_reads_the_next_mention(self) -> None:
        function = find_function(SAMPLE, "sample")
        body = function.body
        # Position right after the declarations: `k` is next written by a kill.
        first = body.declarations
        self.assertTrue(dead_at(function, body, first, "k"))
        # `sum` is next read (`sum += table[i]` is not a kill; `sum = 0` is).
        self.assertTrue(dead_at(function, body, first, "sum"))
        self.assertFalse(dead_at(function, body, first + 1, "sum"))

    def test_a_loop_back_edge_keeps_a_value_alive(self) -> None:
        source = (
            "int f(int n) {\n    int x;\n    x = 0;\n"
            "    while (n) {\n        n = n - x;\n        x = 1;\n    }\n"
            "    return n;\n}\n"
        )
        function = find_function(source, "f")
        loop = function.body.children[2]
        body = loop.children[0]
        # After `x = 1;` the back edge reads x in `n = n - x` before any kill.
        self.assertFalse(dead_at(function, body, len(body.children), "x"))


class LeverCatalogueTests(unittest.TestCase):
    def test_the_catalogue_carries_every_named_lever(self) -> None:
        for name in (
            "dead_read",
            "dead_masked",
            "keep_alive",
            "noop_redef",
            "narrow_type",
            "subscript",
            "boundary",
            "global_reread",
            "zero_def",
            "split_local",
            "merge_locals",
            "reorder",
        ):
            self.assertIn(name, LEVERS)

    def test_a_dead_read_is_typed_through_the_struct(self) -> None:
        edits = {cell.edit for cell in cells_of("dead_read")}
        self.assertIn("k = p->value;", edits)
        # A short field pairs with an int local; a pointer field never does.
        self.assertNotIn("k = p->next;", edits)

    def test_a_masked_dead_read_needs_an_integer_local(self) -> None:
        edits = {cell.edit for cell in cells_of("dead_masked")}
        self.assertIn("k = p->value & 0xFFFF;", edits)

    def test_keep_alive_follows_an_expression_assignment_only(self) -> None:
        edits = [cell.edit for cell in cells_of("keep_alive")]
        self.assertIn("small |= 0;", edits)
        self.assertIn("k ^= 0;", edits)
        self.assertNotIn("sum |= 0;", [e for e in edits if e.startswith("sum")][:0])

    def test_noop_redefinition_casts_to_the_declared_type(self) -> None:
        edits = {cell.edit for cell in cells_of("noop_redef")}
        self.assertIn("small = (short) small;", edits)

    def test_narrow_type_rewrites_one_declaration(self) -> None:
        cells = cells_of("narrow_type")
        cell = next(c for c in cells if c.edit == "short k")
        self.assertIn("short k;", cell.text)
        self.assertEqual(cell.semantics, "check")

    def test_subscript_masks_the_index(self) -> None:
        edits = {cell.edit for cell in cells_of("subscript")}
        self.assertIn("[i] -> [(i) & 0xFFFF]", edits)

    def test_a_scaled_subscript_rewrites_an_address(self) -> None:
        source = (
            "int g(int *a, int j) {\n    int *q;\n    q = &a[j];\n    return *q;\n}\n"
        )
        cells = cells_of("subscript", source, "g")
        scaled = next(cell for cell in cells if "byte-scaled" in cell.edit)
        self.assertIn("(char *) (a) + (j) * sizeof((a)[0])", scaled.text)

    def test_boundary_inserts_an_empty_if_on_the_same_line(self) -> None:
        cells = cells_of("boundary")
        empty = [cell for cell in cells if cell.edit == "if (n) {}"]
        self.assertTrue(empty)
        original_lines = SAMPLE.count("\n")
        self.assertTrue(all(cell.text.count("\n") == original_lines for cell in empty))
        self.assertTrue(any(cell.edit == "do { S } while (0)" for cell in cells))

    def test_own_line_puts_the_statement_on_a_new_line(self) -> None:
        function = find_function(SAMPLE, "sample")
        cells = generate_cells(function, ["boundary"], own_line=True)
        empty = next(cell for cell in cells if cell.edit == "if (n) {}")
        self.assertEqual(empty.text.count("\n"), SAMPLE.count("\n") + 1)

    def test_global_reread_reads_the_global_back(self) -> None:
        source = (
            "extern int global_count;\nint gr(int n) {\n    int x;\n    x = n * 3;\n"
            "    global_count = x;\n    n = x + 1;\n    return n;\n}\n"
        )
        (cell,) = cells_of("global_reread", source, "gr")
        self.assertIn("n = global_count + 1;", cell.text)
        self.assertEqual(cell.semantics, "check")

    def test_global_reread_stops_at_a_redefinition(self) -> None:
        self.assertEqual(cells_of("global_reread"), [])

    def test_zero_def_lands_between_loops(self) -> None:
        edits = {(cell.edit, cell.line) for cell in cells_of("zero_def")}
        self.assertIn(("k = 0;", 14), edits)

    def test_split_local_renames_from_a_redefinition(self) -> None:
        source = (
            "int h(int n) {\n    int x;\n    x = n;\n    n = x + 1;\n"
            "    x = n * 2;\n    return x;\n}\n"
        )
        (cell,) = cells_of("split_local", source, "h")
        self.assertIn("x_b = n * 2;", cell.text)
        self.assertIn("return x_b;", cell.text)
        self.assertIn("int x_b;", cell.text)

    def test_merge_locals_offers_both_declaration_forms(self) -> None:
        source = (
            "int m(int n) {\n    int a;\n    int b;\n    a = n;\n    n = a;\n"
            "    b = n + 1;\n    return b;\n}\n"
        )
        edits = {cell.edit for cell in cells_of("merge_locals", source, "m")}
        self.assertEqual(
            edits, {"b -> a (declaration kept)", "b -> a (declaration dropped)"}
        )

    def test_reorder_swaps_only_independent_statements(self) -> None:
        source = (
            "int r(int *p) {\n    int a;\n    int b;\n    a = 1;\n    b = 2;\n"
            "    return a + b;\n}\n"
        )
        (cell,) = cells_of("reorder", source, "r")
        self.assertIn("b = 2;\n    a = 1;", cell.text)
        dependent = (
            "int r(int n) {\n    int a;\n    int b;\n    a = n;\n    b = a;\n"
            "    return b;\n}\n"
        )
        self.assertEqual(cells_of("reorder", dependent, "r"), [])

    def test_line_restriction_narrows_positions(self) -> None:
        function = find_function(SAMPLE, "sample")
        everything = generate_cells(function, ["boundary"])
        narrowed = generate_cells(function, ["boundary"], {15})
        self.assertLess(len(narrowed), len(everything))
        self.assertTrue(all(cell.line == 15 for cell in narrowed))

    def test_cells_are_unique_and_never_the_base(self) -> None:
        function = find_function(SAMPLE, "sample")
        cells = generate_cells(function, list(LEVERS))
        texts = [cell.text for cell in cells]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertNotIn(SAMPLE, texts)

    def test_an_unknown_lever_is_refused(self) -> None:
        with self.assertRaises(LeverSweepError):
            generate_cells(find_function(SAMPLE, "sample"), ["telepathy"])

    def test_interleave_keeps_every_lever_under_a_cap(self) -> None:
        cells = generate_cells(
            find_function(SAMPLE, "sample"), ["boundary", "keep_alive"]
        )
        chosen = interleave(cells, 4)
        self.assertEqual(len(chosen), 4)
        self.assertEqual({cell.lever for cell in chosen}, {"boundary", "keep_alive"})


def row(
    web: int,
    expr: str,
    lines: list[int],
    colour: int | None,
    phase: str = "p1",
    decision: str = "color",
    forced: str = "-2",
) -> dict[str, Any]:
    return {
        "web": web,
        "phase": phase,
        "expr": expr,
        "kind": "3",
        "blocks": [],
        "lines": lines,
        "decision": decision,
        "forced": forced,
        "colour": colour,
    }


class OracleTests(unittest.TestCase):
    def setUp(self) -> None:
        forced = [row(10, "var:-28:1:4", [8, 10, 11], 15, forced="-1")]
        self.targets = oracle_targets(forced, parse_forces("p1:w10=c15"))

    def test_a_renumbered_web_is_found_by_expression(self) -> None:
        cell = [row(11, "var:-28:1:4", [8, 10, 11], 15), row(10, "var:0:2:4", [7], 17)]
        hits, detail = oracle_status(cell, self.targets)
        self.assertEqual((hits, oracle_label(hits, 1)), (1, "yes"))
        self.assertEqual(detail[0]["rows"][0]["match"], "p1:w11")

    def test_the_wrong_colour_is_a_miss(self) -> None:
        hits, _ = oracle_status([row(10, "var:-28:1:4", [8, 10, 11], 14)], self.targets)
        self.assertEqual(oracle_label(hits, 1), "no")

    def test_a_tie_that_disagrees_is_ambiguous(self) -> None:
        cell = [
            row(10, "var:-28:1:4", [8, 10, 11], 15),
            row(12, "var:-28:1:4", [8, 10, 11], 14),
        ]
        hits, detail = oracle_status(cell, self.targets)
        self.assertEqual(hits, 0)
        self.assertTrue(detail[0]["ambiguous"])
        self.assertEqual(oracle_label(hits, 1, 1), "ambiguous")

    def test_a_split_target_reads_as_memory(self) -> None:
        forced = [row(5, "var:-32:1:4", [12, 13], None, decision="split", forced="-1")]
        targets = oracle_targets(forced, parse_forces("p1:w5=s"))
        self.assertEqual(
            oracle_status([row(7, "var:-32:1:4", [12, 13], None)], targets)[0], 1
        )
        self.assertEqual(
            oracle_status([row(7, "var:-32:1:4", [12, 13], 16)], targets)[0], 0
        )
        # A piece that is never formed counts as reproduced.
        self.assertEqual(oracle_status([], targets)[0], 1)

    def test_a_forced_web_without_webexpr_cannot_be_an_oracle(self) -> None:
        forced = [row(10, None, [8], 15, forced="-1")]  # type: ignore[arg-type]
        with self.assertRaises(LeverSweepError):
            oracle_targets(forced, parse_forces("p1:w10=c15"))

    def test_bias_prices_a_decision_order(self) -> None:
        unbiased = [row(1, "var:-28:1:4", [8], 14), row(2, "var:-32:1:4", [9], 15)]
        biased = [row(2, "var:-32:1:4", [9], 14), row(1, "var:-28:1:4", [8], 15)]
        targets = bias_targets(unbiased, biased, [BiasEntry(2, 4.5)])
        self.assertEqual(targets[0]["spec"], "w2 before w1")
        self.assertEqual(oracle_status(biased, targets)[0], 1)
        self.assertEqual(oracle_status(unbiased, targets)[0], 0)

    def test_bias_parsing(self) -> None:
        self.assertEqual(
            parse_bias("w387=-4.5, 12=3"), [BiasEntry(387, -4.5), BiasEntry(12, 3.0)]
        )
        with self.assertRaises(LeverSweepError):
            parse_bias("387")

    def test_force_acceptance_reads_the_records(self) -> None:
        accepted = (
            "[CDX] p1dec proc=0 web=10 decision=color forced=-1\n"
            "[CDX] p1color proc=0 web=10 color=15 reg=s1 forced=-1\n"
        )
        forces = parse_forces("p1:w10=c15")
        self.assertIsNone(force_acceptance(accepted, 0, forces))
        refused = accepted.replace("color=15", "color=14")
        self.assertIn("not applied", force_acceptance(refused, 0, forces) or "")
        self.assertIn(
            "no allocator decisions", force_acceptance(accepted, 3, forces) or ""
        )
        split = "[CDX] p1dec proc=0 web=5 decision=split forced=-1\n"
        self.assertIsNone(force_acceptance(split, 0, parse_forces("p1:w5=s")))


class EndToEndTests(unittest.TestCase):
    def config(self, scratch: Path, **overrides: Any) -> SweepConfig:
        settings: dict[str, Any] = {
            "source": FIXTURES / "demo.c",
            "function": "demo",
            "target": FIXTURES / "target.objdump",
            "template": FAKE_CC,
            "environment": {},
            "compile_cwd": ROOT,
            "scratch": scratch,
            "oracle": "p1:w10=c15",
            "jobs": 2,
        }
        settings.update(overrides)
        return SweepConfig(**settings)

    def test_the_sweep_finds_the_zero_emission_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = run_sweep(self.config(Path(temp)))
            best = report["summary"]["best"]
            self.assertEqual(report["schema"], LEVER_SWEEP_SCHEMA)
            self.assertEqual(report["base"]["oracle"], "no")
            self.assertEqual(best["edit"], "if (n) {}")
            self.assertEqual(best["oracle"], "yes")
            self.assertTrue(best["equals_forced"])
            self.assertEqual(best["score"]["residual"], 0)
            self.assertTrue(Path(best["kept_source"]).is_file())
            # Zero-emission cells that change nothing are inert, not re-traced.
            inert = [cell for cell in report["cells"] if cell.get("inert")]
            self.assertTrue(any(cell["lever"] == "keep_alive" for cell in inert))

    def test_a_cell_before_the_first_mention_still_matches_after_renumbering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = run_sweep(self.config(Path(temp)))
        first = min(
            (cell for cell in report["cells"] if cell["edit"] == "if (n) {}"),
            key=lambda cell: cell["line"],
        )
        self.assertEqual(first["oracle"], "yes")

    def test_a_broken_identity_gate_stops_the_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = self.config(Path(temp), environment={"FAKE_BREAK_GATE": "1"})
            with self.assertRaises(LeverSweepError) as raised:
                run_sweep(config)
        self.assertIn("IDENTITY GATE", str(raised.exception))

    def test_an_unaccepted_force_stops_the_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(LeverSweepError) as raised:
                run_sweep(self.config(Path(temp), oracle="p1:w99=c15"))
        self.assertIn("not accepted", str(raised.exception))

    def test_the_command_exits_zero_on_a_reproduction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            status, output, error = run_cli(
                [
                    "sweep",
                    "levers",
                    str(FIXTURES / "demo.c"),
                    "--function",
                    "demo",
                    "--target",
                    str(FIXTURES / "target.objdump"),
                    "--compile-command",
                    FAKE_CC,
                    "--oracle",
                    "p1:w10=c15",
                    "--levers",
                    "boundary,keep_alive",
                    "--scratch",
                    temp,
                    "--json",
                ]
            )
        self.assertEqual(status, 0, error)
        data = json.loads(output)
        self.assertEqual(data["summary"]["oracle_yes"], 4)
        self.assertEqual(set(data["generated_by_lever"]), {"boundary", "keep_alive"})

    def test_a_dry_run_counts_cells_without_measuring(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = run_sweep(
                self.config(Path(temp), dry_run=True, levers=("boundary",))
            )
        self.assertEqual(report["measured"], len(report["cells"]))
        self.assertNotIn("summary", report)

    def test_the_sweep_owns_the_trace_variables(self) -> None:
        status, _, error = run_cli(
            [
                "lever-sweep",
                str(FIXTURES / "demo.c"),
                "--function",
                "demo",
                "--target",
                str(FIXTURES / "target.objdump"),
                "--compile-command",
                FAKE_CC,
                "--oracle",
                "p1:w10=c15",
                "--env",
                "CDX_FORCE=p1:w1=c2",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("may not set CDX_FORCE", error)

    def test_an_oracle_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(LeverSweepError):
                run_sweep(self.config(Path(temp), oracle=""))


if __name__ == "__main__":
    unittest.main()
