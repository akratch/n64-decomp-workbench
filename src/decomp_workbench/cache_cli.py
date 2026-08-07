"""CLI registration for safe cache lifecycle commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .cache import cache_status, parse_duration, prune_cache, restore_pruned_cache
from .discovery import subcommand_listing_handler

DEFAULT_CACHE = ".decomp-workbench/cache"
DEFAULT_TRASH = ".decomp-workbench/trash"


def cache_status_command(args: argparse.Namespace) -> int:
    try:
        report = cache_status(args.cache_dir)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"cache: {report['files']} file(s), {report['bytes']} byte(s) "
            f"({report['path']})"
        )
        if not report["exists"]:
            print("state: empty (the cache directory has not been created yet)")
    return 0


def cache_prune_command(args: argparse.Namespace) -> int:
    try:
        older_than = parse_duration(args.older_than)
        report = prune_cache(
            args.cache_dir,
            older_than=older_than,
            apply=args.apply,
            trash_root=args.trash_dir,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"cache prune {report['mode']}: {report['selected_files']} file(s), "
            f"{report['selected_bytes']} byte(s)"
        )
        if args.apply and report["trash_directory"]:
            print(f"moved to: {report['trash_directory']}")
            print(
                f"recovery: decomp-workbench cache restore {report['trash_directory']}"
            )
        elif not args.apply and report["selected_files"]:
            print("next: repeat with --apply to move these files to recoverable trash")
    return 0


def cache_restore_command(args: argparse.Namespace) -> int:
    try:
        restored = restore_pruned_cache(args.trash_directory, args.cache_dir)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = {
        "schema": "decomp-workbench-cache-restore-v1",
        "cache_directory": str(Path(args.cache_dir).expanduser().resolve()),
        "trash_directory": str(Path(args.trash_directory).expanduser().resolve()),
        "restored_files": restored,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"restored {restored} cache file(s) into {payload['cache_directory']}")
    return 0


def register_cache_commands(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "cache",
        help="inspect and recoverably prune compiled-object cache entries",
        description=(
            "Cache cleanup is always explicit. Prune defaults to a dry run and "
            "--apply moves entries to recoverable trash instead of deleting them."
        ),
    )
    operations = parser.add_subparsers(dest="cache_command")
    parser.set_defaults(handler=subcommand_listing_handler(parser))

    status = operations.add_parser("status", help="show cache size and age")
    status.add_argument(
        "--cache-dir",
        default=DEFAULT_CACHE,
        help=f"content cache (default: {DEFAULT_CACHE})",
    )
    status.add_argument("--json", action="store_true", help="emit JSON")
    status.set_defaults(handler=cache_status_command, report_command="cache-status")

    prune = operations.add_parser(
        "prune",
        help="plan or recoverably apply an age-based prune",
    )
    prune.add_argument(
        "--older-than",
        required=True,
        metavar="DURATION",
        help="minimum age, for example 30d, 12h, or 1w2d",
    )
    prune.add_argument(
        "--apply",
        action="store_true",
        help="move selected files to trash; omitted means dry-run",
    )
    prune.add_argument(
        "--cache-dir",
        default=DEFAULT_CACHE,
        help=f"content cache (default: {DEFAULT_CACHE})",
    )
    prune.add_argument(
        "--trash-dir",
        default=DEFAULT_TRASH,
        help=f"recoverable trash root (default: {DEFAULT_TRASH})",
    )
    prune.add_argument("--json", action="store_true", help="emit JSON")
    prune.set_defaults(handler=cache_prune_command, report_command="cache-prune")

    restore = operations.add_parser(
        "restore",
        help="restore a prune trash directory without overwriting entries",
    )
    restore.add_argument("trash_directory")
    restore.add_argument(
        "--cache-dir",
        default=DEFAULT_CACHE,
        help=f"content cache (default: {DEFAULT_CACHE})",
    )
    restore.add_argument("--json", action="store_true", help="emit JSON")
    restore.set_defaults(handler=cache_restore_command, report_command="cache-restore")
