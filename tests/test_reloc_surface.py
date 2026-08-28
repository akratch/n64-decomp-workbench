"""Synthesizing a placeholder symbol's value from the shipped image.

Every fixture here is built by hand from `elf_fixtures`: an object whose
`.text` references two undefined symbols, and a synthetic "image" carrying
the addends a runtime linker would patch. No game bytes, no toolchain, and
no linked ELF -- the link is exactly what is missing in the case the
synthesis exists for.
"""

from __future__ import annotations

import unittest

from elf_fixtures import (
    R_MIPS_26,
    R_MIPS_32,
    R_MIPS_HI16,
    R_MIPS_LO16,
    STB_GLOBAL,
    STB_LOCAL,
    STT_FUNC,
    RelocSpec,
    SymbolSpec,
    build_relocatable,
    words,
)

from decomp_workbench import reloc_surface as rs
from decomp_workbench.elf import parse_elf

JAL = 0x0C000000
LUI = 0x3C010000
LW = 0x8C210000
NOP = 0x00000000

MODULE_START = 0x1000
TU_OFFSET = 0x40


def candidate_object(*, low_addend: int = 0x10, jal_symbol: str = "callee") -> bytes:
    """A translation unit that calls one placeholder and loads through another.

    The object's own instructions carry the compiler's addend (the struct
    field offset in the `%lo`), which is the half that must be subtracted
    before a value reaches the linker script.
    """

    text = words(JAL, NOP, LUI, LW | low_addend)
    return build_relocatable(
        {".text": text},
        [
            SymbolSpec("myFunc", 0, 16, STT_FUNC, STB_GLOBAL, ".text"),
            SymbolSpec(jal_symbol),
            SymbolSpec("gBase"),
        ],
        [
            RelocSpec(".text", 0, jal_symbol, R_MIPS_26),
            RelocSpec(".text", 8, "gBase", R_MIPS_HI16),
            RelocSpec(".text", 12, "gBase", R_MIPS_LO16),
        ],
    )


def shipped_image(*, jal_immediate: int = 0x123, lo: int = 0x8020) -> bytes:
    """The module as the game ships it: stored addends, not addresses."""

    image = bytearray(0x4000)
    body = words(JAL | jal_immediate, NOP, LUI | 0x0002, LW | lo)
    start = MODULE_START + TU_OFFSET
    image[start : start + len(body)] = body
    return bytes(image)


def module_document(**overrides: object) -> dict[str, object]:
    module: dict[str, object] = {
        "name": "m1",
        "image_start": "0x1000",
        "image_end": "0x2000",
        "synthetic_vma": "0xF0000000",
        "sections": {".text": {"offset": 0, "size": 0x800}},
        "text_placement": [
            {
                "object": "tu.c.o",
                "section": ".text",
                "offset": hex(TU_OFFSET),
                "size": 16,
            }
        ],
        "relocation_sites": [
            {"offset": TU_OFFSET + 0, "type": "R_MIPS_26"},
            {"offset": TU_OFFSET + 8, "type": "R_MIPS_HI16"},
            {"offset": TU_OFFSET + 12, "type": "R_MIPS_LO16"},
        ],
    }
    module.update(overrides)
    return {"schema": rs.MODULE_MAP_SCHEMA, "module": module}


def surface_for(
    *,
    object_bytes: bytes | None = None,
    image: bytes | None = None,
    **overrides: object,
) -> rs.RelocSurface:
    module = rs.parse_module_map(module_document(**overrides))
    elf = parse_elf(object_bytes if object_bytes is not None else candidate_object())
    return rs.synthesize(
        [("tu.c.o", elf)], module, image if image is not None else shipped_image()
    )


class ModuleMapTests(unittest.TestCase):
    def test_a_map_parses_hex_and_decimal_alike(self) -> None:
        module = rs.parse_module_map(module_document())
        self.assertEqual(module.image_start, 0x1000)
        self.assertEqual(module.synthetic_vma, 0xF0000000)
        self.assertEqual(module.placements_for("build/tu.c.o")[0].offset, TU_OFFSET)

    def test_an_unknown_schema_is_refused_by_name(self) -> None:
        document = module_document()
        document["schema"] = "something-else-v9"
        with self.assertRaises(rs.ModuleMapError) as caught:
            rs.parse_module_map(document)
        self.assertIn(rs.MODULE_MAP_SCHEMA, str(caught.exception))

    def test_a_section_past_the_modules_end_is_refused(self) -> None:
        with self.assertRaises(rs.ModuleMapError) as caught:
            rs.parse_module_map(
                module_document(sections={".text": {"offset": 0, "size": 0x9000}})
            )
        self.assertIn("past the module", str(caught.exception))

    def test_a_placement_outside_its_section_is_refused(self) -> None:
        with self.assertRaises(rs.ModuleMapError) as caught:
            rs.parse_module_map(
                module_document(
                    text_placement=[
                        {"object": "tu.c.o", "section": ".text", "offset": "0x900"}
                    ]
                )
            )
        self.assertIn("outside section", str(caught.exception))

    def test_a_module_that_ends_before_it_starts_is_refused(self) -> None:
        with self.assertRaises(rs.ModuleMapError):
            rs.parse_module_map(module_document(image_end="0x1000"))


