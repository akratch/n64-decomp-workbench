"""Tests for object parsing and layered comparison metrics."""

from __future__ import annotations

import unittest

from decomp_workbench.compare import (
    compare_instructions,
    mismatch_ranges,
    normalize_instruction,
)
from decomp_workbench.objdump import (
    parse_disassembly,
    parse_relocations,
    trim_function_padding,
)

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

RELOC_TARGET = """
00000000 <demo>:
   0: 0c123456  jal 48d158 <callee>
                        0: R_MIPS_26 callee
   4: 3c010123  lui $at,0x123
                        4: R_MIPS_HI16 global
"""

RELOC_CANDIDATE = """
00000000 <demo>:
   0: 0c000000  jal 0 <callee>
                        0: R_MIPS_26 callee
   4: 3c010000  lui $at,0x0
                        4: R_MIPS_HI16 global
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
        self.assertEqual(
            normalize_instruction("addiu $t0,$t0,-1"),
            "addiu t0,t0,IMM",
        )

    def test_filters_retained_dump_by_symbol(self) -> None:
        text = (
            "00000000 <first>:\n"
            "   0: 03e00008  jr $ra\n"
            "00000004 <second>:\n"
            "   4: 00000000  nop\n"
        )
        selected = parse_disassembly(text, symbol="second")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].address, 4)

    def test_selected_symbol_owns_frame_metric(self) -> None:
        text = (
            "00000000 <first>:\n"
            "   0: 27bdffe0  addiu $sp,$sp,-32\n"
            "00000004 <second>:\n"
            "   4: 27bdffc0  addiu $sp,$sp,-64\n"
        )
        selected = parse_disassembly(text, symbol="second")
        result = compare_instructions(
            selected,
            selected,
            target_name="target",
            candidate_name="candidate",
            symbol="second",
        )
        self.assertEqual(result.candidate_frame_size, -64)

    def test_trims_zero_padding_after_return_delay_slot(self) -> None:
        instructions = parse_disassembly(
            """
00000000 <demo>:
   0: 848e004c  lh $t6,76($a0)
   4: 03e00008  jr $ra
   8: a4ae004c  sh $t6,76($a1)
   c: 00000000  nop
  10: 00000000  nop
""",
            symbol="demo",
        )
        self.assertEqual([item.address for item in instructions], [0, 4, 8])

    def test_does_not_trim_a_return_delay_slot(self) -> None:
        instructions = parse_disassembly(
            """
   0: 03e00008  jr $ra
   4: 00000000  nop
"""
        )
        self.assertEqual(trim_function_padding(instructions), instructions)

    def test_does_not_trim_nonzero_content_after_return(self) -> None:
        instructions = parse_disassembly(
            """
   0: 03e00008  jr $ra
   4: 00000000  nop
   8: 24020001  li $v0,1
"""
        )
        self.assertEqual(trim_function_padding(instructions), instructions)

    def test_comparison_layers(self) -> None:
        target = parse_disassembly(TARGET)
        candidate = parse_disassembly(CANDIDATE)
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        self.assertEqual(result.word_mismatches, 4)
        self.assertEqual(result.raw_word_mismatches, 4)
        self.assertEqual(result.opcode_mismatches, 0)
        self.assertEqual(result.normalized_distance, 1)
        self.assertEqual(result.fp_register_mismatches, 1)
        self.assertEqual(result.fp_mismatch_ranges, [(2, 2)])
        self.assertEqual(result.target_frame_size, -32)
        self.assertEqual(result.candidate_frame_size, -48)
        self.assertFalse(result.exact)

    def test_relocation_fields_are_masked_precisely(self) -> None:
        target = parse_disassembly(RELOC_TARGET)
        candidate = parse_disassembly(RELOC_CANDIDATE)
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        self.assertEqual(result.raw_word_mismatches, 2)
        self.assertEqual(result.word_mismatches, 0)
        self.assertTrue(result.exact)
        self.assertEqual(
            [item.kind for item in target[0].relocations],
            ["R_MIPS_26"],
        )

    def test_unknown_relocation_cannot_claim_exact(self) -> None:
        target = parse_disassembly(
            """
   0: 00000000  nop
                        0: R_MIPS_FUTURE symbol
"""
        )
        candidate = parse_disassembly(
            """
   0: 00000000  nop
                        0: R_MIPS_FUTURE symbol
"""
        )
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        self.assertEqual(result.word_mismatches, 0)
        self.assertEqual(result.unknown_relocations, ["R_MIPS_FUTURE"])
        self.assertFalse(result.exact)

    def test_missing_relocation_cannot_claim_exact(self) -> None:
        target = parse_disassembly(
            "  0: 0c001234 jal 48d0 <callee>\n  0: R_MIPS_26 callee\n"
        )
        candidate = parse_disassembly("  0: 0c005678 jal 159e0 <callee>\n")
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        self.assertEqual(result.word_mismatches, 0)
        self.assertEqual(result.relocation_metadata_mismatches, 1)
        self.assertFalse(result.exact)

    def test_parse_relocations(self) -> None:
        relocations = parse_relocations(RELOC_TARGET)
        self.assertEqual(relocations[0][0].symbol, "callee")
        self.assertEqual(relocations[4][0].kind, "R_MIPS_HI16")

    def test_ranges(self) -> None:
        self.assertEqual(mismatch_ranges([]), [])
        self.assertEqual(
            mismatch_ranges([1, 2, 3, 7, 9, 10]),
            [(1, 3), (7, 7), (9, 10)],
        )


if __name__ == "__main__":
    unittest.main()
