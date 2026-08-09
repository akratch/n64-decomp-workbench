"""Tests for `next`: discovery as a command.

What is pinned here is the *ordering rule*, not the wording. A step that
clears a blocker must outrank a step that interprets what the blocker
distorts, because the campaign's recurring mistake was reading a register
residue that was measured across an instruction-count difference and was
therefore not a register residue at all.
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
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.whats_next import (
    RANK_ATTRIBUTION,
    RANK_BLOCKER,
    RANK_REFERENCE,
    Plan,
    plan_next_steps,
    render_plan,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures"

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def plan_of(
    target: list[str], candidate: list[str], *, source: str | None = None
) -> Plan:
    comparison = compare_instructions(
        parse_disassembly(assemble(target, symbol=SYMBOL), symbol=SYMBOL),
        parse_disassembly(assemble(candidate, symbol=SYMBOL), symbol=SYMBOL),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol=SYMBOL,
    )
    return plan_next_steps(
        comparison, target="target.o", candidate="candidate.o", source=source
    )


class OrderingTests(unittest.TestCase):
    def test_an_instruction_count_difference_ranks_first_as_a_blocker(self) -> None:
        plan = plan_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "addu v1,a0,a2"),
        )
        self.assertEqual(plan.steps[0].rank, RANK_BLOCKER)
        self.assertIn("instruction(s)", plan.steps[0].why)
        self.assertTrue(plan.blocked)
        self.assertIn("not measurable", " ".join(plan.blocked))

    def test_the_count_blocker_routes_to_the_shift_tolerant_diff(self) -> None:
        """ "4640 != 4641" is a shape question, and `align` answers it."""

        plan = plan_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "addu v1,a0,a2"),
        )
        self.assertIn("align target.o candidate.o", plan.steps[0].command)
        self.assertIn("how many instructions away", plan.steps[0].why)

    def test_a_run_of_float_register_rows_routes_to_the_ring_phase(self) -> None:
        """A rotated scratch ring is a renaming, not a list of mistakes."""

        target = body(
            *[f"lwc1 f{4 + 2 * (index % 4)},{index * 4}(sp)" for index in range(8)]
        )
        candidate = body(
            *[f"lwc1 f{8 - 2 * (index % 4) + 2},{index * 4}(sp)" for index in range(8)]
        )
        plan = plan_of(target, candidate)

        commands = [step.command for step in plan.steps]
        self.assertTrue(any("phase target.o candidate.o" in item for item in commands))

    def test_without_a_blocker_the_family_step_leads(self) -> None:
        plan = plan_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        self.assertNotEqual(plan.steps[0].rank, RANK_BLOCKER)
        self.assertEqual(plan.blocked, ())

    def test_steps_are_sorted_by_rank(self) -> None:
        plan = plan_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "addu v1,a0,a2"),
        )
        ranks = [step.rank for step in plan.steps]
        self.assertEqual(ranks, sorted(ranks))

    def test_the_plan_always_ends_at_the_field_guide(self) -> None:
        plan = plan_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        self.assertEqual(plan.steps[-1].rank, RANK_REFERENCE)
        self.assertIn("decomp-workbench guide ", plan.steps[-1].command)


class CommandContentTests(unittest.TestCase):
    def test_every_step_is_a_runnable_command_with_real_paths(self) -> None:
        plan = plan_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        for step in plan.steps:
            self.assertTrue(step.command.startswith("decomp-workbench "))
            # The placeholders other footers print must never survive here.
            self.assertNotIn("TARGET.o", step.command)
            self.assertNotIn("CANDIDATE.o", step.command)

    def test_every_step_carries_one_sentence_of_why(self) -> None:
        plan = plan_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        for step in plan.steps:
            self.assertTrue(step.why.strip())

    def test_a_source_path_is_substituted_into_the_region_step(self) -> None:
        plan = plan_of(
            body("addu v0,a0,a1"), body("addu t0,a0,a1"), source="work/champion.c"
        )
        region = [step for step in plan.steps if step.rank == RANK_ATTRIBUTION]
        self.assertEqual(len(region), 1)
        self.assertIn("--by-region work/champion.c", region[0].command)

    def test_without_a_source_the_step_says_how_to_supply_one(self) -> None:
        plan = plan_of(body("addu v0,a0,a1"), body("addu t0,a0,a1"))
        region = [step for step in plan.steps if step.rank == RANK_ATTRIBUTION]
        self.assertIn("--by-region SRC.c", region[0].command)
        self.assertIn("--src", region[0].why)

    def test_a_match_routes_to_the_whole_object_gate(self) -> None:
        rows = body("addu v0,a0,a1")
        plan = plan_of(rows, rows)
        self.assertTrue(plan.matched)
        commands = " ".join(step.command for step in plan.steps)
        self.assertIn("fidelity", commands)
        self.assertIn("object-collateral", commands)


class RenderTests(unittest.TestCase):
    def test_the_default_render_is_bounded_and_says_so(self) -> None:
        plan = plan_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "addu v1,a0,a2"),
        )
        rendered = "\n".join(render_plan(plan, limit=1))
        self.assertIn("1.", rendered)
        self.assertIn("pass --all", rendered)

    def test_a_blocker_is_labelled_in_the_render(self) -> None:
        plan = plan_of(
            body("addu v0,a0,a1"),
            body("addu v0,a0,a1", "addu v1,a0,a2"),
        )
        self.assertIn("[blocker]", "\n".join(render_plan(plan)))


class NextCommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(arguments)
        return status, out.getvalue(), err.getvalue()

    def test_the_command_prints_a_numbered_plan(self) -> None:
        status, output, _ = self.run_cli(
            [
                "next-dumps",
                str(FIXTURES / "phase-shift-target.objdump"),
                str(FIXTURES / "phase-shift-candidate.objdump"),
            ]
        )
        self.assertEqual(status, 0)
        self.assertTrue(output.startswith("next: "))
        self.assertIn("1.", output)
        self.assertIn("why:", output)

    def test_json_carries_the_schema_and_the_ranks(self) -> None:
        status, output, _ = self.run_cli(
            [
                "next-dumps",
                str(FIXTURES / "phase-shift-target.objdump"),
                str(FIXTURES / "phase-shift-candidate.objdump"),
                "--json",
            ]
        )
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(payload["schema"], "decomp-workbench-next-v1")
        self.assertTrue(payload["steps"])
        for step in payload["steps"]:
            self.assertIn("command", step)
            self.assertIn("why", step)
            self.assertIn("kind", step)

    def test_a_missing_input_is_a_clear_error(self) -> None:
        status, _, error = self.run_cli(["next", "absent-a.o", "absent-b.o"])
        self.assertEqual(status, 2)
        self.assertTrue(error.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
