"""Aligned counts must never be read across candidates without a caution.

Derived from the recorded `object_interaction` campaign, whose real objects
produced these shapes against one 4644-instruction target:

===================  ======  =====  ====  =======  ====
candidate            aligned  words   raw  opcodes  gaps
===================  ======  =====  ====  =======  ====
p2b-final (base)       1865   1865  1894        1     0
p3d-final (renaming)    572    572   617        1     0
p3c-05 (perturbed)     1435   2918  2952     1807     4
===================  ======  =====  ====  =======  ====

`p3c-05` reported *fewer* aligned rows than the base it was supposed to
improve on while holding 2918 mismatching words, and a 257-build lever table
was ordered on that inversion before the stage's own verification caught it.
The fixtures below are synthetic -- the campaign's objects are ROM-derived and
not redistributable -- but they reproduce the same three facts: gaps only on
the perturbed side, `aligned_total == word_mismatches` on the renaming side,
and an aligned total that inverts the honest order.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mips_asm import assemble

from decomp_workbench import object_cli
from decomp_workbench.cli import main
from decomp_workbench.compare import (
    MIXED_ALIGNMENT_CAUTION,
    compare_instructions,
    rank_comparisons,
)
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import parse_disassembly

TARGET = [
    "addiu sp,sp,-32",
    "sw ra,28(sp)",
    "sw s0,24(sp)",
    "lw t0,0(a0)",
    "lw t1,4(a0)",
    "addu t2,t0,t1",
    "sw t2,8(a0)",
    "lw t3,12(a0)",
    "lw t4,16(a0)",
    "addu t5,t3,t4",
    "sw t5,20(a0)",
    "lw t6,24(a0)",
    "lw t7,28(a0)",
    "addu t8,t6,t7",
    "sw t8,32(a0)",
    "lw s0,24(sp)",
    "lw ra,28(sp)",
    "jr ra",
    "addiu sp,sp,32",
]

#: A pure register renaming: same opcodes in the same order, so the aligner
#: never inserts a gap and `aligned_total == word_mismatches` holds.
RENAMED = [
    line.replace("t0", "v0")
    .replace("t1", "v1")
    .replace("t2", "a1")
    .replace("t3", "a2")
    .replace("t4", "a3")
    .replace("t5", "s2")
    if index in range(3, 11)
    else line
    for index, line in enumerate(TARGET)
]

#: One instruction moved eleven slots later. The aligner realigns around it and
#: reports two rows; positionally, twelve words differ.
PERTURBED = TARGET[:3] + TARGET[4:15] + [TARGET[3]] + TARGET[15:]


def compare_lines(target: list[str], candidate: list[str], name: str) -> Comparison:
    """Compare two assembled instruction lists as one function."""

    return compare_instructions(
        parse_disassembly(assemble(target, symbol="demo"), symbol="demo"),
        parse_disassembly(assemble(candidate, symbol="demo"), symbol="demo"),
        target_name="target.o",
        candidate_name=name,
        symbol="demo",
    )


def renamed() -> Comparison:
    return compare_lines(TARGET, RENAMED, "renamed.o")


def perturbed() -> Comparison:
    return compare_lines(TARGET, PERTURBED, "perturbed.o")


class AlignmentGapTests(unittest.TestCase):
    def test_a_renaming_has_no_gaps_and_no_caution(self) -> None:
        item = renamed()
        self.assertEqual(item.aligned_insertions, 0)
        self.assertEqual(item.aligned_deletions, 0)
        self.assertEqual(item.aligned_gaps, 0)
        self.assertEqual(item.opcode_mismatches, 0)
        # The invariant the campaign wrote down: aligned rows and positional
        # words are the same number exactly when nothing moved.
        self.assertEqual(item.aligned_total, item.word_mismatches)
        self.assertTrue(item.alignment_comparable)
        self.assertIsNone(item.alignment_caution)

    def test_a_perturbed_schedule_reports_gaps_and_cautions(self) -> None:
        item = perturbed()
        self.assertEqual(item.aligned_insertions, 1)
        self.assertEqual(item.aligned_deletions, 1)
        self.assertEqual(item.aligned_gaps, 2)
        self.assertFalse(item.alignment_comparable)
        self.assertEqual(
            item.alignment_caution,
            "caution: alignment inserted 2 gaps (9 opcode mismatches) -- "
            "compare candidates on raw words, not aligned rows",
        )

    def test_the_aligned_total_inverts_the_honest_order(self) -> None:
        """The recorded defect, reproduced: fewer rows, far more damage."""

        base, moved = renamed(), perturbed()
        self.assertLess(moved.aligned_total, base.aligned_total)
        self.assertGreater(moved.word_mismatches, base.word_mismatches)
        self.assertGreater(moved.opcode_mismatches, base.opcode_mismatches)

    def test_a_mixed_set_is_ordered_on_words_not_aligned_rows(self) -> None:
        ordered, mixed = rank_comparisons([perturbed(), renamed()])
        self.assertTrue(mixed)
        self.assertEqual(
            [item.candidate for item in ordered], ["renamed.o", "perturbed.o"]
        )

    def test_a_uniform_set_keeps_the_aligned_ordering(self) -> None:
        """Aligned rows still own the ranking where they are comparable."""

        near = compare_lines(TARGET, RENAMED, "near.o")
        far = compare_lines(TARGET, RENAMED, "far.o")
        far.aligned_total += 1
        far.word_mismatches -= 1
        ordered, mixed = rank_comparisons([far, near])
        self.assertFalse(mixed)
        self.assertEqual([item.candidate for item in ordered], ["near.o", "far.o"])


class AlignmentReportSurfaceTests(unittest.TestCase):
    """Every scoring surface owes the reader the same three numbers."""

    def run_cli(self, arguments: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(arguments)
        return status, stdout.getvalue()

    @contextlib.contextmanager
    def dumps(self):  # type: ignore[no-untyped-def]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for name, lines in (
                ("target", TARGET),
                ("renamed", RENAMED),
                ("perturbed", PERTURBED),
            ):
                path = root / f"{name}.objdump"
                path.write_text(assemble(lines, symbol="demo"), encoding="utf-8")
                paths[name] = str(path)
            yield paths

    def test_the_summary_line_always_carries_raw_opcodes_and_gaps(self) -> None:
        with self.dumps() as paths:
            for candidate in ("renamed", "perturbed"):
                with self.subTest(candidate=candidate):
                    _, stdout = self.run_cli(
                        [
                            "compare-dumps",
                            paths["target"],
                            paths[candidate],
                            "--symbol",
                            "demo",
                        ]
                    )
                    summary = next(
                        line for line in stdout.splitlines() if "verdict=" in line
                    )
                    for key in ("words=", "raw=", "opcodes=", "gaps="):
                        self.assertIn(key, summary)

    def test_compare_prints_the_caution_before_the_numbers(self) -> None:
        with self.dumps() as paths:
            _, stdout = self.run_cli(
                [
                    "compare-dumps",
                    paths["target"],
                    paths["perturbed"],
                    "--symbol",
                    "demo",
                ]
            )
        self.assertIn("caution: alignment inserted 2 gaps", stdout)
        self.assertLess(stdout.index("caution:"), stdout.index("verdict="))
        self.assertIn("alignment gaps: insertions=1 deletions=1", stdout)

    def test_compare_stays_quiet_on_a_renaming(self) -> None:
        with self.dumps() as paths:
            _, stdout = self.run_cli(
                ["compare-dumps", paths["target"], paths["renamed"], "--symbol", "demo"]
            )
        self.assertNotIn("caution:", stdout)

    def test_the_json_carries_the_new_fields_beside_the_old_ones(self) -> None:
        with self.dumps() as paths:
            _, stdout = self.run_cli(
                [
                    "compare-dumps",
                    paths["target"],
                    paths["perturbed"],
                    "--symbol",
                    "demo",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        # Existing consumers parse these; they must not move.
        for key in ("aligned_diff_sites", "aligned_total", "diff_site_classes"):
            self.assertIn(key, payload)
        self.assertEqual(payload["aligned_insertions"], 1)
        self.assertEqual(payload["aligned_deletions"], 1)
        self.assertEqual(payload["gaps"], 2)
        self.assertEqual(payload["aligned_gaps"], 2)
        self.assertEqual(payload["opcodes"], payload["opcode_mismatches"])
        self.assertFalse(payload["alignment_comparable"])
        self.assertIn("compare candidates on raw words", payload["alignment_caution"])

    def test_diagnose_prints_the_caution_too(self) -> None:
        with self.dumps() as paths:
            _, stdout = self.run_cli(
                [
                    "diagnose-dumps",
                    paths["target"],
                    paths["perturbed"],
                    "--symbol",
                    "demo",
                    "--width",
                    "200",
                ]
            )
        self.assertIn("caution: alignment inserted 2 gaps", stdout)
        self.assertLess(stdout.index("caution:"), stdout.index("verdict="))

    def test_rank_says_it_reordered_a_mixed_set(self) -> None:
        results = {"perturbed.o": perturbed(), "renamed.o": renamed()}

        def fake_compare(_target: str, candidate: str, **_kwargs: object) -> Comparison:
            return results[candidate]

        with mock.patch.object(object_cli, "compare_objects", fake_compare):
            status, stdout = self.run_cli(
                ["rank", "target.o", "perturbed.o", "renamed.o"]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stdout.index(MIXED_ALIGNMENT_CAUTION), 0)
        self.assertLess(stdout.index("renamed.o"), stdout.index("perturbed.o"))

    def test_rank_json_names_the_metric_it_ordered_on(self) -> None:
        results = {"perturbed.o": perturbed(), "renamed.o": renamed()}

        def fake_compare(_target: str, candidate: str, **_kwargs: object) -> Comparison:
            return results[candidate]

        with mock.patch.object(object_cli, "compare_objects", fake_compare):
            _, stdout = self.run_cli(
                ["rank", "target.o", "perturbed.o", "renamed.o", "--json"]
            )
        payload = json.loads(stdout)
        self.assertTrue(payload["mixed_alignment"])
        self.assertEqual(payload["ranked_by"], "words")
        self.assertEqual(payload["results"][0]["candidate"], "renamed.o")


if __name__ == "__main__":
    unittest.main()