class SynthesisTests(unittest.TestCase):
    def test_a_call_takes_the_synthetic_vma_and_the_stored_immediate(self) -> None:
        surface = surface_for()
        self.assertEqual(surface.value_map()["callee"], 0xF0000000 | (0x123 << 2))

    def test_a_hi_lo_pair_is_read_together_and_the_objects_addend_removed(
        self,
    ) -> None:
        surface = surface_for()
        # (2 << 16) + sext16(0x8020) = 0x18020, less the object's own 0x10.
        self.assertEqual(surface.value_map()["gBase"], 0x18010)

    def test_the_object_addend_is_what_makes_one_base_serve_many_fields(
        self,
    ) -> None:
        """Two objects differing only in the field offset want one value."""

        first = surface_for(
            object_bytes=candidate_object(low_addend=0x10),
            image=shipped_image(lo=0x8020),
        )
        second = surface_for(
            object_bytes=candidate_object(low_addend=0x24),
            image=shipped_image(lo=0x8034),
        )
        self.assertEqual(first.value_map()["gBase"], second.value_map()["gBase"])

    def test_a_symbol_another_object_of_the_module_defines_needs_no_value(
        self,
    ) -> None:
        module = rs.parse_module_map(
            module_document(
                text_placement=[
                    {"object": "tu.c.o", "section": ".text", "offset": hex(TU_OFFSET)},
                    {"object": "other.c.o", "section": ".text", "offset": "0x100"},
                ]
            )
        )
        other = build_relocatable(
            {".text": words(NOP)},
            [SymbolSpec("callee", 0, 4, STT_FUNC, STB_GLOBAL, ".text")],
        )
        surface = rs.synthesize(
            [
                ("tu.c.o", parse_elf(candidate_object())),
                ("other.c.o", parse_elf(other)),
            ],
            module,
            shipped_image(),
        )
        self.assertNotIn("callee", surface.value_map())
        self.assertIn("gBase", surface.value_map())

    def test_a_static_in_another_object_does_not_satisfy_the_reference(
        self,
    ) -> None:
        """Only a linkable definition makes an assignment unnecessary.

        A `STB_LOCAL` symbol resolves nothing outside its own object, so
        treating one as the module's definition drops the value line and
        leaves the link with an undefined reference and no reason for it.
        """

        module = rs.parse_module_map(
            module_document(
                text_placement=[
                    {"object": "tu.c.o", "section": ".text", "offset": hex(TU_OFFSET)},
                    {"object": "other.c.o", "section": ".text", "offset": "0x100"},
                ]
            )
        )
        other = build_relocatable(
            {".text": words(NOP)},
            [SymbolSpec("callee", 0, 4, STT_FUNC, STB_LOCAL, ".text")],
        )
        surface = rs.synthesize(
            [
                ("tu.c.o", parse_elf(candidate_object())),
                ("other.c.o", parse_elf(other)),
            ],
            module,
            shipped_image(),
        )
        self.assertIn("callee", surface.value_map())

    def test_a_map_written_on_windows_matches_a_posix_object_path(self) -> None:
        """A basename is a basename under either separator.

        The map is written once by the host and the objects are named by the
        build; the two need not agree on separators, and matching only on
        `/` silently placed nothing and emitted an empty surface.
        """

        module = rs.parse_module_map(
            module_document(
                text_placement=[
                    {
                        "object": "build\\overlay\\tu.c.o",
                        "section": ".text",
                        "offset": hex(TU_OFFSET),
                        "size": 16,
                    }
                ]
            )
        )
        surface = rs.synthesize(
            [("build/overlay/tu.c.o", parse_elf(candidate_object()))],
            module,
            shipped_image(),
        )
        self.assertIn("callee", surface.value_map())

    def test_an_r_mips_32_site_takes_the_stored_word(self) -> None:
        obj = build_relocatable(
            {".text": words(NOP), ".data": words(0x00000004)},
            [SymbolSpec("gPointer")],
            [RelocSpec(".data", 0, "gPointer", R_MIPS_32)],
        )
        image = bytearray(shipped_image())
        image[MODULE_START + 0x200 : MODULE_START + 0x204] = words(0x80112244)
        surface = surface_for(
            object_bytes=bytes(obj),
            image=bytes(image),
            sections={
                ".text": {"offset": 0, "size": 0x200},
                ".data": {"offset": 0x200, "size": 0x100},
            },
            text_placement=[
                {"object": "tu.c.o", "section": ".data", "offset": "0x200", "size": 4}
            ],
            relocation_sites=[{"offset": 0x200, "type": "R_MIPS_32"}],
        )
        self.assertEqual(surface.value_map(), {"gPointer": 0x80112240})

    def test_an_alias_block_is_emitted_for_the_names_the_object_defines(
        self,
    ) -> None:
        surface = surface_for(alias_template="func_{module}_{module_offset:07X}")
        self.assertEqual(
            [(item.identity, item.name) for item in surface.aliases],
            [("func_m1_0000040", "myFunc")],
        )
        block = "\n".join(rs.render_linker_block(surface))
        self.assertIn("func_m1_0000040 = myFunc;", block)
        self.assertIn("callee = 0xF000048C;", block)

    def test_an_identity_that_is_its_own_name_gets_no_circular_alias(self) -> None:
        obj = build_relocatable(
            {".text": words(NOP)},
            [SymbolSpec("func_m1_0000040", 0, 4, STT_FUNC, STB_GLOBAL, ".text")],
        )
        surface = surface_for(
            object_bytes=obj, alias_template="func_{module}_{module_offset:07X}"
        )
        self.assertEqual(surface.aliases, ())

    def test_the_rendered_block_reads_back_as_the_values_it_states(self) -> None:
        surface = surface_for()
        block = "\n".join(rs.render_linker_block(surface))
        self.assertEqual(rs.tracked_values(block), surface.value_map())


