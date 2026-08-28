"""CLI for the `ranking` group: stamp a closeness ranking, and check one.

Both operations exist for one failure: a ranking is a measurement of a
tree, and the tree moves. Stamping is what the producer does; checking is
what every consumer does before it believes an ordering.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .ranking import (
    check_ranking_fresh,
    git_head,
    render_freshness,
    stamp_ranking,
)

_STAMP_DESCRIPTION = (
    "Record the tree a closeness ranking was measured against. The hash is "
    "read from the project's git HEAD unless --tree-hash names one. "
    "Re-stamping an unchanged ranking keeps the timestamp it already "
    "carries: 'generated_at' says when the measurement was taken, and a "
    "field that is refreshed on every run cannot say that."
)

_CHECK_DESCRIPTION = (
    "Compare a ranking's stamp with the tree in front of you. A ranking "
    "decays within hours -- a function that has since matched is still in "
    "it, and the ordering it encodes describes a tree that no longer "
    "exists -- so a consumer that orders work by it is entitled to know "
    "whether it is reading a measurement or a memory. Exit status is 0 "
    "when the stamp matches HEAD and 1 otherwise, including when the "
    "ranking carries no stamp at all."
)


def _root(args: argparse.Namespace) -> Path:
    """Where to ask git which commit this is.

    The ranking's own directory is the default because `git rev-parse` is
    happy anywhere inside a checkout, so a ranking under a project needs no
    configuration at all to be stamped.
    """

    if getattr(args, "project", None):
        directory = Path(args.project).expanduser()
        return directory if directory.is_dir() else directory.parent
    path = Path(args.path).expanduser().resolve()
    return path.parent if path.parent.exists() else Path.cwd()


def _resolved_hash(args: argparse.Namespace) -> str | None:
    if getattr(args, "tree_hash", None):
        return str(args.tree_hash)
    return git_head(_root(args))


def ranking_stamp_command(args: argparse.Namespace) -> int:
    tree_hash = _resolved_hash(args)
    if tree_hash is None:
        print(
            "error: could not read git HEAD for "
            f"{_root(args)}; pass --tree-hash to stamp explicitly",
            file=sys.stderr,
        )
        return 2
    try:
        result = stamp_ranking(args.path, tree_hash)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        state = "stamped" if result.changed else "already stamped"
        print(f"{state}: {result.path}")
        print(f"  tree_hash       {result.stamp.tree_hash}")
        print(f"  generated_at    {result.stamp.generated_at}")
    return 0


def ranking_check_command(args: argparse.Namespace) -> int:
    freshness = check_ranking_fresh(args.path, _resolved_hash(args))
    if args.json:
        print(json.dumps(freshness.as_dict(), indent=2, sort_keys=True))
    else:
        print("\n".join(render_freshness(freshness)))
    return 0 if freshness.fresh else 1


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", help="the ranking JSON to stamp or check")
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="the project directory whose git HEAD to read (default: the "
        "ranking's own directory)",
    )
    parser.add_argument(
        "--tree-hash",
        metavar="HASH",
        help="use this hash instead of asking git",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")


def register_ranking_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the `ranking` group and its two operations."""

    group = commands.add_parser(
        "ranking",
        help="stamp a closeness ranking with its tree, and check its freshness",
        description=(
            "A closeness ranking is a measurement of one tree and decays as "
            "soon as that tree moves. Stamp it when it is produced, check it "
            "before ordering work by it."
        ),
    )
    operations = group.add_subparsers(dest="ranking_command")
    group.set_defaults(handler=_group_listing(group))

    stamp = operations.add_parser(
        "stamp",
        help="record the tree hash a ranking was measured against",
        description=_STAMP_DESCRIPTION,
        epilog="example: decomp-workbench ranking stamp config/ranking.json",
    )
    _add_shared_arguments(stamp)
    stamp.set_defaults(handler=ranking_stamp_command, report_command="ranking-stamp")

    check = operations.add_parser(
        "check",
        help="report whether a ranking still describes the current tree",
        description=_CHECK_DESCRIPTION,
        epilog="example: decomp-workbench ranking check config/ranking.json",
    )
    _add_shared_arguments(check)
    check.set_defaults(handler=ranking_check_command, report_command="ranking-check")


def _group_listing(parser: argparse.ArgumentParser) -> Any:
    from .discovery import subcommand_listing_handler

    return subcommand_listing_handler(parser)


__all__ = [
    "ranking_check_command",
    "ranking_stamp_command",
    "register_ranking_commands",
]
