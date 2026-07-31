"""CLI wiring, human-factors, and JSON-contract tests for ``probe-lines``."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from test_line_probe import SOURCE, compile_template, write_compiler

from decomp_workbench.cli import main
from decomp_workbench.reporting import SCHEMAS


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ProbeLinesHelpTests(unittest.TestCase):
    def test_help_names_every_variant_and_where_a_dot_i_comes_from(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            run_cli(["probe-lines", "--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_help_text_contents(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
            main(["probe-lines", "--help"])
        text = " ".join(stdout.getvalue().split())
        for expected in (
            "baseline",
            "split-statements",
            "global-shift",
            "cc -E",
            "-K",
            "field-guide lever 23",
            "LINE-SENSITIVE",
            "NONDETERMINISTIC",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_probe_lines_is_registered_in_the_schema_registry(self) -> None:
        self.assertIn("probe-lines", SCHEMAS)


class ProbeLinesDiscoveryTests(unittest.TestCase):
    def test_grouped_spelling_is_an_exact_alias_for_bad_input(self) -> None:
        # Both spellings should fail identically on a missing input, without
        # needing a compiler: this only exercises argument routing.
        flat = run_cli(
            ["probe-lines", "missing.i", "--compile-command", "cc {input} {output}"]
        )
        grouped = run_cli(
            ["probe", "lines", "missing.i", "--compile-command", "cc {input} {output}"]
        )
        self.assertEqual(flat, grouped)


class ProbeLinesEndToEndCliTests(unittest.TestCase):
    def _write_input(self, directory: Path) -> Path:
        source = directory / "unit.i"
        source.write_text(SOURCE, encoding="utf-8")
        return source

    def test_line_sensitive_run_reports_verdict_and_lever(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, stdout, stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "sensitive"),
                    "--split-threshold",
                    "10",
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                ]
            )
            self.assertEqual(stderr, "")
            self.assertEqual(status, 0)
            self.assertIn("LINE-SENSITIVE", stdout)
            self.assertIn("field-guide lever 23", stdout)
            self.assertIn("run directory:", stdout)

    def test_json_output_is_schema_tagged_and_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, stdout, stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "insensitive"),
                    "--split-threshold",
                    "10",
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                    "--json",
                ]
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["schema"], "decomp-workbench-line-probe-v1")
            self.assertEqual(payload["verdict"], "not-line-sensitive")

    def test_nondeterministic_control_failure_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, stdout, _stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "nondeterministic"),
                    "--split-threshold",
                    "10",
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                ]
            )
            self.assertEqual(status, 1)
            self.assertIn("NONDETERMINISTIC", stdout)

    def test_missing_function_error_has_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, stdout, stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "sensitive"),
                    "--split-threshold",
                    "10",
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                    "--function",
                    "does_not_exist",
                ]
            )
            self.assertEqual(status, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr.startswith("error: "))
            self.assertNotIn("Traceback", stderr)
            self.assertIn("whole-.text mode", stderr)
            self.assertIn("IDO", stderr)

    def test_missing_input_error_has_no_traceback(self) -> None:
        status, stdout, stderr = run_cli(
            [
                "probe-lines",
                "does-not-exist.i",
                "--compile-command",
                "cc -c {input} -o {output}",
            ]
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith("error: "))
        self.assertNotIn("Traceback", stderr)
        self.assertIn("cc -E", stderr)

    def test_target_flags_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, _stdout, stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "sensitive"),
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                    "--target-bytes",
                    str(root / "a.bin"),
                    "--target-object",
                    str(root / "b.o"),
                ]
            )
            self.assertEqual(status, 2)
            self.assertIn("mutually exclusive", stderr)

    def test_compile_failure_error_has_no_traceback_and_names_stderr_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_input(root)
            script = write_compiler(root)
            status, _stdout, stderr = run_cli(
                [
                    "probe-lines",
                    str(source),
                    "--compile-command",
                    compile_template(script, "fail"),
                    "--work-dir",
                    str(root / "state"),
                    "--compile-cwd",
                    str(root),
                ]
            )
            self.assertEqual(status, 2)
            self.assertTrue(stderr.startswith("error: "))
            self.assertNotIn("Traceback", stderr)
            self.assertIn("full stderr:", stderr)


if __name__ == "__main__":
    unittest.main()
