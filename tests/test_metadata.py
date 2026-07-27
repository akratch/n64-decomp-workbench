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
        tagged_versions = set(
            re.findall(
                r"/blob/decomp-workbench-v(\d+\.\d+\.\d+)/",
                metadata + (ROOT / "README.md").read_text(encoding="utf-8"),
            )
        )
        self.assertEqual(tagged_versions, {__version__})


if __name__ == "__main__":
    unittest.main()
