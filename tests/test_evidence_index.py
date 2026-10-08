"""Tests for the wave-A evidence index (docs/compiler-laws/ido-5.3-evidence.md).

The page exists to record the origin and limits of thirty compiler claims, so
what is tested is that it keeps doing so: every row names who measured it, an
evidence class, a synthetic-reproduction verdict, and every reproduction it
cites is an original C file that is actually in the repository.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "compiler-laws" / "ido-5.3-evidence.md"
ROW_RE = re.compile(r"^\| (W\d+) \|(.+)\|$", re.MULTILINE)


class EvidenceIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PAGE.read_text(encoding="utf-8")
        self.rows = {
            name: [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]
            for name, body in ROW_RE.findall(self.text)
        }

    def test_rows_are_numbered_contiguously(self) -> None:
        numbers = sorted(int(name[1:]) for name in self.rows)
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        self.assertEqual(len(numbers), 30)

    def test_every_row_records_origin_class_and_reproduction(self) -> None:
        for name, cells in self.rows.items():
            with self.subTest(row=name):
                law, measured, tier, synthetic, _related = cells
                self.assertTrue(law)
                self.assertTrue(measured.startswith("Mickey"), measured)
                self.assertIn(tier, {"T1", "T2", "T3"})
                self.assertTrue(synthetic)

    def test_every_cited_reproduction_is_original_c_in_the_tree(self) -> None:
        cited = set(re.findall(r"`([a-z_]+\.c)`", self.text))
        self.assertEqual(cited, {"loop_exit_test.c", "zero_emission.c"})
        for name in cited:
            path = ROOT / "tests" / "fixtures" / "wave_a" / name
            with self.subTest(fixture=name):
                self.assertTrue(path.is_file())
                header = path.read_text(encoding="utf-8")
                self.assertIn("Synthetic C written for the workbench (CC0)", header)
                self.assertIn("no game code", header)

    def test_the_page_states_its_scope(self) -> None:
        flat = " ".join(self.text.split())
        self.assertIn("Nothing here has been tested on another IDO release", flat)
        self.assertIn("No instruction text", flat)


if __name__ == "__main__":
    unittest.main()
