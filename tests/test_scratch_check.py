"""Tests for safe, site-faithful decomp.me export inspection."""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.scratch_check import (
    SITE_SOURCE_MARKER,
    compose_site_source,
    load_scratch,
)

TARGET_DUMP = """\
00000000 <demo>:
   0: 2401000a  li $at,10
   4: 240e002d  li $t6,45
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

CANDIDATE_DUMP = """\
00000000 <demo>:
   0: 240e002d  li $t6,45
   4: 2401000a  li $at,10
   8: 03e00008  jr $ra
   c: 00000000  nop
"""


def write_export(root: Path, *, dumps: bool = True, objects: bool = False) -> None:
    """Write a small synthetic equivalent of a decomp.me download."""

    metadata = {
        "slug": "abc12",
        "name": "demo scratch",
        "platform": "n64",
        "compiler": "ido5.3",
        "compiler_flags": "-O2 -mips2 -g3",
        "diff_label": "demo",
        "score": 20,
        "max_score": 1000,
    }
    (root / "metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    (root / "ctx.c").write_text("typedef int s32;\n", encoding="utf-8")
    (root / "code.c").write_text(
        "s32 demo(void) { return 1; }\n",
        encoding="utf-8",
    )
    if dumps:
        (root / "target.objdump").write_text(TARGET_DUMP, encoding="utf-8")
        (root / "current.objdump").write_text(CANDIDATE_DUMP, encoding="utf-8")
    if objects:
        (root / "target.o").write_bytes(b"target")
        (root / "current.o").write_bytes(b"current")


class ScratchCheckTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_directory_report_separates_site_score_from_aligned_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root)
            status, stdout, stderr = self.run_cli(
                ["check-scratch", str(root), "--json", "--fail-on-mismatch"]
            )

        payload = json.loads(stdout)
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-scratch-check-v1")
        self.assertEqual(payload["external_score"]["percentage"], 98.0)
        self.assertEqual(payload["evidence"], "retained-objdump-text")
        self.assertEqual(payload["comparison"]["verdict"], "schedule-mismatch")
        self.assertEqual(payload["comparison"]["aligned_schedule"], 2)
        self.assertEqual(payload["comparison"]["symbol"], "demo")

    def test_site_source_composition_resets_editable_source_to_line_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root)
            package = load_scratch(root)

            composed = compose_site_source(package, None)

        self.assertEqual(
            composed,
            "typedef int s32;\n"
            + SITE_SOURCE_MARKER
            + "s32 demo(void) { return 1; }\n",
        )
        self.assertEqual(composed.count(SITE_SOURCE_MARKER), 1)

    def test_site_composition_preserves_context_and_source_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root)
            (root / "ctx.c").write_bytes(b"typedef int s32;\n\n")
            (root / "code.c").write_bytes(b"s32 demo(void) {\r\nreturn 1;\r\n}\r\n")
            package = load_scratch(root)

            composed = compose_site_source(package, None)

        self.assertEqual(
            composed.encode("utf-8"),
            b"typedef int s32;\n\n"
            b'#line 1 "src.c"\n'
            b"s32 demo(void) {\r\nreturn 1;\r\n}\r\n",
        )

    def test_compile_mode_uses_composed_source_and_can_retain_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export = root / "export"
            export.mkdir()
            write_export(export, dumps=False, objects=True)
            helper = root / "compiler.py"
            helper.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[2]).write_bytes(b'candidate')\n",
                encoding="utf-8",
            )
            retained = root / "composed.c"
            command = " ".join(
                (
                    shlex.quote(sys.executable),
                    shlex.quote(str(helper)),
                    "{source}",
                    "{output}",
                )
            )
            instructions = parse_disassembly(TARGET_DUMP, symbol="demo")
            comparison = compare_instructions(
                instructions,
                instructions,
                target_name="target.o",
                candidate_name="candidate.o",
                symbol="demo",
            )

            with mock.patch(
                "decomp_workbench.cli.compare_objects",
                return_value=comparison,
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "check-scratch",
                        str(export),
                        "--compile-command",
                        command,
                        "--keep-composed",
                        str(retained),
                    ]
                )
                json_status, json_stdout, json_stderr = self.run_cli(
                    [
                        "check-scratch",
                        str(export),
                        "--compile-command",
                        command,
                        "--env",
                        "MODE=test",
                        "--json",
                    ]
                )

            composed = retained.read_text(encoding="utf-8")
            compile_report = json.loads(json_stdout)["compile"]

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json_status, 0)
        self.assertEqual(json_stderr, "")
        self.assertIn("source composition: site-faithful", stdout)
        self.assertIn(SITE_SOURCE_MARKER.strip(), composed)
        self.assertEqual(compile_report["explicit_environment"], {"MODE": "test"})
        self.assertEqual(len(compile_report["composed_source_sha256"]), 64)
        self.assertIsNotNone(compile_report["compiler"]["sha256"])
        self.assertEqual(compile_report["timeout_seconds"], 120.0)
        self.assertLess(
            composed.index("typedef int s32"), composed.index(SITE_SOURCE_MARKER)
        )
        self.assertLess(composed.index(SITE_SOURCE_MARKER), composed.index("s32 demo"))

    def test_source_override_requires_compile_mode(self) -> None:
        status, _, stderr = self.run_cli(
            ["check-scratch", "unused.zip", "--source", "candidate.c"]
        )
        self.assertEqual(status, 2)
        self.assertIn("--source requires --compile-command", stderr)

    def test_compile_mode_preflights_target_before_starting_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root, dumps=False, objects=False)
            marker = root / "compiler-ran"
            command = " ".join(
                (
                    shlex.quote(sys.executable),
                    "-c",
                    shlex.quote(
                        f"from pathlib import Path; Path({str(marker)!r}).touch()"
                    ),
                    "{source}",
                    "{output}",
                )
            )

            status, _, stderr = self.run_cli(
                ["check-scratch", str(root), "--compile-command", command]
            )
            compiler_ran = marker.exists()

        self.assertEqual(status, 2)
        self.assertIn("needs target.o", stderr)
        self.assertFalse(compiler_ran)

    def test_zip_is_read_without_extracting_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expanded = root / "expanded"
            expanded.mkdir()
            write_export(expanded)
            archive = root / "scratch.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for item in expanded.iterdir():
                    output.write(item, f"one-root/{item.name}")

            package = load_scratch(archive)

        self.assertEqual(package.kind, "decomp.me-export")
        self.assertIn("metadata.json", package.files)

    def test_zip_rejects_path_traversal_even_though_it_never_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "scratch.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../metadata.json", "{}")

            with self.assertRaisesRegex(ValueError, "unsafe scratch member path"):
                load_scratch(archive)

    def test_zip_rejects_members_combined_from_different_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "mixed.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(
                    "metadata/metadata.json",
                    json.dumps({"score": 0, "max_score": 100}),
                )
                output.writestr("source/code.c", "int demo(void) { return 0; }\n")
                output.writestr("context/ctx.c", "")

            with self.assertRaisesRegex(ValueError, "share one flat directory"):
                load_scratch(archive)

    def test_directory_rejects_nested_content_instead_of_ignoring_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root)
            nested = root / "unexpected"
            nested.mkdir()
            (nested / "other-code.c").write_text("int other;\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must be flat"):
                load_scratch(root)

    def test_export_rejects_impossible_browser_scores(self) -> None:
        for score, maximum in ((-1, 100), (101, 100)):
            with self.subTest(score=score, maximum=maximum):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    write_export(root)
                    metadata = json.loads(
                        (root / "metadata.json").read_text(encoding="utf-8")
                    )
                    metadata.update(score=score, max_score=maximum)
                    (root / "metadata.json").write_text(
                        json.dumps(metadata),
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(ValueError, "score"):
                        load_scratch(root)

    def test_bundle_checksum_failure_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.c").write_text("changed\n", encoding="utf-8")
            (root / "scratch.json").write_text(
                json.dumps(
                    {
                        "schema": "decomp-workbench-scratch-bundle-v1",
                        "files": {"source.c": {"sha256": "0" * 64}},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_scratch(root)

    def test_bundle_rejects_a_non_hex_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.c").write_text("candidate\n", encoding="utf-8")
            (root / "scratch.json").write_text(
                json.dumps(
                    {
                        "schema": "decomp-workbench-scratch-bundle-v1",
                        "files": {"source.c": {"sha256": "z" * 64}},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
                load_scratch(root)

    def test_doctor_validates_scratch_and_prints_quoted_next_command(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scratch with space ") as temporary:
            root = Path(temporary)
            write_export(root)
            status, stdout, stderr = self.run_cli(["doctor", str(root)])

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("scratch: VALID (decomp.me-export", stdout)
        self.assertIn("decomp-workbench check-scratch", stdout)
        self.assertIn("'", stdout)

    def test_doctor_can_inspect_the_cache_used_by_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "custom-cache"
            cache.mkdir()
            (cache / "candidate.o").write_bytes(b"candidate")
            status, stdout, stderr = self.run_cli(
                ["doctor", "--cache-dir", str(cache), "--json"]
            )

        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-doctor-v1")
        self.assertEqual(payload["cache"]["files"], 1)
        self.assertEqual(payload["cache"]["bytes"], 9)

    def test_doctor_fails_readiness_when_exported_objects_cannot_be_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_export(root, dumps=False, objects=True)
            status, stdout, stderr = self.run_cli(
                [
                    "doctor",
                    str(root),
                    "--objdump",
                    "/definitely/missing/mips-objdump",
                ]
            )

        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertIn("object workflow: LIMITED", stdout)
        self.assertIn("explicit objdump", stdout)


if __name__ == "__main__":
    unittest.main()
