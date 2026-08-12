"""Portable contracts exercised by the dedicated Windows CI runner."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from decomp_workbench.artifacts import capture_streams
from decomp_workbench.cache import cache_status, prune_cache
from decomp_workbench.campaign import CompilerTimeoutError, run_compiler
from decomp_workbench.cli import main
from decomp_workbench.notes import add_note, merge_notes


class WindowsCompatibilityTests(unittest.TestCase):
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
