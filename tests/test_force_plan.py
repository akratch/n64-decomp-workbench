"""The force experiment is planned from the residual, never typed by hand."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cascade import CdxLog
from decomp_workbench.cli import main
from decomp_workbench.force_plan import (
    plan_force_experiment,
    substitutions_from_diagnosis,
)
from decomp_workbench.oracle import run_oracle_campaign

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "traces" / "force-plan.log"

TWO_HOLDERS = "".join(
    f"[CDX] p1dec phase=p1 proc=0 web={web} save=1 bestcolor=15 bestreg=s1 "
    "forbidden0=0x0 forbidden1=0x0 decision=color\n"
    f"[CDX] p1color phase=p1 proc=0 web={web} color=15 reg=s1 forced=0\n"
    for web in (3, 8)
)


def log(text: str | None = None) -> CdxLog:
    return CdxLog(text or FIXTURE.read_text(encoding="utf-8"), name="capture.log")


class PlanTests(unittest.TestCase):
    def test_a_transposition_plans_singletons_then_the_set(self) -> None:
        plan = plan_force_experiment(log(), {"s1": "s3", "s3": "s1"})
        self.assertEqual(
            plan["cells"], ["p1:w12=c17", "p1:w19=c15", "p1:w12=c17,p1:w19=c15"]
        )
        self.assertTrue(plan["complete"])
        self.assertEqual(
            plan["oracle_plan"]["schema"], "decomp-workbench-oracle-plan-v1"
        )
        self.assertEqual(plan["oracle_plan"]["procedure"], 0)
        self.assertIn("never a source match", plan["proof"])

    def test_a_forbidden_colour_is_declined_before_a_build(self) -> None:
        plan = plan_force_experiment(log(), {"s2": "s0", "s1": "s3"})
        entry = next(
            item for item in plan["substitutions"] if item["candidate"] == "s2"
        )
        self.assertEqual(entry["status"], "all-forbidden")
        self.assertEqual(entry["declined"][0]["force"], "p1:w27=c14")
        self.assertIsNone(plan["full_set"])
        self.assertIn("withheld", plan["withheld"])
        self.assertEqual(plan["cells"], ["p1:w12=c17"])

    def test_a_ring_temp_and_an_uncoloured_target_are_named_not_guessed(self) -> None:
        plan = plan_force_experiment(log(), {"t6": "s1", "s1": "t9"})
        statuses = {item["candidate"]: item["status"] for item in plan["substitutions"]}
        self.assertEqual(statuses["t6"], "no-coloured-holder")
        self.assertEqual(statuses["s1"], "target-register-uncoloured")
        self.assertEqual(plan["cells"], [])

    def test_two_webs_on_one_register_are_each_planned_alone(self) -> None:
        plan = plan_force_experiment(log(TWO_HOLDERS), {"s1": "s0"})
        self.assertEqual(plan["substitutions"][0]["status"], "ambiguous-holder")
        self.assertEqual(plan["cells"], ["p1:w3=c14", "p1:w8=c14"])
        self.assertIsNone(plan["full_set"])

    def test_substitutions_come_from_a_diagnosis_lever(self) -> None:
        payload = {"lever": {"measurements": {"substitutions": {"s1": "s3"}}}}
        self.assertEqual(substitutions_from_diagnosis(payload), {"s1": "s3"})
        with self.assertRaisesRegex(ValueError, "substitutions"):
            substitutions_from_diagnosis({"lever": None})


COMPILER = (
    "import os, pathlib, sys\n"
    "value = b'exact' if os.environ.get('CDX_FORCE') == "
    "'p1:w12=c17,p1:w19=c15' else b'baseline'\n"
    "pathlib.Path(sys.argv[2]).write_bytes(value)\n"
)
OBJDUMP = (
    "#!/usr/bin/env python3\n"
    "import pathlib, sys\n"
    "obj = next(pathlib.Path(a) for a in sys.argv[1:] "
    "if pathlib.Path(a).suffix == '.o')\n"
    "value = obj.read_bytes()\n"
    "print('00000000 <demo>:')\n"
    "if value in {b'target', b'exact'}:\n"
    " print('   0: 03e00008  jr $ra')\n"
    "else:\n"
    " print('   0: 00001021  move $v0,$zero')\n"
    "print('   4: 00000000  nop')\n"
)


class CommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_a_written_plan_is_what_the_campaign_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            status, _, stderr = self.run_cli(
                [
                    "oracle",
                    "force-plan",
                    str(FIXTURE),
                    "--substitute",
                    "s1=s3",
                    "--substitute",
                    "s3=s1",
                    "--write",
                    str(plan_path),
                ]
            )
            self.assertEqual(status, 0, stderr)
            saved = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema"], "decomp-workbench-force-plan-v1")
            status, _, stderr = self.run_cli(
                [
                    "oracle",
                    "force-plan",
                    str(FIXTURE),
                    "--substitute",
                    "s1=s3",
                    "--write",
                    str(plan_path),
                ]
            )
            self.assertEqual(status, 2)
            self.assertIn("refusing to overwrite", stderr)

            source = root / "candidate.c"
            source.write_text("int demo;\n", encoding="utf-8")
            target = root / "target.o"
            target.write_bytes(b"target")
            compiler = root / "compile.py"
            compiler.write_text(COMPILER, encoding="utf-8")
            objdump = root / "objdump"
            objdump.write_text(OBJDUMP, encoding="utf-8")
            objdump.chmod(0o755)
            report = run_oracle_campaign(
                saved["oracle_plan"],
                source=source,
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                environment={},
                cache_dir=root / "cache",
                objdump=str(objdump),
            )
            self.assertEqual(report["exact_forces"], ["p1:w12=c17,p1:w19=c15"])
            self.assertEqual(report["minimum_forces_to_exact"], 2)

    def test_the_sweep_accepts_a_force_plan_file(self) -> None:
        from decomp_workbench.oracle_cli import _load_plan

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            plan = plan_force_experiment(log(), {"s1": "s3"})
            path.write_text(json.dumps(plan), encoding="utf-8")
            loaded = _load_plan(str(path))
            self.assertEqual(loaded["forces"][0]["force"], "p1:w12=c17")
            path.write_text(json.dumps({"schema": "other"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "neither"):
                _load_plan(str(path))

    def test_no_substitution_is_a_usage_error(self) -> None:
        status, _, stderr = self.run_cli(["oracle", "force-plan", str(FIXTURE)])
        self.assertEqual(status, 2)
        self.assertIn("--substitute", stderr)


if __name__ == "__main__":
    unittest.main()
