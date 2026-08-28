"""Tests for the aligned mechanism view.

Every fixture here reproduces a residual class that cost real campaign time:
a shifted insertion that positional diffing multiplies into phantom hunks, a
commutative operand swap misfiled as allocation, a register cascade that is one
upstream decision, a constant difference that an earlier verdict hid, and a
byte-identical prefix whose state had already diverged.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.force_spec import force_specification
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import (
    REGISTER_CLASS_PROFILES,
    AlignedRow,
    MechanismView,
    Web,
    build_view,
    classify_pair,
    colorable_registers,
    destination_register,
    schema_keys,
    uncolorable_targets,
)
from decomp_workbench.view_cli import Painter, render_view, resolve_color

SYMBOL = "demo"


def view_of(
    target: list[str],
    candidate: list[str],
    *,
    symbol: str = SYMBOL,
    relocations: dict[int, str] | None = None,
    candidate_relocations: dict[int, str] | None = None,
) -> MechanismView:
    """Assemble two instruction lists and align them."""

    target_text = assemble(target, symbol=symbol, relocations=relocations)
    candidate_text = assemble(
        candidate,
        symbol=symbol,
        relocations=(
            relocations if candidate_relocations is None else candidate_relocations
        ),
    )
    return build_view(
        parse_disassembly(target_text, symbol=symbol),
        parse_disassembly(candidate_text, symbol=symbol),
        target_name="target.objdump",
        candidate_name="candidate.objdump",
        symbol=symbol,
    )


# A short prologue/epilogue keeps the fixtures shaped like real functions and
# gives ``trim_function_padding`` a return to find.
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]


def body(*lines: str) -> list[str]:
    return [*PROLOGUE, *lines, *EPILOGUE]


def emitted_keys(view: MechanismView) -> set[str]:
    """Return every key this view actually prints, from both renderings.

    Nested JSON objects count: ``hunk`` and ``web`` are keys a consumer reads,
    and a key nobody explains is exactly the failure the registry exists to
    prevent.  ``slots`` appears only on the human lane rendering, which is why
    the screen is scanned as well as the payload.
    """

    keys: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            keys.update(str(key) for key in node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(view.as_dict(report_regs=True))
    for line in render_view(view, report_regs=True):
        if line.startswith("next: ") or line.startswith("      "):
            continue
        keys.update(re.findall(r"\b([a-z_]+)=", line))
    return keys


class AssemblerFixtureTests(unittest.TestCase):
    """The fixture generator itself has to be trustworthy."""

    def test_words_track_the_printed_operands(self) -> None:
        first = assemble(["addu t6,t0,t1"])
        second = assemble(["addu t7,t0,t1"])
        self.assertIn("addu $t6,$t0,$t1", first)
        self.assertNotEqual(
            parse_disassembly(first)[0].word, parse_disassembly(second)[0].word
        )

    def test_identical_assembly_encodes_identically(self) -> None:
        lines = body("lw t6,0(s0)", "addu t7,t6,t6")
        self.assertEqual(assemble(lines), assemble(lines))

    def test_branch_labels_resolve_to_instruction_indexes(self) -> None:
        text = assemble(["bne a0,zero,@3", "nop", "nop", "jr ra", "nop"])
        self.assertIn("bne $a0,$zero,c <demo+0xc>", text)


class AlignmentTests(unittest.TestCase):
    def test_shifted_insertion_is_one_hunk_not_a_phantom_cascade(self) -> None:
        """Positional diffing turns one insertion into a cascade; LCS does not."""

        target = body(
            "bne a0,zero,@10",
            "lw t6,0(s0)",
            "addu t7,t6,t6",
            "sw t7,4(s0)",
            "lw t8,8(s0)",
            "addu t9,t8,t7",
        )
        candidate = body(
            "bne a0,zero,@11",
            "nop",
            "lw t6,0(s0)",
            "addu t7,t6,t6",
            "sw t7,4(s0)",
            "lw t8,8(s0)",
            "addu t9,t8,t7",
        )
        view = view_of(target, candidate)
        self.assertEqual(view.counts["structural"], 1)
        self.assertEqual(len(view.hunks), 1)
        self.assertEqual(view.verdict, "structure")
        self.assertEqual(view.counts["displacement"], 1)
        self.assertEqual(view.counts["match"], len(target) - 1)

        positional = compare_instructions(
            parse_disassembly(assemble(target, symbol=SYMBOL), symbol=SYMBOL),
            parse_disassembly(assemble(candidate, symbol=SYMBOL), symbol=SYMBOL),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertGreater(positional.word_mismatches, 5 * view.counts["structural"])

    def test_branch_targets_are_alignment_relative(self) -> None:
        """A branch across an insertion still matches once the streams align."""

        view = view_of(
            body("bne a0,zero,@10", "nop", "nop", "nop", "nop", "nop"),
            body("bne a0,zero,@11", "nop", "nop", "nop", "nop", "nop", "nop"),
        )
        branch = next(row for row in view.rows if (row.target or "").startswith("bne"))
        self.assertEqual(branch.classification, "displacement")
        self.assertNotEqual(branch.target, branch.candidate)
        # The encoded offset moved, so this is not byte-identical, but it is
        # not a source difference either: it must not open a hunk.
        self.assertFalse(branch.matched)
        self.assertFalse(branch.reported)
        self.assertTrue(all(hunk.start != branch.index for hunk in view.hunks))

    def test_relocated_call_is_never_read_as_a_local_branch(self) -> None:
        view = view_of(
            body("jal helper", "nop"),
            body("jal helper", "nop"),
            relocations={4: "R_MIPS_26 helper"},
        )
        self.assertEqual(view.verdict, "exact")


class DuplicatedRunTests(unittest.TestCase):
    """Opcode-level LCS cannot resolve a run of repeated opcodes on its own."""

    def test_insertion_into_a_duplicated_opcode_run_is_one_hunk(self) -> None:
        target = body(*[f"addu t{index},t0,t1" for index in (2, 3, 4, 5)])
        candidate = body(
            "addu t2,t0,t1",
            "addu t3,t0,t1",
            "addu t9,t0,t1",
            "addu t4,t0,t1",
            "addu t5,t0,t1",
        )
        view = view_of(target, candidate)
        self.assertEqual(view.verdict, "structure")
        self.assertEqual(view.counts["structural"], 1)
        self.assertEqual(view.counts["register"], 0)
        self.assertEqual(len(view.hunks), 1)
        self.assertEqual(view.counts["match"], len(target))

    def test_the_better_of_the_two_anchorings_wins(self) -> None:
        """Identical text is an unambiguous anchor; the score picks the winner."""

        target = body("addu t2,t0,t1", "addu t2,t0,t1", "addu t2,t0,t1")
        candidate = body(
            "addu t2,t0,t1", "addu t2,t0,t1", "addu t2,t0,t1", "addu t2,t0,t1"
        )
        view = view_of(target, candidate)
        self.assertEqual(view.counts["match"], len(target))
        self.assertEqual(view.counts["structural"], 1)


class PhaseShiftEvidenceTests(unittest.TestCase):
    """`phase-shift` sends the reader upstream; it has to be paid for.

    A constant cyclic offset is findable over almost any small register set --
    every swap of two registers is a rotation of a two-element cycle -- so the
    claim requires a real cycle, real length, and no unexplained lane.
    """

    def test_one_substitution_is_not_a_phase(self) -> None:
        view = view_of(body("lw s1,0(s0)"), body("lw s2,0(s0)"))
        self.assertNotEqual(view.verdict, "phase-shift")
        self.assertEqual(view.verdict, "register-permutation")

    def test_two_register_swap_is_a_permutation_not_a_phase(self) -> None:
        view = view_of(
            body("lw s1,0(s0)", "lw s2,4(s0)", "sw s1,8(s0)", "sw s2,12(s0)"),
            body("lw s2,0(s0)", "lw s1,4(s0)", "sw s2,8(s0)", "sw s1,12(s0)"),
        )
        self.assertEqual(view.verdict, "register-permutation")
        pool = next(lane for lane in view.lanes if lane.classification == "pool")
        self.assertIsNone(pool.rotation)

    def test_inconsistent_substitutions_are_not_a_phase(self) -> None:
        view = view_of(
            body(
                "lw s1,0(s0)",
                "lw s3,4(s0)",
                "lw s4,8(s0)",
                "addu s1,s1,s3",
                "sw s1,12(s0)",
            ),
            body(
                "lw s2,0(s0)",
                "lw s1,4(s0)",
                "lw s2,8(s0)",
                "addu s2,s2,s1",
                "sw s2,12(s0)",
            ),
        )
        self.assertNotEqual(view.verdict, "phase-shift")
        self.assertEqual(view.verdict, "allocation")

    def test_a_reordered_stream_is_not_a_phase(self) -> None:
        view = view_of(
            body("lw t6,0(s0)", "lw t7,4(s0)", "lw t8,8(s0)"),
            body("lw t8,8(s0)", "lw t7,4(s0)", "lw t6,0(s0)"),
        )
        self.assertNotEqual(view.verdict, "phase-shift")
        self.assertEqual(view.verdict, "schedule")

    def test_a_diverging_lane_without_a_rotation_blocks_the_claim(self) -> None:
        """One class turning while another diverges freely is two mechanisms."""

        view = view_of(
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t6,t8,t9",
                "andi t7,t6,0xff",
                "sll t8,t7,2",
                "lw s1,16(s0)",
                "sw s1,20(s0)",
                "lw s1,24(s0)",
            ),
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t7,t8,t9",
                "andi t8,t7,0xff",
                "sll t9,t8,2",
                "lw s3,16(s0)",
                "sw s3,20(s0)",
                "lw s4,24(s0)",
            ),
        )
        self.assertEqual(view.verdict, "allocation")
        temp = next(lane for lane in view.lanes if lane.classification == "temp")
        pool = next(lane for lane in view.lanes if lane.classification == "pool")
        self.assertEqual(temp.rotation, 1)
        self.assertIsNone(pool.rotation)


class DisplacementTests(unittest.TestCase):
    """A shifted branch offset is neither byte identity nor a source problem."""

    def test_displacement_is_counted_but_does_not_open_a_hunk(self) -> None:
        view = view_of(
            body("bne a0,zero,@8", "nop", "nop", "nop"),
            body("bne a0,zero,@9", "nop", "nop", "nop", "nop"),
        )
        self.assertEqual(view.counts["displacement"], 1)
        self.assertEqual(len(view.hunks), 1)
        self.assertEqual(view.hunks[0].classification, "structural")

    def test_displacement_does_not_claim_byte_identity(self) -> None:
        view = view_of(
            body("bne a0,zero,@8", "nop", "nop", "nop"),
            body("bne a0,zero,@9", "nop", "nop", "nop", "nop"),
        )
        branch = next(row for row in view.rows if (row.target or "").startswith("bne"))
        self.assertEqual(branch.classification, "displacement")
        self.assertNotIn(branch.classification, {"match"})
        payload = view.as_dict()
        self.assertEqual(payload["displacement"], 1)
        self.assertEqual(
            payload["match"] + payload["displacement"], view.aligned_rows - 1
        )

    def test_displacement_is_visible_in_the_rendered_screen(self) -> None:
        view = view_of(
            body("bne a0,zero,@8", "nop", "nop", "nop"),
            body("bne a0,zero,@9", "nop", "nop", "nop", "nop"),
        )
        screen = "\n".join(render_view(view, context=6))
        self.assertIn("displacement", screen)


class SymbolTableAsymmetryTests(unittest.TestCase):
    """Whether objdump printed a destination symbolically is not evidence.

    A decomp target is disassembled from a stripped, positional object and a
    candidate from a symbolized one, so the same word renders as `jal 0x0`
    against `jal 0 <fn>` and `b 0x485c` against `b 485c <fn+0x485c>`. On one
    recorded campaign that asymmetry produced 692 phantom `relocation` rows out
    of 780 and buried the real relocation differences under them.
    """

    STRIPPED = (
        "00000000 <.text>:\n"
        "   0: 27bdffe0  addiu $sp,$sp,-32\n"
        "   4: afbf001c  sw $ra,28($sp)\n"
        "   8: 0c000000  jal 0x0\n"
        "                        8: R_MIPS_26 helper\n"
        "   c: 00000000  nop\n"
        "  10: 10000002  b 0x1c\n"
        "  14: 00000000  nop\n"
        "  18: 00000000  nop\n"
        "  1c: 8fbf001c  lw $ra,28($sp)\n"
        "  20: 03e00008  jr $ra\n"
        "  24: 27bd0020  addiu $sp,$sp,32\n"
    )
    SYMBOLIZED = (
        STRIPPED.replace("<.text>", "<demo>")
        .replace("jal 0x0", "jal 0 <demo>")
        .replace("b 0x1c", "b 1c <demo+0x1c>")
    )

    def view(self, target: str, candidate: str) -> MechanismView:
        return build_view(
            parse_disassembly(target),
            parse_disassembly(candidate),
            target_name="target.o",
            candidate_name="candidate.o",
        )

    def test_the_same_word_rendered_two_ways_is_a_match(self) -> None:
        view = self.view(self.STRIPPED, self.SYMBOLIZED)
        self.assertEqual(view.counts["relocation"], 0)
        self.assertEqual(view.counts["structural"], 0)
        self.assertEqual(view.counts["match"], view.aligned_rows)
        self.assertEqual(view.verdict, "exact")

    def test_a_real_relocation_difference_is_still_reported(self) -> None:
        other = self.SYMBOLIZED.replace("R_MIPS_26 helper", "R_MIPS_26 other_helper")
        view = self.view(self.STRIPPED, other)
        self.assertEqual(view.counts["match"], view.aligned_rows - 1)
        call = next(row for row in view.rows if (row.target or "").startswith("jal"))
        self.assertNotEqual(call.classification, "match")


class DisplacedRowTests(unittest.TestCase):
    """An instruction that slid inside a block is a schedule decision.

    LCS reports the move as a deletion and an insertion with matching rows
    between them, so the two land in different runs and neither run's own
    sides balance. The whole-function rule cannot reach it either: it needs
    the entire function's multisets to agree, and any unrelated register
    residual breaks that. The rows were therefore labelled `structural`, which
    routes the reader to "fix structure first" -- the wrong order of work, and
    a different playbook, for a residual with no structure change in it.
    """

    def test_a_moved_instruction_is_schedule_not_structure(self) -> None:
        view = view_of(
            body(
                "lw s1,0(s0)",
                "addu s1,s1,s1",
                "sw ra,20(sp)",
                "sw s1,4(s0)",
                "lw s2,8(s0)",
            ),
            body(
                "sw ra,20(sp)",
                "lw s1,0(s0)",
                "addu s1,s1,s1",
                "sw s1,4(s0)",
                "lw s3,8(s0)",
            ),
        )

        self.assertEqual(view.counts["structural"], 0)
        self.assertEqual(view.counts["schedule"], 2)
        self.assertEqual(view.playbook, "g0-schedule-probe")

    def test_a_real_insertion_is_still_structure(self) -> None:
        """The rule is a balance, not a blanket promotion: an instruction that
        exists on one side only is genuinely new structure."""

        view = view_of(
            body("lw s1,0(s0)", "sw s1,4(s0)"),
            body("lw s1,0(s0)", "addu s1,s1,s1", "sw s1,4(s0)"),
        )

        self.assertEqual(view.counts["schedule"], 0)
        self.assertTrue(view.counts["structural"])
        self.assertEqual(view.playbook, "structure-buckets")


class ColorabilityTests(unittest.TestCase):
    """Whether a color lever can reach the target's register at all.

    The decisive fact about a register residual, and the tool used not to ask
    it. uopt's phase-2 palette is `v0 v1 a0-a3 s0-s8`; `t0-t9` are ugen ring
    temps it never hands out. A residual whose target register is `t6` cannot
    be closed by any reweighting, tie-break, or forced-color probe, so the
    whole `forced-color-oracle` playbook is dead on arrival -- which one
    campaign discovered only by reading raw cost lines out of an instrumented
    compiler, after spending the campaign on levers that could not work.
    """

    def test_the_colorable_set_excludes_the_ugen_ring(self) -> None:
        colorable = colorable_registers("ido53")
        for register in ("v0", "a0", "s0", "s8", "f0", "f12", "f18"):
            self.assertIn(register, colorable)
        for register in ("t0", "t5", "t6", "t9", "f4", "f6", "f8", "f10"):
            self.assertNotIn(register, colorable)

    def test_a_ring_only_residual_is_not_routed_to_a_color_playbook(self) -> None:
        view = view_of(body("lw t6,0(s0)"), body("lw t7,0(s0)"))

        self.assertEqual(view.verdict, "register-ring-only")
        self.assertNotEqual(view.playbook, "forced-color-oracle")
        self.assertNotEqual(view.playbook, "pool-position")
        self.assertEqual(view.playbook, "temp-fifo-phase")

    def test_the_verdict_says_why_rather_than_leaving_it_to_be_derived(
        self,
    ) -> None:
        view = view_of(body("lw t6,0(s0)"), body("lw t7,0(s0)"))
        guidance = " ".join(view.guidance)

        self.assertIn("ring-only", guidance)
        self.assertIn("web-existence problem, not a color problem", guidance)
        self.assertIn("dead families", guidance)
        self.assertEqual(view.as_dict()["ring_only_targets"], ["t6"])

    def test_a_colorable_target_keeps_the_permutation_verdict(self) -> None:
        view = view_of(body("lw s1,0(s0)"), body("lw s2,0(s0)"))

        self.assertEqual(view.verdict, "register-permutation")
        self.assertEqual(view.as_dict()["ring_only_targets"], [])

    def test_a_mixed_residual_names_the_sites_no_color_can_move(self) -> None:
        """A color probe is still worth running for the colorable half, and
        cannot possibly close the rest. Both halves get said."""

        view = view_of(
            body("lw s1,0(s0)", "sw t6,4(s0)"),
            body("lw s2,0(s0)", "sw t7,4(s0)"),
        )

        self.assertEqual(sorted(view.as_dict()["ring_only_targets"]), ["t6"])
        guidance = " ".join(view.guidance)
        self.assertIn("1 of 2 substitutions want a ring-only target", guidance)

    def test_a_force_spec_refuses_a_residual_no_force_can_reach(self) -> None:
        view = view_of(body("lw t6,0(s0)"), body("lw t7,0(s0)"))

        with self.assertRaises(ValueError) as caught:
            force_specification(view)

        message = str(caught.exception)
        self.assertIn("dead on arrival", message)
        self.assertIn("guide temp-fifo-phase", message)

    def test_an_unmeasured_register_is_not_called_unreachable(self) -> None:
        """Absence of a register from the era table is not evidence that the
        coloring pass cannot reach it."""

        webs = (Web(web="w1", target="k0", candidate="k1", count=1, rows=(0,)),)
        self.assertEqual(uncolorable_targets(webs, "ido53"), ())


class ClassificationTests(unittest.TestCase):
    def test_commutative_swap_is_not_an_allocation_problem(self) -> None:
        view = view_of(
            body("lw t6,0(s0)", "lw t7,4(s0)", "or t8,t6,t7", "sw t8,8(s0)"),
            body("lw t6,0(s0)", "lw t7,4(s0)", "or t8,t7,t6", "sw t8,8(s0)"),
        )
        self.assertEqual(view.verdict, "commutative-order")
        self.assertEqual(view.counts["commutative"], 1)
        self.assertEqual(view.counts["register"], 0)
        self.assertEqual(view.playbook, "ast-shape")
        self.assertIn("`x |= y`", " ".join(view.guidance))

    def test_non_commutative_opcode_keeps_the_register_class(self) -> None:
        view = view_of(
            body("subu t8,t6,t7", "sw t8,8(s0)"),
            body("subu t8,t7,t6", "sw t8,8(s0)"),
        )
        self.assertEqual(view.counts["commutative"], 0)
        self.assertEqual(view.counts["register"], 1)

    def test_register_cascade_reports_one_bijection(self) -> None:
        view = view_of(
            body("lw s3,0(s0)", "addu s3,s3,s3", "sw s3,4(s0)", "lw s4,8(s0)"),
            body("lw s1,0(s0)", "addu s1,s1,s1", "sw s1,4(s0)", "lw s4,8(s0)"),
        )
        self.assertEqual(view.verdict, "register-permutation")
        self.assertEqual([web.target for web in view.webs], ["s3"])
        self.assertEqual(view.webs[0].count, 3)
        self.assertEqual(view.webs[0].web, "w1")

    def test_inconsistent_substitutions_are_allocation(self) -> None:
        view = view_of(
            body("lw s3,0(s0)", "sw s3,4(s0)", "lw s3,8(s0)", "sw s3,12(s0)"),
            body("lw s1,0(s0)", "sw s1,4(s0)", "lw s2,8(s0)", "sw s2,12(s0)"),
        )
        self.assertEqual(view.verdict, "allocation")
        self.assertEqual(view.playbook, "pool-position")
        guidance = " ".join(view.guidance)
        self.assertIn("NEXT FREE slot", guidance)
        self.assertIn("only if an instrumented", guidance)

    def test_temp_rotation_is_a_phase_shift(self) -> None:
        view = view_of(
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t6,t8,t9",
                "andi t7,t6,0xff",
                "sll t8,t7,2",
                "sw t8,12(s0)",
            ),
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t7,t8,t9",
                "andi t8,t7,0xff",
                "sll t9,t8,2",
                "sw t9,12(s0)",
            ),
        )
        self.assertEqual(view.verdict, "phase-shift")
        self.assertEqual(view.playbook, "temp-fifo-phase")
        temp = next(lane for lane in view.lanes if lane.classification == "temp")
        self.assertEqual(temp.divergence, 4)
        self.assertEqual(temp.rotation, 1)
        self.assertIn("PRECEDING block", " ".join(view.guidance))

    def test_constant_difference_is_not_an_allocation_verdict(self) -> None:
        view = view_of(
            body("li v0,33", "sw v0,0(s0)"),
            body("li v0,49", "sw v0,0(s0)"),
        )
        self.assertEqual(view.verdict, "constant")
        self.assertEqual(view.counts["constant"], 1)
        self.assertIn("assembly encodes the truth", " ".join(view.guidance))

    def test_stack_offset_shift_reads_as_a_constant_not_a_register_change(self) -> None:
        view = view_of(body("lw t6,16(sp)"), body("lw t6,20(sp)"))
        self.assertEqual(view.counts["constant"], 1)

    def test_reordering_is_schedule_not_structure(self) -> None:
        view = view_of(
            body("addu t6,a0,a1", "lw t7,0(s0)", "sw t7,4(s0)"),
            body("lw t7,0(s0)", "addu t6,a0,a1", "sw t7,4(s0)"),
        )
        self.assertEqual(view.verdict, "schedule")
        self.assertEqual(view.counts["structural"], 0)
        self.assertGreater(view.counts["schedule"], 0)
        self.assertIn("-g0", " ".join(view.guidance))

    def test_same_opcode_reorder_is_schedule_not_allocation(self) -> None:
        """Two loads that swapped places pair up as register differences."""

        view = view_of(
            body("lw t6,0(s0)", "lw t7,4(s0)", "sw t6,8(s0)", "sw t7,12(s0)"),
            body("lw t7,4(s0)", "lw t6,0(s0)", "sw t6,8(s0)", "sw t7,12(s0)"),
        )
        self.assertEqual(view.verdict, "schedule")
        self.assertEqual(view.counts["register"], 0)
        self.assertEqual(view.counts["schedule"], 2)
        self.assertIn("-g0", " ".join(view.guidance))

    def test_relocation_addends_elsewhere_do_not_hide_a_reorder(self) -> None:
        """The final vsprintf residual had both kinds of raw difference."""

        target = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 8c380000  lw $t8,0($at)\n"
            "                        0: R_MIPS_LO16 jump_table\n"
            "   4: 2401000a  li $at,10\n"
            "   8: 240e002d  li $t6,45\n",
            symbol="demo",
        )
        candidate = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 8c380014  lw $t8,20($at)\n"
            "                        0: R_MIPS_LO16 jump_table\n"
            "   4: 240e002d  li $t6,45\n"
            "   8: 2401000a  li $at,10\n",
            symbol="demo",
        )
        view = build_view(
            target,
            candidate,
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )

        self.assertEqual(view.verdict, "schedule")
        self.assertEqual(view.counts["schedule"], 2)
        self.assertEqual(view.counts["structural"], 0)
        # One symbol name on both sides, two different addends: the resolved
        # datum differs, so this is a pool-layout row rather than a
        # linker-controlled one. Either way it must not open or extend the
        # reordering run, which is what this fixture is really about.
        self.assertEqual(view.counts["relocation"], 0)
        self.assertEqual(view.counts["pool_layout"], 1)
        guidance = " ".join(view.guidance)
        self.assertIn("does not prove source correctness", guidance)

    def test_relocation_only_difference_is_linker_controlled(self) -> None:
        target = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 3c010123  lui $at,0x123\n"
            "                        0: R_MIPS_HI16 global\n"
            "   4: 03e00008  jr $ra\n"
            "   8: 00000000  nop\n",
            symbol="demo",
        )
        candidate = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 3c010000  lui $at,0x0\n"
            "                        0: R_MIPS_HI16 global\n"
            "   4: 03e00008  jr $ra\n"
            "   8: 00000000  nop\n",
            symbol="demo",
        )
        view = build_view(
            target,
            candidate,
            target_name="t",
            candidate_name="c",
            symbol="demo",
        )
        self.assertEqual(view.verdict, "words-identical")
        self.assertEqual(view.counts["relocation"], 1)
        self.assertEqual(view.counts["constant"], 0)
        self.assertEqual(view.playbook, "relocation-only")

    def test_jump_table_section_addends_are_not_source_residuals(self) -> None:
        """IDO and hand assembly name the same relocation layout differently."""

        target = body("lui at,0", "addu at,at,t8", "lw t8,0(at)")
        candidate = body("lui at,0", "addu at,at,t8", "lw t8,172(at)")
        view = view_of(
            target,
            candidate,
            relocations={
                4: "R_MIPS_HI16 jtbl_8009AE9C",
                6: "R_MIPS_LO16 jtbl_8009AE9C",
            },
            candidate_relocations={
                4: "R_MIPS_HI16 .rodata",
                6: "R_MIPS_LO16 .rodata",
            },
        )
        self.assertEqual(view.verdict, "words-identical")
        # The pair resolves: `jtbl_8009AE9C+0` and `.rodata+172` are one datum
        # reached through two anchorings, so both rows are `pool`, not
        # `relocation`, and neither is reported as a difference.
        self.assertEqual(view.counts["pool"], 2)
        self.assertEqual(view.counts["pool_layout"], 0)
        self.assertEqual(view.counts["relocation"], 0)
        self.assertEqual(view.counts["schedule"], 0)
        self.assertEqual(view.counts["constant"], 0)

    def test_unknown_relocation_is_announced_not_guessed(self) -> None:
        view = view_of(
            body("jal helper", "nop"),
            body("jal helper", "nop"),
            relocations={4: "R_MIPS_INVENTED helper"},
        )
        self.assertIn("unknown-relocation:R_MIPS_INVENTED", view.signature)

    def test_identical_input_is_exact(self) -> None:
        lines = body("lw t6,0(s0)", "addu t7,t6,t6")
        view = view_of(lines, lines)
        self.assertEqual(view.verdict, "exact")
        self.assertIsNone(view.prefix_exact)
        self.assertIn("prefix-exact@all", view.signature)
        self.assertEqual(view.hunks, ())

    def test_mixed_residual_names_every_class(self) -> None:
        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        self.assertTrue(view.verdict.startswith("mixed("))
        self.assertIn("constant:1", view.verdict)
        self.assertIn("register:2", view.verdict)
        self.assertIn("fix constants first", view.guidance[0])


class SignatureTests(unittest.TestCase):
    def test_prefix_exact_reports_the_first_divergent_row(self) -> None:
        view = view_of(
            body("lw t6,0(s0)", "lw t7,4(s0)", "addu t8,t6,t7"),
            body("lw t6,0(s0)", "lw t7,4(s0)", "subu t8,t6,t7"),
        )
        self.assertEqual(view.prefix_exact, 6)
        self.assertIn("prefix-exact@6", view.signature)
        self.assertFalse(view.register_first_divergence)

    def test_register_first_divergence_is_called_out(self) -> None:
        view = view_of(
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t6,t8,t9",
                "sw t6,12(s0)",
            ),
            body(
                "lw t6,0(s0)",
                "lw t7,4(s0)",
                "addu t8,t6,t7",
                "lw t9,8(s0)",
                "addu t7,t8,t9",
                "sw t7,12(s0)",
            ),
        )
        self.assertIn("state-divergence@temp:4", view.signature)
        self.assertTrue(view.register_first_divergence)
        screen = "\n".join(render_view(view))
        self.assertIn("upstream of hunk 1", screen)


class LaneTests(unittest.TestCase):
    def test_lanes_include_matching_instructions(self) -> None:
        view = view_of(
            body("lw t6,0(s0)", "lw t7,4(s0)", "addu t8,t6,t7"),
            body("lw t6,0(s0)", "lw t7,4(s0)", "addu t8,t6,t7"),
        )
        temp = next(lane for lane in view.lanes if lane.classification == "temp")
        self.assertEqual(temp.target, ("t6", "t7", "t8"))
        self.assertEqual(temp.candidate, ("t6", "t7", "t8"))
        self.assertIsNone(temp.divergence)

    def test_lane_classes_come_from_the_profile_table(self) -> None:
        lines = body("lw s1,0(s0)", "lw t6,4(s0)")
        view = view_of(lines, lines)
        classes = {lane.classification: lane.target for lane in view.lanes}
        # `s1` is a uopt color and `t6` a ugen temp under the verified IDO 5.3
        # split; the two populations never share a lane.
        # `s0` is a color too, so the fixture's own prologue and epilogue
        # bracket the load.
        self.assertEqual(classes["pool"], ("s0", "s1", "s0"))
        self.assertEqual(classes["temp"], ("t6",))

    def test_unknown_profile_is_refused(self) -> None:
        text = assemble(body("nop"), symbol=SYMBOL)
        instructions = parse_disassembly(text, symbol=SYMBOL)
        with self.assertRaises(ValueError) as error:
            build_view(
                instructions,
                instructions,
                target_name="t",
                candidate_name="c",
                register_profile="nope",
            )
        self.assertIn("ido53", str(error.exception))

    def test_stores_and_branches_do_not_add_lane_slots(self) -> None:
        self.assertIsNone(destination_register("sw $t6,4($s0)"))
        self.assertIsNone(destination_register("bne $a0,$zero,10 <demo+0x10>"))
        self.assertIsNone(destination_register("jal 0 <helper>"))
        self.assertIsNone(destination_register("nop"))
        self.assertIsNone(destination_register("mult $t6,$t7"))
        self.assertEqual(destination_register("lw $t6,4($s0)"), "t6")
        self.assertEqual(destination_register("addu $t8,$t6,$t7"), "t8")


class RuleTests(unittest.TestCase):
    def test_classify_pair_rules(self) -> None:
        def pair(target: str, candidate: str) -> str:
            left = Instruction(address=0, word="00000000", assembly=target)
            right = Instruction(address=0, word="00000001", assembly=candidate)
            return classify_pair(
                left,
                right,
                target_text=target.replace("$", ""),
                candidate_text=candidate.replace("$", ""),
            )

        self.assertEqual(pair("addu $t6,$t0,$t1", "addu $t7,$t0,$t1"), "register")
        self.assertEqual(pair("or $t6,$t0,$t1", "or $t6,$t1,$t0"), "commutative")
        self.assertEqual(pair("li $v0,33", "li $v0,49"), "constant")
        self.assertEqual(pair("jal 0 <a>", "jal 0 <b>"), "structural")

    def test_identical_text_with_differing_words_is_structural(self) -> None:
        left = Instruction(address=0, word="00000000", assembly="nop")
        right = Instruction(address=0, word="00000001", assembly="nop")
        self.assertEqual(
            classify_pair(left, right, target_text="nop", candidate_text="nop"),
            "structural",
        )


class RenderingTests(unittest.TestCase):
    def test_every_difference_site_is_printed(self) -> None:
        """The verdict chooses emphasis, never visibility."""

        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        screen = "\n".join(render_view(view))
        self.assertIn("li $v0,33", screen)
        self.assertIn("li $v0,49", screen)
        self.assertIn("t8->t6 [w1]", screen)

    def test_human_labels_are_schema_keys(self) -> None:
        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        allowed = schema_keys()
        for line in render_view(view, report_regs=True):
            if line.startswith("next: ") or line.startswith("      "):
                continue
            for token in re.findall(r"\b([a-z_]+)=", line):
                self.assertIn(token, allowed, line)

    def test_json_keys_are_schema_keys(self) -> None:
        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        payload = view.as_dict(report_regs=True)
        allowed = schema_keys()
        self.assertLessEqual(set(payload), allowed)
        for section in ("hunks", "lanes", "webs", "register_report"):
            for entry in payload[section]:
                self.assertLessEqual(set(entry), allowed, section)

    def test_the_registry_and_the_output_are_one_set(self) -> None:
        """Completeness, both directions.

        ``<=`` in either direction alone is satisfiable by cheating: a registry
        that lists everything imaginable passes the "emitted keys are
        registered" half, and a command that prints nothing passes the other.
        Equality is the property worth having -- a key can neither be printed
        without an explanation nor explained without being printed.
        """

        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        emitted = emitted_keys(view)
        self.assertEqual(emitted - schema_keys(), set(), "printed but unregistered")
        self.assertEqual(schema_keys() - emitted, set(), "registered but never printed")

    def test_json_counts_agree_with_the_printed_header(self) -> None:
        view = view_of(
            body("li v0,33", "lw t8,0(s0)", "sw t8,4(s0)"),
            body("li v0,49", "lw t6,0(s0)", "sw t6,4(s0)"),
        )
        payload = view.as_dict()
        header = render_view(view)[1]
        for key in ("structural", "schedule", "register", "constant"):
            self.assertIn(f"{key}={payload[key]}", header)
        self.assertIn(f"hunks={len(payload['hunks'])}", header)

    def test_report_regs_covers_matching_rows(self) -> None:
        view = view_of(
            body("lw t8,0(s0)", "sw t8,4(s0)"),
            body("lw t6,0(s0)", "sw t6,4(s0)"),
        )
        report = view.register_report()
        self.assertEqual(len(report), view.aligned_rows)
        matched = [item for item in report if item["class"] == "match"]
        self.assertTrue(matched)
        self.assertEqual(matched[0]["target"], matched[0]["candidate"])

    def test_hunk_limit_is_reported_not_silently_applied(self) -> None:
        target = body(*[f"lw t8,{index * 4}(s0)" for index in range(6)])
        candidate = body(*[f"lw t6,{index * 4}(s0)" for index in range(6)])
        # Break the run into separate hunks with matching rows in between.
        for index in (1, 3, 5):
            candidate[len(PROLOGUE) + index] = target[len(PROLOGUE) + index]
        view = view_of(target, candidate)
        screen = "\n".join(render_view(view, max_hunks=1))
        self.assertIn("further hunk(s) not shown", screen)
        self.assertIn("HUNK 1", screen)
        self.assertNotIn("HUNK 2", screen)

    def test_color_is_opt_in_and_monochrome_is_complete(self) -> None:
        view = view_of(body("lw t8,0(s0)"), body("lw t6,0(s0)"))
        monochrome = "\n".join(render_view(view, painter=Painter(False)))
        colored = "\n".join(render_view(view, painter=Painter(True)))
        self.assertNotIn("\033[", monochrome)
        self.assertIn("\033[", colored)
        self.assertIn("[w1]", monochrome)
        self.assertFalse(resolve_color("never"))
        self.assertTrue(resolve_color("always"))

    def test_auto_color_follows_the_stream_and_no_color(self) -> None:
        class Tty(io.StringIO):
            def isatty(self) -> bool:
                return True

        environment = {key: value for key, value in os.environ.items()}
        environment.pop("NO_COLOR", None)
        with unittest.mock.patch.dict(os.environ, environment, clear=True):
            self.assertTrue(resolve_color("auto", stream=Tty()))
            self.assertFalse(resolve_color("auto", stream=io.StringIO()))
        with unittest.mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(resolve_color("auto", stream=Tty()))

    def test_output_is_ascii_only(self) -> None:
        view = view_of(body("lw t8,0(s0)"), body("lw t6,0(s0)"))
        screen = "\n".join(render_view(view, report_regs=True))
        screen.encode("ascii")


OPCODE_CYCLE = (
    "lw t{a},0(s0)",
    "addu t{a},t{a},t{b}",
    "sw t{a},4(s0)",
    "andi t{b},t{a},0xff",
    "sll t{b},t{b},2",
    "lbu t{a},8(s0)",
    "or t{b},t{a},t{b}",
    "subu t{a},t{b},t{a}",
)


def long_function(count: int, *, swap_at: int = -1) -> list[str]:
    """Return a long body whose text repeats, as real idiomatic code does."""

    lines = list(PROLOGUE)
    for index in range(count):
        registers = {"a": 6, "b": 7} if index != swap_at else {"a": 8, "b": 9}
        lines.append(
            OPCODE_CYCLE[index % len(OPCODE_CYCLE)].format(
                a=registers["a"], b=registers["b"]
            )
        )
    return lines + EPILOGUE


class EvidenceTests(unittest.TestCase):
    """Nothing the screen shows may be narrower than the truth it reports."""

    def test_long_rows_are_widened_never_truncated(self) -> None:
        target = body("jal aVeryLongSymbolNameThatKeepsGoingAndGoing1", "nop")
        candidate = body("jal aVeryLongSymbolNameThatKeepsGoingAndGoing2", "nop")
        view = view_of(target, candidate)
        screen = render_view(view)
        self.assertIn("aVeryLongSymbolNameThatKeepsGoingAndGoing1", "\n".join(screen))
        self.assertIn("aVeryLongSymbolNameThatKeepsGoingAndGoing2", "\n".join(screen))

    def test_every_rendered_hunk_row_shows_a_visible_difference(self) -> None:
        """A row whose sides differ must never render as two identical cells."""

        cases = (
            (
                body("jal aLongSymbolNameUsedToForceColumnPadding1", "nop"),
                body("jal aLongSymbolNameUsedToForceColumnPadding2", "nop"),
            ),
            (
                body("lw t6,0(s0)", "andi t6,t6,0x1234"),
                body("lw t6,0(s0)", "andi t6,t6,0x1235"),
            ),
        )
        for target, candidate in cases:
            with self.subTest(target=target[4]):
                view = view_of(target, candidate)
                rendered = {
                    row.index: line
                    for row, line in _hunk_row_lines(view)
                    if row.target != row.candidate
                }
                self.assertTrue(rendered)
                for index, line in rendered.items():
                    left, _, right = line.partition(" | ")
                    self.assertNotEqual(left.strip(), right.strip(), index)

    def test_context_windows_never_print_a_row_twice(self) -> None:
        target = body(
            "lw t6,0(s0)",
            "nop",
            "nop",
            "lw t7,4(s0)",
            "nop",
            "nop",
            "lw t8,8(s0)",
        )
        candidate = body(
            "lw t9,0(s0)",
            "nop",
            "nop",
            "lw t6,4(s0)",
            "nop",
            "nop",
            "lw t7,8(s0)",
        )
        view = view_of(target, candidate)
        self.assertGreaterEqual(len(view.hunks), 3)
        indexes = [row.index for row, _ in _hunk_row_lines(view, context=4)]
        self.assertEqual(sorted(indexes), sorted(set(indexes)))

    def test_header_names_the_register_profile(self) -> None:
        view = view_of(body("lw t6,0(s0)"), body("lw t7,0(s0)"))
        self.assertIn("register_profile=ido53", render_view(view)[0])


def _hunk_row_lines(
    view: MechanismView, *, context: int = 2
) -> list[tuple[AlignedRow, str]]:
    """Return the aligned rows a rendered screen prints, with their lines."""

    pairs: list[tuple[AlignedRow, str]] = []
    for line in render_view(view, context=context):
        match = re.match(r"^\s+(\d+) [ >] ", line)
        if match:
            pairs.append((view.rows[int(match.group(1))], line))
    return pairs


class InputTests(unittest.TestCase):
    def test_empty_input_is_refused_not_called_exact(self) -> None:
        instructions = parse_disassembly(
            assemble(body("nop"), symbol=SYMBOL), symbol=SYMBOL
        )
        for target, candidate in (([], instructions), (instructions, []), ([], [])):
            with self.subTest(target=len(target), candidate=len(candidate)):
                with self.assertRaises(ValueError) as error:
                    build_view(target, candidate, target_name="t", candidate_name="c")
                self.assertIn("no instructions", str(error.exception))


class PerformanceTests(unittest.TestCase):
    def test_large_function_renders_quickly(self) -> None:
        """vsprintf scale: alignment plus rendering must stay interactive."""

        target = long_function(1500)
        candidate = long_function(1500, swap_at=700)
        target_text = assemble(target, symbol="big")
        candidate_text = assemble(candidate, symbol="big")
        start = time.perf_counter()
        view = build_view(
            parse_disassembly(target_text, symbol="big"),
            parse_disassembly(candidate_text, symbol="big"),
            target_name="t",
            candidate_name="c",
            symbol="big",
        )
        lines = render_view(view)
        elapsed = time.perf_counter() - start
        self.assertEqual(view.counts["register"], 1)
        self.assertEqual(view.counts["structural"], 0)
        self.assertTrue(lines)
        self.assertLess(elapsed, 1.0, f"view took {elapsed:.3f}s")

    def test_repeating_text_does_not_derail_the_alignment(self) -> None:
        """A greedy longest-block anchor can throw away half a function.

        The text anchoring alone reported 61 matches and 2079 structural rows
        on this input, because one common run past the change was longer than
        everything before it.  Scoring both anchorings fixes it.
        """

        target = long_function(400)
        candidate = long_function(400, swap_at=100)
        view = view_of(target, candidate, symbol="big")
        self.assertEqual(view.counts["register"], 1)
        self.assertEqual(view.counts["structural"], 0)
        self.assertEqual(view.counts["match"], len(target) - 1)


FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "fixtures"
PHASE_TARGET = str(FIXTURES / "phase-shift-target.objdump")
PHASE_CANDIDATE = str(FIXTURES / "phase-shift-candidate.objdump")
SHIFT_TARGET = str(FIXTURES / "shifted-insertion-target.objdump")
SHIFT_CANDIDATE = str(FIXTURES / "shifted-insertion-candidate.objdump")


class ViewCommandTests(unittest.TestCase):
    """The command must work from reduced dumps: that is the shareable path."""

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_view_dumps_renders_the_documented_screen(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--color",
                "never",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("verdict: phase-shift", stdout)
        self.assertIn("signature: prefix-exact@12", stdout)
        self.assertIn("register-first-divergence", stdout)
        self.assertIn("REGISTER LANES", stdout)
        self.assertIn("rotation=+1", stdout)
        self.assertIn("HUNK 1", stdout)
        self.assertIn("WEBS", stdout)
        self.assertIn("next: one upstream event", stdout)

    def test_documented_contrast_with_positional_counting_holds(self) -> None:
        """The README claim that alignment collapses a cascade must stay true."""

        _, positional, _ = self.run_cli(
            ["compare-dumps", SHIFT_TARGET, SHIFT_CANDIDATE, "--symbol", "blockSum"]
        )
        _, aligned, _ = self.run_cli(
            [
                "view-dumps",
                SHIFT_TARGET,
                SHIFT_CANDIDATE,
                "--symbol",
                "blockSum",
                "--json",
            ]
        )
        payload = json.loads(aligned)
        words = int(next(re.finditer(r"words=\s*(\d+)", positional)).group(1))
        self.assertGreaterEqual(words, 10)
        self.assertEqual(payload["structural"], 1)
        self.assertEqual(payload["register"], 0)
        self.assertEqual(len(payload["hunks"]), 1)
        self.assertEqual(payload["verdict"], "structure")

    def test_symbol_and_function_are_the_same_option(self) -> None:
        arguments = [PHASE_TARGET, PHASE_CANDIDATE, "--color", "never"]
        _, with_symbol, _ = self.run_cli(
            ["view-dumps", *arguments, "--symbol", "animStep"]
        )
        _, with_function, _ = self.run_cli(
            ["view-dumps", *arguments, "--function", "animStep"]
        )
        self.assertEqual(with_symbol, with_function)

    def test_json_uses_the_same_keys_as_the_human_labels(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--symbol",
                "animStep",
                "--json",
                "--report-regs",
            ]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-view-v2")
        self.assertLessEqual(set(payload) - {"schema"}, schema_keys())
        self.assertEqual(payload["verdict"], "phase-shift")
        self.assertEqual(payload["playbook"], "temp-fifo-phase")
        self.assertEqual(payload["prefix_exact"], 12)
        self.assertEqual(payload["register"], 6)
        self.assertEqual(payload["structural"], 0)
        self.assertEqual(len(payload["register_report"]), payload["aligned_rows"])
        self.assertIn("register-first-divergence", payload["signature"])
        temp = next(lane for lane in payload["lanes"] if lane["class"] == "temp")
        self.assertEqual(temp["rotation"], 1)
        # Two units, two names, and the same two names on the screen.
        self.assertEqual(temp["slot"], 5)
        self.assertEqual(temp["aligned_row"], 12)
        self.assertNotIn("divergence", temp)

    def test_fail_on_mismatch_is_opt_in(self) -> None:
        arguments = [
            "view-dumps",
            PHASE_TARGET,
            PHASE_CANDIDATE,
            "--symbol",
            "animStep",
            "--color",
            "never",
        ]
        self.assertEqual(self.run_cli(arguments)[0], 0)
        self.assertEqual(self.run_cli([*arguments, "--fail-on-mismatch"])[0], 1)
        identical = [
            "view-dumps",
            PHASE_TARGET,
            PHASE_TARGET,
            "--symbol",
            "animStep",
            "--fail-on-mismatch",
            "--color",
            "never",
        ]
        self.assertEqual(self.run_cli(identical)[0], 0)

    def test_width_control_bounds_human_lines(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--symbol",
                "animStep",
                "--color",
                "never",
                "--pager",
                "never",
                "--width",
                "40",
            ]
        )
        self.assertEqual(status, 0)
        self.assertTrue(stdout)
        self.assertTrue(all(len(line) <= 40 for line in stdout.splitlines()))

    def test_html_report_is_self_contained_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "view.html"
            arguments = [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--symbol",
                "animStep",
                "--color",
                "never",
                "--pager",
                "never",
                "--html",
                str(output),
            ]
            status, _, _ = self.run_cli(arguments)
            document = output.read_text(encoding="utf-8")
            second_status, _, second_stderr = self.run_cli(arguments)
        self.assertEqual(status, 0)
        self.assertIn("<!doctype html>", document)
        self.assertIn("Machine-readable evidence", document)
        self.assertNotIn("https://", document)
        self.assertEqual(second_status, 2)
        self.assertIn("refusing to overwrite", second_stderr)

    def test_register_permutation_can_emit_an_honest_force_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.objdump"
            candidate = root / "candidate.objdump"
            output = root / "force.json"
            target.write_text(
                "00000000 <demo>:\n"
                "   0: 8e110000  lw $s1,0($s0)\n"
                "   4: ae110004  sw $s1,4($s0)\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "00000000 <demo>:\n"
                "   0: 8e120000  lw $s2,0($s0)\n"
                "   4: ae120004  sw $s2,4($s0)\n",
                encoding="utf-8",
            )
            status, _, _ = self.run_cli(
                [
                    "view-dumps",
                    str(target),
                    str(candidate),
                    "--symbol",
                    "demo",
                    "--color",
                    "never",
                    "--emit-force-spec",
                    str(output),
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(
            payload["schema"],
            "decomp-workbench-diagnostic-force-v1",
        )
        self.assertIsNone(payload["permutation"][0]["allocator_web"])
        self.assertIn("not compiler allocator web IDs", payload["proof"])

    def test_missing_symbol_reports_the_symbol(self) -> None:
        status, _, stderr = self.run_cli(
            ["view-dumps", PHASE_TARGET, PHASE_CANDIDATE, "--symbol", "absent"]
        )
        self.assertEqual(status, 2)
        self.assertIn("absent", stderr)

    def test_unreadable_input_exits_two(self) -> None:
        status, _, stderr = self.run_cli(
            ["view-dumps", PHASE_TARGET, str(FIXTURES / "missing.objdump")]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_view_reports_a_missing_objdump(self) -> None:
        status, _, stderr = self.run_cli(
            [
                "view",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--objdump",
                str(FIXTURES / "no-such-objdump"),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)


class ProfileTests(unittest.TestCase):
    def test_profiles_are_data_and_disjoint(self) -> None:
        for name, profile in REGISTER_CLASS_PROFILES.items():
            seen: set[str] = set()
            for members in profile.values():
                self.assertFalse(seen & set(members), name)
                seen |= set(members)


if __name__ == "__main__":
    unittest.main()
