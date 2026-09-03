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
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.as1_reorganize import parse_as1_reorganize_trace
from decomp_workbench.cascade import CdxLog
from decomp_workbench.cli import main
from decomp_workbench.emit_provenance import parse_emit_trace
from decomp_workbench.frame_ladder import frame_ladder
from decomp_workbench.levers import (
    LEVER_LINE_ORDER,
    LEVER_NONE_KNOWN,
    LEVER_SCHEMA,
    LEVER_STACK_HOME,
    LEVER_TEMP_RING,
    LEVER_UNREACHABLE,
    LINE_ORDER_FAMILIES,
    STACK_HOME_FAMILIES,
    TEMP_RING_FAMILIES,
    UNREACHABLE_PROOFS,
    format_lever,
    lever_for,
    pops_by_line,
    readiness_keys,
)
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.trace import parse_trace
from decomp_workbench.view import build_view

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


def view_for(target: str, candidate: str, **kwargs: object):
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
    def rotation_view(self):
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
    def schedule_view(self):
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
    def selections(self):
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
                "cfe-pointer-add-canonicalisation",
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


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
        self.assertEqual(payload["lever"]["needs"], [])

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
