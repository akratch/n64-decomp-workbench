"""Tests for the lever diagnosis: the edit a residual's evidence supports.

The property under test throughout is the honesty rule. A class named without
its deciding evidence must leave `edit_family` empty and name the capture
command instead, because the failure this module exists to prevent is a
plausible edit family read off a residual's shape -- which is how
`overlay40UpdateEntries` acquired an "unreachable by statement placement"
verdict a trace overturned the same day.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.as1_reorganize import Selection, parse_as1_reorganize_trace
from decomp_workbench.cascade import CdxLog
from decomp_workbench.cli import main
from decomp_workbench.emit_provenance import parse_emit_trace
from decomp_workbench.field_guide import PASS_LAWS
from decomp_workbench.frame_ladder import frame_ladder
from decomp_workbench.levers import (
    LEVER_CLASS_VALUES,
    LEVER_LINE_ORDER,
    LEVER_NONE_KNOWN,
    LEVER_POOL_POPULATION,
    LEVER_POOL_ROTATION,
    LEVER_SCHEMA,
    LEVER_STACK_HOME,
    LEVER_TEMP_RING,
    LEVER_UNREACHABLE,
    LINE_ORDER_FAMILIES,
    STACK_HOME_FAMILIES,
    STACK_HOME_RANKING,
    TEMP_RING_FAMILIES,
    UNREACHABLE_PROOFS,
    classify_construct,
    force_reachability,
    format_lever,
    lever_for,
    pops_by_line,
    readiness_keys,
    sweep_records,
    tie_groups,
)
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.trace import parse_trace
from decomp_workbench.view import MechanismView, Web, build_view

ROOT = Path(__file__).resolve().parents[1]

#: A one-word displaced stack home with equal frames: the shape
#: `func_overlay_026_F0000B18_187AF10` presented, where the target spilled one
#: slot above the candidate at an identical instruction count.
HOME_TARGET = """
00000000 <demo>:
   0: 27bdffd0  addiu $sp,$sp,-48
   4: afbf0014  sw $ra,20($sp)
   8: afa2001c  sw $v0,28($sp)
   c: 8fa2001c  lw $v0,28($sp)
  10: 03e00008  jr $ra
  14: 27bd0030  addiu $sp,$sp,48
"""

HOME_CANDIDATE = """
00000000 <demo>:
   0: 27bdffd0  addiu $sp,$sp,-48
   4: afbf0014  sw $ra,20($sp)
   8: afa20018  sw $v0,24($sp)
   c: 8fa20018  lw $v0,24($sp)
  10: 03e00008  jr $ra
  14: 27bd0030  addiu $sp,$sp,48
"""

#: The same function with one declared local too many: the candidate's frame
#: is a quantum larger, which is a *count* and not a position.
FRAME_TARGET = HOME_TARGET
FRAME_CANDIDATE = """
00000000 <demo>:
   0: 27bdffc8  addiu $sp,$sp,-56
   4: afbf0014  sw $ra,20($sp)
   8: afa2001c  sw $v0,28($sp)
   c: 8fa2001c  lw $v0,28($sp)
  10: 03e00008  jr $ra
  14: 27bd0038  addiu $sp,$sp,56
