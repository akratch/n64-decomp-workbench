"""Reading a row by number is the most common action, and had no command.

Three stages of one recorded campaign each wrote their own objdump-scraping
script to print "rows 850-875 of both sides, side by side" -- and each invented
its own row numbering, none of which was the numbering the tool publishes as
`aligned_row`. A dossier that says "the gate is the `add.s` at row 863" is then
one script away from being unreadable by the next reader.

`window` shares the aligner, so the row numbers quoted in a dossier and the
rows this command prints are the same rows. These tests hold that promise and
the selector's edges.
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
from decomp_workbench.compare import compare_instructions
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view_cli import parse_row_ranges

PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)", "sw s0,24(sp)", "move s0,a0"]
EPILOGUE = ["lw ra,28(sp)", "lw s0,24(sp)", "jr ra", "addiu sp,sp,32"]
TARGET = [*PROLOGUE, "li v0,33", "addu v1,v0,s0", "lw t7,8(s0)", *EPILOGUE]
CANDIDATE = [*PROLOGUE, "li v0,33", "addu v1,v0,s0", "lw t8,8(s0)", *EPILOGUE]


class RowSelectorTests(unittest.TestCase):
    def test_a_single_row_and_a_range_both_parse(self) -> None:
        self.assertEqual(parse_row_ranges(["863"]), [(863, 863)])
        self.assertEqual(parse_row_ranges(["850-875"]), [(850, 875)])
        self.assertEqual(
            parse_row_ranges(["1-2", " 9 "]),
            [(1, 2), (9, 9)],
        )

    def test_a_malformed_or_backwards_selector_is_rejected(self) -> None:
        for value in ("", "a-b", "5-", "-3", "9-4", "1-2-3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_row_ranges([value])


class WindowCommandTests(unittest.TestCase):
    def dumps(self, root: Path) -> tuple[Path, Path]:
        target = root / "target.objdump"
        candidate = root / "candidate.objdump"
        target.write_text(assemble(TARGET, symbol="demo"), encoding="utf-8")
        candidate.write_text(assemble(CANDIDATE, symbol="demo"), encoding="utf-8")
        return target, candidate

    def run_window(self, *flags: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.dumps(Path(temporary))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    ["window-dumps", str(target), str(candidate), *flags],
                )
        return status, stdout.getvalue()

    def payload(self, *flags: str) -> dict[str, Any]:
        status, output = self.run_window("--json", *flags)
        self.assertEqual(status, 0)
        return dict(json.loads(output))

    def test_the_row_numbers_are_the_ones_compare_publishes(self) -> None:
        """The whole point: one row vocabulary, two commands.

        `compare --json` names the differing row; `window` prints that number
        and no other, so a dossier and a terminal agree without translation.
        """

        item = compare_instructions(
            parse_disassembly(assemble(TARGET, symbol="demo"), symbol="demo"),
            parse_disassembly(assemble(CANDIDATE, symbol="demo"), symbol="demo"),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )
        rows = [site["aligned_row"] for site in item.aligned_diff_sites]
        self.assertTrue(rows)

        payload = self.payload("--rows", str(rows[0]))
        self.assertEqual([row["aligned_row"] for row in payload["rows"]], [rows[0]])
        self.assertEqual(payload["differing"], 1)
        self.assertEqual(payload["rows"][0]["substitutions"], [["t7", "t8"]])

    def test_a_matching_row_is_printed_unmarked_and_a_differing_one_marked(
        self,
    ) -> None:
        status, output = self.run_window("--rows", "0-8", "--color", "never")

        self.assertEqual(status, 0)
        marked = [line for line in output.splitlines() if " * " in line]
        self.assertEqual(len(marked), 1)
        self.assertIn("t7", marked[0])
        self.assertIn("t8", marked[0])
        self.assertIn("t7->t8", marked[0])

    def test_several_ranges_are_printed_in_the_order_requested(self) -> None:
        payload = self.payload("--rows", "6", "--rows", "0-1")

        self.assertEqual([row["aligned_row"] for row in payload["rows"]], [6, 0, 1])
        self.assertEqual(payload["requested_rows"], [[6, 6], [0, 1]])

    def test_a_range_past_the_end_is_clamped_and_says_so(self) -> None:
        status, output = self.run_window("--rows", "8-9999", "--color", "never")

        self.assertEqual(status, 0)
        self.assertIn("clamped to the last row", output)

    def test_a_range_entirely_past_the_end_is_not_silent(self) -> None:
        """An empty screen is indistinguishable from a clean window."""

        status, output = self.run_window("--rows", "9000-9001", "--color", "never")

        self.assertEqual(status, 0)
        self.assertIn("past the end", output)

    def test_the_header_names_the_alignment_it_indexes_into(self) -> None:
        status, output = self.run_window("--rows", "0", "--color", "never")

        self.assertEqual(status, 0)
        self.assertIn("aligned_rows=", output.splitlines()[0])

    def test_rows_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.dumps(Path(temporary))
            with self.assertRaises(SystemExit) as raised:
                with contextlib.redirect_stderr(io.StringIO()):
                    main(["window-dumps", str(target), str(candidate)])

        self.assertEqual(raised.exception.code, 2)

    def test_a_bad_selector_is_an_input_error_not_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.dumps(Path(temporary))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = main(
                    [
                        "window-dumps",
                        str(target),
                        str(candidate),
                        "--rows",
                        "20-10",
                    ]
                )

        self.assertEqual(status, 2)
        self.assertIn("backwards", stderr.getvalue())

    def test_a_missing_symbol_is_an_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.dumps(Path(temporary))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = main(
                    [
                        "window-dumps",
                        str(target),
                        str(candidate),
                        "--rows",
                        "0",
                        "--symbol",
                        "absent",
                    ]
                )

        self.assertEqual(status, 2)
        self.assertIn("error:", stderr.getvalue())

    def test_the_grouped_spelling_reaches_the_same_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target, candidate = self.dumps(Path(temporary))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "object",
                        "window-dumps",
                        str(target),
                        str(candidate),
                        "--rows",
                        "0",
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-window-v1")


if __name__ == "__main__":
    unittest.main()
