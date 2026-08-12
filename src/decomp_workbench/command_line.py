"""Shell-free command-template parsing with native Windows path support."""

from __future__ import annotations

import os
import shlex


def split_command(value: str, *, windows: bool | None = None) -> list[str]:
    """Split a user-supplied command without asking a shell to interpret it.

    POSIX command templates use the familiar :mod:`shlex` grammar. On Windows,
    backslashes are path separators rather than general escape characters, so
    POSIX ``shlex.split`` silently corrupts paths such as ``C:\\IDO\\cc.exe``.
    The Windows lexer follows the Microsoft backslash-before-double-quote
    rules while also accepting single quotes as a convenience for templates
    shared with POSIX hosts.
    """

    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return shlex.split(value)
    return _split_windows_command(value)


def _split_windows_command(value: str) -> list[str]:
    arguments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    started = False
    index = 0

    while index < len(value):
        character = value[index]
        if quote is None and character.isspace():
            if started:
                arguments.append("".join(current))
                current = []
                started = False
            index += 1
            continue
        if character == "'" and quote != '"':
            quote = None if quote == "'" else "'"
            started = True
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            started = True
            index += 1
            continue
        if character == "\\" and quote != "'":
            end = index
            while end < len(value) and value[end] == "\\":
                end += 1
            count = end - index
            if end < len(value) and value[end] == '"':
                current.extend("\\" * (count // 2))
                if count % 2:
                    current.append('"')
                else:
                    quote = None if quote == '"' else '"'
                started = True
                index = end + 1
                continue
            current.extend("\\" * count)
            started = True
            index = end
            continue
        current.append(character)
        started = True
        index += 1

    if quote is not None:
        raise ValueError("No closing quotation")
    if started:
        arguments.append("".join(current))
    return arguments
