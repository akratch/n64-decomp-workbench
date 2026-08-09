"""Reading decompiled C as text, with the block structure made explicit.

The workbench does not parse C. It reads the dialect a decompilation project
actually writes -- one statement per line, braces on their own lines, no
macros in the middle of an expression -- and it says so, because the
difference between "a parser proved this" and "the text says this" is the
whole difference between a verifier and a probe.

Two things every source probe here needs and neither had:

* **Where each statement sits in the block structure.** A definition inside an
  `if` that has since closed does not reach a later statement; a definition in
  a block still open at that statement does. Comparing brace *depths* gets
  this wrong (two sibling `if` bodies are both depth 2); comparing the open
  *block path* gets it right.
* **Which statements are inside a loop.** The same construct is free outside a
  loop body and expensive inside one -- one campaign measured the identical
  discarded read at `ni + 0` outside and `ni + 8` inside -- so a candidate
  list that does not separate them is a list of two different experiments.

`composition` already owned the identifier and assignment regexes, and they
live here now so there is one answer to "does this line write `V`" rather
than one per probe.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass

__all__ = [
    "CSourceError",
    "Declaration",
    "Statement",
    "declaration_line",
    "declarations",
    "defines",
    "definition_lines",
    "identifiers",
    "reads",
    "scan_statements",
    "strip_noncode",
    "takes_address",
]


class CSourceError(ValueError):
    """The source could not be read the way a probe needs it."""


#: C identifiers that are not struct or union member selections: `sp4A0`
#: matches, the `count` of `header->count` does not. A member name is owned by
#: a type, so it can never be the local a probe is reasoning about.
IDENTIFIER_RE = re.compile(r"(?<![\w.])(?<!->)[A-Za-z_]\w*")

#: Words that are never a local.
KEYWORDS = frozenset(
    """
    auto break case char const continue default do double else enum extern
    float for goto if inline int long register restrict return short signed
    sizeof static struct switch typedef union unsigned void volatile while
    NULL
    """.split()
)

#: `name =` but not `name ==`, and the compound assignments. A write to the
#: identifier, as far as text can tell.
ASSIGN_TEMPLATE = r"(?<![\w.>])%s\s*(?:\[[^\];]*\])?\s*(?:=(?!=)|[-+*/%%&|^]=|<<=|>>=)"

#: `&name`, `name++`, `--name`: not a plain read. Treated as "may define".
MAY_DEFINE_TEMPLATE = r"(?:&\s*%s\b|\+\+\s*%s\b|%s\s*\+\+|--\s*%s\b|%s\s*--)"

#: A declaration of the identifier: a type, then the name, then `;`/`=`/`,`.
DECLARE_TEMPLATE = (
    r"^\s*(?:[A-Za-z_]\w*\s*[\w*\s]*?)\b%s\s*(?:\[[^\]]*\])?\s*(?:[;,=](?!=))"
)

#: `&name` alone: the one construct that lets a callee write a local, and so
#: the one that decides whether "no call between these two reads can have
#: changed it" is a claim or a guess.
ADDRESS_TEMPLATE = r"&\s*%s\b"

_LOOP_RE = re.compile(r"(?<![\w.])(for|while|do)(?![\w.])")
_SWITCH_RE = re.compile(r"(?<![\w.])switch(?![\w.])")
#: Reasoning about textual order past one of these is not reasoning about
#: control flow, so a statement carrying one is flagged rather than trusted.
_CONTROL_BREAK_RE = re.compile(r"^(case\b|default\s*:|goto\b|break\b|continue\b)")


def strip_noncode(text: str) -> list[str]:
    """Return the file's lines with comments and string bodies blanked out.

    Blanked, not removed: every downstream report cites a line number, and a
    probe whose line numbers do not match the reader's editor is worse than no
    probe. A `/*` inside a string and a quote inside a comment are both
    handled, because a decompiled file has plenty of both.
    """

    result: list[str] = []
    in_block = False
    for line in text.splitlines():
        out: list[str] = []
        index = 0
        length = len(line)
        while index < length:
            char = line[index]
            if in_block:
                if line.startswith("*/", index):
                    in_block = False
                    out.append("  ")
                    index += 2
                    continue
                out.append(" ")
                index += 1
                continue
            if line.startswith("/*", index):
                in_block = True
                out.append("  ")
                index += 2
                continue
            if line.startswith("//", index):
                out.append(" " * (length - index))
                break
            if char in "\"'":
                quote = char
                out.append(char)
                index += 1
                while index < length:
                    if line[index] == "\\" and index + 1 < length:
                        out.append("  ")
                        index += 2
                        continue
                    if line[index] == quote:
                        out.append(quote)
                        index += 1
                        break
                    out.append(" ")
                    index += 1
                continue
            out.append(char)
            index += 1
        result.append("".join(out))
    return result


def identifiers(line: str) -> collections.Counter[str]:
    """Count the identifiers on one line, ignoring keywords and members."""

    return collections.Counter(
        name
        for name in IDENTIFIER_RE.findall(line)
        if name not in KEYWORDS and not name.isdigit()
    )


def defines(line: str, name: str) -> bool:
    """Whether `line` writes `name`, as far as the text can say."""

    quoted = re.escape(name)
    if re.search(ASSIGN_TEMPLATE % quoted, line):
        return True
    if re.search(MAY_DEFINE_TEMPLATE % ((quoted,) * 5), line):
        return True
    return bool(re.search(DECLARE_TEMPLATE % quoted, line))


def declares_without_initializer(line: str, name: str) -> bool:
    quoted = re.escape(name)
    if not re.search(DECLARE_TEMPLATE % quoted, line):
        return False
    return not re.search(ASSIGN_TEMPLATE % quoted, line)


def declaration_line(lines: list[str], name: str) -> int | None:
    """Where `name` is declared, or `None` if this file never declares it."""

    pattern = re.compile(DECLARE_TEMPLATE % re.escape(name))
    for number, line in enumerate(lines, 1):
        if pattern.search(line):
            return number
    return None


def definition_lines(lines: list[str], name: str) -> list[int]:
    """Every line that writes `name`, excluding a bare declaration."""

    return [
        number
        for number, line in enumerate(lines, 1)
        if not declares_without_initializer(line, name) and defines(line, name)
    ]


def reads(line: str, name: str) -> bool:
    """Whether `line` mentions `name` as a value rather than declaring it."""

    if name not in identifiers(line):
        return False
    return not declares_without_initializer(line, name)


def takes_address(lines: list[str], name: str) -> list[int]:
    """Every line that takes `name`'s address.

    The whole purity argument turns on this list being empty: a local whose
    address is never taken cannot be written by any callee, so a call between
    two reads of it cannot have changed the value. One `&` and the argument is
    gone.
    """

    pattern = re.compile(ADDRESS_TEMPLATE % re.escape(name))
    return [number for number, line in enumerate(lines, 1) if pattern.search(line)]


#: A local declaration in the dialect this reads: type words, optional stars,
#: then one or more declarators, then `;`. The type half is deliberately loose
#: (a project's own typedefs are types too) and the exclusions below carry the
#: weight: a line whose first word is a keyword, or whose declarator half opens
#: a parenthesis, is not a local declaration.
_DECLARATION_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<type>(?:(?:const|static|volatile|register|unsigned|signed|struct|"
    r"union|enum|long|short)\s+)*[A-Za-z_]\w*(?:\s+(?:long|int|char|double))*"
    r"(?:\s*\*)*)"
    r"\s+(?P<declarators>[^;]+);\s*$"
)

#: Words that open a statement, never a declaration.
_NOT_A_TYPE = frozenset(
    """
    break case continue default do else for goto if return sizeof switch while
    """.split()
)

_DECLARATOR_RE = re.compile(
    r"^\s*(?P<stars>\**)\s*(?P<name>[A-Za-z_]\w*)\s*"
    r"(?P<array>(?:\[[^\]]*\])*)\s*(?:=\s*(?P<initializer>.+))?$"
)


@dataclass(frozen=True)
class Declaration:
    """One declared local: where, what type, and in what order.

    The declaration *index* is carried because it is load-bearing. One
    campaign measured two entirely different cost deltas at one source line
    depending only on which declaration the carrier came from -- the compiler
    lays the frame out in declaration order, so the index selects the slot,
    and a sweep keyed by site alone cannot tell the two apart.
    """

    line: int
    index: int
    type_text: str
    name: str
    array: str = ""
    initializer: str | None = None

    @property
    def initialized(self) -> bool:
        return self.initializer is not None

    @property
    def is_array(self) -> bool:
        return bool(self.array)

    def as_dict(self) -> dict[str, object]:
        return {
            "line": self.line,
            "index": self.index,
            "type": self.type_text,
            "name": self.name,
            "array": self.array,
            "initializer": self.initializer,
        }


def declarations(lines: list[str]) -> list[Declaration]:
    """Return every local declaration, in declaration order.

    Reads the dialect, not C: one declaration statement per line, the type
    first, commas separating declarators. A declarator that opens a
    parenthesis (a prototype, a function pointer) is skipped rather than
    guessed at, because a wrong entry here becomes a wrong carrier later.
    """

    found: list[Declaration] = []
    for number, line in enumerate(lines, 1):
        match = _DECLARATION_RE.match(line)
        if match is None:
            continue
        type_text = " ".join(match.group("type").split())
        first = type_text.split()[0] if type_text.split() else ""
        if first in _NOT_A_TYPE or first in {"typedef", "extern"}:
            continue
        declarators = match.group("declarators")
        if "(" in declarators or "?" in declarators:
            continue
        for part in _split_declarators(declarators):
            piece = _DECLARATOR_RE.match(part)
            if piece is None:
                continue
            found.append(
                Declaration(
                    line=number,
                    index=len(found),
                    type_text=(type_text + " " + piece.group("stars")).strip(),
                    name=piece.group("name"),
                    array=piece.group("array") or "",
                    initializer=(
                        piece.group("initializer").strip()
                        if piece.group("initializer")
                        else None
                    ),
                )
            )
    return found


def _split_declarators(text: str) -> list[str]:
    """Split `a, b[2], c = 1` on the commas that separate declarators."""

    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [item for item in parts if item.strip()]


@dataclass(frozen=True)
class Statement:
    """One statement position, with the block path that reaches it."""

    line: int
    text: str
    depth: int
    #: Identity of every block still open at this line, outermost first. A
    #: definition reaches this statement when its own path is a prefix of
    #: this one -- i.e. every block the definition sits in is still open.
    path: tuple[int, ...]
    #: Identity of every enclosing loop body, outermost first.
    loops: tuple[int, ...]
    #: Whether this line is a `case`/`default` label, a `goto`, or a jump out
    #: of the block: reasoning about textual order past one of these is not
    #: reasoning about control flow.
    control_break: bool

    @property
    def in_loop(self) -> bool:
        return bool(self.loops)

    def reached_from(self, other: Statement) -> bool:
        """Whether `other`'s block is still open here (structural dominance).

        For structured control flow without `goto`, an earlier statement whose
        enclosing blocks are all still open is executed before this one on
        every path that reaches this one. A statement in a sibling branch that
        has since closed is not, which is exactly the case a plain "the line
        number is smaller" test gets wrong.
        """

        return other.line < self.line and self.path[: len(other.path)] == other.path


def scan_statements(lines: list[str]) -> list[Statement]:
    """Return one `Statement` per code line, with its block and loop path.

    Line-granular on purpose: the dialect this reads writes one statement per
    line, and a probe that cited a column would be claiming a parse it did not
    do. A line holding two statements is reported once, at its start.
    """

    statements: list[Statement] = []
    block_stack: list[int] = []
    loop_stack: list[tuple[int, int]] = []  # (block identity, opening depth)
    next_block = 0
    pending_loop = False
    pending_switch = False
    depth = 0
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        opens = raw.count("{")
        closes = raw.count("}")
        body = _LOOP_RE.search(raw)
        # `} while (...);` closes a do-loop; its `while` is not a new loop.
        if body is not None and not (body.group(1) == "while" and closes and not opens):
            pending_loop = True
        if _SWITCH_RE.search(raw):
            pending_switch = True
        if line:
            statements.append(
                Statement(
                    line=number,
                    text=line,
                    depth=depth,
                    path=tuple(block_stack),
                    loops=tuple(item[0] for item in loop_stack),
                    control_break=_CONTROL_BREAK_RE.match(line) is not None,
                )
            )
        for char in raw:
            if char == "{":
                next_block += 1
                block_stack.append(next_block)
                depth += 1
                if pending_loop and not pending_switch:
                    loop_stack.append((next_block, depth))
                pending_loop = False
                pending_switch = False
            elif char == "}":
                if loop_stack and block_stack and loop_stack[-1][0] == block_stack[-1]:
                    loop_stack.pop()
                if block_stack:
                    block_stack.pop()
                depth = max(0, depth - 1)
        if not opens and (line.endswith(";") or line.endswith("}")):
            # A one-line `if (x) y;` opened no block, so nothing is pending.
            pending_loop = False
            pending_switch = False
    return statements
