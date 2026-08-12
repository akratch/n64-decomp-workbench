"""Keep public package metadata synchronized with the runtime package."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from decomp_workbench import __version__

ROOT = Path(__file__).resolve().parents[1]


class MetadataTests(unittest.TestCase):
    def test_runtime_and_project_versions_match(self) -> None:
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"$', metadata, re.MULTILINE)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(__version__, match.group(1))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/akratch/n64-decomp-workbench",
            metadata,
        )
        self.assertIn("/blob/main/docs/README.md", metadata)
        self.assertNotIn("tools/decomp-workbench", metadata)
        self.assertNotIn("Diddy Kong", readme)
        self.assertNotIn("case-studies", readme)

    def test_source_distribution_includes_linked_case_studies(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("recursive-include case-studies *.md", manifest)
        for path in (ROOT / "case-studies").glob("*.md"):
            self.assertTrue(path.is_file())

    def test_release_tree_excludes_uncleared_cv64_payloads(self) -> None:
        scratches = ROOT / "examples" / "cv64" / "scratches"
        files = [path for path in scratches.rglob("*") if path.is_file()]
        self.assertEqual(files, [])
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertNotIn("cv64/scratches", manifest)


if __name__ == "__main__":
    unittest.main()
