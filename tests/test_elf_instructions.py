"""Tests for the native ELF `.text` true-instruction-count reader (WB-62).

Every fixture here reproduces a shape actually seen on a real campaign
object, not a hypothetical: the 3-word padded function
(`baseline/target.o`, real length 4641, section length 4644) and the
single-trailing-`nop` function whose `.text` needed no alignment filler at
all (`archive/p2-04/cand.o`, real length 4632, where a naive "trim every
trailing zero word" rule silently drops one real instruction). Both counts
were cross-checked against
``mips-linux-gnu-objdump -d obj.o | grep -c '^ *[0-9a-f]*:'`` on the actual
objects before being encoded here as fixtures.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elf_fixtures import build_elf32be, words

from decomp_workbench.elf_instructions import (
    MINIMUM_ELIDED_RUN,
    ElfFormatError,
    read_section,
    true_instruction_count,
    true_instruction_count_from_bytes,
)

JR_RA = 0x03E00008
NONZERO = 0x27BD06A8  # addiu sp,sp,1704 -- an arbitrary nonzero delay slot


def write_object(sections: dict[str, bytes]) -> Path:
    directory = tempfile.mkdtemp()
    path = Path(directory) / "obj.o"
    path.write_bytes(build_elf32be(sections))
    return path


class TrueInstructionCountFromBytesTests(unittest.TestCase):
    def test_trims_a_run_of_trailing_padding(self) -> None:
        # Mirrors baseline/target.o: 3 real words, 3 trailing zero words to
        # round out to a 6-word .text -- real answer is 3, not 6.
        raw = words(0x00000000, JR_RA, NONZERO, 0, 0, 0)
        self.assertEqual(true_instruction_count_from_bytes(raw), 3)

    def test_does_not_trim_a_single_trailing_zero_word(self) -> None:
        # Mirrors archive/p2-04/cand.o: .text ends exactly at the delay slot
        # plus one genuine trailing `nop`, with no alignment padding after
        # it. GNU objdump's default disassembly still prints that nop as a
        # real instruction (a run below MINIMUM_ELIDED_RUN is not elided),
        # so trimming it would silently drop one real instruction -- which
        # is exactly what happened before this was measured.
        raw = words(JR_RA, NONZERO, 0)
        self.assertEqual(true_instruction_count_from_bytes(raw), 3)

    def test_trims_exactly_at_the_measured_threshold(self) -> None:
        self.assertEqual(MINIMUM_ELIDED_RUN, 2)
        below = words(JR_RA, NONZERO, *([0] * (MINIMUM_ELIDED_RUN - 1)))
        at = words(JR_RA, NONZERO, *([0] * MINIMUM_ELIDED_RUN))
        self.assertEqual(true_instruction_count_from_bytes(below), len(below) // 4)
        self.assertEqual(true_instruction_count_from_bytes(at), 2)

    def test_no_padding_needed_reports_the_full_length(self) -> None:
        raw = words(0x00000000, JR_RA, NONZERO)
        self.assertEqual(true_instruction_count_from_bytes(raw), 3)

    def test_no_return_at_all_reports_the_full_length(self) -> None:
        raw = words(0x00000000, 0x00000000, 0x00000000)
        self.assertEqual(true_instruction_count_from_bytes(raw), 3)

    def test_nonzero_content_after_the_last_return_is_not_trimmed(self) -> None:
        # A multi-function section whose final function does not end in a
        # plain `jr ra` -- nothing after the last one is safe to call padding.
        raw = words(JR_RA, NONZERO, 0x24020001, 0, 0)
        self.assertEqual(true_instruction_count_from_bytes(raw), 5)

    def test_a_return_as_the_final_word_is_not_trimmed(self) -> None:
        # No room for a delay slot after it: nothing to trim.
        raw = words(0x00000000, JR_RA)
        self.assertEqual(true_instruction_count_from_bytes(raw), 2)


class ReadSectionTests(unittest.TestCase):
    def test_reads_the_named_section_verbatim(self) -> None:
        text = words(JR_RA, NONZERO)
        path = write_object({".text": text})
        self.assertEqual(read_section(path, ".text"), text)

    def test_a_missing_section_is_none(self) -> None:
        path = write_object({".text": words(JR_RA, NONZERO)})
        self.assertIsNone(read_section(path, ".rodata"))

    def test_rejects_a_non_elf_file(self) -> None:
        directory = tempfile.mkdtemp()
        path = Path(directory) / "not-an-object.o"
        path.write_bytes(b"not an elf file at all, just text")
        with self.assertRaises(ElfFormatError):
            read_section(path, ".text")

    def test_rejects_little_endian_elf(self) -> None:
        data = bytearray(build_elf32be({".text": words(JR_RA, NONZERO)}))
        data[5] = 1  # EI_DATA: ELFDATA2LSB, not the ELFDATA2MSB this reads
        directory = tempfile.mkdtemp()
        path = Path(directory) / "obj.o"
        path.write_bytes(bytes(data))
        with self.assertRaises(ElfFormatError) as caught:
            read_section(path, ".text")
        self.assertIn("big-endian", str(caught.exception))

    def test_rejects_64_bit_elf(self) -> None:
        data = bytearray(build_elf32be({".text": words(JR_RA, NONZERO)}))
        data[4] = 2  # EI_CLASS: ELFCLASS64, not the ELFCLASS32 this reads
        directory = tempfile.mkdtemp()
        path = Path(directory) / "obj.o"
        path.write_bytes(bytes(data))
        with self.assertRaises(ElfFormatError) as caught:
            read_section(path, ".text")
        self.assertIn("32-bit", str(caught.exception))


class TrueInstructionCountTests(unittest.TestCase):
    def test_end_to_end_on_the_padded_fixture(self) -> None:
        # The regression fixture the task named directly: section-size count
        # says 6 (padded), the true count is 3.
        raw = words(0x00000000, JR_RA, NONZERO, 0, 0, 0)
        path = write_object({".text": raw})
        self.assertEqual(len(raw) // 4, 6)
        self.assertEqual(true_instruction_count(path), 3)

    def test_a_section_with_no_content_is_none(self) -> None:
        path = write_object({".text": b""})
        self.assertIsNone(true_instruction_count(path))

    def test_an_absent_section_is_none(self) -> None:
        path = write_object({".data": words(0)})
        self.assertIsNone(true_instruction_count(path, section=".text"))


if __name__ == "__main__":
    unittest.main()