class RefusalTests(unittest.TestCase):
    def test_two_sites_demanding_different_values_are_refused_by_name(self) -> None:
        """The schedule diverged at the site; no addend is readable there."""

        text = words(JAL, JAL, NOP, NOP)
        obj = build_relocatable(
            {".text": text},
            [SymbolSpec("callee")],
            [
                RelocSpec(".text", 0, "callee", R_MIPS_26),
                RelocSpec(".text", 4, "callee", R_MIPS_26),
            ],
        )
        image = bytearray(0x4000)
        start = MODULE_START + TU_OFFSET
        image[start : start + 16] = words(JAL | 0x111, JAL | 0x222, NOP, NOP)
        surface = surface_for(
            object_bytes=obj,
            image=bytes(image),
            relocation_sites=[
                {"offset": TU_OFFSET, "type": "R_MIPS_26"},
                {"offset": TU_OFFSET + 4, "type": "R_MIPS_26"},
            ],
        )
        self.assertEqual(surface.value_map(), {})
        self.assertFalse(surface.ok)
        (conflict,) = surface.conflicts
        self.assertEqual(conflict.symbol, "callee")
        self.assertEqual(conflict.reason, "schedule-divergence-at-site")
        self.assertEqual(
            conflict.values, (0xF0000000 | (0x111 << 2), 0xF0000000 | (0x222 << 2))
        )
        self.assertEqual(
            sorted(site.module_offset for site in conflict.sites),
            [TU_OFFSET, TU_OFFSET + 4],
        )

    def test_a_site_the_shipped_table_does_not_name_is_ignored_when_another_is(
        self,
    ) -> None:
        """The image's own statement, not a heuristic: only patched sites count."""

        text = words(JAL, JAL, NOP, NOP)
        obj = build_relocatable(
            {".text": text},
            [SymbolSpec("callee")],
            [
                RelocSpec(".text", 0, "callee", R_MIPS_26),
                RelocSpec(".text", 4, "callee", R_MIPS_26),
            ],
        )
        image = bytearray(0x4000)
        start = MODULE_START + TU_OFFSET
        image[start : start + 16] = words(JAL | 0x111, JAL | 0x222, NOP, NOP)
        surface = surface_for(
            object_bytes=obj,
            image=bytes(image),
            relocation_sites=[{"offset": TU_OFFSET, "type": "R_MIPS_26"}],
        )
        self.assertEqual(surface.value_map(), {"callee": 0xF0000000 | (0x111 << 2)})
        self.assertEqual(surface.conflicts, ())

    def test_a_symbol_whose_every_corroborated_site_moved_is_reported(self) -> None:
        """Corroborated somewhere, but not where this object still spells it.

        The shipped table names the `%hi` site and not its `%lo` partner, so
        the pair is dropped by the corroboration filter and no addend survives
        for `gBase`. Saying nothing would leave the caller with an undefined
        reference and no reason for it.
        """

        surface = surface_for(
            relocation_sites=[{"offset": TU_OFFSET + 8, "type": "R_MIPS_HI16"}]
        )
        reasons = {item.symbol: item.reason for item in surface.conflicts}
        self.assertEqual(reasons.get("gBase"), "no-corroborated-site")
        self.assertIn("callee", surface.value_map())

    def test_a_site_outside_the_module_is_not_read_as_an_addend(self) -> None:
        surface = surface_for(
            text_placement=[
                {"object": "tu.c.o", "section": ".text", "offset": "0x7F8"}
            ],
            relocation_sites=[],
        )
        reasons = {item.reason for item in surface.conflicts}
        self.assertIn("unmapped-site", reasons)

    def test_an_object_the_map_does_not_place_says_so(self) -> None:
        module = rs.parse_module_map(module_document())
        surface = rs.synthesize(
            [("unplaced.c.o", parse_elf(candidate_object()))], module, shipped_image()
        )
        self.assertEqual(surface.values, ())
        self.assertTrue(
            any("places no section" in warning for warning in surface.warnings)
        )

    def test_without_a_shipped_table_the_missing_corroboration_is_stated(
        self,
    ) -> None:
        surface = surface_for(relocation_sites=[])
        self.assertFalse(surface.corroborated)
        self.assertTrue(
            any("no shipped relocation table" in item for item in surface.warnings)
        )


