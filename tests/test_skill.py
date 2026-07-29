"""Tests for the portable Agent Skills bundle."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "n64-decomp-campaign" / "SKILL.md"


class AgentSkillTests(unittest.TestCase):
    def test_portable_skill_has_only_standard_core_frontmatter(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        match = re.match(r"---\n(?P<frontmatter>.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match)
        if match is None:
            return
        fields = dict(
            line.split(": ", 1)
            for line in match.group("frontmatter").splitlines()
            if line
        )
        self.assertEqual(set(fields), {"name", "description"})
        self.assertEqual(fields["name"], "n64-decomp-campaign")
        self.assertTrue(fields["description"])

    def test_skill_references_are_present(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        references = re.findall(r"\(references/([^)]+)\)", text)
        self.assertEqual(
            references,
            [
                "evidence-ladder.md",
                "ido-late-stage-patterns.md",
                "campaign-hygiene.md",
            ],
        )
        for reference in references:
            self.assertTrue((SKILL.parent / "references" / reference).is_file())


if __name__ == "__main__":
    unittest.main()
