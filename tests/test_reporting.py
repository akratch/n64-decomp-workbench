"""Durable machine-readable output contracts."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import build_parser, main
from decomp_workbench.reporting import ERROR_SCHEMA, SCHEMAS

DUMP = """
00000000 <demo>:
   0: 03e00008  jr $ra
   4: 00000000  nop
"""


class ReportingTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_success_is_one_schema_named_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dump = Path(temporary) / "demo.objdump"
            dump.write_text(DUMP, encoding="utf-8")
            status, stdout, stderr = self.run_cli(
                ["compare-dumps", str(dump), str(dump), "--json"]
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-comparison-v1")

    def test_handler_failure_is_structured_json_not_mixed_streams(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["compare-dumps", "missing-a", "missing-b", "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], ERROR_SCHEMA)
        self.assertEqual(payload["command"], "compare-dumps")
        self.assertEqual(payload["status"], 2)
        self.assertEqual(payload["error"]["kind"], "not-found")

    def test_argument_failure_is_also_structured_json(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["compare-dumps", "--definitely-not-an-option", "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], ERROR_SCHEMA)
        self.assertEqual(payload["stage"], "command")
        self.assertEqual(payload["error"]["kind"], "usage")

    def test_human_error_contract_is_unchanged(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["compare-dumps", "missing-a", "missing-b"]
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith("error: "))

    def test_every_json_capable_parser_has_an_explicit_schema(self) -> None:
        missing: list[str] = []

        def visit(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
            option_strings = {
                option for action in parser._actions for option in action.option_strings
            }
            if "--json" in option_strings or "--json-summary" in option_strings:
                report_command = parser.get_default("report_command")
                command = (
                    str(report_command)
                    if report_command is not None
                    else path[-1]
                    if path
                    else ""
                )
                if command not in SCHEMAS:
                    missing.append(" ".join(path) + f" -> {command}")
            for action in parser._actions:
                if not isinstance(action, argparse._SubParsersAction):
                    continue
                for name, child in action.choices.items():
                    visit(child, (*path, name))

        visit(build_parser(), ())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
