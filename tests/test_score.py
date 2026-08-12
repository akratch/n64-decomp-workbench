"""Tests for `score`: byte-exact function scoring against ROM/object truth."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.score import (
    BETWEEN_RATIONALE,
    ControlSpec,
    ScoreError,
    ScoreSpec,
    TargetSpec,
    WordScore,
    build_guidance,
    label_addresses,
    parse_control_spec,
    read_rom_window,
    score_report,
    score_spec_from_dict,
    score_window,
    window_between,
    window_by_symbol,
    words_from_bytes,
)

# One section holding a visible function (funcA), a local/static function IDO
# stripped from the symbol table (hidden), and another visible function
# (funcB) -- the shape --between exists for.
SECTION_TEXT = """
00000000 <funcA>:
   0: 03e00008  jr $ra
   4: 00000000  nop

00000008 <hidden>:
   8: 27bdffe0  addiu $sp,$sp,-32
   c: 03e00008  jr $ra
  10: 00000000  nop

00000014 <funcB>:
  14: 03e00008  jr $ra
  18: 00000000  nop
"""

# One function with a relocation on its first word (the jal target is
# resolved by the linker, not this object) and a plain literal on the second.
RELOC_CANDIDATE_TEXT = """
00000000 <demo>:
   0: 0c000000  jal 0 <callee>
                        0: R_MIPS_26 callee
   4: 24020005  li $v0,5
   8: 03e00008  jr $ra
   c: 00000000  nop
