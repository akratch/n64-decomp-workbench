"""What the tool says about its own inputs, before it says anything about code.

Three failures share one shape: the command answered a question the reader did
not ask, and said nothing about the substitution.

* comparing two differently-named functions positionally and reporting a
  confident verdict about the result -- the only shape in this tool that turns
  silence into a *wrong* answer rather than a coarse one;
* a symbol typo and a symbol case slip producing the same opaque sentence;
* an objdump failure quoted raw, with two unrelated-looking lines glued
  together and no cause named.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench import objdump
from decomp_workbench.cli import main
from decomp_workbench.objdump import (
    _objdump_failure,
    cross_function_warning,
    symbol_labels,
    symbol_selection_error,
)

ONE = """
00000000 <drawObject>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 24020021  li $v0,33
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

OTHER = """
00000000 <drawShadow>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 24020031  li $v0,49
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

TWO_LABELS = """
00000000 <drawObject>:
   0: 24020021  li $v0,33
00000004 <drawShadow>:
   4: 03e00008  jr $ra
   8: 00000000  nop
"""


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class DumpPair:
    """Two retained dumps on disk, for the commands that read text."""

    def __init__(self, stack: contextlib.ExitStack, target: str, candidate: str):
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.target = root / "target.objdump"
        self.candidate = root / "candidate.objdump"
        self.target.write_text(target, encoding="utf-8")
        self.candidate.write_text(candidate, encoding="utf-8")

    def argv(self) -> list[str]:
        return [str(self.target), str(self.candidate)]


class CrossFunctionWarningTests(unittest.TestCase):
    def test_one_function_each_with_different_names_warns(self) -> None:
        warning = cross_function_warning(ONE, OTHER, symbol=None)
        assert warning is not None
        self.assertIn("'drawObject'", warning)
        self.assertIn("'drawShadow'", warning)
        self.assertIn("positionally", warning)
        self.assertIn("Pass --function", warning)

    def test_the_same_name_on_both_sides_is_the_normal_case(self) -> None:
        self.assertIsNone(cross_function_warning(ONE, ONE, symbol=None))

    def test_several_labels_are_a_whole_section_comparison_on_purpose(self) -> None:
        """A multi-symbol object is the documented whole-section mode.

        Naming "the" function of a five-function object would be a guess, and
        the reader who dumped a whole section meant to.
        """

        self.assertIsNone(cross_function_warning(TWO_LABELS, ONE, symbol=None))
        self.assertIsNone(cross_function_warning(ONE, TWO_LABELS, symbol=None))

    def test_an_explicit_selector_answers_the_question_already(self) -> None:
        self.assertIsNone(cross_function_warning(ONE, OTHER, symbol="drawObject"))

    def test_the_section_name_follows_the_selected_section(self) -> None:
        warning = cross_function_warning(ONE, OTHER, symbol=None, section=".rodata")
        assert warning is not None
        self.assertIn(".rodata section", warning)

    def test_symbol_labels_are_read_in_order(self) -> None:
        self.assertEqual(symbol_labels(TWO_LABELS), ("drawObject", "drawShadow"))
        self.assertEqual(symbol_labels("   0: 24020021  li $v0,33\n"), ())


class WarningReachesEveryRendererTests(unittest.TestCase):
    """A warning printed by one of four commands is a warning three can hide."""

    def assert_warns(self, command: str) -> str:
        # `compare-dumps` has no pager; the other two must not open one here.
        pager = [] if command == "compare-dumps" else ["--pager", "never"]
        with contextlib.ExitStack() as stack:
            pair = DumpPair(stack, ONE, OTHER)
            status, stdout, _ = run_cli([command, *pair.argv(), *pager])
        self.assertEqual(status, 0)
        self.assertIn("warning: target defines 'drawObject'", stdout)
        return stdout

    def test_compare_dumps_warns_before_the_verdict(self) -> None:
        stdout = self.assert_warns("compare-dumps")
        self.assertLess(stdout.index("warning:"), stdout.index("verdict="))

    def test_view_dumps_warns_before_the_header(self) -> None:
        stdout = self.assert_warns("view-dumps")
        self.assertLess(stdout.index("warning:"), stdout.index("verdict:"))

    def test_diagnose_dumps_warns_once_before_everything(self) -> None:
        stdout = self.assert_warns("diagnose-dumps")
        self.assertEqual(stdout.count("warning: target defines"), 1)
        self.assertLess(stdout.index("warning:"), stdout.index("COMPARISON"))

    def test_json_consumers_see_the_warning_too(self) -> None:
        """CI reads the payload, and a wrong verdict is worse unattended."""

        import json

        with contextlib.ExitStack() as stack:
            pair = DumpPair(stack, ONE, OTHER)
            _, stdout, _ = run_cli(["compare-dumps", *pair.argv(), "--json"])
        payload = json.loads(stdout)
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("drawShadow", payload["warnings"][0])

    def test_a_matching_pair_stays_quiet(self) -> None:
        with contextlib.ExitStack() as stack:
            pair = DumpPair(stack, ONE, ONE)
            status, stdout, _ = run_cli(["compare-dumps", *pair.argv()])
        self.assertEqual(status, 0)
        self.assertNotIn("warning:", stdout)


class SymbolSelectionErrorTests(unittest.TestCase):
    def test_a_case_slip_shows_the_name_that_exists(self) -> None:
        message = symbol_selection_error(
            "DrawObject",
            inputs=(("target.objdump", ONE), ("candidate.objdump", OTHER)),
        )
        self.assertIn("'DrawObject' produced no instructions", message)
        self.assertIn("target.objdump defines: drawObject", message)
        self.assertIn("candidate.objdump defines: drawShadow", message)
        self.assertIn("Names are case-sensitive.", message)
        self.assertIn(
            "docs/troubleshooting.md#objdump-produced-no-instructions", message
        )

    def test_a_long_symbol_list_is_elided_not_dumped(self) -> None:
        text = "".join(
            f"0000000{index} <func_{index}>:\n   {index}: 24020021  li $v0,33\n"
            for index in range(12)
        )
        message = symbol_selection_error("missing", inputs=(("big.objdump", text),))
        self.assertIn("func_0", message)
        self.assertIn("(+4 more)", message)
        self.assertNotIn("func_9", message)

    def test_no_selector_and_no_instructions_names_the_expected_shape(self) -> None:
        message = symbol_selection_error(None, inputs=(("notes.txt", "hello\n"),))
        self.assertIn("no GNU-style objdump instruction lines in notes.txt", message)
        self.assertIn("lw t9", message)

    def test_every_text_command_uses_it(self) -> None:
        for command in ("compare-dumps", "view-dumps", "diagnose-dumps"):
            with self.subTest(command=command):
                with contextlib.ExitStack() as stack:
                    pair = DumpPair(stack, ONE, OTHER)
                    status, _, stderr = run_cli(
                        [command, *pair.argv(), "--function", "DrawObject"]
                    )
                self.assertEqual(status, 2)
                self.assertIn("Names are case-sensitive.", stderr)
                self.assertIn("defines: drawObject", stderr)


class FilteredDumpEvidenceTests(unittest.TestCase):
    """One unfiltered second pass, serving two features that both need it.

    ``objdump --disassemble=NAME`` filters case-sensitively and prints nothing
    when it matches nothing -- no error, no symbol headers, an empty stream.
    Two independent fixes converge on that fact:

    * a Pascal-era frontend folds identifiers, so ``Foo`` is on disk as
      ``foo``; a unique case-insensitive match should simply work;
    * when no such match exists, the error must say what the object really
      defines, and built from the filtered stream it said "no symbols".

    They were developed on separate branches and each promised, in its
    docstring, to become the other's second pass. This asserts they did: one
    re-dump, either outcome.
    """

    SECTION = """
