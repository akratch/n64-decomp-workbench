"""Keep the navigable documentation free of broken local links."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class DocumentationTests(unittest.TestCase):
    def test_local_markdown_links_exist(self) -> None:
        failures: list[str] = []
        for document in sorted(ROOT.rglob("*.md")):
            for target in LINK_RE.findall(
                document.read_text(encoding="utf-8")
            ):
                target = target.strip()
                if (
                    not target
                    or target.startswith(("#", "http://", "https://", "mailto:"))
                ):
                    continue
                path_text = unquote(target.split("#", 1)[0])
                resolved = (document.parent / path_text).resolve()
                if not resolved.exists():
                    failures.append(
                        f"{document.relative_to(ROOT)} -> {target}"
                    )
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
