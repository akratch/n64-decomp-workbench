"""Static Binasm boundary and IDO peephole evidence."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.binasm import (
    build_binasm_boundary_report,
    parse_binasm,
    parse_peepdbg,
)


def record(*words: int) -> bytes:
    return struct.pack(">IIII", *words)


class BinasmTests(unittest.TestCase):
    def test_known_records_are_named_without_losing_raw_words(self) -> None:
        data = b"".join(
            (
                record(0, 0x001C0000, 28, 85),
                record(0, 0x00200000, 8, 0),
                record(0, 0x001701AE, 0x060D0000, 0xFF),
                record(0xFFFFFFDB, 0, 0, 0),
            )
        )
        parsed = parse_binasm(data)
        self.assertEqual(
            [item.name for item in parsed],
            ["loc", "set-nomove", "andi", "local-label"],
        )
        self.assertEqual(parsed[2].words, (0, 0x001701AE, 0x060D0000, 0xFF))
        self.assertIn("width normalization", parsed[2].source_lever or "")

    def test_partial_record_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "multiple of 16"):
            parse_binasm(b"short")

    def test_peepdbg_pairs_replacement_with_removed_copy(self) -> None:
        events, unparsed = parse_peepdbg(
            ">>Repl_reg (INST 3) 3 with 2\n"
            ">>Repl_reg (INST 4) changed to NOP\n"
            ">>Peepreg (INST 5) changed rs 2 => 3\n"
        )
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].action, "register-replacement")
        self.assertEqual(events[1].action, "changed-to-nop")
        self.assertEqual(events[2].with_register, 3)
        self.assertEqual(unparsed, [])

    def test_report_keeps_downstream_probe_claim_separate_from_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unit.G"
            path.write_bytes(
                record(0, 0x00170062, 0x040D4000, 0)
                + record(0, 0x001701AE, 0x060D0000, 0xFF)
            )
            report = build_binasm_boundary_report(
                path,
                boundary=0x10,
                probe_results={
                    "results": [
                        {
                            "name": "identity-andi-v1-v1-ff-pre-add",
                            "exact": True,
                        },
                        {"name": "identity-sll-v1-v1-zero-pre-add", "exact": False},
                    ]
                },
            )
        probes = report["barrier_probes"]
        self.assertEqual(probes["exact_count"], 1)
        self.assertEqual(probes["site_counts"], {"pre-add": 1})
        self.assertIn("do not prove a C spelling", probes["strongest_claim"])
        self.assertEqual(report["boundary"]["after"]["name"], "andi")


if __name__ == "__main__":
    unittest.main()

