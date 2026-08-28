"""A verdict names a mechanism; `routing` names the tool that gets it next.

The gap between those two cost a campaign about a million tokens: an
"interference-forbidden colour" and a "list-scheduler slot-fill -- no source
lever" were read as proof that two functions could not be matched, a bespoke
instrumentation build was funded to explain why, and a twenty-minute permuter
run then matched both. Every test here is about one property: an allocation,
colour, or schedule tie must never read as proven unmatchable, and must say
which tool to run instead.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import unittest
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.diagnosis import DIAGNOSIS_SCHEMA, diagnose_dumps
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import (
    PERMUTER_ROUTING_SENTENCE,
    PERMUTER_ROUTING_STEPS,
    ROUTING_IMPORT_FIX,
    ROUTING_NONE,
    ROUTING_PERMUTER_FIRST,
    ROUTING_STRUCTURAL,
    ROUTING_VALUES,
    MechanismView,
    build_view,
    routing_for,
)
from decomp_workbench.view_cli import render_view

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "fixtures"
PHASE_TARGET = str(FIXTURES / "phase-shift-target.objdump")
PHASE_CANDIDATE = str(FIXTURES / "phase-shift-candidate.objdump")

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]


def view_of(target: list[str], candidate: list[str]) -> MechanismView:
    target_text = assemble([*PROLOGUE, *target, *EPILOGUE], symbol=SYMBOL)
    candidate_text = assemble([*PROLOGUE, *candidate, *EPILOGUE], symbol=SYMBOL)
    return build_view(
        parse_disassembly(target_text, symbol=SYMBOL),
        parse_disassembly(candidate_text, symbol=SYMBOL),
        target_name="target.objdump",
        candidate_name="candidate.objdump",
        symbol=SYMBOL,
    )


class RoutingVocabularyTests(unittest.TestCase):
    def test_an_allocation_or_schedule_tie_routes_to_the_permuter(self) -> None:
        for verdict in (
            "allocation",
            "phase-shift",
            "register-permutation",
            "register-ring-only",
            "schedule",
        ):
            with self.subTest(verdict=verdict):
                self.assertEqual(routing_for(verdict, {}), ROUTING_PERMUTER_FIRST)

    def test_a_difference_the_diff_already_shows_routes_to_the_source(self) -> None:
        for verdict in ("constant", "structure", "pool-layout", "frame-layout"):
            with self.subTest(verdict=verdict):
                self.assertEqual(routing_for(verdict, {}), ROUTING_STRUCTURAL)

    def test_a_mixed_verdict_routes_on_its_dominant_class(self) -> None:
        self.assertEqual(
            routing_for(
                "mixed(register:6, schedule:2)", {"register": 6, "schedule": 2}
            ),
            ROUTING_PERMUTER_FIRST,
        )
        self.assertEqual(
            routing_for(
                "mixed(constant:3, register:1)", {"constant": 3, "register": 1}
            ),
            ROUTING_STRUCTURAL,
        )

    def test_incomparable_inputs_route_to_the_import_before_anything_else(
        self,
    ) -> None:
        """A warning means the comparison answered a different question.

        Neither a lever nor a search is the next move when the two sides were
        not the same function to begin with.
        """

        self.assertEqual(
            routing_for("register-permutation", {}, ("selected a different symbol",)),
            ROUTING_IMPORT_FIX,
        )

    def test_an_exact_pair_routes_nowhere(self) -> None:
        self.assertEqual(routing_for("exact", {}), ROUTING_NONE)
        self.assertEqual(routing_for("words-identical", {}), ROUTING_NONE)

    def test_every_answer_is_one_of_the_declared_values(self) -> None:
        for verdict in (
            "exact",
            "allocation",
            "constant",
            "mixed(register:2)",
            "something-nobody-has-written-yet",
        ):
            self.assertIn(routing_for(verdict, {"register": 2}), ROUTING_VALUES)


class RoutedGuidanceTests(unittest.TestCase):
    def test_a_register_verdict_ends_by_naming_the_permuter(self) -> None:
        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
        )
        self.assertEqual(view.routing, ROUTING_PERMUTER_FIRST)
        self.assertIn(PERMUTER_ROUTING_SENTENCE, view.guidance)
        self.assertIn("permute-doctor", " ".join(view.guidance))
        # Last, because the levers above it are what to try first: the whole
        # routing block is the tail of the footer, in order.
        self.assertEqual(
            view.guidance[-len(PERMUTER_ROUTING_STEPS) :], PERMUTER_ROUTING_STEPS
        )

    def test_the_sentence_corrects_the_scope_of_the_claim(self) -> None:
        """`HAND` is the whole correction, so it is not decoration."""

        self.assertIn("HAND", PERMUTER_ROUTING_SENTENCE)
        self.assertIn("permuter target", PERMUTER_ROUTING_SENTENCE)
        self.assertIn("before concluding a wall", PERMUTER_ROUTING_SENTENCE)

    def test_a_constant_residual_is_not_sent_to_a_random_search(self) -> None:
        view = view_of(["li v0,33"], ["li v0,49"])
        self.assertEqual(view.routing, ROUTING_STRUCTURAL)
        self.assertNotIn(PERMUTER_ROUTING_SENTENCE, view.guidance)

    def test_an_exact_pair_is_not_sent_anywhere(self) -> None:
        view = view_of(["li v0,33"], ["li v0,33"])
        self.assertEqual(view.routing, ROUTING_NONE)
        self.assertNotIn(PERMUTER_ROUTING_SENTENCE, view.guidance)

    def test_the_screen_names_the_tool_beside_the_lever_family(self) -> None:
        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
        )
        header = next(line for line in render_view(view) if line.startswith("verdict:"))
        self.assertIn(f"routing={ROUTING_PERMUTER_FIRST}", header)

    def test_the_payload_carries_the_same_answer_as_the_screen(self) -> None:
        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
        )
        self.assertEqual(view.as_dict()["routing"], view.routing)


class DiagnosisRoutingTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_verdict_schema_carries_routing_additively(self) -> None:
        status, stdout, stderr = self.run_cli(
            [
                "diagnose-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--json",
            ]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-diagnosis-v2")
        self.assertEqual(payload["schema"], DIAGNOSIS_SCHEMA)
        self.assertEqual(payload["routing"], ROUTING_PERMUTER_FIRST)
        self.assertEqual(payload["view"]["routing"], ROUTING_PERMUTER_FIRST)
        # Additive: every v1 key a consumer read is still where it was.
        self.assertIn("comparison", payload)
        self.assertIn("view", payload)
        self.assertEqual(payload["view"]["verdict"], "phase-shift")

    def test_the_screen_routes_a_tie_instead_of_ending_it(self) -> None:
        status, stdout, _ = self.run_cli(
            [
                "diagnose-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--terse",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn(PERMUTER_ROUTING_SENTENCE, stdout)
        self.assertIn(f"routing={ROUTING_PERMUTER_FIRST}", stdout)

    def test_a_relocation_naming_a_different_symbol_routes_to_the_import(
        self,
    ) -> None:
        """The one thing the view cannot see, and the comparison can.

        A candidate that reads a different global is not a colouring outcome
        at all; sending it to a randomized search would be searching for a
        register assignment that was never the difference.
        """

        diagnosis = diagnose_dumps(
            FIXTURES / "phase-shift-target.objdump",
            FIXTURES / "phase-shift-candidate.objdump",
            symbol="animStep",
        )
        self.assertEqual(diagnosis.routing, ROUTING_PERMUTER_FIRST)
        disagreeing = dataclasses.replace(
            diagnosis,
            comparison=dataclasses.replace(
                diagnosis.comparison, relocation_symbol_mismatches=1
            ),
        )
        self.assertEqual(disagreeing.routing, ROUTING_IMPORT_FIX)
        self.assertEqual(disagreeing.as_dict()["routing"], ROUTING_IMPORT_FIX)
        # The view still reports the mechanism it measured; only the routing
        # changes, because only the routing is a claim about what to do next.
        self.assertEqual(disagreeing.view.routing, ROUTING_PERMUTER_FIRST)


if __name__ == "__main__":
    unittest.main()
