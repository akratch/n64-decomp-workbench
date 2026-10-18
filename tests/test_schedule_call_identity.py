"""Synthetic calls distinguish target substitution from actual displacement."""

from __future__ import annotations

import unittest
from dataclasses import replace

from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Instruction, Relocation
from decomp_workbench.view import build_view


def call(address: int, symbol: str | None, *, addend: int = 0) -> Instruction:
    return Instruction(
        address,
        f"{0x0C000000 | addend:08x}",
        f"jal 0 <{symbol or 'unknown'}>",
        (Relocation(address, "R_MIPS_26", symbol),),
    )


def nop(address: int) -> Instruction:
    return Instruction(address, "00000000", "nop")


class ScheduleCallIdentityTests(unittest.TestCase):
    def test_unrelated_call_is_structure_not_schedule(self) -> None:
        target = [call(0, "alpha"), nop(4)]
        candidate = [call(0, "beta"), nop(4)]
        before_target = list(target)
        before_candidate = list(candidate)
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertEqual(view.counts["schedule"], 0)
        self.assertEqual(view.counts["structural"], 1)
        self.assertNotEqual(view.playbook, "g0-schedule-probe")
        self.assertEqual(target, before_target)
        self.assertEqual(candidate, before_candidate)
        comparison = compare_instructions(
            target, candidate, target_name="t", candidate_name="c", symbol=None
        )
        self.assertEqual(comparison.raw_word_mismatches, 0)
        self.assertEqual(comparison.word_mismatches, 0)
        self.assertEqual(comparison.relocation_metadata_mismatches, 0)
        self.assertEqual(comparison.relocation_target_mismatches, 1)
        # Existing object comparator policy reports symbol identities separately.
        # This diagnostic fix must not silently redefine its exactness contract.
        self.assertTrue(comparison.exact)

    def test_equal_call_multiset_does_not_prove_schedule(self) -> None:
        target = [call(0, "alpha"), nop(4), call(8, "beta"), nop(12)]
        candidate = [call(0, "beta"), nop(4), call(8, "alpha"), nop(12)]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertEqual(view.counts["schedule"], 0)
        self.assertEqual(view.counts["structural"], 2)

    def test_same_identity_call_can_still_move(self) -> None:
        load = Instruction(0, "8C820000", "lw v0,0(a0)")
        target = [load, call(4, "alpha"), nop(8)]
        candidate = [call(0, "alpha"), replace(load, address=4), nop(8)]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertGreater(view.counts["schedule"], 0)
        self.assertEqual(view.counts["structural"], 0)

    def test_same_site_addend_bits_keep_relocation_only_classification(self) -> None:
        # No dump provenance distinguishes linked bits from a REL addend.
        target = [call(0, "alpha"), nop(4)]
        candidate = [call(0, "alpha", addend=1), nop(4)]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertEqual(view.counts["schedule"], 0)
        self.assertEqual(view.counts["structural"], 0)
        self.assertEqual(view.counts["relocation"], 1)

    def test_displaced_call_with_different_addend_cannot_prove_a_move(self) -> None:
        load = Instruction(0, "8C820000", "lw v0,0(a0)")
        target = [load, call(4, "alpha"), nop(8)]
        candidate = [call(0, "alpha", addend=1), replace(load, address=4), nop(8)]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertGreater(view.counts["structural"], 0)

    def test_missing_call_identity_cannot_authenticate_a_move(self) -> None:
        load = Instruction(0, "8C820000", "lw v0,0(a0)")
        target = [load, call(4, None), nop(8)]
        candidate = [call(0, None), replace(load, address=4), nop(8)]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertGreater(view.counts["structural"], 0)
        self.assertTrue(any(row.reported for row in view.rows))

    def test_tuple_count_mismatch_remains_nonexact(self) -> None:
        first = call(0, "alpha")
        second = replace(first, relocations=first.relocations * 2)
        view = build_view([first], [second], target_name="t", candidate_name="c")
        self.assertEqual(view.counts["schedule"], 0)
        self.assertEqual(view.counts["structural"], 1)
        comparison = compare_instructions(
            [first], [second], target_name="t", candidate_name="c", symbol=None
        )
        self.assertFalse(comparison.exact)
        self.assertEqual(comparison.relocation_metadata_mismatches, 1)

    def test_identical_calls_stay_exact(self) -> None:
        target = [call(0, "alpha"), nop(4)]
        view = build_view(target, target, target_name="t", candidate_name="c")
        self.assertEqual(view.verdict, "exact")
        self.assertEqual(view.counts["match"], 2)

    def test_tail_call_and_linking_branch_substitutions_stay_visible(self) -> None:
        for opcode, word, kind in [
            ("j", "08000000", "R_MIPS_26"),
            ("bal", "0411ffff", "R_MIPS_PC16"),
        ]:
            with self.subTest(opcode=opcode):
                target = [
                    Instruction(
                        0, word, f"{opcode} 0 <alpha>", (Relocation(0, kind, "alpha"),)
                    )
                ]
                candidate = [
                    Instruction(
                        0, word, f"{opcode} 0 <beta>", (Relocation(0, kind, "beta"),)
                    )
                ]
                view = build_view(
                    target, candidate, target_name="t", candidate_name="c"
                )
                self.assertEqual(view.counts["schedule"], 0)
                self.assertEqual(view.counts["structural"], 1)

    def test_unrelated_arithmetic_reordering_stays_schedule(self) -> None:
        left = Instruction(0, "24020001", "li v0,1")
        right = Instruction(4, "24030002", "li v1,2")
        target = [left, right, call(8, "alpha"), nop(12)]
        candidate = [
            replace(right, address=0),
            replace(left, address=4),
            call(8, "alpha"),
            nop(12),
        ]
        view = build_view(target, candidate, target_name="t", candidate_name="c")
        self.assertEqual(view.counts["structural"], 0)
        self.assertEqual(view.counts["schedule"], 2)


if __name__ == "__main__":
    unittest.main()
