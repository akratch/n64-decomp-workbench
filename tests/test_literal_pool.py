"""Literal-pool anchoring density is not evidence; a different slot is.

Derived from the recorded `object_interaction` campaign.  Its target object
carries one *named external* symbol per literal (`D_80052A9C`, `D_80052AA0`,
...) with a zero addend and no `.rodata` section at all; the candidate the
compiler produced carries a single dense anonymous `.rodata` section symbol
with the slot number in the addend.  Every shared slot therefore rendered as a
different `(symbol, addend)` pair, and 88 rows -- 59 `lui at,0x0` against
`lui at,0x0`, and 29 `lwc1 $fN,0(at)` against `lwc1 $fN,K(at)` -- were reported
as relocation evidence against a pair whose pool accesses agree at every site.
The cost was a planned campaign work item ("fix the literal pool") with nothing
to fix.

Hand-checked against `readelf -r` plus the candidate's `.rodata` hexdump on
five of those sites (`.text` 0x0c9c, 0x111c, 0x1194, 0x15bc, 0x15c8): the
target names `D_80052AA8/AB4/AB8/AC8/ACC` with addend 0 where the candidate
names `.rodata` with addends 8/20/24/40/44, and every one of the five implies
the same pool base, 0x80052AA0.

The fixtures here are synthetic -- the campaign's objects are ROM-derived and
not redistributable -- but they reproduce the pathology and, just as
importantly, the cases that must *not* be absorbed by it.
"""

from __future__ import annotations

import unittest

from mips_asm import assemble

from decomp_workbench.compare import compare_instructions
from decomp_workbench.literal_pool import (
    ABSOLUTE,
    CORRESPONDENCE,
    pool_accesses,
)
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import MechanismView, build_view


#: Three literal loads and a return.  Indices 0/2/4 are the `lui` anchors and
#: 1/3/5 the loads that select a slot.
def body(offsets: list[int]) -> list[str]:
    lines: list[str] = []
    for register, offset in zip(("v0", "v1", "a0"), offsets, strict=True):
        lines.append("lui at,0x0")
        lines.append(f"lw {register},{offset}(at)")
    lines.extend(["jr ra", "nop"])
    return lines


def named(symbols: list[str]) -> dict[int, str]:
    """Relocations naming one external symbol per literal (the target shape)."""

    relocations: dict[int, str] = {}
    for slot, symbol in enumerate(symbols):
        relocations[slot * 2] = f"R_MIPS_HI16 {symbol}"
        relocations[slot * 2 + 1] = f"R_MIPS_LO16 {symbol}"
    return relocations


def dense(count: int, symbol: str = ".rodata") -> dict[int, str]:
    """Relocations naming one section symbol for every literal (the candidate)."""

    return named([symbol] * count)


def view_of(
    target: list[str],
    candidate: list[str],
    *,
    relocations: dict[int, str],
    candidate_relocations: dict[int, str],
) -> MechanismView:
    return build_view(
        parse_disassembly(
            assemble(target, symbol="demo", relocations=relocations), symbol="demo"
        ),
        parse_disassembly(
            assemble(candidate, symbol="demo", relocations=candidate_relocations),
            symbol="demo",
        ),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol="demo",
    )


SPARSE_SYMBOLS = ["D_80052AA8", "D_80052AB4", "D_80052AC8"]


def sparse_versus_dense(candidate_offsets: list[int]) -> MechanismView:
    """The campaign pathology: named-per-literal against one dense pool."""

    return view_of(
        body([0, 0, 0]),
        body(candidate_offsets),
        relocations=named(SPARSE_SYMBOLS),
        candidate_relocations=dense(3),
    )