"""


def fake_dump_object(
    section_text: str,
) -> Callable[..., tuple[str, list[Instruction]]]:
    """Return a `dump_object`-shaped stub driven entirely by parsed text.

    Mirrors real `dump_object` success behavior (symbol filtering, padding
    trim) without a subprocess or a real objdump binary, matching the
    convention `tests/test_input_diagnostics.py` and `tests/test_diagnosis.py`
    already use for object-shaped tests.
    """

    def _dump(
        path: str | Path,
        *,
        objdump: str | None = None,
        symbol: str | None = None,
        section: str = ".text",
    ) -> tuple[str, list[Instruction]]:
        instructions = parse_disassembly(section_text, symbol=symbol)
        if symbol and not instructions:
            raise RuntimeError(f"symbol {symbol!r} produced no instructions")
        return section_text, instructions

    return _dump


class WindowingTests(unittest.TestCase):
    def test_window_by_symbol_extracts_one_function(self) -> None:
        with mock.patch(
            "decomp_workbench.score.dump_object",
            side_effect=fake_dump_object(SECTION_TEXT),
        ):
            window = window_by_symbol("candidate.o", objdump=None, symbol="funcA")
        self.assertEqual(window.mode, "function")
        self.assertEqual(len(window.instructions), 2)
        self.assertEqual(window.size, 8)
        self.assertIsNone(window.note)

    def test_window_by_symbol_missing_symbol_suggests_between(self) -> None:
        with mock.patch(
            "decomp_workbench.score.dump_object",
            side_effect=fake_dump_object(SECTION_TEXT),
        ):
            with self.assertRaises(ScoreError) as raised:
                window_by_symbol("candidate.o", objdump=None, symbol="nope")
        self.assertIn("--between", str(raised.exception))

    def test_label_addresses_parses_whole_section_text(self) -> None:
        addresses = label_addresses(SECTION_TEXT)
        self.assertEqual(addresses, {"funcA": 0, "hidden": 8, "funcB": 0x14})

    def test_window_between_locates_the_stripped_local_function(self) -> None:
        with mock.patch(
            "decomp_workbench.score.dump_object",
            side_effect=fake_dump_object(SECTION_TEXT),
        ):
            window = window_between(
                "candidate.o", objdump=None, start_symbol="funcA", end_symbol="funcB"
            )
        self.assertEqual(window.mode, "between")
        self.assertEqual(window.note, BETWEEN_RATIONALE)
        self.assertEqual(len(window.instructions), 3)
        self.assertEqual([item.address for item in window.instructions], [8, 0xC, 0x10])

    def test_window_between_reports_missing_end_symbol(self) -> None:
        with mock.patch(
            "decomp_workbench.score.dump_object",
            side_effect=fake_dump_object(SECTION_TEXT),
        ):
            with self.assertRaises(ScoreError) as raised:
                window_between(
                    "candidate.o",
                    objdump=None,
                    start_symbol="funcA",
                    end_symbol="typo",
                )
        self.assertIn("defines: funcA, funcB, hidden", str(raised.exception))

    def test_window_between_reports_empty_or_reversed_range(self) -> None:
        with mock.patch(
            "decomp_workbench.score.dump_object",
            side_effect=fake_dump_object(SECTION_TEXT),
        ):
            with self.assertRaises(ScoreError) as raised:
                window_between(
                    "candidate.o",
                    objdump=None,
                    start_symbol="funcB",
                    end_symbol="funcA",
                )
        self.assertIn("empty or reversed", str(raised.exception))


class RomWindowTests(unittest.TestCase):
    def test_reads_the_requested_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(b"\x00" * 16 + b"\x01\x02\x03\x04" + b"\xff" * 16)
            window = read_rom_window(rom, offset=16, size=4)
        self.assertEqual(window, b"\x01\x02\x03\x04")
        self.assertEqual(words_from_bytes(window), ["01020304"])

    def test_missing_rom_names_the_fix(self) -> None:
        with self.assertRaises(ScoreError) as raised:
            read_rom_window("/no/such/rom.z64", offset=0, size=4)
        self.assertIn("does not exist", str(raised.exception))

    def test_offset_past_end_of_file_names_the_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(b"\x00" * 8)
            with self.assertRaises(ScoreError) as raised:
                read_rom_window(rom, offset=100, size=4)
        self.assertIn("past the end", str(raised.exception))

    def test_size_reaching_past_end_of_file_names_the_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(b"\x00" * 8)
            with self.assertRaises(ScoreError) as raised:
                read_rom_window(rom, offset=4, size=8)
        self.assertIn("reaches past the end", str(raised.exception))

    def test_non_word_aligned_size_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(b"\x00" * 8)
            with self.assertRaises(ScoreError) as raised:
                read_rom_window(rom, offset=0, size=3)
        self.assertIn("not a multiple of 4", str(raised.exception))


class ScoreWordsTests(unittest.TestCase):
    def test_relocation_words_are_a_floor_not_a_diff(self) -> None:
        instructions = parse_disassembly(RELOC_CANDIDATE_TEXT, symbol="demo")
        from decomp_workbench.score import Window

        window = Window(label="demo", instructions=tuple(instructions), mode="function")
        target_words = ["0c123456", "24020006", "03e00008", "00000000"]
        result = score_window(window, target_words)
        self.assertEqual(result.candidate_size, 16)
        self.assertEqual(result.target_size, 16)
        self.assertEqual(result.relocation_floor, 1)
        self.assertEqual(result.diff_words, 1)
        self.assertEqual(result.diff_positions, (1,))
        self.assertFalse(result.matched)
        self.assertIn("size 16/16, diff words 1", result.summary)
        self.assertIn("+1 relocation-floor word)", result.summary)

    def test_size_mismatch_counts_as_diff(self) -> None:
        instructions = parse_disassembly(RELOC_CANDIDATE_TEXT, symbol="demo")
        from decomp_workbench.score import Window

        window = Window(label="demo", instructions=tuple(instructions), mode="function")
        target_words = ["0c123456", "24020005", "03e00008"]  # one word short
        result = score_window(window, target_words)
        self.assertEqual(result.diff_words, 1)
        self.assertFalse(result.matched)


class ControlSpecTests(unittest.TestCase):
    def test_bare_name(self) -> None:
        self.assertEqual(parse_control_spec("ctrl"), ControlSpec(name="ctrl"))

    def test_name_with_offset(self) -> None:
        self.assertEqual(
            parse_control_spec("ctrl@0x100"), ControlSpec(name="ctrl", offset=0x100)
        )

    def test_name_with_offset_and_size(self) -> None:
        self.assertEqual(
            parse_control_spec("ctrl@0x100:32"),
            ControlSpec(name="ctrl", offset=0x100, size=32),
        )

    def test_invalid_spec_names_the_fix(self) -> None:
        with self.assertRaises(ScoreError) as raised:
            parse_control_spec("@0x10")
        self.assertIn("NAME@0xOFFSET", str(raised.exception))


class ScoreReportTests(unittest.TestCase):
    def test_matched_function_with_relocation_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(
                b"\x00" * 32
                + bytes.fromhex("0c123456")
                + bytes.fromhex("24020005")
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
            )
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            spec = ScoreSpec(
                target=TargetSpec(kind="rom", rom=str(rom), rom_offset=32),
                function="demo",
                between=None,
            )
            with mock.patch(
                "decomp_workbench.score.dump_object",
                side_effect=fake_dump_object(RELOC_CANDIDATE_TEXT),
            ):
                report = score_report(candidate, spec)
        self.assertTrue(report.matched)
        self.assertEqual(report.function.diff_words, 0)
        self.assertEqual(report.function.relocation_floor, 1)
        self.assertFalse(report.controls_broken)
        self.assertIn("relocation floor", "".join(report.guidance))

    def test_object_mismatch_guidance_names_the_real_candidate(self) -> None:
        target = TargetSpec(kind="object", target_object="target.o")
        guidance = build_guidance(
            matched=False,
            function_score=WordScore(
                label="demo",
                mode="function",
                note=None,
                candidate_size=4,
                target_size=4,
                diff_words=1,
                relocation_floor=0,
                diff_positions=(0,),
                candidate_sha256="0" * 64,
                matched=False,
            ),
            controls_broken=False,
            target=target,
            function_symbol="demo",
            candidate="run/objects/best.o",
        )
        self.assertIn("target.o run/objects/best.o", guidance[0])
        self.assertNotIn("<candidate.o>", guidance[0])

    def test_between_guidance_does_not_invent_a_function_symbol(self) -> None:
        guidance = build_guidance(
            matched=False,
            function_score=WordScore(
                label="before..after",
                mode="between",
                note=None,
                candidate_size=4,
                target_size=4,
                diff_words=1,
                relocation_floor=0,
                diff_positions=(0,),
                candidate_sha256="0" * 64,
                matched=False,
            ),
            controls_broken=False,
            target=TargetSpec(kind="rom", rom="base.z64", rom_offset=0),
            function_symbol=None,
            candidate="candidate.o",
        )
        self.assertIn("selected with `--between`", guidance[0])
        self.assertIn("diagnose-dumps", guidance[0])
        self.assertNotIn("--function", guidance[0])

    def test_broken_control_marks_the_whole_run(self) -> None:
        control_text = """
