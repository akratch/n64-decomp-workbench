"""Predictable terminal width and pager behavior."""

from __future__ import annotations

import argparse
import os
import pydoc
import re
import shutil
import sys
from collections.abc import Sequence
from typing import TextIO

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


WEB_COLORS = ("36", "33", "35", "32", "34", "31")

#: One colour per verdict family, so a wall of reports is scannable by hue.
#:
#: The verdict is the most important token on the screen and used to be the
#: only plain one, while a downstream explanatory sentence rendered bold red.
#: Green is reserved for "nothing left to explain"; every mismatch family gets
#: its own hue so two adjacent runs never look alike by accident.
VERDICT_COLORS: dict[str, str] = {
    "exact": "32",
    "instruction-exact": "32",
    "words-identical": "32",
    "instruction-words-identical": "32",
    "constant": "33",
    "constant-mismatch": "33",
    "operand-mismatch": "33",
    "commutative-order": "34",
    "schedule": "36",
    "schedule-mismatch": "36",
    "structure": "35",
    "structure-mismatch": "35",
    "phase-shift": "95",
    "register-permutation": "91",
    "allocation": "31",
    "allocation-mismatch": "31",
    "relocation-layout-mismatch": "90",
    "unknown-relocation": "1;31",
}

#: Anything unrecognized, including every `mixed(...)` composition.
DEFAULT_VERDICT_COLOR = "31"


class Painter:
    """Minimal ANSI painter with a monochrome-safe default."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled and text else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def warn(self, text: str) -> str:
        return self._wrap("1;31", text)

    def web(self, number: int, text: str) -> str:
        return self._wrap(WEB_COLORS[(number - 1) % len(WEB_COLORS)], text)

    def verdict(self, name: str, text: str | None = None) -> str:
        """Colour a verdict value by its family."""

        code = VERDICT_COLORS.get(name, DEFAULT_VERDICT_COLOR)
        return self._wrap(f"1;{code}", name if text is None else text)


def warn_to_stderr(note: str) -> None:
    """Print one input-recovery note where it cannot corrupt `--json` stdout."""

    print(f"warning: {note}", file=sys.stderr)


def add_color_argument(parser: argparse.ArgumentParser) -> None:
    """Offer ANSI colour on any command that prints a verdict.

    `compare` and `compare-dumps` had no such option, so the one journey that
    scans many reports at once -- batch triage -- was the only one that could
    never colourize them.
    """

    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="ANSI coloring; every label and annotation is present without it",
    )


def resolve_color(choice: str, *, stream: TextIO | None = None) -> bool:
    """Decide whether ANSI output is appropriate."""

    if choice == "always":
        return True
    if choice == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    target = sys.stdout if stream is None else stream
    return bool(getattr(target, "isatty", lambda: False)())


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


def visible_length(text: str) -> int:
    """Return the printed width of `text`, ignoring ANSI colour sequences."""

    return len(ANSI_RE.sub("", text))


def visible_ljust(text: str, width: int) -> str:
    """Pad `text` to `width` printed columns, ignoring ANSI colour sequences.

    ``str.ljust`` counts escape bytes as characters, so a coloured cell padded
    with it collapses the column that the eye uses to compare two instructions
    side by side.
    """

    return text + " " * max(0, width - visible_length(text))


def resolve_width(width: int) -> int:
    """Return the column budget a renderer should lay out for.

    ``0`` means unlimited and ``-1`` means "ask the terminal", the same two
    sentinels `emit_lines` consumes. Renderers need the resolved number *before*
    they build a line, because deciding what to drop is a layout decision and
    `emit_lines` can only ever cut from the right.
    """

    if width == -1:
        return shutil.get_terminal_size(fallback=(120, 24)).columns
    return width


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
