"""Tests for the append-safe findings log.

The load-bearing test here is
:meth:`NoteDurabilityTests.test_a_whole_file_rewrite_cannot_lose_a_note`,
because that is the exact failure that destroyed twenty-six entries: not a
crash, not an error, but a cooperating writer whose work was replaced by a
second writer holding a stale copy of the file.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.notes import (
    NoteError,
    add_note,
    merge_notes,
    merged_view,
    notes_directory,
    parse_log_entries,
    read_notes,
)

LOG = """# Findings

## WB-01 — the first finding
**Status:** LOGGED.

## WB-02 — the second finding
Some prose about the finding.
**Status:** SHIPPED.

# Recovery notice

Prose that is not an entry.
"""


class NoteDurabilityTests(unittest.TestCase):
    """The contract: a written note cannot be lost by a concurrent writer."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "IMPROVEMENTS.md"
        self.log.write_text(LOG, encoding="utf-8")

    def test_a_whole_file_rewrite_cannot_lose_a_note(self) -> None:
        add_note(self.log, identifier="WB-54", title="survives", body="evidence")
        # The exact hostile pattern: another agent read the log before the
        # note existed and writes its own copy back afterwards.
        self.log.write_text(LOG, encoding="utf-8")
        pending = read_notes(self.log)
        self.assertEqual([note.identifier for note in pending], ["WB-54"])
        self.assertEqual(pending[0].body, "evidence")

    def test_the_log_is_never_opened_for_writing_by_add(self) -> None:
        before = self.log.read_text(encoding="utf-8")
        add_note(self.log, identifier="WB-54", title="untouched")
        self.assertEqual(self.log.read_text(encoding="utf-8"), before)

    def test_concurrent_writers_all_survive(self) -> None:
        identifiers = [f"WB-{number}" for number in range(60, 92)]

        def record(identifier: str) -> None:
            add_note(self.log, identifier=identifier, title=f"note {identifier}")

        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(record, identifiers))
        recorded = {note.identifier for note in read_notes(self.log)}
        self.assertEqual(recorded, set(identifiers))

    def test_same_identifier_twice_in_one_second_keeps_both(self) -> None:
        add_note(self.log, identifier="WB-54", title="first")
        add_note(self.log, identifier="WB-54", title="second")
        titles = sorted(note.title for note in read_notes(self.log))
        self.assertEqual(titles, ["first", "second"])

    def test_add_rejects_an_empty_identifier(self) -> None:
        with self.assertRaises(NoteError):
            add_note(self.log, identifier="   ")


class LogParsingTests(unittest.TestCase):
    def test_entries_and_statuses_are_read_from_the_document(self) -> None:
        entries = parse_log_entries(LOG)
        self.assertEqual(
            [(item.identifier, item.title, item.status) for item in entries],
            [
                ("WB-01", "the first finding", "LOGGED"),
                ("WB-02", "the second finding", "SHIPPED"),
            ],
        )

    def test_prose_headings_are_not_mistaken_for_entries(self) -> None:
        self.assertEqual(parse_log_entries("## Recovery notice\n## Next steps\n"), ())

    def test_an_absent_log_is_an_empty_merged_view_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            view = merged_view(Path(directory) / "absent.md")
            self.assertEqual(view.entries, ())
            self.assertEqual(view.pending, ())


class MergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "IMPROVEMENTS.md"
        self.log.write_text(LOG, encoding="utf-8")

    def test_merge_appends_and_keeps_the_original_entries(self) -> None:
        add_note(self.log, identifier="WB-54", title="a new one", body="the body")
        merged = merge_notes(self.log)
        self.assertEqual([note.identifier for note in merged], ["WB-54"])
        text = self.log.read_text(encoding="utf-8")
        self.assertIn("## WB-01 — the first finding", text)
        self.assertIn("## WB-54 — a new one", text)
        self.assertIn("the body", text)
        self.assertEqual(read_notes(self.log), ())

    def test_merged_notes_are_archived_not_deleted(self) -> None:
        add_note(self.log, identifier="WB-54", title="kept")
        merge_notes(self.log)
        archived = read_notes(self.log, merged=True)
        self.assertEqual([note.identifier for note in archived], ["WB-54"])
        # And the archived copy still outlives a hostile rewrite of the log.
        self.log.write_text(LOG, encoding="utf-8")
        self.assertEqual(len(read_notes(self.log, merged=True)), 1)

    def test_dry_run_reports_without_writing(self) -> None:
        add_note(self.log, identifier="WB-54", title="staged")
        before = self.log.read_text(encoding="utf-8")
        pending = merge_notes(self.log, dry_run=True)
        self.assertEqual([note.identifier for note in pending], ["WB-54"])
        self.assertEqual(self.log.read_text(encoding="utf-8"), before)
        self.assertEqual(len(read_notes(self.log)), 1)

    def test_merge_of_nothing_is_a_no_op(self) -> None:
        before = self.log.read_text(encoding="utf-8")
        self.assertEqual(merge_notes(self.log), ())
        self.assertEqual(self.log.read_text(encoding="utf-8"), before)

    def test_a_duplicate_identifier_is_reported_not_resolved(self) -> None:
        add_note(self.log, identifier="WB-01", title="a second WB-01")
        self.assertEqual(merged_view(self.log).duplicate_ids, ("WB-01",))


class NoteCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "IMPROVEMENTS.md"
        self.log.write_text(LOG, encoding="utf-8")

    def run_cli(self, arguments: list[str]) -> tuple[int, str]:
        import contextlib
        import io

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = main(arguments)
        return status, stream.getvalue()

    def test_add_reports_the_file_it_wrote(self) -> None:
        status, output = self.run_cli(
            ["note", "add", "--log", str(self.log), "--id", "WB-54", "--title", "x"]
        )
        self.assertEqual(status, 0)
        self.assertIn("note: WB-54 recorded", output)
        self.assertIn(str(notes_directory(self.log).name), output)

    def test_list_shows_log_entries_and_pending_notes(self) -> None:
        self.run_cli(
            ["note", "add", "--log", str(self.log), "--id", "WB-54", "--title", "new"]
        )
        status, output = self.run_cli(["note", "list", "--log", str(self.log)])
        self.assertEqual(status, 0)
        self.assertIn("2 in the log, 1 pending", output)
        self.assertIn("WB-01", output)
        self.assertIn("WB-54", output)

    def test_list_json_carries_its_schema(self) -> None:
        status, output = self.run_cli(
            ["note", "list", "--log", str(self.log), "--json"]
        )
        payload = json.loads(output)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-note-list-v1")
        self.assertEqual(len(payload["entries"]), 2)

    def test_body_can_be_read_from_a_file(self) -> None:
        body = Path(self.directory.name) / "body.txt"
        body.write_text("measured evidence\n", encoding="utf-8")
        self.run_cli(
            [
                "note",
                "add",
                "--log",
                str(self.log),
                "--id",
                "WB-54",
                "--body-file",
                str(body),
            ]
        )
        self.assertEqual(read_notes(self.log)[0].body, "measured evidence\n")

    def test_merge_command_folds_pending_notes_in(self) -> None:
        self.run_cli(
            ["note", "add", "--log", str(self.log), "--id", "WB-54", "--title", "new"]
        )
        status, output = self.run_cli(["note", "merge", "--log", str(self.log)])
        self.assertEqual(status, 0)
        self.assertIn("appended 1 note(s)", output)
        self.assertIn("## WB-54 — new", self.log.read_text(encoding="utf-8"))

    def test_a_notes_directory_is_named_after_its_log(self) -> None:
        self.assertEqual(notes_directory(self.log).name, f"{self.log.name}.notes.d")

    def test_unwritable_notes_directory_is_a_clear_error(self) -> None:
        directory = notes_directory(self.log)
        directory.mkdir()
        os.chmod(directory, 0o500)
        self.addCleanup(os.chmod, directory, 0o700)
        with self.assertRaises(NoteError):
            add_note(self.log, identifier="WB-54")


if __name__ == "__main__":
    unittest.main()
