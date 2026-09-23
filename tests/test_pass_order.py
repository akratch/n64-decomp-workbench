"""The pass-order model reproduces the mini-TU rules and reads a listing."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.pass_order import (
    Statement,
    parse_annotations,
    pass_order_report,
    replay,
)

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "examples" / "fixtures" / "pass-order-mini.c"
LISTING = ROOT / "examples" / "fixtures" / "pass-order-mini.s"


def fates(*statements: Statement) -> list[tuple[int, str, str]]:
    return [(v.statement.line, v.fate, v.rule) for v in replay(statements)]


def s(line: int, role: str, block: int, value: str = "?", var: str = "i") -> Statement:
    return Statement(line, role, None if role == "call" else var, block, value)


class RuleTests(unittest.TestCase):
    def test_a_guard_reset_kills_the_earlier_def(self) -> None:
        """m1: nothing reads the delay-slot def before the guard overwrites it."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "call", 181),
            s(3, "def", 184, "0"),
            s(4, "loop", 184),
        )
        self.assertEqual(result[0][1:], ("deleted", "dse-no-counted-read"))
        self.assertEqual(result[3][1:], ("folded-init", "sr-own-block-def"))

    def test_a_folded_read_does_not_keep_a_def_alive(self) -> None:
        """m12b: `x += i & 0` a block earlier is folded, and the def dies."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "read", 183),
            s(3, "def", 184, "0"),
            s(4, "loop", 184),
        )
        self.assertEqual(result[1][1:], ("folded", "early-fold"))
        self.assertEqual(result[0][1:], ("deleted", "dse-no-counted-read"))

    def test_a_read_followed_by_a_def_in_its_block_counts(self) -> None:
        """m11f: the same read with the reset after it in 184 keeps the def."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "read", 184),
            s(3, "def", 184, "0"),
            s(4, "loop", 184),
        )
        self.assertEqual(result[1][1:], ("counted", "read-before-def-in-block"))
        self.assertEqual(result[0][1], "emitted")
        # m22c: behind a read of i, the redundant store is kept
        self.assertEqual(result[2][1:], ("emitted", "redundant-blocked"))

    def test_a_redundant_store_is_deleted_only_as_its_blocks_first_reference(
        self,
    ) -> None:
        """m22a: behind an unrelated statement the plain reset is deleted."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "selfdef", 181, "0"),
            s(3, "call", 184),
            s(4, "def", 184, "0"),
            s(5, "loop", 184),
        )
        self.assertEqual(result[3][1:], ("deleted", "redundant-first-reference"))

    def test_the_init_fold_needs_the_preheaders_own_def(self) -> None:
        """m11b: known from 180 through the calls, the init still stays unfolded."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "call", 181),
            s(3, "loop", 184),
        )
        self.assertEqual(result[-1][1:], ("unfolded-init", "sr-no-own-block-def"))

    def test_a_call_between_the_reset_and_its_loop_kills_the_fold(self) -> None:
        result = fates(s(1, "def", 184, "0"), s(2, "call", 184), s(3, "loop", 184))
        self.assertEqual(result[-1][1:], ("unfolded-init", "sr-call-kills-fold"))

    def test_a_conditional_store_of_a_known_value_is_deleted_first(self) -> None:
        """m20: whatever the condition, the if-body no-op rule removes it."""

        result = fates(
            s(1, "def", 180, "0"),
            s(2, "cond", 183, "0"),
            s(3, "loop", 184),
        )
        self.assertEqual(result[1][1:], ("deleted", "conditional-known-store"))
        self.assertEqual(result[2][1:], ("unfolded-init", "sr-no-own-block-def"))

    def test_a_self_reading_def_keeps_the_def_it_reads(self) -> None:
        """m24f: `i &= 0` after the first call reads the delay-slot def."""

        verdicts = replay(
            (s(1, "def", 180, "0"), s(2, "call", 181), s(3, "selfdef", 181, "0"))
        )
        self.assertEqual(verdicts[0].fate, "emitted")
        self.assertIn("line 3", verdicts[0].notes[0])
        self.assertEqual(verdicts[2].fate, "survives-dse")
        self.assertTrue(verdicts[2].notes)  # both measured outcomes are stated


class AnnotationTests(unittest.TestCase):
    def test_annotations_read_role_variable_block_and_value(self) -> None:
        statements = parse_annotations(MINI.read_text(encoding="utf-8"))
        self.assertEqual(statements[0].role, "def")
        self.assertEqual(statements[0].value, "0")
        self.assertEqual(statements[2].variable, None)
        self.assertEqual(statements[-1].role, "loop")

    def test_malformed_annotations_are_refused_with_the_line(self) -> None:
        for text, message in (
            ("i = 0; /* @pass store i block=1 */", "unknown @pass role"),
            ("i = 0; /* @pass def block=1 */", "needs block=N|names no variable"),
            ("i = 0; /* @pass def i */", "needs block=N"),
            ("int x;", "no @pass annotations"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                parse_annotations(text)


class ListingTests(unittest.TestCase):
    def test_the_fixture_agrees_with_the_model(self) -> None:
        report = pass_order_report(
            parse_annotations(MINI.read_text(encoding="utf-8")),
            listing=LISTING.read_text(encoding="utf-8"),
        )
        self.assertTrue(report["observed"])
        self.assertEqual(report["unexplained"], [])
        guard = next(row for row in report["statements"] if row["line"] == 17)
        self.assertEqual(
            (guard["predicted"], guard["observed"]), ("deleted", "deleted")
        )
        self.assertEqual(guard["law"], "L164")

    def test_a_def_the_model_cannot_explain_is_reported(self) -> None:
        listing = LISTING.read_text(encoding="utf-8").replace(
            "\t.loc\t1 19\n", "\t.loc\t1 17\n\tmove\t$16, $0\n\t.loc\t1 19\n"
        )
        report = pass_order_report(
            parse_annotations(MINI.read_text(encoding="utf-8")), listing=listing
        )
        self.assertEqual(report["unexplained"], [17])

    def test_a_listing_without_loc_records_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, ".loc"):
            pass_order_report(
                parse_annotations(MINI.read_text(encoding="utf-8")),
                listing="\tmove\t$16, $0\n",
            )


COMPILER = r"""
import pathlib, sys
source = pathlib.Path(sys.argv[-1])
listing = pathlib.Path(sys.argv[1]).read_text()
(pathlib.Path.cwd() / (source.stem + ".s")).write_text(listing)
"""


class CommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_journey_spelling_with_a_listing(self) -> None:
        status, stdout, _ = self.run_cli(
            ["pass", "order", str(MINI), "--listing", str(LISTING), "--json"]
        )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["schema"], "decomp-workbench-pass-order-v1")

    def test_compile_mode_runs_in_a_private_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            compiler = Path(temporary) / "fake_cc.py"
            compiler.write_text(COMPILER, encoding="utf-8")
            template = f"{sys.executable} {compiler} {LISTING} -S {{source}}"
            status, stdout, stderr = self.run_cli(
                ["pass-order", str(MINI), "--compile-command", template]
            )
            self.assertEqual(status, 0, stderr)
            self.assertIn("model checked against the listing", stdout)
            self.assertEqual(
                sorted(p.name for p in Path(temporary).iterdir()), ["fake_cc.py"]
            )

    def test_model_only_without_a_listing(self) -> None:
        status, stdout, _ = self.run_cli(["pass-order", str(MINI)])
        self.assertEqual(status, 0)
        self.assertIn("model only", stdout)


if __name__ == "__main__":
    unittest.main()
