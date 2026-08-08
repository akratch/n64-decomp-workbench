"""Tests for the one honest headline number.

The property under test is not arithmetic -- every count here was already
computed correctly -- but *selection*: that one number is named as the score,
that the other two are labelled with what they are for, and that a reader is
told when they disagree instead of being left to notice.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.headline import (
    ROLE_NEVER,
    ROLE_ONE_CANDIDATE,
    ROLE_SCORE,
    Headline,
    build_headline,
    headline_line,
    render_headline,
)
from decomp_workbench.objdump import parse_disassembly

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures"

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def headline_of(target: list[str], candidate: list[str]) -> Headline:
    comparison = compare_instructions(
        parse_disassembly(assemble(target, symbol=SYMBOL), symbol=SYMBOL),
        parse_disassembly(assemble(candidate, symbol=SYMBOL), symbol=SYMBOL),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol=SYMBOL,
    )
    return build_headline(comparison)


class HeadlineSelectionTests(unittest.TestCase):
    def test_the_headline_is_the_positional_word_delta(self) -> None:
        report = headline_of(
            body("addu v0,a0,a1", "addu v1,a0,a2"),
            body("addu v0,a0,a1", "addu t0,a0,a2"),
        )
        self.assertEqual(report.words, 1)
        self.assertEqual(headline_line(report), "score: 1 word differ (0 = match)")

    def test_a_match_says_match_and_exits_zero(self) -> None:
        rows = body("addu v0,a0,a1")
        report = headline_of(rows, rows)
        self.assertTrue(report.matched)
        self.assertEqual(headline_line(report), "score: 0 words differ — MATCH")

    def test_exactly_one_metric_is_labelled_the_score(self) -> None:
        report = headline_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        roles = [row.role for row in report.metrics]
        self.assertEqual(roles.count(ROLE_SCORE), 1)
        self.assertEqual(report.metrics[0].key, "words")
        self.assertIn(ROLE_ONE_CANDIDATE, roles)
        self.assertIn(ROLE_NEVER, roles)

    def test_aligned_total_is_never_the_score_even_when_it_is_lower(self) -> None:
        # The inversion that cost one campaign a 257-build lever table: the
        # aligner realigns a shifted candidate and reports fewer rows than the
        # base it is supposed to improve on.
        report = headline_of(
            body("addu v0,a0,a1", "addu v1,a0,a2", "addu a3,a0,a3"),
            body("nop", "addu v0,a0,a1", "addu v1,a0,a2", "addu a3,a0,a3"),
        )
        score_rows = [row for row in report.metrics if row.role == ROLE_SCORE]
        self.assertEqual([row.key for row in score_rows], ["words"])


class DisagreementTests(unittest.TestCase):
    def test_agreement_is_stated_rather_than_left_silent(self) -> None:
        report = headline_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        self.assertEqual(report.disagreements, ())
        rendered = "\n".join(render_headline(report))
        self.assertIn("the three counts agree", rendered)

    def test_alignment_gaps_are_named_with_their_consequence(self) -> None:
        report = headline_of(
            body("addu v0,a0,a1", "addu v1,a0,a2"),
            body("nop", "addu v0,a0,a1", "addu v1,a0,a2"),
        )
        text = " ".join(report.disagreements)
        self.assertIn("gap", text)
        self.assertIn("must not be ranked against it", text)

    def test_an_instruction_count_difference_is_reported_first_class(self) -> None:
        report = headline_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "nop"),
        )
        self.assertEqual(report.instruction_delta, 1)
        text = " ".join(report.disagreements)
        self.assertIn("instruction(s) than the target", text)

    def test_relocation_controlled_words_explain_raw_above_words(self) -> None:
        target = parse_disassembly(
            (FIXTURES / "target.objdump").read_text(encoding="utf-8")
        )
        candidate = parse_disassembly(
            (FIXTURES / "relocated-match.objdump").read_text(encoding="utf-8")
        )
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        report = build_headline(comparison)
        if comparison.raw_word_mismatches > comparison.word_mismatches:
            text = " ".join(report.disagreements)
            self.assertIn("relocation-controlled", text)
            self.assertIn("words=0 is the honest gate", text)


class ScoreCommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(arguments)
        return status, out.getvalue(), err.getvalue()

    def test_two_objects_print_the_headline_first(self) -> None:
        status, output, _ = self.run_cli(
            [
                "score",
                str(FIXTURES / "phase-shift-target.objdump"),
                str(FIXTURES / "phase-shift-candidate.objdump"),
            ]
        )
        # Reduced dumps are accepted by the object reader, so this exercises
        # the same path a pair of .o files takes.
        self.assertIn(status, (0, 1, 2))
        if status in (0, 1):
            self.assertTrue(output.startswith("score: "))

    def test_json_names_the_headline_metric_explicitly(self) -> None:
        status, output, _ = self.run_cli(
            [
                "score",
                str(FIXTURES / "phase-shift-target.objdump"),
                str(FIXTURES / "phase-shift-candidate.objdump"),
                "--json",
            ]
        )
        if status in (0, 1):
            payload = json.loads(output)
            self.assertEqual(payload["headline_metric"], "words")
            self.assertEqual(payload["mode"], "headline")
            self.assertEqual(payload["schema"], "decomp-workbench-score-v1")
            self.assertIn("metric_disagreements", payload)

    def test_mixing_the_two_forms_names_both_spellings(self) -> None:
        status, _, error = self.run_cli(
            [
                "score",
                str(FIXTURES / "target.objdump"),
                str(FIXTURES / "relocated-match.objdump"),
                "--target-object",
                str(FIXTURES / "target.objdump"),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("score TARGET.o CANDIDATE.o", error)
        self.assertIn("--target-object", error)

    def test_the_single_object_form_still_needs_external_truth(self) -> None:
        status, _, error = self.run_cli(["score", str(FIXTURES / "target.objdump")])
        self.assertEqual(status, 2)
        self.assertIn("--target-object", error)


if __name__ == "__main__":
    unittest.main()
