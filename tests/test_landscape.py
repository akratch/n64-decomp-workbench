"""The colour landscape plans from the held trace and packs by radii."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.globalcolor import parse_globalcolor_trace
from decomp_workbench.landscape import (
    LandscapeRun,
    footprint,
    freshness,
    histogram,
    landscape_report,
    landscape_webs,
    pack,
    plan_probes,
    repack,
    rivals,
    run_landscape,
    validate_hold,
    winners,
)

TRACE = """
[CDX] p1cost phase=p1 proc=0 web=10 color=2 reg=v1 kind=caller cost=1
[CDX] p1cost phase=p1 proc=0 web=10 color=3 reg=a0 kind=caller cost=1
[CDX] p1cost phase=p1 proc=0 web=10 color=14 reg=s0 kind=callee cost=0
[CDX] p1color phase=p1 proc=0 web=10 sym=1 color=2 reg=v1 forced=0
[CDX] p1cost phase=p1 proc=0 web=11 color=15 reg=s1 kind=callee cost=2
[CDX] p1cost phase=p1 proc=0 web=11 color=16 reg=s2 kind=callee cost=3
[CDX] p1cost phase=p1 proc=0 web=11 color=17 reg=s3 kind=callee cost=3
[CDX] p1color phase=p1 proc=0 web=11 sym=2 color=15 reg=s1 forced=0
[CDX] p1cost phase=p1 proc=0 web=12 color=4 reg=a1 kind=caller cost=0
[CDX] p1color phase=p1 proc=0 web=12 sym=3 color=4 reg=a1 forced=0
[CDX] p1cost phase=p1 proc=1 web=10 color=9 reg=t2 kind=caller cost=0
[CDX] p1color phase=p1 proc=1 web=10 sym=4 color=9 reg=t2 forced=0
"""


def row(force: str, web: int, score: int, windows: dict[int, int]) -> dict[str, Any]:
    return {
        "force": force,
        "web": web,
        "color": int(force.rsplit("c", 1)[1]),
        "score": score,
        "status": "ok",
        "footprint": dict(windows),
    }


class PlanTests(unittest.TestCase):
    def test_webs_are_read_per_procedure_from_their_own_cost_tables(self) -> None:
        webs = landscape_webs(parse_globalcolor_trace(TRACE), proc=0)
        self.assertEqual(sorted(webs), [10, 11, 12])
        self.assertEqual(webs[10].register, "v1")
        self.assertEqual(webs[10].kind, "caller")
        self.assertEqual(webs[10].legal_colors(same_kind=True), [3])
        self.assertEqual(sorted(webs[10].legal_colors(same_kind=False)), [3, 14])

    def test_the_probe_stays_in_its_save_kind_and_skips_held_webs(self) -> None:
        webs = landscape_webs(parse_globalcolor_trace(TRACE), proc=0)
        plan = plan_probes(webs, hold=("p1:w11=c16",))
        self.assertEqual(
            [(probe.web, probe.color) for probe in plan], [(10, 3), (12, None)]
        )
        self.assertEqual(plan[1].reason, "no second colour in its cost table")

    def test_every_colour_orders_nearest_first(self) -> None:
        webs = landscape_webs(parse_globalcolor_trace(TRACE), proc=0)
        plan = plan_probes(webs, every_colour=True, wanted=[11])
        self.assertEqual([probe.force for probe in plan], ["p1:w11=c16", "p1:w11=c17"])

    def test_a_requested_web_the_trace_never_coloured_is_visible(self) -> None:
        webs = landscape_webs(parse_globalcolor_trace(TRACE), proc=0)
        plan = plan_probes(webs, wanted=[99])
        self.assertIsNone(plan[0].color)
        self.assertIn("no p1color", plan[0].reason)

    def test_a_hold_names_each_web_once_and_is_phase_qualified(self) -> None:
        self.assertEqual(
            validate_hold(["p1:w1=c14,p1:w2=c15"]), ("p1:w1=c14", "p1:w2=c15")
        )
        with self.assertRaisesRegex(ValueError, "twice"):
            validate_hold(["p1:w1=c14", "p1:w1=c15"])
        with self.assertRaises(ValueError):
            validate_hold(["w1=c14"])


class PackingTests(unittest.TestCase):
    def test_footprint_is_the_signed_window_difference(self) -> None:
        base = histogram([0, 1, 9, 40], 0x10)
        cell = histogram([0, 9, 10, 40], 0x10)
        self.assertEqual(footprint(base, cell), {0x0: -1, 0x20: 1})

    def test_packing_beats_sorting_by_score(self) -> None:
        """The overlay 58 shape: the better single colour duplicates a radius.

        `w225=c20` scores better alone than `w225=c14`, but it shares its
        radius with `w379=c20`, so a set holding it abandons the region only
        c14 reaches. Greedy by score would take c20; the packing must not.
        """

        rows = [
            row("p1:w225=c20", 225, 217, {0x80: -10}),
            row("p1:w379=c20", 379, 215, {0x80: -12}),
            row("p1:w225=c14", 225, 220, {0x780: -7}),
        ]
        result = pack(rows, 227)
        self.assertEqual(sorted(result["forces"]), ["p1:w225=c14", "p1:w379=c20"])
        self.assertEqual(result["predicted_score"], 227 - 12 - 7)

    def test_a_web_takes_one_colour_in_a_packing(self) -> None:
        rows = [
            row("p1:w5=c14", 5, 90, {0x0: -10}),
            row("p1:w5=c15", 5, 92, {0x100: -8}),
        ]
        self.assertEqual(pack(rows, 100)["forces"], ["p1:w5=c14"])

    def test_identical_radii_are_rivals_not_additions(self) -> None:
        rows = [
            row("p1:w1=c3", 1, 8, {0x0: -2}),
            row("p1:w2=c5", 2, 9, {0x0: -1}),
            row("p1:w3=c6", 3, 9, {0x80: -1}),
        ]
        self.assertEqual(
            [[item["force"] for item in group] for group in rivals(rows, 10)],
            [["p1:w1=c3", "p1:w2=c5"]],
        )
        self.assertEqual(len(winners(rows, 10)), 3)

    def test_no_winner_is_a_scoped_closure_and_names_no_next_hold(self) -> None:
        rows = [row("p1:w1=c3", 1, 12, {0x0: 2})]
        report = landscape_report(
            rows, base_score=10, hold=("p1:w9=c14",), window=0x80, proc=0, planned=1
        )
        self.assertEqual(report["winners"], [])
        self.assertIsNone(report["next_hold"])
        self.assertIn("floor for any one additional force", report["closure"])
        self.assertIn("never a claim", report["closure"])

    def test_a_reloaded_report_repacks_to_the_same_answer(self) -> None:
        rows = [
            row("p1:w1=c3", 1, 8, {0x0: -2}),
            row("p1:w3=c6", 3, 9, {0x80: -1}),
        ]
        report = landscape_report(
            rows, base_score=10, hold=(), window=0x80, proc=0, planned=2
        )
        reloaded = repack(json.loads(json.dumps(report)))
        self.assertEqual(reloaded["packing"], report["packing"])
        self.assertEqual(reloaded["next_hold"], ["p1:w1=c3", "p1:w3=c6"])


# A fake instrumented compiler: the object is a list of (word, assembly) rows
# chosen by CDX_FORCE, and with CDX_LOG it writes a CDX trace to CDX_OUT.
COMPILER = r"""
import os, pathlib, sys
BASE = "00851021 addu $v0,$a0,$a1"
DIFF = "00851821 addu $v1,$a0,$a1"
forces = set(filter(None, os.environ.get("CDX_FORCE", "").split(",")))
rows = [BASE] * 12
wrong = {1, 5, 9}
if "p1:w10=c3" in forces or "p1:w12=c5" in forces:
    wrong.discard(1)
