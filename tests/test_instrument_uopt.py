"""Tests for guarded, profiled uopt instrumentation."""

from __future__ import annotations

import unittest

from decomp_workbench.instrument_uopt import (
    MARKER,
    instrument_uopt_globalcolor,
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
cf = f6.f[0] <= f20.f[0];
//nop;
if (!cf) {
}
L471d6c:
t5 = MEM_U32(sp + 220);
cf = f20.f[0] < f10.f[0];
//nop;
if (!cf) {
}
L4727d4:
t8 = MEM_U32(sp + 220);
}
"""


class UoptInstrumentationTests(unittest.TestCase):
    def test_refuses_unpinned_source_by_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            instrument_uopt_globalcolor(SOURCE)

    def test_instruments_all_profile_anchors(self) -> None:
        result = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        )
        self.assertIn(MARKER, result.source)
        self.assertIn("[CDX] p1dec", result.source)
        self.assertIn("[CDX] p2color", result.source)
        self.assertIn("CDX_FORCE", result.source)

    def test_refuses_double_instrumentation(self) -> None:
        once = instrument_uopt_globalcolor(
            SOURCE, allow_unverified_source=True
        ).source
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            instrument_uopt_globalcolor(
                once, allow_unverified_source=True
            )

    def test_refuses_partial_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "phase-two color"):
            instrument_uopt_globalcolor(
                SOURCE.replace("L4727d4:", "Lchanged:"),
                allow_unverified_source=True,
            )


if __name__ == "__main__":
    unittest.main()
