"""Tests for reproducible campaign preparation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict

from decomp_workbench.campaign import (
    candidate_key,
    executable_identity,
    group_object_basins,
    prepare_candidates,
    render_compile_command,
    run_campaign,
)
from decomp_workbench.cli import parse_environment


class CampaignArguments(TypedDict):
    target: Path
    template: str
    cache_dir: Path
    ledger: Path
    objdump: str
    symbol: str
    section: str


class CampaignTests(unittest.TestCase):
    def test_compiler_identity_resolves_relative_executable(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            executable = Path(temp) / "compiler"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            relative = executable.relative_to(Path.cwd())
            identity = executable_identity([str(relative)])
            self.assertEqual(identity["resolved"], str(executable.resolve()))
            self.assertIsNotNone(identity["sha256"])

    def test_render_command_does_not_use_a_shell(self) -> None:
        command = render_compile_command(
            "./compile.sh --input {source} --output {output}",
            Path("/tmp/a source.c"),
            Path("/tmp/a.o"),
        )
        self.assertEqual(
            command,
            [
                "./compile.sh",
                "--input",
                "/tmp/a source.c",
                "--output",
                "/tmp/a.o",
            ],
        )

    def test_render_command_requires_both_placeholders(self) -> None:
        with self.assertRaisesRegex(ValueError, r"\{output\}"):
            render_compile_command("cc {source}", Path("a.c"), Path("a.o"))

    def test_candidate_key_tracks_source_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "candidate.c"
            target = root / "target.o"
            compiler = root / "compiler"
            source.write_text("int value = 1;\n", encoding="utf-8")
            target.write_bytes(b"target")
            compiler.write_text("#!/bin/sh\n", encoding="utf-8")
            command = [str(compiler), str(source), "{cache_object}"]
            first = candidate_key(
                source,
                command=command,
                target=target,
                symbol="demo",
                environment={"MODE": "one"},
            )
            second = candidate_key(
                source,
                command=command,
                target=target,
                symbol="demo",
                environment={"MODE": "two"},
            )
            self.assertNotEqual(first, second)
            source.write_text("int value = 2;\n", encoding="utf-8")
            third = candidate_key(
                source,
                command=command,
                target=target,
                symbol="demo",
                environment={"MODE": "one"},
            )
            self.assertNotEqual(first, third)

    def test_candidate_keys_are_path_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            first = root / "first.c"
            second = root / "second.c"
            first.write_text("int same;\n", encoding="utf-8")
            second.write_text("int same;\n", encoding="utf-8")
            candidates, duplicates = prepare_candidates(
                [first, second],
                template="cc {source} -o {output}",
                target=target,
                symbol=None,
                environment={},
            )
            # Paths are intentionally part of the rendered command. This
            # avoids assuming that wrappers are source-path independent.
            self.assertEqual(len(candidates), 2)
            self.assertEqual(len(duplicates), 2)

    def test_candidate_key_tracks_compiler_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "candidate.c"
            target = root / "target.o"
            source.write_text("int candidate;\n", encoding="utf-8")
            target.write_bytes(b"target")
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            self.assertNotEqual(
                candidate_key(
                    source,
                    command=["./compile", str(source), "{cache_object}"],
                    target=target,
                    symbol=None,
                    environment={},
                    compile_cwd=first,
                ),
                candidate_key(
                    source,
                    command=["./compile", str(source), "{cache_object}"],
                    target=target,
                    symbol=None,
                    environment={},
                    compile_cwd=second,
                ),
            )

    def test_campaign_caches_and_records_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            source = root / "candidate.c"
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes("
                "pathlib.Path(sys.argv[1]).read_bytes())\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            cache = root / "cache"
            ledger = root / "ledger.jsonl"
            arguments: CampaignArguments = {
                "target": target,
                "template": (f"{sys.executable} {compiler} {{source}} {{output}}"),
                "cache_dir": cache,
                "ledger": ledger,
                "objdump": str(objdump),
                "symbol": "demo",
                "section": ".text",
            }
            first, _ = run_campaign([source], **arguments)
            second, _ = run_campaign([source], **arguments)
            comparison = first[0].comparison
            if comparison is None:
                raise AssertionError("campaign did not compare the compiled object")
            self.assertTrue(comparison.exact)
            self.assertFalse(first[0].cached)
            self.assertTrue(second[0].cached)
            records = [
                json.loads(line)
                for line in ledger.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[0]["provenance"]["source_sha256"],
                records[1]["provenance"]["source_sha256"],
            )
            self.assertEqual(records[0]["provenance"]["section"], ".text")
            self.assertEqual(
                records[0]["provenance"]["objdump"]["resolved"],
                str(objdump.resolve()),
            )
            self.assertEqual(
                records[0]["provenance"]["compile_cwd"],
                str(Path.cwd().resolve()),
            )

    def test_campaign_uses_explicit_compiler_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            (project / "required.txt").write_text("present", encoding="utf-8")
            source = root / "candidate.c"
            target = root / "target.o"
            source.write_text("int candidate;\n", encoding="utf-8")
            target.write_bytes(b"target")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "assert pathlib.Path('required.txt').is_file()\n"
                "pathlib.Path(sys.argv[2]).write_bytes("
                "pathlib.Path(sys.argv[1]).read_bytes())\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            results, _ = run_campaign(
                [source],
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                cache_dir=root / "cache",
                objdump=str(objdump),
                symbol="demo",
                compile_cwd=project,
            )
            self.assertIsNotNone(results[0].comparison)

    def test_groups_distinct_sources_that_compile_to_one_object_basin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            first = root / "first.c"
            second = root / "second.c"
            first.write_text("int first;\n", encoding="utf-8")
            second.write_text("int second;\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'constant object')\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            results, _ = run_campaign(
                [first, second],
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                cache_dir=root / "cache",
                objdump=str(objdump),
                symbol="demo",
            )
            basins = group_object_basins(results)
            self.assertEqual(len(basins), 1)
            self.assertEqual(
                [item.source for item in basins[0]],
                [str(first.resolve()), str(second.resolve())],
            )
            first_comparison = results[0].comparison
            second_comparison = results[1].comparison
            if first_comparison is None or second_comparison is None:
                raise AssertionError("campaign results were not compared")
            first_comparison.word_mismatches = 5
            second_comparison.word_mismatches = 0
            basins = group_object_basins(results)
            self.assertIs(basins[0][0], results[1])

    def test_parse_environment(self) -> None:
        self.assertEqual(
            parse_environment(["TRACE=1", "MODE=verbose"]),
            {"TRACE": "1", "MODE": "verbose"},
        )
        with self.assertRaises(ValueError):
            parse_environment(["NOT-VALID=1"])


if __name__ == "__main__":
    unittest.main()