class LoneHi16Tests(unittest.TestCase):
    """A HI16 with no LO16 cannot observe the borrow its pair would carry."""

    @staticmethod
    def orphan_object() -> bytes:
        return build_relocatable(
            {".text": words(LUI, NOP)},
            [
                SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("gBase"),
            ],
            [RelocSpec(".text", 0, "gBase", R_MIPS_HI16)],
        )

    def surface(self) -> rs.RelocSurface:
        image = bytearray(0x4000)
        image[MODULE_START + TU_OFFSET : MODULE_START + TU_OFFSET + 8] = words(
            LUI | 0x0002, NOP
        )
        return surface_for(
            object_bytes=self.orphan_object(),
            image=bytes(image),
            relocation_sites=[{"offset": TU_OFFSET + 0, "type": "R_MIPS_HI16"}],
        )

    def test_the_value_is_produced_but_the_run_says_it_is_a_guess(self) -> None:
        """The low half is unobserved, so the value may be 0x10000 out.

        A HI16 field is written as `((V + 0x8000) >> 16) & 0xFFFF`: the
        borrow depends on the sign of the LO16 half, and with no LO16 site
        the synthesis cannot see it. Both 0x20000 and anything in
        0x18000..0x1FFFF write the same word, and the run has to say so
        rather than let a linker script carry a silent guess.
        """

        surface = self.surface()
        self.assertEqual(surface.value_map()["gBase"], 0x0002 << 16)
        self.assertTrue(
            any("gBase" in item and "LO16" in item for item in surface.warnings),
            surface.warnings,
        )

    def test_a_paired_hi16_is_not_warned_about(self) -> None:
        self.assertFalse(
            any("unpaired" in item for item in surface_for().warnings),
        )


