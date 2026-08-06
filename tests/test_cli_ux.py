"""Tests for action-oriented CLI behavior."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
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
    "diagnose",
    "diagnose-dumps",
    "view",
    "view-dumps",
    "check-scratch",
    "rank",
    "compile-rank",
    "campaign",
)

#: Every command that produces one report a predicate can be asked about.
CENSUS_COMMANDS = (
    "compare",
    "compare-dumps",
    "diagnose",
    "diagnose-dumps",
    "view",
    "view-dumps",
)


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

    def test_lineage_table_requires_procedure(self) -> None:
        status, _, stderr = self.run_cli(
            ["trace-globalcolor", "unused.log", "--lineage-table", "1004"]
        )
        self.assertEqual(status, 2)
        self.assertIn("--lineage-table requires --proc", stderr)

    def test_trace_globalcolor_renders_formation_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] lineage_range proc=0 event=0 table=1004 chain=0 "
                "type=4 dtype=6\n"
                "[CDX] lineage_member proc=0 event=1 table=1004 chain=0 "
                "bb=10 line=2 flags=0,0,0,0,0,0\n"
                "[CDX] lineage_range proc=0 event=2 table=688 chain=0 "
                "type=3 dtype=6\n",
                encoding="utf-8",
            )
            status, stdout, stderr = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "0",
                    "--lineage-table",
                    "1004",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("lineage range: proc=0 event=0 table=1004", stdout)
        self.assertIn("lineage member: proc=0 event=1 table=1004", stdout)
        self.assertNotIn("table=688", stdout)
        self.assertIn("lineage=2", stdout)
        self.assertIn("allocator-webs=0 decisions=0", stdout)

    def test_origin_probe_help_states_its_non_attribution_scope(self) -> None:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        commands = subparsers.choices
        help_text = " ".join(commands["trace-origin-probe"].format_help().split())
        self.assertIn("controlled perturbation", help_text)
        self.assertIn("does not claim source attribution", help_text)

    def test_trace_group_help_lists_copy_decisions(self) -> None:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        help_text = subparsers.choices["trace"].format_help()

        self.assertIn("trace copy-decisions", help_text)
        self.assertIn("coalesced-versus-temporary", help_text)

    def test_trace_comparisons_succeed_when_evidence_is_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            trace = root / "trace.log"
            trace.write_text(
                "[CDX] p2dec phase=p2 proc=0 web=1 bestcolor=12 decision=color\n",
                encoding="utf-8",
            )
            status, _, stderr = self.run_cli(
                ["trace-webs", str(trace), "--against", str(trace), "--proc", "0"]
            )

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")

    def test_copy_diff_succeeds_when_only_candidate_has_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline.log"
            candidate = root / "candidate.log"
            baseline.write_text("", encoding="utf-8")
            candidate.write_text(
                "CDXW 000001 p0 d2 COPYDEC tag=pre-reemit stmt=1 lhs=2 "
                "rhs=3 rhsop=00 rhstable=0 rhschain=0 occ=0/0 rhsformed=1 "
                "bbwit=0 lhscolor=1 rhscolor=2 lhsframe=fffffff0 -> TEMPCOPY\n",
                encoding="utf-8",
            )
            status, _, stderr = self.run_cli(
                [
                    "trace-copy-decisions",
                    str(baseline),
                    "--against",
                    str(candidate),
                ]
            )

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")

    def test_empty_origin_probe_is_not_a_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline.log"
            variant = root / "variant.log"
            baseline.write_text("", encoding="utf-8")
            variant.write_text("", encoding="utf-8")
            status, stdout, stderr = self.run_cli(
                ["trace-origin-probe", str(baseline), str(variant), "--role", "empty"]
            )

        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertIn("classification=no-evidence", stdout)

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

    def test_cdx_only_trace_does_not_claim_zero_live_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p2dec phase=p2 proc=0 web=9 bestcolor=12 decision=color\n",
                encoding="utf-8",
            )
            status, stdout, stderr = self.run_cli(
                ["trace-globalcolor", str(trace), "--proc", "0", "--web", "9"]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("legacy-live-ranges=not-captured", stdout)
        self.assertNotIn("live-ranges=0/0", stdout)

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
                    inputs = (
                        [str(Path(temp))]
                        if command == "check-scratch"
                        else [str(dump), str(dump)]
                    )
                    with self.assertRaises(SystemExit) as raised:
                        self.run_cli(
                            [
                                command,
                                *inputs,
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
        """`view` answers the next question about the inputs `compare` reads.

        Read from the visible choice actions rather than the usage metavar:
        the metavar is one word now, because forty-odd names inline made every
        argument error unreadable. The listed order is still the promise.
        """

        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        order = [choice.dest for choice in subparsers._choices_actions]
        self.assertEqual(
            order[:6],
            [
                "compare",
                "compare-dumps",
                "view",
                "view-dumps",
                "diagnose",
                "diagnose-dumps",
            ],
        )

    def test_every_compiler_command_has_the_same_runtime_controls(self) -> None:
        parser = build_parser()
        cases = {
            "check-scratch": ["check-scratch", "scratch.zip"],
            "compile-rank": ["compile-rank", "target.o", "candidate.c"],
            "campaign": ["campaign", "target.o", "candidate.c"],
        }
        for command, arguments in cases.items():
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    self.run_cli([command, "--help"])
                self.assertIn("--compile-cwd", self.last_stdout)
                self.assertIn("--env", self.last_stdout)
                self.assertIn("--timeout", self.last_stdout)
                parsed = parser.parse_args(
                    [
                        *arguments,
                        "--compile-command",
                        "cc {source} -o {output}",
                        "--timeout",
                        "7",
                    ]
                )
                self.assertEqual(parsed.timeout, 7.0)

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
        self.assertIn("natural=c2(v1) assigned=c2(v1)", stdout)
        self.assertIn("c2(v1):1.0", stdout)
        self.assertIn("selected c2 (v1)", stdout)

    def test_trace_globalcolor_explains_desired_register_barrier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p2cost phase=p2 proc=0 web=62 color=12 reg=t5 "
                "kind=caller cost=0.0 best_before=0.0\n"
                "[CDX] p2cost phase=p2 proc=0 web=62 color=18 reg=s4 "
                "kind=callee cost=5.5 best_before=0.0\n"
                "[CDX] p2dec phase=p2 proc=0 web=62 class=1 save=100 "
                "nocs=1 totalsave=100 bestcost=0 bestcolor=12 bestreg=t5 "
                "forbidden0=0x7ff00000 decision=color\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "0",
                    "--web",
                    "62",
                    "--desired-register",
                    "s4",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("desired=c18(s4) cost=5.5", stdout)
        self.assertIn("natural=c12(t5) cost=0.0 gap=5.5", stdout)
        self.assertIn("make the natural color unavailable", stdout)
        self.assertIn("a force tests the endpoint only", stdout)

    def test_trace_globalcolor_names_forbidden_register_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p2dec phase=p2 proc=0 web=100 bestcolor=18 "
                "forbidden0=0x00080000 decision=color\n"
                "[CDX] intf phase=p2 proc=0 web=100 other=60 assigned=12\n"
                "[CDX] webdetail phase=p2 proc=0 role=neighbor web=60 "
                "dtype=6 type=4 table=1004\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "0",
                    "--web",
                    "100",
                    "--desired-register",
                    "t5",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("blocker: p2:w60 assigned=c12(t5)", stdout)
        self.assertIn("dtype=6 type=4 table=1004", stdout)

    def test_trace_globalcolor_reports_ineligible_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "globalcolor.log"
            trace.write_text(
                "[CDX] p2cost phase=p2 proc=3 web=0 color=12 reg=t5 "
                "kind=caller cost=100000002004087734272.000000\n"
                "[CDX] p2cost phase=p2 proc=3 web=0 color=14 reg=s0 "
                "kind=callee cost=4.5\n"
                "[CDX] p2dec phase=p2 proc=3 web=0 bestcolor=14 "
                "forbidden0=0x00000000 decision=color\n",
                encoding="utf-8",
            )
            status, stdout, _ = self.run_cli(
                [
                    "trace-globalcolor",
                    str(trace),
                    "--proc",
                    "3",
                    "--web",
                    "0",
                    "--desired-register",
                    "t5",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("gap=None forbidden=no ineligible=yes", stdout)
        self.assertIn("unavailable-cost sentinel", stdout)

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
                "--state-dir",
                str(root / "state"),
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

    def test_the_bare_program_name_welcomes_instead_of_failing(self) -> None:
        """Typing the name is curiosity, not a usage error.

        argparse answered it with a 44-name choice wall and exit 2, which reads
        as "you did something wrong" and names no starting point.
        """

        status, stdout, stderr = self.run_cli([])
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn("decomp-workbench commands", stdout)
        self.assertIn("docs/START_HERE.md", stdout)
        self.assertIn("--help", stdout)

    def test_the_usage_line_is_one_word_not_a_command_wall(self) -> None:
        help_text = build_parser().format_help()
        usage = help_text.split("\n\n", 1)[0]
        self.assertIn("COMMAND", usage)
        self.assertNotIn("compare-dumps", usage)
        # the pointer survives in both the subparser help and the epilog
        self.assertIn("decomp-workbench commands", help_text)

    def test_the_first_recommended_command_matches_the_narrative_docs(self) -> None:
        """README and START_HERE teach the flat spelling exclusively."""

        status, stdout, _ = self.run_cli(["commands"])
        self.assertEqual(status, 0)
        self.assertIn("decomp-workbench diagnose target.o candidate.o", stdout)
        self.assertNotIn("object diagnose TARGET CANDIDATE", stdout)

    def test_every_selector_says_what_omitting_it_means(self) -> None:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        for command in SYMBOL_COMMANDS:
            with self.subTest(command=command):
                child = subparsers.choices[command]
                selector = next(
                    action
                    for action in child._actions
                    if "--symbol" in action.option_strings
                )
                assert selector.help is not None
                self.assertIn("whole section positionally", selector.help)


if __name__ == "__main__":
    unittest.main()


class ViewShowAllFlagTest(unittest.TestCase):
    """`view --show-all` must exist: the field guide advertises it."""

    def _command(self, name: str) -> argparse.ArgumentParser:
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        return subparsers.choices[name]

    def test_view_accepts_show_all(self) -> None:
        arguments = self._command("view").parse_args(
            ["target.o", "candidate.o", "--show-all"]
        )
        self.assertTrue(arguments.show_all)

    def test_view_dumps_accepts_show_all(self) -> None:
        arguments = self._command("view-dumps").parse_args(
            ["target.objdump", "candidate.objdump", "--show-all"]
        )
        self.assertTrue(arguments.show_all)

    def test_diagnose_still_accepts_show_all(self) -> None:
        arguments = self._command("diagnose").parse_args(
            ["target.o", "candidate.o", "--show-all"]
        )
        self.assertTrue(arguments.show_all)

    def test_check_scratch_still_accepts_show_all(self) -> None:
        arguments = self._command("check-scratch").parse_args(
            ["export.zip", "--show-all"]
        )
        self.assertTrue(arguments.show_all)
