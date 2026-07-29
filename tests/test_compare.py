"""Tests for object parsing and layered comparison metrics."""

from __future__ import annotations

import unittest

from mips_asm import assemble

from decomp_workbench.compare import (
    ALIGNED_CLASS_KEYS,
    aligned_residual,
    commutative_swap,
    compare_instructions,
    mismatch_ranges,
    normalize_instruction,
)
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import (
    parse_disassembly,
    parse_relocations,
    trim_function_padding,
)
from decomp_workbench.view import RESIDUAL_CLASSES, build_view

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


# A register-range residual that also carries one literal difference. The
# comparator once counted the `li` site in `raw` and printed only the register
# groups, which cost a mis-scoped experiment.
MIXED_TARGET = """
00000000 <demo>:
   0: 24020021  li $v0,33
   4: 012a4021  addu $t0,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

MIXED_CANDIDATE = """
00000000 <demo>:
   0: 24020031  li $v0,49
   4: 012a5821  addu $t3,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
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

    def test_register_comparison_accepts_objdump_dialects(self) -> None:
        target = parse_disassembly(
            """
   0: 012a4021  addu $t0,$t1,$t2
   4: 460c0000  add.s $f0,$f0,$f12
"""
        )
        candidate = parse_disassembly(
            """
   0: 012a4021  addu t0,t1,t2
   4: 460c0000  add.s f0,f0,f12
"""
        )
        result = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        self.assertEqual(result.register_mismatches, 0)
        self.assertEqual(result.fp_register_mismatches, 0)
        self.assertEqual(result.candidate_fp_register_uses, {"$f0": 2, "$f12": 1})

    def test_register_comparison_detects_prefixless_gp_difference(self) -> None:
        target = parse_disassembly("   0: 012a4021  addu t0,t1,t2\n")
        candidate = parse_disassembly("   0: 016c5021  addu t2,t3,t4\n")
        result = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        self.assertEqual(result.register_mismatches, 1)
        self.assertEqual(
            result.register_diff[0]["target_registers"],
            ["t0", "t1", "t2"],
        )

    def test_symbolized_hex_address_is_not_a_register(self) -> None:
        target = parse_disassembly("   0: 10000027  bnez at,a0 <demo+0xa0>\n")
        candidate = parse_disassembly("   0: 10000027  bnez at,85bc <demo+0xa0>\n")
        result = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol=None,
        )
        self.assertEqual(result.register_mismatches, 0)
        self.assertEqual(result.fp_register_mismatches, 0)

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
        self.assertEqual(result.verdict, "instruction-exact")
        self.assertEqual(result.raw_difference_breakdown, {"relocation_controlled": 2})
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
        self.assertEqual(result.verdict, "unknown-relocation")

    def test_cross_rom_structural_match_is_not_object_exact(self) -> None:
        target = parse_disassembly(
            """
   0: 3c080123  lui t0,0x123
   4: 25081234  addiu t0,t0,4660
   8: 8d090020  lw t1,32(t0)
"""
        )
        candidate = parse_disassembly(
            """
   0: 3c084567  lui $t0,0x4567
   4: 250889ab  addiu $t0,$t0,-30293
   8: 8d090060  lw $t1,96($t0)
"""
        )
        result = compare_instructions(
            target,
            candidate,
            target_name="jp.objdump",
            candidate_name="us.objdump",
            symbol="demo",
        )
        self.assertFalse(result.exact)
        self.assertTrue(result.structural_exact)
        self.assertEqual(result.verdict, "operand-mismatch")
        self.assertEqual(result.normalized_distance, 0)
        self.assertEqual(result.register_mismatches, 0)

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
        self.assertEqual(result.verdict, "relocation-layout-mismatch")

    def test_raw_identity_is_scoped_to_instruction_words(self) -> None:
        instructions = parse_disassembly(TARGET)
        result = compare_instructions(
            instructions,
            instructions,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        self.assertTrue(result.exact)
        self.assertEqual(result.verdict, "instruction-words-identical")

    def test_register_verdict_still_reports_the_literal_site(self) -> None:
        result = compare_instructions(
            parse_disassembly(MIXED_TARGET, symbol="demo"),
            parse_disassembly(MIXED_CANDIDATE, symbol="demo"),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        self.assertEqual(result.verdict, "allocation-mismatch")
        self.assertEqual(result.register_mismatch_ranges, [(1, 1)])
        self.assertEqual(result.raw_word_mismatches, 2)
        self.assertEqual(result.diff_site_classes, {"constant": 1, "register": 1})
        literal = [site for site in result.diff_sites if site["class"] == "constant"]
        self.assertEqual(len(literal), 1)
        self.assertEqual(literal[0]["index"], 0)
        self.assertEqual(literal[0]["target"], "li $v0,33")
        self.assertEqual(literal[0]["candidate"], "li $v0,49")

    def test_every_differing_word_becomes_a_diff_site(self) -> None:
        pairs = (
            (TARGET, CANDIDATE),
            (MIXED_TARGET, MIXED_CANDIDATE),
            (RELOC_TARGET, RELOC_CANDIDATE),
            (TARGET, MIXED_CANDIDATE),
        )
        for target_text, candidate_text in pairs:
            with self.subTest(target=target_text.splitlines()[1]):
                result = compare_instructions(
                    parse_disassembly(target_text),
                    parse_disassembly(candidate_text),
                    target_name="target.o",
                    candidate_name="candidate.o",
                    symbol=None,
                )
                differing = [
                    site
                    for site in result.diff_sites
                    if site["target_word"] != site["candidate_word"]
                ]
                self.assertEqual(len(differing), result.raw_word_mismatches)
                self.assertEqual(
                    sum(result.diff_site_classes.values()),
                    len(result.diff_sites),
                )

    def test_length_difference_is_a_diff_site(self) -> None:
        result = compare_instructions(
            parse_disassembly("   0: 03e00008  jr $ra\n   4: 00000000  nop\n"),
            parse_disassembly(
                "   0: 03e00008  jr $ra\n"
                "   4: 00000000  nop\n"
                "   8: 24020001  li $v0,1\n"
            ),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        self.assertEqual(result.diff_site_classes, {"instruction-count": 1})
        self.assertEqual(result.diff_sites[0]["target"], "-")
        self.assertEqual(result.diff_sites[0]["candidate"], "li $v0,1")

    def test_relocation_layout_difference_is_a_diff_site(self) -> None:
        result = compare_instructions(
            parse_disassembly(
                "  0: 0c001234 jal 48d0 <callee>\n  0: R_MIPS_26 callee\n"
            ),
            parse_disassembly("  0: 0c005678 jal 159e0 <callee>\n"),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        self.assertEqual(result.diff_site_classes, {"relocation-layout": 1})

    def compare_text(self, target: str, candidate: str) -> Comparison:
        return compare_instructions(
            parse_disassembly(target),
            parse_disassembly(candidate),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )

    def test_swapped_commutative_operands_are_not_an_allocation_verdict(self) -> None:
        result = self.compare_text(
            "   0: 00851025  or $v0,$a0,$a1\n",
            "   0: 00a41025  or $v0,$a1,$a0\n",
        )
        self.assertEqual(result.verdict, "commutative-order")
        self.assertEqual(result.diff_site_classes, {"commutative-order": 1})
        self.assertEqual(result.register_mismatches, 1)
        guidance = " ".join(result.guidance)
        self.assertIn("|=", guidance)
        self.assertNotIn("trace", guidance.replace("Do not trace", ""))

    def test_same_operand_order_is_not_a_commutative_verdict(self) -> None:
        result = self.compare_text(
            "   0: 00851025  or $v0,$a0,$a1\n",
            "   0: 00851825  or $v1,$a0,$a1\n",
        )
        self.assertEqual(result.verdict, "allocation-mismatch")

    def test_reordered_identical_opcodes_are_a_schedule_verdict(self) -> None:
        result = self.compare_text(
            "   0: 8c880000  lw $t0,0($a0)\n   4: 25290001  addiu $t1,$t1,1\n",
            "   0: 25290001  addiu $t1,$t1,1\n   4: 8c880000  lw $t0,0($a0)\n",
        )
        self.assertEqual(result.verdict, "schedule-mismatch")
        self.assertEqual(result.opcode_mismatches, 2)
        self.assertEqual(result.instruction_delta, 0)
        guidance = " ".join(result.guidance)
        self.assertIn("-g0", guidance)
        self.assertIn("replay-as1", guidance)

    def test_reordering_with_a_register_difference_is_not_a_schedule_verdict(
        self,
    ) -> None:
        # Same opcode multiset and a real reordering, but one instruction also
        # changes a register. Calling this "not allocation" would send the next
        # experiment to the wrong layer.
        result = self.compare_text(
            "   0: 8c880000  lw $t0,0($a0)\n"
            "   4: 25290001  addiu $t1,$t1,1\n"
            "   8: 016c5021  addu $t2,$t3,$t4\n",
            "   0: 25290001  addiu $t1,$t1,1\n"
            "   4: 8c880000  lw $t0,0($a0)\n"
            "   8: 016c6821  addu $t5,$t3,$t4\n",
        )
        self.assertEqual(
            result.diff_site_classes,
            {"opcode": 2, "register": 1},
        )
        self.assertNotEqual(result.verdict, "schedule-mismatch")
        self.assertEqual(result.verdict, "structure-mismatch")
        self.assertNotIn("not allocation", " ".join(result.guidance))

    def test_changed_opcode_multiset_stays_a_structure_verdict(self) -> None:
        result = self.compare_text(
            "   0: 8c880000  lw $t0,0($a0)\n   4: 25290001  addiu $t1,$t1,1\n",
            "   0: 25290001  addiu $t1,$t1,1\n   4: 25290001  addiu $t1,$t1,1\n",
        )
        self.assertEqual(result.verdict, "structure-mismatch")

    def test_two_operand_commutative_swap_is_recognized(self) -> None:
        result = self.compare_text(
            "   0: 00850018  mult $a0,$a1\n",
            "   0: 00a40018  mult $a1,$a0\n",
        )
        self.assertEqual(result.diff_site_classes, {"commutative-order": 1})
        self.assertEqual(result.verdict, "commutative-order")

    def test_two_operand_non_commutative_opcode_is_not_a_swap(self) -> None:
        result = self.compare_text(
            "   0: 0085001a  div $a0,$a1\n",
            "   0: 00a4001a  div $a1,$a0\n",
        )
        self.assertEqual(result.diff_site_classes, {"register": 1})
        self.assertEqual(result.verdict, "allocation-mismatch")

    def test_register_verdict_names_a_constant_site_when_present(self) -> None:
        result = compare_instructions(
            parse_disassembly(MIXED_TARGET, symbol="demo"),
            parse_disassembly(MIXED_CANDIDATE, symbol="demo"),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        self.assertEqual(result.verdict, "allocation-mismatch")
        self.assertIn("constant materializations", result.guidance[0])

    def test_register_verdict_names_a_commutative_site_when_present(self) -> None:
        result = self.compare_text(
            "   0: 00851025  or $v0,$a0,$a1\n   4: 012a4021  addu $t0,$t1,$t2\n",
            "   0: 00a41025  or $v0,$a1,$a0\n   4: 012a5821  addu $t3,$t1,$t2\n",
        )
        self.assertEqual(
            result.diff_site_classes,
            {"commutative-order": 1, "register": 1},
        )
        self.assertEqual(result.verdict, "allocation-mismatch")
        self.assertIn("commutative", result.guidance[0])

    def test_register_verdict_without_mixed_sites_keeps_its_first_line(self) -> None:
        result = self.compare_text(
            "   0: 012a4021  addu $t0,$t1,$t2\n",
            "   0: 012a5821  addu $t3,$t1,$t2\n",
        )
        self.assertEqual(result.verdict, "allocation-mismatch")
        self.assertTrue(result.guidance[0].startswith("Opcode shape matches"))

    def test_literal_only_difference_is_a_constant_verdict(self) -> None:
        result = self.compare_text(
            "   0: 24020021  li $v0,33\n",
            "   0: 24020031  li $v0,49\n",
        )
        self.assertEqual(result.verdict, "constant-mismatch")
        guidance = " ".join(result.guidance)
        self.assertIn("assembly encodes the truth", guidance)
        self.assertIn("fake", guidance)

    def test_linker_controlled_words_do_not_change_the_mechanism(self) -> None:
        result = self.compare_text(
            "   0: 24020021  li $v0,33\n"
            "   4: 3c010123  lui $at,0x123\n"
            "                        4: R_MIPS_HI16 global\n",
            "   0: 24020031  li $v0,49\n"
            "   4: 3c010000  lui $at,0x0\n"
            "                        4: R_MIPS_HI16 global\n",
        )
        self.assertEqual(
            result.diff_site_classes,
            {"constant": 1, "relocation-controlled": 1},
        )
        self.assertEqual(result.verdict, "constant-mismatch")

    def test_frame_adjustment_is_not_a_constant_verdict(self) -> None:
        result = self.compare_text(
            "   0: 27bdffe0  addiu $sp,$sp,-32\n",
            "   0: 27bdffd0  addiu $sp,$sp,-48\n",
        )
        self.assertEqual(result.diff_site_classes, {"operand": 1})
        self.assertEqual(result.verdict, "operand-mismatch")

    def test_structure_verdict_names_a_constant_site_when_present(self) -> None:
        result = self.compare_text(
            "   0: 3c081000  lui $t0,0x1000\n   4: 8c880000  lw $t0,0($a0)\n",
            "   0: 3c080010  lui $t0,0x10\n",
        )
        self.assertEqual(result.verdict, "structure-mismatch")
        self.assertIn("constant materializations", result.guidance[0])

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


#: The class name each command prints for one mechanism.  The two vocabularies
#: differ, the mechanism does not.
COMMUTATIVE_CLASS_NAMES: dict[str, str] = {
    "commutative": "commutative-order",
    "register": "register",
}

#: One differing site per case, in the two operand shapes that used to be read
#: differently by the two commands, plus non-commutative controls.  Each entry
#: is (name, target line, candidate line, mechanism).
COMMUTATIVE_CASES: tuple[tuple[str, str, str, str], ...] = (
    (
        "three-operand or",
        "   0: 00851025  or $v0,$a0,$a1\n",
        "   0: 00a41025  or $v0,$a1,$a0\n",
        "commutative",
    ),
    (
        "two-operand mult",
        "   0: 00850018  mult $a0,$a1\n",
        "   0: 00a40018  mult $a1,$a0\n",
        "commutative",
    ),
    (
        "two-operand div",
        "   0: 0085001a  div $a0,$a1\n",
        "   0: 00a4001a  div $a1,$a0\n",
        "register",
    ),
    (
        "three-operand subu",
        "   0: 00851023  subu $v0,$a0,$a1\n",
        "   0: 00a41023  subu $v0,$a1,$a0\n",
        "register",
    ),
    (
        "three-operand or with a moved destination",
        "   0: 00851025  or $v0,$a0,$a1\n",
        "   0: 00a41825  or $v1,$a1,$a0\n",
        "register",
    ),
)


class CommutativeSwapTests(unittest.TestCase):
    """One table, one predicate, and two commands that cannot disagree."""

    def test_operand_shapes(self) -> None:
        self.assertTrue(commutative_swap("or", ["t0", "t1", "t2"], ["t0", "t2", "t1"]))
        self.assertTrue(commutative_swap("mult", ["t1", "t2"], ["t2", "t1"]))
        self.assertFalse(
            commutative_swap("subu", ["t0", "t1", "t2"], ["t0", "t2", "t1"])
        )
        self.assertFalse(commutative_swap("div", ["t1", "t2"], ["t2", "t1"]))
        self.assertFalse(commutative_swap("or", ["t0", "t1", "t2"], ["t0", "t1", "t2"]))
        self.assertFalse(commutative_swap("or", ["t0", "t1", "t2"], ["t3", "t2", "t1"]))
        self.assertFalse(commutative_swap("or", ["t0", "t1"], ["t0", "t1", "t2"]))

    def test_both_call_sites_agree(self) -> None:
        """``compare`` and ``view`` classify one site through one predicate."""

        for name, target, candidate, mechanism in COMMUTATIVE_CASES:
            with self.subTest(case=name):
                comparison = compare_instructions(
                    parse_disassembly(target),
                    parse_disassembly(candidate),
                    target_name="target.o",
                    candidate_name="candidate.o",
                    symbol=None,
                )
                self.assertEqual(
                    comparison.diff_site_classes,
                    {COMMUTATIVE_CLASS_NAMES[mechanism]: 1},
                )
                view = build_view(
                    parse_disassembly(target),
                    parse_disassembly(candidate),
                    target_name="target.o",
                    candidate_name="candidate.o",
                )
                self.assertEqual(view.counts[mechanism], 1)
                other = "register" if mechanism == "commutative" else "commutative"
                self.assertEqual(view.counts[other], 0)


# One target and two candidates that positional counting ranks backwards.
# `SHIFTED` inserts a single instruction, which moves every later position and
# reads as a long cascade; `RECOLORED` really does allocate three registers
# differently. The aligned truth is 1 versus 3, and positional words say the
# opposite.
ALIGN_TARGET = [
    "addiu sp,sp,-32",
    "sw ra,28(sp)",
    "lw t0,0(a0)",
    "lw t1,4(a0)",
    "addu t2,t0,t1",
    "sw t2,8(a0)",
    "lw ra,28(sp)",
    "jr ra",
    "addiu sp,sp,32",
]
SHIFTED = [
    "addiu sp,sp,-32",
    "sw ra,28(sp)",
    "nop",
    "lw t0,0(a0)",
    "lw t1,4(a0)",
    "addu t2,t0,t1",
    "sw t2,8(a0)",
    "lw ra,28(sp)",
    "jr ra",
    "addiu sp,sp,32",
]
RECOLORED = [
    "addiu sp,sp,-32",
    "sw ra,28(sp)",
    "lw t4,0(a0)",
    "lw t5,4(a0)",
    "addu t2,t4,t5",
    "sw t2,8(a0)",
    "lw ra,28(sp)",
    "jr ra",
    "addiu sp,sp,32",
]


def compare_lines(target: list[str], candidate: list[str]) -> Comparison:
    """Compare two assembled instruction lists as one function."""

    return compare_instructions(
        parse_disassembly(assemble(target, symbol="demo"), symbol="demo"),
        parse_disassembly(assemble(candidate, symbol="demo"), symbol="demo"),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol="demo",
    )


class AlignedResidualTests(unittest.TestCase):
    """Positional word counts misranked candidates in six recorded campaigns.

    The comparison therefore carries LCS-aligned counts beside the positional
    ones, and they come from the `view` analysis rather than from a second
    aligner living here: two implementations of one idea would put different
    numbers under the same name in two commands.
    """

    def test_the_counts_are_the_view_counts(self) -> None:
        target = parse_disassembly(assemble(ALIGN_TARGET, symbol="demo"), symbol="demo")
        candidate = parse_disassembly(assemble(SHIFTED, symbol="demo"), symbol="demo")
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        view = build_view(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        for name in RESIDUAL_CLASSES:
            with self.subTest(classification=name):
                self.assertEqual(
                    getattr(comparison, f"aligned_{name}"), view.counts[name]
                )
        self.assertEqual(
            comparison.aligned_total,
            sum(getattr(comparison, key) for key in ALIGNED_CLASS_KEYS),
        )

    def test_an_insertion_is_one_aligned_difference_not_a_cascade(self) -> None:
        comparison = compare_lines(ALIGN_TARGET, SHIFTED)
        self.assertEqual(comparison.aligned_structural, 1)
        self.assertEqual(comparison.aligned_total, 1)
        # The positional count is the cascade the alignment exists to remove.
        self.assertGreater(comparison.word_mismatches, comparison.aligned_total)

    def test_ranking_follows_the_aligned_residual(self) -> None:
        shifted = compare_lines(ALIGN_TARGET, SHIFTED)
        recolored = compare_lines(ALIGN_TARGET, RECOLORED)
        self.assertEqual(recolored.aligned_register, 3)
        # Positional counting ranks these backwards, which is the recorded
        # defect: the one-insertion candidate is the closer base.
        self.assertGreater(shifted.word_mismatches, recolored.word_mismatches)
        self.assertLess(shifted.aligned_total, recolored.aligned_total)
        shifted.candidate = "shifted.o"
        recolored.candidate = "recolored.o"
        self.assertEqual(
            [
                item.candidate
                for item in sorted([recolored, shifted], key=lambda item: item.sort_key)
            ],
            ["shifted.o", "recolored.o"],
        )

    def test_positional_words_break_an_aligned_tie(self) -> None:
        """Same aligned residual, so the positional count still decides."""

        far = compare_lines(ALIGN_TARGET, RECOLORED)
        far.candidate = "far.o"
        near = compare_lines(ALIGN_TARGET, RECOLORED)
        near.candidate = "near.o"
        near.word_mismatches -= 1
        self.assertEqual(far.aligned_total, near.aligned_total)
        self.assertEqual(
            [
                item.candidate
                for item in sorted([far, near], key=lambda item: item.sort_key)
            ],
            ["near.o", "far.o"],
        )

    def test_relocation_and_match_rows_are_not_residual(self) -> None:
        """The residual counts only what a source change controls."""

        self.assertEqual(
            set(ALIGNED_CLASS_KEYS),
            {f"aligned_{name}" for name in RESIDUAL_CLASSES},
        )
        for excluded in ("match", "displacement", "relocation"):
            with self.subTest(classification=excluded):
                self.assertNotIn(f"aligned_{excluded}", ALIGNED_CLASS_KEYS)

    def test_jump_table_section_addends_do_not_inflate_aligned_total(self) -> None:
        target = parse_disassembly(
            "   0: 3c010000  lui $at,0x0\n"
            "                        0: R_MIPS_HI16 jtbl_8009AE9C\n"
            "   4: 00380821  addu $at,$at,$t8\n"
            "   8: 8c380000  lw $t8,0($at)\n"
            "                        8: R_MIPS_LO16 jtbl_8009AE9C\n"
        )
        candidate = parse_disassembly(
            "   0: 3c010000  lui $at,0x0\n"
            "                        0: R_MIPS_HI16 .rodata\n"
            "   4: 00380821  addu $at,$at,$t8\n"
            "   8: 8c3800ac  lw $t8,172($at)\n"
            "                        8: R_MIPS_LO16 .rodata\n"
        )
        result = compare_instructions(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol=None,
        )
        self.assertTrue(result.exact)
        self.assertEqual(result.aligned_total, 0)
        self.assertEqual(result.aligned_schedule, 0)
        self.assertEqual(result.aligned_constant, 0)

    def test_an_empty_side_is_never_reported_as_agreement(self) -> None:
        target = parse_disassembly(assemble(ALIGN_TARGET, symbol="demo"), symbol="demo")
        counts = aligned_residual(target, [])
        self.assertEqual(counts["aligned_structural"], len(target))
        self.assertEqual(sum(counts.values()), len(target))
        self.assertEqual(aligned_residual([], []), dict.fromkeys(ALIGNED_CLASS_KEYS, 0))


if __name__ == "__main__":
    unittest.main()
