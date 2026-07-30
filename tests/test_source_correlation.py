"""Trace source correlation keeps line-marker evidence and ambiguity honest."""

from __future__ import annotations

import unittest

from decomp_workbench.globalcolor import parse_globalcolor_trace
from decomp_workbench.source_correlation import (
    correlate_trace_source,
    parse_line_marked_source,
    parse_listing_locations,
)

TRACE = """\
[CDX] webdetail proc=7 web=9 role=target dtype=13 bb=4 line=2
[CDX] p1dec phase=p1 proc=7 web=9 bestcolor=1 forbidden0=0 forbidden1=0
"""


class SourceCorrelationTests(unittest.TestCase):
    def test_line_markers_apply_to_the_following_physical_line(self) -> None:
        lines = parse_line_marked_source(
            '# 40 "first.c" 1\nalpha\n#line 7 "second.c"\nbeta\n',
            origin="combined.i",
        )
        self.assertEqual(
            [(item.file, item.line, item.physical_line, item.text) for item in lines],
            [
                ("first.c", 40, 2, "alpha"),
                ("second.c", 7, 4, "beta"),
            ],
        )

    def test_listing_locations_decode_file_table_without_guessing_unknowns(
        self,
    ) -> None:
        locations = parse_listing_locations(
            '.file 1 "candidate.c"\n.loc 1 12 3\n.loc 8 20\n'
        )
        self.assertEqual(locations[0].file, "candidate.c")
        self.assertEqual(locations[0].column, 3)
        self.assertIsNone(locations[1].file)

    def test_duplicate_include_line_is_ambiguous_until_file_is_selected(self) -> None:
        source = '# 2 "first.h"\nint first;\n# 2 "candidate.c"\nint candidate;\n'
        trace = parse_globalcolor_trace(TRACE)
        ambiguous = correlate_trace_source(
            trace,
            source_text=source,
            source_origin="combined.i",
        )
        self.assertEqual(ambiguous["states"]["ambiguous"], 1)
        self.assertEqual(ambiguous["correlated_webs"], 0)

        selected = correlate_trace_source(
            trace,
            source_text=source,
            source_origin="combined.i",
            source_file="candidate.c",
            listing_text='.file 1 "candidate.c"\n.loc 1 2 0\n',
        )
        row = selected["webs"][0]
        self.assertEqual(row["state"], "selected")
        self.assertEqual(row["source_candidates"][0]["text"], "int candidate;")
        self.assertEqual(row["listing_locations"][0]["file"], "candidate.c")
        self.assertIn("never promoted", selected["proof"])


if __name__ == "__main__":
    unittest.main()
