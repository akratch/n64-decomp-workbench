"""The preprocessor-conditional audit: evaluator, findings, multi-file, CLI."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench import context_lint
from decomp_workbench.cli import main
from decomp_workbench.context_lint import (
    ExpressionError,
    analyze_expression,
    file_scope_definitions,
    lint_files,
    lint_sources,
    parse_defines,
    render_report,
    scan_conditionals,
    strip_comments,
)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ExpressionEvaluatorTests(unittest.TestCase):
    """The small cpp constant-expression subset, in isolation."""

    def test_bare_literals_need_no_macro_table(self) -> None:
        analysis = analyze_expression("1 + 2 * 3", {})
        self.assertTrue(analysis.ok)
        self.assertEqual(analysis.value, 7)
        self.assertEqual(analysis.value_identifiers, ())

    def test_precedence_matches_c(self) -> None:
        cases = {
            "2 + 3 * 4": 14,
            "(2 + 3) * 4": 20,
            "1 << 2 + 1": 8,  # + binds tighter than <<
            "1 | 0 && 0": 0,  # | binds tighter than &&: (1 | 0) && 0
            "4 - 2 - 1": 1,  # left-associative
            "2 == 1 + 1": 1,
            "!0 && !1": 0,
            "~0": -1,
            "-3 % 2": -1,  # C truncating modulo, not floor
            "-7 / 2": -3,  # C truncating division, not floor
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                analysis = analyze_expression(expression, {})
                self.assertTrue(analysis.ok, analysis.error)
                self.assertEqual(analysis.value, expected)

    def test_ternary_evaluates_the_selected_branch(self) -> None:
        analysis = analyze_expression("1 ? 10 : 20", {})
        self.assertEqual(analysis.value, 10)
        analysis = analyze_expression("0 ? 10 : 20", {})
        self.assertEqual(analysis.value, 20)

    def test_defined_checks_presence_without_becoming_a_value_identifier(self) -> None:
        analysis = analyze_expression("defined(FOO)", {"FOO": None})
        self.assertTrue(analysis.ok)
        self.assertEqual(analysis.value, 1)
        self.assertEqual(analysis.value_identifiers, ())

        analysis = analyze_expression("defined FOO", {})
        self.assertEqual(analysis.value, 0)
        self.assertEqual(analysis.value_identifiers, ())

    def test_defined_and_bare_reference_are_independent(self) -> None:
        analysis = analyze_expression("defined(FOO) && BAR", {"FOO": None})
        # BAR is undefined -> 0, so the conjunction is false regardless of FOO.
        self.assertEqual(analysis.value, 0)
        self.assertEqual(analysis.value_identifiers, ("BAR",))
        self.assertEqual(analysis.undefined_identifiers, ("BAR",))

    def test_defined_macro_with_a_value_substitutes_it(self) -> None:
        analysis = analyze_expression("VERSION >= 3", {"VERSION": 5})
        self.assertEqual(analysis.value, 1)
        self.assertEqual(analysis.defined_identifiers, ("VERSION",))
        self.assertEqual(analysis.undefined_identifiers, ())

    def test_defined_macro_with_no_value_is_treated_as_one(self) -> None:
        analysis = analyze_expression("FLAG", {"FLAG": None})
        self.assertEqual(analysis.value, 1)

    def test_undefined_bare_identifier_collapses_to_zero(self) -> None:
        analysis = analyze_expression("BUILD_VERSION", {})
        self.assertEqual(analysis.value, 0)
        self.assertEqual(analysis.undefined_identifiers, ("BUILD_VERSION",))

    def test_the_drawbitmap_trap_expression(self) -> None:
        """0 >= 0 is true: the exact mechanism that hid `drawbitmap`."""

        analysis = analyze_expression("BUILD_VERSION >= VERSION_J", {})
        self.assertTrue(analysis.ok)
        self.assertEqual(analysis.value, 1)
        self.assertEqual(
            analysis.undefined_identifiers, ("BUILD_VERSION", "VERSION_J")
        )

    def test_function_like_reference_still_collects_argument_identifiers(self) -> None:
        analysis = analyze_expression("FOO(BAR, 1)", {})
        self.assertTrue(analysis.ok)
        self.assertIn("FOO", analysis.value_identifiers)
        self.assertIn("BAR", analysis.value_identifiers)

    def test_unparseable_expression_reports_ok_false_with_an_error(self) -> None:
        analysis = analyze_expression("(1 +", {})
        self.assertFalse(analysis.ok)
        self.assertIsNotNone(analysis.error)
        self.assertIsNone(analysis.value)

    def test_division_and_modulo_by_zero_are_reported_not_raised_to_the_caller(
        self,
    ) -> None:
        for expression in ("1 / 0", "1 % 0"):
            with self.subTest(expression=expression):
                analysis = analyze_expression(expression, {})
                self.assertFalse(analysis.ok)

    def test_char_and_hex_and_octal_literals(self) -> None:
        cases = {"'A'": 65, "0x2A": 42, "052": 42, "'\\n'": 10}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                analysis = analyze_expression(expression, {})
                self.assertEqual(analysis.value, expected)

    def test_tokenizer_rejects_unknown_characters(self) -> None:
        with self.assertRaises(ExpressionError):
            context_lint._tokenize("FOO $ BAR")


class CommentStrippingTests(unittest.TestCase):
    def test_line_and_block_comments_are_blanked_but_lines_survive(self) -> None:
        text = "a // comment\nb /* block\nspans */ c\n"
        stripped = strip_comments(text)
        self.assertEqual(text.count("\n"), stripped.count("\n"))
        self.assertNotIn("comment", stripped)
        self.assertNotIn("spans", stripped)
        self.assertIn("a", stripped)
        self.assertIn("c", stripped)

    def test_comment_markers_inside_strings_are_preserved(self) -> None:
        text = 'const char *s = "http://example.com";\n'
        stripped = strip_comments(text)
        self.assertIn("http://example.com", stripped)


class FindingClassificationTests(unittest.TestCase):
    """Each finding class the module promises, from a minimal fixture."""

    def test_all_undefined_and_true_is_high_severity(self) -> None:
        text = (
            "#if BUILD_VERSION >= VERSION_J\n"
            "case DRAW_SOMETHING:\n"
            "    do_thing();\n"
            "#endif\n"
        )
        findings = scan_conditionals(text, "drawbitmap.c", {})
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.kind, "always-true-by-absence")
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.directive, "if")
        self.assertEqual(finding.line, 1)
        self.assertEqual(finding.region_first_line, 2)
        self.assertEqual(finding.region_last_line, 3)
        self.assertEqual(finding.region_line_count, 2)
        self.assertEqual(finding.region_first_source_line, "case DRAW_SOMETHING:")
        self.assertEqual(
            set(finding.undefined_identifiers), {"BUILD_VERSION", "VERSION_J"}
        )
        self.assertIn("define", finding.action)

    def test_all_undefined_and_false_is_informational(self) -> None:
        text = "#if OLD_FEATURE_A && OLD_FEATURE_B\ndead_code();\n#endif\n"
        findings = scan_conditionals(text, "legacy.c", {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "always-false-by-absence")
        self.assertEqual(findings[0].severity, "info")

    def test_mixed_defined_and_undefined_is_noted(self) -> None:
        text = "#if KNOWN_FLAG && UNKNOWN_FLAG\nmaybe();\n#endif\n"
        findings = scan_conditionals(text, "mixed.c", {"KNOWN_FLAG": 1})
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.kind, "mixed-defined-undefined")
        self.assertEqual(finding.undefined_identifiers, ("UNKNOWN_FLAG",))
        self.assertEqual(finding.defined_identifiers, ("KNOWN_FLAG",))

    def test_unparseable_expression_is_its_own_class(self) -> None:
        text = "#if (BROKEN\nnever();\n#endif\n"
        findings = scan_conditionals(text, "broken.c", {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "unparseable-expression")
        self.assertEqual(findings[0].severity, "note")
        self.assertIn("could not parse", findings[0].action)

    def test_fully_defined_expression_produces_no_finding(self) -> None:
        text = "#if VERSION >= 3\ncase A:\n#endif\n"
        findings = scan_conditionals(text, "fine.c", {"VERSION": 5})
        self.assertEqual(findings, [])

    def test_pure_defined_check_produces_no_finding(self) -> None:
        """`#ifdef`-shaped usage is not the collapse-by-absence trap."""

        text = "#if defined(FEATURE)\ncase A:\n#endif\n"
        findings = scan_conditionals(text, "fine.c", {})
        self.assertEqual(findings, [])

    def test_elif_is_scanned_the_same_way_as_if(self) -> None:
        text = (
            "#if 0\n"
            "never();\n"
            "#elif BUILD_VERSION >= VERSION_J\n"
            "case DRAW_SOMETHING:\n"
            "#endif\n"
        )
        findings = scan_conditionals(text, "drawbitmap.c", {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].directive, "elif")
        self.assertEqual(findings[0].line, 3)

    def test_empty_guarded_region_reports_zero_line_count(self) -> None:
        text = "#if BUILD_VERSION >= VERSION_J\n#endif\n"
        findings = scan_conditionals(text, "empty.c", {})
        self.assertEqual(findings[0].region_line_count, 0)
        self.assertEqual(findings[0].region_first_source_line, "")

    def test_findings_are_sorted_most_severe_first(self) -> None:
        text = (
            "#if OLD_A && OLD_B\n"  # always-false -> info
            "dead();\n"
            "#endif\n"
            "#if BUILD_VERSION >= VERSION_J\n"  # always-true -> high
            "case X:\n"
            "#endif\n"
        )
        report = lint_sources((("one.c", text),))
        self.assertEqual(len(report.findings), 2)
        self.assertEqual(report.findings[0].severity, "high")
        self.assertEqual(report.findings[1].severity, "info")


class DefineAccumulationTests(unittest.TestCase):
    def test_a_define_seen_in_an_earlier_file_clears_a_later_finding(self) -> None:
        header = "#define BUILD_VERSION 3\n#define VERSION_J 5\n"
        body = "#if BUILD_VERSION >= VERSION_J\ncase X:\n#endif\n"
        report = lint_sources((("header.h", header), ("body.c", body)))
        self.assertEqual(report.findings, ())
        self.assertEqual(report.defines["BUILD_VERSION"], 3)
        self.assertEqual(report.defines["VERSION_J"], 5)

    def test_cli_define_flags_seed_the_table_before_any_file_is_read(self) -> None:
        body = "#if BUILD_VERSION >= VERSION_J\ncase X:\n#endif\n"
        report = lint_sources(
            (("body.c", body),), defines={"BUILD_VERSION": 3, "VERSION_J": 5}
        )
        self.assertEqual(report.findings, ())

    def test_undef_removes_a_macro_for_files_scanned_afterward(self) -> None:
        first = "#define FLAG 1\n"
        second = "#undef FLAG\n#if FLAG\ncase X:\n#endif\n"
        report = lint_sources((("a.c", first), ("b.c", second)))
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].kind, "always-false-by-absence")

    def test_a_computed_define_value_participates_in_later_arithmetic(self) -> None:
        text = "#define A 2\n#define B (A + 1)\n#if B >= 4\ncase X:\n#endif\n"
        report = lint_sources((("one.c", text),))
        # A=2, B=(2+1)=3, 3>=4 is false, and both identifiers are defined ->
        # no finding at all (not a collapse-by-absence case).
        self.assertEqual(report.findings, ())
        self.assertEqual(report.defines["B"], 3)

    def test_function_like_macro_is_recorded_as_defined_with_unknown_value(
        self,
    ) -> None:
        text = "#define MAX(a, b) ((a) > (b) ? (a) : (b))\n"
        report = lint_sources((("one.c", text),))
        self.assertIn("MAX", report.defines)
        self.assertIsNone(report.defines["MAX"])

    def test_line_continuation_is_spliced_before_directive_parsing(self) -> None:
        text = "#if BUILD_VERSION \\\n    >= VERSION_J\ncase X:\n#endif\n"
        findings = scan_conditionals(text, "spliced.c", {})
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "always-true-by-absence")


class ParseDefinesTests(unittest.TestCase):
    def test_bare_name_is_defined_with_no_numeric_value(self) -> None:
        defines = parse_defines(["FOO"])
        self.assertIsNone(defines["FOO"])

    def test_name_equals_value_is_parsed_as_a_constant_expression(self) -> None:
        defines = parse_defines(["VERSION=5"])
        self.assertEqual(defines["VERSION"], 5)

    def test_later_entries_may_reference_earlier_ones(self) -> None:
        defines = parse_defines(["A=2", "B=A+1"])
        self.assertEqual(defines["B"], 3)

    def test_invalid_name_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_defines(["1BAD=2"])


class FileScopeDefinitionTests(unittest.TestCase):
    def test_a_simple_static_declaration_is_found(self) -> None:
        names = file_scope_definitions("static int *prev_bmbuf = 0;\n")
        self.assertEqual(names, {"prev_bmbuf": 1})

    def test_a_one_line_function_signature_is_found(self) -> None:
        names = file_scope_definitions("s32 demo(void) {\n    return 1;\n}\n")
        self.assertEqual(names["demo"], 1)

    def test_locals_inside_a_function_body_are_not_file_scope(self) -> None:
        text = "void f(void) {\n    int x = 0;\n}\n"
        names = file_scope_definitions(text)
        self.assertNotIn("x", names)

    def test_a_function_prototype_is_not_treated_as_a_definition(self) -> None:
        names = file_scope_definitions("void f(int x);\n")
        self.assertEqual(names, {})

    def test_extern_declarations_are_excluded(self) -> None:
        names = file_scope_definitions("extern int shared_counter;\n")
        self.assertEqual(names, {})

    def test_typedef_names_are_recognized(self) -> None:
        names = file_scope_definitions("typedef unsigned int u32;\n")
        self.assertIn("u32", names)


class LintFilesTests(unittest.TestCase):
    def test_files_are_read_in_order_and_defines_accumulate_across_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "header.h"
            body = root / "body.c"
            header.write_text("#define BUILD_VERSION 3\n#define VERSION_J 5\n")
            body.write_text("#if BUILD_VERSION >= VERSION_J\ncase X:\n#endif\n")

            report = lint_files([header, body])

        self.assertEqual(report.files, (str(header), str(body)))
        self.assertEqual(report.findings, ())


class RenderReportTests(unittest.TestCase):
    def test_zero_findings_is_one_calm_line_not_silence(self) -> None:
        report = lint_sources((("a.c", "int x;\n"),))
        lines = render_report(report)
        self.assertEqual(len(lines), 2)
        self.assertIn("0 finding", lines[0])
        self.assertIn("no undefined-identifier collapse", lines[1])

    def test_a_finding_shows_the_first_guarded_line_and_a_do_action(self) -> None:
        text = "#if BUILD_VERSION >= VERSION_J\ncase DRAW_SOMETHING:\n#endif\n"
        report = lint_sources((("drawbitmap.c", text),))
        lines = "\n".join(render_report(report))
        self.assertIn("DRAW_SOMETHING", lines)
        self.assertIn("do:", lines)
        self.assertIn("HIGH", lines)


class ContextLintCliTests(unittest.TestCase):
    def test_lint_reports_the_trap_and_exits_zero_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "drawbitmap.c"
            source.write_text(
                "#if BUILD_VERSION >= VERSION_J\ncase DRAW_SOMETHING:\n#endif\n"
            )
            status, stdout, stderr = run_cli(["context", "lint", str(source)])

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("always-true-by-absence", stdout)
        self.assertIn("DRAW_SOMETHING", stdout)

    def test_fail_on_high_returns_one_when_a_high_finding_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "drawbitmap.c"
            source.write_text(
                "#if BUILD_VERSION >= VERSION_J\ncase DRAW_SOMETHING:\n#endif\n"
            )
            status, _, _ = run_cli(
                ["context", "lint", str(source), "--fail-on-high"]
            )

        self.assertEqual(status, 1)

    def test_define_flag_resolves_the_trap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "drawbitmap.c"
            source.write_text(
                "#if BUILD_VERSION >= VERSION_J\ncase DRAW_SOMETHING:\n#endif\n"
            )
            status, stdout, _ = run_cli(
                [
                    "context",
                    "lint",
                    str(source),
                    "--define",
                    "BUILD_VERSION=3",
                    "--define",
                    "VERSION_J=5",
                    "--fail-on-high",
                ]
            )

        self.assertEqual(status, 0)
        self.assertIn("no undefined-identifier collapse", stdout)

    def test_json_output_has_the_documented_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "drawbitmap.c"
            source.write_text(
                "#if BUILD_VERSION >= VERSION_J\ncase DRAW_SOMETHING:\n#endif\n"
            )
            status, stdout, stderr = run_cli(
                ["context", "lint", str(source), "--json"]
            )

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-context-lint-v1")
        self.assertEqual(len(payload["findings"]), 1)
        finding = payload["findings"][0]
        self.assertEqual(finding["kind"], "always-true-by-absence")
        self.assertEqual(finding["severity"], "high")
        self.assertIn("region", finding)
        self.assertIn("first_line", finding["region"])
        self.assertIn("action", finding)

    def test_multiple_files_are_scanned_in_the_given_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            header = Path(temporary) / "header.h"
            body = Path(temporary) / "body.c"
            header.write_text("#define BUILD_VERSION 3\n#define VERSION_J 5\n")
            body.write_text("#if BUILD_VERSION >= VERSION_J\ncase X:\n#endif\n")

            status, stdout, _ = run_cli(
                ["context", "lint", str(header), str(body)]
            )

        self.assertEqual(status, 0)
        self.assertIn("0 finding", stdout)

    def test_missing_file_is_a_usage_error_not_a_traceback(self) -> None:
        status, _, stderr = run_cli(["context", "lint", "/no/such/file.c"])
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_the_command_map_lists_context_lint(self) -> None:
        status, stdout, _ = run_cli(["commands", "--json"])
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertIn("context", payload["groups"])


if __name__ == "__main__":
    unittest.main()