class AuditTests(unittest.TestCase):
    def test_a_hand_written_block_that_agrees_scores_clean(self) -> None:
        surface = surface_for()
        report = rs.audit(surface, rs.tracked_values("callee = 0xF000048C;\n"))
        self.assertEqual((report.agree, report.disagree), (1, 0))
        self.assertTrue(report.ok)
        self.assertEqual(report.count("untracked"), 1)

    def test_a_disagreement_names_both_values(self) -> None:
        surface = surface_for()
        report = rs.audit(surface, {"callee": 0x1234})
        row = next(item for item in report.rows if item.name == "callee")
        self.assertEqual(row.status, "disagree")
        self.assertEqual((row.tracked, row.synthesized), (0x1234, 0xF000048C))
        self.assertFalse(report.ok)

    def test_a_name_the_synthesis_did_not_reach_is_not_a_disagreement(self) -> None:
        surface = surface_for()
        report = rs.audit(surface, {"gElsewhere": 0x10})
        row = next(item for item in report.rows if item.name == "gElsewhere")
        self.assertEqual(row.status, "unreproduced")
        self.assertEqual(report.disagree, 0)

    def test_the_last_assignment_wins_the_way_a_linker_reads_one(self) -> None:
        block = "gDup = 0x1;\n/* gDup = 0x9; */\ngDup = 0x2;\n"
        self.assertEqual(rs.tracked_values(block), {"gDup": 0x2})

    def test_an_alias_line_reads_back_as_a_name_not_a_number(self) -> None:
        parsed = rs.parse_linker_block("func_m1_0000040 = myFunc;\ngA = 0x4;\n")
        self.assertEqual(parsed, {"func_m1_0000040": "myFunc", "gA": "0x4"})
        self.assertEqual(rs.tracked_values("func_m1_0000040 = myFunc;\n"), {})


