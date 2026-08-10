"""Tests for opt-in ugen source instrumentation."""

from __future__ import annotations

import unittest

from decomp_workbench.instrument import MARKER, instrument_ugen

SOURCE = """\
#include "header.h"
static uint32_t f_alloc_reg(uint8_t *mem, uint32_t sp, uint32_t a0) {
return a0;
}
static void f_free_reg(uint8_t *mem, uint32_t sp, uint32_t a0) {
(void)mem;
}
static void helper(void) {
}
"""


class InstrumentTests(unittest.TestCase):
    def test_instruments_selected_functions_and_hooks(self) -> None:
        result = instrument_ugen(SOURCE)
        self.assertEqual(result.functions, 2)
        self.assertEqual(result.free_list_hooks, 2)
        self.assertIn(MARKER, result.source)
        self.assertIn('DKWB_TRACE_FRAME("f_alloc_reg");', result.source)
        self.assertIn('dkwb_freelist("ALLOC", a0, mem);', result.source)
        self.assertIn("emitted=%ld", result.source)
        self.assertIn("DKWB_IBUFFER_FORWARD_CURSOR", result.source)
        self.assertNotIn('DKWB_TRACE_FRAME("helper");', result.source)

    def test_filter_retains_free_list_hook(self) -> None:
        result = instrument_ugen(SOURCE, function_pattern=r"^f_free")
        self.assertEqual(result.functions, 1)
        self.assertEqual(result.free_list_hooks, 2)

    def test_refuses_double_instrumentation(self) -> None:
        once = instrument_ugen(SOURCE).source
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            instrument_ugen(once)


if __name__ == "__main__":
    unittest.main()
