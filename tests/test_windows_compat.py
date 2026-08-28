"""Portable contracts exercised by the dedicated Windows CI runner."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.artifacts import capture_streams
from decomp_workbench.cache import cache_status, prune_cache
from decomp_workbench.campaign import (
    CompilerTimeoutError,
    render_compile_command,
    run_compiler,
)
from decomp_workbench.cli import main
from decomp_workbench.command_line import split_command
from decomp_workbench.notes import add_note, merge_notes
from decomp_workbench.permute import load_gate_note, permuter_argv, wait_for_headroom


class WindowsCompatibilityTests(unittest.TestCase):
    def test_windows_command_parser_preserves_native_paths(self) -> None:
        command = split_command(
            r'"C:\Program Files\IDO\cc.exe" C:\work\compile.py {source} {output}',
            windows=True,
        )
        self.assertEqual(
            command,
            [
                r"C:\Program Files\IDO\cc.exe",
                r"C:\work\compile.py",
                "{source}",
                "{output}",
            ],
        )

    def test_windows_command_parser_accepts_single_quoted_arguments(self) -> None:
        self.assertEqual(
            split_command("cc '--flag=a b' {source} {output}", windows=True),
            ["cc", "--flag=a b", "{source}", "{output}"],
        )

    def test_windows_parser_round_trips_native_quoted_arguments(self) -> None:
        arguments = [
            "C:\\Program Files\\IDO\\",
            'argument with "quotes"',
            "",
            "plain",
        ]
        rendered = subprocess.list2cmdline(arguments)
        self.assertEqual(split_command(rendered, windows=True), arguments)

    def test_compile_template_keeps_native_source_and_output_paths(self) -> None:
        source = Path(r"C:\work tree\candidate.c")
        output = Path(r"C:\work tree\candidate.o")
        with mock.patch("decomp_workbench.command_line.os.name", "nt"):
            command = render_compile_command(
                r"C:\IDO\cc.exe --input {source} --output {output}", source, output
            )
        self.assertEqual(command[0], r"C:\IDO\cc.exe")
        self.assertEqual(command[-3:], [str(source), "--output", str(output)])

    def test_command_parser_rejects_an_unclosed_quote(self) -> None:
        with self.assertRaisesRegex(ValueError, "closing quotation"):
            split_command('cc "unfinished', windows=True)

    def test_the_complete_cli_imports_and_renders_help(self) -> None:
        self.assertEqual(main([]), 0)

    def test_note_merge_uses_a_native_portable_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "NOTES.md"
            log.write_text("# Notes\n", encoding="utf-8")
            add_note(log, identifier="WB-1", title="portable")
            merged = merge_notes(log)
            self.assertEqual([item.identifier for item in merged], ["WB-1"])
            self.assertIn("WB-1", log.read_text(encoding="utf-8"))

    def test_compiler_timeout_ends_the_direct_wrapper(self) -> None:
        started = time.monotonic()
        with self.assertRaises(CompilerTimeoutError):
            run_compiler(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                environment={},
                compile_cwd=Path.cwd(),
                timeout=0.2,
            )
        self.assertLess(time.monotonic() - started, 10)

    def test_unicode_stream_bounding_is_platform_neutral(self) -> None:
        capture = capture_streams("é" * 100, "", limit=15, stem="portable")
        self.assertTrue(capture.stdout_truncated)
        self.assertEqual(capture.stdout_bytes, 200)

    def test_compiler_output_with_invalid_utf8_remains_reportable(self) -> None:
        completed = run_compiler(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes([255]))",
            ],
            environment={},
            compile_cwd=Path.cwd(),
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "\N{REPLACEMENT CHARACTER}")

    def test_the_permuter_is_not_prefixed_with_a_program_windows_lacks(
        self,
    ) -> None:
        """`nice` is POSIX. Prefixing it elsewhere fails every function."""

        argv = permuter_argv(
            python="python",
            permuter=Path(r"C:\permuter\permuter.py"),
            scratch=Path(r"C:\work\scratch"),
            threads=2,
            posix=False,
        )
        self.assertEqual(argv[0], "python")
        self.assertNotIn("nice", argv)
        self.assertIn("--stack-diffs", argv)

    def test_a_load_gate_without_a_load_average_says_it_is_not_gating(
        self,
    ) -> None:
        """Windows has no `getloadavg`, and silence would read as headroom."""

        self.assertEqual(wait_for_headroom(9.0, load=lambda: None), 0)
        note = load_gate_note(9.0, load=lambda: None)
        assert note is not None
        self.assertIn("no load average", note)

    def test_cache_dry_run_handles_native_paths_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            cache.mkdir()
            entry = cache / "entry.o"
            entry.write_bytes(b"object")
            old = time.time() - 100
            os.utime(entry, (old, old))
            report = prune_cache(
                cache,
                older_than=10,
                apply=False,
                trash_root=Path(temporary) / "trash",
            )
            self.assertEqual(report["selected_files"], 1)
            self.assertTrue(entry.is_file())
            self.assertEqual(cache_status(cache)["files"], 1)


if __name__ == "__main__":
    unittest.main()
