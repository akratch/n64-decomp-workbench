"""A force control owns object rows only if you measure which ones moved.

The campaign prototype this generalizes zipped two disassemblies by position.
That is right exactly when the force changes no instruction count and the
candidate has not drifted from the target -- neither of which holds in the case
the tool exists for. These tests hold the two corrections: runs come from an
alignment, and the target join goes through the alignment `compare` publishes.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.force_rows import build_force_rows, group_moved_runs
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import build_view

PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]
BODY = ["li v0,33", "addu v1,v0,s0", "lw t7,8(s0)", "addu a0,t7,v1", "sw a0,4(s0)"]

BASELINE = [*PROLOGUE, *BODY, *EPILOGUE]
# One register moved, at two sites: the shape of a colour force.
FORCED = [
    *PROLOGUE,
    "li v0,33",
    "addu v1,v0,s0",
    "lw t8,8(s0)",
    "addu a0,t8,v1",
    "sw a0,4(s0)",
    *EPILOGUE,
]
# The target differs from the baseline earlier, so a positional target join
# would name the wrong instruction.
TARGET = [*PROLOGUE, "nop", *BODY, *EPILOGUE]


def instructions(rows: list[str]) -> Any:
    return parse_disassembly(assemble(rows, symbol="demo"), symbol="demo")


class RunGroupingTests(unittest.TestCase):
    def view(self, forced: list[str]) -> Any:
        return build_view(
            instructions(BASELINE),
            instructions(forced),
            target_name="baseline",
            candidate_name="forced",
        )

    def test_a_short_matched_stretch_stays_inside_one_run(self) -> None:
        view = self.view(FORCED)
        self.assertEqual(group_moved_runs(view, gap=3), [(6, 7)])

    def test_gap_zero_reports_strictly_contiguous_runs(self) -> None:
        forced = [*PROLOGUE, "li v0,34", "addu v1,v0,s0", "lw t8,8(s0)"]
        forced += ["addu a0,t8,v1", "sw a0,4(s0)", *EPILOGUE]
        view = self.view(forced)
        self.assertEqual(group_moved_runs(view, gap=0), [(4, 4), (6, 7)])
        self.assertEqual(group_moved_runs(view, gap=3), [(4, 7)])

    def test_a_negative_gap_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            group_moved_runs(self.view(FORCED), gap=-1)


class ForceRowsTests(unittest.TestCase):
    def build(self, forced: list[str], **kwargs: Any) -> Any:
        return build_force_rows(
            instructions(BASELINE),
            instructions(forced),
            force="p1:w9=c30",
            baseline_name="baseline.o",
            forced_name="forced.o",
            **kwargs,
        )

    def test_moved_rows_are_grouped_and_counted(self) -> None:
        result = self.build(FORCED)
        self.assertFalse(result.inert)
        self.assertEqual(result.moved_rows, 2)
        self.assertEqual(len(result.runs), 1)
        run = result.runs[0]
        self.assertEqual((run.start, run.end), (6, 7))
        self.assertEqual((run.baseline_start, run.baseline_end), (6, 7))

    def test_an_unchanged_build_is_reported_as_byte_inert(self) -> None:
        result = self.build(BASELINE)
        self.assertTrue(result.inert)
        self.assertEqual(result.moved_rows, 0)
        self.assertEqual(result.runs, ())

    def test_a_changed_instruction_count_is_aligned_not_zipped(self) -> None:
        # A positional diff would call every row after the insertion moved.
        forced = [*PROLOGUE, "nop", *BODY, *EPILOGUE]
        result = self.build(forced)
        self.assertEqual(result.moved_rows, 1)
        self.assertEqual(len(result.runs), 1)
        self.assertTrue(
            any("changed the instruction count" in text for text in result.warnings),
            result.warnings,
        )

    def test_the_target_join_uses_the_published_row_numbers(self) -> None:
        result = self.build(FORCED, target=instructions(TARGET), target_name="target.o")
        run = result.runs[0]
        # The baseline row 6 sits one row later in the target alignment,
        # because the target holds an extra instruction before it.
        self.assertEqual(run.baseline_start, 6)
        self.assertEqual(run.compare_start, 7)
        self.assertIn("lw", run.target_text or "")
        self.assertIn("t7", run.target_text or "")


class ForceRowsCommandTests(unittest.TestCase):
    def run_command(self, *flags: str, forced: list[str] = FORCED) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for name, rows in (
                ("baseline", BASELINE),
                ("forced", forced),
                ("target", TARGET),
            ):
                path = root / f"{name}.objdump"
                path.write_text(assemble(rows, symbol="demo"), encoding="utf-8")
                paths.append(str(path))
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                status = main(["force-rows-dumps", paths[0], paths[1], *flags])
            return status, stdout.getvalue() + stderr.getvalue()

    def test_a_run_is_printed_with_its_class_and_evidence(self) -> None:
        status, output = self.run_command("--force", "p1:w9=c30")
        self.assertEqual(status, 0, output)
        self.assertIn("force=p1:w9=c30", output)
        self.assertIn("rows 6-7", output)
        self.assertIn("baseline:", output)

    def test_an_inert_control_says_so_instead_of_printing_nothing(self) -> None:
        status, output = self.run_command("--force", "p1:w9=s", forced=BASELINE)
        self.assertEqual(status, 0, output)
        self.assertIn("BYTE-INERT", output)
        self.assertIn("evidence, not a failed run", output)

    def test_an_unqualified_force_is_refused_before_any_work(self) -> None:
        status, output = self.run_command("--force", "w9=c30")
        self.assertEqual(status, 2)
        self.assertIn("phase-qualified", output)

    def test_json_publishes_the_schema_and_the_control(self) -> None:
        status, output = self.run_command("--force", "p2:w55=c2", "--json")
        self.assertEqual(status, 0, output)
        payload: dict[str, Any] = json.loads(output)
        self.assertEqual(payload["schema"], "decomp-workbench-force-rows-v1")
        self.assertEqual(payload["force"], "p2:w55=c2")
        self.assertFalse(payload["inert"])
        self.assertEqual(payload["runs"][0]["start"], 6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
