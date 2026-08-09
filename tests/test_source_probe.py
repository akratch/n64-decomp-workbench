"""The two source questions one campaign could not ask its tools.

`probe-equiv` is the check five stages did not run: two reads of a local whose
address never escapes, with no definition between them, are the same value —
so two differently-spelled expressions built from them are equal. The campaign
searched the register allocator instead.

`probe-deadread` lists the positions where a statement that emits nothing can
still move the allocator. Nothing in an object diff can point at one, because
nothing was emitted on either side.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.csource import CSourceError, scan_statements, strip_noncode
from decomp_workbench.source_probe import (
    SPELLINGS,
    dead_read_report,
    value_equality_report,
)

# One local, defined twice, read on both sides of the second definition; one
# read inside a loop; one call between two reads, to exercise the purity half.
SOURCE = """\
void demo(Object *obj) {
    f32 sp4B8;
    f32 sp4A0;
    s32 i;

    if (obj->flags) {
        sp4B8 = obj->x * obj->x;
        sp4A0 = angle(sp4B8);
        if (obj->near) {
            sp4B8 += obj->y * obj->y;
            sp4A0 = angle(sp4B8);
        }
        limit(sp4B8);
        for (i = 0; i < 4; i++) {
            step(sp4B8);
        }
    }
    tail(sp4A0);
}
"""

ADDRESS_SOURCE = """\
void demo(void) {
    f32 v;

    v = 1.0f;
    read(v);
    fill(&v);
    read(v);
}
"""

GOTO_SOURCE = """\
void demo(void) {
    f32 v;

    v = 1.0f;
    read(v);
again:
    read(v);
    goto again;
}
"""


@contextlib.contextmanager
def written(text: str, *, name: str = "work.c"):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        yield str(path)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class CSourceTests(unittest.TestCase):
    def test_comments_and_strings_cannot_create_a_definition(self) -> None:
        lines = strip_noncode('int a; /* v = 1; */ char *s = "v = 2;"; // v = 3;\n')

        self.assertNotIn("v = 1", lines[0])
        self.assertNotIn("v = 2", lines[0])
        self.assertNotIn("v = 3", lines[0])
        # Blanked, not removed: every report cites a line number.
        self.assertEqual(len(lines), 1)
        self.assertIn("int a;", lines[0])

    def test_a_sibling_branch_does_not_reach_a_later_statement(self) -> None:
        """Brace depth says these are the same block; the block path does not."""

        code = strip_noncode(
            "void f(void) {\n"
            "    if (a) {\n"
            "        v = 1;\n"
            "    }\n"
            "    if (b) {\n"
            "        read(v);\n"
            "    }\n"
            "}\n"
        )
        statements = {item.line: item for item in scan_statements(code)}

        definition, later = statements[3], statements[6]
        self.assertEqual(definition.depth, later.depth)
        self.assertFalse(later.reached_from(definition))

    def test_an_enclosing_block_does_reach_a_later_statement(self) -> None:
        code = strip_noncode(
            "void f(void) {\n    v = 1;\n    if (b) {\n        read(v);\n    }\n}\n"
        )
        statements = {item.line: item for item in scan_statements(code)}

        self.assertTrue(statements[4].reached_from(statements[2]))

    def test_a_loop_body_is_named_and_a_do_while_closes_it(self) -> None:
        code = strip_noncode(
            "void f(void) {\n"
            "    do {\n"
            "        step();\n"
            "    } while (c);\n"
            "    after();\n"
            "}\n"
        )
        statements = {item.line: item for item in scan_statements(code)}

        self.assertTrue(statements[3].in_loop)
        self.assertFalse(statements[5].in_loop)


class ValueEqualityTests(unittest.TestCase):
    def test_two_reads_with_no_definition_between_them_are_one_value(self) -> None:
        """KEY-D: the keystone was one grep and one brace match."""

        with written(SOURCE) as path:
            report = value_equality_report(path, variable="sp4B8", positions=(11, 13))

        self.assertTrue(report["callee_safe"])
        pair = report["pairs"][0]
        self.assertEqual(pair["verdict"], "SAME-VALUE")
        self.assertIn("no definition between them", pair["reasons"][0])

    def test_a_definition_between_them_is_named_as_the_reason(self) -> None:
        with written(SOURCE) as path:
            report = value_equality_report(path, variable="sp4B8", positions=(8, 13))

        pair = report["pairs"][0]
        self.assertEqual(pair["verdict"], "NOT-PROVEN")
        self.assertIn("definition at line 10", pair["reasons"][0])

    def test_an_escaping_address_withdraws_the_purity_argument(self) -> None:
        with written(ADDRESS_SOURCE) as path:
            report = value_equality_report(path, variable="v", positions=(5, 7))

        self.assertFalse(report["callee_safe"])
        self.assertEqual(report["address_taken_at"], [6])
        pair = report["pairs"][0]
        self.assertEqual(pair["verdict"], "NOT-PROVEN")

    def test_a_label_makes_textual_order_stop_describing_control_flow(self) -> None:
        with written(GOTO_SOURCE) as path:
            report = value_equality_report(path, variable="v", positions=(5, 7))

        self.assertTrue(report["ranges"][0]["control_breaks"])
        self.assertEqual(report["pairs"][0]["verdict"], "NOT-PROVEN")

    def test_the_ranges_partition_the_reads_by_definition(self) -> None:
        with written(SOURCE) as path:
            report = value_equality_report(path, variable="sp4B8")

        self.assertEqual(report["definitions"], [7, 10])
        self.assertEqual([item["defined_at"] for item in report["ranges"]], [7, 10])
        self.assertEqual(report["ranges"][0]["reads"], [8])

    def test_an_unknown_identifier_is_an_error_that_says_why(self) -> None:
        with written(SOURCE) as path:
            with self.assertRaises(CSourceError) as caught:
                value_equality_report(path, variable="nosuchlocal")

        self.assertIn("struct or union member", str(caught.exception))


class DeadReadTests(unittest.TestCase):
    def test_only_positions_a_definition_reaches_are_candidates(self) -> None:
        with written(SOURCE) as path:
            report = dead_read_report(path, variable="sp4A0")

        lines = [item["line"] for item in report["candidates"]]
        # `sp4A0` is defined at 8 and 11, both inside the `if (obj->flags)`
        # block, so line 18 -- after that block closes -- is not reached.
        self.assertIn(13, lines)
        self.assertNotIn(18, lines)
        self.assertTrue(all(item["dominated"] for item in report["candidates"]))

    def test_the_textual_reach_widens_the_set_and_marks_it(self) -> None:
        """The campaign's own sweep used the wider set and found kills in it."""

        with written(SOURCE) as path:
            narrow = dead_read_report(path, variable="sp4A0")
            wide = dead_read_report(path, variable="sp4A0", reach="textual")

        self.assertGreater(wide["candidate_count"], narrow["candidate_count"])
        self.assertIn(18, [item["line"] for item in wide["candidates"]])
        undominated = [item for item in wide["candidates"] if not item["dominated"]]
        self.assertTrue(undominated)
        self.assertEqual(wide["dominated_count"], narrow["candidate_count"])

    def test_loop_positions_are_marked_and_ranked_last(self) -> None:
        with written(SOURCE) as path:
            report = dead_read_report(path, variable="sp4B8", reach="textual")

        in_loop = [item for item in report["candidates"] if item["in_loop"]]
        self.assertTrue(in_loop)
        self.assertEqual(in_loop[-1], report["candidates"][-1])
        self.assertLess(report["loop_free_count"], report["candidate_count"])

    def test_the_patch_keeps_the_line_indentation(self) -> None:
        with written(SOURCE) as path:
            report = dead_read_report(path, variable="sp4B8")

        patch = report["candidates"][0]["patches"][0]
        self.assertEqual(patch["spelling"], "if (V != 0.0f);")
        self.assertTrue(patch["insert"].startswith("        "))
        self.assertIn("if (sp4B8 != 0.0f);", patch["insert"])

    def test_the_spelling_table_separates_the_inert_from_the_costly(self) -> None:
        spellings = {item.text: item for item in SPELLINGS}

        self.assertIn("INERT", spellings["V = 0.0f;"].note)
        self.assertIn("INERT", spellings["V = V;"].note)
        self.assertEqual(spellings["if (V);"].footprint, "0 or +2")
        self.assertEqual(spellings["if (V != 0.0f);"].footprint, "0")

    def test_a_variable_that_is_never_assigned_is_an_error(self) -> None:
        with written("void f(void) {\n    f32 v;\n    read(v);\n}\n") as path:
            with self.assertRaises(CSourceError) as caught:
                dead_read_report(path, variable="v")

        self.assertIn("there is nothing to read", str(caught.exception))


