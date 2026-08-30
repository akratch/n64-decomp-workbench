"""Campaign artifacts preserve current and best independently and recoverably."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.candidate_lifecycle import archive_candidate
from decomp_workbench.cli import main
from decomp_workbench.dossier import read_dossier


class CandidateLifecycleTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.cache = self.root / "cache"
        self.target = self.root / "target.o"
        self.source = self.root / "candidate.c"
        self.compiler = self.root / "compile.py"
        self.objdump = self.root / "objdump"
        self.target.write_bytes(b"target")
        self.source.write_text("int original;\n", encoding="utf-8")
        self.compiler.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
            encoding="utf-8",
        )
        self.objdump.write_text(
            "#!/usr/bin/env python3\n"
            "print('00000000 <demo>:')\n"
            "print('   0: 03e00008  jr $ra')\n"
            "print('   4: 00000000  nop')\n",
            encoding="utf-8",
        )
        self.objdump.chmod(0o755)
        status, stdout, stderr = self.run_cli(
            [
                "campaign",
                str(self.target),
                str(self.source),
                "--compile-command",
                f"{sys.executable} {self.compiler} {{source}} {{output}}",
                "--objdump",
                str(self.objdump),
                "--symbol",
                "demo",
                "--cache-dir",
                str(self.cache),
                "--state-dir",
                str(self.state),
                "--json-summary",
            ]
        )
        self.assertEqual((status, stderr), (0, ""))
        self.manifest = Path(json.loads(stdout)["manifest"])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_checkpoint_restore_backup_and_acceptance(self) -> None:
        self.source.write_text("int current;\n", encoding="utf-8")
        status, stdout, stderr = self.run_cli(
            [
                "campaign",
                "checkpoint",
                str(self.manifest),
                "--current-source",
                str(self.source),
                "--json",
            ]
        )
        self.assertEqual((status, stderr), (0, ""))
        checkpoint = json.loads(stdout)
        self.assertNotEqual(checkpoint["current"]["id"], checkpoint["best"]["id"])

        self.source.write_text("int drifted;\n", encoding="utf-8")
        status, _stdout, stderr = self.run_cli(
            [
                "campaign",
                "restore-best",
                str(self.manifest),
                "--destination",
                str(self.source),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("changed since the current checkpoint", stderr)

        status, stdout, stderr = self.run_cli(
            [
                "campaign",
                "restore-best",
                str(self.manifest),
                "--destination",
                str(self.source),
                "--allow-drift",
                "--json",
            ]
        )
        self.assertEqual((status, stderr), (0, ""))
        restored = json.loads(stdout)
        self.assertEqual(self.source.read_text(encoding="utf-8"), "int original;\n")
        self.assertTrue(Path(restored["backup"]["path"]).is_file())

        status, stdout, stderr = self.run_cli(
            ["campaign", "accept", str(self.manifest), "--json"]
        )
        self.assertEqual((status, stderr), (0, ""))
        accepted = json.loads(stdout)["accepted"]
        self.assertTrue(accepted["exact"])
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["accepted"]["artifact_id"], accepted["artifact_id"])

    def test_current_may_already_be_the_ranked_best(self) -> None:
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        cache_key = manifest["sources"][0]["cache_key"]
        current_object = Path(manifest["cache_directory"]) / f"{cache_key}.o"
        status, stdout, stderr = self.run_cli(
            [
                "campaign",
                "checkpoint",
                str(self.manifest),
                "--current-source",
                str(self.source),
                "--current-object",
                str(current_object),
                "--json",
            ]
        )
        self.assertEqual((status, stderr), (0, ""))
        checkpoint = json.loads(stdout)
        self.assertTrue(checkpoint["same"])
        self.assertEqual(checkpoint["current"]["id"], checkpoint["best"]["id"])

    def test_archive_identity_does_not_depend_on_origin_name(self) -> None:
        source_alias = self.root / "same-source.txt"
        object_alias = self.root / "same-object.bin"
        source_alias.write_bytes(self.source.read_bytes())
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        cache_key = manifest["sources"][0]["cache_key"]
        current_object = Path(manifest["cache_directory"]) / f"{cache_key}.o"
        object_alias.write_bytes(current_object.read_bytes())
        first = archive_candidate(
            self.manifest.parent,
            source=self.source,
            object_path=current_object,
        )
        second = archive_candidate(
            self.manifest.parent,
            source=source_alias,
            object_path=object_alias,
        )
        self.assertEqual(first, second)

    def test_checkpoint_refuses_an_object_changed_after_measurement(self) -> None:
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        cache_key = manifest["sources"][0]["cache_key"]
        current_object = Path(manifest["cache_directory"]) / f"{cache_key}.o"
        current_object.write_bytes(b"changed after the ledger measurement")
        status, _stdout, stderr = self.run_cli(
            ["campaign", "checkpoint", str(self.manifest)]
        )
        self.assertEqual(status, 2)
        self.assertIn("object hash disagrees with its ledger record", stderr)

    def test_acceptance_revalidates_immutable_archive_metadata(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["campaign", "checkpoint", str(self.manifest), "--json"]
        )
        self.assertEqual((status, stderr), (0, ""))
        checkpoint = json.loads(stdout)
        metadata = (
            self.manifest.parent
            / "artifacts"
            / checkpoint["best"]["id"]
            / "artifact.json"
        )
        record = json.loads(metadata.read_text(encoding="utf-8"))
        record["id"] = "0" * 24
        metadata.write_text(json.dumps(record), encoding="utf-8")
        status, _stdout, stderr = self.run_cli(
            ["campaign", "accept", str(self.manifest)]
        )
        self.assertEqual(status, 2)
        self.assertIn("immutable metadata", stderr)

    def test_dossier_is_append_only_queryable_and_deduplicated(self) -> None:
        arguments = [
            "campaign",
            "dossier-add",
            str(self.manifest),
            "--function",
            "demo",
            "--hypothesis",
            "commuting the operands changes the scheduler basin",
            "--lever",
            "swap the two source operands",
            "--result",
            "falsified",
            "--outcome",
            "the normalized object hash was unchanged",
            "--do-not-repeat",
            "--evidence",
            "campaign row 4",
            "--json",
        ]
        status, stdout, stderr = self.run_cli(arguments)
        self.assertEqual((status, stderr), (0, ""))
        identifier = json.loads(stdout)["entry"]["id"]
        status, duplicate_stdout, stderr = self.run_cli(arguments)
        self.assertEqual(status, 2)
        self.assertEqual(stderr, "")
        self.assertIn(identifier, duplicate_stdout)

        status, stdout, stderr = self.run_cli(
            [
                "campaign",
                "dossier-list",
                str(self.manifest),
                "--function",
                "demo",
                "--result",
                "falsified",
                "--json",
            ]
        )
        self.assertEqual((status, stderr), (0, ""))
        report = json.loads(stdout)
        self.assertEqual((report["entry_count"], report["do_not_repeat"]), (1, 1))

        dossier = self.manifest.parent / "dossier.jsonl"
        entry = json.loads(dossier.read_text(encoding="utf-8"))
        entry["outcome"] = "tampered"
        dossier.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "content does not match id"):
            read_dossier(dossier)

    def test_complete_corrupt_final_dossier_line_is_not_treated_as_torn(self) -> None:
        dossier = self.manifest.parent / "dossier.jsonl"
        dossier.write_text('{"schema":\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed dossier line"):
            read_dossier(dossier)


if __name__ == "__main__":
    unittest.main()
