"""A shipped shell example must work in the reader's shell, not only in mine.

`python3 bands.py $LABS`, with `LABS` a newline-joined list, works under `bash`
and silently does not under `zsh`: zsh does not word-split a parameter
expansion, so the whole list arrives as one argument and the run dies inside
`objdump` with "file name too long". That reads as a scorer bug rather than a
quoting bug, and it cost one campaign a stage before anyone recognised it —
every scorer invocation in that campaign's own drivers had the same shape.

The rule this enforces on everything the repository ships: **no shipped shell
example expands a variable unquoted.** Either quote it, in which case it is one
argument in every shell, or do not put a list in a variable at all — every
list-valued option here also accepts `--OPTION-from FILE`.
"""

from __future__ import annotations

import re
import unittest
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCUMENTS = (
    ROOT / "README.md",
    *sorted((ROOT / "docs").rglob("*.md")),
    *sorted((ROOT / "examples").rglob("*.md")),
)

SCRIPTS = tuple(
    path
    for path in sorted(ROOT.rglob("*.sh"))
    if not any(part in {".git", ".venv", "node_modules"} for part in path.parts)
)

SHELL_LANGUAGES = frozenset({"sh", "shell", "bash", "console", "zsh"})
FENCE_RE = re.compile(r"^\s*```(\S*)\s*$")

_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?(?P<name>[A-Za-z_]\w*)=")
_EXPANSION_RE = re.compile(r"\$(?:\{(?P<braced>\w+)[^}]*\}|(?P<bare>\w+))")

#: Expansions that are never a word list in these examples, and that quoting
#: would make unreadable in the one place they appear.
_ALWAYS_FINE = frozenset({"PWD", "HOME", "PATH", "SHELL", "PS1", "IFS"})

#: A block that is *demonstrating* the mistake says so, on its own line, and is
#: skipped. Troubleshooting pages have to be able to print the broken form.
_ALLOW_MARKER = "shell-lint: allow-unquoted"


def shell_blocks(document: Path) -> list[tuple[int, list[str]]]:
    """Return `(first body line number, body lines)` for each shell block."""

    blocks: list[tuple[int, list[str]]] = []
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
            if info.lower() in SHELL_LANGUAGES:
                blocks.append((start + 1, body))
            info = None
    return blocks


def unquoted_expansions(lines: list[str]) -> list[tuple[int, str]]:
    """Return every unquoted expansion of a variable this snippet assigns.

    Quoting state is tracked across the line so `"$D/usr/lib/acpp"` is not a
    finding and `$D/usr/lib/acpp` is. A variable the snippet never assigns is
    the reader's environment and not this repository's to police.
    """

    if any(_ALLOW_MARKER in line for line in lines):
        return []
    assigned: set[str] = set()
    findings: list[tuple[int, str]] = []
    for offset, raw in enumerate(lines):
        line = raw
        assignment = _ASSIGNMENT_RE.match(raw)
        if assignment is not None:
            assigned.add(assignment.group("name"))
            # An assignment's own value is never field-split, in any shell, so
            # `OBJDUMP=${OBJDUMP:-/opt/…}` is safe. Scan only what follows it.
            line = raw[_assignment_end(raw) :]
        for index, name in _expansions(line):
            if name in assigned and name not in _ALWAYS_FINE:
                findings.append((offset, raw.strip()))
                del index
                break
    return findings


def _assignment_end(line: str) -> int:
    """Return the offset just past the leading assignment word."""

    single = False
    double = False
    depth = 0
    for index, char in enumerate(line.lstrip()):
        if char == "\\":
            continue
        if char == "'" and not double:
            single = not single
        elif char == '"' and not single:
            double = not double
        elif char in "{(" and not single and not double:
            depth += 1
        elif char in "})" and not single and not double:
            depth -= 1
        elif char.isspace() and not single and not double and depth <= 0:
            return len(line) - len(line.lstrip()) + index
    return len(line)


def _expansions(line: str) -> Iterator[tuple[int, str]]:
    """Yield `(index, name)` for each expansion outside single or double quotes."""

    single = False
    double = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\":
            index += 2
            continue
        if char == "'" and not double:
            single = not single
        elif char == '"' and not single:
            double = not double
        elif (
            char == "#"
            and not single
            and not double
            and (index == 0 or line[index - 1].isspace())
        ):
            return
        elif char == "$" and not single and not double:
            match = _EXPANSION_RE.match(line, index)
            if match is not None:
                yield index, match.group("braced") or match.group("bare")
                index = match.end()
                continue
        index += 1


class ShellSafetyTests(unittest.TestCase):
    maxDiff = None

    def test_no_shipped_example_expands_a_variable_unquoted(self) -> None:
        failures: list[str] = []
        for document in DOCUMENTS:
            for start, body in shell_blocks(document):
                for offset, text in unquoted_expansions(body):
                    failures.append(
                        f"{document.relative_to(ROOT)}:{start + offset}: {text}"
                    )
        self.assertEqual(
            failures,
            [],
            "Quote the expansion, or take the list from a file: zsh does not "
            "word-split a parameter expansion, so an unquoted list arrives as "
            f"one argument. A block demonstrating the mistake may carry "
            f"`# {_ALLOW_MARKER}`.\n" + "\n".join(failures),
        )

    def test_no_shipped_script_expands_a_variable_unquoted(self) -> None:
        failures: list[str] = []
        for script in SCRIPTS:
            lines = script.read_text(encoding="utf-8").splitlines()
            for offset, text in unquoted_expansions(lines):
                failures.append(f"{script.relative_to(ROOT)}:{offset + 1}: {text}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_the_lint_catches_the_shape_that_cost_a_stage(self) -> None:
        """A scanner that found nothing would pass the two tests above."""

        found = unquoted_expansions(
            ["LABS=$(ls o/*.o)", "python3 bands.py $LABS"],
        )
        self.assertEqual(len(found), 1)
        self.assertIn("bands.py $LABS", found[0][1])

    def test_a_block_demonstrating_the_mistake_can_say_so(self) -> None:
        self.assertEqual(
            unquoted_expansions(
                [f"# {_ALLOW_MARKER}", "LABS=$(ls o/*.o)", "run $LABS"]
            ),
            [],
        )

    def test_quoting_it_is_accepted(self) -> None:
        self.assertEqual(
            unquoted_expansions(["D=/opt/irix", 'run -L "$D" "$D/usr/lib/acpp"']),
            [],
        )

    def test_a_variable_the_snippet_never_assigns_is_not_policed(self) -> None:
        self.assertEqual(unquoted_expansions(["run $PROJECT_ROOT/build.sh"]), [])

    def test_an_expansion_inside_a_comment_is_not_a_finding(self) -> None:
        self.assertEqual(
            unquoted_expansions(["D=/opt", "# pass $D to the wrapper"]), []
        )

    def test_every_repeatable_sweep_option_offers_a_file_input(self) -> None:
        """The list-valued options are the ones a driver builds in a variable."""

        import argparse

        from decomp_workbench.cli import build_parser

        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        expected = {
            "sweep-regress": "--construct-from",
            "sweep-hoist": "--carrier-from",
            "sweep-commute": "--line-from",
            "sweep-fuse": "--donor-from",
        }
        for command, option in expected.items():
            with self.subTest(command=command):
                help_text = subparsers.choices[command].format_help()
                self.assertIn(option, help_text)
                self.assertIn("--frozen-from", help_text)


if __name__ == "__main__":
    unittest.main()
