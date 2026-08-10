"""A commutative classification that does nothing is not a finding.

Two campaign incidents:

* the class count printed on hundreds of build lines with no lever attached to
  it, so nobody ever acted on it;
* a wrong operand order in the source left the arithmetic row byte-identical
  and showed up only in the two operand loads above it, so the classifier
  flagged the loads as an ordinary register difference and sent the reader to
  the allocator for a front-end question. One stage found the one-line fix by
  hand-reading; another measured the class as worth fifteen rows.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Comparison, Instruction
from decomp_workbench.objdump import parse_disassembly

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def rows(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol=SYMBOL), symbol=SYMBOL)


def comparison(target: list[str], candidate: list[str]) -> Comparison:
    return compare_instructions(
        rows(target),
        rows(candidate),
        target_name="target",
        candidate_name="candidate",
        symbol=SYMBOL,
    )


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class CommutativeFindingTests(unittest.TestCase):
    def test_a_swapped_pair_names_the_operands_and_the_edit(self) -> None:
        target = body("or t2,t0,t1")
        candidate = body("or t2,t1,t0")

        item = comparison(target, candidate)

        (finding,) = item.commutative_findings
        self.assertEqual(finding["kind"], "operand-order")
        self.assertEqual(finding["sources"], ["t0", "t1"])
        self.assertIn("expression shape", finding["lever"])
        self.assertIn("not register", finding["lever"])

    def test_a_clean_arithmetic_row_with_crossed_loads_is_found(self) -> None:
        """The row that differs is not the row to change.

        Both objects compute the same ``or``; the two operand loads above it
        are crossed, which is a swapped operand order in the source.
        """

        target = body("lw t0,8(sp)", "lw t1,12(sp)", "or t2,t0,t1")
        candidate = body("lw t1,8(sp)", "lw t0,12(sp)", "or t2,t0,t1")

        item = comparison(target, candidate)

        (finding,) = item.commutative_findings
        self.assertEqual(finding["kind"], "operand-load")
        self.assertEqual(finding["target"], finding["candidate"])
        self.assertEqual(
            [entry["register"] for entry in finding["definitions"]], ["t0", "t1"]
        )
        self.assertIn("operand loads", finding["lever"])
        self.assertIn("wrong repair", finding["lever"])

    def test_an_unrelated_register_difference_is_not_called_commutative(self) -> None:
        target = body("lw t0,8(sp)", "lw t1,12(sp)", "or t2,t0,t1")
        candidate = body("lw t0,8(sp)", "lw t1,16(sp)", "or t2,t0,t1")

        self.assertEqual(comparison(target, candidate).commutative_findings, [])

    def test_a_matching_pair_produces_no_finding(self) -> None:
        target = body("lw t0,8(sp)", "lw t1,12(sp)", "or t2,t0,t1")

        self.assertEqual(comparison(target, target).commutative_findings, [])

    def test_a_non_commutative_opcode_is_left_alone(self) -> None:
        """``subu`` is not commutative; crossed loads there mean something else."""

        target = body("lw t0,8(sp)", "lw t1,12(sp)", "subu t2,t0,t1")
        candidate = body("lw t1,8(sp)", "lw t0,12(sp)", "subu t2,t0,t1")

        self.assertEqual(comparison(target, candidate).commutative_findings, [])


class CommutativeRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _dump(self, name: str, lines: list[str]) -> str:
        path = self.root / name
        path.write_text(assemble(lines, symbol=SYMBOL), encoding="utf-8")
        return str(path)

    def test_compare_prints_the_lever_beside_the_count(self) -> None:
        target = self._dump(
            "target.objdump", body("lw t0,8(sp)", "lw t1,12(sp)", "or t2,t0,t1")
        )
        candidate = self._dump(
            "candidate.objdump", body("lw t1,8(sp)", "lw t0,12(sp)", "or t2,t0,t1")
        )

        status, stdout, stderr = run_cli(
            ["compare-dumps", target, candidate, "--symbol", SYMBOL]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("commutative operands: 1 site(s)", stdout)
        self.assertIn("visible only in the operand loads", stdout)
        self.assertIn("lever:", stdout)

    def test_the_findings_are_machine_readable(self) -> None:
        target = self._dump("target.objdump", body("or t2,t0,t1"))
        candidate = self._dump("candidate.objdump", body("or t2,t1,t0"))

        status, stdout, stderr = run_cli(
            ["compare-dumps", target, candidate, "--symbol", SYMBOL, "--json"]
        )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(len(payload["commutative_findings"]), 1)
        self.assertEqual(payload["commutative_findings"][0]["kind"], "operand-order")


if __name__ == "__main__":
    unittest.main()
