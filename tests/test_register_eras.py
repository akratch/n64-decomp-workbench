"""Which pass owns a register is per-compiler-era data, and it is now probed.

Before this, `view` classed `t0`-`t5` as uopt coloring-pool registers and
`t6`-`t9` plus `s8` as ugen temps, under the single profile name `ido53`. That
table was inherited from earlier campaigns and had never been measured against
a named release. On IDO 5.3 at `-O2 -mips2` it is wrong in both directions:
nine forced-color experiments, confirmed against an instrumented ugen, show
uopt handing out only `v0`/`v1`/`a0-a3`/`s0-s8` and `f0`/`f2`/`f12-f24`, with
`t0-t9` and `f4/f6/f8/f10` *always* ugen block-local temps.

The cost of the old table was three campaign agents reading a `t`-register
difference as a coloring-priority question and spending variants on levers
7-13, when the mechanism was the ugen ring and the levers were 14-16.

The pre-probe table is still shipped, under the honest name `unverified`, and
is still what an unmeasured compiler gets: correcting `ido53` must not silently
relabel evidence recorded for a release nobody probed.
"""

from __future__ import annotations

import argparse
import unittest
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.field_guide import next_steps
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import (
    DEFAULT_REGISTER_PROFILE,
    REGISTER_CLASS_PROFILES,
    REGISTER_PROFILE_EVIDENCE,
    UNVERIFIED_CLASSES,
    MechanismView,
    build_view,
)
from decomp_workbench.view_cli import add_view_render_arguments

ROOT = Path(__file__).resolve().parents[1]

PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]


def _instructions(lines: list[str]) -> list[Instruction]:
    body = [*PROLOGUE, *lines, *EPILOGUE]
    return parse_disassembly(assemble(body, symbol="demo"), symbol="demo")


def view_of(
    lines: list[str],
    candidate_lines: list[str] | None = None,
    *,
    profile: str = DEFAULT_REGISTER_PROFILE,
) -> MechanismView:
    instructions = _instructions(lines)
    candidate = (
        instructions if candidate_lines is None else _instructions(candidate_lines)
    )
    return build_view(
        instructions,
        candidate,
        target_name="t",
        candidate_name="c",
        symbol="demo",
        register_profile=profile,
    )


def lane_of(view: MechanismView, register: str) -> str | None:
    for lane in view.lanes:
        if register in lane.target:
            return lane.classification
    return None


def candidate_lane_of(view: MechanismView, register: str) -> str | None:
    for lane in view.lanes:
        if register in lane.candidate:
            return lane.classification
    return None


class VerifiedEraTests(unittest.TestCase):
    """IDO 5.3 -O2 -mips2, the one release with a probe behind it."""

    def test_t_registers_are_ugen_temps_never_pool_colors(self) -> None:
        for register in ("t0", "t1", "t2", "t3", "t4", "t5", "t6", "t9"):
            with self.subTest(register=register):
                view = view_of([f"lw {register},0(s0)"])
                self.assertEqual(lane_of(view, register), "temp")

    def test_saved_registers_are_uopt_colors(self) -> None:
        for register in ("s1", "s2", "s7", "s8"):
            with self.subTest(register=register):
                view = view_of([f"lw {register},0(s0)"])
                self.assertEqual(lane_of(view, register), "pool")

    def test_the_float_split_is_carried_too(self) -> None:
        profile = REGISTER_CLASS_PROFILES["ido53"]
        for register in ("f4", "f6", "f8", "f10"):
            self.assertIn(register, profile["fp-temp"])
        for register in ("f0", "f2", "f12", "f20", "f24"):
            self.assertIn(register, profile["fp-pool"])
        # Not the ambiguous pair they look like. ugen initializes `ffree` with
        # six entries, withdraws f16/f18 before the first allocation, and never
        # hands them out (1460/1460 float allocations measured in f4-f10); uopt
        # colors them as c28/c29. A tool that reads the six-entry initializer
        # as the ring reports an `f12` -> `f16` coloring change as a closed
        # temp-ring site, which cost one campaign stage ~15 builds.
        self.assertIn("f16", profile["fp-pool"])
        self.assertIn("f18", profile["fp-pool"])
        self.assertNotIn("f16", profile["fp-temp"])
        self.assertNotIn("f18", profile["fp-temp"])
        self.assertEqual(len(profile["fp-temp"]), 4)

    def test_f16_is_read_as_a_coloring_change_not_a_closed_temp_site(self) -> None:
        """The phantom closure, as the lanes actually report it.

        `f12` on one side against `f16` on the other is one uopt color against
        another. Both must land in `fp-pool`, so the difference is attributed
        to coloring; a six-wide float ring would put `f16` in `fp-temp` and the
        same row would read as a temp-ring event.
        """

        view = view_of(["lwc1 f12,16(s0)"], ["lwc1 f16,16(s0)"])
        self.assertEqual(lane_of(view, "f12"), "fp-pool")
        self.assertEqual(candidate_lane_of(view, "f16"), "fp-pool")

    def test_the_profile_evidence_states_the_measured_float_ring(self) -> None:
        evidence = REGISTER_PROFILE_EVIDENCE["ido53"]
        self.assertIn("f16/f18", evidence)
        self.assertIn("withdrawn", evidence)

    def test_temp_tables_are_in_ugen_ring_order(self) -> None:
        """A rotation is a contiguous run of the table, so order is load-bearing.

        ugen seeds the int free list `t6 t7 t8 t9 t0 .. t5` and the float list
        `f4 f6 f8 f10`, and hands out its head. Storing the tables in register
        order instead would make a genuine one-step phase shift look like an
        arbitrary permutation.
        """

        profile = REGISTER_CLASS_PROFILES["ido53"]
        self.assertEqual(
            profile["temp"],
            ("t6", "t7", "t8", "t9", "t0", "t1", "t2", "t3", "t4", "t5"),
        )
        self.assertEqual(profile["fp-temp"], ("f4", "f6", "f8", "f10"))


