"""Command journey for the shiftability instrumentation.

``shift`` is a group with room in it. ``shift audit`` is the static half: one
map, one image, one pass, no build. ``shift rehearse`` -- the empirical half,
which relinks against a padded script and diffs the two images -- is the
command every "forthcoming" in the audit's output points at, and joins here
when it lands. They share a vocabulary (regions, the movable window, the
address model) and a reader's mental model, so they share a group rather than
arriving as two unrelated top-level words.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .census import census_status, evaluate_census, parse_census, print_census
from .cli_options import (
    add_census_argument,
    add_explain_keys_argument,
)
from .discovery import subcommand_listing_handler
from .ldmap import read_ld_map
from .mips_refs import WhitelistEntry
from .pins import PinCatalogue, default_pin_model, parse_whitelist_text, read_pin_files
from .schema import SHIFT_CENSUS_KEYS
from .shift_audit import build_shift_audit, shift_audit_lines
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_shift_commands", "shift_audit_command"]

#: How many rows each capped detail list prints, in both renderings. Every
#: list that hits it prints the cap beside the total, so a truncated list is
#: never mistaken for a short one.
DEFAULT_LIMIT = 40


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def shift_audit_command(args: argparse.Namespace) -> int:
    """Report where a linked project's addresses come from."""

    # The predicate is parsed before anything is read: a sweep that runs this
    # over every version of a ROM should not pay a 10 MB scan to learn that a
    # census key is misspelled.
    try:
        predicates = parse_census(args.census, allowed=SHIFT_CENSUS_KEYS)
    except ValueError as error:
        return _fail(str(error))

    try:
        whitelist: tuple[WhitelistEntry, ...] = tuple(
            entry
            for path in args.whitelist
            for entry in parse_whitelist_text(Path(path).read_text(encoding="utf-8"))
        )
        model = default_pin_model(whitelist=whitelist)
        pin_files = [*args.pins, *args.symbol_addrs]
        pins = (
            read_pin_files(pin_files, model=model)
            if pin_files
            else PinCatalogue(entries=(), sources=())
        )
        ldmap = read_ld_map(args.map)
        image = Path(args.image).read_bytes()
    except (OSError, ValueError) as error:
        return _fail(str(error))

    audit = build_shift_audit(
        ldmap=ldmap,
        image=image,
        pins=pins,
        model=model,
        blobs=args.blob,
        map_path=str(args.map),
        image_path=str(args.image),
    )
    payload = audit.as_dict(limit=args.limit)
    try:
        census = evaluate_census(predicates, payload)
    except ValueError as error:
        return _fail(str(error))

    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        emit_lines(
            shift_audit_lines(audit, limit=args.limit),
            width=args.width,
            pager=args.pager,
        )
        print_census(census)
    return census_status(census, otherwise=0)


_AUDIT_DESCRIPTION = (
    "Inventory a linked project's addresses without building anything. The "
    "pin half reads the project's own linker-input symbol files and says "
    "which addresses follow the layout (`gMainMemoryPool = main_BSS_END`) "
    "and which are written down (`D_B0000574 = 0xB0000574`). The scan half "
    "reads the image's data and blob regions and reports every word holding "
    "a value inside the movable VRAM window -- with the features that "
    "discriminate a real address reference from a packed field, a repeated "
    "struct constant, a fixed-point table value, or build-machine garbage. "
    "Tiers rank how confidently a word is a reference, never how dangerous "
    "it is: a linked ROM keeps no relocations, so only a shifted relink "
    "(`shift rehearse`, forthcoming) can say which references actually move."
)


def register_shift_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the ``shift`` group and its ``audit`` operation."""

    parser = commands.add_parser(
        "shift",
        help="inventory and rehearse a project's shiftability",
        description=(
            "Static inventory now, empirical rehearsal when it lands. Run "
            "`decomp-workbench shift audit --help` for the inventory."
        ),
    )
    operations = parser.add_subparsers(dest="shift_command")
    # Naming no operation is discovery, not a usage error -- see
    # `subcommand_listing_handler`.
    parser.set_defaults(handler=subcommand_listing_handler(parser))

    audit = operations.add_parser(
        "audit",
        help="report where a linked project's addresses come from",
        description=_AUDIT_DESCRIPTION,
        epilog=(
            "example: decomp-workbench shift audit --map build/game.map "
            "--image build/game.z64 --pins ver/symbols/undefined_syms.txt "
            "--blob .assets"
        ),
    )
    audit.add_argument(
        "--map", required=True, metavar="FILE", help="the linked `ld -Map` file"
    )
    audit.add_argument(
        "--image",
        required=True,
        metavar="FILE",
        help="the linked image the map describes",
    )
    audit.add_argument(
        "--pins",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "an ld-script symbol-assignment file such as "
            "ver/symbols/undefined_syms.txt; repeatable"
        ),
    )
    audit.add_argument(
        "--symbol-addrs",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "a splat `symbol_addrs` file; repeatable. Read with the same "
            "grammar as --pins, plus the `key:value` attributes splat writes "
            "in the trailing comment"
        ),
    )
    audit.add_argument(
        "--blob",
        action="append",
        default=[],
        metavar="SECTION",
        help=(
            "treat this output section as opaque bytes: scanned, but never "
            "split by its input records and never attributed to a symbol. "
            "Repeatable. Use it for DMA'd segments and boot code, whose VMA "
            "is a load target rather than a place code lives"
        ),
    )
    audit.add_argument(
        "--whitelist",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "addresses to accept as authentic, one `0xADDR reason` or "
            "`0xLO-0xHI reason` per line (# comments ignored, high bound "
            "inclusive). Repeatable. A reason is required: an address with "
            "no reason is one somebody re-derives later"
        ),
    )
    audit.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=(
            f"rows per capped detail list (default: {DEFAULT_LIMIT}); every "
            "list prints its cap beside its total"
        ),
    )
    audit.add_argument(
        "--json",
        action="store_true",
        help="emit a `decomp-workbench-shift-audit-v1` report",
    )
    add_census_argument(audit)
    add_explain_keys_argument(audit)
    add_terminal_arguments(audit)
    audit.set_defaults(handler=shift_audit_command, report_command="shift-audit")
