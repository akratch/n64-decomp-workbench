"""Synthetic local PC16 evidence: diagnostic alignment, never exactness credit."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from elf_fixtures import RelocSpec, SymbolSpec, build_relocatable, words

from decomp_workbench.compare import compare_instructions
from decomp_workbench.elf import read_elf
from decomp_workbench.elf_symbols import SymbolExtent
from decomp_workbench.local_pc16 import annotate_local_pc16
from decomp_workbench.model import Instruction, Relocation
from decomp_workbench.objdump import dump_object
from decomp_workbench.view import build_view, normalized_text


class LocalPC16Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "sample.o"
        self.extent = SymbolExtent("demo", ".text", 0, 16, "size")

    def fixture(
        self,
        *,
        word: int = 0x1000FFFF,
        symbol_value: int = 12,
        symbol_section: str | None = ".text",
        offset: int = 0,
        duplicate: bool = False,
    ) -> list[Instruction]:
        code = [0, 0, 0, 0]
        code[offset // 4] = word
        relocations = [RelocSpec(".text", offset, ".Linside", 10)]
        if duplicate:
            relocations *= 2
        self.path.write_bytes(
            build_relocatable(
                {".text": words(*code), ".data": words(0)},
                [
                    SymbolSpec("demo", size=16, kind=2, section=".text"),
                    SymbolSpec(".Linside", value=symbol_value, section=symbol_section),
                ],
                relocations,
            )
        )
        return [
            Instruction(
                position * 4,
                f"{value:08x}",
                "b 0 <demo>" if position * 4 == offset else "nop",
                (Relocation(offset, "R_MIPS_PC16", ".Linside"),)
                if position * 4 == offset
                else (),
            )
            for position, value in enumerate(code)
        ]

    def test_signed_rel_addends_and_backward_branch(self) -> None:
        for immediate, symbol, offset, expected in [
            (0xFFFF, 12, 0, 12),
            (0xFFFE, 12, 0, 8),
            (0, 4, 0, 8),
            (1, 4, 0, 12),
            (0xFFFF, 0, 12, 0),
        ]:
            with self.subTest(immediate=immediate, offset=offset):
                original = self.fixture(
                    word=0x10000000 | immediate, symbol_value=symbol, offset=offset
                )
                annotated = annotate_local_pc16(self.path, original, self.extent)
                branch = annotated[offset // 4]
                self.assertEqual(branch.local_branch_destination, expected)
                self.assertEqual(branch.word, original[offset // 4].word)
                self.assertEqual(branch.relocations, original[offset // 4].relocations)

    def test_unproved_destinations_remain_relocations(self) -> None:
        cases = [
            {"word": 0x2402FFFF},  # not a branch
            {"word": 0x0411FFFF},  # branch-and-link call
            {"word": 0x1801FFFF},  # reserved blez encoding
            {"symbol_section": None},
            {"symbol_section": ".data", "symbol_value": 0},
            {"symbol_value": 16},  # outside owned function
            {"symbol_value": 10},  # misaligned symbol
            {"word": 0x10000000},  # addend resolves just past function
            {"word": 0x1000FFFB},  # addend resolves before function
            {"word": 0x10007FFF},  # large positive addend is not a local edge
            {"duplicate": True},
        ]
        for case in cases:
            with self.subTest(case=case):
                original = self.fixture(**case)  # type: ignore[arg-type]
                annotated = annotate_local_pc16(self.path, original, self.extent)
                self.assertEqual(annotated, original)

    def test_text_must_agree_with_elf(self) -> None:
        original = self.fixture()
        for branch in [
            replace(original[0], word="10000000"),
            replace(original[0], relocations=(Relocation(0, "R_MIPS_PC16", "other"),)),
            replace(
                original[0], relocations=(Relocation(4, "R_MIPS_PC16", ".Linside"),)
            ),
            replace(original[0], relocations=()),
        ]:
            with self.subTest(branch=branch):
                stream = [branch, *original[1:]]
                self.assertEqual(
                    annotate_local_pc16(self.path, stream, self.extent), stream
                )

    def test_owned_extent_and_present_destination_required(self) -> None:
        original = self.fixture()
        for extent in [
            None,
            replace(self.extent, stop=None),
            replace(self.extent, stop=20),
            replace(self.extent, stop=12),
            replace(self.extent, start=4),
            replace(self.extent, name="missing"),
            replace(self.extent, stop=10),
        ]:
            with self.subTest(extent=extent):
                self.assertEqual(
                    annotate_local_pc16(self.path, original, extent), original
                )
        self.assertEqual(
            annotate_local_pc16(self.path, original[:-1], self.extent), original[:-1]
        )

    def test_plain_text_does_not_infer_local_destination(self) -> None:
        original = self.fixture()
        text = normalized_text(
            original[0], address_index={0: 0, 12: 3}, row_of_index={0: 0, 3: 3}
        )
        self.assertEqual(text, "b <.Linside>")

    def test_resolved_candidate_aligns_but_remains_nonexact(self) -> None:
        target = annotate_local_pc16(self.path, self.fixture(), self.extent)
        candidate = [Instruction(0, "10000002", "b c <demo+0xc>"), *target[1:]]
        view = build_view(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol="demo",
        )
        branch = view.rows[0]
        self.assertEqual(branch.classification, "displacement")
        self.assertFalse(branch.matched)
        self.assertFalse(branch.reported)
        comparison = compare_instructions(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol="demo",
        )
        self.assertFalse(comparison.exact)
        self.assertEqual(comparison.raw_word_mismatches, 1)
        self.assertEqual(comparison.relocation_metadata_mismatches, 1)
        self.assertEqual(len(target[0].relocations), 1)
        self.assertEqual(len(candidate[0].relocations), 0)
        self.assertEqual(comparison.aligned_structural, 0)

    def test_loader_authenticates_and_preserves_raw_text(self) -> None:
        self.fixture()
        dump = (
            "00000000 <demo>:\n"
            " 0: 1000ffff b 0 <demo>\n"
            " 0: R_MIPS_PC16 .Linside\n"
            " 4: 00000000 nop\n 8: 00000000 nop\n c: 00000000 nop\n"
        )
        result = subprocess.CompletedProcess(["objdump"], 0, dump, "")
        with (
            patch("decomp_workbench.objdump.discover_objdump", return_value="objdump"),
            patch("decomp_workbench.objdump._run_objdump", return_value=result),
        ):
            raw, instructions = dump_object(self.path, symbol="demo")
        self.assertEqual(raw, dump)
        self.assertEqual(instructions[0].local_branch_destination, 12)
        self.assertEqual(instructions[0].word, "1000ffff")

    def test_bare_operand_uses_authenticated_destination(self) -> None:
        original = self.fixture()
        original[0] = replace(original[0], assembly="b 0x0")
        annotated = annotate_local_pc16(self.path, original, self.extent)
        text = normalized_text(
            annotated[0], address_index={0: 0, 12: 3}, row_of_index={0: 0, 3: 3}
        )
        self.assertEqual(text, "b @row3")

    def test_different_runtime_destination_stays_a_diagnostic_difference(self) -> None:
        target = annotate_local_pc16(self.path, self.fixture(), self.extent)
        candidate = [Instruction(0, "10000001", "b 8 <demo+0x8>"), *target[1:]]
        view = build_view(
            target,
            candidate,
            target_name="target",
            candidate_name="candidate",
            symbol="demo",
        )
        self.assertNotEqual(view.rows[0].classification, "displacement")
        self.assertTrue(view.rows[0].reported)

    def test_unreadable_or_wrong_abi_elf_never_authenticates(self) -> None:
        original = self.fixture()
        body = self.path.read_bytes()
        for content in [b"not ELF", body[:16] + b"\x00\x02" + body[18:]]:
            with self.subTest(content=content[:20]):
                self.path.write_bytes(content)
                self.assertEqual(
                    annotate_local_pc16(self.path, original, self.extent), original
                )
        self.path.unlink()
        self.assertEqual(
            annotate_local_pc16(self.path, original, self.extent), original
        )

    def test_malformed_metadata_or_nonexecutable_section_refuses_hint(self) -> None:
        original = self.fixture()
        elf = read_elf(self.path)
        for untrusted in [
            replace(elf, malformed_reloc_sections=(".rel.text",)),
            replace(
                elf,
                sections=tuple(
                    replace(section, flags=0) if section.name == ".text" else section
                    for section in elf.sections
                ),
            ),
        ]:
            with patch("decomp_workbench.local_pc16.read_elf", return_value=untrusted):
                self.assertEqual(
                    annotate_local_pc16(self.path, original, self.extent), original
                )

    def test_supported_nonlinking_branch_families(self) -> None:
        for word in [0x1400FFFF, 0x5000FFFF, 0x1800FFFF, 0x0401FFFF, 0x4501FFFF]:
            with self.subTest(word=word):
                original = self.fixture(word=word)
                self.assertEqual(
                    annotate_local_pc16(self.path, original, self.extent)[
                        0
                    ].local_branch_destination,
                    12,
                )


if __name__ == "__main__":
    unittest.main()
