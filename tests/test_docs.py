"""Keep the navigable documentation free of broken local links."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
REFERENCE_RE = re.compile(r"^\[([^\]]+)\]:\s+\S+", re.MULTILINE)
REFERENCE_USE_RE = re.compile(r"\[[^\]]+\]\[([^\]]+)\]")


def heading_anchors(document: Path) -> set[str]:
    """Return the simple GitHub-style anchors used by this documentation."""

    anchors: set[str] = set()
    for heading in re.findall(
        r"^#{1,6}\s+(.+?)\s*#*\s*$",
        document.read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        anchors.add(slug)
    return anchors


class DocumentationTests(unittest.TestCase):
    def test_local_markdown_links_exist(self) -> None:
        failures: list[str] = []
        for document in sorted(ROOT.rglob("*.md")):
            for target in LINK_RE.findall(document.read_text(encoding="utf-8")):
                target = target.strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                path_text, _, fragment = target.partition("#")
                resolved = (
                    document
                    if not path_text
                    else (document.parent / unquote(path_text)).resolve()
                )
                if not resolved.exists():
                    failures.append(f"{document.relative_to(ROOT)} -> {target}")
                elif fragment and resolved.suffix == ".md":
                    anchor = unquote(fragment)
                    if anchor not in heading_anchors(resolved):
                        failures.append(
                            f"{document.relative_to(ROOT)} -> missing anchor {target}"
                        )
        self.assertEqual(failures, [], "\n".join(failures))

    def test_readme_reference_links_are_defined(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        definitions = set(REFERENCE_RE.findall(readme))
        uses = set(REFERENCE_USE_RE.findall(readme))
        self.assertEqual(uses - definitions, set())


if __name__ == "__main__":
    unittest.main()
