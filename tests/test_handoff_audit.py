"""Public handoffs must not depend on files that only exist locally."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.handoff_audit import audit_handoff


def git_init(root: Path, *tracked: str) -> None:
    subprocess.run(
        ["git", "init", "-q", str(root)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if tracked:
        subprocess.run(
            ["git", "-C", str(root), "add", "--", *tracked],
            check=True,
            stdout=subprocess.DEVNULL,
        )


class HandoffAuditTests(unittest.TestCase):
    def test_a_tracked_relative_reference_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools").mkdir()
            (root / "README.md").write_text(
                "Run [`verify.py`](tools/verify.py).\n", encoding="utf-8"
            )
            (root / "tools" / "verify.py").write_text("print('ok')\n", encoding="utf-8")
            git_init(root, "README.md", "tools/verify.py")

            report = audit_handoff(root)

        self.assertTrue(report["ready"])
        self.assertEqual(report["findings"], [])

    def test_an_inline_doc_dependency_missing_from_publication_is_an_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            handoff = base / "handoff"
            project = base / "project"
            handoff.mkdir()
            project.mkdir()
            (handoff / "README.md").write_text(
                "See the project's `tools/ido71-threshold4/README.md`.\n",
                encoding="utf-8",
            )
            dependency = project / "tools" / "ido71-threshold4" / "README.md"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("local only\n", encoding="utf-8")
            git_init(handoff, "README.md")
            git_init(project)

            report = audit_handoff(handoff, dependency_roots=[project])

        self.assertFalse(report["ready"])
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["findings"][0]["code"], "untracked-dependency")
        self.assertEqual(report["findings"][0]["line"], 1)

    def test_a_local_file_that_will_not_be_published_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("proof\n", encoding="utf-8")
            (root / "proof.txt").write_text("forgotten\n", encoding="utf-8")
            git_init(root, "README.md")

            report = audit_handoff(root)

        codes = {item["code"] for item in report["findings"]}
        self.assertIn("untracked-file", codes)

    def test_cli_json_returns_one_for_a_nonportable_absolute_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text(
                "Built from `/Users/example/private/compiler`.\n", encoding="utf-8"
            )
            git_init(root, "README.md")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["handoff", "audit", str(root), "--json"])

        report = json.loads(stdout.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(report["schema"], "decomp-workbench-handoff-audit-v1")
        self.assertEqual(report["findings"][0]["code"], "absolute-user-path")


if __name__ == "__main__":
    unittest.main()
