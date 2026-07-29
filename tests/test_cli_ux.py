"""Tests for action-oriented CLI behavior."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import build_parser, main

#: Every command that selects one function, and therefore owes the reader both
#: spellings, the conflict check, and the key registry. `view` and `view-dumps`
#: were merged in with their own copy of the option and had none of the three.
SYMBOL_COMMANDS = (
    "compare",
    "compare-dumps",
    "view",
    "view-dumps",
    "rank",
    "compile-rank",
    "campaign",
)

#: Every command that produces one report a predicate can be asked about.
CENSUS_COMMANDS = ("compare", "compare-dumps", "view", "view-dumps")


class CliUxTests(unittest.TestCase):
    last_stdout = ""
    last_stderr = ""

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                status = main(arguments)
        finally:
            self.last_stdout = stdout.getvalue()
            self.last_stderr = stderr.getvalue()
        return status, self.last_stdout, self.last_stderr

    def test_web_lookup_requires_procedure(self) -> None:
        status, _, stderr = self.run_cli(
            ["trace-globalcolor", "unused.log", "--web", "9"]
        )
        self.assertEqual(status, 2)
        self.assertIn("--web requires --proc", stderr)

    def test_missing_web_lists_available_webs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p1dec proc=3 web=9 bestcolor=17 decision=color\n",
                encoding="utf-8",
            )
            status, _, stderr = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "3",
                    "--web",
                    "10",
                ]
            )
        self.assertEqual(status, 1)
        self.assertIn("available web(s): 9", stderr)

    def test_missing_procedure_does_not_show_unscoped_live_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "CSAVE bitpos=1 kind=1 dtype=13 unk1C=1 adjsave=1 unk23=0\n"
                "[CDX] p1dec proc=3 web=9 bestcolor=17 decision=color\n",
                encoding="utf-8",
            )
            status, stdout, stderr = self.run_cli(
                ["trace-globalcolor", str(trace), "--proc", "4"]
            )
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("available procedure(s): 3", stderr)

    def test_cross_rom_json_states_its_acceptance_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "jp.objdump"
            candidate = root / "us.objdump"
            target.write_text(
                "0: 3c080123  lui t0,0x123\n4: 25081234  addiu t0,t0,4660\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "0: 3c084567  lui $t0,0x4567\n4: 250889ab  addiu $t0,$t0,-30293\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "compare-dumps",
                    str(target),
                    str(candidate),
                    "--cross-rom",
                    "--fail-on-mismatch",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertFalse(payload["exact"])
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["acceptance_basis"], "cross-rom-structural")

    def write_two_function_dump(self, root: Path) -> Path:
        dump = root / "two.objdump"
        dump.write_text(
            "00000000 <first>:\n"
            "   0: 24020021  li $v0,33\n"
            "00000004 <second>:\n"
            "   4: 03e00008  jr $ra\n"
            "   8: 00000000  nop\n",
            encoding="utf-8",
        )
        return dump

    def test_function_is_accepted_as_a_symbol_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dump = self.write_two_function_dump(Path(temp))
            status, stdout, _ = self.run_cli(
                ["compare-dumps", str(dump), str(dump), "--function", "first", "--json"]
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(payload["symbol"], "first")
        self.assertEqual(payload["candidate_instructions"], 1)

    def test_symbol_spelling_is_not_leaked_into_command_arguments(self) -> None:
        seen: list[argparse.Namespace] = []
        parser = build_parser()
        arguments = parser.parse_args(
            ["compare-dumps", "a.objdump", "b.objdump", "--function", "demo"]
        )
        self.assertIn("symbol_option", vars(arguments))

        def capture(args: argparse.Namespace) -> int:
            seen.append(args)
            return 0

        with tempfile.TemporaryDirectory() as temp:
            dump = self.write_two_function_dump(Path(temp))
            with mock.patch(
                "decomp_workbench.cli.compare_dumps_command",
                side_effect=capture,
            ):
                status, _, _ = self.run_cli(
                    ["compare-dumps", str(dump), str(dump), "--function", "first"]
                )
        self.assertEqual(status, 0)
        self.assertEqual(seen[0].symbol, "first")
        self.assertNotIn("symbol_option", vars(seen[0]))

    def test_repeated_symbol_spellings_agree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dump = self.write_two_function_dump(Path(temp))
            status, stdout, _ = self.run_cli(
                [
                    "compare-dumps",
                    str(dump),
                    str(dump),
                    "--symbol",
                    "first",
                    "--function",
                    "first",
                    "--json",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["symbol"], "first")

    def test_conflicting_symbol_and_function_is_rejected(self) -> None:
        for command in SYMBOL_COMMANDS:
            with self.subTest(command=command):
                with tempfile.TemporaryDirectory() as temp:
                    dump = self.write_two_function_dump(Path(temp))
                    with self.assertRaises(SystemExit) as raised:
                        self.run_cli(
                            [
                                command,
                                str(dump),
                                str(dump),
                                "--symbol",
                                "first",
                                "--function",
                                "second",
                            ]
                        )
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("two spellings of one selector", self.last_stderr)

    def test_every_symbol_command_documents_the_function_alias(self) -> None:
        for command in SYMBOL_COMMANDS:
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    self.run_cli([command, "--help"])
                selector = [
                    line
                    for line in self.last_stdout.splitlines()
                    if line.strip().startswith("--symbol")
                ]
                self.assertEqual(len(selector), 1)
                self.assertIn("--function", selector[0])

    def test_the_two_input_commands_are_listed_together(self) -> None:
        """`view` answers the next question about the inputs `compare` reads."""

        listing = re.search(r"\{([^}]+)\}", build_parser().format_help())
        assert listing is not None
        order = re.sub(r"\s+", "", listing.group(1)).split(",")
        self.assertEqual(order[:4], ["compare", "compare-dumps", "view", "view-dumps"])

    def test_show_diff_prints_literal_sites_under_a_register_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.objdump"
            candidate = root / "candidate.objdump"
            target.write_text(
                "00000000 <demo>:\n"
                "   0: 24020021  li $v0,33\n"
                "   4: 012a4021  addu $t0,$t1,$t2\n",
                encoding="utf-8",
            )
            candidate.write_text(
                "00000000 <demo>:\n"
                "   0: 24020031  li $v0,49\n"
                "   4: 012a5821  addu $t3,$t1,$t2\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "compare-dumps",
                    str(target),
                    str(candidate),
                    "--function",
                    "demo",
                    "--show-diff",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("verdict=allocation-mismatch", stdout)
        self.assertIn("diff_sites=2 (constant=1, register=1)", stdout)
        self.assertIn("li $v0,33", stdout)
        self.assertIn("li $v0,49", stdout)
        self.assertIn("addu $t3,$t1,$t2", stdout)

    def test_explain_keys_is_available_without_positional_arguments(self) -> None:
        for command in ("", *SYMBOL_COMMANDS):
            arguments = [command, "--explain-keys"] if command else ["--explain-keys"]
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as raised:
                    self.run_cli(arguments)
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("words", self.last_stdout)
                self.assertIn("word_mismatches", self.last_stdout)
                # One registry: the aligned view's keys are explained too.
                self.assertIn("aligned_rows", self.last_stdout)
                self.assertIn("Aligned mechanism view keys", self.last_stdout)

    def test_census_is_offered_by_every_command_that_reports(self) -> None:
        """One spelling, one exit-code contract, four commands.

        The key is validated before the inputs are read, so this also proves
        the promise a sweep depends on: a misspelled predicate costs nothing.
        """

        for command in CENSUS_COMMANDS:
            with self.subTest(command=command):
                status, _, stderr = self.run_cli(
                    [command, "missing-target", "missing-candidate", "--census", "x=1"]
                )
                self.assertEqual(status, 2)
                self.assertIn("unknown census key 'x'", stderr)

    def test_json_reports_both_the_canonical_and_deprecated_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dump = self.write_two_function_dump(Path(temp))
            _, stdout, _ = self.run_cli(
                ["compare-dumps", str(dump), str(dump), "--json"]
            )
        payload = json.loads(stdout)
        for key, alias in (
            ("words", "word_mismatches"),
            ("insns", "candidate_instructions"),
            ("frame", "candidate_frame_size"),
        ):
            with self.subTest(key=key):
                self.assertEqual(payload[key], payload[alias])

    def test_unqualified_force_key_is_rejected_before_compiling(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "candidate.c").write_text("int candidate;\n", encoding="utf-8")
            (root / "target.o").write_bytes(b"target")
            status, _, stderr = self.run_cli(
                [
                    "campaign",
                    str(root / "target.o"),
                    str(root / "candidate.c"),
                    "--compile-command",
                    "cc {source} -o {output}",
                    "--env",
                    "CDX_FORCE=w55=c2",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("not a phase-qualified force control", stderr)
        self.assertIn("p2:w9=c30", stderr)

    def test_trace_globalcolor_decodes_colors_and_force_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p2cost phase=p2 proc=7 web=55 color=2 reg=v1 "
                "kind=caller cost=1.0 best_before=2.0\n"
                "[CDX] p2dec phase=p2 proc=7 web=55 sym=55 class=1 save=1 "
                "nocs=2 totalsave=2 bestcost=0 bestcolor=2 bestreg=v1 "
                "decision=color\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                ["trace-globalcolor", str(trace), "--proc", "7", "--web", "55"]
            )
        self.assertEqual(status, 0)
        self.assertIn("force_key=p2:w55", stdout)
        self.assertIn("register=v1", stdout)
        self.assertIn("c2(v1):1.0", stdout)
        self.assertIn("selected c2 (v1)", stdout)

    def test_campaign_reports_what_stopping_early_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "target.o").write_bytes(b"target")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            sources = []
            for index in range(3):
                source = root / f"candidate{index}.c"
                source.write_text(f"int value = {index};\n", encoding="utf-8")
                sources.append(str(source))
            arguments = [
                "campaign",
                str(root / "target.o"),
                *sources,
                "--function",
                "demo",
                "--objdump",
                str(objdump),
                "--compile-command",
                f"{sys.executable} {compiler} {{source}} {{output}}",
                "--cache-dir",
                str(root / "cache"),
                "--jobs",
                "1",
            ]
            status, stdout, _ = self.run_cli(arguments)
            self.assertEqual(status, 0)
            self.assertIn("stopped on the first exact match", stdout)
            self.assertIn("--no-stop-on-exact", stdout)

            status, stdout, _ = self.run_cli([*arguments, "--no-stop-on-exact"])
            self.assertEqual(status, 0)
            self.assertNotIn("stopped on the first exact match", stdout)
            self.assertEqual(stdout.count("verdict="), 3)

    def test_install_skill_reports_current_on_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            arguments = [
                "install-skill",
                "claude",
                "--destination",
                str(Path(temp) / "skills"),
                "--json",
            ]
            first_status, first_stdout, _ = self.run_cli(arguments)
            second_status, second_stdout, _ = self.run_cli(arguments)
        self.assertEqual(first_status, 0)
        self.assertEqual(json.loads(first_stdout)["status"], "installed")
        self.assertEqual(second_status, 0)
        self.assertEqual(json.loads(second_stdout)["status"], "current")


if __name__ == "__main__":
    unittest.main()
