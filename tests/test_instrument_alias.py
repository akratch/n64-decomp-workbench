"""Tests for guarded alias-state instrumentation."""

from __future__ import annotations

import unittest

from decomp_workbench.instrument_alias import (
    MARKER,
    instrument_uopt_alias,
)


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
"""


class AliasInstrumentationTests(unittest.TestCase):
    def test_refuses_unpinned_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            instrument_uopt_alias(SOURCE)

    def test_instruments_base_and_decision(self) -> None:
        result = instrument_uopt_alias(
            SOURCE, allow_unverified_source=True
        )
        self.assertIn(MARKER, result.source)
        self.assertIn("DKWB-BASE", result.source)
        self.assertIn("DKWB-ALIAS-QUERY", result.source)
        self.assertIn("DKWB_UOPT_ALIAS_TRACE", result.source)

    def test_refuses_missing_anchor(self) -> None:
        with self.assertRaisesRegex(ValueError, "base-in-register"):
            instrument_uopt_alias(
                SOURCE.replace("t0 = a3 + t6;", "t0 = a3 + t7;"),
                allow_unverified_source=True,
            )


if __name__ == "__main__":
    unittest.main()
