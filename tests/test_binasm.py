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

    def test_a_stream_is_read_from_bytes_or_from_a_path(self) -> None:
        data = record(0, 0x001C0000, 28, 85)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unit.G"
            path.write_bytes(data)
            from_path = parse_binasm(path)
            from_text_path = parse_binasm(str(path))
        self.assertEqual(
            [item.words for item in from_path],
            [item.words for item in parse_binasm(data)],
        )
        self.assertEqual(from_text_path[0].name, "loc")

    def test_both_label_definition_shapes_are_named(self) -> None:
        """ugen mints negative local labels; as0 emits positive symbol ones.

        The decoder used to recognize only the negative half of one record
        family, so every label in an as0-produced stream read as "unknown".
        """

        parsed = parse_binasm(record(0xFFFFFFDB, 0, 0, 0) + record(3, 0, 0, 0))
        self.assertEqual(
            [(item.name, item.detail) for item in parsed],
            [
                ("local-label", "local label $37"),
                ("symbol-label", "label definition for symbol index 3"),
            ],
        )

    def test_a_case_table_entry_names_its_target_label(self) -> None:
        parsed = parse_binasm(
            record(0, 0x001A0000, 0, 0)
            + record(0xFFFFFFDD, 0, 0, 0)
            + record(0xFFFFFF9D, 0x00160000, 0, 1)
            + record(0, 0x00150000, 0, 0)
        )
        self.assertEqual(
            [item.name for item in parsed],
            ["section-switch", "local-label", "table-entry", "text"],
        )
        self.assertEqual(parsed[2].kind, "jump-table")
        self.assertEqual(parsed[2].detail, "case target $99")

    def test_a_float_literal_frames_its_ascii_digits_as_payload(self) -> None:
        """Word 3 is a byte length, and the digits that follow are not words.

        A decoder that walks 16 bytes at a time and classifies on word 1 reads
        b"00e-05          " as a record family, which is how the ad hoc
        classifier invented opcodes such as 0x30320000.
        """

        parsed = parse_binasm(
            record(0, 0x001701F8, 0x5D208000, 22)
            + b"3.05175781250000"
            + b"00e-05          "
            + record(0, 0x001C0000, 28, 86)
        )
        self.assertEqual(
            [item.name for item in parsed],
            ["float-literal", "ascii-payload", "ascii-payload", "loc"],
        )
        self.assertIn("2 payload record(s)", parsed[0].detail)
        self.assertEqual(parsed[2].detail, "ASCII literal digits '00e-05'")

    def test_an_observed_family_is_marked_inferred_not_calibrated(self) -> None:
        parsed = parse_binasm(
            record(0, 0x00150000, 0, 0)
            + record(0, 0x00350000, 0x0C00000E, 0)
            + record(1, 0x00FF0000, 0, 0)
        )
        self.assertEqual(
            [item.evidence for item in parsed], ["calibrated", "inferred", "none"]
        )
        self.assertEqual(parsed[2].kind, "unknown")

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
