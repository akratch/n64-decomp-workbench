"""The last mile: a named concept must always come with an address.

A correct verdict that leaves the reader asking "no idea what im meant to do
next" has failed at its actual job. These tests hold three promises:

* the shipped guide is the documented guide, so `guide` never prints a stale
  fork of the crown jewel;
* every playbook the diagnosis taxonomy can print resolves to levers that
  really exist, with a one-line action each;
* the on-ramp survives a stripped installation, an unnumbered lever, and a
  reader who pastes a verdict instead of a playbook.
"""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

from mips_asm import assemble

from decomp_workbench import field_guide
from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import build_view

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs" / "field-guide.md"
PACKAGED = ROOT / "src" / "decomp_workbench" / "docs" / "field-guide.md"

SYMBOL = "demo"

#: A register permutation: every difference is the same substitution, which is
#: the transcript's verdict and the one with no source lever at the end of it.
PERMUTATION_TARGET = ["lw t8,0(s0)", "addu t8,t8,t8", "sw t8,4(s0)"]
PERMUTATION_CANDIDATE = ["lw t6,0(s0)", "addu t6,t6,t6", "sw t6,4(s0)"]


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    """Run one command in process and capture both streams."""

    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def instructions(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol=SYMBOL), symbol=SYMBOL)


class PackagedGuideTests(unittest.TestCase):
    def test_packaged_guide_matches_the_documentation(self) -> None:
        """The wheel must ship the guide a reader browses, not a fork of it."""

        self.assertEqual(
            PACKAGED.read_text(encoding="utf-8"),
            CANONICAL.read_text(encoding="utf-8"),
            "the packaged field guide drifted; run:\n"
            "  cp docs/field-guide.md src/decomp_workbench/docs/field-guide.md",
        )

    def test_every_shipped_section_parses_with_its_number(self) -> None:
        sections = field_guide.sections()
        # Numbering is contiguous from 1 and only ever grows: asserting the
        # exact upper bound made every new lever a two-file edit, and the
        # property that matters is that no number is skipped.
        self.assertEqual(sorted(sections), list(range(1, max(sections) + 1)))
        self.assertGreaterEqual(max(sections), 24)
        self.assertEqual(sections[19].family, "When source search is over")
        self.assertIn("forced-color", sections[19].title)
        self.assertEqual(
            sections[21].family, "When the compiler itself is the variable"
        )
        self.assertTrue(sections[7].lines[0].startswith("### 7."))

    def test_a_missing_section_is_reported_not_raised(self) -> None:
        """An installation whose mirror is older than its code still answers.

        Levers 20-22 were numbered and actionable here while their prose was
        still on another branch; they ship now, so the case is reproduced by
        withholding a section rather than by naming one that is absent.
        """

        shipped = field_guide.sections()
        pruned = {number: shipped[number] for number in shipped if number != 20}
        topic = field_guide.resolve_topic("20")
        rendered = "\n".join(field_guide.render_topic(topic, pruned))
        self.assertIn("not in the shipped field guide", rendered)
        self.assertIn(field_guide.LEVER_ACTIONS[20], rendered)

    def test_the_levers_that_arrived_late_now_have_their_prose(self) -> None:
        """The composition point between the two branches, asserted."""

        shipped = field_guide.sections()
        for number in (20, 21, 22):
            with self.subTest(lever=number):
                self.assertIn(number, shipped)
                body = "\n".join(shipped[number].lines)
                self.assertNotIn("not in the shipped field guide", body)
        topic = field_guide.resolve_topic("frontend-lineage")
        rendered = "\n".join(field_guide.render_topic(topic, shipped))
        self.assertIn("### 20.", rendered)
        self.assertIn("### 21.", rendered)
        self.assertIn("### 22.", rendered)
        self.assertIn("docs/alternate-frontends.md", rendered)


class PreprocessorAuditLeverTests(unittest.TestCase):
    """Lever 24: the drawbitmap-class undefined-identifier collapse."""

    def test_lever_24_has_a_one_line_action_naming_the_command(self) -> None:
        action = field_guide.LEVER_ACTIONS[24]
        self.assertNotIn("\n", action)
        self.assertIn("context lint", action)

    def test_lever_24_routes_from_the_structural_and_schedule_playbooks(self) -> None:
        self.assertIn(24, field_guide.PLAYBOOK_LEVERS["structure-buckets"])
        self.assertIn(24, field_guide.PLAYBOOK_LEVERS["g0-schedule-probe"])

    def test_lever_24_section_is_shipped_and_reachable_by_number(self) -> None:
        shipped = field_guide.sections()
        self.assertIn(24, shipped)
        self.assertIn("Preprocessor-conditional audit", shipped[24].title)
        status, stdout, _ = run_cli(["guide", "24", "--pager", "never"])
        self.assertEqual(status, 0)
        self.assertIn("### 24.", stdout)
        self.assertIn("drawbitmap", stdout)

    def test_levers_23_and_24_coexist_after_integration(self) -> None:
        """23 (line assignment) and 24 (conditional audit) were developed on
        sibling branches; the merged guide must carry both."""

        self.assertIn(23, field_guide.LEVER_ACTIONS)
        self.assertIn(24, field_guide.LEVER_ACTIONS)

    def test_structure_and_schedule_verdicts_print_lever_24_in_their_on_ramp(
        self,
    ) -> None:
        for playbook in ("structure-buckets", "g0-schedule-probe"):
            with self.subTest(playbook=playbook):
                steps = field_guide.next_steps(playbook)
                text = "\n".join(steps)
                self.assertIn("lever 24:", text)


