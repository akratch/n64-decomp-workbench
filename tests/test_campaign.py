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


class StopOnExactArguments(TypedDict):
    target: Path
    template: str
    cache_dir: Path
    objdump: str
    symbol: str
    jobs: int
    ledger: Path


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
            self.assertEqual(records[0]["execution"]["timeout_seconds"], 120.0)

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
                stop_on_exact=False,
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

    def write_counting_objdump(self, root: Path, counter: Path) -> Path:
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib\n"
            f"pathlib.Path({str(counter)!r}).open('a').write('run\\n')\n"
            "print('00000000 <demo>:')\n"
            "print('   0: 03e00008  jr $ra')\n"
            "print('   4: 00000000  nop')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        return objdump

    def write_copying_compiler(self, root: Path) -> Path:
        compiler = root / "compile.py"
        compiler.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[2]).write_bytes("
            "pathlib.Path(sys.argv[1]).read_bytes())\n",
            encoding="utf-8",
        )
        return compiler

    def test_target_is_disassembled_once_for_the_whole_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            counter = root / "objdump-runs.txt"
            objdump = self.write_counting_objdump(root, counter)
            compiler = self.write_copying_compiler(root)
            sources = []
            for index in range(3):
                source = root / f"candidate{index}.c"
                source.write_text(f"int candidate = {index};\n", encoding="utf-8")
                sources.append(source)
            results, _ = run_campaign(
                sources,
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                cache_dir=root / "cache",
                objdump=str(objdump),
                symbol="demo",
                stop_on_exact=False,
            )
            self.assertEqual(len(results), 3)
            runs = counter.read_text(encoding="utf-8").splitlines()
            # One target disassembly plus one per candidate; the comparison
            # itself never leaves the process.
            self.assertEqual(len(runs), 4)

    def test_stop_on_exact_leaves_later_candidates_uncompiled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            objdump = self.write_counting_objdump(root, root / "runs.txt")
            compiler = self.write_copying_compiler(root)
            sources = []
            for index in range(3):
                source = root / f"candidate{index}.c"
                source.write_text(f"int candidate = {index};\n", encoding="utf-8")
                sources.append(source)
            ledger = root / "ledger.jsonl"
            arguments: StopOnExactArguments = {
                "target": target,
                "template": f"{sys.executable} {compiler} {{source}} {{output}}",
                "cache_dir": root / "cache",
                "objdump": str(objdump),
                "symbol": "demo",
                "jobs": 1,
                "ledger": ledger,
            }
            stopped, _ = run_campaign(sources, stop_on_exact=True, **arguments)
            self.assertEqual(len(stopped), 1)
            first = stopped[0].comparison
            if first is None:
                raise AssertionError("campaign did not compare the compiled object")
            self.assertTrue(first.exact)
            self.assertEqual(
                len(ledger.read_text(encoding="utf-8").splitlines()),
                1,
            )

            swept, _ = run_campaign(sources, stop_on_exact=False, **arguments)
            self.assertEqual(len(swept), 3)
            self.assertEqual(
                len(ledger.read_text(encoding="utf-8").splitlines()),
                4,
            )

    def test_stopping_early_keeps_every_candidate_that_actually_ran(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            objdump = self.write_counting_objdump(root, root / "runs.txt")
            compiler = root / "compile.py"
            # A compiler slow enough that every job is in flight when the
            # first one finishes exact.
            compiler.write_text(
                "import pathlib, sys, time\n"
                "time.sleep(0.3)\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
                encoding="utf-8",
            )
            sources = []
            for index in range(6):
                source = root / f"candidate{index}.c"
                source.write_text(f"int value = {index};\n", encoding="utf-8")
                sources.append(source)
            ledger = root / "ledger.jsonl"
            results, _ = run_campaign(
                sources,
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                cache_dir=root / "cache",
                objdump=str(objdump),
                symbol="demo",
                jobs=6,
                ledger=ledger,
                stop_on_exact=True,
            )
            # Every candidate the pool started is compiled, compared, and
            # recorded; dropping in-flight work would make the ledger lie and
            # would throw away objects the campaign already paid for.
            self.assertEqual(len(results), 6)
            self.assertEqual(
                len(ledger.read_text(encoding="utf-8").splitlines()),
                6,
            )
            self.assertTrue(all(item.comparison is not None for item in results))

    def test_one_broken_candidate_does_not_end_the_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            compiler = self.write_copying_compiler(root)
            # Objdump output that is not valid UTF-8 raises through the
            # comparison, which is neither OSError nor RuntimeError.
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "objects = [item for item in sys.argv[1:] "
                "if item.endswith('.o')]\n"
                "data = pathlib.Path(objects[-1]).read_bytes()\n"
                "if b'poison' in data:\n"
                "    sys.stdout.buffer.write(b'0: 03e00008 \\xff\\xfe\\n')\n"
                "    raise SystemExit(0)\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            good = root / "good.c"
            good.write_text("int good;\n", encoding="utf-8")
            poisoned = root / "poison.c"
            poisoned.write_text("int poison;\n", encoding="utf-8")
            other = root / "other.c"
            other.write_text("int other;\n", encoding="utf-8")
            ledger = root / "ledger.jsonl"
            results, _ = run_campaign(
                [good, poisoned, other],
                target=target,
                template=f"{sys.executable} {compiler} {{source}} {{output}}",
                cache_dir=root / "cache",
                objdump=str(objdump),
                symbol="demo",
                jobs=1,
                ledger=ledger,
                stop_on_exact=False,
            )
            self.assertEqual(len(results), 3)
            self.assertEqual(
                len(ledger.read_text(encoding="utf-8").splitlines()),
                3,
            )
            failed = [item for item in results if item.comparison is None]
            self.assertEqual(len(failed), 1)
            self.assertIn("poison", failed[0].source)
            self.assertNotEqual(failed[0].returncode, 0)
            self.assertTrue(failed[0].stderr)

    def test_parse_environment(self) -> None:
        self.assertEqual(
            parse_environment(["TRACE=1", "MODE=verbose"]),
            {"TRACE": "1", "MODE": "verbose"},
        )
        with self.assertRaises(ValueError):
            parse_environment(["NOT-VALID=1"])


if __name__ == "__main__":
    unittest.main()
