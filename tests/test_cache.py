"""Cache cleanup is inspectable, opt-in, and recoverable."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from decomp_workbench.cache import (
    cache_status,
    format_bytes,
    parse_duration,
    parse_size,
    prune_cache,
    restore_pruned_cache,
)


class CacheTests(unittest.TestCase):
    def test_duration_parser_accepts_combinations(self) -> None:
        self.assertEqual(parse_duration("1w2d3h"), 788_400)
        with self.assertRaises(ValueError):
            parse_duration("30 days")

    def test_size_parser_and_formatter_are_human_readable(self) -> None:
        self.assertEqual(parse_size("1.5MiB"), 1_572_864)
        self.assertEqual(parse_size("2G"), 2 * 1024**3)
        self.assertEqual(format_bytes(1536), "1.5 KiB")
        with self.assertRaises(ValueError):
            parse_size("lots")

    def test_prune_defaults_to_a_non_mutating_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            old = cache / "old.o"
            recent = cache / "recent.o"
            old.write_bytes(b"old")
            recent.write_bytes(b"recent")
            old_time = time.time() - 10 * 24 * 60 * 60
            os.utime(old, (old_time, old_time))
            report = prune_cache(
                cache,
                older_than=7 * 24 * 60 * 60,
                apply=False,
                trash_root=root / "trash",
            )
            self.assertEqual(report["selected_files"], 1)
            self.assertTrue(old.is_file())
            self.assertTrue(recent.is_file())
            self.assertFalse((root / "trash").exists())

    def test_applied_prune_moves_to_trash_and_restores(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            entry = cache / "entry.o"
            entry.write_bytes(b"object")
            old_time = time.time() - 100
            os.utime(entry, (old_time, old_time))
            report = prune_cache(
                cache,
                older_than=10,
                apply=True,
                trash_root=root / "trash",
            )
            self.assertFalse(entry.exists())
            trash = Path(str(report["trash_directory"]))
            self.assertEqual((trash / "entry.o").read_bytes(), b"object")
            self.assertEqual(restore_pruned_cache(trash, cache), 1)
            self.assertEqual(entry.read_bytes(), b"object")
            self.assertEqual(cache_status(cache)["files"], 1)

    def test_size_prune_uses_lru_and_can_protect_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            entries = []
            for index in range(4):
                entry = cache / f"{index}.o"
                entry.write_bytes(b"x" * 10)
                stamp = time.time() - (100 - index)
                os.utime(entry, (stamp, stamp))
                entries.append(entry)
            report = prune_cache(
                cache,
                max_size=15,
                keep_recent=1,
                apply=False,
                trash_root=root / "trash",
            )
            self.assertEqual(report["selected_files"], 3)
            self.assertEqual(report["cache_bytes_after"], 10)
            self.assertNotIn(
                str(entries[-1]), {item["path"] for item in report["entries"]}
            )

    def test_nested_entries_round_trip_through_recoverable_trash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            nested = cache / "objects" / "entry.o"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"nested")
            old = time.time() - 100
            os.utime(nested, (old, old))
            report = prune_cache(
                cache,
                older_than=10,
                apply=True,
                trash_root=root / "trash",
            )
            trash = Path(str(report["trash_directory"]))
            self.assertEqual((trash / "objects" / "entry.o").read_bytes(), b"nested")
            self.assertEqual(restore_pruned_cache(trash, cache), 1)
            self.assertEqual(nested.read_bytes(), b"nested")

    def test_restore_preflights_every_collision_before_moving(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trash = root / "trash"
            cache = root / "cache"
            trash.mkdir()
            cache.mkdir()
            (trash / "first.o").write_bytes(b"first")
            (trash / "second.o").write_bytes(b"second")
            (cache / "second.o").write_bytes(b"existing")

            with self.assertRaisesRegex(FileExistsError, "partial restore"):
                restore_pruned_cache(trash, cache)

            self.assertEqual((trash / "first.o").read_bytes(), b"first")
            self.assertEqual((trash / "second.o").read_bytes(), b"second")
            self.assertFalse((cache / "first.o").exists())
            self.assertEqual((cache / "second.o").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
