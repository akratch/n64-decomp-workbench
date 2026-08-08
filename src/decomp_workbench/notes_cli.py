"""`decomp-workbench note`: add to and read a shared findings log safely.

The commands are thin. Everything that makes a note durable lives in
:mod:`decomp_workbench.notes`; what belongs here is the part a reader meets --
that `note add` reports *where* the note went, so nobody has to trust that it
worked, and that `note list` shows the pending count next to the log's own
entries, so a staged note is visible rather than merely safe.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .notes import (
    MergedNotes,
    Note,
    NoteError,
    merge_notes,
    merged_view,
    notes_directory,
)


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        if args.body_file == "-":
            return sys.stdin.read()
        try:
            with open(args.body_file, encoding="utf-8") as handle:
                return handle.read()
        except OSError as error:
            raise NoteError(f"could not read --body-file: {error}") from error
    if args.body == "-":
        return sys.stdin.read()
    return args.body or ""


def note_add_command(args: argparse.Namespace) -> int:
    try:
        note = add_note_from_args(args)
    except (NoteError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {"schema": "decomp-workbench-note-add-v1", **note.as_dict()},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"note: {note.identifier} recorded ({note.status})")
    print(f"file: {note.path}")
    # The reassurance is the product. The mechanism this command replaced also
    # reported success, and was wrong, so this line says what is true and why.
    print(
        "safe: the note is its own file; a whole-file rewrite of "
        f"{args.log} cannot remove it"
    )
    print(f"next: decomp-workbench note list --log {args.log}")
    return 0


def add_note_from_args(args: argparse.Namespace) -> Note:
    """Build and write the note described by parsed `note add` arguments."""

    from .notes import add_note

    return add_note(
        args.log,
        identifier=args.id,
        title=args.title or "",
        status=args.status,
        body=_read_body(args),
        author=args.author,
    )


def render_note_list(view: MergedNotes, *, verbose: bool) -> list[str]:
    """Render the merged view: the log's entries, then what is still pending."""

    lines = [
        f"log: {view.log}",
        f"entries: {len(view.entries)} in the log, "
        f"{len(view.pending)} pending, {len(view.merged)} merged",
    ]
    for duplicate in view.duplicate_ids:
        lines.append(
            f"warning: {duplicate} is pending and already in the log; "
            "merging will record it twice"
        )
    if view.entries:
        lines.append("")
        lines.append("in the log:")
        width = max(len(entry.identifier) for entry in view.entries)
        for entry in view.entries:
            status = entry.status or "-"
            title = entry.title if verbose else entry.title[:56]
            lines.append(
                f"  {entry.identifier.ljust(width)}  [{status}]  {title}".rstrip()
            )
    if view.pending:
        lines.append("")
        lines.append("pending (in the sidecar, not yet in the log):")
        width = max(len(note.identifier) for note in view.pending)
        for note in view.pending:
            author = f" by {note.author}" if note.author else ""
            lines.append(
                f"  {note.identifier.ljust(width)}  [{note.status}]  "
                f"{note.title}".rstrip()
            )
            lines.append(f"  {' ' * width}  {note.recorded}{author}")
            if verbose and note.body.strip():
                lines.extend(
                    f"  {' ' * width}  {line}"
                    for line in note.body.strip().splitlines()
                )
        lines.append("")
        lines.append(f"next: decomp-workbench note merge --log {view.log}")
    elif not view.entries:
        lines.append("")
        lines.append(f"notes directory: {notes_directory(view.log)}")
        lines.append(
            f'next: decomp-workbench note add --log {view.log} --id WB-NN --title "..."'
        )
    return lines


def note_list_command(args: argparse.Namespace) -> int:
    try:
        view = merged_view(args.log)
    except (NoteError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.id:
        view = MergedNotes(
            log=view.log,
            entries=tuple(item for item in view.entries if item.identifier == args.id),
            pending=tuple(item for item in view.pending if item.identifier == args.id),
            merged=tuple(item for item in view.merged if item.identifier == args.id),
        )
    if args.json:
        print(json.dumps(view.as_dict(), indent=2, sort_keys=True))
    else:
        print("\n".join(render_note_list(view, verbose=args.verbose)))
    return 0


def note_merge_command(args: argparse.Namespace) -> int:
    try:
        pending = merge_notes(args.log, dry_run=args.dry_run)
    except (NoteError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "decomp-workbench-note-merge-v1",
                    "log": str(args.log),
                    "dry_run": args.dry_run,
                    "merged": [note.as_dict() for note in pending],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not pending:
        print(f"merge: nothing pending for {args.log}")
        return 0
    verb = "would append" if args.dry_run else "appended"
    print(f"merge: {verb} {len(pending)} note(s) to {args.log}")
    for note in pending:
        print(f"  {note.identifier}  [{note.status}]  {note.title}".rstrip())
    if not args.dry_run:
        print(
            f"kept: the merged note files remain under "
            f"{notes_directory(args.log) / 'merged'}"
        )
    return 0


def _add_log_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--log",
        required=True,
        metavar="FILE",
        help=(
            "the shared findings log. It is read, never rewritten; notes are "
            "stored beside it in FILE.notes.d/"
        ),
    )


def register_note_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the flat `note-*` commands behind the `note` group spelling."""

    add = commands.add_parser(
        "note-add",
        help=argparse.SUPPRESS,
        description=(
            "Record one note for a shared findings log without opening the "
            "log for writing. The note is written to its own file under "
            "FILE.notes.d/, so a concurrent writer that rewrites the whole "
            "log cannot destroy it. Use `note merge` to fold pending notes "
            "into the log itself."
        ),
    )
    _add_log_argument(add)
    add.add_argument("--id", required=True, metavar="WB-NN", help="note identifier")
    add.add_argument("--title", help="one-line summary")
    add.add_argument(
        "--status", default="LOGGED", help="status token (default: LOGGED)"
    )
    add.add_argument(
        "--body",
        default="",
        help="note body; pass - to read the body from standard input",
    )
    add.add_argument(
        "--body-file", metavar="FILE", help="read the body from FILE, or - for stdin"
    )
    add.add_argument("--author", help="who recorded it")
    add.add_argument("--json", action="store_true", help="emit JSON")
    add.set_defaults(handler=note_add_command)

    listing = commands.add_parser(
        "note-list",
        help=argparse.SUPPRESS,
        description=(
            "Render the merged view of a findings log: the entries the log "
            "itself carries, followed by the sidecar notes not yet folded in."
        ),
    )
    _add_log_argument(listing)
    listing.add_argument("--id", metavar="WB-NN", help="show only this identifier")
    listing.add_argument(
        "--verbose", action="store_true", help="show full titles and pending bodies"
    )
    listing.add_argument("--json", action="store_true", help="emit JSON")
    listing.set_defaults(handler=note_list_command)

    merge = commands.add_parser(
        "note-merge",
        help=argparse.SUPPRESS,
        description=(
            "Append every pending sidecar note to the log under an exclusive "
            "lock, then move the merged note files aside. This is the only "
            "command that writes the log, and it appends rather than "
            "rewriting it."
        ),
    )
    _add_log_argument(merge)
    merge.add_argument(
        "--dry-run", action="store_true", help="report what would be appended"
    )
    merge.add_argument("--json", action="store_true", help="emit JSON")
    merge.set_defaults(handler=note_merge_command)