"""

#: Free-list records as `instrument-ugen`'s hooks emit them, with ugen's own
#: current source line. Line 42 consumes two pops; every other line consumes
#: one. That is the phantom pop, and the line is the statement to edit.
RING_TRACE = """\
DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=14 line=41 emitted=10
DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=15 line=42 emitted=11
DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=24 line=42 emitted=12
DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=25 line=43 emitted=13
DKWB-FREELIST REMOVE proc=3 reg=8 line=43 emitted=13
"""

#: The `overlay40UpdateEntries` preheader shape: a loop-count initialiser at
#: line 45 emitted before the loop-invariant address ugen stamps with the loop
#: header's line 46.
EMIT_TRACE = """\
DKWB-EMIT-V1 proc=0 block=0 emit=4 op=28 line=45 buffer=fwd fn=f_emit_dir2
DKWB-EMIT-V1 proc=0 block=0 emit=5 op=41 line=45 buffer=fwd fn=f_emit_ri_
DKWB-EMIT-V1 proc=0 block=0 emit=7 op=36 line=46 buffer=fwd fn=f_emit_ra
"""


def view_for(target: str, candidate: str, **kwargs: object) -> MechanismView:
    return build_view(
        parse_disassembly(target),
        parse_disassembly(candidate),
        target_name="target",
        candidate_name="candidate",
        symbol="demo",
        **kwargs,  # type: ignore[arg-type]
    )


class StackHomeLeverTests(unittest.TestCase):
    def test_a_displaced_home_at_an_equal_frame_names_the_carrier_edit(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        self.assertEqual(lever.lever_class, LEVER_STACK_HOME)
        self.assertIsNotNone(lever.family)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "reuse-an-existing-local-as-carrier")
        self.assertEqual(lever.measurements["frame_delta"], 0)
        self.assertTrue(lever.measurements["instruction_counts_agree"])

    def test_a_larger_candidate_frame_names_the_drop_edit(self) -> None:
        lever = lever_for(view_for(FRAME_TARGET, FRAME_CANDIDATE))
        self.assertEqual(lever.lever_class, LEVER_STACK_HOME)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "drop-a-declared-local")
        self.assertEqual(lever.measurements["frame_delta"], 8)
        self.assertEqual(lever.measurements["frame_delta_words"], 2)

    def test_one_home_referenced_twice_is_one_home_not_two(self) -> None:
        # Store plus reload is two rows and one slot. Counting rows here
        # picks the pair-reorder family for a residual that is one carrier.
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        self.assertEqual(lever.measurements["displaced_home_rows"], 2)
        self.assertEqual(lever.measurements["displaced_homes"], 1)

    def test_the_declared_local_count_is_absent_until_a_ladder_is_read(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        self.assertIsNone(lever.measurements["declared_locals"])
        self.assertTrue(any("CDX_SYMTAB=1" in item for item in lever.needs))

    def test_a_ladder_supplies_the_declared_local_count(self) -> None:
        log = CdxLog(
            (ROOT / "examples" / "traces" / "frame-ladder.log").read_text(
                encoding="utf-8"
            ),
            name="frame-ladder.log",
        )
        ladder = frame_ladder(log, frame=-216)
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE), ladder=ladder)
        self.assertEqual(lever.measurements["declared_locals"], len(ladder.named))
        self.assertFalse(any("CDX_SYMTAB=1" in item for item in lever.needs))

    def test_the_reservation_law_is_stated_with_its_measurement(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        joined = " ".join(lever.evidence)
        self.assertIn("register-coloured", joined)
        self.assertIn("rounds up to 8", joined)

    def test_every_family_is_offered_exactly_once(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        assert lever.family is not None
        names = {lever.family.name, *(item.name for item in lever.alternatives)}
        self.assertEqual(names, {item.name for item in STACK_HOME_FAMILIES})


class TempRingLeverTests(unittest.TestCase):
    def rotation_view(self) -> MechanismView:
        return view_for(
            (ROOT / "examples" / "fixtures" / "phase-shift-target.objdump").read_text(
                encoding="utf-8"
            ),
            (
                ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
            ).read_text(encoding="utf-8"),
        )

    def test_a_rotation_without_a_trace_refuses_to_name_a_family(self) -> None:
        lever = lever_for(self.rotation_view())
        self.assertEqual(lever.lever_class, LEVER_TEMP_RING)
        self.assertIsNone(lever.family)
        self.assertTrue(any("DKWB_UGEN_TRACE=1" in item for item in lever.needs))
        self.assertEqual(
            {item.name for item in lever.alternatives},
            {item.name for item in TEMP_RING_FAMILIES},
        )

    def test_a_ring_trace_reports_pops_per_source_line(self) -> None:
        lever = lever_for(
            self.rotation_view(), ring_events=parse_trace(RING_TRACE), proc=3
        )
        self.assertEqual(lever.lever_class, LEVER_TEMP_RING)
        self.assertEqual(
            lever.measurements["pops_by_line"], {"41": 1, "42": 2, "43": 1}
        )
        self.assertEqual(lever.measurements["pop_total"], 4)
        self.assertIn("42", " ".join(lever.evidence))

    def test_the_ring_order_is_reported_by_register_name(self) -> None:
        lever = lever_for(
            self.rotation_view(), ring_events=parse_trace(RING_TRACE), proc=3
        )
        self.assertEqual(lever.measurements["ring_order"], ["t6", "t7", "t8", "t9"])

    def test_the_two_pop_rule_is_always_stated(self) -> None:
        lever = lever_for(
            self.rotation_view(), ring_events=parse_trace(RING_TRACE), proc=3
        )
        self.assertIn("two pops off means two of these", " ".join(lever.evidence))

    def test_a_procedure_scope_excludes_other_procedures(self) -> None:
        events = parse_trace(RING_TRACE)
        self.assertEqual(pops_by_line(events, proc=4), {})
        self.assertEqual(pops_by_line(events, proc=3), {41: 1, 42: 2, 43: 1})


class LineOrderLeverTests(unittest.TestCase):
    def schedule_view(self) -> MechanismView:
        return view_for(
            (ROOT / "examples" / "fixtures" / "loc-boundary-target.objdump").read_text(
                encoding="utf-8"
            ),
            (
                ROOT / "examples" / "fixtures" / "loc-boundary-candidate.objdump"
            ).read_text(encoding="utf-8"),
        )

    def test_an_emit_trace_names_the_join_and_the_conflicting_pair(self) -> None:
        events, _ = parse_emit_trace(EMIT_TRACE)
        lever = lever_for(self.schedule_view(), emit_events=events)
        self.assertEqual(lever.lever_class, LEVER_LINE_ORDER)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "join-the-initialiser-to-the-loop-header")
        self.assertEqual(lever.measurements["line_order_conflicts"], 1)
        self.assertIn("line 45", " ".join(lever.evidence))

    def test_the_birth_order_family_is_the_stated_alternative(self) -> None:
        events, _ = parse_emit_trace(EMIT_TRACE)
        lever = lever_for(self.schedule_view(), emit_events=events)
        self.assertEqual(
            [item.name for item in lever.alternatives],
            [LINE_ORDER_FAMILIES[1].name],
        )

    def test_an_emit_trace_with_no_conflict_is_none_known_not_a_guess(self) -> None:
        events, _ = parse_emit_trace(
            "DKWB-EMIT-V1 proc=0 block=0 emit=5 op=41 line=46 buffer=fwd "
            "fn=f_emit_ri_\n"
            "DKWB-EMIT-V1 proc=0 block=0 emit=7 op=36 line=46 buffer=fwd "
            "fn=f_emit_ra\n"
        )
        lever = lever_for(self.schedule_view(), emit_events=events)
        self.assertEqual(lever.lever_class, LEVER_NONE_KNOWN)
        self.assertIsNone(lever.family)
        self.assertIn("nothing here is separated by a line stamp", lever.reason)


class As1ReadinessTests(unittest.TestCase):
    def selections(self) -> list[Selection]:
        text = (ROOT / "examples" / "traces" / "as1-reorganize.log").read_text(
            encoding="utf-8"
        )
        selections, _events, _ignored = parse_as1_reorganize_trace(text)
        return selections

    def test_the_deciding_key_tally_is_reported(self) -> None:
        tally = readiness_keys(self.selections())
        self.assertTrue(tally)
        self.assertEqual(sum(tally.values()), len(self.selections()))

    def test_a_readiness_decided_block_is_unreachable_with_its_proof(self) -> None:
        selections = [item for item in self.selections() if item.tie in {"start-time"}]
        if not selections:  # pragma: no cover - fixture guard
            self.skipTest("fixture holds no start-time decision")
        lever = lever_for(
            view_for(HOME_TARGET, HOME_CANDIDATE), as1_selections=selections
        )
        self.assertEqual(lever.lever_class, LEVER_UNREACHABLE)
        assert lever.unreachable is not None
        self.assertEqual(lever.unreachable.name, "as1-readiness")
        self.assertIn("leftover", lever.unreachable.proof)
        self.assertIn("besttime", lever.unreachable.reopens_when)

    def test_a_line_decided_block_is_the_line_lever_not_a_wall(self) -> None:
        selections = [item for item in self.selections() if item.tie == "lineno"]
        if not selections:  # pragma: no cover - fixture guard
            self.skipTest("fixture holds no lineno decision")
        lever = lever_for(
            view_for(HOME_TARGET, HOME_CANDIDATE), as1_selections=selections
        )
        self.assertEqual(lever.lever_class, LEVER_LINE_ORDER)

    def test_the_as1_trace_outranks_the_frame_reading(self) -> None:
        # The frame pair here would otherwise classify stack-home. A measured
        # selection key is stronger evidence than a shape, so it wins.
        selections = [item for item in self.selections() if item.tie in {"start-time"}]
        if not selections:  # pragma: no cover - fixture guard
            self.skipTest("fixture holds no start-time decision")
        lever = lever_for(
            view_for(FRAME_TARGET, FRAME_CANDIDATE), as1_selections=selections
        )
        self.assertEqual(lever.lever_class, LEVER_UNREACHABLE)


class CatalogueTests(unittest.TestCase):
    def test_every_proof_names_its_function_and_what_reopens_it(self) -> None:
        for name, proof in UNREACHABLE_PROOFS.items():
            with self.subTest(proof=name):
                self.assertEqual(proof.name, name)
                self.assertTrue(proof.proof.strip())
                self.assertTrue(proof.citation.strip())
                self.assertTrue(proof.reopens_when.strip())

    def test_the_four_proven_classes_are_all_present(self) -> None:
        self.assertEqual(
            set(UNREACHABLE_PROOFS),
            {
                "as1-readiness",
                "uopt-address-folding",
                "uopt-coalescing-tie-break",
                "cfe-pointer-add-order",
            },
        )

    def test_every_family_cites_a_function_and_a_date(self) -> None:
        for family in (
            *STACK_HOME_FAMILIES,
            *TEMP_RING_FAMILIES,
            *LINE_ORDER_FAMILIES,
        ):
            with self.subTest(family=family.name):
                self.assertIn("2026-09-0", family.citation)
                self.assertTrue(family.discriminator.strip())


class RenderingTests(unittest.TestCase):
    def test_the_block_prints_the_class_the_edit_and_the_receipt(self) -> None:
        lines = format_lever(lever_for(view_for(HOME_TARGET, HOME_CANDIDATE)))
        self.assertTrue(lines[0].startswith("lever: stack-home --"))
        self.assertTrue(any(item.startswith("  edit (") for item in lines))
        self.assertTrue(any(item.startswith("  proved on: ") for item in lines))

    def test_a_missing_trace_prints_the_capture_command(self) -> None:
        lines = format_lever(
            lever_for(
                view_for(
                    (
                        ROOT / "examples" / "fixtures" / "phase-shift-target.objdump"
                    ).read_text(encoding="utf-8"),
                    (
                        ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
                    ).read_text(encoding="utf-8"),
                )
            )
        )
        self.assertTrue(any(item.startswith("  capture: ") for item in lines))

    def test_the_payload_is_json_shaped_and_names_its_own_schema(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        payload = lever.as_dict()
        self.assertEqual(
            set(payload),
            {
                "lever_class",
                "reason",
                "reachability",
                "edit_family",
                "edit",
                "citation",
                "evidence",
                "needs",
                "measurements",
                "alternatives",
                "see_also",
                "unreachable",
            },
        )
        self.assertNotIn("schema", payload)
        self.assertEqual(LEVER_SCHEMA, "decomp-workbench-lever-v1")

    def test_every_class_keeps_the_documented_nullability(self) -> None:
        """`docs/json-contracts.md` states four invariants. Hold every one.

        The contract is what a consumer switches on, so the cases are
        enumerated rather than sampled: a lever with a family, one with none
        because its trace is absent, one that ruled the edit out, and one that
        found nothing to say.
        """

        ring = view_for(
            (ROOT / "examples" / "fixtures" / "phase-shift-target.objdump").read_text(
                encoding="utf-8"
            ),
            (
                ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
            ).read_text(encoding="utf-8"),
        )
        selections, _events, _ignored = parse_as1_reorganize_trace(
            (ROOT / "examples" / "traces" / "as1-reorganize.log").read_text(
                encoding="utf-8"
            )
        )
        readiness = [item for item in selections if item.tie == "start-time"]
        levers = [
            lever_for(view_for(HOME_TARGET, HOME_CANDIDATE)),
            lever_for(ring),
            lever_for(ring, ring_events=parse_trace(RING_TRACE), proc=3),
            lever_for(ring, as1_selections=readiness),
        ]
        for lever in levers:
            payload = lever.as_dict()
            with self.subTest(lever_class=payload["lever_class"]):
                self.assertIn(payload["lever_class"], LEVER_CLASS_VALUES)
                # `edit`/`citation` travel with `edit_family` or not at all.
                named = payload["edit_family"] is not None
                self.assertEqual(named, payload["edit"] is not None)
                self.assertEqual(named, payload["citation"] is not None)
                # `unreachable` is present exactly for the unreachable class.
                self.assertEqual(
                    payload["unreachable"] is not None,
                    payload["lever_class"] == LEVER_UNREACHABLE,
                )
                # A ruled-out residual never also names an edit.
                if payload["lever_class"] == LEVER_UNREACHABLE:
                    self.assertIsNone(payload["edit_family"])
                # `see_also` is a pointer, never a diagnosis: it appears only
                # where nothing was named.
                if payload["see_also"]:
                    self.assertIsNone(payload["edit_family"])
                    self.assertIsNone(payload["unreachable"])

    def test_only_stack_home_names_a_family_while_needs_is_non_empty(self) -> None:
        """The one exception the contract has to spell out.

        A stack-home family is picked from the frame pair, which every
        disassembly carries, so `--ladder` corroborates a named family rather
        than producing one. Every other class reads its family from a trace,
        and says `edit_family: null` until it has one.
        """

        stack_home = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        self.assertIsNotNone(stack_home.family)
        self.assertTrue(stack_home.needs)

        untraced = lever_for(
            view_for(
                (
                    ROOT / "examples" / "fixtures" / "phase-shift-target.objdump"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
                ).read_text(encoding="utf-8"),
            )
        )
        self.assertEqual(untraced.lever_class, LEVER_TEMP_RING)
        self.assertIsNone(untraced.family)
        self.assertTrue(untraced.needs)


class DiagnoseCommandTests(unittest.TestCase):
    """The block on the screen and in the payload, from the real command."""

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def dumps(self, root: Path) -> tuple[Path, Path]:
        target = root / "target.objdump"
        candidate = root / "candidate.objdump"
        target.write_text(HOME_TARGET, encoding="utf-8")
        candidate.write_text(HOME_CANDIDATE, encoding="utf-8")
        return target, candidate

    def test_the_screen_carries_the_lever_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, candidate = self.dumps(Path(directory))
            status, stdout, _ = self.run_cli(
                ["diagnose-dumps", str(target), str(candidate), "--function", "demo"]
            )
        self.assertEqual(status, 0)
        self.assertIn("lever: stack-home", stdout)
        self.assertIn("proved on: ", stdout)

    def test_the_payload_namespaces_the_block_and_its_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, candidate = self.dumps(Path(directory))
            _status, stdout, _ = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-diagnosis-v3")
        self.assertEqual(payload["lever_schema"], LEVER_SCHEMA)
        self.assertEqual(payload["lever"]["lever_class"], LEVER_STACK_HOME)

    def test_an_exact_comparison_gets_no_block_because_it_has_no_residual(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.objdump"
            target.write_text(HOME_TARGET, encoding="utf-8")
            _status, stdout, _ = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(target),
                    "--function",
                    "demo",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertNotIn("lever", payload)
        self.assertNotIn("lever_schema", payload)

    def test_a_ring_trace_reaches_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.objdump"
            candidate = root / "candidate.objdump"
            target.write_text(
                (
                    ROOT / "examples" / "fixtures" / "phase-shift-target.objdump"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            candidate.write_text(
                (
                    ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
                ).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            trace = root / "ring.log"
            trace.write_text(RING_TRACE, encoding="utf-8")
            _status, stdout, _ = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "animStep",
                    "--ring-trace",
                    str(trace),
                    "--lever-proc",
                    "3",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual(
            payload["lever"]["measurements"]["pops_by_line"],
            {"41": 1, "42": 2, "43": 1},
        )
        # A trace alone names the line and not the rule: the construct on it
        # is what says which pop-cost law applies, so the block asks for the
        # source rather than naming the nearest family.
        self.assertIsNone(payload["lever"]["edit_family"])
        self.assertTrue(any("--source" in item for item in payload["lever"]["needs"]))

    def test_an_unreadable_trace_is_an_error_document_not_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, candidate = self.dumps(Path(directory))
            status, _stdout, stderr = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--emit-trace",
                    str(Path(directory) / "missing.log"),
                ]
            )
        self.assertEqual(status, 2)
        self.assertTrue(stderr.startswith("error: "))


class LawCitationTests(unittest.TestCase):
    """Every lever family and proof has a law on the page behind it.

    A family with no law leaves the reader to re-derive the mechanism, which
    is what the whole overlay cohort did before contributing L72-L82.
    """

    def laws(self) -> str:
        return (ROOT / "docs" / "compiler-laws" / "ido-5.3.md").read_text(
            encoding="utf-8"
        )

    def test_the_new_laws_are_on_the_page(self) -> None:
        text = self.laws()
        for law in range(72, 83):
            with self.subTest(law=law):
                self.assertIn(f"### L{law}.", text)

    def test_every_function_a_family_cites_appears_in_a_law(self) -> None:
        text = self.laws()
        functions = {
            "overlay34InitStorage",
            "func_overlay_026_F0000B18_187AF10",
            "overlay84InitializeAndUpdate",
            "overlay20UpdateObjectResource",
            "func_overlay_070_F00000D8",
            "overlay40UpdateEntries",
            "func_overlay_047_F00009D0",
            "func_overlay_014_F0000000",
        }
        for name in functions:
            with self.subTest(function=name):
                self.assertIn(name, text)

    def test_every_unreachable_proof_has_its_law(self) -> None:
        text = self.laws()
        for name in (
            "overlay1FindNextAngle",
            "func_overlay_038_F0000000",
            "overlay59PrepareEntry",
            "levelFreeAll",
        ):
            with self.subTest(function=name):
                self.assertIn(name, text)

    def test_the_pass_law_table_reaches_the_new_laws(self) -> None:
        cited = {
            law for entries in PASS_LAWS.values() for _era, law, _summary in entries
        }
        self.assertTrue({"L72", "L73", "L76", "L77", "L79", "L80"} <= cited)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


#: Two caller-saved decisions, in the shape `overlay43FilterImage` and
#: `overlay60ReassignChoiceSlots` recorded: p2 visits in ascending web number,
#: every `bestcost` is zero, and the saves are wildly unequal and inert. Web 9
#: is a `type=4` expression web -- the synthetic intermediate of a narrowing
#: cast, which is the shape the one measured renumbering spelling was
#: measured on.
P2_LOG = """\
[CDX] webdetail phase=p2 proc=0 role=target web=6 sym=6 type=3 dtype=6 \
table=1 chain=1 exprtable=1 exprchain=1 bb=1 line=9 raw10=0x00000000 \
raw14=0x00000000 raw18=0x00000000 raw20=0x00000000
[CDX] p2dec phase=p2 proc=0 web=6 sym=6 class=1 save=560.500000 nocs=1 \
totalsave=560.500000 bestcost=0.000000 bestcolor=1 bestreg=v0 \
forbidden0=0x00000000 forbidden1=0x00000000 regsleft=9 numintf=4 \
available0=0x7ffc0000 available1=0x00000000 allcallersave=0 taken1=-1 \
taken2=-1 decision=color forced=-2
[CDX] p2color phase=p2 proc=0 web=6 sym=6 color=1 reg=v0 forced=-2
[CDX] webdetail phase=p2 proc=0 role=target web=9 sym=0 type=4 dtype=6 \
table=2 chain=1 exprtable=2 exprchain=1 bb=4 line=9 raw10=0x00000000 \
raw14=0x00000000 raw18=0x00000000 raw20=0x00000000
[CDX] p2dec phase=p2 proc=0 web=9 sym=0 class=1 save=3.700000 nocs=1 \
totalsave=3.700000 bestcost=0.000000 bestcolor=2 bestreg=v1 \
forbidden0=0x00000000 forbidden1=0x00000000 regsleft=8 numintf=4 \
available0=0x7ffc0000 available1=0x00000000 allcallersave=0 taken1=-1 \
taken2=-1 decision=color forced=-2
[CDX] p2color phase=p2 proc=0 web=9 sym=0 color=2 reg=v1 forced=-2
"""

#: The callee-saved sweep, in the shape `overlay4UpdateObjectMotion` recorded:
#: one web at save 7.0 taken first, then a tie group at save 1.5 whose members
#: are ordered by web number alone.
P1_TIED_LOG = """\
[CDX] webdetail phase=p1 proc=1 role=target web=48 sym=0 type=4 dtype=6 \
table=1 chain=1 exprtable=1 exprchain=1 bb=6 line=81 raw10=0x00000000 \
raw14=0x00000000 raw18=0x00000000 raw20=0x00000000
[CDX] p1dec phase=p1 proc=1 web=48 sym=0 class=1 save=1.500000 nocs=2 \
totalsave=3.000000 bestcost=0.000000 bestcolor=1 bestreg=v0 \
forbidden0=0x00038000 forbidden1=0x00000000 regsleft=9 numintf=4 \
available0=0x7ffc0000 available1=0x00000000 allcallersave=0 taken1=-1 \
taken2=-1 decision=color forced=-2
[CDX] p1color phase=p1 proc=1 web=48 sym=0 color=1 reg=v0 forced=-2
[CDX] webdetail phase=p1 proc=1 role=target web=50 sym=71 type=3 dtype=6 \
table=2 chain=1 exprtable=2 exprchain=1 bb=6 line=81 raw10=0x00000000 \
raw14=0x00000000 raw18=0x00000000 raw20=0x00000000
[CDX] p1dec phase=p1 proc=1 web=50 sym=71 class=1 save=1.500000 nocs=2 \
totalsave=3.000000 bestcost=0.000000 bestcolor=2 bestreg=v1 \
forbidden0=0x00038000 forbidden1=0x00000000 regsleft=8 numintf=4 \
available0=0x7ffc0000 available1=0x00000000 allcallersave=0 taken1=-1 \
taken2=-1 decision=color forced=-2
[CDX] p1color phase=p1 proc=1 web=50 sym=71 color=2 reg=v1 forced=-2
[CDX] webdetail phase=p1 proc=1 role=target web=146 sym=12 type=3 dtype=6 \
table=3 chain=1 exprtable=3 exprchain=1 bb=1 line=81 raw10=0x00000000 \
raw14=0x00000000 raw18=0x00000000 raw20=0x00000000
[CDX] p1dec phase=p1 proc=1 web=146 sym=12 class=1 save=7.000000 nocs=2 \
totalsave=14.000000 bestcost=0.000000 bestcolor=14 bestreg=s0 \
forbidden0=0x00000000 forbidden1=0x00000000 regsleft=9 numintf=9 \
available0=0x7ffc0000 available1=0x00000000 allcallersave=0 taken1=-1 \
taken2=-1 decision=color forced=-2
[CDX] p1color phase=p1 proc=1 web=146 sym=12 color=14 reg=s0 forced=-2
"""

#: The same p1 pair with the saves separated, which is what puts a rotation
#: out of numbering's reach: p1 takes the larger save first whatever the web
#: numbers are.
P1_UNTIED_LOG = P1_TIED_LOG.replace(
    "web=50 sym=71 class=1 save=1.500000", "web=50 sym=71 class=1 save=4.000000"
)

#: A recorded force run: `overlay4UpdateObjectMotion` went to words=0 under
#: three pinned colours, which is the complete reachability proof.
FORCE_PROVEN = {
    "schema": "decomp-workbench-oracle-sweep-v1",
    "baseline": {
        "force": None,
        "comparison": {"words": 8, "candidate_instructions": 96},
    },
    "results": [
        {
            "force": "p1:w13=c2",
            "comparison": {"words": 5, "candidate_instructions": 96},
        },
        {
            "force": "p1:w13=c2,p1:w48=c3,p1:w50=c2",
            "comparison": {"words": 0, "candidate_instructions": 96},
        },
    ],
}

#: The opposite receipt: one force the pass declined outright and one it
#: bought with two extra instructions.
FORCE_REFUSED = {
    "schema": "decomp-workbench-oracle-sweep-v1",
    "baseline": {
        "force": None,
        "comparison": {"words": 8, "candidate_instructions": 96},
    },
    "results": [
        {"force": "p1:w13=c2", "comparison": None},
        {
            "force": "p1:w22=c2",
            "comparison": {"words": 6, "candidate_instructions": 98},
        },
    ],
}


class PoolLaneGateTests(unittest.TestCase):
    """The length gate, and the counter-example it exists for.

    `overlay43FilterImage` carried "the residual is one cyclic pool rotation"
    until somebody compared the lanes: 18 target slots against 15. Forcing the
    rotation to the target's colours improved 33 words to 26 and raised opcode
    mismatches from 8 to 10, because the three values the target colours are in
    our temp ring and no colour reaches them.
    """

    def colour_view(
        self,
        *,
        target_pool: tuple[str, ...],
        candidate_pool: tuple[str, ...],
        webs: tuple[tuple[str, str], ...] = (("v1", "v0"), ("v0", "v1")),
    ) -> MechanismView:
        view = view_for(HOME_TARGET, HOME_TARGET)
        made = tuple(
            Web(
                web=f"w{index}",
                target=target,
                candidate=candidate,
                count=3,
                rows=(index,),
            )
            for index, (target, candidate) in enumerate(webs)
        )
        pool = next(item for item in view.lanes if item.classification == "pool")
        pool = dataclasses.replace(pool, target=target_pool, candidate=candidate_pool)
        return dataclasses.replace(
            view,
            webs=made,
            verdict="register-permutation",
            lanes=tuple(
                pool if item.classification == "pool" else item for item in view.lanes
            ),
        )

    def test_unequal_lanes_are_a_population_difference_not_a_rotation(self) -> None:
        lever = lever_for(
            self.colour_view(
                target_pool=("v0", "v1", "a0"), candidate_pool=("v0", "v1")
            )
        )
        self.assertEqual(lever.lever_class, LEVER_POOL_POPULATION)
        self.assertIsNone(lever.family)
        self.assertEqual(lever.measurements["pool_lane_length_delta"], -1)
        self.assertIn("not a rotation", lever.reason)

    def test_the_population_verdict_names_the_side_holding_the_surplus(self) -> None:
        lever = lever_for(
            self.colour_view(
                target_pool=("v0", "v1"), candidate_pool=("v0", "v1", "a0")
            )
        )
        self.assertIn("the candidate colours 1 value", lever.reason)

    def test_the_counter_example_is_cited_where_the_gate_fires(self) -> None:
        lever = lever_for(
            self.colour_view(
                target_pool=("v0", "v1", "a0"), candidate_pool=("v0", "v1")
            )
        )
        self.assertIn("overlay43FilterImage", " ".join(lever.evidence))

    def test_equal_lanes_with_no_capture_ask_for_the_sweep(self) -> None:
        lever = lever_for(
            self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1"))
        )
        self.assertEqual(lever.lever_class, LEVER_POOL_ROTATION)
        self.assertIsNone(lever.family)
        self.assertTrue(any("CDX_LOG=1" in item for item in lever.needs))

    def test_an_identical_pool_lane_is_not_routed_here_at_all(self) -> None:
        """No difference in the lane is no rotation, whatever the webs say."""

        lever = lever_for(
            self.colour_view(target_pool=("v0", "v1"), candidate_pool=("v0", "v1"))
        )
        self.assertNotIn(
            lever.lever_class, {LEVER_POOL_ROTATION, LEVER_POOL_POPULATION}
        )


class OwningSweepTests(PoolLaneGateTests):
    """Which sweep coloured the webs, and what each one's order is."""

    def log(self, text: str) -> CdxLog:
        return CdxLog(text, name="capture.log")

    def rotation(self) -> MechanismView:
        return self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1"))

    def test_p2_is_named_from_the_records_with_its_visit_order(self) -> None:
        lever = lever_for(self.rotation(), cdx_log=self.log(P2_LOG), proc=0)
        self.assertEqual(lever.lever_class, LEVER_POOL_ROTATION)
        self.assertEqual(lever.measurements["owning_sweep"], "p2")
        self.assertIn("ascending web number", " ".join(lever.evidence))

    def test_p2_reports_the_save_cost_as_inert(self) -> None:
        lever = lever_for(self.rotation(), cdx_log=self.log(P2_LOG), proc=0)
        self.assertIn("bestcost=0.000000", " ".join(lever.evidence))

    def test_the_direction_names_the_web_that_must_move_earlier(self) -> None:
        lever = lever_for(self.rotation(), cdx_log=self.log(P2_LOG), proc=0)
        self.assertEqual(lever.measurements["move_earlier"], 9)
        self.assertEqual(lever.measurements["move_later"], 6)
        self.assertIn("web 9 must be visited before web 6", lever.reason)

    def test_a_p1_tie_group_is_named_with_its_save_and_members(self) -> None:
        lever = lever_for(self.rotation(), cdx_log=self.log(P1_TIED_LOG), proc=1)
        self.assertEqual(lever.measurements["owning_sweep"], "p1")
        self.assertEqual(lever.measurements["tie_group"]["save"], 1.5)
        self.assertEqual(lever.measurements["tie_group"]["webs"], [48, 50])

    def test_an_untied_p1_pair_routes_to_cost_and_says_why(self) -> None:
        lever = lever_for(self.rotation(), cdx_log=self.log(P1_UNTIED_LOG), proc=1)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "change-the-save-cost")
        self.assertIn("not tied on save", " ".join(lever.evidence))

    def test_the_truncation_family_needs_an_expression_web(self) -> None:
        """The one measured spelling, and the shape it was measured on."""

        lever = lever_for(self.rotation(), cdx_log=self.log(P2_LOG), proc=0)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "store-site-truncation")

        without = P2_LOG.replace("web=9 sym=0 type=4", "web=9 sym=0 type=3")
        other = lever_for(self.rotation(), cdx_log=self.log(without), proc=0)
        self.assertIsNone(other.family)
        self.assertIn("type=4 expression web", " ".join(other.evidence))

    def test_no_renumbering_edit_is_named_without_a_second_capture(self) -> None:
        for text, proc in ((P2_LOG, 0), (P1_TIED_LOG, 1), (P1_UNTIED_LOG, 1)):
            with self.subTest(proc=proc):
                lever = lever_for(self.rotation(), cdx_log=self.log(text), proc=proc)
                if lever.family is None:
                    continue
                self.assertTrue(
                    any("CONFIRMING second capture" in item for item in lever.needs),
                    lever.needs,
                )

    def test_a_web_held_by_two_decisions_names_no_direction(self) -> None:
        """The `overlay4UpdateObjectMotion` ambiguity, reported as one.

        Webs 13 and 22 arrived at their decisions with identical records and
        both took v0. A register that two coloured webs hold does not say
        which of them carries the residual's sites, and the block asks for the
        detail capture instead of picking one.
        """

        doubled = P2_LOG + P2_LOG.split(
            "[CDX] webdetail phase=p2 proc=0 role=target web=9"
        )[0].replace("web=6", "web=13")
        lever = lever_for(self.rotation(), cdx_log=self.log(doubled), proc=0)
        self.assertIsNone(lever.measurements["move_earlier"])
        self.assertIn("more than one coloured web", lever.reason)
        self.assertTrue(any("CDX_DETAIL_WEB" in item for item in lever.needs))


