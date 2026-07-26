"""Tests for object parsing and layered comparison metrics."""

from __future__ import annotations

import unittest

from decomp_workbench.compare import (
    compare_instructions,
    mismatch_ranges,
    normalize_instruction,
)
from decomp_workbench.objdump import parse_disassembly


TARGET = """
00000000 <demo>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: afbf001c  sw $ra,28($sp)
   8: 460c0000  add.s $f0,$f0,$f12
   c: 10000002  b 18 <demo+0x18>
"""

CANDIDATE = """
00000000 <demo>:
   0: 27bdffd0  addiu $sp,$sp,-48
   4: afbf002c  sw $ra,44($sp)
   8: 460c0800  add.s $f0,$f1,$f12
   c: 10000005  b 24 <demo+0x24>
"""


class CompareTests(unittest.TestCase):
    def test_parse_and_normalize(self) -> None:
        instructions = parse_disassembly(TARGET)
        self.assertEqual(len(instructions), 4)
        self.assertEqual(instructions[0].word, "27bdffe0")
        self.assertEqual(
            normalize_instruction(instructions[1].assembly),
            "sw ra,OFF(sp)",
        )
        self.assertEqual(
            normalize_instruction(instructions[3].assembly),
            "b ADDR",
        )

    def test_comparison_layers(self) -> None:
        target = parse_disassembly(TARGET)
        candidate = parse_disassembly(CANDIDATE)
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
            target_text=TARGET,
            candidate_text=CANDIDATE,
        )
        self.assertEqual(result.word_mismatches, 4)
        self.assertEqual(result.opcode_mismatches, 0)
        self.assertEqual(result.normalized_distance, 1)
        self.assertEqual(result.fp_register_mismatches, 1)
        self.assertEqual(result.fp_mismatch_ranges, [(2, 2)])
        self.assertEqual(result.target_frame_size, -32)
        self.assertEqual(result.candidate_frame_size, -48)
        self.assertFalse(result.exact)

    def test_ranges(self) -> None:
        self.assertEqual(mismatch_ranges([]), [])
        self.assertEqual(
            mismatch_ranges([1, 2, 3, 7, 9, 10]),
            [(1, 3), (7, 7), (9, 10)],
        )


if __name__ == "__main__":
    unittest.main()