00000000 <ctrl>:
   0: 24020005  li $v0,5
   4: 03e00008  jr $ra
   8: 00000000  nop
"""

        def dump(
            path: str | Path,
            *,
            objdump: str | None = None,
            symbol: str | None = None,
            section: str = ".text",
        ) -> tuple[str, list[Instruction]]:
            if symbol == "demo" or (symbol is None and "demo" in str(path)):
                return RELOC_CANDIDATE_TEXT, parse_disassembly(
                    RELOC_CANDIDATE_TEXT, symbol=symbol
                )
            return control_text, parse_disassembly(control_text, symbol=symbol)

        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            # main function target: matches exactly (accounting for the reloc floor)
            rom.write_bytes(
                bytes.fromhex("0c123456")
                + bytes.fromhex("24020005")
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
                # control target: differs from control candidate at word 0
                + bytes.fromhex("24020099")
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
            )
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            spec = ScoreSpec(
                target=TargetSpec(kind="rom", rom=str(rom), rom_offset=0),
                function="demo",
                between=None,
                controls=(ControlSpec(name="ctrl", offset=16),),
            )
            with mock.patch("decomp_workbench.score.dump_object", side_effect=dump):
                report = score_report(candidate, spec)
        self.assertTrue(report.function.matched)
        self.assertFalse(report.controls[0].matched)
        self.assertTrue(report.controls_broken)
        self.assertFalse(report.matched)
        self.assertTrue(
            any("CONTROLS BROKEN" in line for line in report.guidance),
            report.guidance,
        )
        # The function under test already matches; guidance must not also
        # claim it still has diff words to classify -- only the control did.
        self.assertEqual(len(report.guidance), 1)
        self.assertNotIn("diagnose", report.guidance[0])

    def test_candidate_missing_names_the_fix(self) -> None:
        spec = ScoreSpec(
            target=TargetSpec(kind="rom", rom="unused", rom_offset=0),
            function="demo",
            between=None,
        )
        with self.assertRaises(ScoreError) as raised:
            score_report("/no/such/candidate.o", spec)
        self.assertIn("does not exist", str(raised.exception))


class ScoreSpecFromDictTests(unittest.TestCase):
    def test_requires_exactly_one_of_function_or_between(self) -> None:
        with self.assertRaises(ScoreError):
            score_spec_from_dict({"rom": "r.z64", "rom_offset": "0x0"})
        with self.assertRaises(ScoreError):
            score_spec_from_dict(
                {
                    "function": "demo",
                    "between": ["a", "b"],
                    "rom": "r.z64",
                    "rom_offset": "0x0",
                }
            )

    def test_requires_exactly_one_of_rom_or_target_object(self) -> None:
        with self.assertRaises(ScoreError):
            score_spec_from_dict({"function": "demo"})

    def test_rom_requires_rom_offset(self) -> None:
        with self.assertRaises(ScoreError):
            score_spec_from_dict({"function": "demo", "rom": "r.z64"})

    def test_parses_a_complete_spec(self) -> None:
        spec = score_spec_from_dict(
            {
                "function": "demo",
                "rom": "r.z64",
                "rom_offset": "0x100",
                "size": 32,
                "controls": ["ctrl@0x200:16"],
            }
        )
        self.assertEqual(spec.target.kind, "rom")
        self.assertEqual(spec.target.rom_offset, 0x100)
        self.assertEqual(
            spec.controls, (ControlSpec(name="ctrl", offset=0x200, size=16),)
        )


class ScoreCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_matched_run_exits_zero_and_prints_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(
                bytes.fromhex("0c123456")
                + bytes.fromhex("24020005")
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
            )
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            with mock.patch(
                "decomp_workbench.score.dump_object",
                side_effect=fake_dump_object(RELOC_CANDIDATE_TEXT),
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "score",
                        str(candidate),
                        "--function",
                        "demo",
                        "--rom",
                        str(rom),
                        "--rom-offset",
                        "0x0",
                    ]
                )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("verdict: MATCH", stdout)
        self.assertIn("next:", stdout)

    def test_mismatch_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(
                bytes.fromhex("0c123456")
                + bytes.fromhex("24020099")  # differs from candidate's 24020005
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
            )
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            with mock.patch(
                "decomp_workbench.score.dump_object",
                side_effect=fake_dump_object(RELOC_CANDIDATE_TEXT),
            ):
                status, stdout, _ = self.run_cli(
                    [
                        "score",
                        str(candidate),
                        "--function",
                        "demo",
                        "--rom",
                        str(rom),
                        "--rom-offset",
                        "0x0",
                    ]
                )
        self.assertEqual(status, 1)
        self.assertIn("verdict: MISMATCH", stdout)

    def test_json_output_has_the_score_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            rom.write_bytes(
                bytes.fromhex("0c123456")
                + bytes.fromhex("24020005")
                + bytes.fromhex("03e00008")
                + bytes.fromhex("00000000")
            )
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            with mock.patch(
                "decomp_workbench.score.dump_object",
                side_effect=fake_dump_object(RELOC_CANDIDATE_TEXT),
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "score",
                        str(candidate),
                        "--function",
                        "demo",
                        "--rom",
                        str(rom),
                        "--rom-offset",
                        "0x0",
                        "--json",
                    ]
                )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-score-v1")
        self.assertEqual(payload["function"]["relocation_floor"], 1)
        self.assertTrue(payload["matched"])

    def test_missing_candidate_file_is_a_clean_error(self) -> None:
        status, stdout, stderr = self.run_cli(
            [
                "score",
                "/no/such/candidate.o",
                "--function",
                "demo",
                "--rom",
                "/no/such/rom.z64",
                "--rom-offset",
                "0x0",
            ]
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("does not exist", stderr)

    def test_conflicting_target_options_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"x")
            status, _, stderr = self.run_cli(
                [
                    "score",
                    str(candidate),
                    "--function",
                    "demo",
                    "--rom",
                    "rom.z64",
                    "--rom-offset",
                    "0x0",
                    "--target-object",
                    "other.o",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("exactly one of --target-object or --rom", stderr)

    def test_function_and_between_conflict_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"x")
            status, _, stderr = self.run_cli(
                [
                    "score",
                    str(candidate),
                    "--rom",
                    "rom.z64",
                    "--rom-offset",
                    "0x0",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("exactly one of --function/--symbol or --between", stderr)

    def test_between_flag_is_wired_to_the_windower(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rom = Path(temp) / "baserom.z64"
            # target bytes for `hidden`: addiu sp,-32 / jr ra / nop, from
            # SECTION_TEXT's own encoded words.
            hidden_words = [
                item.word
                for item in parse_disassembly(SECTION_TEXT, symbol=None)
                if 8 <= item.address < 0x14
            ]
            rom.write_bytes(bytes.fromhex("".join(hidden_words)))
            candidate = Path(temp) / "candidate.o"
            candidate.write_bytes(b"placeholder")
            with mock.patch(
                "decomp_workbench.score.dump_object",
                side_effect=fake_dump_object(SECTION_TEXT),
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "score",
                        str(candidate),
                        "--between",
                        "funcA,funcB",
                        "--rom",
                        str(rom),
                        "--rom-offset",
                        "0x0",
                        "--json",
                    ]
                )
        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["matched"])
        self.assertEqual(payload["function"]["mode"], "between")
        self.assertEqual(payload["function"]["note"], BETWEEN_RATIONALE)


if __name__ == "__main__":
    unittest.main()
