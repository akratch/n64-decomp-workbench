"""`decomp-workbench guide`: the command every `next:` footer now names.

The footer's job is to fit on a screen, so it can only afford one line per
lever. This command is where that line expands into the field guide's own
section, with the same width and pager behavior as the diagnosis the reader
just ran -- pasting the command should feel like scrolling further, not like
leaving the tool.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .field_guide import (
    GuideSection,
    render_topic,
    resolve_topic,
    sections,
    topic_index_lines,
)
from .terminal import add_terminal_arguments, emit_lines


def guide_command(args: argparse.Namespace) -> int:
    """Print the field-guide sections for a playbook, verdict, or lever."""

    if not args.topic:
        emit_lines(topic_index_lines(), width=args.width, pager=args.pager)
        return 0
    try:
        topic = resolve_topic(args.topic)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    available: dict[int, GuideSection] = {}
    missing: str | None = None
    try:
        available = sections()
    except FileNotFoundError as error:
        missing = str(error)
    # A missing document is a packaging failure, so it exits non-zero -- but
    # the reader asked a real question and the answer is already in memory.
    # Refusing to print it would repeat the mistake this command exists to fix.
    emit_lines(render_topic(topic, available), width=args.width, pager=args.pager)
    if missing is not None:
        print(f"error: {missing}", file=sys.stderr)
        return 2
    return 0


def register_guide_command(commands: argparse._SubParsersAction[Any]) -> None:
    """Register `guide` on an existing subparser set."""

    parser = commands.add_parser(
        "guide",
        help="print the field-guide levers for a playbook, verdict, or lever",
        description=(
            "Expand the lever family named by a `next:` footer into the field "
            "guide's own text. Run without a topic for the index."
        ),
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="playbook (forced-color-oracle), verdict (register-permutation), "
        "or lever number (19)",
    )
    add_terminal_arguments(parser)
    parser.set_defaults(handler=guide_command)
