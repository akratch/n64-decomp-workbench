"""Regression cover for `compare --symbol` on multi-function objects.

The defect (docs/known-defects.md, 2026-08-24): the selector ended the
selection at the first ``<label>:`` header after the requested symbol. A target
object extracted from a ROM carries a symbol for every jump-table destination
*inside* one function body, so the selection stopped 68 instructions into an
1,868-instruction function and the comparison reported ``words=1799
opcodes=1798 gaps=1798`` -- a prologue against a whole function, reading as a
broken candidate rather than a broken selector.

Every fixture here is synthetic: hand-built ELF objects and hand-written
objdump text, no game code.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from elf_fixtures import (
    STB_GLOBAL,
    STB_LOCAL,
    STT_FUNC,
    STT_NOTYPE,
    build_object,
    words,
)

from decomp_workbench.compare import compare_objects
from decomp_workbench.elf_symbols import symbol_extent
from decomp_workbench.objdump import interior_labels, parse_disassembly

# Two trivial functions. `wb_first` is four words; `wb_second` is a loop whose
# body carries an interior label -- the shape a jump table or a `goto` target
# produces, and the shape that broke the selector.
FIRST = words(
    0x03E00008,  # jr ra
    0x24020001,  # addiu v0,zero,1
    0x00000000,  # nop
    0x00000000,  # nop
)
SECOND = words(
    0x27BDFFE8,  # addiu sp,sp,-24
    0x00001025,  # move v0,zero
    0x1880000B,  # blez a0,+11        -> the interior label
    0x00000000,  # nop
    0x8C830000,  # lw v1,0(a0)
    0x00431021,  # addu v0,v0,v1
    0x2484FFFF,  # addiu a0,a0,-1
    0x1C80FFFC,  # bgtz a0,-4
    0x00000000,  # nop
    0x03E00008,  # jr ra
    0x27BD0018,  # addiu sp,sp,24
)

SECOND_START = len(FIRST)
#: The interior label sits inside `wb_second`, at its ninth word.
INTERIOR_OFFSET = SECOND_START + 9 * 4


def _two_function_object() -> bytes:
    return build_object(
        text=FIRST + SECOND,
        symbols=[
            ("wb_first", 0, len(FIRST), STT_FUNC, STB_GLOBAL),
            ("wb_second", SECOND_START, len(SECOND), STT_FUNC, STB_GLOBAL),
            # The label that used to end the selection. Local, no type, no
            # size: everything a jump-table destination is.
            ("wb_second_case", INTERIOR_OFFSET, 0, STT_NOTYPE, STB_LOCAL),
        ],
    )


def _sized_free_object() -> bytes:
    """`wb_second` alone, with no ELF size -- the assembly-defined shape."""

    return build_object(
        text=SECOND,
        symbols=[
            ("wb_second", 0, 0, STT_FUNC, STB_GLOBAL),
            ("wb_second_case", 9 * 4, 0, STT_NOTYPE, STB_LOCAL),
        ],
    )


#: objdump text for a function whose body carries two interior labels. The
#: addresses are the fixture's, so a parse can be checked against them.
DUMP_WITH_INTERIOR_LABELS = """
demo.o:     file format elf32-tradbigmips

Disassembly of section .text:

00000000 <wb_second>:
   0:\t27bdffe8 \taddiu\tsp,sp,-24
   4:\t00001025 \tmove\tv0,zero
   8:\t1880000b \tblez\ta0,24 <wb_second_case>

0000000c <wb_second_case>:
   c:\t8c830000 \tlw\tv1,0(a0)
  10:\t00431021 \taddu\tv0,v0,v1
  14:\t1c80fffc \tbgtz\ta0,c <wb_second_case>

00000018 <wb_second_tail>:
  18:\t03e00008 \tjr\tra
  1c:\t27bd0018 \taddiu\tsp,sp,24

00000020 <wb_third>:
  20:\t03e00008 \tjr\tra
  24:\t00000000 \tnop
