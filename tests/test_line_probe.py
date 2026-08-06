"""Tests for the line-assignment probe's tokenizer, ELF reader, and verdicts."""

from __future__ import annotations

import struct
import sys
import tempfile
import textwrap
import unittest
from collections.abc import Sequence
from pathlib import Path

from fake_object import build_elf32

from decomp_workbench.line_probe import (
    VERDICT_LINE_SENSITIVE,
    VERDICT_NONDETERMINISTIC,
    VERDICT_NOT_LINE_SENSITIVE,
    ElfFormatError,
    LineProbeError,
    classify_verdict,
    extract_text_window,
    global_shift,
    next_steps,
    run_line_probe,
    score_against_target,
    split_statement_lines,
    tie_statement_lines,
    word_diff_positions,
)

TESTS_DIR = Path(__file__).resolve().parent

#: A self-contained fake "compiler": no real cc/IDO involved. It hashes
#: whitespace-delimited tokens into 4-byte words and wraps them in a minimal
#: ELF32 object built by `fake_object.build_elf32`. Mode selects whether the
#: word order is sensitive to physical line boundaries (see the module
#: docstring in `line_probe.py` for why that is the whole experiment).
COMPILER_SCRIPT = textwrap.dedent(
    f"""\
    import hashlib
    import sys
    from pathlib import Path

    sys.path.insert(0, {str(TESTS_DIR)!r})
    from fake_object import build_elf32

    mode = sys.argv[1]
    source = Path(sys.argv[2])
    output = Path(sys.argv[3])
    text = source.read_text(encoding="utf-8")

    def word_for(token):
        return hashlib.sha256(token.encode("utf-8")).digest()[:4]

    words = []
    if mode == "sensitive":
        for line in text.splitlines():
            for token in reversed(line.split()):
                words.append(word_for(token))
    elif mode == "insensitive":
        for token in text.split():
            words.append(word_for(token))
    elif mode == "nondeterministic":
        words.append(word_for(str(text.count(chr(10)))))
        for token in text.split():
            words.append(word_for(token))
    elif mode == "fail":
        sys.stderr.write("synthetic compiler error: refusing to compile\\n")
        raise SystemExit(1)
    else:
        raise SystemExit("unknown mode: " + mode)

    text_bytes = b"".join(words)
    half = (len(text_bytes) // 4 // 2) * 4
    symbols = [("prefix_fn", 0, half), ("target_fn", half, len(text_bytes) - half)]
    output.write_bytes(build_elf32(text_bytes, symbols))
    """
)

#: A single statement-dense line, long enough to pass a low --split-threshold,
#: nested one brace deep (as `split-statements` requires).
SOURCE = "int f(void) {\n    aaaa; bbbb; cccc; dddd;\n}\n"


def write_compiler(directory: Path) -> Path:
    script = directory / "fake_compiler.py"
    script.write_text(COMPILER_SCRIPT, encoding="utf-8")
    return script


def compile_template(script: Path, mode: str) -> str:
    return f"{sys.executable} {script} {mode} {{input}} {{output}}"