class ForceReachabilityTests(PoolLaneGateTests):
    """A recorded force is a statement about the web graph, not about source."""

    def test_words_zero_under_a_force_is_proven(self) -> None:
        lever = lever_for(
            self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1")),
            cdx_log=CdxLog(P2_LOG, name="capture.log"),
            force_result=FORCE_PROVEN,
            proc=0,
        )
        self.assertEqual(lever.reachability, "proven")
        self.assertIn("words=0", " ".join(lever.evidence))

    def test_a_declined_or_costed_force_is_unreachable(self) -> None:
        lever = lever_for(
            self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1")),
            cdx_log=CdxLog(P2_LOG, name="capture.log"),
            force_result=FORCE_REFUSED,
            proc=0,
        )
        self.assertEqual(lever.reachability, "unreachable")

    def test_a_force_that_neither_closed_nor_failed_proves_nothing(self) -> None:
        payload = {
            "schema": "decomp-workbench-oracle-sweep-v1",
            "baseline": {"comparison": {"words": 8, "candidate_instructions": 96}},
            "results": [
                {
                    "force": "p1:w13=c2",
                    "comparison": {"words": 5, "candidate_instructions": 96},
                }
            ],
        }
        verdict, notes = force_reachability(payload)
        self.assertIsNone(verdict)
        self.assertIn("measurement, not a proof", " ".join(notes))

    def test_no_force_leaves_the_field_null_and_asks_for_the_run(self) -> None:
        lever = lever_for(
            self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1")),
            cdx_log=CdxLog(P2_LOG, name="capture.log"),
            proc=0,
        )
        self.assertIsNone(lever.reachability)
        self.assertTrue(any("CDX_FORCE" in item for item in lever.needs))

    def test_the_rendered_block_prints_the_reachability_line(self) -> None:
        lines = format_lever(
            lever_for(
                self.colour_view(target_pool=("v1", "v0"), candidate_pool=("v0", "v1")),
                cdx_log=CdxLog(P2_LOG, name="capture.log"),
                force_result=FORCE_PROVEN,
                proc=0,
            )
        )
        self.assertTrue(
            any(item.startswith("  reachability: proven") for item in lines)
        )