class SparseVersusDenseTests(unittest.TestCase):
    """The 88 phantom rows, reproduced and then absent."""

    def test_every_row_resolves_to_the_same_slot(self) -> None:
        view = sparse_versus_dense([0, 4, 8])
        self.assertIsNotNone(view.pool)
        assert view.pool is not None
        self.assertEqual(view.pool.resolution, CORRESPONDENCE)
        # Three anchors plus three loads: all six rows are `pool`, and none of
        # them is `relocation` or `constant` any more.
        self.assertEqual(view.counts["pool"], 6)
        self.assertEqual(view.counts["pool_layout"], 0)
        self.assertEqual(view.counts["relocation"], 0)
        self.assertEqual(view.counts["constant"], 0)

    def test_the_rows_stop_being_reported_at_all(self) -> None:
        view = sparse_versus_dense([0, 4, 8])
        self.assertEqual([row for row in view.rows if row.reported], [])
        self.assertEqual(view.verdict, "words-identical")
        self.assertEqual(view.hunks, ())

    def test_both_objects_report_the_same_slot_count(self) -> None:
        view = sparse_versus_dense([0, 4, 8])
        assert view.pool is not None
        self.assertEqual(view.pool.target_slots, 3)
        self.assertEqual(view.pool.candidate_slots, 3)
        self.assertFalse(view.pool.slots_differ)

    def test_a_reordered_pool_is_still_one_to_one(self) -> None:
        """Slot order is a `.rodata` question, not a `.text` one.

        Nothing in either `.text` stream says which byte of the pool a named
        external symbol lives at, so a candidate that emits the same three
        literals in another order still reads the same datum at every site.
        The tool says so, and says which resolution it used, instead of
        claiming a byte identity it cannot see.
        """

        view = sparse_versus_dense([8, 0, 4])
        self.assertEqual(view.counts["pool"], 6)
        self.assertEqual(view.counts["pool_layout"], 0)

    def test_folding_two_slots_into_one_breaks_the_correspondence(self) -> None:
        """The candidate reads slot 0 where the target reads two literals."""

        view = sparse_versus_dense([0, 0, 8])
        # The load that collides, and the `lui` above it whose anchor pair no
        # load justified any more.
        self.assertEqual(view.counts["pool_layout"], 2)
        self.assertEqual(view.verdict, "pool-layout")
        self.assertIn("literal-pool access", view.guidance[0])

    def test_an_inconsistent_displacement_is_reported(self) -> None:
        """One anchor pair, two displacements: a one-to-one map is not enough.

        Both sides name every slot through the *same* pair of anchors here, so
        the slot bijection holds; the pools are still different, because the
        two target slots the candidate places 8 bytes apart are 4 bytes apart
        for the target.
        """

        view = view_of(
            body([0, 4, 8]),
            body([0, 8, 16]),
            relocations=named(["pool", "pool", "pool"]),
            candidate_relocations=dense(3),
        )
        self.assertGreater(view.counts["pool_layout"], 0)


class DenseVersusDenseTests(unittest.TestCase):
    """When both sides anchor on a section, the byte offset is comparable."""

    def test_identical_offsets_resolve_absolutely(self) -> None:
        view = view_of(
            body([0, 4, 8]),
            body([0, 4, 8]),
            relocations=dense(3),
            candidate_relocations=dense(3, ".rdata"),
        )
        assert view.pool is not None
        self.assertEqual(view.pool.resolution, ABSOLUTE)
        # `.rodata` and `.rdata` are one section kind, so the anchors agree and
        # only the byte offsets are compared.
        self.assertEqual(view.counts["pool"], 6)
        self.assertEqual(view.counts["pool_layout"], 0)

    def test_a_different_byte_offset_is_a_pool_layout_difference(self) -> None:
        view = view_of(
            body([0, 4, 8]),
            body([0, 4, 12]),
            relocations=dense(3),
            candidate_relocations=dense(3),
        )
        assert view.pool is not None
        self.assertEqual(view.pool.resolution, ABSOLUTE)
        self.assertEqual(view.counts["pool_layout"], 1)
        self.assertEqual(view.verdict, "pool-layout")