class SplitStatementLinesTests(unittest.TestCase):
    def test_splits_only_overlong_lines(self) -> None:
        short = split_statement_lines(SOURCE, threshold=1000)
        self.assertEqual(short, SOURCE)
        long_split = split_statement_lines(SOURCE, threshold=10)
        self.assertIn("aaaa;\n bbbb;\n cccc;\n dddd;", long_split)

    def test_ignores_semicolons_in_string_and_char_literals(self) -> None:
        source = "void h(void) { char *s = \"a;b;c\"; char ch = ';'; int n = 1; }"
        result = split_statement_lines(source, threshold=5)
        self.assertIn('"a;b;c"', result)
        self.assertNotIn("a;\nb;\nc", result)
        self.assertIn("';';", result)

    def test_ignores_semicolons_in_line_and_block_comments(self) -> None:
        source = (
            "void h(void) { /* a;b;c */ int n = 1; // trailing ; comment\nint m = 2; }"
        )
        result = split_statement_lines(source, threshold=5)
        self.assertIn("/* a;b;c */", result)
        self.assertIn("// trailing ; comment", result)
        # The real statement semicolons still split.
        self.assertIn("n = 1;\n", result)

    def test_does_not_split_a_for_header(self) -> None:
        source = (
            "void g(void) { for (i = 0; i < 10; i++) { "
            "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx = 1; } }"
        )
        result = split_statement_lines(source, threshold=10)
        self.assertIn("for (i = 0; i < 10; i++)", result)
        self.assertIn("= 1;\n", result)

    def test_does_not_split_an_empty_for_header(self) -> None:
        source = "void g(void) { for (;;) { aaaaaaaaaaaaaaaaaaaaaaaaaaaa = 1; } }"
        result = split_statement_lines(source, threshold=5)
        self.assertIn("for (;;)", result)

    def test_does_not_split_outside_a_brace(self) -> None:
        source = "int a; int b; int c; int d; int e; int f; int g; int h;"
        self.assertGreater(len(source), 5)
        result = split_statement_lines(source, threshold=5)
        self.assertEqual(result, source)

    def test_handles_nested_braces(self) -> None:
        source = (
            "void g(void) { if (x) { "
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa = 1; b = 2; "
            "} }"
        )
        result = split_statement_lines(source, threshold=10)
        self.assertIn("= 1;\n", result)
        self.assertIn("b = 2;\n", result)

    def test_rejects_non_positive_threshold(self) -> None:
        with self.assertRaisesRegex(LineProbeError, "split-threshold"):
            split_statement_lines(SOURCE, threshold=0)


class GlobalShiftTests(unittest.TestCase):
    def test_prepends_blank_lines(self) -> None:
        self.assertEqual(global_shift("abc\n", blank_lines=3), "\n\n\nabc\n")

    def test_zero_blank_lines_is_a_no_op(self) -> None:
        self.assertEqual(global_shift("abc\n", blank_lines=0), "abc\n")

    def test_rejects_negative_blank_lines(self) -> None:
        with self.assertRaisesRegex(LineProbeError, "shift-lines"):
            global_shift("abc\n", blank_lines=-1)