class SweepRecordTests(unittest.TestCase):
    def test_tie_groups_are_p1_only_and_keyed_by_save(self) -> None:
        records = sweep_records(CdxLog(P1_TIED_LOG, name="capture.log"), proc=1)
        self.assertEqual(tie_groups(records)[1.5], (48, 50))
        self.assertEqual(tie_groups(records)[7.0], (146,))

    def test_p2_records_carry_no_tie_group_because_p2_does_not_use_save(
        self,
    ) -> None:
        records = sweep_records(CdxLog(P2_LOG, name="capture.log"), proc=0)
        self.assertEqual(tie_groups(records), {})
        self.assertEqual([item.phase for item in records], ["p2", "p2"])


class ConstructClassificationTests(unittest.TestCase):
    """The precondition check the field test found missing.

    `func_800056A4` was given `read-the-field-directly` for a line whose local
    holds a cast integer constant. The pop count was right; the law was not,
    and all three spellings compiled byte-identically.
    """

    def test_each_pop_cost_construct_is_recognised(self) -> None:
        cases = {
            "flare.blue = entry->blue & 0xFFFFU;": "field-through-local",
            "owner = context->entries[index * 2].owner;": "scaled-index",
            "angle = state->angle + state->angleStep * ticks;": ("fused-accumulate"),
        }
        for text, expected in cases.items():
            with self.subTest(line=text):
                self.assertEqual(classify_construct(text), expected)

    def test_a_cast_integer_constant_is_not_a_field_read(self) -> None:
        for text in (
            "table = (s32 **)0x800A0000;",
            "count = 7;",
            "i = 0;",
        ):
            with self.subTest(line=text):
                self.assertEqual(classify_construct(text), "constant")

    def test_anything_unplaceable_is_unclassified_not_the_nearest_rule(
        self,
    ) -> None:
        for text in ("entry = &D_0_entries;", "if (a == b) {", ""):
            with self.subTest(line=text):
                self.assertEqual(classify_construct(text), "unclassified")

    def test_the_fused_shape_outranks_the_field_read_it_contains(self) -> None:
        self.assertEqual(
            classify_construct("x = s->base + s->step * n;"), "fused-accumulate"
        )


