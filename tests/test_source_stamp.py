"""Tests for the source stamp every compile-keyed artefact carries (item 20)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.source_stamp import (
    STAMP_KEY,
    STATUSES,
    StaleSourceError,
    check_source_stamp,
    enforce,
    read_source_stamp,
    stamp_sources,
)


class SourceStampTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.root / "a.c"
        self.second = self.root / "b.h"
        self.first.write_text("int a;\n", encoding="utf-8")
        self.second.write_text("extern int a;\n", encoding="utf-8")

    def test_a_stamp_round_trips_through_a_document(self) -> None:
        stamp = stamp_sources([self.first, self.second])
        document = {"rows": [], STAMP_KEY: stamp.as_dict()}
        read = read_source_stamp(document)
        assert read is not None
        self.assertEqual(read.sources, stamp.sources)
        self.assertTrue(stamp.stamped_at.endswith("Z"))

    def test_an_unchanged_source_is_fresh_and_enforce_is_silent(self) -> None:
        freshness = check_source_stamp(
            stamp_sources([self.first, self.second]), artefact="landscape"
        )
        self.assertEqual(freshness.status, "fresh")
        self.assertEqual(enforce(freshness), [])

    def test_one_moved_source_of_several_makes_the_artefact_stale(self) -> None:
        stamp = stamp_sources([self.first, self.second])
        self.second.write_text("extern int a, b;\n", encoding="utf-8")
        freshness = check_source_stamp(stamp, artefact="landscape")
        self.assertEqual(freshness.status, "stale")
        self.assertTrue(freshness.refused)
        self.assertEqual([item.status for item in freshness.checks], ["fresh", "stale"])
        with self.assertRaises(StaleSourceError) as raised:
            enforce(freshness)
        self.assertIn("STALE: landscape", str(raised.exception))
        self.assertIn(str(self.second.resolve()), str(raised.exception))

    def test_a_touch_is_not_a_change(self) -> None:
        """Content, not mtime: a checkout or a rebase moves every mtime."""

        stamp = stamp_sources([self.first])
        self.first.write_text("int a;\n", encoding="utf-8")
        self.assertEqual(check_source_stamp(stamp, artefact="x").status, "fresh")

    def test_allowed_stale_proceeds_and_still_says_so(self) -> None:
        stamp = stamp_sources([self.first])
        self.first.write_text("int b;\n", encoding="utf-8")
        freshness = check_source_stamp(stamp, artefact="x", allow_stale=True)
        self.assertFalse(freshness.refused)
        lines = enforce(freshness)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("WARNING: STALE:"))
        self.assertTrue(freshness.as_dict()["allowed_stale"])

    def test_unstamped_and_unreadable_warn_rather_than_refuse(self) -> None:
        unstamped = check_source_stamp(None, artefact="x")
        self.assertEqual(unstamped.status, "unstamped")
        self.assertFalse(unstamped.refused)
        self.assertEqual(len(enforce(unstamped)), 1)

        stamp = stamp_sources([self.first])
        self.first.unlink()
        unknown = check_source_stamp(stamp, artefact="x")
        self.assertEqual(unknown.status, "unknown")
        self.assertFalse(unknown.refused)
        self.assertIn("--stamped-source", enforce(unknown)[0])

    def test_an_override_path_reads_a_moved_checkout(self) -> None:
        stamp = stamp_sources([self.first])
        moved = self.root / "moved.c"
        moved.write_bytes(self.first.read_bytes())
        self.first.unlink()
        freshness = check_source_stamp(stamp, artefact="x", source=moved)
        self.assertEqual(freshness.status, "fresh")
        self.assertEqual(freshness.checks[0].checked_path, str(moved))

    def test_one_override_for_several_sources_is_refused_not_guessed(self) -> None:
        stamp = stamp_sources([self.first, self.second])
        with self.assertRaisesRegex(ValueError, "cannot say which"):
            check_source_stamp(stamp, artefact="x", source=self.first)

    def test_a_legacy_digest_is_honoured_when_no_stamp_exists(self) -> None:
        read = read_source_stamp(
            {"schema": "old"}, legacy=[(str(self.first), "0" * 64)]
        )
        freshness = check_source_stamp(read, artefact="x")
        self.assertEqual(freshness.status, "stale")

    def test_a_malformed_stamp_reads_as_unstamped(self) -> None:
        samples: tuple[object, ...] = (
            {"sources": []},
            {"sources": [{"path": 1}]},
            "text",
            None,
        )
        for raw in samples:
            with self.subTest(raw=raw):
                self.assertIsNone(read_source_stamp({STAMP_KEY: raw}))

    def test_statuses_are_ordered_worst_last(self) -> None:
        self.assertEqual(STATUSES[0], "fresh")
        self.assertEqual(STATUSES[-1], "stale")


if __name__ == "__main__":
    unittest.main()