class BoundaryTests(unittest.TestCase):
    """What the pool verdict must never swallow."""

    def test_one_symbol_with_two_addends_is_a_real_difference(self) -> None:
        """An identical symbol names an identical address in both objects."""

        view = view_of(
            body([0, 0, 0]),
            body([0, 20, 0]),
            relocations=named(["jump_table"] * 3),
            candidate_relocations=named(["jump_table"] * 3),
        )
        self.assertEqual(view.counts["pool_layout"], 1)
        # Every other row is byte-identical with identical relocations, so it
        # never reaches the pool resolution at all.
        self.assertEqual(view.counts["match"], 7)
        self.assertEqual(view.counts["pool"], 0)

    def test_an_unpaired_anchor_naming_one_symbol_stays_relocation(self) -> None:
        """A `lui` immediate with no load under it is the linker's field.

        Nothing in the window says which slot it reaches, so resolving it
        would be an invention. The relocation classifier already answers this
        correctly and keeps the row.
        """

        target = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 3c010123  lui $at,0x123\n"
            "                        0: R_MIPS_HI16 global\n"
            "   4: 03e00008  jr $ra\n"
            "   8: 00000000  nop\n",
            symbol="demo",
        )
        candidate = parse_disassembly(
            "00000000 <demo>:\n"
            "   0: 3c010000  lui $at,0x0\n"
            "                        0: R_MIPS_HI16 global\n"
            "   4: 03e00008  jr $ra\n"
            "   8: 00000000  nop\n",
            symbol="demo",
        )
        view = build_view(
            target,
            candidate,
            target_name="t",
            candidate_name="c",
            symbol="demo",
        )
        self.assertEqual(view.counts["relocation"], 1)
        self.assertEqual(view.counts["pool"], 0)
        self.assertEqual(view.counts["pool_layout"], 0)

    def test_a_row_that_also_moved_a_register_is_not_a_pool_row(self) -> None:
        """The resolution speaks for the operand it resolved, and no other."""

        candidate = body([0, 4, 8])
        candidate[3] = "lw t8,4(at)"
        view = view_of(
            body([0, 0, 0]),
            candidate,
            relocations=named(SPARSE_SYMBOLS),
            candidate_relocations=dense(3),
        )
        self.assertEqual(view.counts["register"], 1)
        self.assertEqual(view.counts["pool"], 5)

    def test_an_unrelocated_immediate_is_still_a_constant(self) -> None:
        view = view_of(
            ["li v0,33", "jr ra", "nop"],
            ["li v0,49", "jr ra", "nop"],
            relocations={},
            candidate_relocations={},
        )
        self.assertEqual(view.counts["constant"], 1)
        self.assertEqual(view.counts["pool"], 0)
        self.assertIsNone(view.pool)


class ResolutionTests(unittest.TestCase):
    """The resolver itself, in isolation."""

    def test_an_anchor_carries_no_slot_and_a_load_does(self) -> None:
        instructions = parse_disassembly(
            assemble(body([0, 4, 8]), symbol="demo", relocations=dense(3)),
            symbol="demo",
        )
        accesses = pool_accesses(instructions)
        self.assertEqual(
            [item.role for item in accesses.values()][:2],
            [
                "anchor",
                "access",
            ],
        )
        self.assertEqual([accesses[index].offset for index in (1, 3, 5)], [0, 4, 8])
        self.assertEqual([accesses[index].width for index in (1, 3, 5)], [4, 4, 4])
        self.assertEqual(accesses[0].section, "rodata")

    def test_a_negative_addend_is_signed(self) -> None:
        instructions = parse_disassembly(
            assemble(body([0, -4, 8]), symbol="demo", relocations=dense(3)),
            symbol="demo",
        )
        self.assertEqual(pool_accesses(instructions)[3].offset, -4)


class ComparisonReportTests(unittest.TestCase):
    """`compare --json` must carry the reading, and must lose the rows."""

    def comparison(self) -> Comparison:
        return compare_instructions(
            parse_disassembly(
                assemble(
                    body([0, 0, 0]), symbol="demo", relocations=named(SPARSE_SYMBOLS)
                ),
                symbol="demo",
            ),
            parse_disassembly(
                assemble(body([0, 4, 8]), symbol="demo", relocations=dense(3)),
                symbol="demo",
            ),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        )

    def test_the_phantom_rows_are_gone_from_aligned_diff_sites(self) -> None:
        item = self.comparison()
        self.assertEqual(item.aligned_diff_sites, [])
        self.assertEqual(item.aligned_total, 0)

    def test_the_reading_is_reported_beside_the_counts(self) -> None:
        payload = self.comparison().as_dict()
        self.assertEqual(payload["pool_resolution"], CORRESPONDENCE)
        self.assertEqual(payload["pool_matches"], 6)
        self.assertEqual(payload["pool_layout_mismatches"], 0)
        self.assertEqual(payload["target_pool_slots"], 3)
        self.assertEqual(payload["candidate_pool_slots"], 3)

    def test_a_pair_with_no_relocated_data_reports_nothing(self) -> None:
        payload = compare_instructions(
            parse_disassembly(assemble(["li v0,33", "jr ra", "nop"]), symbol="demo"),
            parse_disassembly(assemble(["li v0,49", "jr ra", "nop"]), symbol="demo"),
            target_name="target.o",
            candidate_name="candidate.o",
            symbol="demo",
        ).as_dict()
        self.assertIsNone(payload["pool_resolution"])
        self.assertEqual(payload["pool_matches"], 0)


if __name__ == "__main__":
    unittest.main()
