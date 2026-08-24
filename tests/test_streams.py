"""Record-level windows, diffs, and surgery on synthesized phase streams."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from phase_streams import binasm_stream, ucode_stream, urecord

from decomp_workbench.cli import main
from decomp_workbench.streams import (
    allocate_fresh_labels,
    decode_stream,
    detect_format,
    diff_streams,
    max_label,
    parse_record_spec,
    patch_stream,
    stream_window,
)
from decomp_workbench.ucode import parse_ucode


class FormatDetectionTests(unittest.TestCase):
    def test_each_stream_is_detected_from_its_own_framing(self) -> None:
        self.assertEqual(detect_format(ucode_stream()), "ucode")
        self.assertEqual(detect_format(binasm_stream()), "binasm")

    def test_an_empty_or_ragged_stream_says_why(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            detect_format(b"")
        with self.assertRaisesRegex(ValueError, "32-bit words"):
            detect_format(b"\x00\x00\x00")

    def test_a_decoder_accepts_bytes_and_paths_alike(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unit.U"
            path.write_bytes(ucode_stream())
            from_path = decode_stream(path)
            from_bytes = decode_stream(ucode_stream())
            records = parse_ucode(path)
            text_path_records = parse_ucode(str(path))
        self.assertEqual(from_path[2], from_bytes[2])
        self.assertEqual(records, parse_ucode(ucode_stream()))
        self.assertEqual(text_path_records[0].name, "lab")


class WindowTests(unittest.TestCase):
    def test_a_record_index_and_its_byte_offset_select_the_same_record(
        self,
    ) -> None:
        by_index = stream_window(ucode_stream(), at="#2", radius=1)
        by_offset = stream_window(ucode_stream(), at="0x18", radius=1)
        self.assertEqual(by_index["position"], by_offset["position"])
        self.assertEqual(by_index["position"]["record_index"], 2)
        centre = next(item for item in by_index["records"] if item["at_position"])
        self.assertEqual(centre["name"], "Uujp")
        self.assertEqual(centre["detail"], "target=L5")

    def test_an_offset_inside_a_record_names_the_nearest_boundaries(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a record boundary"):
            stream_window(ucode_stream(), at="0x14")

    def test_the_window_reads_a_binasm_stream_the_same_way(self) -> None:
        report = stream_window(binasm_stream(), at="#4", radius=1)
        self.assertEqual(report["format"], "binasm")
        centre = next(item for item in report["records"] if item["at_position"])
        self.assertEqual(centre["name"], "local-label")


class FreshLabelTests(unittest.TestCase):
    def test_a_fresh_label_is_above_every_label_the_stream_uses(self) -> None:
        _format, _data, records = decode_stream(ucode_stream())
        self.assertEqual(max_label(records, stream_format="ucode"), 5)
        self.assertEqual(
            allocate_fresh_labels(records, 2, stream_format="ucode"), (6, 7)
        )

    def test_a_spec_using_more_fresh_slots_than_allocated_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, r"only 1 fresh label"):
            parse_record_spec("0x1,{fresh+3}", fresh_labels=(6,))


class PatchTests(unittest.TestCase):
    def test_insert_then_decode_round_trips_the_new_records(self) -> None:
        stream = ucode_stream()
        _format, _data, before = decode_stream(stream)
        spec = "0x26660000,{fresh} | 0x42600000,{fresh},0,2"
        patched, report = patch_stream(
            stream,
            insert_at="#2",
            records_spec=spec,
            fresh_label_count=1,
        )
        self.assertEqual(report["fresh_labels"], [6])
        self.assertTrue(report["result"]["decodes"])
        self.assertEqual(report["result"]["record_delta"], 2)
        _format, _data, after = decode_stream(patched)
        self.assertEqual(len(after), len(before) + 2)
        self.assertEqual([record.name for record in after[2:4]], ["Ufjp", "Ulab"])
        self.assertEqual(after[2].detail, "target=L6")
        self.assertEqual(after[3].detail, "label=L6")
        # The records that surrounded the insertion point are untouched.
        self.assertEqual(after[1].words, before[1].words)
        self.assertEqual(after[4].words, before[2].words)

    def test_a_spec_may_come_from_a_file_with_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            spec = Path(temporary) / "barrier.hex"
            spec.write_text(
                "# a conditional branch to the very next label\n"
                "0x26660000 {fresh}\n"
                "\n"
                "0x42600000 {fresh} 0 2\n",
                encoding="utf-8",
            )
            _patched, report = patch_stream(
                ucode_stream(),
                insert_at="#2",
                records_spec=str(spec),
                fresh_label_count=1,
            )
        self.assertEqual(report["inserted"]["bytes"], 24)
        self.assertEqual(
            [item["name"] for item in report["inserted"]["records"]],
            ["Ufjp", "Ulab"],
        )

    def test_a_spec_whose_groups_do_not_match_the_framing_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "do not match decoded record"):
            patch_stream(
                ucode_stream(),
                insert_at="#2",
                # Ulab is a four-word record; splitting it in two is a lie
                # about the framing even though the bytes are identical.
                records_spec="0x42600000,7 | 0,2",
            )

    def test_a_patch_that_breaks_framing_is_refused_by_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not decode"):
            patch_stream(
                ucode_stream(),
                insert_at="#1",
                records_spec="0xff000000,0",
            )

    def test_delete_and_replace_keep_the_stream_decodable(self) -> None:
        stream = ucode_stream()
        deleted, delete_report = patch_stream(stream, delete="1")
        self.assertEqual(delete_report["result"]["record_delta"], -1)
        self.assertEqual(len(deleted), len(stream) - 8)

        replaced, replace_report = patch_stream(
            stream,
            replace="1",
            records_spec="0x7f660000,5",
        )
        self.assertEqual(replace_report["result"]["record_delta"], 0)
        _format, _data, records = decode_stream(replaced)
        self.assertEqual(records[1].name, "Utjp")

    def test_exactly_one_operation_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one of"):
            patch_stream(ucode_stream(), records_spec="0x0,0")
        with self.assertRaisesRegex(ValueError, "exactly one of"):
            patch_stream(ucode_stream(), insert_at="#0", delete="1")


class DiffTests(unittest.TestCase):
    def test_identical_streams_report_no_divergence(self) -> None:
        report = diff_streams(ucode_stream(), ucode_stream())
        self.assertTrue(report["identical"])
        self.assertIsNone(report["first_divergence"])
        self.assertEqual(report["opcode_counts"]["equal"], 5)

    def test_one_inserted_record_is_one_inserted_row(self) -> None:
        patched, _report = patch_stream(
            ucode_stream(),
            insert_at="#2",
            records_spec="0x7f660000,5",
        )
        report = diff_streams(ucode_stream(), patched)
        self.assertFalse(report["identical"])
        self.assertEqual(report["opcode_counts"]["insert"], 1)
        self.assertEqual(report["opcode_counts"]["replace"], 0)
        self.assertEqual(report["opcode_counts"]["equal"], 5)
        divergence = report["first_divergence"]
        self.assertEqual(divergence["tag"], "insert")
        self.assertEqual(divergence["right"]["name"], "Utjp")
        self.assertEqual(divergence["left_index"], 2)

    def test_a_changed_record_is_reported_as_a_replacement(self) -> None:
        changed = ucode_stream().replace(urecord("nop"), urecord("ret"))
        report = diff_streams(ucode_stream(), changed)
        self.assertEqual(report["opcode_counts"]["replace"], 1)
        self.assertEqual(report["first_divergence"]["left"]["name"], "Unop")
        self.assertEqual(report["first_divergence"]["right"]["name"], "Uret")

    def test_binasm_streams_diff_by_record_too(self) -> None:
        left = binasm_stream()
        right = left[:0x30] + left[0x40:]
        report = diff_streams(left, right)
        self.assertEqual(report["format"], "binasm")
        self.assertEqual(report["opcode_counts"]["delete"], 1)

    def test_streams_of_different_formats_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "different formats"):
            diff_streams(ucode_stream(), binasm_stream())


class StreamCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_grouped_and_flat_spellings_agree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unit.U"
            path.write_bytes(ucode_stream())
            grouped = self.run_cli(["ucode", "window", str(path), "--at", "#2"])
            flat = self.run_cli(["ucode-window", str(path), "--at", "#2"])
        self.assertEqual(grouped, flat)
        self.assertEqual(grouped[0], 0)
        self.assertIn("Uujp", grouped[1])

    def test_patch_writes_only_when_an_output_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "unit.U"
            source.write_bytes(ucode_stream())
            output = Path(temporary) / "patched.U"
            status, stdout, stderr = self.run_cli(
                [
                    "ucode",
                    "patch",
                    str(source),
                    "--insert-at",
                    "#2",
                    "--records",
                    "0x42600000,{fresh},0,2",
                    "--fresh-label",
                    "-o",
                    str(output),
                ]
            )
            self.assertEqual(status, 0, stderr)
            self.assertIn("fresh labels: 6", stdout)
            self.assertEqual(source.read_bytes(), ucode_stream())
            self.assertEqual(len(output.read_bytes()), len(ucode_stream()) + 16)

    def test_patching_a_stream_in_place_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "unit.U"
            source.write_bytes(ucode_stream())
            status, _stdout, stderr = self.run_cli(
                [
                    "ucode",
                    "patch",
                    str(source),
                    "--delete",
                    "1",
                    "-o",
                    str(source),
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("in place", stderr)

    def test_stream_diff_prints_the_first_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            left = Path(temporary) / "left.U"
            right = Path(temporary) / "right.U"
            left.write_bytes(ucode_stream())
            patched, _report = patch_stream(
                ucode_stream(), insert_at="#2", records_spec="0x7f660000,5"
            )
            right.write_bytes(patched)
            status, stdout, stderr = self.run_cli(
                ["stream", "diff", str(left), str(right)]
            )
        self.assertEqual(status, 0, stderr)
        self.assertIn("DIFFERENT", stdout)
        self.assertIn("first divergence: insert", stdout)


if __name__ == "__main__":
    unittest.main()
