"""Synthetic capability/role separation; no project or compiler payloads."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mips_asm import assemble

from decomp_workbench.force_spec import force_specification
from decomp_workbench.globalcolor import register_for_color
from decomp_workbench.levers import lever_for
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.register_state import (
    REGISTER_STATE_SCHEMA,
    RegisterReservations,
    load_reservations,
)
from decomp_workbench.view import MechanismView, build_view, colorable_registers


def make_view(
    target: list[str],
    candidate: list[str],
    target_state: RegisterReservations | None = None,
    candidate_state: RegisterReservations | None = None,
) -> MechanismView:
    return build_view(
        parse_disassembly(assemble(target, symbol="demo"), symbol="demo"),
        parse_disassembly(assemble(candidate, symbol="demo"), symbol="demo"),
        target_name="target",
        candidate_name="candidate",
        symbol="demo",
        target_reservations=target_state,
        candidate_reservations=candidate_state,
    )


class ReservationTests(unittest.TestCase):
    def test_decoded_colors_are_possible_not_automatically_actual(self) -> None:
        for color in range(7, 13):
            register = register_for_color(color)
            self.assertIn(register, colorable_registers())
            view = make_view([f"lw {register},0(s0)"], ["lw s1,0(s0)"])
            self.assertEqual(view.as_dict()["ring_only_targets"], [])
            self.assertEqual(view.owning_pass, "unknown")
            self.assertEqual(view.routing, "evidence-first")
            self.assertEqual(view.lanes[1].classification, "shared")

    def test_store_only_color_and_force_spec_remain_diagnostic(self) -> None:
        view = make_view(["sw t0,0(s0)"], ["sw t2,0(s0)"])
        spec = force_specification(view)
        entry = spec["permutation"][0]
        self.assertFalse(entry["ring_only_target"])
        self.assertIsNone(entry["allocator_web"])
        self.assertIsNone(entry["phase"])

    def test_cyclic_shared_roles_do_not_prove_fifo_or_pop_edit(self) -> None:
        view = make_view(
            ["lw t0,0(s0)", "lw t1,4(s0)", "lw t2,8(s0)"],
            ["lw t1,0(s0)", "lw t2,4(s0)", "lw t0,8(s0)"],
        )
        self.assertNotEqual(view.verdict, "phase-shift")
        self.assertEqual(view.playbook, "register-role-audit")
        lever = lever_for(view)
        self.assertIsNone(lever.measurements["complete_reservation_state"])
        self.assertIsNone(lever.family)

    def test_supplied_sides_do_not_leak_and_remain_conditional(self) -> None:
        five = RegisterReservations(
            ("t0", "t1", "t2", "t3", "t4"), "synthetic assumption"
        )
        six = RegisterReservations((*five.reserved, "t5"), "synthetic assumption")
        left, right = ["lw t5,0(s0)"], ["lw t6,0(s0)"]
        for target, candidate, ts, cs in (
            (left, right, five, six),
            (right, left, six, five),
        ):
            view = make_view(target, candidate, ts, cs)
            self.assertEqual(view.owning_pass, "unknown")
            state = view.as_dict()["register_reservations"]
            self.assertEqual(state["target"]["reserved"], list(ts.reserved))
            self.assertEqual(state["candidate"]["reserved"], list(cs.reserved))
            self.assertFalse(any(lane.rotation for lane in view.lanes))
            self.assertEqual(state["candidate"]["basis"], "supplied-reservations")
        unknown = make_view(left, right, None, six)
        self.assertIsNone(unknown.as_dict()["register_reservations"]["target"])
        self.assertIn(
            "t5",
            next(
                lane for lane in unknown.lanes if lane.classification == "shared"
            ).target,
        )

    def test_reserved_without_emission_is_not_an_invented_use(self) -> None:
        state = RegisterReservations(("t5",), "synthetic assumption")
        view = make_view(["lw t6,0(s0)"], ["lw t7,0(s0)"], state, state)
        self.assertTrue(
            all("t5" not in lane.target + lane.candidate for lane in view.lanes)
        )
        self.assertEqual(
            view.as_dict()["register_reservations"]["target"]["reserved"], ["t5"]
        )

    def test_projection_does_not_change_comparison_metrics_or_exactness(self) -> None:
        lines = ["lw t5,0(s0)", "sw t5,4(s0)"]
        plain = make_view(lines, lines)
        state = RegisterReservations(("t5",), "synthetic assumption")
        supplied = make_view(lines, lines, state, state)
        self.assertEqual(plain.counts, supplied.counts)
        self.assertEqual(supplied.verdict, "exact")

    def test_invalid_or_unsupported_reservations_refuse(self) -> None:
        for regs in (("t0", "t0"), ("t6",), ("unknown",)):
            with self.assertRaises(ValueError):
                RegisterReservations(regs, "synthetic")
        with self.assertRaises(ValueError):
            RegisterReservations((), "")

    def test_sidecar_binding_and_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, sidecar = root / "input.o", root / "state.json"
            source.write_bytes(b"synthetic object identity")
            value = {
                "schema": REGISTER_STATE_SCHEMA,
                "symbol": "demo",
                "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "reserved": ["t0"],
                "evidence": "explicit synthetic assumption",
            }
            sidecar.write_text(json.dumps(value))
            state = load_reservations(sidecar, source, "demo")
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state.reserved, ("t0",))
            replacements: list[Any] = [
                [],
                {**value, "symbol": "other"},
                {**value, "input_sha256": "0" * 64},
                {**value, "reserved": "t0"},
                {**value, "reserved": [8]},
            ]
            for replacement in replacements:
                sidecar.write_text(json.dumps(replacement))
                with self.assertRaises(ValueError):
                    load_reservations(sidecar, source, "demo")


if __name__ == "__main__":
    unittest.main()
