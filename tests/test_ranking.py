"""A closeness ranking is a measurement of one tree, and says which one.

Nothing here needs git, a build, or a project: the head reader is an
argument, and every other input is a JSON file in a temporary directory.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.permute import load_ranking
from decomp_workbench.ranking import (
    RANKING_STAMP_SCHEMA,
    check_ranking_fresh,
    freshness_note,
    freshness_warning,
    git_head,
    read_stamp,
    render_freshness,
    stamp_ranking,
)

ROWS = [
    {"name": "func_80012574", "differing_words": 18, "size_bytes": 240},
    {"name": "func_8001A154", "differing_words": 214, "size_bytes": 1200},
]

HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"


def moment() -> datetime:
    return datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def write_ranking(root: Path, payload: Any) -> Path:
    path = root / "ranking.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class GitHeadTests(unittest.TestCase):
    def test_the_head_is_read_from_the_project_root(self) -> None:
        seen: list[dict[str, Any]] = []

        def runner(argv: list[str], **kwargs: Any) -> Any:
            seen.append({"argv": argv, "cwd": kwargs.get("cwd")})
            return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n", "")

        self.assertEqual(git_head("/project", runner=runner), HEAD)
        self.assertEqual(seen[0]["argv"], ["git", "rev-parse", "HEAD"])
        self.assertEqual(seen[0]["cwd"], "/project")

    def test_a_tree_that_is_not_a_checkout_is_unknown_not_an_error(self) -> None:
        """An unpacked archive has no HEAD, and that is a state, not a crash."""

        def failed(argv: list[str], **kwargs: Any) -> Any:
            return subprocess.CompletedProcess(argv, 128, "", "not a repository")

        def missing(argv: list[str], **kwargs: Any) -> Any:
            raise OSError("git: not found")

        self.assertIsNone(git_head(".", runner=failed))
        self.assertIsNone(git_head(".", runner=missing))


class StampTests(unittest.TestCase):
    def test_a_stamped_ranking_still_reads_as_a_ranking(self) -> None:
        """The stamp is one added key, never a reshaping of the rows."""

        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            stamp_ranking(path, HEAD, now=moment)
            ranking = load_ranking(path)
            document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(ranking["func_80012574"], (18, 240))
        self.assertEqual(document["stamp"]["tree_hash"], HEAD)
        self.assertEqual(document["stamp"]["generated_at"], "2026-08-28T12:00:00Z")
        self.assertEqual(document["stamp"]["schema"], RANKING_STAMP_SCHEMA)

    def test_the_object_spelling_keeps_its_other_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(
                Path(temporary), {"functions": ROWS, "producer": "objdiff"}
            )
            stamp_ranking(path, HEAD, now=moment)
            document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["producer"], "objdiff")
        self.assertEqual(len(document["functions"]), 2)

    def test_restamping_the_same_tree_keeps_the_original_timestamp(self) -> None:
        """`generated_at` says when the measurement was taken.

        Refreshing it on every run would turn the one field that says how
        old this ordering is into a field that always says "just now".
        """

        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            first = stamp_ranking(path, HEAD, now=moment)
            later = stamp_ranking(
                path,
                HEAD,
                now=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
        self.assertTrue(first.changed)
        self.assertFalse(later.changed)
        self.assertEqual(later.stamp.generated_at, "2026-08-28T12:00:00Z")

    def test_a_new_tree_replaces_the_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            stamp_ranking(path, HEAD, now=moment)
            second = stamp_ranking(
                path, OTHER, now=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)
            )
        self.assertTrue(second.changed)
        self.assertEqual(second.stamp.tree_hash, OTHER)
        self.assertEqual(second.stamp.generated_at, "2026-09-01T00:00:00Z")

    def test_an_empty_hash_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            with self.assertRaises(ValueError):
                stamp_ranking(path, "  ")

    def test_a_ranking_that_is_neither_list_nor_object_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), 12)
            with self.assertRaises(ValueError):
                stamp_ranking(path, HEAD)

    def test_a_malformed_stamp_reads_as_no_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(
                Path(temporary), {"functions": ROWS, "stamp": {"tree_hash": ""}}
            )
            self.assertIsNone(read_stamp(path))
            self.assertIsNone(read_stamp(Path(temporary) / "absent.json"))


class FreshnessTests(unittest.TestCase):
    def test_the_four_states_a_consumer_has_to_tell_apart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stamped = write_ranking(root, ROWS)
            stamp_ranking(stamped, HEAD, now=moment)
            bare = root / "bare.json"
            bare.write_text(json.dumps(ROWS), encoding="utf-8")

            fresh = check_ranking_fresh(stamped, HEAD)
            stale = check_ranking_fresh(stamped, OTHER)
            unknown = check_ranking_fresh(stamped, None)
            unstamped = check_ranking_fresh(bare, HEAD)
            missing = check_ranking_fresh(root / "absent.json", HEAD)

        self.assertEqual(fresh.status, "fresh")
        self.assertTrue(fresh.fresh)
        self.assertEqual(stale.status, "stale")
        self.assertEqual(unknown.status, "unknown")
        self.assertEqual(unstamped.status, "unstamped")
        self.assertEqual(missing.status, "missing")
        self.assertFalse(any(item.fresh for item in (stale, unknown, unstamped)))

    def test_a_stale_ranking_names_both_trees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            stamp_ranking(path, HEAD, now=moment)
            stale = check_ranking_fresh(path, OTHER)
        self.assertIn(HEAD[:12], stale.message)
        self.assertIn(OTHER[:12], stale.message)
        self.assertIn("WARNING:", str(freshness_warning(stale)))
        self.assertIn("warning", "\n".join(render_freshness(stale)))
        self.assertEqual(stale.as_dict()["status"], "stale")

    def test_only_a_contradiction_is_loud(self) -> None:
        """An unstamped ranking is where every project starts.

        Shouting about the state everyone is in is how the warning that
        matters gets filtered out before it arrives.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bare = write_ranking(root, ROWS)
            unstamped = check_ranking_fresh(bare, HEAD)
            stamp_ranking(bare, HEAD, now=moment)
            fresh = check_ranking_fresh(bare, HEAD)
        self.assertIsNone(freshness_warning(unstamped))
        self.assertIn("note:", str(freshness_note(unstamped)))
        self.assertIsNone(freshness_warning(fresh))
        self.assertIsNone(freshness_note(fresh))


class RankingCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_stamp_then_check_is_fresh_and_a_moved_tree_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            stamped, out, _ = self.run_cli(
                ["ranking", "stamp", str(path), "--tree-hash", HEAD]
            )
            again, repeat, _ = self.run_cli(
                ["ranking", "stamp", str(path), "--tree-hash", HEAD]
            )
            fresh, _, _ = self.run_cli(
                ["ranking", "check", str(path), "--tree-hash", HEAD]
            )
            stale, report, _ = self.run_cli(
                ["ranking", "check", str(path), "--tree-hash", OTHER]
            )
        self.assertEqual((stamped, again, fresh, stale), (0, 0, 0, 1))
        self.assertIn(HEAD, out)
        self.assertIn("already stamped", repeat)
        self.assertIn("stale", report)

    def test_check_reports_json_with_its_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            self.run_cli(["ranking", "stamp", str(path), "--tree-hash", HEAD])
            status, out, _ = self.run_cli(
                ["ranking", "check", str(path), "--tree-hash", OTHER, "--json"]
            )
            payload = json.loads(out)
        self.assertEqual(status, 1)
        self.assertEqual(payload["schema"], RANKING_STAMP_SCHEMA)
        self.assertEqual(payload["tree_hash"], HEAD)
        self.assertEqual(payload["current_hash"], OTHER)
        self.assertFalse(payload["fresh"])

    def test_an_unreadable_head_asks_for_an_explicit_hash(self) -> None:
        """Stamping with a hash nobody could read would stamp a lie."""

        with tempfile.TemporaryDirectory() as temporary:
            path = write_ranking(Path(temporary), ROWS)
            status, _out, err = self.run_cli(
                ["ranking", "stamp", str(path), "--project", "/nonexistent-project"]
            )
        self.assertEqual(status, 2)
        self.assertIn("--tree-hash", err)

    def test_a_ranking_that_is_not_json_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ranking.json"
            path.write_text("not json", encoding="utf-8")
            status, _out, err = self.run_cli(
                ["ranking", "stamp", str(path), "--tree-hash", HEAD]
            )
        self.assertEqual(status, 2)
        self.assertTrue(err.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
