"""Integrity checks for the complete Castlevania 64 scratch examples."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRATCHES = ROOT / "examples" / "cv64" / "scratches"
EXPECTED_EXACT = {
    "func_800010A0_1CA0": False,
    "func_800010C8_1CC8": False,
    "func_800012C0_1EC0": True,
    "func_8013B270_BE460": True,
    "menuButton_selectNextOption": False,
}
REQUIRED_FILES = {
    "README.md",
    "SHA256SUMS",
    "context.c",
    "scratch.json",
    "source.c",
    "target.s",
    "workbench.json",
}


class Cv64ExampleTests(unittest.TestCase):
    def test_complete_scratch_bundles_are_self_consistent(self) -> None:
        bundles = {
            path.name: path
            for path in SCRATCHES.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }
        self.assertEqual(set(bundles), set(EXPECTED_EXACT))

        for name, bundle in bundles.items():
            with self.subTest(bundle=name):
                self.assertEqual(
                    {path.name for path in bundle.iterdir() if path.is_file()},
                    REQUIRED_FILES,
                )

                scratch = json.loads(
                    (bundle / "scratch.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    scratch["schema"], "decomp-workbench-scratch-bundle-v1"
                )
                self.assertEqual(scratch["decomp_me"]["compiler"], "IDO 7.1")
                self.assertEqual(scratch["decomp_me"]["diff_label"], name)

                target = (bundle / "target.s").read_text(encoding="utf-8")
                self.assertEqual(target.count("glabel "), 1)
                self.assertIn(f"glabel {name}", target)

                checksums = {}
                for line in (
                    (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
                ):
                    digest, filename = line.split("  ", maxsplit=1)
                    checksums[filename] = digest
                self.assertEqual(
                    checksums,
                    {
                        filename: metadata["sha256"]
                        for filename, metadata in scratch["files"].items()
                    },
                )
                for filename, expected_digest in checksums.items():
                    actual_digest = hashlib.sha256(
                        (bundle / filename).read_bytes()
                    ).hexdigest()
                    self.assertEqual(actual_digest, expected_digest)

                workbench = json.loads(
                    (bundle / "workbench.json").read_text(encoding="utf-8")
                )
                self.assertEqual(workbench["exact"], EXPECTED_EXACT[name])