00000000 <funcA>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 03e00008  jr $ra
   8: 00000000  nop

0000000c <funcB>:
   c: 03e00008  jr $ra
"""

    def run_dump(self, symbol: str | None) -> tuple[int, object]:
        """Dump against a fake objdump, counting subprocess invocations."""

        calls = 0

        def fake_run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal calls
            calls += 1
            filtered = any(str(item).startswith("--disassemble=") for item in command)
            return subprocess.CompletedProcess(
                command, 0, "" if filtered else self.SECTION, ""
            )

        with (
            mock.patch("decomp_workbench.objdump.subprocess.run", fake_run),
            mock.patch.object(objdump, "discover_objdump", lambda value=None: "od"),
        ):
            try:
                outcome: object = objdump.dump_object("build/foo.o", symbol=symbol)
            except RuntimeError as error:
                outcome = error
        return calls, outcome

    def test_a_case_slip_succeeds_through_the_fallback(self) -> None:
        calls, outcome = self.run_dump("FuncA")
        self.assertNotIsInstance(outcome, RuntimeError)
        assert isinstance(outcome, tuple)
        _text, instructions = outcome
        self.assertEqual(len(instructions), 3)
        self.assertEqual(calls, 2)

    def test_an_entirely_wrong_symbol_fails_with_the_defines_list(self) -> None:
        calls, outcome = self.run_dump("drawShadow")
        self.assertIsInstance(outcome, RuntimeError)
        message = str(outcome)
        self.assertIn("symbol 'drawShadow' produced no instructions", message)
        self.assertIn("defines: funcA, funcB", message)
        self.assertNotIn("no symbols", message)
        self.assertIn("Names are case-sensitive.", message)
        self.assertEqual(calls, 2)

    def test_an_ambiguous_fold_is_refused_rather_than_guessed(self) -> None:
        """Two symbols folding alike is not a unique match, so it is an error."""

        ambiguous = FilteredDumpEvidenceTests.SECTION.replace("funcB", "FUNCA")
        with mock.patch.object(FilteredDumpEvidenceTests, "SECTION", ambiguous):
            calls, outcome = self.run_dump("funca")
        self.assertIsInstance(outcome, RuntimeError)
        self.assertIn("defines: funcA, FUNCA", str(outcome))
        self.assertEqual(calls, 2)

    def test_no_selector_does_not_pay_for_a_retry(self) -> None:
        calls = 0

        def fake_run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            nonlocal calls
            calls += 1
            return subprocess.CompletedProcess(command, 0, "nothing here\n", "")

        with (
            mock.patch("decomp_workbench.objdump.subprocess.run", fake_run),
            mock.patch.object(objdump, "discover_objdump", lambda value=None: "od"),
        ):
            with self.assertRaises(RuntimeError):
                objdump.dump_object("build/foo.o")
        self.assertEqual(calls, 1)

    def test_a_failing_retry_falls_back_to_what_we_had(self) -> None:
        """A second failure must not replace a bad message with a crash."""

        def fake_run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            filtered = any(str(item).startswith("--disassemble=") for item in command)
            if filtered:
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 1, "", "boom")

        with (
            mock.patch("decomp_workbench.objdump.subprocess.run", fake_run),
            mock.patch.object(objdump, "discover_objdump", lambda value=None: "od"),
        ):
            with self.assertRaises(RuntimeError) as caught:
                objdump.dump_object("build/foo.o", symbol="FuncA")
        self.assertIn("produced no instructions", str(caught.exception))


class ObjdumpFailureTests(unittest.TestCase):
    def test_an_unrecognized_format_names_the_likely_cause(self) -> None:
        result = subprocess.CompletedProcess(
            args=["objdump"],
            returncode=1,
            stdout="",
            stderr=(
                "objdump: build/foo.o: file format not recognized\n"
                "objdump: build/foo.o: Bad value\n"
            ),
        )
        message = _objdump_failure("build/foo.o", result)
        self.assertIn("does not look like a compiled MIPS ELF object", message)
        self.assertIn("that the build actually produced an object file", message)
        # the tool's own words survive, indented beneath the synthesis
        self.assertIn("  objdump: build/foo.o: file format not recognized", message)
        self.assertIn("  objdump: build/foo.o: Bad value", message)

    def test_an_unfamiliar_failure_is_still_quoted_in_full(self) -> None:
        result = subprocess.CompletedProcess(
            args=["objdump"],
            returncode=1,
            stdout="",
            stderr="objdump: section '.text' not found\n",
        )
        message = _objdump_failure("build/foo.o", result)
        self.assertNotIn("does not look like", message)
        self.assertIn("  objdump: section '.text' not found", message)

    def test_a_silent_failure_still_produces_a_sentence(self) -> None:
        result = subprocess.CompletedProcess(
            args=["objdump"], returncode=1, stdout="", stderr=""
        )
        self.assertIn("no output", _objdump_failure("build/foo.o", result))


if __name__ == "__main__":
    unittest.main()


class MissingCandidateTests(unittest.TestCase):
    """A candidate that is not there must stop the run, not shrink the report.

    A campaign lost half a sweep to a downstream driver that read a comparison
    it never got and carried on with the previous candidate's numbers. That
    driver was the bug, but the audit belongs here: whatever the tool does at
    the boundary is what every driver will rely on, so it is pinned by test
    rather than by inspection. The contract is a nonzero exit, the path named
    in the message, and -- when JSON was asked for -- one schema-named error
    document rather than an empty or partial report.
    """

    #: GNU objdump's own behaviour for a path that is not there: exit 1, one
    #: sentence on stderr, nothing on stdout. Only the absent path fails, so
    #: the target dumps normally and the candidate is the one that stops it.
    @staticmethod
    def _absent(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        target = command[-1]
        if "nonexistent" in target:
            return subprocess.CompletedProcess(
                command, 1, "", f"objdump: '{target}': No such file\n"
            )
        return subprocess.CompletedProcess(command, 0, ONE, "")

    def run_compare(self, arguments: list[str]) -> tuple[int, str, str]:
        with (
            mock.patch("decomp_workbench.objdump.subprocess.run", self._absent),
            mock.patch.object(objdump, "discover_objdump", lambda value=None: "od"),
        ):
            return run_cli(arguments)

    def test_compare_against_a_missing_candidate_exits_nonzero(self) -> None:
        status, stdout, stderr = self.run_compare(
            ["compare", "target.o", "/nonexistent/candidate.o"]
        )

        self.assertNotEqual(status, 0)
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)
        self.assertIn("/nonexistent/candidate.o", stderr)
        self.assertEqual(stdout, "")

    def test_the_json_failure_is_one_schema_named_document(self) -> None:
        import json

        status, stdout, _ = self.run_compare(
            ["compare", "target.o", "/nonexistent/candidate.o", "--json"]
        )

        self.assertEqual(status, 2)
        document = json.loads(stdout)
        self.assertEqual(document["schema"], "decomp-workbench-error-v1")
        # `not-found`, not the generic `process-failed`: the classifier
        # reads the cause out of the message, and a driver that branches on
        # `kind` can tell a missing file from a broken toolchain.
        self.assertEqual(document["error"]["kind"], "not-found")
        self.assertIn("/nonexistent/candidate.o", document["error"]["message"])
        self.assertNotIn("exact", document)

    def test_compare_dumps_against_a_missing_file_exits_nonzero(self) -> None:
        status, stdout, stderr = run_cli(
            ["compare-dumps", "/nonexistent/target.objdump", "/nonexistent/c.objdump"]
        )

        self.assertEqual(status, 2)
        self.assertIn("/nonexistent/target.objdump", stderr)
        self.assertEqual(stdout, "")

    def test_an_unreadable_candidate_is_not_read_as_an_empty_one(self) -> None:
        # An existing but non-ELF file is the more dangerous shape: the path
        # resolves, so a check for existence passes, and only objdump knows.
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.o"
            candidate.write_text("not an object\n", encoding="utf-8")

            def unreadable(
                command: list[str], **kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    command, 1, "", "objdump: file format not recognized\n"
                )

            with (
                mock.patch("decomp_workbench.objdump.subprocess.run", unreadable),
                mock.patch.object(objdump, "discover_objdump", lambda value=None: "od"),
            ):
                status, stdout, stderr = run_cli(
                    ["compare", "target.o", str(candidate)]
                )

        self.assertEqual(status, 2)
        self.assertIn("MIPS ELF object", stderr)
        self.assertEqual(stdout, "")

    def test_rank_reports_a_missing_candidate_rather_than_ranking_around_it(
        self,
    ) -> None:
        # `rank` deliberately continues past one bad candidate, which is the
        # right call for a sweep -- but the failure has to appear in the
        # report, or a sweep silently ranks N-1 candidates as if it ranked N.
        import json

        status, stdout, _ = self.run_compare(
            ["rank", "target.o", "/nonexistent/a.o", "--json"]
        )

        document = json.loads(stdout)
        self.assertEqual(
            [item["candidate"] for item in document["errors"]], ["/nonexistent/a.o"]
        )
        self.assertNotEqual(status, 0)
