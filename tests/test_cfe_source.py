"""Synthetic event/stream fixtures; no compiler or game payloads."""

import unittest
from typing import Any

from phase_streams import urecord

from decomp_workbench.cfe_source import SOURCE_SHA256, _instrument, instrument
from decomp_workbench.cfe_source import join_trace as raw_join_trace


def join_trace(trace: str, ucode: bytes) -> dict[str, Any]:
    return raw_join_trace(
        f"DKWB-CFE profile=1 source_sha256={SOURCE_SHA256}\n" + trace, ucode
    )


def source_fixture() -> str:
    return (
        '#include "header.h"\n'
        + "".join(
            f"static void f_{name}(uint8_t *mem, uint32_t a0) {{\nreturn;\n}}\n"
            for name in ("load_var", "store_var", "load_addr")
        )
        + (
            "static uint64_t f_UWRITE(uint8_t *mem) {\n"
            "return ((uint64_t)v0 << 32) | v1;\n}\n"
        )
    )


def begin(seq: int = 1, offset: int = 0) -> str:
    return (
        f"DKWB-CFE begin={seq} op=load_var offset={offset} decl=100 "
        "raw36=-32 raw44=1 raw60=3 namehex=76616c7565 truncated=0\n"
    )


class InstrumentTests(unittest.TestCase):
    def test_profile_rejects_unrecognized_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            instrument(source_fixture())

    def test_structural_hooks(self) -> None:
        result = _instrument(source_fixture())
        self.assertEqual(result.count("dkwb_cfe_end(mem,dkwb_cfe_id);"), 3)
        self.assertEqual(result.count("dkwb_cfe_write(v0);"), 1)

    def test_missing_and_duplicate_function_anchors(self) -> None:
        for source in (
            source_fixture().replace("f_load_var", "f_other"),
            source_fixture() + "static void f_load_var(void) {\nreturn;\n}\n",
            source_fixture().replace("return;", "", 1),
            source_fixture().replace('"header.h"', '"other.h"'),
            source_fixture() + '#include "header.h"\n',
            source_fixture().replace("return ((uint64_t)v0 << 32) | v1;", ""),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                _instrument(source)

    def test_double_instrumentation_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "already"):
            _instrument(_instrument(source_fixture()))


class JoinTests(unittest.TestCase):
    stream = urecord("nop") + urecord("ret")

    def test_missing_or_duplicate_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "profile"):
            raw_join_trace("DKWB-CFE written=16\n", self.stream)
        with self.assertRaisesRegex(ValueError, "profile"):
            join_trace(
                f"DKWB-CFE profile=1 source_sha256={SOURCE_SHA256}\n", self.stream
            )

    def test_exact_intervals_and_raw_fields(self) -> None:
        report = join_trace(
            begin() + "DKWB-CFE end=1 offset=8\nDKWB-CFE written=16\n", self.stream
        )
        self.assertEqual(report["events"][0]["record_indices"], [0])
        self.assertEqual(report["events"][0]["raw_fields"]["raw36"], -32)
        self.assertFalse(report["final_home_proof"])
        self.assertFalse(report["fidelity_proof"])

    def test_nested_emissions_preserve_parent(self) -> None:
        report = join_trace(
            begin() + begin(2) + "DKWB-CFE end=2 offset=8\n"
            "DKWB-CFE end=1 offset=16\nDKWB-CFE written=16\n",
            self.stream,
        )
        self.assertEqual(report["events"][1]["parent"], 1)

    def test_same_name_not_merged(self) -> None:
        report = join_trace(
            begin()
            + "DKWB-CFE end=1 offset=8\n"
            + begin(2, 8)
            + "DKWB-CFE end=2 offset=16\nDKWB-CFE written=16\n",
            self.stream,
        )
        self.assertEqual(len(report["events"]), 2)

    def test_partial_duplicate_unbalanced_and_bad_boundaries(self) -> None:
        bad = [
            begin(),
            begin() + "DKWB-CFE written=16\n",
            begin() + "DKWB-CFE end=2 offset=8\nDKWB-CFE written=16\n",
            begin() + "DKWB-CFE end=1 offset=4\nDKWB-CFE written=16\n",
            begin(1, 4) + "DKWB-CFE end=1 offset=8\nDKWB-CFE written=16\n",
            begin() + begin() + "DKWB-CFE written=16\n",
            "DKWB-CFE written=8\nDKWB-CFE written=4\n",
            "DKWB-CFE written=20\n",
            "DKWB-CFE end=1 offset=0\n",
            "DKWB-CFE unknown=0\n",
            "DKWB-CFE written=16 written=16\n",
            "DKWB-CFE written=16 junk\n",
        ]
        for trace in bad:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                join_trace(trace, self.stream)

    def test_write_flushes_and_unrelated_diagnostics(self) -> None:
        report = join_trace(
            "diagnostic\n" + begin() + "DKWB-CFE written=8\n"
            "DKWB-CFE end=1 offset=16\nDKWB-CFE written=16\n",
            self.stream,
        )
        self.assertEqual(report["events"][0]["record_indices"], [0, 1])

    def test_missing_name_is_explicit(self) -> None:
        report = join_trace(
            "DKWB-CFE begin=1 op=load_addr offset=0 decl=0\n"
            "DKWB-CFE end=1 offset=8\nDKWB-CFE written=16\n",
            self.stream,
        )
        self.assertNotIn("name_bytes_hex", report["events"][0])


if __name__ == "__main__":
    unittest.main()
