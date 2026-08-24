"""Layout-aware verdicts: the aligner runs itself on structure-mismatch.

`words` is positional. Move a block and every row between its old and its new
home is compared against a stranger, so a candidate whose real edit script is
*one relocated block* reports a residual three orders of magnitude larger than
its distance. Two campaign waves ranked such candidates below strictly worse
ones on that number (docs/history/postmortem-2026-08-24-cef4c-exact.md, item
5). These tests hold the shape of the fix: on that verdict, and only on that
verdict, the shift-tolerant edit script is computed and reported beside the
positional count.
"""

from __future__ import annotations

import unittest

from mips_asm import assemble

from decomp_workbench.compare import compare_instructions, layout_summary
from decomp_workbench.comparison_render import layout_lines
from decomp_workbench.model import Comparison, Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.shift_align import build_shift_diff, moved_blocks

#: A prologue, a distinctive block, a second block that shares no opcode with
#: it, then an epilogue. The opcode sets are disjoint on purpose: that is what
#: makes the aligner report a relocation as delete-plus-insert rather than
#: quietly pairing the two blocks off as replacements.
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
BLOCK = [
    "addu v0,a0,a1",
    "or t1,v0,a2",
    "xor t2,t1,a3",
    "sltu t3,t2,t1",
    "nor t4,t3,t2",
]
MIDDLE = [
    "lw s0,0(a0)",
    "lhu s1,4(a0)",
    "mult s0,s1",
    "sb s1,8(a0)",
]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]

TARGET = PROLOGUE + BLOCK + MIDDLE + EPILOGUE
#: The same instructions with the block moved after the middle: a pure
#: permutation, whose instruction multiset survives intact.
PERMUTED = PROLOGUE + MIDDLE + BLOCK + EPILOGUE
#: The same move, plus one instruction the candidate added. The multiset no
#: longer survives, so this is the `structure-mismatch` half of the pair.
PERMUTED_PLUS = PROLOGUE + MIDDLE + BLOCK + ["andi s2,s1,15"] + EPILOGUE
#: Genuinely different code of the same length: no block is relocated.
REWRITTEN = (
    PROLOGUE
    + BLOCK
    + ["sh s1,2(a0)", "lb s0,1(a0)", "multu s0,s1", "srl s1,s0,3"]
    + EPILOGUE
)


def _rows(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol="demo"))


def _compare(target: list[str], candidate: list[str]) -> Comparison:
    return compare_instructions(
        _rows(target),
        _rows(candidate),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol=None,
    )


class MovedBlockTests(unittest.TestCase):
    def test_a_relocated_block_is_found_by_its_content(self) -> None:
        target, candidate = _rows(TARGET), _rows(PERMUTED)
        diff = build_shift_diff(target, candidate, granularity="normalized")
        moved = moved_blocks(diff, target, candidate)
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0].rows, len(MIDDLE))
        self.assertNotEqual(moved[0].displacement, 0)

    def test_a_relocation_folded_into_a_replace_block_is_still_found(self) -> None:
        # The aligner swallows an unrelated neighbouring edit into a `replace`
        # rather than reporting a clean delete/insert pair. Searching for the
        # content rather than pairing blocks is what survives that.
        target, candidate = _rows(TARGET), _rows(PERMUTED_PLUS)
        diff = build_shift_diff(target, candidate, granularity="normalized")
        moved = moved_blocks(diff, target, candidate)
        self.assertEqual([block.rows for block in moved], [len(MIDDLE)])

    def test_different_code_is_not_a_moved_block(self) -> None:
        target, candidate = _rows(TARGET), _rows(REWRITTEN)
        diff = build_shift_diff(target, candidate, granularity="normalized")
        self.assertEqual(moved_blocks(diff, target, candidate), ())

    def test_a_short_run_is_below_the_noise_floor(self) -> None:
        target = _rows([*PROLOGUE, "nop", "nop", *BLOCK, *EPILOGUE])
        candidate = _rows([*PROLOGUE, *BLOCK, "nop", "nop", *EPILOGUE])
        diff = build_shift_diff(target, candidate, granularity="normalized")
        self.assertEqual(moved_blocks(diff, target, candidate), ())


class LayoutSummaryTests(unittest.TestCase):
    def test_the_summary_reports_the_permutation_and_the_positional_cost(
        self,
    ) -> None:
        summary = layout_summary(_rows(TARGET), _rows(PERMUTED))
        self.assertEqual(summary["moved_block_count"], 1)
        self.assertEqual(summary["moved_rows"], len(MIDDLE))
        # The whole point: the shift-tolerant distance is below what a
        # positional count charges for the same object.
        self.assertLess(
            int(summary["rows_away"]), int(summary["positional_mismatches"])
        )


class ComparisonWiringTests(unittest.TestCase):
    def test_structure_mismatch_carries_the_layout_automatically(self) -> None:
        comparison = _compare(TARGET, PERMUTED_PLUS)
        self.assertEqual(comparison.verdict, "structure-mismatch")
        assert comparison.layout is not None
        self.assertEqual(comparison.layout["moved_block_count"], 1)
        self.assertLess(int(comparison.layout["rows_away"]), comparison.word_mismatches)

    def test_schedule_mismatch_carries_it_too(self) -> None:
        # A permutation whose instruction multiset survives lands here, not on
        # structure-mismatch. Reporting the edit script for only one of the two
        # would leave half the permutations ranked on the inflated number.
        comparison = _compare(TARGET, PERMUTED)
        self.assertEqual(comparison.verdict, "schedule-mismatch")
        assert comparison.layout is not None
        self.assertEqual(comparison.layout["moved_block_count"], 1)

    def test_the_guidance_leads_with_the_permutation(self) -> None:
        comparison = _compare(TARGET, PERMUTED_PLUS)
        self.assertTrue(comparison.guidance[0].startswith("Layout:"))
        self.assertIn("permutation", comparison.guidance[0])

    def test_the_terminal_prints_the_script_beside_words(self) -> None:
        comparison = _compare(TARGET, PERMUTED_PLUS)
        rendered = "\n".join(layout_lines(comparison))
        self.assertIn("moved blocks: 1", rendered)
        self.assertIn("rows_away=", rendered)
        self.assertIn(f"against words={comparison.word_mismatches}", rendered)

    def test_a_structure_mismatch_with_no_permutation_says_so(self) -> None:
        comparison = _compare(TARGET, REWRITTEN)
        assert comparison.layout is not None
        self.assertEqual(comparison.layout["moved_block_count"], 0)
        rendered = "\n".join(layout_lines(comparison))
        self.assertIn("moved blocks: none", rendered)
        # A non-permutation must not grow a Layout: lead: the positional
        # counts are reading real changed code and are the right headline.
        self.assertFalse(comparison.guidance[0].startswith("Layout:"))

    def test_other_verdicts_do_not_pay_for_an_alignment(self) -> None:
        # An allocation residual has no layout question, and running the
        # aligner on every comparison would cost a campaign's whole wave.
        renamed = [line.replace("v0", "v1") for line in TARGET]
        comparison = _compare(TARGET, renamed)
        self.assertEqual(comparison.verdict, "allocation-mismatch")
        self.assertIsNone(comparison.layout)

    def test_the_layout_reaches_json(self) -> None:
        payload = _compare(TARGET, PERMUTED_PLUS).as_dict()
        self.assertEqual(payload["layout"]["moved_block_count"], 1)
        self.assertEqual(
            payload["layout"]["schema"], "decomp-workbench-layout-summary-v1"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
