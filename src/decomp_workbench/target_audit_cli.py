"""Command-line interface for the static target-object audit.

``target`` is a group with room for more static object checks later;
``audit`` is the one this wave ships. See `decomp_workbench.target_audit`
for what it checks and why, and `docs/target-audit.md` for the worked
cef4c narrative.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .discovery import subcommand_listing_handler
from .target_audit import (
    TARGET_AUDIT_SCHEMA,
    ElfFormatError,
    audit_target,
    target_audit_lines,
)

__all__ = ["register_target_commands", "target_audit_command"]

_VERDICT_EXIT = {"ok": 0, "warnings": 1, "defects": 2}

_AUDIT_DESCRIPTION = (
    "Verify a campaign/scratch target object's scope before anyone spends "
    "time matching against it. Static ELF sanity (sections, relocation "
    "entry counts, symbol table consistency), the literal-pool truncation "
    "heuristic (a function-owned literal pool externalized and its "
    "`.rodata` truncated at the jump table boundary to hide it -- the "
    "exact cef4c defect), and a data-scope report of every undefined "
    "symbol `.text` reaches through a %hi/%lo pair. --rom/--rom-offset/"
    "--va add an optional, read-only ROM cross-check: the bytes just past "
    "the object's own extracted `.rodata` extent, reported so a reader can "
    "see for themselves whether the pool belongs to the function."
)


def _parse_hex(value: str, *, name: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise ValueError(f"{name} is not a valid integer: {value!r}") from error


def target_audit_command(args: argparse.Namespace) -> int:
    try:
        rom_given = (args.rom, args.rom_offset, args.va)
        if any(item is not None for item in rom_given) and not all(
            item is not None for item in rom_given
        ):
            raise ValueError(
                "--rom, --rom-offset, and --va must be supplied together, "
                "or not at all"
            )
        rom_offset = (
            _parse_hex(args.rom_offset, name="--rom-offset")
            if args.rom_offset is not None
            else None
        )
        va = _parse_hex(args.va, name="--va") if args.va is not None else None
        audit = audit_target(
            args.target, rom=args.rom, rom_offset=rom_offset, va=va
        )
    except (OSError, ValueError, ElfFormatError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(audit.as_dict(), indent=2, sort_keys=True))
    else:
        print("\n".join(target_audit_lines(audit)))
    return _VERDICT_EXIT[audit.verdict]


def register_target_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the ``target`` group and its ``audit`` operation."""

    parser = commands.add_parser(
        "target",
        help="static checks against a campaign/scratch target object",
        description=(
            "Static checks a target object should pass before a campaign "
            "trusts its scope. Run `decomp-workbench target audit --help`."
        ),
    )
    operations = parser.add_subparsers(dest="target_command")
    parser.set_defaults(handler=subcommand_listing_handler(parser))

    audit = operations.add_parser(
        "audit",
        help="verify a target object's ELF scope and literal-pool extent",
        description=_AUDIT_DESCRIPTION,
        epilog=(
            "example: decomp-workbench target audit target.o --rom "
            "baserom.us.z64 --rom-offset 0x519a4 --va 0x800d5fc4"
        ),
    )
    audit.add_argument("target", help="the target/candidate object to audit")
    audit.add_argument(
        "--rom",
        metavar="FILE",
        help=(
            "a ROM image to read (read-only) for the optional cross-check. "
            "Goes with --rom-offset and --va; supplying one without the "
            "others is refused"
        ),
    )
    audit.add_argument(
        "--rom-offset",
        metavar="HEX",
        help=(
            "the ROM file offset of the *start* of this object's own "
            "extracted `.rodata` -- the same byte --va names. Used to "
            "derive where the bytes just past the extracted extent are"
        ),
    )
    audit.add_argument(
        "--va",
        metavar="HEX",
        help="the run-time address --rom-offset corresponds to",
    )
    audit.add_argument(
        "--json",
        action="store_true",
        help=f"emit a `{TARGET_AUDIT_SCHEMA}` report",
    )
    audit.set_defaults(handler=target_audit_command, report_command="target-audit")