class TempRingPreconditionTests(unittest.TestCase):
    def rotation_view(self) -> MechanismView:
        return view_for(
            (ROOT / "examples" / "fixtures" / "phase-shift-target.objdump").read_text(
                encoding="utf-8"
            ),
            (
                ROOT / "examples" / "fixtures" / "phase-shift-candidate.objdump"
            ).read_text(encoding="utf-8"),
        )

    def source(self, line42: str) -> list[str]:
        lines = ["" for _ in range(50)]
        lines[40] = "total = other;"
        lines[41] = line42
        lines[42] = "next = other;"
        return lines

    def test_a_trace_without_source_names_no_family(self) -> None:
        lever = lever_for(
            self.rotation_view(), ring_events=parse_trace(RING_TRACE), proc=3
        )
        self.assertEqual(lever.lever_class, LEVER_TEMP_RING)
        self.assertIsNone(lever.family)
        self.assertTrue(any("--source" in item for item in lever.needs))

    def test_a_field_read_on_the_charged_line_names_its_family(self) -> None:
        lever = lever_for(
            self.rotation_view(),
            ring_events=parse_trace(RING_TRACE),
            proc=3,
            source=self.source("blue = entry->blue;"),
        )
        self.assertIsNotNone(lever.family)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "read-the-field-directly")
        self.assertEqual(lever.needs, ())

    def test_a_constant_on_the_charged_line_names_none(self) -> None:
        # The field-test case: the pop count is real and the construct is not
        # one any pop-cost rule was measured on.
        lever = lever_for(
            self.rotation_view(),
            ring_events=parse_trace(RING_TRACE),
            proc=3,
            source=self.source("table = (s32 **)0x800A0000;"),
        )
        self.assertEqual(lever.lever_class, LEVER_TEMP_RING)
        self.assertIsNone(lever.family)
        self.assertIn("measured pop cost", lever.reason)
        self.assertIn("constant", lever.reason)

    def test_the_reason_names_the_line_that_selected_the_family(self) -> None:
        """With no line doubled, every traced line is charged.

        The family then comes from whichever of them holds a construct with a
        measured pop cost, and the reason has to name *that* line. Naming the
        first charged line instead reports a `constant` as the construct a
        field-read rule was measured on, which is both false and the exact
        confusion this gate exists to prevent.
        """

        flat = (
            "DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=14 line=41 emitted=10\n"
            "DKWB-FREELIST ALLOC_GP_RESULT proc=3 reg=15 line=42 emitted=11\n"
        )
        lines = ["" for _ in range(50)]
        lines[40] = "limit = 0x40;"
        lines[41] = "count = entry->total;"
        lever = lever_for(
            self.rotation_view(),
            ring_events=parse_trace(flat),
            proc=3,
            source=lines,
        )
        assert lever.family is not None
        self.assertEqual(lever.family.name, "read-the-field-directly")
        self.assertIn("line 42 is a field-through-local", lever.reason)
        self.assertNotIn("is a constant", lever.reason)

    def test_a_dereference_is_not_a_fused_accumulate(self) -> None:
        # `*` is a multiply in L78's construct and a dereference here. Read as
        # an accumulate, the line names `split-the-accumulate` for a shape the
        # rule was never measured on.
        self.assertEqual(classify_construct("n = *cursor + 1;"), "unclassified")
        self.assertEqual(classify_construct("x = a + b * c;"), "fused-accumulate")

    def test_the_charged_constructs_reach_the_measurements(self) -> None:
        lever = lever_for(
            self.rotation_view(),
            ring_events=parse_trace(RING_TRACE),
            proc=3,
            source=self.source("blue = entry->blue;"),
        )
        self.assertEqual(
            lever.measurements["constructs_by_line"]["42"], "field-through-local"
        )

    def test_a_scaled_index_names_the_double_scale_family(self) -> None:
        lever = lever_for(
            self.rotation_view(),
            ring_events=parse_trace(RING_TRACE),
            proc=3,
            source=self.source("owner = ctx->entries[i * 2].owner;"),
        )
        assert lever.family is not None
        self.assertEqual(lever.family.name, "scale-the-index-twice")


