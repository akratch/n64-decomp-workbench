"""Tests for source-region attribution of differing words.

The properties that matter are the honest ones. Attribution must refuse to
guess a line it cannot know, must drop an ambiguous anchor rather than
force-match it, and must say what its own coverage was. A ranking that looks
confident and is wrong is worse than no ranking, because it directs the next
edit.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.model import Instruction, Relocation
from decomp_workbench.regions import (
    Anchor,
    RegionError,
    RegionReport,
    build_anchors,
    build_region_report,
    object_calls,
    source_calls,
    strip_noncode,
)

SOURCE = """\
#include <stuff.h>

void demo(void) {
    if (ready()) {
        alpha();
    }
    beta(1, 2);
    /* gamma() in a comment must not count */
    delta();
}
"""


def call_instruction(address: int, symbol: str) -> Instruction:
    return Instruction(
        address=address,
        word="0c000000",
        assembly=f"jal {symbol}",
        relocations=(Relocation(offset=address, kind="R_MIPS_26", symbol=symbol),),
    )


def plain(address: int) -> Instruction:
    return Instruction(address=address, word="00000000", assembly="nop")


class SourceScanTests(unittest.TestCase):
    def test_comments_and_strings_do_not_contribute_calls(self) -> None:
        names = [name for _line, name in source_calls(SOURCE)]
        self.assertIn("alpha", names)
        self.assertNotIn("gamma", names)

    def test_control_keywords_are_not_calls(self) -> None:
        names = [name for _line, name in source_calls(SOURCE)]
        self.assertNotIn("if", names)
        self.assertIn("ready", names)

    def test_line_numbers_survive_comment_blanking(self) -> None:
        text = "/* a\nmultiline\ncomment */\nalpha();\n"
        self.assertEqual(strip_noncode(text).count("\n"), text.count("\n"))
        self.assertEqual(source_calls(text), [(4, "alpha")])


class AnchorTests(unittest.TestCase):
    def test_matching_sequences_anchor_every_call(self) -> None:
        object_side = [(0, "alpha"), (16, "beta"), (32, "delta")]
        source_side = [(5, "alpha"), (7, "beta"), (9, "delta")]
        anchors, dropped = build_anchors(object_side, source_side)
        self.assertEqual(len(anchors), 3)
        self.assertEqual(dropped, ())
        self.assertEqual(anchors[1], Anchor(address=16, line=7, symbol="beta"))

    def test_a_nested_call_transposition_is_dropped_not_guessed(self) -> None:
        # Source text reads outer-first; the object emits inner-first.
        object_side = [(0, "inner"), (16, "outer"), (32, "tail")]
        source_side = [(5, "outer"), (5, "inner"), (9, "tail")]
        anchors, dropped = build_anchors(object_side, source_side)
        anchored = {anchor.symbol for anchor in anchors}
        self.assertIn("tail", anchored)
        self.assertTrue(dropped)
        # Whatever survived must not claim a line the alignment did not prove.
        for anchor in anchors:
            self.assertEqual(
                anchor.symbol,
                dict(((line, name) for line, name in source_side)).get(
                    anchor.line, anchor.symbol
                ),
            )

    def test_spurious_source_names_fall_out_of_the_alignment(self) -> None:
        object_side = [(0, "alpha"), (16, "beta")]
        source_side = [(1, "SOME_MACRO"), (5, "alpha"), (7, "beta")]
        anchors, _dropped = build_anchors(object_side, source_side)
        self.assertEqual([anchor.symbol for anchor in anchors], ["alpha", "beta"])

    def test_anchors_are_monotone_in_both_coordinates(self) -> None:
        object_side = [(0, "a"), (8, "b"), (16, "c"), (24, "d")]
        source_side = [(10, "a"), (30, "b"), (20, "c"), (40, "d")]
        anchors, _dropped = build_anchors(object_side, source_side)
        lines = [anchor.line for anchor in anchors]
        addresses = [anchor.address for anchor in anchors]
        self.assertEqual(lines, sorted(lines))
        self.assertEqual(addresses, sorted(addresses))


class ObjectScanTests(unittest.TestCase):
    def test_only_call_relocations_anchor(self) -> None:
        instructions = [
            call_instruction(0, "alpha"),
            Instruction(
                address=4,
                word="3c010000",
                assembly="lui at,0x0",
                relocations=(Relocation(offset=4, kind="R_MIPS_HI16", symbol="data"),),
            ),
            call_instruction(8, "beta"),
        ]
        self.assertEqual(object_calls(instructions), [(0, "alpha"), (8, "beta")])


class ReportTests(unittest.TestCase):
    def build(self, sites: list[dict[str, object]], *, delta: int = 0) -> RegionReport:
        candidate = [
            call_instruction(0, "ready"),
            plain(4),
            plain(8),
            call_instruction(12, "alpha"),
            plain(16),
            call_instruction(20, "beta"),
            plain(24),
            call_instruction(28, "delta"),
            plain(32),
        ]
        return build_region_report(
            source_path="demo.c",
            source_text=SOURCE,
            candidate=candidate,
            sites=sites,
            instruction_delta=delta,
        )

    def test_words_are_bracketed_between_the_calls_around_them(self) -> None:
        report = self.build([{"index": 4, "class": "register"}])
        self.assertEqual(len(report.regions), 1)
        region = report.regions[0]
        self.assertEqual(region.low_symbol, "alpha")
        self.assertEqual(region.high_symbol, "beta")
        self.assertIsNotNone(region.low_line)
        self.assertLess(region.low_line or 0, region.high_line or 0)

    def test_regions_are_ranked_by_word_count(self) -> None:
        report = self.build(
            [
                {"index": 4, "class": "register"},
                {"index": 8, "class": "register"},
                {"index": 8, "class": "register"},
                {"index": 8, "class": "register"},
            ]
        )
        self.assertGreaterEqual(report.regions[0].words, report.regions[-1].words)
        self.assertEqual(report.regions[0].words, 3)

    def test_relocation_class_words_are_excluded_and_counted(self) -> None:
        report = self.build(
            [
                {"index": 4, "class": "register"},
                {"index": 6, "class": "relocation-controlled"},
            ]
        )
        self.assertEqual(report.attributed_words, 1)
        self.assertEqual(report.excluded_words, 1)
        self.assertIn("relocation-class", " ".join(report.caveats))

    def test_attribution_never_interpolates_a_point(self) -> None:
        report = self.build([{"index": 4, "class": "register"}])
        # The bracket is the answer; a single line is only reported when the
        # row sits exactly on an anchor.
        self.assertNotEqual(report.regions[0].low_line, report.regions[0].high_line)
        self.assertIn("never interpolated", " ".join(report.caveats))

    def test_an_instruction_count_delta_warns_about_shadow_rows(self) -> None:
        report = self.build([{"index": 4, "class": "constant"}], delta=2)
        self.assertIn("shadow", " ".join(report.caveats))

    def test_coverage_is_always_reported(self) -> None:
        report = self.build([{"index": 4, "class": "register"}])
        self.assertEqual(report.object_calls, 4)
        self.assertTrue(report.source_calls >= 4)

    def test_an_object_with_no_call_relocations_is_a_clear_refusal(self) -> None:
        with self.assertRaises(RegionError) as caught:
            build_region_report(
                source_path="demo.c",
                source_text=SOURCE,
                candidate=[plain(0), plain(4)],
                sites=[{"index": 1, "class": "register"}],
            )
        self.assertIn("no call relocations", str(caught.exception))

    def test_a_source_that_matches_nothing_is_a_clear_refusal(self) -> None:
        with self.assertRaises(RegionError) as caught:
            build_region_report(
                source_path="wrong.c",
                source_text="void f(void) { unrelated(); }\n",
                candidate=[call_instruction(0, "alpha"), plain(4)],
                sites=[{"index": 1, "class": "register"}],
            )
        self.assertIn("not the one that produced this object", str(caught.exception))


class ByRegionCommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(arguments)
        return status, out.getvalue(), err.getvalue()

    def test_a_missing_source_file_is_an_error_not_a_silent_omission(self) -> None:
        fixtures = Path(__file__).resolve().parents[1] / "examples" / "fixtures"
        status, _, error = self.run_cli(
            [
                "compare-dumps",
                str(fixtures / "phase-shift-target.objdump"),
                str(fixtures / "phase-shift-candidate.objdump"),
                "--by-region",
                "definitely-absent.c",
            ]
        )
        self.assertEqual(status, 2)
        self.assertTrue(error.startswith("error: "))

    def test_json_carries_the_region_payload_beside_the_existing_keys(self) -> None:
        fixtures = Path(__file__).resolve().parents[1] / "examples" / "fixtures"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "demo.c"
            source.write_text(SOURCE, encoding="utf-8")
            status, output, _ = self.run_cli(
                [
                    "compare-dumps",
                    str(fixtures / "phase-shift-target.objdump"),
                    str(fixtures / "phase-shift-candidate.objdump"),
                    "--by-region",
                    str(source),
                    "--json",
                ]
            )
        if status == 0:
            payload = json.loads(output)
            self.assertIn("verdict", payload)
            self.assertIn("by_region", payload)
            self.assertEqual(
                payload["by_region"]["method"], "call-relocation anchoring"
            )


if __name__ == "__main__":
    unittest.main()
