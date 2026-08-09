"""What a shifted candidate is allowed to cost.

Every property here is a bill one campaign paid. A single inserted instruction
turned an almost-finished object into an apparently catastrophic one eleven
separate times, because the scorer read candidate row N against target row N;
two more stages rediscovered the same gap independently. The banded scorers
that tried to compensate for it merged the two objects' relocation rows into
one set and dropped genuine mismatches near the shift boundary, and required a
human to read the insertion points off an alignment and retype them.
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
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.shift_align import (
    build_shift_diff,
    comparable_text,
    relocation_rows,
)

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]

#: A varied instruction stream. Alignment is a longest-common-subsequence
#: question, so a fixture built from thirty identical mnemonics has many equally
#: long alignments and the one difflib picks is arbitrary -- a property of the
#: fixture, not of the tool. Real function bodies are not like that, and
#: neither are these.
FORMS = (
    "addiu t0,t0,{n}",
    "or t1,t2,t3",
    "lw t4,{m}(sp)",
    "sll t5,t6,{s}",
    "and t7,t8,t9",
    "xor s0,s1,s2",
    "sw t3,{m}(sp)",
    "subu s3,s4,s5",
    "slt s6,s7,t0",
    "nor v0,v1,a0",
    "andi t9,t9,{n}",
    "addu s0,s1,s2",
    "sltu t2,t3,t4",
)


def stream(count: int) -> list[str]:
    """Return `count` distinct-looking instructions with varied mnemonics."""

    return [
        FORMS[index % len(FORMS)].format(
            n=index % 100, m=(index % 20) * 4, s=index % 31
        )
        for index in range(count)
    ]


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def rows(
    lines: list[str], *, relocations: dict[int, str] | None = None
) -> list[Instruction]:
    text = assemble(lines, symbol=SYMBOL, relocations=relocations)
    return parse_disassembly(text, symbol=SYMBOL)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ShiftToleranceTests(unittest.TestCase):
    def test_one_inserted_instruction_reads_as_one_instruction_away(self) -> None:
        """The whole point: 4640 against 4641 is not "rejected", it is "+1"."""

        lines = body(*stream(40))
        shifted = list(lines)
        shifted.insert(20, "nop")

        diff = build_shift_diff(rows(lines), rows(shifted))

        self.assertEqual((diff.replaced, diff.inserted, diff.deleted), (0, 1, 0))
        self.assertEqual(diff.rows_away, 1)
        self.assertTrue(diff.insertion_only)
        # The number the position-indexed scorers really printed for objects of
        # this shape, and the reason stage after stage abandoned them.
        self.assertGreater(diff.positional_mismatches, 20)

    def test_the_cut_list_comes_from_the_alignment_not_from_a_human(self) -> None:
        lines = body(*stream(20))
        shifted = list(lines)
        shifted.insert(9, "nop")

        diff = build_shift_diff(rows(lines), rows(shifted))

        self.assertEqual(diff.cuts, (9,))
        self.assertEqual(diff.pairing.candidate_row(8), 8)
        self.assertEqual(diff.pairing.candidate_row(9), 10)

    def test_a_deleted_instruction_is_not_the_compensable_shape(self) -> None:
        lines = body(*stream(20))
        shorter = [line for index, line in enumerate(lines) if index != 9]

        diff = build_shift_diff(rows(lines), rows(shorter))

        self.assertEqual(diff.deleted, 1)
        self.assertFalse(diff.insertion_only)

    def test_a_branch_over_an_insertion_is_not_a_mismatch(self) -> None:
        """A local branch encodes a row number, so a shift rewrites its word.

        Charging that as a difference manufactures mismatches out of correct
        code, which is what made a shifted candidate look hopeless even to a
        scorer that had noticed the shift.
        """

        lines = body("beq t0,t1,@9", *stream(10))
        shifted = list(lines)
        shifted.insert(5, "nop")
        shifted[2] = "beq t0,t1,@10"

        diff = build_shift_diff(rows(lines), rows(shifted))

        self.assertEqual(diff.paired_mismatches, 0)
        self.assertEqual(diff.rows_away, 1)

    def test_relocation_masking_keeps_the_two_row_spaces_apart(self) -> None:
        """The published "31" was really 33: two mismatches a merged set ate.

        The banded scorer built one set from the target's relocation rows and
        the candidate's, then tested *both* a target row and its shifted
        candidate counterpart against it. A row that is a relocation only on
        the other side, at the other index, disappears that way.
        """

        lines = body(*stream(20))
        relocated_row = 8
        target = rows(lines, relocations={relocated_row: "R_MIPS_LO16"})

        shifted = list(lines)
        shifted.insert(4, "nop")
        # A genuine difference at the target row immediately after the
        # relocated one -- the row the merged set silently swallows.
        broken_row = relocated_row + 1
        shifted[broken_row + 1] = "addiu t1,t1,999"
        candidate = rows(shifted, relocations={relocated_row + 1: "R_MIPS_LO16"})

        merged = relocation_rows(target) | relocation_rows(candidate)
        self.assertIn(broken_row, merged)

        diff = build_shift_diff(target, candidate)

        self.assertIn(broken_row, diff.paired_mismatch_rows)
        self.assertEqual(diff.relocation_masked, 1)

    def test_comparable_text_leaves_a_hexadecimal_immediate_alone(self) -> None:
        """`ori v0,v0,0x1234` ends in hex too; only a branch carries a row."""

        (instruction,) = parse_disassembly(
            assemble(["ori v0,v0,0x1234"], symbol=SYMBOL), symbol=SYMBOL
        )
        self.assertEqual(comparable_text(instruction), instruction.assembly)


class AlignCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _dump(self, name: str, lines: list[str]) -> str:
        path = self.root / name
        path.write_text(assemble(lines, symbol=SYMBOL), encoding="utf-8")
        return str(path)

    def test_the_report_states_the_positional_reading_it_replaces(self) -> None:
        lines = body(*stream(30))
        shifted = list(lines)
        shifted.insert(15, "nop")
        target = self._dump("target.objdump", lines)
        candidate = self._dump("candidate.objdump", shifted)

        status, stdout, stderr = run_cli(["align-dumps", target, candidate])

        self.assertEqual(status, 0, stderr)
        self.assertIn("1 instruction(s) away", stdout)
        self.assertIn("position-indexed comparison charges", stdout)
        self.assertIn("insertion-only", stdout)

    def test_many_candidates_produce_one_ranked_line_each(self) -> None:
        lines = body(*stream(30))
        near = list(lines)
        near.insert(15, "nop")
        far = [*lines[:5], *["nop"] * 8, *lines[5:]]
        target = self._dump("target.objdump", lines)
        first = self._dump("near.objdump", near)
        second = self._dump("far.objdump", far)

        status, stdout, stderr = run_cli(["align-dumps", target, second, first])

        self.assertEqual(status, 0, stderr)
        ranked = [
            line.split()[0]
            for line in stdout.splitlines()
            if line.startswith(str(self.root))
        ]
        self.assertEqual(ranked, [first, second])

    def test_the_window_tally_separates_insertions_before_from_inside(self) -> None:
        lines = body(*stream(30))
        shifted = list(lines)
        shifted.insert(20, "nop")
        shifted.insert(4, "nop")
        target = self._dump("target.objdump", lines)
        candidate = self._dump("candidate.objdump", shifted)

        status, stdout, stderr = run_cli(
            ["align-dumps", target, candidate, "--window", "10..25", "--json"]
        )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["window"]["before"], 1)
        self.assertEqual(payload["window"]["inside"], 1)

    def test_a_malformed_window_says_how_to_write_one(self) -> None:
        with self.assertRaises(SystemExit):
            run_cli(["align-dumps", "a", "b", "--window", "10-25"])


if __name__ == "__main__":
    unittest.main()
