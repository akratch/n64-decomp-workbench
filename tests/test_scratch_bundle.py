"""Tests for local, upload-neutral decomp.me scratch bundles."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.scratch_bundle import bundle_scratch


class ScratchBundleTests(unittest.TestCase):
    def test_copies_inputs_and_records_reproducible_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "input.s"
            context = root / "input.ctx.c"
            source = root / "input.c"
            target.write_text("glabel demo\njr $ra\n nop\n", encoding="utf-8")
            context.write_text("typedef int s32;\n", encoding="utf-8")
            source.write_text("s32 demo(void) { return 0; }\n", encoding="utf-8")

            result = bundle_scratch(
                root / "bundle",
                target_assembly=target,
                context=context,
                source=source,
                platform="n64",
                compiler="IDO 7.1",
                compiler_flags="-O2 -mips2",
                diff_label="demo",
                project="example",
                compiler_id="ido7.1_c++",
                language="C++",
                provenance={
                    "schema": "decomp-workbench-campaign-promotion-v1",
                    "source_cache_key": "abc123",
                },
            )

            output = Path(result.output)
            self.assertEqual((output / "target.s").read_bytes(), target.read_bytes())
            self.assertEqual((output / "context.c").read_bytes(), context.read_bytes())
            self.assertEqual((output / "source.c").read_bytes(), source.read_bytes())
            manifest = json.loads((output / "scratch.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "decomp-workbench-scratch-bundle-v1")
            self.assertEqual(manifest["decomp_me"]["diff_label"], "demo")
            self.assertEqual(manifest["project"], "example")
            self.assertEqual(manifest["decomp_me"]["compiler_id"], "ido7.1_c++")
            self.assertEqual(manifest["decomp_me"]["language"], "C++")
            self.assertEqual(manifest["provenance"]["source_cache_key"], "abc123")
            self.assertEqual(len(manifest["files"]["target.s"]["sha256"]), 64)
            self.assertNotIn(str(root), (output / "scratch.json").read_text())
            self.assertIn(
                "https://www.decomp.me/new",
                (output / "README.md").read_text(),
            )
            readme = (output / "README.md").read_text()
            self.assertIn("Preset** to **Custom", readme)
            self.assertIn("canonical compiler id `ido7.1_c++`", readme)
            self.assertIn("decomp-workbench check-scratch .", readme)
            self.assertNotIn("shasum", readme)

    def test_refuses_a_nonempty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input"
            input_path.write_text("content", encoding="utf-8")
            output = root / "bundle"
            output.mkdir()
            (output / "keep").write_text("mine", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not empty"):
                bundle_scratch(
                    output,
                    target_assembly=input_path,
                    context=input_path,
                    source=input_path,
                    platform="n64",
                    compiler="IDO 7.1",
                    compiler_flags="-O2",
                    diff_label="demo",
                )

    def test_refuses_empty_required_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input"
            input_path.write_text("content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "diff_label"):
                bundle_scratch(
                    root / "bundle",
                    target_assembly=input_path,
                    context=input_path,
                    source=input_path,
                    platform="n64",
                    compiler="IDO 7.1",
                    compiler_flags="",
                    diff_label="",
                )