if "p1:w11=c16" in forces:
    wrong.discard(5)
for index in wrong:
    rows[index] = DIFF
if "p1:w13=c7" in forces:
    rows.append("00000000 nop")
pathlib.Path(sys.argv[2]).write_text("\n".join(rows) + "\n")
if os.environ.get("CDX_LOG") and os.environ.get("CDX_OUT"):
    held = "p1:w14=c17" in forces
    lines = []
    webs = ((10, 2, (3,)), (11, 15, (16,)), (12, 4, (5,)), (13, 6, (7,)))
    webs += ((14, 17 if held else 18, (17, 18)),)
    for web, colour, others in webs:
        head = f"phase=p1 proc=0 web={web}"
        for c in (colour, *others):
            lines.append(f"[CDX] p1cost {head} color={c} kind=caller cost=1")
        lines.append(f"[CDX] p1color {head} color={colour} forced=0")
    pathlib.Path(os.environ["CDX_OUT"]).write_text("\n".join(lines) + "\n")
"""

OBJDUMP = r"""#!/usr/bin/env python3
import pathlib, sys
obj = next(pathlib.Path(a) for a in sys.argv[1:] if pathlib.Path(a).suffix == ".o")
print("00000000 <demo>:")
for index, line in enumerate(obj.read_text().splitlines()):
    word, asm = line.split(" ", 1)
    print(f"{index * 4:>4x}: {word}  {asm}")
