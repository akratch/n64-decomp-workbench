"""Tests for composing guarded uopt instrumentation profiles."""

from __future__ import annotations

import unittest

from decomp_workbench.instrument_alias import MARKER as ALIAS_MARKER
from decomp_workbench.instrument_profiles import instrument_uopt_profiles
from decomp_workbench.instrument_uopt import MARKER as GLOBALCOLOR_MARKER

SOURCE = """\
#include "header.h"
static uint32_t f_base_noalias(void) {
L420e28:
// bdead 21 ra = MEM_U32(sp + 36);
// bdead 21 sp = sp + 0x28;
v0 = a0 < 0x1;
}
static void f_base_in_reg(void) {
t0 = a3 + t6;
v0 = MEM_U32(t0 + 0);
// fdead 400083eb MEM_U32(sp + 44) = s6;
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


class InstrumentProfilesTests(unittest.TestCase):
    def test_combines_profiles_in_stable_order(self) -> None:
        result = instrument_uopt_profiles(
            SOURCE,
            ["globalcolor", "alias", "globalcolor"],
            allow_unverified_source=True,
        )
        self.assertEqual(result.profiles, ("alias", "globalcolor"))
        self.assertEqual(result.trace_points, 12)
        self.assertIn(ALIAS_MARKER, result.source)
        self.assertIn(GLOBALCOLOR_MARKER, result.source)

    def test_rejects_unknown_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown uopt"):
            instrument_uopt_profiles(SOURCE, ["other"], allow_unverified_source=True)


if __name__ == "__main__":
    unittest.main()