class StackFrameRecoveryTests(unittest.TestCase):
    """Lever 26: allocator-exact output must not route to literal search."""

    TARGET: ClassVar[list[str]] = [
        "addiu sp,sp,-40",
        "sw ra,36(sp)",
        "lw ra,36(sp)",
        "addiu sp,sp,40",
        "jr ra",
        "nop",
    ]
    CANDIDATE: ClassVar[list[str]] = [
        "addiu sp,sp,-56",
        "sw ra,36(sp)",
        "lw ra,36(sp)",
        "addiu sp,sp,56",
        "jr ra",
        "nop",
    ]

    def test_compare_names_the_frame_pair_instead_of_a_literal(self) -> None:
        result = compare_instructions(
            instructions(self.TARGET),
            instructions(self.CANDIDATE),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertEqual(result.verdict, "frame-layout-mismatch")
        guidance = "\n".join(result.guidance)
        self.assertIn("stack-home/layout", guidance)
        self.assertNotIn("flag, enum", guidance)
        self.assertIn("lever 26:", guidance)

    def test_view_routes_to_stack_frame_recovery(self) -> None:
        view = build_view(
            instructions(self.TARGET),
            instructions(self.CANDIDATE),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertEqual(view.verdict, "frame-layout")
        self.assertEqual(view.playbook, "stack-frame-recovery")
        guidance = "\n".join(view.guidance)
        self.assertIn("allocator-winning live ranges", guidance)
        self.assertIn("lever 26:", guidance)

    def test_playbook_and_shipped_section_are_reachable(self) -> None:
        self.assertEqual(field_guide.PLAYBOOK_LEVERS["stack-frame-recovery"], (26,))
        self.assertEqual(
            field_guide.VERDICT_PLAYBOOKS["frame-layout-mismatch"],
            "stack-frame-recovery",
        )
        self.assertIn(26, field_guide.sections())
        status, stdout, _ = run_cli(
            ["guide", "stack-frame-recovery", "--pager", "never"]
        )
        self.assertEqual(status, 0)
        self.assertIn("### 26.", stdout)
        self.assertIn("allocation is exact", stdout.lower())


class LeverMappingTests(unittest.TestCase):
    def test_every_playbook_lever_has_a_one_line_action(self) -> None:
        for playbook, levers in field_guide.PLAYBOOK_LEVERS.items():
            for number in levers:
                with self.subTest(playbook=playbook, lever=number):
                    action = field_guide.LEVER_ACTIONS[number]
                    self.assertTrue(action)
                    self.assertNotIn("\n", action)

    def test_every_playbook_lever_is_in_the_shipped_guide(self) -> None:
        """Levers 1-19 are this branch's contract; a typo here is silent."""

        shipped = field_guide.sections()
        cited = {
            number
            for levers in field_guide.PLAYBOOK_LEVERS.values()
            for number in levers
        }
        self.assertEqual(cited - set(shipped), set())

    def test_the_transcript_playbook_names_levers_and_a_command(self) -> None:
        steps = field_guide.next_steps("forced-color-oracle")
        text = "\n".join(steps)
        self.assertIn("lever 17:", text)
        self.assertIn("lever 18:", text)
        self.assertIn("lever 19:", text)
        self.assertIn("decision-trace order", text)
        self.assertIn("decomp-workbench guide forced-color-oracle", text)
        self.assertIn("have an instrumented toolchain?", text)
        self.assertIn("don't have one?", text)
        self.assertIn("docs/compiler-instrumentation.md", text)

    def test_every_instrumentation_playbook_offers_both_branches(self) -> None:
        """A tool most readers lack is only advice if the other branch exists."""

        for playbook in ("forced-color-oracle", "pool-position", "temp-fifo-phase"):
            with self.subTest(playbook=playbook):
                steps = field_guide.PLAYBOOK_ONRAMPS[playbook]
                self.assertTrue(any(step.startswith("have") for step in steps))
                self.assertTrue(any(step.startswith("don't have") for step in steps))

    def test_the_source_branch_comes_first_where_source_still_works(self) -> None:
        """Trace last is the documented order; a footer teaches it or fights it.

        `forced-color-oracle` is the deliberate exception: lever 19 is the
        point where source search is genuinely over, so its instrumented
        branch leads.
        """

        for playbook in ("pool-position", "temp-fifo-phase"):
            with self.subTest(playbook=playbook):
                first = field_guide.PLAYBOOK_ONRAMPS[playbook][0]
                self.assertTrue(first.startswith("don't have"))
        oracle = field_guide.PLAYBOOK_ONRAMPS["forced-color-oracle"][0]
        self.assertTrue(oracle.startswith("have an instrumented toolchain?"))

    def test_the_catch_all_playbook_admits_it_is_a_catch_all(self) -> None:
        caveat = field_guide.PLAYBOOK_CAVEATS["pool-position"]
        self.assertIn("three unresolved allocation families", caveat)
        _, stdout, _ = run_cli(["guide", "pool-position", "--pager", "never"])
        self.assertIn("three unresolved allocation families", stdout)


class GuideCommandTests(unittest.TestCase):
    def test_no_topic_lists_every_topic_class(self) -> None:
        status, stdout, _ = run_cli(["guide", "--pager", "never"])
        self.assertEqual(status, 0)
        self.assertIn("forced-color-oracle", stdout)
        self.assertIn("register-permutation", stdout)
        self.assertIn("19", stdout)

    def test_a_playbook_prints_each_of_its_sections(self) -> None:
        status, stdout, _ = run_cli(
            ["guide", "forced-color-oracle", "--pager", "never"]
        )
        self.assertEqual(status, 0)
        self.assertIn("### 17.", stdout)
        self.assertIn("### 18.", stdout)
        self.assertIn("### 19.", stdout)

    def test_a_lever_number_prints_one_section_and_its_playbook(self) -> None:
        status, stdout, _ = run_cli(["guide", "19", "--pager", "never"])
        self.assertEqual(status, 0)
        self.assertIn("### 19.", stdout)
        self.assertNotIn("### 18.", stdout)
        self.assertIn("decomp-workbench guide forced-color-oracle", stdout)

    def test_a_verdict_resolves_to_the_same_page_as_its_playbook(self) -> None:
        """The reader pastes what the footer printed, whichever taxonomy it is."""

        _, by_verdict, _ = run_cli(
            ["guide", "register-permutation", "--pager", "never"]
        )
        _, by_compare_verdict, _ = run_cli(
            ["guide", "allocation-mismatch", "--pager", "never"]
        )
        self.assertIn("playbook=forced-color-oracle", by_verdict)
        self.assertIn("### 19.", by_verdict)
        self.assertIn("playbook=pool-position", by_compare_verdict)

    def test_unknown_topic_points_at_the_index(self) -> None:
        status, _, stderr = run_cli(["guide", "not-a-playbook", "--pager", "never"])
        self.assertEqual(status, 2)
        self.assertIn("decomp-workbench guide", stderr)

    def test_missing_resource_degrades_to_the_one_line_actions(self) -> None:
        """A stripped install still answers; it just cannot elaborate."""

        with mock.patch.object(
            field_guide,
            "read_field_guide",
            side_effect=FileNotFoundError("the field guide is not installed"),
        ):
            status, stdout, stderr = run_cli(
                ["guide", "forced-color-oracle", "--pager", "never"]
            )
        self.assertEqual(status, 2)
        self.assertIn("not installed", stderr)
        self.assertIn(field_guide.LEVER_ACTIONS[19], stdout)
        self.assertIn("### 19. (not in the shipped field guide)", stdout)


class NextStepsRenderingTests(unittest.TestCase):
    def test_register_permutation_view_carries_the_on_ramp(self) -> None:
        view = build_view(
            instructions(PERMUTATION_TARGET),
            instructions(PERMUTATION_CANDIDATE),
            symbol=SYMBOL,
            target_name="target",
            candidate_name="candidate",
        )
        self.assertEqual(view.verdict, "register-permutation")
        guidance = "\n".join(view.guidance)
        # the expert content that was already there
        self.assertIn("one bijection", guidance)
        self.assertIn("forced color probe", guidance)
        # and the address it never had
        self.assertIn("lever 17:", guidance)
        self.assertIn("decomp-workbench guide forced-color-oracle", guidance)
        self.assertIn("don't have one?", guidance)

    def test_a_coarse_verdict_names_three_families_and_picks_none(self) -> None:
        """These very fixtures are why the old lever dump was a guess.

        `compare` calls this pair `allocation-mismatch`; `view`, looking at the
        same two streams, calls it `register-permutation`, whose levers are
        17-19. The previous assertion locked in `pool-position`'s levers 7-13
        on evidence that contradicted them, and the sentence directly above
        told the reader to run `view` because *it* names the family.
        """

        result = compare_instructions(
            instructions(PERMUTATION_TARGET),
            instructions(PERMUTATION_CANDIDATE),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertEqual(result.verdict, "allocation-mismatch")
        view = build_view(
            instructions(PERMUTATION_TARGET),
            instructions(PERMUTATION_CANDIDATE),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertEqual(view.verdict, "register-permutation")

        guidance = "\n".join(result.guidance)
        # all three families, each with the command that opens it
        for playbook in ("temp-fifo-phase", "pool-position", "forced-color-oracle"):
            self.assertIn(f"decomp-workbench guide {playbook}", guidance)
        # and no committed lever list from any one of them
        self.assertNotIn("lever 7:", guidance)
        self.assertNotIn("field guide levers for playbook=", guidance)
        # led by the sentence that says why this command cannot choose
        self.assertIn("compare cannot see which of the three it is", guidance)

    def test_no_coarse_verdict_can_ever_borrow_one_familys_levers(self) -> None:
        """Structural guard for the bug class behind round-2 finding #1.

        The original defect was a data-table entry: a coarse verdict routed to
        one family's committed lever list, and a rendering test locked the
        guess in. Guard the table itself so the regression cannot re-enter
        through any renderer: every verdict routed to an ambiguous playbook
        must produce the three-family block, and the allocation catch-alls
        must stay routed to an ambiguous playbook.
        """

        ambiguous = field_guide.AMBIGUOUS_PLAYBOOK_FAMILIES
        for coarse in ("allocation", "allocation-mismatch"):
            self.assertIn(field_guide.VERDICT_PLAYBOOKS[coarse], ambiguous, coarse)
        for verdict, playbook in field_guide.VERDICT_PLAYBOOKS.items():
            if playbook not in ambiguous:
                continue
            lines = "\n".join(field_guide.next_steps(playbook))
            self.assertNotIn("field guide levers for playbook=", lines, verdict)
            for family in ("temp-fifo-phase", "pool-position", "forced-color-oracle"):
                self.assertIn(f"decomp-workbench guide {family}", lines, verdict)

    def test_the_view_verdict_that_can_choose_still_does(self) -> None:
        """Only the coarse tags go neutral; a named mechanism keeps its levers."""

        view = build_view(
            instructions(PERMUTATION_TARGET),
            instructions(PERMUTATION_CANDIDATE),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        guidance = "\n".join(view.guidance)
        self.assertIn("field guide levers for playbook=forced-color-oracle", guidance)
        self.assertIn("lever 19:", guidance)

    def test_the_rendered_footer_keeps_the_next_prefix(self) -> None:
        """The block is one footer, not a second style bolted beside it."""

        status, stdout, _ = run_cli(
            [
                "diagnose-dumps",
                str(ROOT / "examples" / "fixtures" / "target.objdump"),
                str(ROOT / "examples" / "fixtures" / "register-mismatch.objdump"),
                "--pager",
                "never",
            ]
        )
        self.assertEqual(status, 0)
        footer = stdout.split("next: ", 1)[1].splitlines()
        self.assertTrue(
            all(not line or line.startswith("      ") for line in footer[1:])
        )
        self.assertIn("decomp-workbench guide forced-color-oracle", stdout)

    def test_diagnose_prints_one_lever_block_not_two(self) -> None:
        """`diagnose` renders both taxonomies; only the aligned one gets a footer.

        The comparison half and the mechanism half now each carry an on-ramp.
        Printing both would hand the reader two different lever lists for one
        residual, which is the confusion this change set out to remove.
        """

        status, stdout, _ = run_cli(
            [
                "diagnose-dumps",
                str(ROOT / "examples" / "fixtures" / "target.objdump"),
                str(ROOT / "examples" / "fixtures" / "register-mismatch.objdump"),
                "--pager",
                "never",
            ]
        )
        self.assertEqual(status, 0)
        self.assertEqual(stdout.count("field guide levers for playbook="), 1)
        self.assertNotIn("pool-position", stdout)

    def test_every_diagnosable_verdict_reaches_a_playbook(self) -> None:
        """A verdict with no on-ramp is the bug this change exists to remove."""

        for verdict in (
            "allocation",
            "commutative-order",
            "constant",
            "phase-shift",
            "register-permutation",
            "schedule",
            "structure",
        ):
            with self.subTest(verdict=verdict):
                playbook = field_guide.VERDICT_PLAYBOOKS[verdict]
                self.assertTrue(field_guide.next_steps(playbook))


if __name__ == "__main__":
    unittest.main()
