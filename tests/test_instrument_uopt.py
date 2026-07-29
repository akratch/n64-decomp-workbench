"""Tests for guarded, profiled uopt instrumentation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.globalcolor import COLOR_REGISTERS
from decomp_workbench.instrument_uopt import (
    HEADER,
    MARKER,
    ForceEntry,
    color_register_table,
    instrument_uopt_globalcolor,
    parse_force_specification,
)

SOURCE = """\
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
    (void)dkwb_cdx_reg_taken(dkwb_test_memory, 1);
    dkwb_cdx_log_interference(dkwb_test_memory, 0, 9, 0);
    DKWB_CDX_LOG(0, "%s\\n", dkwb_cdx_register_name(2));
    DKWB_CDX_COST(0, "p1", 9, 2, "caller", 1.0, 2.0);
    return 0;
}
"""


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

    def test_force_keys_are_phase_qualified(self) -> None:
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        self.assertIn('snprintf(key, sizeof(key), "%s:w%d=", phase, web)', source)
        self.assertEqual(source.count('dkwb_cdx_lookup(dkwb_cdx_ordinal, "p1"'), 2)
        self.assertEqual(source.count('dkwb_cdx_lookup(dkwb_cdx_ordinal, "p2"'), 2)
        self.assertIn("is not phase-qualified", source)
        self.assertIn("disjoint web spaces", source)
        self.assertIn("dkwb_cdx_validate_force", source)

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

    def test_generated_header_compiles(self) -> None:
        compiler = shutil.which("cc") or shutil.which("gcc")
        if compiler is None:
            self.skipTest("no host C compiler available")
        source = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        start = source.index("/* DKWB_UOPT_GLOBALCOLOR_V1")
        end = source.index("static void f_compute_save")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / "header.c"
            program.write_text(
                COMPILE_PRELUDE + source[start:end] + COMPILE_DRIVER,
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    compiler,
                    "-Wall",
                    "-Werror",
                    "-c",
                    str(program),
                    "-o",
                    str(root / "header.o"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_force_specification_rejects_unqualified_keys(self) -> None:
        self.assertEqual(
            parse_force_specification("p2:w55=c2,p1:w9=s"),
            [ForceEntry("p2", 55, 2), ForceEntry("p1", 9, None)],
        )
        self.assertEqual(str(ForceEntry("p2", 55, 2)), "p2:w55=c2")
        with self.assertRaisesRegex(ValueError, "not phase-qualified"):
            parse_force_specification("w55=c2")
        with self.assertRaisesRegex(ValueError, "disjoint web spaces"):
            parse_force_specification("p1:w9=c30,w55=c2")
        with self.assertRaisesRegex(ValueError, "empty"):
            parse_force_specification("  ")

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
