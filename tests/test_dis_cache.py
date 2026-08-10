"""A cache entry is a claim about an object, and claims are checked here.

The incident: a scoring run was killed by a tool timeout mid-write, leaving a
zero-byte disassembly cache file. The next run's guard was
``if not os.path.exists(dis)``, so the file was kept; it parsed to no rows;
every downstream loop was "for each row present in both sides"; and the object
scored a **perfect match**. Four later stages reported the same defect
independently, and the strengthened guard one of them wrote -- also reject an
empty file -- still accepts a cache truncated at sixty per cent and still
scores it as better than the object is.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

from elf_fixtures import build_elf32be
from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.dis_cache import DisassemblyCache, DisassemblyCacheError
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]
FORMS = (
    "addiu t0,t0,{n}",
    "or t1,t2,t3",
    "lw t4,{m}(sp)",
    "sll t5,t6,{s}",
    "and t7,t8,t9",
    "xor s0,s1,s2",
    "sw t3,{m}(sp)",
    "subu s3,s4,s5",
)


def body(count: int) -> list[str]:
    filler = [
        FORMS[index % len(FORMS)].format(
            n=index % 100, m=(index % 20) * 4, s=index % 31
        )
        for index in range(count)
    ]
    return [*PROLOGUE, *filler, *EPILOGUE]


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class DisassemblyCacheTests(unittest.TestCase):
    """The cache is exercised without a MIPS toolchain.

    The object is a real (synthetic) ELF32 big-endian file, so the SHA-256 and
    the section-word count are read from bytes exactly as they would be from a
    compiler's output; only the disassembler is stood in for.
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.cache_dir = self.root / "cache"

    def _object(
        self, name: str, lines: list[str]
    ) -> tuple[Path, str, list[Instruction]]:
        text = assemble(lines, symbol=SYMBOL)
        instructions = parse_disassembly(text, symbol=SYMBOL)
        section = b"".join(bytes.fromhex(item.word) for item in instructions)
        path = self.root / name
        path.write_bytes(build_elf32be({".text": section}))
        return path, text, instructions

    @contextlib.contextmanager
    def _disassembler(
        self, table: dict[Path, tuple[str, list[Instruction]]]
    ) -> Iterator[list[Path]]:
        calls: list[Path] = []

        def fake(
            path: str | Path,
            *,
            objdump: str | None = None,
            symbol: str | None = None,
            section: str = ".text",
        ) -> tuple[str, list[Instruction]]:
            calls.append(Path(path))
            return table[Path(path)]

        with mock.patch("decomp_workbench.dis_cache.dump_object", fake):
            yield calls

    def test_a_zero_byte_entry_does_not_score_as_a_perfect_match(self) -> None:
        path, text, instructions = self._object("candidate.o", body(24))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({path: (text, instructions)}):
            cache.load(path)
            entry = cache.entry_path(path, symbol=None, section=".text")
            entry.write_bytes(b"")

            _text, reread = cache.load(path)

        # The defect, stated as the test would have caught it: an interrupted
        # write leaves an entry that parses to no rows, and no rows reads as
        # no mismatches.
        self.assertEqual(len(parse_disassembly("")), 0)
        self.assertEqual(len(reread), len(instructions))
        self.assertEqual([event.status for event in cache.rejections], ["rejected"])
        self.assertIn("empty cache entry", cache.rejections[0].reason or "")

    def test_a_truncated_entry_is_rejected_even_though_it_is_not_empty(self) -> None:
        path, text, instructions = self._object("candidate.o", body(24))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({path: (text, instructions)}):
            cache.load(path)
            entry = cache.entry_path(path, symbol=None, section=".text")
            lines = entry.read_text(encoding="utf-8").splitlines()
            entry.write_text("\n".join(lines[: len(lines) // 2]), encoding="utf-8")

            _text, reread = cache.load(path)

        self.assertEqual(len(reread), len(instructions))
        self.assertIn("truncated", cache.rejections[0].reason or "")

    def test_an_entry_written_for_a_different_object_is_rejected(self) -> None:
        path, text, instructions = self._object("candidate.o", body(24))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({path: (text, instructions)}):
            cache.load(path)
        # The object is rebuilt; its entry now describes a file that no longer
        # exists, which is the "scored last night's object" failure.
        rebuilt, new_text, new_instructions = self._object("candidate.o", body(25))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({rebuilt: (new_text, new_instructions)}):
            _text, reread = cache.load(rebuilt)

        self.assertEqual(len(reread), len(new_instructions))
        self.assertIn("the object changed", cache.rejections[0].reason or "")

    def test_a_valid_entry_is_reused_without_disassembling_again(self) -> None:
        path, text, instructions = self._object("candidate.o", body(24))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({path: (text, instructions)}) as calls:
            first = cache.load(path)[1]
            second = cache.load(path)[1]

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [item.assembly for item in first], [item.assembly for item in second]
        )
        self.assertEqual([event.status for event in cache.events], ["miss", "hit"])

    def test_a_disassembly_that_misses_rows_of_the_section_raises(self) -> None:
        """Not a cache problem: the object and its disassembly disagree."""

        path, text, instructions = self._object("candidate.o", body(24))
        cache = DisassemblyCache(self.cache_dir)
        with self._disassembler({path: (text, instructions[:-4])}):
            with self.assertRaises(DisassemblyCacheError) as raised:
                cache.load(path)

        self.assertIn("does not describe the whole object", str(raised.exception))
        self.assertIn("--section", str(raised.exception))


class CachedScoringTests(unittest.TestCase):
    """The same defect, seen from the command a reader actually runs."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def _object(
        self, name: str, lines: list[str]
    ) -> tuple[Path, tuple[str, list[Instruction]]]:
        text = assemble(lines, symbol=SYMBOL)
        instructions = parse_disassembly(text, symbol=SYMBOL)
        section = b"".join(bytes.fromhex(item.word) for item in instructions)
        path = self.root / name
        path.write_bytes(build_elf32be({".text": section}))
        return path, (text, instructions)

    def test_align_reports_the_real_residual_through_a_poisoned_cache(self) -> None:
        lines = body(24)
        broken = list(lines)
        broken[6] = "addiu t0,t0,999"
        broken[9] = "xor s0,s1,s3"
        target, target_dump = self._object("target.o", lines)
        candidate, candidate_dump = self._object("candidate.o", broken)
        cache_dir = self.root / "cache"

        def fake(
            path: str | Path,
            *,
            objdump: str | None = None,
            symbol: str | None = None,
            section: str = ".text",
        ) -> tuple[str, list[Instruction]]:
            return {target: target_dump, candidate: candidate_dump}[Path(path)]

        with mock.patch("decomp_workbench.dis_cache.dump_object", fake):
            status, stdout, stderr = run_cli(
                [
                    "align",
                    str(target),
                    str(candidate),
                    "--disassembly-cache",
                    str(cache_dir),
                    "--json",
                ]
            )
            self.assertEqual(status, 0, stderr)
            self.assertEqual(json.loads(stdout)["paired_mismatches"], 2)

            for entry in cache_dir.glob("*.objdump"):
                entry.write_bytes(b"")

            status, stdout, stderr = run_cli(
                [
                    "align",
                    str(target),
                    str(candidate),
                    "--disassembly-cache",
                    str(cache_dir),
                    "--json",
                ]
            )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        # The existence-only guard reported zero here, and the campaign
        # believed it.
        self.assertEqual(payload["paired_mismatches"], 2)
        self.assertEqual(len(payload["cache_rejections"]), 2)


if __name__ == "__main__":
    unittest.main()
