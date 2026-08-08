"""Append-safe notes for a shared findings log.

A campaign's improvement log is written by many agents at once, and the usual
guidance -- "append only, re-read the file first" -- is not a mechanism. It is
a request, and it cannot be honoured: between the read and the write another
writer's whole-file rewrite lands, and the second writer's copy wins with no
error anywhere. One campaign lost roughly twenty-six consecutive entries that
way, over eight stages, while every agent involved reported success honestly.
Each of them *had* appended. Each of them was then overwritten.

The fix has to survive a writer that does not cooperate, because that is the
writer that caused the loss. `flock` alone does not: it serializes the two
`open`/`read`/`write` sequences without stopping the second from writing back
a copy of the file that predates the first. So the durable record is never the
shared file. `note add` writes each note to its own new file under a sidecar
directory (:func:`notes_directory`), created with ``O_EXCL``, and never opens
the log for writing at all. A whole-file rewrite of the log cannot destroy a
file it does not touch, and two concurrent `note add` calls cannot collide
because neither reuses a name.

`note list` renders the merged view -- the log's own entries plus every
sidecar note not yet folded in -- so the sidecar is a staging area a reader
sees, not a directory that quietly fills up. `note merge` folds the pending
notes into the log with `flock` and ``O_APPEND`` (correct here, because the
merge is the one writer that does append rather than rewrite) and then moves
the merged files aside rather than deleting them: the note survives even if
the merge output is later clobbered by the same kind of writer this module
exists to defend against.

The contract this module owes its caller is exactly one sentence: *a note,
once written, cannot be lost by a concurrent writer.*
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Schema written into every sidecar note file. Readers check it so a future
#: format change is a clear error rather than a silently half-read note.
NOTE_SCHEMA = "decomp-workbench-note-v1"

#: Suffix appended to the log's own name to locate its sidecar directory.
#: Derived from the log path rather than configured, so two tools pointed at
#: the same log always agree on where the notes are without being told.
NOTES_SUFFIX = ".notes.d"

#: Sidecar subdirectory holding notes already folded into the log. Merged
#: notes are moved here rather than removed: the whole point of the sidecar is
#: that it is the copy a careless whole-file writer cannot reach, and that
#: stays true only while the file still exists.
MERGED_DIRECTORY = "merged"

#: A log heading that introduces an entry, e.g. ``## WB-54 — title``. The
#: identifier is required to carry a digit so ordinary prose headings such as
#: ``## Recovery notice`` are not mistaken for entries.
_HEADING_RE = re.compile(
    r"^\#{2,}\s+(?P<id>[A-Za-z][A-Za-z0-9_.]*[-_]?\d[A-Za-z0-9_.-]*)"
    r"\s*(?:[-—:]+\s*)?(?P<title>.*)$"
)

#: A status line inside an entry, e.g. ``**Status:** LOGGED``.
_STATUS_RE = re.compile(r"^\s*\*{0,2}Status\*{0,2}\s*:\s*\*{0,2}\s*(?P<status>.+?)\s*$")


class NoteError(ValueError):
    """A note could not be written or read.

    Every message names the file involved and the fix, because the failure
    mode this module exists to prevent is a writer that believes it succeeded.
    A note command that cannot do its job must say so loudly.
    """


@dataclass(frozen=True)
class Note:
    """One recorded note, as stored in its own sidecar file."""

    identifier: str
    title: str
    status: str
    body: str
    author: str | None
    recorded: str
    path: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "title": self.title,
            "status": self.status,
            "body": self.body,
            "author": self.author,
            "recorded": self.recorded,
            "path": str(self.path),
        }

    def as_markdown(self) -> str:
        """Render the note as the log section `note merge` appends."""

        attribution = f"{self.recorded}"
        if self.author:
            attribution += f" by {self.author}"
        lines = [
            f"## {self.identifier} — {self.title}"
            if self.title
            else f"## {self.identifier}"
        ]
        lines.append(f"**Recorded:** {attribution}")
        if self.body.strip():
            lines.extend(("", self.body.strip()))
        lines.extend(("", f"**Status:** {self.status}"))
        return "\n".join(lines)


@dataclass(frozen=True)
class LogEntry:
    """One entry already present in the log document itself."""

    identifier: str
    title: str
    status: str | None
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "title": self.title,
            "status": self.status,
            "line": self.line,
            "source": "log",
        }


@dataclass(frozen=True)
class MergedNotes:
    """The merged view: the log's own entries plus the pending sidecar notes."""

    log: Path
    entries: tuple[LogEntry, ...]
    pending: tuple[Note, ...]
    merged: tuple[Note, ...]

    @property
    def duplicate_ids(self) -> tuple[str, ...]:
        """Identifiers that are both in the log and pending in the sidecar.

        Reported rather than resolved. A pending note whose identifier is
        already in the log is usually a second finding under one number, and
        deciding which text wins is an editorial call the tool must not make
        silently.
        """

        known = {entry.identifier for entry in self.entries}
        return tuple(
            sorted(
                {note.identifier for note in self.pending if note.identifier in known}
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "decomp-workbench-note-list-v1",
            "log": str(self.log),
            "entries": [entry.as_dict() for entry in self.entries],
            "pending": [note.as_dict() for note in self.pending],
            "merged": [note.as_dict() for note in self.merged],
            "pending_count": len(self.pending),
            "duplicate_ids": list(self.duplicate_ids),
        }


def notes_directory(log: str | Path) -> Path:
    """Return the sidecar directory for ``log``.

    Derived from the path, never configured: the guarantee only holds while
    every writer of one log agrees on one sidecar, and agreement by convention
    is what failed the first time.
    """

    path = Path(log)
    return path.parent / f"{path.name}{NOTES_SUFFIX}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _note_filename(identifier: str) -> str:
    """Build a name no concurrent writer can also choose.

    The timestamp sorts, the identifier makes the directory readable, and the
    random token is what makes the ``O_EXCL`` create succeed for both of two
    writers that arrive in the same second with the same identifier.
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", identifier) or "note"
    return f"{stamp}-{safe}-{secrets.token_hex(4)}.json"


def add_note(
    log: str | Path,
    *,
    identifier: str,
    title: str = "",
    status: str = "LOGGED",
    body: str = "",
    author: str | None = None,
) -> Note:
    """Write one note to the log's sidecar directory and return it.

    The log itself is never opened. That is the whole mechanism: a note that
    is not in the shared file cannot be lost when the shared file is replaced.
    """

    identifier = identifier.strip()
    if not identifier:
        raise NoteError("a note needs a non-empty --id, e.g. --id WB-54")
    directory = notes_directory(log)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise NoteError(
            f"could not create the notes directory {directory}: {error}"
        ) from error
    recorded = _utc_now()
    payload = {
        "schema": NOTE_SCHEMA,
        "id": identifier,
        "title": title.strip(),
        "status": status.strip() or "LOGGED",
        "body": body,
        "author": author,
        "recorded": recorded,
    }
    target = directory / _note_filename(identifier)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        # O_EXCL is the collision check; the random token in the name makes it
        # succeed. Written in one call so a reader never sees a partial note.
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(descriptor, text.encode("utf-8"))
        finally:
            os.close(descriptor)
    except OSError as error:
        raise NoteError(f"could not write the note {target}: {error}") from error
    return Note(
        identifier=identifier,
        title=title.strip(),
        status=status.strip() or "LOGGED",
        body=body,
        author=author,
        recorded=recorded,
        path=target,
    )


def _load_note(path: Path) -> Note | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != NOTE_SCHEMA:
        return None
    author = payload.get("author")
    return Note(
        identifier=str(payload.get("id", "")),
        title=str(payload.get("title", "")),
        status=str(payload.get("status", "LOGGED")),
        body=str(payload.get("body", "")),
        author=str(author) if author else None,
        recorded=str(payload.get("recorded", "")),
        path=path,
    )


def read_notes(log: str | Path, *, merged: bool = False) -> tuple[Note, ...]:
    """Read the sidecar notes for ``log``, pending by default."""

    directory = notes_directory(log)
    if merged:
        directory = directory / MERGED_DIRECTORY
    if not directory.is_dir():
        return ()
    found = [
        note
        for note in (_load_note(path) for path in sorted(directory.glob("*.json")))
        if note is not None
    ]
    return tuple(sorted(found, key=lambda note: (note.recorded, note.path.name)))


def parse_log_entries(text: str) -> tuple[LogEntry, ...]:
    """Return the identified entries a Markdown findings log already carries.

    Deliberately shallow: it recognizes a heading whose first token looks like
    an identifier, and the first status line beneath it. A findings log is
    prose, and a parser that demanded more structure than the humans writing
    it actually use would report an empty log and be believed.
    """

    entries: list[LogEntry] = []
    pending_id: str | None = None
    pending_title = ""
    pending_line = 0
    pending_status: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        heading = _HEADING_RE.match(line)
        if heading:
            if pending_id is not None:
                entries.append(
                    LogEntry(pending_id, pending_title, pending_status, pending_line)
                )
            pending_id = heading.group("id")
            pending_title = heading.group("title").strip()
            pending_line = number
            pending_status = None
            continue
        if pending_id is not None and pending_status is None:
            status = _STATUS_RE.match(line)
            if status:
                pending_status = status.group("status").rstrip(".")
    if pending_id is not None:
        entries.append(
            LogEntry(pending_id, pending_title, pending_status, pending_line)
        )
    return tuple(entries)


def merged_view(log: str | Path) -> MergedNotes:
    """Return the log's own entries together with the sidecar notes."""

    path = Path(log)
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as error:
        raise NoteError(f"could not read the log {path}: {error}") from error
    return MergedNotes(
        log=path,
        entries=parse_log_entries(text),
        pending=read_notes(path),
        merged=read_notes(path, merged=True),
    )


def merge_notes(log: str | Path, *, dry_run: bool = False) -> tuple[Note, ...]:
    """Fold every pending sidecar note into the log and return what moved.

    This is the one place the log is opened for writing, and it appends under
    an exclusive lock: `O_APPEND` keeps two merges from overwriting each
    other's bytes, and the lock keeps their records from interleaving. Neither
    defends against a whole-file rewrite by some other tool, which is why the
    merged note files are moved aside instead of deleted.
    """

    path = Path(log)
    pending = read_notes(path)
    if not pending or dry_run:
        return pending
    sections = "\n\n".join(note.as_markdown() for note in pending)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except OSError as error:
        raise NoteError(f"could not open the log {path} to append: {error}") from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            os.write(descriptor, ("\n" + sections + "\n").encode("utf-8"))
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as error:
        raise NoteError(f"could not append to the log {path}: {error}") from error
    finally:
        os.close(descriptor)
    archive = notes_directory(path) / MERGED_DIRECTORY
    archive.mkdir(parents=True, exist_ok=True)
    for note in pending:
        try:
            note.path.rename(archive / note.path.name)
        except OSError as error:
            raise NoteError(
                f"the log was updated but {note.path} could not be archived: {error}"
            ) from error
    return pending
