"""Public handoffs must not depend on files that only exist locally."""

from __future__ import annotations

import contextlib
import io
import json
import os
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


class HandoffRootResolutionTests(unittest.TestCase):
    """A relative argument must name the same tree an absolute one names.

    A campaign read `handoff root is not a directory: .../bundle/bundle` as the
    command appending the argument's basename to itself. It does not: the two
    spellings resolve to one canonical root, and the doubled path was a working
    directory that had already moved into `bundle`. Both halves are locked
    here -- the resolution, and the sentence that tells those two cases apart.
    """

    def setUp(self) -> None:
        self.previous = Path.cwd()
        self.addCleanup(os.chdir, self.previous)

    def audit(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["audit-handoff", *arguments, "--json"])
        return status, json.loads(stdout.getvalue())

    def test_a_relative_path_from_the_parent_names_the_same_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            bundle = parent / "bundle"
            bundle.mkdir()
            (bundle / "README.md").write_text("proof\n", encoding="utf-8")
            git_init(bundle, "README.md")

            absolute_status, absolute = self.audit(str(bundle))
            for working, spelling in (
                (parent, "bundle"),
                (parent, "bundle/"),
                (parent, "./bundle"),
                (bundle, "."),
                (bundle, "../bundle"),
            ):
                with self.subTest(cwd=working.name, spelling=spelling):
                    os.chdir(working)
                    status, report = self.audit(spelling)
                    self.assertEqual(status, absolute_status)
                    self.assertEqual(report["root"], absolute["root"])
                    self.assertEqual(report["findings"], absolute["findings"])

    def test_a_missing_relative_root_names_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            os.chdir(parent)
            with self.assertRaises(NotADirectoryError) as raised:
                audit_handoff("bundle/")

        message = str(raised.exception)
        self.assertIn("handoff root is not a directory", message)
        self.assertIn("'bundle/'", message)
        self.assertIn(str(parent), message)
        self.assertNotIn("bundle/bundle", message)

    def test_a_missing_absolute_root_does_not_quote_a_working_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary).resolve() / "bundle"
            with self.assertRaises(NotADirectoryError) as raised:
                audit_handoff(missing)

        self.assertIn(str(missing), str(raised.exception))
        self.assertNotIn("relative to", str(raised.exception))

    def test_a_relative_dependency_root_resolves_the_same_way(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            bundle = parent / "bundle"
            project = parent / "project"
            bundle.mkdir()
            project.mkdir()
            (bundle / "README.md").write_text("proof\n", encoding="utf-8")
            git_init(bundle, "README.md")
            git_init(project)
            os.chdir(parent)

            report = audit_handoff("bundle/", dependency_roots=["project/"])

        self.assertEqual(report["root"], str(bundle))
        self.assertTrue(report["ready"])


if __name__ == "__main__":
    unittest.main()
