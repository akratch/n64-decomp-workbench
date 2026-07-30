"""Predictable terminal width and pager behavior."""

from __future__ import annotations

import argparse
import pydoc
import re
import shutil
import sys
from collections.abc import Sequence

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def terminal_width(value: str) -> int:
    """Parse a ``--width`` argument into the sentinel `emit_lines` expects.

    ``auto`` is ``-1`` and ``unlimited`` is ``0`` so that the default of ``0``
    means "do not truncate" without a separate flag. Kept here beside
    `emit_lines`, which is the only reader of those sentinels, so every command
    that bounds its output spells the option the same way.
    """

    if value == "auto":
        return -1
    if value in {"unlimited", "none"}:
        return 0
    try:
        width = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "width must be auto, unlimited, or a positive integer"
        ) from None
    if width < 20:
        raise argparse.ArgumentTypeError("width must be at least 20 columns")
    return width


def add_terminal_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--width``/``--pager`` controls to one command."""

    parser.add_argument(
        "--width",
        type=terminal_width,
        default=0,
        metavar="COLUMNS",
        help="bound terminal lines; use auto or unlimited (default: unlimited)",
    )
    parser.add_argument(
        "--pager",
        choices=("auto", "always", "never"),
        default="auto",
        help="page long human output (default: auto on a TTY)",
    )


def fit_line(line: str, width: int) -> str:
    """Bound a rendered line without splitting terminal escape sequences."""

    visible = ANSI_RE.sub("", line)
    if width <= 0 or len(visible) <= width:
        return line
    if width == 1:
        return "…"
    budget = width - 1
    parts: list[str] = []
    position = 0
    consumed = 0
    has_ansi = bool(ANSI_RE.search(line))
    for match in ANSI_RE.finditer(line):
        plain = line[position : match.start()]
        take = min(len(plain), budget - consumed)
        parts.append(plain[:take])
        consumed += take
        if consumed >= budget:
            break
        parts.append(match.group())
        position = match.end()
    else:
        plain = line[position:]
        parts.append(plain[: budget - consumed])
    return "".join(parts) + "…" + ("\033[0m" if has_ansi else "")


def emit_lines(
    lines: Sequence[str],
    *,
    width: int,
    pager: str,
) -> None:
    """Render lines directly or through the user's pager when appropriate."""

    effective_width = (
        shutil.get_terminal_size(fallback=(120, 24)).columns if width == -1 else width
    )
    text = "\n".join(fit_line(line, effective_width) for line in lines) + "\n"
    use_pager = pager == "always" or (
        pager == "auto"
        and sys.stdout.isatty()
        and text.count("\n") > shutil.get_terminal_size(fallback=(120, 24)).lines
    )
    if use_pager:
        pydoc.pager(text)
    else:
        print(text, end="")