class ElfWindowTests(unittest.TestCase):
    def _write(
        self,
        directory: Path,
        text_bytes: bytes,
        symbols: Sequence[tuple[str, int, int]] = (),
    ) -> Path:
        path = directory / "unit.o"
        path.write_bytes(build_elf32(text_bytes, list(symbols)))
        return path

    def test_whole_text_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            text_bytes = bytes(range(4 * 8))
            path = self._write(Path(temp), text_bytes)
            window = extract_text_window(path, function=None)
            self.assertEqual(len(window.words), 8)
            self.assertIn("whole section", window.source)

    def test_function_window_slices_the_right_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            text_bytes = b"".join(bytes([i]) * 4 for i in range(8))
            path = self._write(
                Path(temp),
                text_bytes,
                symbols=[("prefix_fn", 0, 16), ("target_fn", 16, 16)],
            )
            window = extract_text_window(path, function="target_fn")
            self.assertEqual(
                window.words,
                (
                    b"\x04\x04\x04\x04",
                    b"\x05\x05\x05\x05",
                    b"\x06\x06\x06\x06",
                    b"\x07\x07\x07\x07",
                ),
            )

    def test_missing_function_suggests_whole_text_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(Path(temp), b"\x00" * 16, symbols=[("known_fn", 0, 16)])
            with self.assertRaisesRegex(
                ElfFormatError, "no symbol named 'missing_fn'"
            ) as ctx:
                extract_text_window(path, function="missing_fn")
            message = str(ctx.exception)
            self.assertIn("whole-.text mode", message)
            self.assertIn("IDO", message)
            self.assertIn("static", message)
            self.assertIn("known_fn", message)

    def test_function_missing_symtab_suggests_whole_text_mode(self) -> None:
        # Build an object with .text but drop the two symbol-table sections.
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "no-symtab.o"
            shstrtab = b"\x00.text\x00.shstrtab\x00"
            text_bytes = b"\x00" * 8
            header_size = 52
            text_off = header_size
            shstrtab_off = text_off + len(text_bytes)
            shoff = shstrtab_off + len(shstrtab)
            sections = [
                (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                (1, 1, 0x6, 0, text_off, len(text_bytes), 0, 0, 4, 0),
                (7, 3, 0, 0, shstrtab_off, len(shstrtab), 0, 0, 1, 0),
            ]
            section_blob = b"".join(
                struct.pack(">IIIIIIIIII", *entry) for entry in sections
            )
            e_ident = b"\x7fELF" + bytes([1, 2, 1]) + b"\x00" * 9
            header = e_ident + struct.pack(
                ">HHIIIIIHHHHHH", 1, 8, 1, 0, 0, shoff, 0, 52, 0, 0, 40, 3, 2
            )
            path.write_bytes(header + text_bytes + shstrtab + section_blob)
            with self.assertRaisesRegex(ElfFormatError, "no .symtab") as ctx:
                extract_text_window(path, function="anything")
            self.assertIn("whole-.text mode", str(ctx.exception))

    def test_rejects_non_elf_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "not-an-object.o"
            path.write_bytes(b"not an elf file at all")
            with self.assertRaisesRegex(ElfFormatError, "ELF"):
                extract_text_window(path, function=None)

    def test_zero_size_symbol_suggests_whole_text_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self._write(Path(temp), b"\x00" * 8, symbols=[("stripped_fn", 0, 0)])
            with self.assertRaisesRegex(ElfFormatError, "size 0") as ctx:
                extract_text_window(path, function="stripped_fn")
            self.assertIn("whole-.text mode", str(ctx.exception))

    def test_non_multiple_of_four_window_keeps_a_short_trailing_word(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            text_bytes = b"\x01\x02\x03\x04\x05\x06"  # 6 bytes: one word + 2
            path = self._write(Path(temp), text_bytes)
            window = extract_text_window(path, function=None)
            self.assertEqual(window.words, (b"\x01\x02\x03\x04", b"\x05\x06"))


class WordScoringTests(unittest.TestCase):
    def test_word_diff_counts_positions_and_length_difference(self) -> None:
        left = (b"aaaa", b"bbbb", b"cccc")
        right = (b"aaaa", b"xxxx")
        self.assertEqual(word_diff_positions(left, right), 2)

    def test_score_against_target_partitions_toward_away_unchanged(self) -> None:
        target = (b"1111", b"2222", b"3333", b"4444")
        baseline = (b"0000", b"2222", b"3333", b"9999")  # mismatches at 0, 3
        # variant fixes site 0, breaks site 2, leaves 1 and 3 as-is.
        variant = (b"1111", b"2222", b"0000", b"9999")
        score = score_against_target(variant, baseline, target)
        self.assertEqual(score["toward"], 1)
        self.assertEqual(score["away"], 1)
        self.assertEqual(score["unchanged"], 2)
        self.assertEqual(score["total_positions"], 4)
        self.assertEqual(
            score["toward"] + score["away"] + score["unchanged"],
            score["total_positions"],
        )

    def test_score_against_target_self_comparison_is_all_unchanged(self) -> None:
        baseline = (b"1111", b"2222")
        target = (b"9999", b"9999")
        score = score_against_target(baseline, baseline, target)
        self.assertEqual(score["toward"], 0)
        self.assertEqual(score["away"], 0)
        self.assertEqual(score["unchanged"], 2)


class ClassifyVerdictTests(unittest.TestCase):
    def test_line_sensitive_names_the_lever_and_recipe(self) -> None:
        verdict, message = classify_verdict(4, 0, shift_lines=20)
        self.assertEqual(verdict, VERDICT_LINE_SENSITIVE)
        self.assertIn("LINE-SENSITIVE", message)
        self.assertIn("field-guide lever 23", message)
        self.assertIn("acpp", message)

    def test_not_line_sensitive(self) -> None:
        verdict, message = classify_verdict(0, 0, shift_lines=20)
        self.assertEqual(verdict, VERDICT_NOT_LINE_SENSITIVE)
        self.assertIn("NOT line-sensitive", message)

    def test_nondeterministic_control_failure_takes_priority(self) -> None:
        verdict, message = classify_verdict(4, 2, shift_lines=20)
        self.assertEqual(verdict, VERDICT_NONDETERMINISTIC)
        self.assertIn("NONDETERMINISTIC", message)
        self.assertIn("untrustworthy", message)
        self.assertIn("20", message)


class RunLineProbeTests(unittest.TestCase):
    def _write_input(self, directory: Path) -> Path:
        source = directory / "unit.i"
        source.write_text(SOURCE, encoding="utf-8")
        return source

    def test_line_sensitive_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "sensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
            )
            self.assertEqual(report["verdict"], VERDICT_LINE_SENSITIVE)
            self.assertGreater(report["split_word_diff"], 0)
            self.assertEqual(report["shift_word_diff"], 0)
            run_dir = Path(report["run_directory"])
            self.assertTrue(run_dir.is_dir())
            for name in ("baseline", "split-statements", "global-shift"):
                self.assertTrue(Path(report["variants"][name]["object_path"]).is_file())

    def test_not_line_sensitive_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "insensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
            )
            self.assertEqual(report["verdict"], VERDICT_NOT_LINE_SENSITIVE)
            self.assertEqual(report["split_word_diff"], 0)
            self.assertEqual(report["shift_word_diff"], 0)

    def test_nondeterministic_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "nondeterministic"),
                split_threshold=10,
                shift_lines=5,
                work_dir=root / "state",
                compile_cwd=root,
            )
            self.assertEqual(report["verdict"], VERDICT_NONDETERMINISTIC)
            self.assertGreater(report["shift_word_diff"], 0)

    def test_target_scoring_reports_toward_away_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            # Compile the split variant once up front to build a target that
            # partially agrees with it and partially still needs the split.
            baseline_probe = run_line_probe(
                source,
                compile_template=compile_template(script, "sensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
            )
            # Use the split-statements object itself as the target, via
            # --target-object so it is windowed through the same ELF .text
            # extraction as every variant: a variant scored against its own
            # words has every mismatched baseline site moving toward it, and
            # no site regressing.
            split_object = Path(
                baseline_probe["variants"]["split-statements"]["object_path"]
            )
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "sensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
                target_object=split_object,
            )
            target = report["target"]
            self.assertIsNotNone(target)
            baseline_score = target["baseline"]
            split_score = target["split-statements"]
            self.assertGreater(baseline_score["mismatched_vs_target"], 0)
            self.assertEqual(split_score["away"], 0)
            self.assertGreater(split_score["toward"], 0)
            self.assertEqual(
                split_score["toward"] + split_score["away"] + split_score["unchanged"],
                split_score["total_positions"],
            )

    def test_compile_failure_points_at_the_captured_stderr_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            with self.assertRaises(RuntimeError) as ctx:
                run_line_probe(
                    source,
                    compile_template=compile_template(script, "fail"),
                    split_threshold=10,
                    work_dir=root / "state",
                    compile_cwd=root,
                )
            message = str(ctx.exception)
            self.assertIn("full stderr:", message)
            stderr_line = next(
                line for line in message.splitlines() if line.startswith("full stderr:")
            )
            stderr_path = Path(stderr_line.removeprefix("full stderr:").strip())
            self.assertTrue(stderr_path.is_file())
            self.assertIn(
                "synthetic compiler error",
                stderr_path.read_text(encoding="utf-8"),
            )

    def test_run_directory_is_retained_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            with self.assertRaises(RuntimeError) as ctx:
                run_line_probe(
                    source,
                    compile_template=compile_template(script, "fail"),
                    split_threshold=10,
                    work_dir=root / "state",
                    compile_cwd=root,
                )
            run_dir_line = next(
                line
                for line in str(ctx.exception).splitlines()
                if line.startswith("run directory")
            )
            run_dir = Path(run_dir_line.split(":", 1)[1].strip())
            self.assertTrue(run_dir.is_dir())
            self.assertTrue((run_dir / "baseline" / "compile.stderr.txt").is_file())

    def test_missing_input_names_where_a_dot_i_comes_from(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = write_compiler(root)
            with self.assertRaisesRegex(FileNotFoundError, "cc -E"):
                run_line_probe(
                    root / "missing.i",
                    compile_template=compile_template(script, "sensitive"),
                    work_dir=root / "state",
                    compile_cwd=root,
                )

    def test_target_bytes_and_target_object_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            with self.assertRaisesRegex(LineProbeError, "mutually exclusive"):
                run_line_probe(
                    source,
                    compile_template=compile_template(script, "sensitive"),
                    work_dir=root / "state",
                    compile_cwd=root,
                    target_bytes=root / "a",
                    target_object=root / "b",
                )

    def test_target_offset_requires_target_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            with self.assertRaisesRegex(LineProbeError, "target-offset"):
                run_line_probe(
                    source,
                    compile_template=compile_template(script, "sensitive"),
                    work_dir=root / "state",
                    compile_cwd=root,
                    target_offset=4,
                )


class TieStatementLinesTest(unittest.TestCase):
    """--tie N=M reassigns one statement's line number via a #line pair."""

    SOURCE = "int a;\nint b;\nint c;\nint d;\n"

    def test_single_tie_wraps_statement_in_line_directives(self) -> None:
        from decomp_workbench.line_probe import tie_statement_lines

        tied = tie_statement_lines(self.SOURCE, [(2, 4)])
        self.assertEqual(
            tied,
            "int a;\n#line 4\nint b;\n#line 3\nint c;\nint d;\n",
        )

    def test_multiple_ties_use_original_numbering(self) -> None:
        from decomp_workbench.line_probe import tie_statement_lines

        tied = tie_statement_lines(self.SOURCE, [(1, 3), (3, 1)])
        self.assertEqual(
            tied,
            "#line 3\nint a;\n#line 2\nint b;\n#line 1\nint c;\n#line 4\nint d;\n",
        )

    def test_tie_line_out_of_range_is_rejected(self) -> None:
        from decomp_workbench.line_probe import LineProbeError, tie_statement_lines

        with self.assertRaises(LineProbeError):
            tie_statement_lines(self.SOURCE, [(9, 1)])
        with self.assertRaises(LineProbeError):
            tie_statement_lines(self.SOURCE, [(0, 2)])

    def test_tie_variant_joins_generate_variants(self) -> None:
        from decomp_workbench.line_probe import generate_variants

        variants = generate_variants(self.SOURCE, ties=[(2, 4)])
        self.assertIn("tie", variants)
        self.assertIn("#line 4", variants["tie"])
        variants_without = generate_variants(self.SOURCE)
        self.assertNotIn("tie", variants_without)


class TieValidationTest(unittest.TestCase):
    """A tie names a statement; the probe refuses inputs that name none.

    Each rejection here is a variant that would have compiled successfully and
    reported an honest-looking zero: the run costs a build and teaches the
    reader that the mechanism does not apply, which is exactly the false
    negative this probe exists to prevent.
    """

    SOURCE = "int a;\n\n#line 40\nint c;\n"

    def test_duplicate_statement_line_names_both_assignments(self) -> None:
        with self.assertRaises(LineProbeError) as caught:
            tie_statement_lines(self.SOURCE, [(1, 5), (1, 6)])
        message = str(caught.exception)
        self.assertIn("statement line 1 twice", message)
        self.assertIn("5", message)
        self.assertIn("6", message)

    def test_a_blank_line_carries_no_statement(self) -> None:
        with self.assertRaisesRegex(LineProbeError, "blank"):
            tie_statement_lines(self.SOURCE, [(2, 9)])

    def test_a_preprocessing_directive_carries_no_statement(self) -> None:
        with self.assertRaisesRegex(LineProbeError, "preprocessing directive"):
            tie_statement_lines(self.SOURCE, [(3, 9)])

    def test_an_assigned_line_past_the_end_of_the_file_is_allowed(self) -> None:
        """The number a statement needs is not bounded by the file's length."""

        tied = tie_statement_lines(self.SOURCE, [(4, 900)])
        self.assertIn("#line 900\n", tied)

    def test_an_assigned_line_below_one_is_rejected(self) -> None:
        with self.assertRaisesRegex(LineProbeError, "assigned line number"):
            tie_statement_lines(self.SOURCE, [(4, 0)])


class NextStepsTests(unittest.TestCase):
    """The verdict names the mechanism; these name the next command."""

    def test_a_line_sensitive_verdict_without_ties_routes_to_tie(self) -> None:
        steps = "\n".join(next_steps(VERDICT_LINE_SENSITIVE))
        self.assertIn("--tie STATEMENT=LINE", steps)
        self.assertIn("--target-object", steps)

    def test_an_already_scored_run_is_not_told_to_pass_target_again(self) -> None:
        steps = next_steps(
            VERDICT_LINE_SENSITIVE,
            target={"baseline": {"toward": 0, "away": 0}},
        )
        self.assertEqual(len(steps), 1)
        self.assertIn("--tie STATEMENT=LINE", steps[0])

    def test_an_unscored_tie_is_told_to_score_itself(self) -> None:
        steps = "\n".join(next_steps(VERDICT_LINE_SENSITIVE, ties=[(3, 5)]))
        self.assertIn("nothing scored it", steps)

    def test_a_winning_tie_routes_to_the_natural_spelling(self) -> None:
        steps = "\n".join(
            next_steps(
                VERDICT_LINE_SENSITIVE,
                ties=[(3, 5)],
                target={"tie": {"toward": 4, "away": 0}},
            )
        )
        self.assertIn("4 site(s) toward", steps)
        self.assertIn("guide 25", steps)

    def test_a_losing_tie_says_so_and_scopes_the_negative(self) -> None:
        steps = "\n".join(
            next_steps(
                VERDICT_LINE_SENSITIVE,
                ties=[(3, 5)],
                target={"tie": {"toward": 1, "away": 6}},
            )
        )
        self.assertIn("not the one", steps)
        self.assertIn("scoped", steps)

    def test_a_negative_result_still_routes_somewhere(self) -> None:
        steps = "\n".join(next_steps(VERDICT_NOT_LINE_SENSITIVE))
        self.assertIn("guide g0-schedule-probe", steps)

    def test_a_failed_control_routes_nowhere(self) -> None:
        """Nothing downstream of a broken control is earned."""

        self.assertEqual(next_steps(VERDICT_NONDETERMINISTIC), ())


class TieReportTests(unittest.TestCase):
    def test_the_report_records_the_ties_that_defined_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "unit.i"
            source.write_text(SOURCE, encoding="utf-8")
            script = write_compiler(root)
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "sensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
                ties=[(2, 1)],
            )
            self.assertEqual(report["ties"], [[2, 1]])
            self.assertIsNotNone(report["tie_word_diff"])
            self.assertIn("tie", report["variants"])
            self.assertTrue(report["next_steps"])

    def test_a_run_without_ties_records_none_and_three_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "unit.i"
            source.write_text(SOURCE, encoding="utf-8")
            script = write_compiler(root)
            report = run_line_probe(
                source,
                compile_template=compile_template(script, "sensitive"),
                split_threshold=10,
                work_dir=root / "state",
                compile_cwd=root,
            )
            self.assertEqual(report["ties"], [])
            self.assertIsNone(report["tie_word_diff"])
            self.assertNotIn("tie", report["variants"])


if __name__ == "__main__":
    unittest.main()
