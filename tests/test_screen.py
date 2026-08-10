"""The four facts one sweep line has to carry, and the two nobody printed.

Every stage of one campaign wrote its own screen line. Three of them built
objects whose scratch ring had rotated, read them through a coset-quotienting
band scorer, and recorded them as wins, because no line carried the coset. A
separate stage lost the distinction between a killed stack slot and a
relocated one, because screens printed ``ld1184`` and never ``st1184``.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.screen import build_screen_line

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]

ROTATION = {"f4": "f8", "f6": "f10", "f8": "f4", "f10": "f6"}


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def rows(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol=SYMBOL), symbol=SYMBOL)


def rotate(lines: list[str]) -> list[str]:
    rotated = []
    for line in lines:
        opcode, _, operands = line.partition(" ")
        rotated.append(
            f"{opcode} "
            + ",".join(ROTATION.get(part, part) for part in operands.split(","))
        )
    return rotated


def fake_dump(text: str) -> Callable[..., tuple[str, list[Instruction]]]:
    def _dump(
        path: str | Path,
        *,
        objdump: str | None = None,
        symbol: str | None = None,
        section: str = ".text",
    ) -> tuple[str, list[Instruction]]:
        return text, parse_disassembly(text, symbol=symbol)

    return _dump


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


TRAFFIC = ["lwc1 f4,1184(sp)", "swc1 f6,1184(sp)", "lwc1 f8,16(sp)"]


class ScreenLineTests(unittest.TestCase):
    def test_stores_are_counted_apart_from_loads(self) -> None:
        """The store count is what separated a kill from a relocation."""

        line = build_screen_line(rows(body(*TRAFFIC)), label=SYMBOL)

        self.assertEqual((line.loads, line.stores), (2, 1))
        self.assertIn("ld=2", line.render())
        self.assertIn("st=1", line.render())

    def test_a_slot_narrows_both_counts_and_labels_them(self) -> None:
        line = build_screen_line(rows(body(*TRAFFIC)), label=SYMBOL, slot=1184)

        self.assertEqual((line.loads, line.stores), (1, 1))
        self.assertIn("ld1184=1 st1184=1", line.render())

    def test_the_line_carries_the_frame_and_the_true_length(self) -> None:
        line = build_screen_line(rows(body(*TRAFFIC)), label=SYMBOL)

        self.assertEqual(line.frame, -32)
        self.assertEqual(line.instructions, len(body(*TRAFFIC)))

    def test_a_rotated_ring_is_named_and_cautioned(self) -> None:
        traffic = [
            "lwc1 f4,8(sp)",
            "lwc1 f6,12(sp)",
            "swc1 f8,16(sp)",
            "swc1 f10,20(sp)",
        ]
        target = rows(body(*traffic))
        candidate = rows(body(*rotate(traffic)))

        line = build_screen_line(candidate, label=SYMBOL, target=target)

        self.assertTrue(line.rotated)
        self.assertIn("coset=", line.render())
        caution = line.caution()
        assert caution is not None
        self.assertIn("Do not record it as a win", caution)
        self.assertEqual(line.quotiented, 0)
        self.assertEqual(line.positional, len(traffic))

    def test_an_unrotated_candidate_says_identity_and_nothing_else(self) -> None:
        target = rows(body(*TRAFFIC))

        line = build_screen_line(target, label=SYMBOL, target=target)

        self.assertFalse(line.rotated)
        self.assertIsNone(line.caution())
        self.assertIn("coset=id", line.render())

    def test_an_object_with_no_ring_row_is_not_reported_as_rotated(self) -> None:
        """`?` is "nothing to read", not "the ring moved".

        An object holding no ring-carrying row reads `coset=?`, and treating
        that as a rotation printed the coset caution over whole sweeps of
        integer objects that had no ring to rotate. Found by the sweep-ingest
        report, which prints one caution for a whole family.
        """

        target = rows(body("sw ra,8(sp)", "lw ra,8(sp)"))

        line = build_screen_line(target, label=SYMBOL, target=target)

        self.assertEqual(line.coset, "?")
        self.assertFalse(line.rotated)
        self.assertIsNone(line.caution())

    def test_without_a_target_the_coset_is_declared_unmeasured(self) -> None:
        line = build_screen_line(rows(body(*TRAFFIC)), label=SYMBOL)

        self.assertIsNone(line.coset)
        self.assertNotIn("coset=", line.render())
        assert line.coset_unavailable is not None
        self.assertIn("not measured", line.coset_unavailable)


class ScoreScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _object(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(b"\x7fELF placeholder")
        return str(path)

    def test_score_prints_the_screen_line_beside_the_headline(self) -> None:
        traffic = ["lwc1 f4,1184(sp)", "swc1 f6,1184(sp)"]
        text = assemble(body(*traffic), symbol=SYMBOL)
        target, candidate = self._object("target.o"), self._object("candidate.o")

        with mock.patch(
            "decomp_workbench.compare.dump_object", side_effect=fake_dump(text)
        ):
            status, stdout, stderr = run_cli(
                ["score", target, candidate, "--slot", "1184"]
            )

        self.assertEqual(status, 0, stderr)
        self.assertIn("screen: sha=", stdout)
        self.assertIn("ld1184=1 st1184=1", stdout)
        self.assertIn("coset=id", stdout)

    def test_a_rotated_candidate_is_cautioned_on_the_score_screen(self) -> None:
        traffic = [
            "lwc1 f4,8(sp)",
            "lwc1 f6,12(sp)",
            "swc1 f8,16(sp)",
            "swc1 f10,20(sp)",
        ]
        target_text = assemble(body(*traffic), symbol=SYMBOL)
        candidate_text = assemble(body(*rotate(traffic)), symbol=SYMBOL)
        target, candidate = self._object("target.o"), self._object("candidate.o")

        def dump(
            path: str | Path,
            *,
            objdump: str | None = None,
            symbol: str | None = None,
            section: str = ".text",
        ) -> tuple[str, list[Instruction]]:
            text = target_text if str(path) == target else candidate_text
            return text, parse_disassembly(text, symbol=symbol)

        with mock.patch("decomp_workbench.compare.dump_object", dump):
            status, stdout, stderr = run_cli(["score", target, candidate, "--json"])

        self.assertEqual(status, 1, stderr)
        payload = json.loads(stdout)
        self.assertNotEqual(payload["screen"]["coset"], "id")
        self.assertIn("Do not record it as a win", payload["screen"]["coset_caution"])


if __name__ == "__main__":
    unittest.main()