class SourceProbeCommandTests(unittest.TestCase):
    def test_equiv_prints_the_verdict_and_its_limits(self) -> None:
        with written(SOURCE) as path:
            status, out, _ = run_cli(
                ["probe-equiv", path, "--variable", "sp4B8", "--at", "11", "--at", "13"]
            )

        self.assertEqual(status, 0)
        self.assertIn("SAME-VALUE", out)
        self.assertIn("address is never taken", out)
        self.assertIn("what this does not know:", out)

    def test_equiv_json_carries_the_schema(self) -> None:
        with written(SOURCE) as path:
            status, out, _ = run_cli(
                ["probe-equiv", path, "--variable", "sp4B8", "--json"]
            )

        self.assertEqual(status, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-value-equality-v1")
        self.assertTrue(payload["callee_safe"])

    def test_deadread_prints_the_table_and_a_patch(self) -> None:
        with written(SOURCE) as path:
            status, out, _ = run_cli(["probe-deadread", path, "--variable", "sp4B8"])

        self.assertEqual(status, 0)
        self.assertIn("dead-read probe:", out)
        self.assertIn("if (sp4B8 != 0.0f);", out)
        self.assertIn("INERT", out)

    def test_deadread_writes_one_variant_per_candidate(self) -> None:
        with written(SOURCE) as path:
            output = str(Path(path).with_name("variants"))
            status, out, _ = run_cli(
                [
                    "probe-deadread",
                    path,
                    "--variable",
                    "sp4B8",
                    "--limit",
                    "2",
                    "--write",
                    output,
                ]
            )
            written_files = sorted(Path(output).glob("*.c"))
            first = written_files[0].read_text(encoding="utf-8").splitlines()

        self.assertEqual(status, 0)
        self.assertEqual(len(written_files), 2)
        self.assertIn("wrote 2 variant source(s)", out)
        # The inserted line sits before the statement it was listed against,
        # and the rest of the file is unchanged.
        self.assertTrue(any("if (sp4B8 != 0.0f);" in line for line in first))
        self.assertEqual(len(first), len(SOURCE.splitlines()) + 1)

    def test_deadread_json_carries_the_schema_and_the_reach(self) -> None:
        with written(SOURCE) as path:
            status, out, _ = run_cli(
                [
                    "probe-deadread",
                    path,
                    "--variable",
                    "sp4B8",
                    "--reach",
                    "textual",
                    "--json",
                ]
            )

        self.assertEqual(status, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-dead-read-v1")
        self.assertEqual(payload["reach"], "textual")

    def test_an_unreadable_source_reports_json_rather_than_bare_text(self) -> None:
        status, out, _ = run_cli(
            ["probe-equiv", "/nonexistent/work.c", "--variable", "v", "--json"]
        )

        self.assertEqual(status, 2)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-error-v1")

    def test_the_shipped_example_source_is_the_fixture(self) -> None:
        """`docs/source-probes.md` quotes real output of this file."""

        fixture = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "fixtures"
            / "value-equality.c"
        )
        self.assertEqual(fixture.read_text(encoding="utf-8"), SOURCE)

    def test_the_grouped_spellings_reach_the_same_commands(self) -> None:
        with written(SOURCE) as path:
            status, out, _ = run_cli(["probe", "equiv", path, "--variable", "sp4B8"])

        self.assertEqual(status, 0)
        self.assertIn("value equality:", out)


if __name__ == "__main__":
    unittest.main()
