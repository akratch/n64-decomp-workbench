"""Compiler output stays bounded unless the user explicitly retains artifacts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.artifacts import capture_streams


class ArtifactTests(unittest.TestCase):
    def test_preview_is_bounded_and_full_output_is_opt_in(self) -> None:
        value = "é" * 100
        capture = capture_streams(value, "", limit=17, stem="candidate")
        self.assertTrue(capture.stdout_truncated)
        self.assertEqual(capture.stdout_bytes, 200)
        self.assertIn("omitted", capture.stdout)
        self.assertEqual(capture.artifacts, {})

    def test_explicit_artifact_preserves_complete_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = capture_streams(
                "complete output",
                "complete error",
                limit=4,
                artifact_dir=temporary,
                stem="candidate",
            )
            stdout = Path(capture.artifacts["stdout"])
            stderr = Path(capture.artifacts["stderr"])
            self.assertEqual(stdout.read_text(encoding="utf-8"), "complete output")
            self.assertEqual(stderr.read_text(encoding="utf-8"), "complete error")

    def test_repeated_stems_never_overwrite_a_previous_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = capture_streams(
                "first",
                "",
                artifact_dir=temporary,
                stem="candidate",
            )
            second = capture_streams(
                "second",
                "",
                artifact_dir=temporary,
                stem="candidate",
            )
            first_path = Path(first.artifacts["stdout"])
            second_path = Path(second.artifacts["stdout"])
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_text(encoding="utf-8"), "first")
            self.assertEqual(second_path.read_text(encoding="utf-8"), "second")


if __name__ == "__main__":
    unittest.main()
