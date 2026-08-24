"""CLI for record-level windows, diffs, and surgery on IDO phase streams."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .streams import (
    FORMATS,
    count_fresh_slots,
    diff_streams,
    patch_stream,
    stream_window,
)


def _render_record(record: dict[str, Any] | None, width: int) -> str:
    if record is None:
        return " " * width
    text = f"#{record['index']:<5d} {record['offset_hex']:>7s} {record['name']}"
    return text[:width].ljust(width)


def _print_window(report: dict[str, Any]) -> None:
    stream = report["stream"]
    print(
        f"{report['format']}: {stream['record_count']} record(s), "
        f"{stream['bytes']} bytes, sha256={stream['sha256'][:12]}"
    )
    position = report["position"]
    print(f"position: {position['offset_hex']} = record #{position['record_index']}")
    for record in report["records"]:
        marker = ">" if record["at_position"] else " "
        print(
            f"{marker} #{record['index']:<5d} {record['offset_hex']:>8s} "
            f"{record['name']:<16s} {record['raw_hex']}"
        )
        print(f"      {record['detail']}")


def stream_window_command(args: argparse.Namespace) -> int:
    try:
        report = stream_window(
            args.stream,
            at=args.at,
            radius=args.radius,
            stream_format=args.format,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    _print_window(report)
    print(f"proof: {report['proof']}")
    return 0


def stream_diff_command(args: argparse.Namespace) -> int:
    try:
        report = diff_streams(
            args.left,
            args.right,
            stream_format=args.format,
            limit=args.limit,
            context=args.context,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    counts = report["record_counts"]
    print(
        f"{report['format']}: {counts['left']} vs {counts['right']} record(s); "
        f"{'IDENTICAL' if report['identical'] else 'DIFFERENT'}; "
        f"similarity={report['similarity']:.4f}"
    )
    print(
        "records: "
        + ", ".join(
            f"{tag}={count}" for tag, count in sorted(report["opcode_counts"].items())
        )
    )
    divergence = report["first_divergence"]
    if divergence is None:
        print("first divergence: none")
    else:
        print(
            f"first divergence: {divergence['tag']} at left "
            f"#{divergence['left_index']} {divergence['left_offset_hex']} / right "
            f"#{divergence['right_index']} {divergence['right_offset_hex']}"
        )
    width = 46
    for row in report["rows"]:
        marker = {"equal": " ", "replace": "~", "insert": "+", "delete": "-"}[
            row["tag"]
        ]
        print(
            f"{marker} {_render_record(row['left'], width)} | "
            f"{_render_record(row['right'], width)}"
        )
        if row["tag"] != "equal":
            for side in ("left", "right"):
                if row[side] is not None:
                    print(f"    {side:<5s} {row[side]['raw_hex']}")
    if report["rows_truncated"]:
        print(f"(rows truncated at --limit {args.limit})")
    print(f"proof: {report['proof']}")
    return 0


def ucode_patch_command(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser() if args.output else None
    if (
        output is not None
        and output.resolve() == Path(args.stream).expanduser().resolve()
    ):
        print(
            "error: refusing to patch a retained stream in place; give a new -o",
            file=sys.stderr,
        )
        return 2
    fresh_count = 0
    if args.fresh_label:
        fresh_count = max(args.fresh_label, count_fresh_slots(args.records or ""))
    try:
        data, report = patch_stream(
            args.stream,
            stream_format=args.format,
            insert_at=args.insert_at,
            replace=args.replace,
            delete=args.delete,
            records_spec=args.records,
            fresh_label_count=fresh_count,
            allow_undecodable=args.allow_undecodable,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        report["output"] = str(output.resolve())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    position = report["position"]
    result = report["result"]
    print(
        f"{report['format']} {report['operation']}: at record "
        f"#{position['record_index']} ({position['offset_hex']}), "
        f"removed {position['removed_records']} record(s), "
        f"inserted {report['inserted']['bytes']} byte(s)"
    )
    if report["fresh_labels"]:
        print(
            f"fresh labels: {', '.join(str(item) for item in report['fresh_labels'])} "
            f"(highest existing label {report['max_existing_label']})"
        )
    for record in report["inserted"]["records"]:
        print(f"  + {record['name']:<10s} {record['raw_hex']}  {record['detail']}")
    print(
        f"result: {result['bytes']} bytes, {result['record_count']} record(s) "
        f"({result['record_delta']:+d}), sha256={result['sha256'][:12]}, "
        f"decodes={result['decodes']}"
    )
    if report.get("output"):
        print(f"wrote: {report['output']}")
    else:
        print("no -o given; nothing was written")
    print(f"proof: {report['proof']}")
    return 0


def _add_format_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=FORMATS,
        help="decode as this stream format instead of detecting it",
    )


def register_stream_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    for name, subject in (("ucode-window", "Ucode"), ("binasm-window", "Binasm")):
        window = commands.add_parser(
            name,
            help=f"print the decoded {subject} records around one position",
            description=(
                "Decode the records around a byte offset or a record index in "
                "a retained phase stream. The format is detected from record "
                "framing unless --format says otherwise, so both spellings of "
                "this command read either stream."
            ),
        )
        window.add_argument("stream", help="retained phase stream")
        window.add_argument(
            "--at",
            required=True,
            help="byte offset (decimal or 0x) or #record-index",
        )
        window.add_argument(
            "--radius",
            type=int,
            default=6,
            help="records shown on each side of the position (default: 6)",
        )
        _add_format_option(window)
        window.add_argument("--json", action="store_true", help="emit JSON")
        window.set_defaults(handler=stream_window_command)

    diff = commands.add_parser(
        "stream-diff",
        help="compare two phase streams record by record",
        description=(
            "Align two retained Ucode or Binasm streams by decoded record and "
            "report the first divergence plus a side-by-side edit script. The "
            "alignment is shift-tolerant, so one inserted record does not "
            "render every later record as changed."
        ),
    )
    diff.add_argument("left", help="first retained phase stream")
    diff.add_argument("right", help="second retained phase stream")
    _add_format_option(diff)
    diff.add_argument(
        "--limit",
        type=int,
        default=40,
        help="maximum rows printed (default: 40)",
    )
    diff.add_argument(
        "--context",
        type=int,
        default=2,
        help="equal records shown around each change (default: 2)",
    )
    diff.add_argument("--json", action="store_true", help="emit JSON")
    diff.set_defaults(handler=stream_diff_command)

    patch = commands.add_parser(
        "ucode-patch",
        help="insert, replace, or delete whole records in a phase stream",
        description=(
            "Record-level surgery on a retained Ucode (or Binasm) stream. The "
            "patched stream is decoded before it is written, so a record spec "
            "that breaks framing is refused instead of being replayed as "
            "damage. --fresh-label allocates label numbers above every label "
            "the stream already uses, which is what makes an inserted "
            "branch/label barrier safe."
        ),
    )
    patch.add_argument("stream", help="retained phase stream to read")
    patch.add_argument(
        "--insert-at",
        help="insert --records before this byte offset or #record-index",
    )
    patch.add_argument(
        "--replace",
        metavar="N[:M]",
        help="replace records N..M (half-open, default one record) with --records",
    )
    patch.add_argument(
        "--delete",
        metavar="N[:M]",
        help="delete records N..M (half-open, default one record)",
    )
    patch.add_argument(
        "--records",
        help=(
            "a hex-word spec or a path to one: words separated by whitespace "
            "or commas, records by | or a blank line, # comments, and "
            "{fresh}/{fresh+N} for allocated labels"
        ),
    )
    patch.add_argument(
        "--fresh-label",
        nargs="?",
        type=int,
        const=1,
        default=0,
        metavar="COUNT",
        help="allocate COUNT (default 1) label numbers above the stream's highest",
    )
    patch.add_argument(
        "--allow-undecodable",
        action="store_true",
        help="write the patched stream even if it no longer decodes",
    )
    patch.add_argument("-o", "--output", help="write the patched stream here")
    _add_format_option(patch)
    patch.add_argument("--json", action="store_true", help="emit JSON")
    patch.set_defaults(handler=ucode_patch_command)