class UnverifiedEraTests(unittest.TestCase):
    """An era with no probe keeps the behavior it already had."""

    def test_the_pre_probe_table_is_shipped_unchanged(self) -> None:
        self.assertEqual(
            UNVERIFIED_CLASSES,
            {
                "pool": (
                    "v0",
                    "v1",
                    "a0",
                    "a1",
                    "a2",
                    "a3",
                    "t0",
                    "t1",
                    "t2",
                    "t3",
                    "t4",
                    "t5",
                ),
                "temp": ("t6", "t7", "t8", "t9", "s8"),
            },
        )
        self.assertEqual(REGISTER_CLASS_PROFILES["unverified"], UNVERIFIED_CLASSES)

    def test_the_two_eras_disagree_about_the_same_register(self) -> None:
        """The whole point of the switch, in one assertion."""

        self.assertEqual(lane_of(view_of(["lw t0,0(s0)"]), "t0"), "temp")
        self.assertEqual(
            lane_of(view_of(["lw t0,0(s0)"], profile="unverified"), "t0"), "pool"
        )

    def test_an_unverified_era_has_no_float_lanes(self) -> None:
        self.assertNotIn("fp-temp", REGISTER_CLASS_PROFILES["unverified"])


class ProvenanceTests(unittest.TestCase):
    """A probed table and an inherited one must never read the same."""

    def test_every_profile_declares_what_it_is_made_of(self) -> None:
        self.assertEqual(set(REGISTER_PROFILE_EVIDENCE), set(REGISTER_CLASS_PROFILES))

    def test_the_evidence_travels_with_the_answer(self) -> None:
        payload = view_of(["lw t6,0(s0)"]).as_dict()
        self.assertEqual(payload["register_profile"], "ido53")
        self.assertIn("probed", payload["register_profile_evidence"])
        payload = view_of(["lw t6,0(s0)"], profile="unverified").as_dict()
        self.assertEqual(payload["register_profile"], "unverified")
        self.assertIn("not measured", payload["register_profile_evidence"])

    def test_the_flag_help_names_every_era_and_its_evidence(self) -> None:
        parser = argparse.ArgumentParser()
        add_view_render_arguments(parser)
        help_text = parser.format_help()
        for name, evidence in REGISTER_PROFILE_EVIDENCE.items():
            with self.subTest(profile=name):
                self.assertIn(name, help_text)
                self.assertIn(evidence.split(",")[0], help_text)


class DocumentationTests(unittest.TestCase):
    """The guide has to carry the law, not just the levers."""

    def guide(self) -> str:
        return (ROOT / "docs" / "field-guide.md").read_text(encoding="utf-8")

    def test_the_era_table_names_both_populations_and_the_caveat(self) -> None:
        text = self.guide()
        self.assertIn("s0 s1 s2 s3 s4 s5 s6 s7 s8", text)
        self.assertIn("t6 t7 t8 t9 t0 t1 t2 t3 t4 t5", text)
        self.assertIn("f4 f6 f8 f10", text)
        self.assertIn("unverified", text)

    def test_the_temp_playbook_carries_the_five_three_law(self) -> None:
        text = self.guide()
        for phrase in (
            "least-recently-freed",
            "once per procedure",
            "pure function of the alloc/free",
            "class-crossing",
            "monotone",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_playbook_says_which_claims_are_five_three_verified(self) -> None:
        text = self.guide()
        self.assertIn("5.3-verified", text)
        self.assertIn("IDO 7.1", text)

    def test_the_onramp_repeats_the_site_count_rule(self) -> None:
        joined = " ".join(next_steps("temp-fifo-phase"))
        self.assertIn("class-crossing", joined.lower())
        self.assertIn("not", joined)
        self.assertIn("monotone", joined)

    def test_the_agent_reference_carries_the_split(self) -> None:
        text = (
            ROOT
            / "src"
            / "decomp_workbench"
            / "skills"
            / "n64-decomp-campaign"
            / "references"
            / "ido-late-stage-patterns.md"
        ).read_text(encoding="utf-8")
        self.assertIn("always", text)
        self.assertIn("`t0-t9`", text)
        self.assertIn("unverified", text)


if __name__ == "__main__":
    unittest.main()
