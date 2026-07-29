"""Run the documented fixture commands and check their documented output.

The narrative documentation (`docs/START_HERE.md` and its neighbours) is only
useful if a reader can paste its command lines and see what the page says they
will see. This test extracts every ``decomp-workbench`` command line in the
documentation that reads a shipped fixture, runs it in process, and asserts
both that it succeeds and that any output the page claims for it is really
there.

The contract a document opts into:

* a ``sh`` fenced block holding a ``decomp-workbench`` command whose arguments
  mention a redistributable fixture or trace under ``examples/`` is executed
  from the repository root, and must exit ``0``;
* a ``text`` fenced block is checked against the most recent such command in
  the same document, line by line, with runs of whitespace collapsed and a
  trailing ``...`` meaning "the line continues";
* a ``text`` block with no preceding fixture command in its document is
  prose — a diagram or an illustrative transcript — and is ignored.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shlex
import unittest
from pathlib import Path
from typing import ClassVar, NamedTuple

from decomp_workbench.cli import main

ROOT = Path(__file__).resolve().parents[1]

#: Documentation that is browsed by a reader rather than shipped as data. The
#: list is explicit so a stray Markdown file in a build or virtual-environment
#: directory can never turn into a test case.
DOCUMENTS = (
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / "examples").rglob("*.md")),
)

#: The command whose invocations this test owns. Any other program in a fenced
#: block belongs to the reader's project and cannot be run here.
PROGRAM = "decomp-workbench"

#: Markers that make a command line runnable without a ROM or compiler.
RUNNABLE_MARKERS = ("examples/fixtures/", "examples/traces/")

SHELL_LANGUAGES = frozenset({"sh", "shell", "bash", "console"})
FENCE_RE = re.compile(r"^\s*```(\S*)\s*$")


class DocumentedCommand(NamedTuple):
    """One runnable command line, with whatever output the page promises."""

    document: Path
    line: int
    argv: tuple[str, ...]
    expectations: tuple[tuple[int, str], ...]

    def __str__(self) -> str:
        relative = self.document.relative_to(ROOT)
        return f"{relative}:{self.line}: {PROGRAM} {' '.join(self.argv)}"


def collapse(text: str) -> str:
    """Return `text` with every run of whitespace reduced to one space.

    Report columns are padded for the eye (``words=   0``). Collapsing lets a
    document quote a line as it reads without the test becoming a check on
    column widths, which are presentation and are allowed to change.
    """

    return " ".join(text.split())


def fenced_blocks(document: Path) -> list[tuple[int, str, list[str]]]:
    """Return `(line number, info string, body lines)` for each fenced block."""

    blocks: list[tuple[int, str, list[str]]] = []
    info: str | None = None
    start = 0
    body: list[str] = []
    for number, line in enumerate(
        document.read_text(encoding="utf-8").splitlines(), start=1
    ):
        fence = FENCE_RE.match(line)
        if fence is None:
            if info is not None:
                body.append(line)
            continue
        if info is None:
            info, start, body = fence.group(1), number, []
        else:
            blocks.append((start, info, body))
            info = None
    return blocks


def command_lines(body: list[str]) -> list[str]:
    """Return the block's shell commands with continuations joined."""

    commands: list[str] = []
    pending = ""
    for raw in body:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        commands.append((pending + line).strip())
        pending = ""
    if pending:
        commands.append(pending.strip())
    return commands


def split_arguments(command: str) -> tuple[str, ...]:
    """Split a documented command line into arguments.

    `shlex` is deliberate: the documented lines quote flag values the way a
    reader would type them (``--compiler-flags='-O2 -mips2'``), and a naive
    split would hand the quotes to `argparse`.
    """

    return tuple(shlex.split(command))


def discover() -> list[DocumentedCommand]:
    """Return every documented fixture command, with its promised output."""

    discovered: list[DocumentedCommand] = []
    for document in DOCUMENTS:
        pending: list[tuple[int, tuple[str, ...], list[tuple[int, str]]]] = []
        for line, info, body in fenced_blocks(document):
            language = info.lower()
            if language in SHELL_LANGUAGES:
                for command in command_lines(body):
                    arguments = split_arguments(command)
                    if not arguments or arguments[0] != PROGRAM:
                        continue
                    if not any(
                        marker in item
                        for item in arguments
                        for marker in RUNNABLE_MARKERS
                    ):
                        continue
                    pending.append((line, arguments[1:], []))
            elif language == "text" and pending:
                offset = line
                for index, raw in enumerate(body, start=1):
                    text = raw.strip()
                    if text:
                        pending[-1][2].append((offset + index, text))
        discovered.extend(
            DocumentedCommand(document, line, argv, tuple(expected))
            for line, argv, expected in pending
        )
    return discovered


class DocumentedCommandTests(unittest.TestCase):
    """Every command line a reader can paste really runs and really says that."""

    maxDiff = None
    commands: ClassVar[list[DocumentedCommand]] = []

    @classmethod
    def setUpClass(cls) -> None:
        cls.commands = discover()

    def run_documented(self, command: DocumentedCommand) -> tuple[int, str]:
        """Run one documented command from the repository root."""

        stdout = io.StringIO()
        previous = Path.cwd()
        os.chdir(ROOT)
        try:
            with contextlib.redirect_stdout(stdout):
                status = main(list(command.argv))
        finally:
            os.chdir(previous)
        return status, stdout.getvalue()

    def test_documentation_has_runnable_examples(self) -> None:
        """A silent extractor that found nothing would pass every other test."""

        documents = {command.document for command in self.commands}
        self.assertIn(ROOT / "docs" / "START_HERE.md", documents)
        self.assertIn(ROOT / "README.md", documents)
        self.assertGreaterEqual(len(self.commands), 8)

    def test_documented_commands_succeed(self) -> None:
        failures: list[str] = []
        for command in self.commands:
            status, _ = self.run_documented(command)
            if status != 0:
                failures.append(f"{command} -> exit {status}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_documented_output_is_real(self) -> None:
        failures: list[str] = []
        for command in self.commands:
            if not command.expectations:
                continue
            _, output = self.run_documented(command)
            actual = collapse(output)
            for line, expected in command.expectations:
                wanted = collapse(expected.removesuffix("..."))
                if not wanted:
                    continue
                if wanted not in actual:
                    relative = command.document.relative_to(ROOT)
                    failures.append(
                        f"{relative}:{line}: not in the output of "
                        f"`{PROGRAM} {' '.join(command.argv)}`:\n  {wanted}"
                    )
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