class StackHomeRankingTests(unittest.TestCase):
    """Lane evidence outranks frame arithmetic.

    On `func_80005868` the frames agreed and one home was displaced, so the
    frame-only ranking named `reuse-an-existing-local-as-carrier` -- for a
    six-line function with no dead local. The pool lane printed two paragraphs
    above named the surplus web, and declaration placement closed two stack
    constants, 8 words to 6.
    """

    def test_a_surplus_candidate_web_names_the_drop_direction(self) -> None:
        view = view_for(HOME_TARGET, HOME_CANDIDATE)
        pool = next(item for item in view.lanes if item.classification == "pool")
        surplus = dataclasses.replace(pool, candidate=(*pool.candidate, "v1"))
        view = dataclasses.replace(
            view,
            lanes=tuple(
                surplus if item.classification == "pool" else item
                for item in view.lanes
            ),
        )
        lever = lever_for(view)
        assert lever.family is not None
        self.assertEqual(lever.family.name, "drop-a-declared-local")
        self.assertEqual(lever.measurements["pool_lane_length_delta"], 1)
        self.assertIn("outranks the frame arithmetic", " ".join(lever.evidence))

    def test_a_shorter_candidate_lane_says_the_target_holds_the_web(self) -> None:
        """The two sides of the lane comparison name opposite directions.

        Reported the wrong way round, the reason contradicts the evidence line
        printed directly above it in the same block.
        """

        view = view_for(HOME_TARGET, HOME_CANDIDATE)
        pool = next(item for item in view.lanes if item.classification == "pool")
        surplus = dataclasses.replace(pool, target=(*pool.target, "v1"))
        view = dataclasses.replace(
            view,
            lanes=tuple(
                surplus if item.classification == "pool" else item
                for item in view.lanes
            ),
        )
        lever = lever_for(view)
        self.assertEqual(lever.measurements["pool_lane_length_delta"], -1)
        self.assertIn("so the target colours a web", lever.reason)
        self.assertIn("the target colours a web", " ".join(lever.evidence))

    def test_equal_lanes_fall_through_to_the_frame_arithmetic(self) -> None:
        lever = lever_for(view_for(HOME_TARGET, HOME_CANDIDATE))
        assert lever.family is not None
        self.assertEqual(lever.family.name, "reuse-an-existing-local-as-carrier")

    def test_the_ordering_rule_is_stated_in_order(self) -> None:
        self.assertEqual(len(STACK_HOME_RANKING), 3)
        self.assertIn("pool lane", STACK_HOME_RANKING[0])
        self.assertIn("frame delta", STACK_HOME_RANKING[1])