"""


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate.c"
        self.source.write_text("int demo;\n", encoding="utf-8")
        self.target = self.root / "target.o"
        self.target.write_text("\n".join(["00851021 addu $v0,$a0,$a1"] * 12) + "\n")
        compiler = self.root / "compile.py"
        compiler.write_text(COMPILER, encoding="utf-8")
        self.objdump = self.root / "objdump"
        self.objdump.write_text(OBJDUMP, encoding="utf-8")
        self.objdump.chmod(0o755)
        self.template = f"{sys.executable} {compiler} {{source}} {{output}}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_config(self, **overrides: object) -> LandscapeRun:
        values: dict[str, object] = {
            "source": self.source,
            "target": self.target,
            "template": self.template,
            "environment": {},
            "cache_dir": self.root / "cache",
            "state_dir": self.root / "state",
            "proc": 0,
            "objdump": str(self.objdump),
            "window": 0x10,
            "compile_cwd": self.root,
        }
        values.update(overrides)
        return LandscapeRun(**values)  # type: ignore[arg-type]

    def test_a_held_landscape_plans_from_its_own_trace_and_packs(self) -> None:
        report = run_landscape(self.run_config(hold=("p1:w14=c17",)))
        self.assertEqual(report["order"], "held")
        self.assertEqual(report["trace_identity"], "identical")
        self.assertEqual(report["base_score"], 3)
        forces = {row["force"] for row in report["rows"]}
        self.assertNotIn("p1:w14=c18", forces)  # the held web is the premise
        self.assertEqual(report["size_changed"], ["p1:w13=c7"])
        self.assertEqual(report["rivals"], [["p1:w10=c3", "p1:w12=c5"]])
        self.assertEqual(report["packing"]["predicted_score"], 1)
        self.assertEqual(len(report["packing"]["forces"]), 2)
        self.assertIn("p1:w11=c16", report["packing"]["forces"])
        self.assertEqual(report["next_hold"][0], "p1:w14=c17")
        self.assertIn("never source-match evidence", report["proof"])

    def test_a_supplied_trace_is_refused_beside_a_hold(self) -> None:
        trace = self.root / "unforced.log"
        trace.write_text(TRACE, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot be combined with --hold"):
            run_landscape(self.run_config(hold=("p1:w14=c17",), trace=trace))

    def test_the_landscape_owns_force_and_tracing_controls(self) -> None:
        with self.assertRaisesRegex(ValueError, "owns CDX_FORCE"):
            run_landscape(self.run_config(environment={"CDX_FORCE": "p1:w1=c2"}))

    def test_every_colour_on_a_size_mismatch_is_refused(self) -> None:
        self.target.write_text(
            "\n".join(["00851021 addu $v0,$a0,$a1"] * 13) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "insertion shadow"):
            run_landscape(self.run_config(every_colour=True))

    def test_the_cli_writes_a_report_that_goes_stale_with_its_source(self) -> None:
        arguments = [
            "sweep",
            "landscape",
            str(self.source),
            "--target",
            str(self.target),
            "--toolchain",
            str(self.root / "toolchain"),
            "--compile-command",
            self.template,
            "--objdump",
            str(self.objdump),
            "--window",
            "0x10",
            "--state-dir",
            str(self.root / "state"),
            "--cache-dir",
            str(self.root / "cache"),
            "--json",
        ]
        with mock.patch(
            "decomp_workbench.landscape_cli.merge_toolchain_environment",
            side_effect=lambda environment, *_args, **_kwargs: dict(environment),
        ):
            status, stdout, _ = self.cli(arguments)
        self.assertEqual(status, 0, stdout)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-landscape-v1")
        saved = Path(payload["state"]["report"])
        status, _, _ = self.cli(["sweep", "landscape", "--report", str(saved)])
        self.assertEqual(status, 0)
        self.source.write_text("int demo2;\n", encoding="utf-8")
        status, stdout, _ = self.cli(["sweep", "landscape", "--report", str(saved)])
        self.assertEqual(status, 1)
        self.assertIn("STALE", stdout)
        self.assertIn("STALE", freshness(json.loads(saved.read_text())) or "")

    def cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
