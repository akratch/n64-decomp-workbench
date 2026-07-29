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
import time
import unittest
import unittest.mock
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import (
    REGISTER_CLASS_PROFILES,
    MechanismView,
    build_view,
    classify_pair,
    commutative_swap,
    destination_register,
    schema_keys,
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
        self.assertEqual(view.counts["match"], len(target))

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
        self.assertTrue(branch.matched)
        self.assertNotEqual(branch.target, branch.candidate)

    def test_relocated_call_is_never_read_as_a_local_branch(self) -> None:
        view = view_of(
            body("jal helper", "nop"),
            body("jal helper", "nop"),
            relocations={4: "R_MIPS_26 helper"},
        )
        self.assertEqual(view.verdict, "exact")


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
            body("lw t8,0(s0)", "addu t8,t8,t8", "sw t8,4(s0)", "lw t9,8(s0)"),
            body("lw t6,0(s0)", "addu t6,t6,t6", "sw t6,4(s0)", "lw t9,8(s0)"),
        )
        self.assertEqual(view.verdict, "register-permutation")
        self.assertEqual([web.target for web in view.webs], ["t8"])
        self.assertEqual(view.webs[0].count, 3)
        self.assertEqual(view.webs[0].web, "w1")

    def test_inconsistent_substitutions_are_allocation(self) -> None:
        view = view_of(
            body("lw t8,0(s0)", "sw t8,4(s0)", "lw t8,8(s0)", "sw t8,12(s0)"),
            body("lw t6,0(s0)", "sw t6,4(s0)", "lw t7,8(s0)", "sw t7,12(s0)"),
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
        self.assertFalse(view.upstream_byte_invisible)

    def test_state_divergence_before_the_visible_block_is_called_out(self) -> None:
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
        self.assertTrue(view.upstream_byte_invisible)
        screen = "\n".join(render_view(view))
        self.assertIn("UPSTREAM of hunk 1", screen)


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
        lines = body("lw t0,0(s0)", "lw t6,4(s0)")
        view = view_of(lines, lines)
        classes = {lane.classification: lane.target for lane in view.lanes}
        self.assertEqual(classes["pool"], ("t0",))
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
    def test_commutative_swap_rule(self) -> None:
        self.assertTrue(commutative_swap("or", ["t0", "t1", "t2"], ["t0", "t2", "t1"]))
        self.assertTrue(commutative_swap("mult", ["t1", "t2"], ["t2", "t1"]))
        self.assertFalse(
            commutative_swap("subu", ["t0", "t1", "t2"], ["t0", "t2", "t1"])
        )
        self.assertFalse(commutative_swap("or", ["t0", "t1", "t2"], ["t0", "t1", "t2"]))
        self.assertFalse(commutative_swap("or", ["t0", "t1", "t2"], ["t3", "t2", "t1"]))

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
                self.assertLessEqual(set(entry) - {"classes"}, allowed, section)

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


class PerformanceTests(unittest.TestCase):
    def test_large_function_renders_quickly(self) -> None:
        """vsprintf scale: alignment plus rendering must stay interactive."""

        def stream(swap_at: int) -> list[Instruction]:
            items = []
            for index in range(1500):
                register = "t6" if index != swap_at else "t7"
                items.append(
                    Instruction(
                        address=index * 4,
                        word=f"{index:08x}",
                        assembly=f"lw ${register},{index % 64 * 4}($s0)",
                    )
                )
            return items

        start = time.perf_counter()
        view = build_view(
            stream(-1),
            stream(700),
            target_name="t",
            candidate_name="c",
            symbol="big",
        )
        lines = render_view(view)
        elapsed = time.perf_counter() - start
        self.assertEqual(view.counts["register"], 1)
        self.assertTrue(lines)
        self.assertLess(elapsed, 1.0, f"view took {elapsed:.3f}s")


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
        self.assertIn("upstream-byte-invisible", stdout)
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
        self.assertLessEqual(set(payload), schema_keys())
        self.assertEqual(payload["verdict"], "phase-shift")
        self.assertEqual(payload["playbook"], "temp-fifo-phase")
        self.assertEqual(payload["prefix_exact"], 12)
        self.assertEqual(payload["register"], 6)
        self.assertEqual(payload["structural"], 0)
        self.assertEqual(len(payload["register_report"]), payload["aligned_rows"])
        self.assertIn("upstream-byte-invisible", payload["signature"])
        temp = next(lane for lane in payload["lanes"] if lane["class"] == "temp")
        self.assertEqual(temp["rotation"], 1)
        self.assertEqual(temp["divergence"], 5)

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