class ProofPromotionTests(unittest.TestCase):
    """A catalogue proof whose precondition is met is the verdict."""

    def colour_view(self, webs: int) -> MechanismView:
        view = view_for(HOME_TARGET, HOME_TARGET)
        made = tuple(
            Web(web=f"w{index}", target="v0", candidate="a0", count=7, rows=(index,))
            for index in range(webs)
        )
        return dataclasses.replace(view, webs=made, verdict="register-permutation")

    def test_one_web_under_the_colourer_is_unreachable_not_none_known(
        self,
    ) -> None:
        lever = lever_for(self.colour_view(1))
        self.assertEqual(lever.lever_class, LEVER_UNREACHABLE)
        assert lever.unreachable is not None
        self.assertEqual(lever.unreachable.name, "uopt-coalescing-tie-break")
        self.assertEqual(lever.needs, ())

    def test_the_promoted_proof_leaves_the_others_as_see_also(self) -> None:
        lever = lever_for(self.colour_view(1))
        self.assertEqual(
            [item.name for item in lever.see_also], ["uopt-address-folding"]
        )

    def test_several_webs_do_not_meet_the_precondition(self) -> None:
        lever = lever_for(self.colour_view(3))
        self.assertEqual(lever.lever_class, LEVER_NONE_KNOWN)
        self.assertTrue(lever.needs)

    def test_a_saved_register_web_is_not_the_argument_return_tie(self) -> None:
        """One web under the colourer is necessary, not sufficient.

        L82 is about a tie between the register a call takes its argument in
        and the one it returns in. An `s0`->`s1` web is one consistent
        substitution under the same pass and the proof says nothing about it,
        so promoting it to a verdict would rule out an edit on a shape nobody
        measured.
        """

        view = self.colour_view(1)
        view = dataclasses.replace(
            view,
            webs=(dataclasses.replace(view.webs[0], target="s0", candidate="s1"),),
        )
        lever = lever_for(view)
        self.assertEqual(lever.lever_class, LEVER_NONE_KNOWN)
        self.assertIn(
            "uopt-coalescing-tie-break", [item.name for item in lever.see_also]
        )

    def test_every_proof_states_the_shape_it_was_measured_on(self) -> None:
        for name, proof in UNREACHABLE_PROOFS.items():
            with self.subTest(proof=name):
                self.assertTrue(proof.precondition.strip())

    def test_an_unpromotable_proof_prints_its_precondition(self) -> None:
        lines = format_lever(lever_for(self.colour_view(3)))
        self.assertTrue(any(item.startswith("    applies when: ") for item in lines))


