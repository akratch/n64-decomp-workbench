"""The linked image as an oracle, classified per function range.

The images here are synthetic byte strings: what is under test is the
classification and the arithmetic, not any particular game's layout.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from decomp_workbench import linked_compare as lc

TARGET = bytes(range(256)) * 16


def built(**edits: int) -> bytes:
    image = bytearray(TARGET)
    for offset, value in edits.items():
        image[int(offset[1:], 0)] = value
    return bytes(image)


class RangeParsingTests(unittest.TestCase):
    def test_a_command_line_range_reads_start_and_end(self) -> None:
        item = lc.parse_range_argument("draw:0x100:0x180")
        self.assertEqual((item.name, item.start, item.end), ("draw", 0x100, 0x180))

    def test_a_command_line_range_reads_start_and_size(self) -> None:
        item = lc.parse_range_argument("draw:0x100+0x80")
        self.assertEqual(item.end, 0x180)

    def test_an_empty_range_is_refused_rather_than_reported_exact(self) -> None:
        with self.assertRaises(lc.RangeError) as caught:
            lc.parse_range_argument("draw:0x100:0x100")
        self.assertIn("empty range", str(caught.exception))

    def test_a_range_without_a_separator_says_what_the_shape_is(self) -> None:
        with self.assertRaises(lc.RangeError) as caught:
            lc.parse_range_argument("draw")
        self.assertIn("NAME:START:END", str(caught.exception))

    def test_a_ranges_document_accepts_end_or_size(self) -> None:
        parsed = lc.parse_ranges(
            {
                "schema": lc.RANGES_SCHEMA,
                "ranges": [
                    {"name": "a", "start": "0x10", "end": "0x20"},
                    {"name": "b", "start": 32, "size": 16},
                ],
            }
        )
        self.assertEqual([item.end for item in parsed], [0x20, 48])

    def test_a_bare_list_of_ranges_is_accepted(self) -> None:
        parsed = lc.parse_ranges([{"name": "a", "start": 0, "size": 4}])
        self.assertEqual(len(parsed), 1)

    def test_an_unknown_ranges_schema_is_refused_by_name(self) -> None:
        with self.assertRaises(lc.RangeError) as caught:
            lc.parse_ranges({"schema": "other-v1", "ranges": []})
        self.assertIn(lc.RANGES_SCHEMA, str(caught.exception))

    def test_a_range_with_neither_end_nor_size_is_refused(self) -> None:
        with self.assertRaises(lc.RangeError) as caught:
            lc.parse_ranges([{"name": "a", "start": 0}])
        self.assertIn("'end' or a 'size'", str(caught.exception))


class ClassificationTests(unittest.TestCase):
    ranges = (lc.ImageRange("draw", 0x100, 0x140),)

    def test_an_identical_image_is_exact(self) -> None:
        result = lc.compare_images(TARGET, TARGET, self.ranges)
        self.assertEqual(result.klass, "exact")
        self.assertEqual(result.differing_bytes, 0)
        self.assertTrue(result.ok)
        self.assertEqual(result.verdicts[0].summary, "exact")

    def test_a_difference_outside_the_range_is_text_exact(self) -> None:
        result = lc.compare_images(built(o0x800=0xFF), TARGET, self.ranges)
        verdict = result.verdicts[0]
        self.assertEqual(verdict.klass, "text-exact")
        self.assertEqual(verdict.out_of_range_bytes, 1)
        self.assertEqual(verdict.first_out_of_range, 0x800)
        self.assertIsNone(verdict.first_in_range)
        self.assertTrue(result.ok)

    def test_differences_inside_the_range_are_counted_in_words(self) -> None:
        """Two bytes of one word are one word of residual, not two."""

        result = lc.compare_images(
            built(o0x104=0xFF, o0x105=0xFE, o0x120=0xFD), TARGET, self.ranges
        )
        verdict = result.verdicts[0]
        self.assertEqual(verdict.klass, "text-differs")
        self.assertEqual(verdict.in_range_bytes, 3)
        self.assertEqual(verdict.in_range_words, 2)
        self.assertEqual(verdict.first_in_range, 0x104)
        self.assertEqual(verdict.summary, "text-differs 2 words")
        self.assertFalse(result.ok)

    def test_a_size_difference_refuses_a_range_verdict(self) -> None:
        result = lc.compare_images(TARGET + b"\x00" * 16, TARGET, self.ranges)
        self.assertEqual(result.size_delta, 16)
        self.assertEqual(result.verdicts[0].klass, "size-differs")
        self.assertEqual(result.verdicts[0].summary, "size-differs (+16)")
        self.assertFalse(result.ok)

    def test_a_range_past_the_shorter_image_is_a_size_difference(self) -> None:
        short = TARGET[:0x120]
        result = lc.compare_images(short, short + b"\x00" * 0x100, self.ranges)
        self.assertEqual(result.verdicts[0].klass, "size-differs")

    def test_a_range_past_an_equal_length_image_says_that_and_not_a_delta(
        self,
    ) -> None:
        """`size-differs (+0)` is a verdict nobody can act on.

        Two images of the same length, a range naming bytes past their end:
        the range is wrong, not the build, and the summary has to say which.
        """

        result = lc.compare_images(
            TARGET, TARGET, (lc.ImageRange("beyond", len(TARGET) - 4, len(TARGET) + 8),)
        )
        verdict = result.verdicts[0]
        self.assertEqual(verdict.klass, "size-differs")
        self.assertTrue(verdict.past_image)
        self.assertEqual(verdict.size_delta, 0)
        self.assertIn("past the image", verdict.summary)
        self.assertFalse(result.ok)

    def test_a_range_inside_a_differently_sized_image_is_not_past_it(self) -> None:
        result = lc.compare_images(TARGET + b"\x00" * 16, TARGET, self.ranges)
        self.assertFalse(result.verdicts[0].past_image)
        self.assertEqual(result.verdicts[0].summary, "size-differs (+16)")

    def test_many_ranges_over_a_wholly_differing_image_stay_linear(self) -> None:
        """The per-range scan must not walk every differing byte again.

        A build that went wrong differs over megabytes and a trial names
        hundreds of functions; the product of the two is the shape that
        turns a report into a hang.
        """

        size = 0x40000
        target = bytes(size)
        build = bytes(0xFF for _ in range(size))
        ranges = tuple(
            lc.ImageRange(f"f{index}", index * 0x40, index * 0x40 + 0x40)
            for index in range(400)
        )
        start = time.monotonic()
        result = lc.compare_images(build, target, ranges)
        self.assertLess(time.monotonic() - start, 5.0)
        self.assertEqual(result.verdicts[0].in_range_words, 0x10)
        self.assertEqual(result.verdicts[0].first_in_range, 0x0)
        self.assertEqual(result.verdicts[1].first_in_range, 0x40)
        self.assertEqual(result.verdicts[0].out_of_range_bytes, size - 0x40)
        self.assertEqual(result.verdicts[0].first_out_of_range, 0x40)
        self.assertEqual(result.verdicts[-1].first_out_of_range, 0x0)

    def test_the_image_verdict_is_the_worst_of_its_ranges(self) -> None:
        result = lc.compare_images(
            built(o0x104=0xFF),
            TARGET,
            (lc.ImageRange("a", 0x0, 0x40), lc.ImageRange("draw", 0x100, 0x140)),
        )
        self.assertEqual(
            [item.klass for item in result.verdicts], ["text-exact", "text-differs"]
        )
        self.assertEqual(result.klass, "text-differs")

    def test_with_no_ranges_the_image_still_gets_a_verdict(self) -> None:
        self.assertEqual(lc.compare_images(TARGET, TARGET).klass, "exact")
        self.assertEqual(
            lc.compare_images(built(o0x800=0xFF), TARGET).klass, "text-exact"
        )

    def test_every_differing_byte_is_visited_across_block_boundaries(self) -> None:
        """The block scan is an optimization; it must not sample."""

        big = bytes(0x4000)
        edited = bytearray(big)
        for offset in (0x0, 0xFFF, 0x1000, 0x2FFF, 0x3FFF):
            edited[offset] = 0xFF
        self.assertEqual(
            list(lc.differing_offsets(bytes(edited), big)),
            [0x0, 0xFFF, 0x1000, 0x2FFF, 0x3FFF],
        )

    def test_the_table_names_the_class_and_the_first_offset(self) -> None:
        result = lc.compare_images(built(o0x104=0xFF), TARGET, self.ranges)
        text = "\n".join(lc.render(result))
        self.assertIn("draw", text)
        self.assertIn("text-differs", text)
        self.assertIn("0x104", text)
        self.assertIn("verdict         text-differs", text)


class RoundTripTests(unittest.TestCase):
    def test_the_json_document_carries_every_range_and_its_class(self) -> None:
        result = lc.compare_images(
            built(o0x104=0xFF), TARGET, (lc.ImageRange("draw", 0x100, 0x140),)
        )
        payload = json.loads(json.dumps(result.as_dict()))
        self.assertEqual(payload["schema"], lc.LINKED_COMPARE_SCHEMA)
        self.assertEqual(payload["class"], "text-differs")
        self.assertEqual(payload["ranges"][0]["in_range_words"], 1)
        self.assertFalse(payload["ok"])

    def test_a_ranges_file_written_by_a_host_reads_back(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ranges.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": lc.RANGES_SCHEMA,
                        "ranges": [{"name": "draw", "start": "0x100", "end": "0x140"}],
                    }
                ),
                encoding="utf-8",
            )
            parsed = lc.parse_ranges(
                json.loads(path.read_text(encoding="utf-8")), origin=str(path)
            )
        self.assertEqual(parsed[0].size, 0x40)


if __name__ == "__main__":
    unittest.main()