"""


class InteriorLabelTests(unittest.TestCase):
    def test_a_conditional_branch_target_is_an_interior_label(self) -> None:
        self.assertEqual(interior_labels(DUMP_WITH_INTERIOR_LABELS), {"wb_second_case"})

    def test_text_selection_runs_through_a_branch_target_label(self) -> None:
        # Before the fix this returned three instructions: the selection ended
        # at `<wb_second_case>:`.
        parsed = parse_disassembly(DUMP_WITH_INTERIOR_LABELS, symbol="wb_second")
        self.assertEqual([item.address for item in parsed], [0, 4, 8, 0xC, 0x10, 0x14])

    def test_text_selection_still_stops_at_an_unreferenced_label(self) -> None:
        # `wb_second_tail` is reached by no conditional branch, so text alone
        # cannot prove it interior and the parser must not assume it is. This
        # is the documented limit of the text-only rule, asserted so it stays
        # a known limit rather than becoming an accidental behaviour change.
        parsed = parse_disassembly(DUMP_WITH_INTERIOR_LABELS, symbol="wb_second_tail")
        self.assertEqual([item.address for item in parsed], [0x18, 0x1C])

    def test_extent_selection_ignores_labels_entirely(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "sized.o"
            path.write_bytes(_sized_free_object())
            extent = symbol_extent(path, "wb_second")
        assert extent is not None
        parsed = parse_disassembly(
            DUMP_WITH_INTERIOR_LABELS, symbol="wb_second", extent=extent
        )
        # No size and no later function symbol: the extent runs to the end of
        # the section, so every row of the dump is selected -- including the
        # rows behind the two interior labels.
        self.assertEqual(
            [item.address for item in parsed],
            [0, 4, 8, 0xC, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24],
        )


class SymbolExtentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.two = self.directory / "two.o"
        self.two.write_bytes(_two_function_object())
        self.one = self.directory / "one.o"
        self.one.write_bytes(
            build_object(
                text=SECOND,
                symbols=[("wb_second", 0, len(SECOND), STT_FUNC, STB_GLOBAL)],
            )
        )

    def test_declared_size_bounds_the_symbol(self) -> None:
        extent = symbol_extent(self.two, "wb_second")
        assert extent is not None
        self.assertEqual(
            (extent.start, extent.stop, extent.basis),
            (SECOND_START, SECOND_START + len(SECOND), "size"),
        )

    def test_an_interior_label_never_bounds_a_function(self) -> None:
        extent = symbol_extent(self.two, "wb_second")
        assert extent is not None
        # The whole defect in one assertion: the interior label's offset is
        # inside the extent, not the end of it.
        self.assertTrue(extent.contains(INTERIOR_OFFSET))

    def test_a_sizeless_symbol_is_bounded_by_the_next_function(self) -> None:
        path = self.directory / "sizeless.o"
        path.write_bytes(
            build_object(
                text=FIRST + SECOND,
                symbols=[
                    ("wb_first", 0, 0, STT_FUNC, STB_GLOBAL),
                    ("wb_second", SECOND_START, 0, STT_FUNC, STB_GLOBAL),
                    ("wb_first_case", 8, 0, STT_NOTYPE, STB_LOCAL),
                ],
            )
        )
        extent = symbol_extent(path, "wb_first")
        assert extent is not None
        self.assertEqual(
            (extent.start, extent.stop, extent.basis),
            (0, SECOND_START, "next-function"),
        )

    def test_a_sizeless_final_symbol_runs_to_the_section_end(self) -> None:
        path = self.directory / "final.o"
        path.write_bytes(_sized_free_object())
        extent = symbol_extent(path, "wb_second")
        assert extent is not None
        self.assertEqual(
            (extent.start, extent.stop, extent.basis), (0, None, "section-end")
        )
        self.assertTrue(extent.contains(len(SECOND) - 4))

    def test_a_unique_case_fold_is_honoured(self) -> None:
        extent = symbol_extent(self.two, "WB_Second")
        assert extent is not None
        self.assertEqual(extent.name, "wb_second")

    def test_an_unknown_symbol_declines_rather_than_guessing(self) -> None:
        self.assertIsNone(symbol_extent(self.two, "wb_missing"))

    def test_a_non_elf_file_declines(self) -> None:
        path = self.directory / "not-an-object.txt"
        path.write_text("this is not an ELF file", encoding="utf-8")
        self.assertIsNone(symbol_extent(path, "wb_second"))


@unittest.skipUnless(
    shutil.which("mips-linux-gnu-objdump") or shutil.which("mips64-elf-objdump"),
    "needs a MIPS objdump",
)
class SymbolScopedComparisonTests(unittest.TestCase):
    """The defect end to end: one function carved out of two, through objdump."""

    def test_a_multi_function_object_compares_only_the_named_function(self) -> None:
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            two = directory / "two.o"
            two.write_bytes(_two_function_object())
            one = directory / "one.o"
            one.write_bytes(
                build_object(
                    text=SECOND,
                    symbols=[("wb_second", 0, len(SECOND), STT_FUNC, STB_GLOBAL)],
                )
            )
            scoped = compare_objects(one, two, symbol="wb_second")
            whole = compare_objects(one, two)
        # Same function, so the scoped comparison is exact. Before the fix the
        # target side stopped at the interior label and this reported a
        # four-figure residual against an object holding identical code.
        self.assertTrue(scoped.exact, scoped.verdict)
        self.assertEqual(scoped.word_mismatches, 0)
        self.assertEqual(scoped.target_instructions, scoped.candidate_instructions)
        # And the control: without the selector, the whole section really does
        # differ, because the candidate has an extra function in front.
        self.assertFalse(whole.exact)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