#: A two-register transposition with equal pool lanes: the shape
#: `overlay60ReassignChoiceSlots` presented, where both lanes are the same
#: length and the whole residual is a v0/v1 substitution.
ROTATION_TARGET = """
00000000 <demo>:
   0: 27bdffe8  addiu $sp,$sp,-24
   4: afbf0014  sw $ra,20($sp)
   8: 00808025  move $s0,$a0
   c: 8e020000  lw $v0,0($s0)
  10: 8e030004  lw $v1,4($s0)
  14: 00431021  addu $v0,$v0,$v1
  18: 03e00008  jr $ra
  1c: 27bd0018  addiu $sp,$sp,24
"""

ROTATION_CANDIDATE = """
00000000 <demo>:
   0: 27bdffe8  addiu $sp,$sp,-24
   4: afbf0014  sw $ra,20($sp)
   8: 00808025  move $s0,$a0
   c: 8e030000  lw $v1,0($s0)
  10: 8e020004  lw $v0,4($s0)
  14: 00621821  addu $v1,$v1,$v0
  18: 03e00008  jr $ra
  1c: 27bd0018  addiu $sp,$sp,24
"""


class PoolRotationCommandTests(unittest.TestCase):
    """The block on the screen, from two real disassemblies and one capture.

    Everything above builds its view by hand. This one does not: the pair
    below diverges only in which of two registers holds which value, which is
    what a rotation is, and it is the shape the command has to recognise
    without being told.
    """

    def run_cli(self, arguments: list[str]) -> tuple[int, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue()

    def dumps(self, root: Path) -> tuple[Path, Path]:
        target = root / "target.objdump"
        candidate = root / "candidate.objdump"
        target.write_text(ROTATION_TARGET, encoding="utf-8")
        candidate.write_text(ROTATION_CANDIDATE, encoding="utf-8")
        return target, candidate

    def test_an_uncaptured_rotation_asks_for_the_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, candidate = self.dumps(Path(directory))
            status, stdout = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--json",
                ]
            )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)["lever"]
        self.assertEqual(payload["lever_class"], LEVER_POOL_ROTATION)
        self.assertIsNone(payload["reachability"])
        self.assertTrue(any("CDX_LOG=1" in item for item in payload["needs"]))

    def test_the_capture_and_the_force_reach_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, candidate = self.dumps(root)
            log = root / "cdx.log"
            log.write_text(P2_LOG, encoding="utf-8")
            force = root / "force.json"
            force.write_text(json.dumps(FORCE_PROVEN), encoding="utf-8")
            status, stdout = self.run_cli(
                [
                    "diagnose-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--ladder",
                    str(log),
                    "--force-result",
                    str(force),
                    "--lever-proc",
                    "0",
                    "--json",
                ]
            )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)["lever"]
        self.assertEqual(payload["lever_class"], LEVER_POOL_ROTATION)
        self.assertEqual(payload["reachability"], "proven")
        self.assertEqual(payload["measurements"]["owning_sweep"], "p2")
        self.assertEqual(payload["measurements"]["move_earlier"], 9)
