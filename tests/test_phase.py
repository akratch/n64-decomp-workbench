"""What a phase report may never do, each pinned to what it once did.

Four campaign incidents live here:

* a band scorer's eight named ranges left 105 rows of a 4641-row object
  unnamed, so a mismatch there was absent from every total and one candidate
  reported ``RAW=1`` with two real mismatches;
* a headline "39 -> 29" was really 1045 positional rows, because the scorer
  quotiented a global ring rotation away and printed the small number bare;
* three stages built ring-flipped objects and recorded them as wins, because
  no screen line carried the coset;
* a small slot's best-fit permutation, measured in isolation, classified a
  working construct as ring-foreign and dropped it from every catalogue.
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
from decomp_workbench.phase import (
    DEFAULT_RING,
    Coset,
    PhaseError,
    Slot,
    build_phase_report,
    parse_ring,
    parse_slots,
    ring_cosets,
    validate_partition,
)
from decomp_workbench.shift_align import build_shift_diff

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]

#: A rotation of the four-register scratch ring: what a "coset-flipped"
#: candidate looks like. `$f4 -> $f8`, `$f6 -> $f10`, and back.
ROTATION = {"f4": "f8", "f6": "f10", "f8": "f4", "f10": "f6"}


def float_traffic(count: int) -> list[str]:
    """Return ring-using rows, one load or store per ring register."""

    registers = [name.lstrip("$") for name in DEFAULT_RING]
    rows: list[str] = []
    for index in range(count):
        register = registers[index % len(registers)]
        opcode = "lwc1" if index % 2 == 0 else "swc1"
        rows.append(f"{opcode} {register},{(index % 12) * 4}(sp)")
    return rows


def rotate(lines: list[str]) -> list[str]:
    rotated: list[str] = []
    for line in lines:
        opcode, _, operands = line.partition(" ")
        parts = operands.split(",")
        parts = [ROTATION.get(part, part) for part in parts]
        rotated.append(f"{opcode} {','.join(parts)}")
    return rotated


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def rows(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol=SYMBOL), symbol=SYMBOL)


def report(target: list[str], candidate: list[str], **kwargs: object):
    left, right = rows(target), rows(candidate)
    shift = build_shift_diff(left, right)
    return build_phase_report(left, right, shift=shift, **kwargs)  # type: ignore[arg-type]


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class SlotPartitionTests(unittest.TestCase):
    def test_a_hole_names_the_rows_it_would_have_swallowed(self) -> None:
        """The verified defect: 3234, 3285..3387 and 3403..3404 named nowhere."""

        table = parse_slots(
            "B1=7..1573,B2=1574..2038,W=2039..2110,B3=2111..3233,"
            "IR=3235..3284,CP=3388..3402,MD=3405..3450,RS=3451..4633"
        )
        with self.assertRaises(PhaseError) as raised:
            validate_partition(table, first=0, last=4640)

        message = str(raised.exception)
        self.assertIn("belong to no slot", message)
        self.assertIn("3285..3387 (103 row(s))", message)
        self.assertIn("3403..3404", message)
        self.assertIn("0..6", message)

    def test_an_overlap_is_an_error_because_it_counts_a_row_twice(self) -> None:
        table = (Slot("a", 0, 10), Slot("b", 8, 20))
        with self.assertRaises(PhaseError) as raised:
            validate_partition(table, first=0, last=20)
        self.assertIn("overlap at rows 8..10", str(raised.exception))

    def test_the_default_slot_table_cannot_have_a_hole(self) -> None:
        item = report(body(*float_traffic(12)), body(*float_traffic(12)))
        self.assertEqual(len(item.slots), 1)
        self.assertEqual(item.slots[0].slot.start, 0)
        self.assertEqual(item.slots[0].slot.stop, item.target_rows - 1)

    def test_a_malformed_slot_says_how_to_write_one(self) -> None:
        with self.assertRaises(PhaseError) as raised:
            parse_slots("B1=7-1573")
        self.assertIn("NAME=LO..HI", str(raised.exception))


class CosetTests(unittest.TestCase):
    def test_the_paired_family_is_the_four_physically_plausible_cosets(self) -> None:
        cosets = ring_cosets(DEFAULT_RING, family="paired")
        self.assertEqual(len(cosets), 4)
        self.assertTrue(cosets[0].is_identity)

    def test_the_full_family_is_every_permutation_identity_first(self) -> None:
        cosets = ring_cosets(DEFAULT_RING, family="all")
        self.assertEqual(len(cosets), 24)
        self.assertTrue(cosets[0].is_identity)

    def test_a_rotated_candidate_reports_its_coset_and_both_counts(self) -> None:
        """ "39 -> 29" was 1045 positional. Never print the small one alone."""

        traffic = float_traffic(24)
        item = report(body(*traffic), body(*rotate(traffic)))

        (slot,) = item.slots
        self.assertFalse(slot.coset.is_identity)
        self.assertEqual(slot.quotiented, 0)
        self.assertEqual(slot.positional, len(traffic))
        self.assertFalse(item.quotiented_is_bare)

    def test_the_report_refuses_to_print_a_bare_free_count(self) -> None:
        from decomp_workbench.phase import coset_warning, phase_lines

        traffic = float_traffic(24)
        item = report(body(*traffic), body(*rotate(traffic)))
        text = "\n".join(phase_lines(item))

        self.assertIn("free=0 [COSET", text)
        self.assertIn(f"positional {item.positional}]", text)
        self.assertIn("COSET:", coset_warning(item) or "")

    def test_an_identity_candidate_prints_free_without_a_caveat(self) -> None:
        from decomp_workbench.phase import coset_warning, phase_lines

        traffic = float_traffic(24)
        item = report(body(*traffic), body(*traffic))
        text = "\n".join(phase_lines(item))

        self.assertTrue(item.quotiented_is_bare)
        self.assertIn("every slot at the identity coset", text)
        self.assertIsNone(coset_warning(item))

    def test_each_slot_carries_its_own_coset(self) -> None:
        """The state is a vector: eight sub-zones rotate independently."""

        first = float_traffic(12)
        second = float_traffic(12)
        target = body(*first, *second)
        candidate = body(*first, *rotate(second))
        last = len(rows(target)) - 1
        table = (Slot("head", 0, 13), Slot("tail", 14, last))

        item = report(target, candidate, slots=table)

        head, tail = item.slots
        self.assertTrue(head.coset.is_identity)
        self.assertFalse(tail.coset.is_identity)
        self.assertEqual(item.phase_vector[0], "id")


class RingTests(unittest.TestCase):
    def test_any_register_pool_may_be_the_ring(self) -> None:
        """The integer temporaries rotate too, and it is the same fact."""

        self.assertEqual(parse_ring("$t6,$t7,$t8,$t9"), ("$t6", "$t7", "$t8", "$t9"))
        self.assertEqual(parse_ring("f4, f6"), ("$f4", "$f6"))

    def test_a_short_register_never_matches_inside_a_longer_one(self) -> None:
        """A substring rewrite would turn `$f10` into `$f80` and lie about it."""

        coset = Coset(ring=("$f1", "$f2"), image=("$f2", "$f1"))
        self.assertEqual(coset.apply("lwc1 $f10,8($sp)"), "lwc1 $f10,8($sp)")
        self.assertEqual(coset.apply("lwc1 $f1,8($sp)"), "lwc1 $f2,8($sp)")

    def test_a_ring_of_one_has_nothing_to_report(self) -> None:
        with self.assertRaises(PhaseError) as raised:
            parse_ring("$f4")
        self.assertIn("at least two registers", str(raised.exception))

    def test_an_unknown_register_names_both_example_rings(self) -> None:
        with self.assertRaises(PhaseError) as raised:
            parse_ring("$q9")
        message = str(raised.exception)
        self.assertIn("$f4,$f6,$f8,$f10", message)
        self.assertIn("$t6,$t7,$t8,$t9", message)


class EvidenceTests(unittest.TestCase):
    def test_a_slot_with_no_ring_evidence_is_not_labelled_identity(self) -> None:
        """A best fit over zero informative rows is not a measurement."""

        target = body(*[f"addiu t0,t0,{index}" for index in range(12)])
        item = report(target, target)

        (slot,) = item.slots
        self.assertEqual(slot.informative, 0)
        self.assertEqual(slot.coset_evidence, "no-evidence")

    def test_min_evidence_raises_the_bar_for_calling_a_slot_measured(self) -> None:
        traffic = float_traffic(24)
        target, candidate = body(*traffic), body(*rotate(traffic))

        measured = report(target, candidate)
        guarded = report(target, candidate, minimum_evidence=1000)

        self.assertEqual(measured.slots[0].coset_evidence, "measured")
        self.assertEqual(guarded.slots[0].coset_evidence, "no-evidence")
        # Refusing to name a coset must not quietly improve the score.
        self.assertEqual(guarded.slots[0].quotiented, guarded.slots[0].positional)

    def test_a_context_object_fixes_the_coset_the_candidate_is_scored_at(self) -> None:
        """Screened in isolation the slot lands at its own best fit and reads clean.

        Scored on a context that already carries the wanted rotation, the same
        object's real cost shows -- the false negative that hid a whole prior
        stage's result.
        """

        traffic = float_traffic(24)
        target = body(*traffic)
        candidate = body(*rotate(traffic))
        context = body(*traffic)

        alone = report(target, candidate)
        in_context = report(
            target,
            candidate,
            context=rows(context),
            context_shift=build_shift_diff(rows(target), rows(context)),
            context_name="context.o",
        )

        self.assertEqual(alone.slots[0].quotiented, 0)
        self.assertEqual(in_context.slots[0].coset_evidence, "fixed-by-context")
        self.assertEqual(in_context.slots[0].quotiented, len(traffic))


class ShiftAndGuardTests(unittest.TestCase):
    def test_an_inserted_instruction_does_not_shift_every_later_row(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        shifted = list(target)
        shifted.insert(6, "nop")

        item = report(target, shifted)

        self.assertEqual(item.instruction_delta, 1)
        self.assertEqual(item.positional, 0)
        self.assertEqual(item.quotiented, 0)

    def test_healed_and_broken_are_separate_facts_not_one_delta(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        previous = list(target)
        previous[4] = "lwc1 f8,4(sp)"
        previous[5] = "swc1 f10,8(sp)"
        candidate = list(target)
        candidate[9] = "lwc1 f8,4(sp)"

        item = report(
            target,
            candidate,
            baseline=rows(previous),
            baseline_shift=build_shift_diff(rows(target), rows(previous)),
            baseline_name="previous.o",
        )

        self.assertEqual(item.healed, 2)
        self.assertEqual(item.broken, 1)

    def test_detail_bounds_the_healed_and_broken_row_lists(self) -> None:
        """A thousand row numbers on a terminal is not evidence anybody reads."""

        from decomp_workbench.phase import phase_lines

        traffic = float_traffic(24)
        target = body(*traffic)
        previous = [
            line.replace("f4,", "f8,") if "f4," in line else line for line in target
        ]
        item = report(
            target,
            target,
            baseline=rows(previous),
            baseline_shift=build_shift_diff(rows(target), rows(previous)),
            baseline_name="previous.o",
        )
        text = "\n".join(phase_lines(item, detail=True))

        self.assertIn("collapsed into runs", text)
        self.assertIn("broke none", text)
        self.assertRegex(text, r"healed \d+ row\(s\):")


class PhaseCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _dump(self, name: str, lines: list[str]) -> str:
        path = self.root / name
        path.write_text(assemble(lines, symbol=SYMBOL), encoding="utf-8")
        return str(path)

    def test_a_shifted_candidate_is_flagged_and_still_scored(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        shifted = list(target)
        shifted.insert(6, "nop")

        status, stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("candidate.objdump", shifted),
            ]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("SHIFTED", stdout)
        self.assertIn("insertion-only", stdout)

    def test_a_large_ring_falls_back_to_paired_cosets_with_a_notice(self) -> None:
        """An 8-register ring must not error when --cosets is unspecified."""

        traffic = float_traffic(24)
        target = body(*traffic)

        status, stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("t8.objdump", target),
                self._dump("c8.objdump", target),
                "--ring",
                "$t2,$t3,$t4,$t5,$t6,$t7,$t8,$t9",
            ]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("paired cosets", stderr)

    def test_require_ni_refuses_a_candidate_of_the_wrong_length(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        shifted = list(target)
        shifted.insert(6, "nop")

        status, _stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("candidate.objdump", shifted),
                "--require-ni",
            ]
        )

        self.assertEqual(status, 2)
        self.assertIn("--require-ni", stderr)
        self.assertIn("real instruction", stderr)

    def test_a_pinned_base_refuses_a_table_built_from_another_base(self) -> None:
        traffic = float_traffic(12)
        target = self._dump("target.objdump", body(*traffic))
        candidate = self._dump("candidate.objdump", body(*traffic))
        source = self.root / "champion.c"
        source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

        status, _stdout, stderr = run_cli(
            [
                "phase-dumps",
                target,
                candidate,
                "--base",
                str(source),
                "--require-base",
                "0000000000",
            ]
        )

        self.assertEqual(status, 2)
        self.assertIn("built from a different base", stderr)

    def test_the_slot_table_can_come_from_a_file(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        last = len(rows(target)) - 1
        table = self.root / "slots.txt"
        table.write_text(
            f"# named zones\nhead=0..13\ntail=14..{last}\n", encoding="utf-8"
        )

        status, stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("candidate.objdump", target),
                "--slots-from",
                str(table),
                "--json",
            ]
        )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual([slot["slot"] for slot in payload["slots"]], ["head", "tail"])

    def test_a_slot_hole_is_reported_as_a_usage_error(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)

        status, _stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("candidate.objdump", target),
                "--slots",
                "head=0..5,tail=10..28",
            ]
        )

        self.assertEqual(status, 2)
        self.assertIn("belong to no slot", stderr)

    def test_many_candidates_produce_a_ranked_phase_census(self) -> None:
        traffic = float_traffic(24)
        target = body(*traffic)
        rotated = body(*rotate(traffic))

        status, stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("clean.objdump", target),
                self._dump("rotated.objdump", rotated),
            ]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("COSET", stdout)
        self.assertIn("rank on positional", stdout)

    def test_a_census_names_the_shared_directory_once(self) -> None:
        """The first column padded to a long absolute path ate the table.

        Campaign objects live under one long directory, so a census padded its
        candidate column to that width and `--width` then elided the numbers,
        leaving a table of paths and no data.
        """

        traffic = float_traffic(24)
        target = body(*traffic)

        status, stdout, stderr = run_cli(
            [
                "phase-dumps",
                self._dump("target.objdump", target),
                self._dump("clean.objdump", target),
                self._dump("rotated.objdump", body(*rotate(traffic))),
            ]
        )

        self.assertEqual(status, 0, stderr)
        self.assertIn("paths are relative to", stdout)
        table = [line for line in stdout.splitlines() if line.startswith("clean")]
        self.assertTrue(table, stdout)
        self.assertTrue(table[0].startswith("clean.objdump"), table[0])


if __name__ == "__main__":
    unittest.main()


class BlindTotalTests(unittest.TestCase):
    """When every slot is no-evidence the total row must not read 'identity'.

    Regression: an integer-only function scored against the float ring
    printed per-slot no-evidence but a total labelled identity, which reads
    as a measured identity phase (ge007-mp-watch-menu campaign).
    """

    def test_all_blind_slots_make_the_total_no_evidence(self) -> None:
        from decomp_workbench.phase import phase_lines

        target = body(*[f"addiu t0,t0,{index}" for index in range(12)])
        item = report(target, target)
        (slot,) = item.slots
        self.assertEqual(slot.coset_evidence, "no-evidence")

        text = "\n".join(phase_lines(item))
        total_line = next(
            line for line in text.splitlines() if line.startswith("total")
        )
        self.assertIn("no-evidence", total_line)
        self.assertNotIn("identity", total_line)