class PlaceholderCallTests(unittest.TestCase):
    """The permuter's precondition: can the scratch name what the target calls?"""

    @staticmethod
    def target(symbol: str) -> bytes:
        return build_relocatable(
            {".text": words(JAL, NOP)},
            [
                SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec(symbol) if symbol != "myFunc" else SymbolSpec("pad"),
            ],
            [RelocSpec(".text", 0, symbol, R_MIPS_26)],
        )

    def test_a_call_that_names_the_function_itself_is_unreproducible(self) -> None:
        finding = rs.placeholder_call_check(
            parse_elf(self.target("myFunc")), None, function="myFunc"
        )
        self.assertTrue(finding.blocked)
        self.assertEqual(finding.self_named, ("myFunc",))
        self.assertIn("linked-compare", finding.message)

    def test_a_call_to_a_symbol_the_candidate_lacks_is_unreproducible(self) -> None:
        candidate = build_relocatable(
            {".text": words(JAL, NOP)},
            [SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text")],
        )
        finding = rs.placeholder_call_check(
            parse_elf(self.target("overlayChain0Reloc")),
            parse_elf(candidate),
            function="myFunc",
        )
        self.assertTrue(finding.blocked)
        self.assertEqual(finding.absent_from_candidate, ("overlayChain0Reloc",))

    def test_a_call_the_candidate_can_name_is_not_blocked(self) -> None:
        candidate = build_relocatable(
            {".text": words(JAL, NOP)},
            [
                SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("ordinaryCallee"),
            ],
            [RelocSpec(".text", 0, "ordinaryCallee", R_MIPS_26)],
        )
        finding = rs.placeholder_call_check(
            parse_elf(self.target("ordinaryCallee")),
            parse_elf(candidate),
            function="myFunc",
        )
        self.assertFalse(finding.blocked)
        self.assertEqual(finding.reproducible, ("ordinaryCallee",))

    def test_ordinary_self_recursion_the_candidate_reproduces_is_not_blocked(
        self,
    ) -> None:
        """A resident recursive function is the false positive to avoid.

        Its target object also spells a call with the containing symbol, so
        the name alone cannot tell it from an unrelocated module's
        placeholder. The candidate can: it carries the same symbol and
        relocates against it too, so the permuter reproduces that word and
        the score has no floor.
        """

        candidate = build_relocatable(
            {".text": words(JAL, NOP)},
            [SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text")],
            [RelocSpec(".text", 0, "myFunc", R_MIPS_26)],
        )
        finding = rs.placeholder_call_check(
            parse_elf(self.target("myFunc")), parse_elf(candidate), function="myFunc"
        )
        self.assertFalse(finding.blocked)
        self.assertEqual(finding.reproducible, ("myFunc",))
        self.assertEqual(finding.self_named, ())

    def test_without_a_candidate_a_self_call_names_recursion_as_the_other_read(
        self,
    ) -> None:
        """The verdict stands, but it must not claim to have excluded recursion."""

        finding = rs.placeholder_call_check(
            parse_elf(self.target("myFunc")), None, function="myFunc"
        )
        self.assertTrue(finding.blocked)
        self.assertIn("--candidate-object", finding.message)
        self.assertIn("recursion", finding.message)

    def test_a_function_with_no_calls_at_all_is_never_blocked(self) -> None:
        obj = build_relocatable(
            {".text": words(NOP, NOP)},
            [SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text")],
        )
        finding = rs.placeholder_call_check(
            parse_elf(obj), parse_elf(obj), function="myFunc"
        )
        self.assertEqual(finding.call_sites, 0)
        self.assertFalse(finding.blocked)

    def test_only_the_named_functions_own_sites_are_read(self) -> None:
        """A neighbour's call in the same object must not decide this verdict."""

        obj = build_relocatable(
            {".text": words(JAL, NOP, JAL, NOP)},
            [
                SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("neighbour", 8, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("ordinaryCallee"),
            ],
            [
                RelocSpec(".text", 0, "ordinaryCallee", R_MIPS_26),
                RelocSpec(".text", 8, "myFunc", R_MIPS_26),
            ],
        )
        candidate = build_relocatable(
            {".text": words(JAL, NOP)},
            [
                SymbolSpec("myFunc", 0, 8, STT_FUNC, STB_GLOBAL, ".text"),
                SymbolSpec("ordinaryCallee"),
            ],
        )
        finding = rs.placeholder_call_check(
            parse_elf(obj), parse_elf(candidate), function="myFunc"
        )
        self.assertEqual(finding.call_sites, 1)
        self.assertFalse(finding.blocked)


if __name__ == "__main__":
    unittest.main()


class AddendArithmeticTests(unittest.TestCase):
    """The synthesized value, replayed through the linker's own formulas.

    A value is right when relinking with it reproduces the shipped word. That
    is a property, not an example, so these replay the o32 REL formulas the
    linker applies -- including the ``+ 0x8000`` the HI16 half of a pair
    carries -- over the sign-extension boundary rather than asserting one
    hand-computed number.
    """

    @staticmethod
    def link_hi_lo(value: int, hi_addend: int, lo_addend: int) -> tuple[int, int]:
        """What `ld` stores at a HI16/LO16 pair for ``value``.

        The MIPS pairing convention: the LO16 field is signed, so the HI16
        field carries the borrow the sign extension will apply, which is what
        the ``+ 0x8000`` before the shift computes.
        """

        final = (value + (hi_addend << 16) + rs.sext16(lo_addend)) & 0xFFFFFFFF
        return ((final + 0x8000) >> 16) & 0xFFFF, final & 0xFFFF

    @staticmethod
    def link_jump(value: int, addend: int) -> int:
        """What `ld` stores in an `R_MIPS_26` field for an external symbol."""

        return ((value + (addend << 2)) >> 2) & 0x03FFFFFF

    def test_a_hi_lo_value_relinks_to_the_shipped_words(self) -> None:
        for stored_lo in (0x0000, 0x0001, 0x7FFF, 0x8000, 0x8020, 0xFFFF):
            for object_lo in (0x0000, 0x0010, 0x7FFF, 0x8000, 0xFFF0):
                with self.subTest(stored_lo=stored_lo, object_lo=object_lo):
                    surface = surface_for(
                        object_bytes=candidate_object(low_addend=object_lo),
                        image=shipped_image(lo=stored_lo),
                    )
                    value = surface.value_map()["gBase"]
                    self.assertEqual(
                        self.link_hi_lo(value, 0x0000, object_lo),
                        (0x0002, stored_lo),
                    )

    def test_a_call_value_relinks_to_the_shipped_immediate(self) -> None:
        for stored in (0x000000, 0x000123, 0x1FFFFFF, 0x3FFFFFF):
            with self.subTest(stored=stored):
                surface = surface_for(image=shipped_image(jal_immediate=stored))
                value = surface.value_map()["callee"]
                self.assertEqual(self.link_jump(value, 0x0), stored)

    def test_a_synthetic_vma_below_the_jump_region_does_not_reach_the_field(
        self,
    ) -> None:
        """A `jal` field is 28 bits; the rest of the VMA is the region nibble.

        A module map whose `synthetic_vma` carries anything below bit 28 --
        a real load address like `0x80100000` rather than a round synthetic
        one -- must not have those bits bled into the immediate. The
        hardware takes `(PC & 0xF0000000) | (imm << 2)`, so only the top
        nibble of the VMA belongs in the value.
        """

        surface = surface_for(
            synthetic_vma="0x80100000", image=shipped_image(jal_immediate=0x123)
        )
        value = surface.value_map()["callee"]
        self.assertEqual(value, 0x80000000 | (0x123 << 2))
        self.assertEqual(self.link_jump(value, 0x0), 0x123)
