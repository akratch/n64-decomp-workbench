"""Journey aliases and generated command discovery stay useful and compatible."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import build_parser, main

DUMP = """
00000000 <demo>:
   0: 03e00008  jr $ra
   4: 00000000  nop
"""


class DiscoveryTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_grouped_object_command_is_an_exact_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dump = Path(temporary) / "demo.objdump"
            dump.write_text(DUMP, encoding="utf-8")
            flat = self.run_cli(["compare-dumps", str(dump), str(dump), "--json"])
            grouped = self.run_cli(
                ["object", "compare-dumps", str(dump), str(dump), "--json"]
            )
        self.assertEqual(grouped, flat)

    def test_group_without_operation_prints_a_compact_map(self) -> None:
        status, stdout, stderr = self.run_cli(["object"])
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("object diagnose", stdout)
        self.assertIn("object compare", stdout)
        self.assertNotIn("trace globalcolor", stdout)

    def test_command_map_has_a_versioned_json_form(self) -> None:
        status, stdout, stderr = self.run_cli(["commands", "--json"])
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-command-map-v1")
        self.assertIn("campaign", payload["groups"])

    def test_legacy_aliases_stay_parseable_without_polluting_help(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        self.assertNotIn("==SUPPRESS==", help_text)
        self.assertNotIn("campaign-status", help_text)
        self.assertNotIn("toolchain-init", help_text)
        self.assertEqual(
            parser.parse_args(["campaign-status"]).command,
            "campaign-status",
        )

    def test_completions_are_generated_for_four_shells(self) -> None:
        markers = {
            "bash": "complete -F",
            "zsh": "#compdef",
            "fish": "complete -c",
            "powershell": "Register-ArgumentCompleter",
        }
        for shell, marker in markers.items():
            with self.subTest(shell=shell):
                status, stdout, stderr = self.run_cli(["completion", shell])
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                self.assertIn(marker, stdout)
                self.assertIn("diagnose", stdout)
                self.assertIn("status", stdout)
                self.assertIn("oracle", stdout)

    def test_completions_include_nested_operations_and_live_options(self) -> None:
        for shell in ("bash", "zsh", "fish", "powershell"):
            with self.subTest(shell=shell):
                status, stdout, stderr = self.run_cli(["completion", shell])
                self.assertEqual(status, 0)
                self.assertEqual(stderr, "")
                self.assertIn("oracle", stdout)
                self.assertIn("sweep", stdout)
                self.assertIn("--toolchain", stdout)


if __name__ == "__main__":
    unittest.main()
