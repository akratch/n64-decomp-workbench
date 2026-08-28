"""A verdict names the mechanism; ownership names the pass and how close source gets.

`routing` said which tool a residual belongs to. It still did not say *why*,
and the three actionably-different cases behind one register verdict -- a
colourable tie a lever moves, a colour that is forbidden rather than
underpriced, and a decision the instrument does not expose -- demand opposite
responses. Operators were separating them by hand, one `CDX_FORCE` probe at a
time, on functions where the probe was always going to decline.

Two properties are held here. The answer must never be silently a guess: a
heuristic read from two disassemblies and a decision read out of a compiler
trace print differently and are labelled. And `pass-owned` must never read as
a wall -- it routes to the search like any other tie.
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
from decomp_workbench.globalcolor import parse_globalcolor_trace, pass_evidence
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.schema import VIEW_METRICS_BY_KEY
from decomp_workbench.view import (
    BASIS_HEURISTIC,
    BASIS_NONE,
    BASIS_TRACE,
    BASIS_VALUES,
    OWNING_PASS_CFE,
    OWNING_PASS_G0_SCHEDULER,
    OWNING_PASS_LOAD_FORM,
    OWNING_PASS_NONE,
    OWNING_PASS_STACK_HOME,
    OWNING_PASS_UGEN_RING,
    OWNING_PASS_UNKNOWN,
    OWNING_PASS_UOPT_COLOR,
    OWNING_PASS_VALUES,
    REACHABILITY_PASS_OWNED,
    REACHABILITY_PERMUTER,
    REACHABILITY_SOURCE,
    REACHABILITY_UNKNOWN,
    REACHABILITY_VALUES,
    ROUTING_IMPORT_FIX,
    ROUTING_PERMUTER_FIRST,
    ROUTING_STRUCTURAL,
    MechanismView,
    PassEvidence,
    build_view,
    ownership_for,
    routing_for,
)
from decomp_workbench.view_cli import render_view

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "fixtures"
PHASE_TARGET = str(FIXTURES / "phase-shift-target.objdump")
PHASE_CANDIDATE = str(FIXTURES / "phase-shift-candidate.objdump")

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]


def view_of(
    target: list[str],
    candidate: list[str],
    *,
    evidence: PassEvidence | None = None,
) -> MechanismView:
    target_text = assemble([*PROLOGUE, *target, *EPILOGUE], symbol=SYMBOL)
    candidate_text = assemble([*PROLOGUE, *candidate, *EPILOGUE], symbol=SYMBOL)
    return build_view(
        parse_disassembly(target_text, symbol=SYMBOL),
        parse_disassembly(candidate_text, symbol=SYMBOL),
        target_name="target.objdump",
        candidate_name="candidate.objdump",
        symbol=SYMBOL,
        evidence=evidence,
    )


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class VocabularyTests(unittest.TestCase):
    def test_every_answer_is_one_of_the_declared_values(self) -> None:
        cases: list[tuple[list[str], list[str]]] = [
            (["li v0,33"], ["li v0,33"]),
            (["li v0,33"], ["li v0,49"]),
            (["lw t8,0(s0)", "sw t8,4(s0)"], ["lw t6,0(s0)", "sw t6,4(s0)"]),
            (["sw v0,24(sp)"], ["sw v0,28(sp)"]),
            (["addu v0,a0,a1", "lw a2,0(s0)"], ["lw a2,0(s0)", "addu v0,a0,a1"]),
        ]
        for target, candidate in cases:
            with self.subTest(target=target):
                ownership = view_of(target, candidate).ownership
                self.assertIn(ownership.owning_pass, OWNING_PASS_VALUES)
                self.assertIn(ownership.reachability, REACHABILITY_VALUES)
                self.assertIn(ownership.basis, BASIS_VALUES)
                self.assertTrue(ownership.reason)

    def test_an_exact_pair_owns_nothing_and_says_so(self) -> None:
        ownership = view_of(["li v0,33"], ["li v0,33"]).ownership
        self.assertEqual(ownership.owning_pass, OWNING_PASS_NONE)
        self.assertEqual(ownership.basis, BASIS_NONE)
        # Nothing to say in a footer about a residual that does not exist.
        self.assertEqual(ownership.steps, ())

    def test_incomparable_inputs_settle_nothing(self) -> None:
        """A warning means the two sides answered different questions."""

        ownership = ownership_for(
            "register-permutation",
            rows=(),
            lanes=(),
            webs=(),
            warnings=("selected a different symbol",),
        )
        self.assertEqual(ownership.owning_pass, OWNING_PASS_UNKNOWN)
        self.assertEqual(ownership.reachability, REACHABILITY_UNKNOWN)
        self.assertEqual(ownership.basis, BASIS_NONE)


class HeuristicOwnershipTests(unittest.TestCase):
    """Each residual shape the workbench can already see, and its owner."""

    def test_a_moved_stack_offset_is_a_home_not_an_immediate(self) -> None:
        view = view_of(["sw v0,24(sp)"], ["sw v0,28(sp)"])
        self.assertEqual(view.owning_pass, OWNING_PASS_STACK_HOME)
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)
        self.assertIn("N(sp)", view.ownership.reason)

    def test_a_frame_size_pair_is_a_stack_home_residual(self) -> None:
        frame = ["sw ra,36(sp)", "lw ra,36(sp)"]
        view = build_view(
            parse_disassembly(
                assemble(
                    ["addiu sp,sp,-40", *frame, "addiu sp,sp,40", "jr ra", "nop"],
                    symbol=SYMBOL,
                ),
                symbol=SYMBOL,
            ),
            parse_disassembly(
                assemble(
                    ["addiu sp,sp,-56", *frame, "addiu sp,sp,56", "jr ra", "nop"],
                    symbol=SYMBOL,
                ),
                symbol=SYMBOL,
            ),
            target_name="target",
            candidate_name="candidate",
            symbol=SYMBOL,
        )
        self.assertEqual(view.verdict, "frame-layout")
        self.assertEqual(view.owning_pass, OWNING_PASS_STACK_HOME)
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)

    def test_a_pool_load_against_a_materialised_constant_is_a_load_form(
        self,
    ) -> None:
        view = view_of(["lwc1 f4,0(s0)"], ["lui a0,0x3f00"])
        self.assertEqual(view.owning_pass, OWNING_PASS_LOAD_FORM)
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)

    def test_a_pool_load_on_both_sides_is_not_a_load_form_difference(
        self,
    ) -> None:
        """One side must pool-load where the other materialises.

        Both sides loading from the pool, beside any row that happens to
        mention an `addiu`, is a register or schedule residual and not a
        question about a constant's value -- and answering it
        `rodata-load-form` sends the reader to audit a constant that was
        never wrong, and hides the pass that did decide it.
        """

        view = view_of(
            ["lwc1 f4,0(s0)", "addiu t0,t1,8"],
            ["lwc1 f6,0(s0)", "lw t2,0(sp)"],
        )
        self.assertNotEqual(view.owning_pass, OWNING_PASS_LOAD_FORM)

    def test_an_ordinary_constant_is_a_front_end_spelling(self) -> None:
        view = view_of(["li v0,33"], ["li v0,49"])
        self.assertEqual(view.owning_pass, OWNING_PASS_CFE)
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)

    def test_a_pure_reordering_belongs_to_the_scheduler(self) -> None:
        view = view_of(
            ["addu v0,a0,a1", "lw a2,0(s0)"],
            ["lw a2,0(s0)", "addu v0,a0,a1"],
        )
        self.assertEqual(view.verdict, "schedule")
        self.assertEqual(view.owning_pass, OWNING_PASS_G0_SCHEDULER)
        self.assertEqual(view.reachability, REACHABILITY_PERMUTER)

    def test_a_rotating_temp_lane_is_the_ring_and_source_reaches_it(self) -> None:
        """The shipped phase-shift fixture: one ring pop, not six decisions."""

        diagnosis = diagnose_dumps(
            FIXTURES / "phase-shift-target.objdump",
            FIXTURES / "phase-shift-candidate.objdump",
            symbol="animStep",
        )
        self.assertEqual(diagnosis.view.verdict, "phase-shift")
        self.assertEqual(diagnosis.ownership.owning_pass, OWNING_PASS_UGEN_RING)
        self.assertEqual(diagnosis.ownership.reachability, REACHABILITY_SOURCE)

    def test_a_colourable_substitution_belongs_to_the_colouring_pass(self) -> None:
        view = view_of(["move s0,s1"], ["move s0,s2"])
        self.assertEqual(view.owning_pass, OWNING_PASS_UOPT_COLOR)
        self.assertEqual(view.reachability, REACHABILITY_PERMUTER)

    def test_a_ring_only_target_with_no_rotation_is_pass_owned(self) -> None:
        """No colouring reaches a `t` register, and no phase explains it."""

        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
        )
        self.assertEqual(view.owning_pass, OWNING_PASS_UGEN_RING)
        self.assertEqual(view.reachability, REACHABILITY_PASS_OWNED)

    def test_a_heuristic_answer_is_labelled_a_heuristic(self) -> None:
        for target, candidate in (
            (["li v0,33"], ["li v0,49"]),
            (["sw v0,24(sp)"], ["sw v0,28(sp)"]),
            (["move s0,s1"], ["move s0,s2"]),
        ):
            with self.subTest(target=target):
                self.assertEqual(
                    view_of(target, candidate).ownership.basis, BASIS_HEURISTIC
                )


class TraceOwnershipTests(unittest.TestCase):
    """A trace turns the same question into a measurement, and says so."""

    def test_a_declined_force_is_a_measurement_not_a_guess(self) -> None:
        view = view_of(
            ["move s0,s1"],
            ["move s0,s2"],
            evidence=PassEvidence(force_declined=True),
        )
        self.assertEqual(view.ownership.basis, BASIS_TRACE)
        self.assertEqual(view.owning_pass, OWNING_PASS_UOPT_COLOR)
        self.assertEqual(view.reachability, REACHABILITY_PASS_OWNED)
        self.assertIn("taken, not underpriced", view.ownership.reason)

    def test_a_contested_allocation_says_the_register_was_taken(self) -> None:
        view = view_of(
            ["move s0,s1"],
            ["move s0,s2"],
            evidence=PassEvidence(contested_allocation=True),
        )
        self.assertEqual(view.ownership.basis, BASIS_TRACE)
        self.assertIn("regsleft=0", view.ownership.reason)

    def test_a_ring_pop_divergence_keeps_source_in_reach(self) -> None:
        """A pop has a source line, which is the whole value of the record."""

        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
            evidence=PassEvidence(ring_pop_divergence=True),
        )
        self.assertEqual(view.owning_pass, OWNING_PASS_UGEN_RING)
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)
        self.assertEqual(view.ownership.basis, BASIS_TRACE)

    def test_evidence_that_settles_nothing_leaves_the_heuristic_alone(self) -> None:
        view = view_of(["li v0,33"], ["li v0,49"], evidence=PassEvidence())
        self.assertEqual(view.ownership.basis, BASIS_HEURISTIC)
        self.assertEqual(view.owning_pass, OWNING_PASS_CFE)

    def test_a_globalcolor_trace_produces_the_evidence(self) -> None:
        """The bridge is real: the trace the workbench already parses.

        Without a producer, the `trace` basis would be a branch nothing ever
        takes -- which is the same as not having it.
        """

        trace = parse_globalcolor_trace(
            "[CDX] force_declined phase=p1 site=color proc=1 web=7 color=12\n"
        )
        evidence = pass_evidence(trace, proc=1, web=7)
        self.assertTrue(evidence.force_declined)
        self.assertTrue(evidence.decisive)
        # Scoped: another procedure's declined force is not this residual's.
        self.assertFalse(pass_evidence(trace, proc=2).decisive)


#: A hand-written trace, in the repository, exercising exactly the two facts
#: `pass_evidence` reads. Nothing about it came from a compiler or a ROM.
TRACE_FIXTURE = str(FIXTURES / "globalcolor-declined.log")


class TraceFlagTests(unittest.TestCase):
    """`--trace` is what makes `ownership_basis=trace` reachable at all.

    `pass_evidence` existed and was tested, and no command fed it: the
    measured basis was a branch a terminal could never take, which is the
    same as not having it. These tests are about the flag, not the parser.
    """

    def diagnose(self, *extra: str) -> tuple[int, str, str]:
        return run_cli(
            [
                "diagnose-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--terse",
                *extra,
            ]
        )

    def test_without_a_trace_the_same_residual_is_a_heuristic(self) -> None:
        status, stdout, stderr = self.diagnose()
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"ownership_basis={BASIS_HEURISTIC}", stdout)

    def test_a_scoped_trace_turns_the_verdict_into_a_measurement(self) -> None:
        status, stdout, stderr = self.diagnose(
            "--trace", TRACE_FIXTURE, "--trace-proc", "1", "--trace-web", "7"
        )
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"ownership_basis={BASIS_TRACE}", stdout)
        self.assertIn(f"owning_pass={OWNING_PASS_UOPT_COLOR}", stdout)
        self.assertIn(f"reachability={REACHABILITY_PASS_OWNED}", stdout)
        # The basis names the file it came from: a measurement with no
        # provenance is not reproducible.
        self.assertIn("globalcolor-declined.log", stdout)
        self.assertIn("proc=1, web=7", stdout)

    def test_a_trace_scoped_elsewhere_settles_nothing_and_says_so(self) -> None:
        """Silence here would read exactly like a run given no trace.

        The reader asked the trace this question. `heuristic` with no
        explanation invites reading the trace as having *agreed* with the
        heuristic, which it did not: it was never asked about this residual.
        """

        status, stdout, stderr = self.diagnose(
            "--trace", TRACE_FIXTURE, "--trace-proc", "2"
        )
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"ownership_basis={BASIS_HEURISTIC}", stdout)
        self.assertIn("holds no declined force", stdout)
        self.assertIn("--trace-proc", stdout)

    def test_the_measured_basis_reaches_json_too(self) -> None:
        status, stdout, stderr = run_cli(
            [
                "diagnose-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--json",
                "--trace",
                TRACE_FIXTURE,
                "--trace-proc",
                "1",
                "--trace-web",
                "7",
            ]
        )
        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["ownership_basis"], BASIS_TRACE)
        self.assertEqual(payload["owning_pass"], OWNING_PASS_UOPT_COLOR)
        self.assertIn("globalcolor-declined.log", " ".join(payload["view"]["next"]))

    def test_a_missing_trace_is_a_usage_error_not_a_silent_heuristic(self) -> None:
        status, _, stderr = self.diagnose("--trace", str(FIXTURES / "absent.trace"))
        self.assertEqual(status, 2)
        self.assertIn("absent.trace", stderr)


class RoutingTests(unittest.TestCase):
    """`pass-owned` is a statement about the levers, never about the function."""

    def test_a_pass_owned_residual_still_routes_to_the_search(self) -> None:
        self.assertEqual(
            routing_for("constant", {"constant": 3}, (), REACHABILITY_PASS_OWNED),
            ROUTING_PERMUTER_FIRST,
        )

    def test_a_pass_owned_residual_carries_the_routing_sentence(self) -> None:
        view = view_of(
            ["lw t8,0(s0)", "sw t8,4(s0)"],
            ["lw t6,0(s0)", "sw t6,4(s0)"],
        )
        self.assertEqual(view.reachability, REACHABILITY_PASS_OWNED)
        self.assertEqual(view.routing, ROUTING_PERMUTER_FIRST)
        footer = " ".join(view.guidance)
        self.assertIn("permute-doctor", footer)
        self.assertIn("NOT a wall", footer)

    def test_incomparable_inputs_still_outrank_ownership(self) -> None:
        self.assertEqual(
            routing_for(
                "constant",
                {"constant": 1},
                ("selected a different symbol",),
                REACHABILITY_PASS_OWNED,
            ),
            ROUTING_IMPORT_FIX,
        )

    def test_a_source_reachable_residual_is_not_sent_to_a_search(self) -> None:
        view = view_of(["li v0,33"], ["li v0,49"])
        self.assertEqual(view.reachability, REACHABILITY_SOURCE)
        self.assertEqual(view.routing, ROUTING_STRUCTURAL)


class FooterTests(unittest.TestCase):
    def test_the_footer_names_the_pass_before_the_levers(self) -> None:
        view = view_of(["sw v0,24(sp)"], ["sw v0,28(sp)"])
        guidance = list(view.guidance)
        owning = next(
            index for index, line in enumerate(guidance) if line.startswith("owning ")
        )
        levers = next(
            index
            for index, line in enumerate(guidance)
            if line.startswith("field guide levers")
        )
        self.assertLess(owning, levers)
        self.assertTrue(guidance[owning + 1].startswith("reachability: "))

    def test_the_footer_points_a_residual_at_its_law(self) -> None:
        """A stack-home residual owes the reader L63, as a command."""

        view = view_of(["sw v0,24(sp)"], ["sw v0,28(sp)"])
        footer = " ".join(view.guidance)
        self.assertIn("law L63:", footer)
        self.assertIn("decomp-workbench guide laws ido53 L63", footer)


class ScreenAndPayloadTests(unittest.TestCase):
    def test_the_screen_prints_all_three_fields(self) -> None:
        view = view_of(["sw v0,24(sp)"], ["sw v0,28(sp)"])
        line = next(
            item for item in render_view(view) if item.startswith("ownership: ")
        )
        self.assertIn(f"owning_pass={OWNING_PASS_STACK_HOME}", line)
        self.assertIn(f"reachability={REACHABILITY_SOURCE}", line)
        self.assertIn(f"ownership_basis={BASIS_HEURISTIC}", line)

    def test_the_payload_says_what_the_screen_says(self) -> None:
        view = view_of(["sw v0,24(sp)"], ["sw v0,28(sp)"])
        payload = view.as_dict()
        self.assertEqual(payload["owning_pass"], view.owning_pass)
        self.assertEqual(payload["reachability"], view.reachability)
        self.assertEqual(payload["ownership_basis"], view.ownership.basis)

    def test_every_new_key_is_registered_with_an_explanation(self) -> None:
        for key in ("owning_pass", "reachability", "ownership_basis"):
            with self.subTest(key=key):
                self.assertIn(key, VIEW_METRICS_BY_KEY)


class DiagnosisTests(unittest.TestCase):
    def test_the_schema_bump_is_additive(self) -> None:
        status, stdout, stderr = run_cli(
            [
                "diagnose-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--json",
            ]
        )
        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-diagnosis-v3")
        self.assertEqual(payload["schema"], DIAGNOSIS_SCHEMA)
        self.assertEqual(payload["owning_pass"], OWNING_PASS_UGEN_RING)
        self.assertEqual(payload["reachability"], REACHABILITY_SOURCE)
        self.assertEqual(payload["ownership_basis"], BASIS_HEURISTIC)
        # Additive: every key an older consumer read is still where it was.
        for key in ("comparison", "view", "routing"):
            self.assertIn(key, payload)
        self.assertEqual(payload["view"]["verdict"], "phase-shift")
        self.assertEqual(payload["view"]["owning_pass"], payload["owning_pass"])

    def test_the_screen_carries_the_line(self) -> None:
        status, stdout, _ = run_cli(
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
        self.assertIn(f"owning_pass={OWNING_PASS_UGEN_RING}", stdout)
        self.assertIn(f"reachability={REACHABILITY_SOURCE}", stdout)

    def test_a_relocation_naming_another_symbol_has_no_owning_pass(self) -> None:
        """The one correction the comparison can make and the view cannot.

        A candidate reading a different global is not a colouring outcome, and
        attributing it to the colourer would invent a decision nobody took.
        """

        diagnosis = diagnose_dumps(
            FIXTURES / "phase-shift-target.objdump",
            FIXTURES / "phase-shift-candidate.objdump",
            symbol="animStep",
        )
        disagreeing = dataclasses.replace(
            diagnosis,
            comparison=dataclasses.replace(
                diagnosis.comparison, relocation_symbol_mismatches=1
            ),
        )
        self.assertEqual(disagreeing.ownership.owning_pass, OWNING_PASS_UNKNOWN)
        self.assertEqual(disagreeing.ownership.reachability, REACHABILITY_UNKNOWN)
        self.assertEqual(disagreeing.routing, ROUTING_IMPORT_FIX)
        self.assertEqual(disagreeing.as_dict()["owning_pass"], OWNING_PASS_UNKNOWN)
        # The view still reports the mechanism it measured.
        self.assertEqual(disagreeing.view.owning_pass, OWNING_PASS_UGEN_RING)


if __name__ == "__main__":
    unittest.main()
