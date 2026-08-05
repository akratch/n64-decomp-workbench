"""Tests for guarded, profiled uopt instrumentation."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.globalcolor import COLOR_REGISTERS, color_is_forbidden
from decomp_workbench.instrument_uopt import (
    HEADER,
    MARKER,
    ForceEntry,
    color_register_table,
    instrument_uopt_globalcolor,
    parse_force_specification,
)

SOURCE = (
    "static void f_formlivbb(uint8_t *mem, uint32_t sp, uint32_t a0, "
    "uint32_t a1, uint32_t a2) {\n"
    """\
uint32_t zero = 0;
uint32_t v0 = 0, s0 = a0, s1 = a2;
MEM_U32(sp + 92) = a1;
MEM_U32(v0 + 52) = zero;
MEM_U32(v0 + 56) = zero;
goto L464644;
L464644:
L4647b8:
// bdead 1 ra = MEM_U32(sp + 36);
}
static void f_makelivranges(uint8_t *mem, uint32_t sp) {
L468998:
//makelivranges:
}
static void f_compute_save(uint8_t *mem, uint32_t sp, uint32_t a0) {
}
static void f_globalcolor(uint8_t *mem, uint32_t sp) {
uint32_t a3 = 0;
L47106c:
//globalcolor:
L471758:
s5 = MEM_U32(sp + 276);
//nop;
f0.w[0] = MEM_U32(s5 + 48);
L47190c:
cf = f2.f[0] < f20.f[0];
L471afc:
cf = f2.f[0] < f20.f[0];
cf = f6.f[0] <= f20.f[0];
//nop;
if (!cf) {
}
L471d6c:
t5 = MEM_U32(sp + 220);
L4723a4:
cf = f2.f[0] < f20.f[0];
L4725b0:
cf = f2.f[0] < f20.f[0];
cf = f20.f[0] < f10.f[0];
//nop;
if (!cf) {
}
L4727d4:
t8 = MEM_U32(sp + 220);
}
"""
)


# The emulated-memory accessors and a driver, so the injected header can be
# compiled on its own. Building the whole recompiled pass needs the external
# research toolchain; this proves the generated C at least compiles cleanly.
COMPILE_PRELUDE = """\
#include <stdint.h>
static uint8_t dkwb_test_memory[64];
#define MEM_U32(address) (*(uint32_t *)dkwb_test_memory)
#define MEM_U16(address) (*(uint16_t *)dkwb_test_memory)
#define MEM_U8(address) (*(uint8_t *)dkwb_test_memory)
"""

COMPILE_DRIVER = """\
int main(void) {
    dkwb_cdx_init();
    dkwb_cdx_procindex();
    dkwb_cdx_finish();
    (void)dkwb_cdx_active(0);
    (void)dkwb_cdx_lookup(0, "p1", 9);
    (void)dkwb_cdx_lookup(0, "p2", 9);
    (void)dkwb_cdx_force_color(0, "p1", "dec", 9, 0, 0);
    (void)dkwb_cdx_reg_taken(dkwb_test_memory, 1);
    dkwb_cdx_lineage_begin();
    dkwb_cdx_log_lineage_range(dkwb_test_memory, 0, 0);
    dkwb_cdx_log_lineage_member(dkwb_test_memory, 0, 0, 0);
    dkwb_cdx_log_interference(dkwb_test_memory, 0, "p1", 9, 0);
    DKWB_CDX_LOG(0, "%s\\n", dkwb_cdx_register_name(2));
    DKWB_CDX_COST(0, "p1", 9, 2, "caller", 1.0, 2.0);
    return 0;
}
"""

# A driver for the force path: it prints what the pass would do with the
# CDX_FORCE in the environment against the interference mask given on the
# command line. -2 is "no override", -1 is "force the split path", and a
# non-negative value is the color the pass will install.
FORCE_DRIVER = """\
int main(int argc, char **argv) {
    uint32_t forbidden0 = (uint32_t)strtoul(argv[1], 0, 0);
    uint32_t forbidden1 = (uint32_t)strtoul(argv[2], 0, 0);
    int web = (int)strtol(argv[3], 0, 0);
    (void)argc;
    dkwb_cdx_init();
    printf("force=%d\\n",
        dkwb_cdx_force_color(0, "p1", "dec", web, forbidden0, forbidden1));
    (void)dkwb_cdx_active(0);
    (void)dkwb_cdx_lookup(0, "p2", 9);
    (void)dkwb_cdx_reg_taken(dkwb_test_memory, 1);
    dkwb_cdx_lineage_begin();
    dkwb_cdx_log_lineage_range(dkwb_test_memory, 0, 0);
    dkwb_cdx_log_lineage_member(dkwb_test_memory, 0, 0, 0);
    dkwb_cdx_log_interference(dkwb_test_memory, 0, "p1", 9, 0);
    DKWB_CDX_LOG(0, "%s\\n", dkwb_cdx_register_name(2));
    DKWB_CDX_COST(0, "p1", 9, 2, "caller", 1.0, 2.0);
    dkwb_cdx_procindex();
    dkwb_cdx_finish();
    return 0;
}
"""

# One decode ring, two implementations. forbidden0=0x7f800000 meaning exactly
# c1-c8 is the recorded observation this table is anchored on; a workbench that
# read the mask differently from the pass would predict the wrong endpoints and
# send a campaign after probes that cannot run.
FORBIDDEN_MASKS: tuple[tuple[int, int, int, bool], ...] = (
    (0x7F800000, 0, 1, True),
    (0x7F800000, 0, 8, True),
    (0x7F800000, 0, 9, False),
    (0x7F800000, 0, 0, False),
    (0x00000000, 0, 2, False),
    (0x80000000, 0, 0, True),
    (0x20000000, 0, 2, True),
    (0x20000000, 0, 3, False),
    (0x00000001, 0, 31, True),
    (0x00000001, 0, 30, False),
    (0x08CBBF00, 0, 4, True),
    (0x08CBBF00, 0, 5, False),
    (0, 0x80000000, 32, True),
    (0, 0x80000000, 33, False),
    (0, 0x00000001, 63, True),
    (0xFFFFFFFF, 0xFFFFFFFF, 23, True),
)

# One table, two validators. The workbench refuses a malformed force control
# before a campaign spends a compile on it, and the instrumented pass refuses
# it again at the point of use. A control the pass would silently ignore is
# exactly the defect that produced a false exoneration in the field, so the
# two must agree entry for entry.
FORCE_SPECIFICATIONS: tuple[tuple[str, bool], ...] = (
    ("p1:w9=c30", True),
    ("p2:w55=c2", True),
    ("p1:w9=s", True),
    ("p2:w0=c0", True),
    ("p1:w9=c30,p2:w55=c2", True),
    ("p1:w123=c7,p1:w4=s,p2:w9=c1", True),
    # Unqualified: the recorded trap.
    ("w55=c2", False),
    ("w9=s", False),
    ("p1:w9=c30,w55=c2", False),
    # Partially formed keys the pass would otherwise treat as "no force".
    ("p1:w9", False),
    ("p1:w9=", False),
    ("p1:wgarbage=c2", False),
    ("p1:w9=zzz", False),
    ("p1:w9=c", False),
    ("p1:w9=cx", False),
    ("p1:w9=c30x", False),
    ("p1:w9=sx", False),
    ("p3:w9=c30", False),
    ("p1w9=c30", False),
    ("P1:W9=C30", False),
    ("p1:w-1=c30", False),
    # Empty and whitespace entries must not be silently skipped.
    ("", False),
    (",", False),
    ("p1:w9=c30,", False),
    (",p1:w9=c30", False),
    ("p1:w9=c30,,p2:w1=s", False),
    (" p1:w9=c30", False),
    ("p1:w9=c30 ", False),
    # Longer than the pass's per-entry buffer.
    ("p1:w9=c" + "3" * 60, False),
)


class UoptInstrumentationTests(unittest.TestCase):
    def test_refuses_unpinned_source_by_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            instrument_uopt_globalcolor(SOURCE)

    def test_instruments_all_profile_anchors(self) -> None:
        result = instrument_uopt_globalcolor(SOURCE, allow_unverified_source=True)
        self.assertIn(MARKER, result.source)
        self.assertIn("[CDX] p1dec", result.source)
        self.assertIn("[CDX] p2color", result.source)
        self.assertIn("[CDX] intf", result.source)
        self.assertIn("[CDX] webdetail", result.source)
        self.assertIn("[CDX] %scost", result.source)
        self.assertIn('"p1", (int)MEM_U32(sp + 268)', result.source)
        self.assertIn('"p2", (int)MEM_U32(sp + 272)', result.source)
        self.assertIn("dkwb_cdx_emulated_pointer", result.source)
        self.assertIn("CDX_DETAIL_WEB", result.source)
        self.assertIn("CDX_LINEAGE_TABLES", result.source)
        self.assertIn("[CDX] lineage_range", result.source)
        self.assertIn("[CDX] lineage_member", result.source)
        self.assertEqual(result.trace_points, 13)
        self.assertIn('strcmp(value, "all")', result.source)
        self.assertIn("forbidden0=0x%08x forbidden1=0x%08x", result.source)
        self.assertIn("available0=0x%08x available1=0x%08x", result.source)
        self.assertIn("allcallersave=%d taken1=%d taken2=%d", result.source)
        self.assertIn("dkwb_cdx_reg_taken(mem, 2)", result.source)
        self.assertIn("MEM_U8(s5 + 33)", result.source)
        self.assertIn("CDX_FORCE", result.source)
        self.assertIn("CDX_FORCE ignored without CDX_PROC", result.source)
        self.assertEqual(
            result.source.count("dkwb_web = (int)MEM_U32(sp + 268)"),
            2,
        )
        self.assertEqual(
            result.source.count("dkwb_web = (int)MEM_U32(sp + 272)"),
            2,
        )

    def test_records_carry_their_allocator_phase(self) -> None:
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        for record in ("p1cand", "p1dec", "p1color"):
            self.assertIn(f"[CDX] {record} phase=p1", source)
        for record in ("p2dec", "p2color"):
            self.assertIn(f"[CDX] {record} phase=p2", source)
        self.assertIn('"[CDX] %scost phase=%s', source)
        self.assertIn('"[CDX] webdetail phase=%s', source)
        self.assertIn('"[CDX] intf phase=%s', source)
        self.assertIn(
            'dkwb_cdx_log_interference(mem, dkwb_cdx_ordinal, "p1"',
            source,
        )
        self.assertIn(
            'dkwb_cdx_log_interference(mem, dkwb_cdx_ordinal, "p2"',
            source,
        )

    def test_force_keys_are_phase_qualified(self) -> None:
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        self.assertIn('snprintf(key, sizeof(key), "%s:w%d=", phase, web)', source)
        # Both force sites of each phase go through the decline wrapper, which
        # is the only caller of the raw lookup.
        self.assertEqual(source.count('dkwb_cdx_force_color(dkwb_cdx_ordinal, "p1"'), 2)
        self.assertEqual(source.count('dkwb_cdx_force_color(dkwb_cdx_ordinal, "p2"'), 2)
        self.assertEqual(source.count("dkwb_cdx_lookup(ordinal, phase, web)"), 1)
        self.assertIn("is not a phase-qualified force ", source)
        self.assertIn("disjoint ", source)
        self.assertIn("web spaces", source)
        self.assertIn("dkwb_cdx_validate_force", source)
        self.assertIn("dkwb_cdx_force_entry_ok", source)

    def test_colors_are_decoded_to_registers_in_output(self) -> None:
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        self.assertIn("bestcolor=%d bestreg=%s", source)
        self.assertIn("color=%d reg=%s forced=%d", source)
        self.assertIn("color=%d reg=%s kind=%s", source)
        self.assertIn("dkwb_cdx_register_name((int)MEM_U32(sp + 220))", source)

    def test_color_table_is_generated_from_one_mapping(self) -> None:
        table = color_register_table()
        self.assertIn(f"#define DKWB_CDX_MAX_COLOR {max(COLOR_REGISTERS)}", table)
        for color, register in COLOR_REGISTERS.items():
            with self.subTest(color=color):
                self.assertIn(f'"{register}"', table)
        # Colors the profile has not confirmed stay numeric rather than being
        # guessed: color 13 sits between t5 and s0 with no recorded register.
        self.assertNotIn(13, COLOR_REGISTERS)
        self.assertIn('"t5", 0, "s0"', table)
        self.assertIn("DKWB_CDX_COLOR_TABLE", HEADER)
        self.assertNotIn(
            "DKWB_CDX_COLOR_TABLE",
            instrument_uopt_globalcolor(SOURCE, allow_unverified_source=True).source,
        )

    def test_symbol_named_procedure_is_refused_with_an_index_table(self) -> None:
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        self.assertIn("strtol(value, &end, 10)", source)
        self.assertIn("is a symbol name", source)
        self.assertIn("[CDX] procindex proc=%d decisions=%d", source)
        self.assertIn("dkwb_cdx_proc_decisions++", source)
        self.assertIn("atexit(dkwb_cdx_finish)", source)

    def build_header_program(self, root: Path, driver: str = COMPILE_DRIVER) -> Path:
        """Compile the injected header on its own and return the binary."""

        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("no host C compiler available")
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        start = source.index("/* DKWB_UOPT_GLOBALCOLOR_V1")
        end = source.index("static void f_compute_save")
        program = root / "header.c"
        program.write_text(
            COMPILE_PRELUDE + source[start:end] + driver,
            encoding="utf-8",
        )
        binary = root / "header"
        completed = subprocess.run(
            [compiler, "-Wall", "-Werror", str(program), "-o", str(binary)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return binary

    def test_generated_header_compiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(self.build_header_program(Path(temp)).is_file())

    def test_force_specification_parses_accepted_controls(self) -> None:
        self.assertEqual(
            parse_force_specification("p2:w55=c2,p1:w9=s"),
            [ForceEntry("p2", 55, 2), ForceEntry("p1", 9, None)],
        )
        self.assertEqual(str(ForceEntry("p2", 55, 2)), "p2:w55=c2")
        self.assertEqual(str(ForceEntry("p1", 9, None)), "p1:w9=s")
        with self.assertRaisesRegex(ValueError, "phase-qualified"):
            parse_force_specification("w55=c2")
        with self.assertRaisesRegex(ValueError, "disjoint web spaces"):
            parse_force_specification("p1:w9=c30,w55=c2")
        with self.assertRaisesRegex(ValueError, "empty"):
            parse_force_specification("")

    def test_workbench_force_validation_matches_the_table(self) -> None:
        for specification, accepted in FORCE_SPECIFICATIONS:
            with self.subTest(specification=specification):
                if accepted:
                    self.assertTrue(parse_force_specification(specification))
                else:
                    with self.assertRaises(ValueError):
                        parse_force_specification(specification)

    def test_generated_pass_force_validation_matches_the_workbench(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            binary = self.build_header_program(Path(temp))
            for specification, accepted in FORCE_SPECIFICATIONS:
                if not specification:
                    # An unset CDX_FORCE is not a malformed one; the pass
                    # simply has no controls to apply.
                    continue
                with self.subTest(specification=specification):
                    completed = subprocess.run(
                        [str(binary)],
                        check=False,
                        capture_output=True,
                        text=True,
                        env={
                            "CDX_FORCE": specification,
                            "CDX_PROC": "0",
                            "PATH": os.environ.get("PATH", ""),
                        },
                    )
                    if accepted:
                        self.assertEqual(completed.returncode, 0, completed.stderr)
                    else:
                        self.assertEqual(completed.returncode, 2, completed.stdout)
                        self.assertIn("phase-qualified", completed.stderr)

    def test_a_forbidden_force_is_declined_at_every_force_site(self) -> None:
        """The four sites that honor a force all go through the decline."""

        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        self.assertIn("[CDX] force_declined phase=%s site=%s", source)
        self.assertIn("dkwb_cdx_color_forbidden", source)
        for phase, site in (
            ("p1", "dec"),
            ("p1", "color"),
            ("p2", "dec"),
            ("p2", "color"),
        ):
            with self.subTest(phase=phase, site=site):
                self.assertIn(
                    f'dkwb_cdx_force_color(dkwb_cdx_ordinal, "{phase}", "{site}"',
                    source,
                )
        # Every force site reads the web's own mask, and the raw lookup is no
        # longer reachable from one: an undeclined path would still abort.
        self.assertEqual(source.count("MEM_U32(s5 + 40), MEM_U32(s5 + 44));"), 4)
        self.assertEqual(source.count("dkwb_cdx_lookup(dkwb_cdx_ordinal,"), 0)

    def test_the_workbench_and_the_pass_decode_one_mask(self) -> None:
        for forbidden0, forbidden1, color, forbidden in FORBIDDEN_MASKS:
            with self.subTest(mask=(hex(forbidden0), hex(forbidden1)), color=color):
                self.assertEqual(
                    color_is_forbidden(forbidden0, forbidden1, color), forbidden
                )

    def test_the_generated_pass_declines_the_colors_the_workbench_names(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            binary = self.build_header_program(Path(temp), FORCE_DRIVER)
            for forbidden0, forbidden1, color, forbidden in FORBIDDEN_MASKS:
                with self.subTest(mask=hex(forbidden0), color=color):
                    completed = subprocess.run(
                        [str(binary), hex(forbidden0), hex(forbidden1), "9"],
                        check=False,
                        capture_output=True,
                        text=True,
                        env={
                            "CDX_FORCE": f"p1:w9=c{color}",
                            "CDX_PROC": "0",
                            "PATH": os.environ.get("PATH", ""),
                        },
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    if forbidden:
                        # -2 is "no override": the natural coloring stands.
                        self.assertIn("force=-2", completed.stdout)
                        self.assertIn("[CDX] force_declined", completed.stderr)
                        self.assertIn(f"color={color}", completed.stderr)
                        self.assertIn(
                            f"forbidden=0x{forbidden0:08x}{forbidden1:08x}",
                            completed.stderr,
                        )
                    else:
                        self.assertIn(f"force={color}", completed.stdout)
                        self.assertNotIn("force_declined", completed.stderr)

    def test_a_decline_is_recorded_even_with_tracing_off(self) -> None:
        """A silent no-op is exactly what the record exists to prevent."""

        with tempfile.TemporaryDirectory() as temp:
            binary = self.build_header_program(Path(temp), FORCE_DRIVER)
            completed = subprocess.run(
                [str(binary), "0x20000000", "0x0", "9"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    "CDX_FORCE": "p1:w9=c2",
                    "CDX_PROC": "0",
                    "PATH": os.environ.get("PATH", ""),
                },
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # CDX_LOG is unset, so nothing else printed; the decline still did.
        self.assertIn(
            "[CDX] force_declined phase=p1 site=dec proc=0 web=9", completed.stderr
        )
        self.assertIn("reg=v1", completed.stderr)
        self.assertNotIn("[CDX] p1cost", completed.stderr)

    def test_the_split_force_is_never_declined(self) -> None:
        """`s` asks for the split path, which no color mask can forbid."""

        with tempfile.TemporaryDirectory() as temp:
            binary = self.build_header_program(Path(temp), FORCE_DRIVER)
            completed = subprocess.run(
                [str(binary), "0xffffffff", "0xffffffff", "9"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    "CDX_FORCE": "p1:w9=s",
                    "CDX_PROC": "0",
                    "PATH": os.environ.get("PATH", ""),
                },
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("force=-1", completed.stdout)
        self.assertNotIn("force_declined", completed.stderr)

    def test_refuses_double_instrumentation(self) -> None:
        once = instrument_uopt_globalcolor(SOURCE, allow_unverified_source=True).source
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            instrument_uopt_globalcolor(once, allow_unverified_source=True)

    def test_refuses_partial_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "phase-two color"):
            instrument_uopt_globalcolor(
                SOURCE.replace("L4727d4:", "Lchanged:"),
                allow_unverified_source=True,
            )


if __name__ == "__main__":
    unittest.main()
