"""Tests for the portable Agent Skills bundle."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.agent_skill import (
    bundled_skill_path,
    install_agent_skill,
)

ROOT = Path(__file__).resolve().parents[1]
SKILL = (
    ROOT / "src" / "decomp_workbench" / "skills" / "n64-decomp-campaign" / "SKILL.md"
)


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

    def test_bundled_skill_path_is_the_validated_source(self) -> None:
        self.assertEqual(bundled_skill_path(), SKILL.parent)

    def test_the_repository_has_no_second_skill_tree(self) -> None:
        """The packaged bundle is the only copy.

        A root-level `skills/n64-decomp-campaign/` once held empty `agents/`
        and `references/` directories, which made the skill look hollow to
        anyone browsing the repository while `install-skill` shipped a
        populated bundle from `src/`. Either the root tree matches what is
        installed, or it does not exist.
        """

        root_skills = ROOT / "skills"
        if not root_skills.exists():
            return
        packaged = bundled_skill_path()
        checked_in = {
            item.relative_to(root_skills).as_posix()
            for item in root_skills.rglob("*")
            if item.is_file()
        }
        shipped = {
            f"{packaged.name}/{item.relative_to(packaged).as_posix()}"
            for item in packaged.rglob("*")
            if item.is_file()
        }
        self.assertEqual(
            checked_in,
            shipped,
            f"{root_skills} does not match the packaged skill; check the "
            "content in or remove the directory",
        )
        for name in sorted(checked_in):
            with self.subTest(path=name):
                self.assertEqual(
                    (root_skills / name).read_bytes(),
                    (packaged.parent / name).read_bytes(),
                )

    def test_installer_is_idempotent_and_refuses_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "skills"
            installed, status = install_agent_skill("claude", destination=destination)
            self.assertEqual(status, "installed")
            self.assertTrue((installed / "SKILL.md").is_file())

            current, status = install_agent_skill("claude", destination=destination)
            self.assertEqual((current, status), (installed, "current"))

            (installed / "SKILL.md").write_text("different\n", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "already exists and differs"):
                install_agent_skill("claude", destination=destination)

    def test_installer_rejects_unknown_client_with_custom_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "unsupported client"):
                install_agent_skill("other", destination=temp)

    def test_installer_rejects_file_as_skills_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "not-a-directory"
            destination.write_text("file\n", encoding="utf-8")
            with self.assertRaisesRegex(NotADirectoryError, "not a directory"):
                install_agent_skill("codex", destination=destination)


if __name__ == "__main__":
    unittest.main()
