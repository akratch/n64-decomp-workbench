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

# The recompiled fp allocator takes a request descriptor in a0 and returns the
# register it chose in v0; only a return-site hook can see the allocation.
FP_ALLOC_SOURCE = """\
#include "header.h"
static uint32_t f_get_free_fp_reg(uint8_t *mem, uint32_t sp, uint32_t a0, uint32_t a1, uint32_t a2) {
uint32_t v0 = 0, s0 = 0;
s0 = a0;
v0 = s0;
return v0;
}
static void f_free_reg(uint8_t *mem, uint32_t sp, uint32_t a0) {
(void)mem;
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

    def test_fp_allocator_records_returned_register(self) -> None:
        result = instrument_ugen(FP_ALLOC_SOURCE)
        self.assertEqual(result.result_hooks, 1)
        # The entry hook still stamps the request descriptor (a0)...
        self.assertIn('dkwb_freelist("ALLOC_FP", a0, mem);', result.source)
        # ...and a return-site hook now stamps the allocated register (v0),
        # placed immediately before the return so it fires on that exit.
        self.assertIn('dkwb_freelist("ALLOC_FP_RESULT", v0, mem);', result.source)
        result_index = result.source.index('dkwb_freelist("ALLOC_FP_RESULT", v0, mem);')
        return_index = result.source.index("return v0;")
        self.assertLess(result_index, return_index)

    def test_no_result_hook_without_the_named_function(self) -> None:
        # SOURCE defines f_alloc_reg/f_free_reg but not f_get_free_fp_reg, so
        # no result hook is injected and the request-side behavior is intact.
        result = instrument_ugen(SOURCE)
        self.assertEqual(result.result_hooks, 0)
        self.assertNotIn("ALLOC_FP_RESULT", result.source)


if __name__ == "__main__":
    unittest.main()
