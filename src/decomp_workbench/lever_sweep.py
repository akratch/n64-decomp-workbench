"""Zero-emission source levers, generated at every statement position.

When a force has already *priced* a target -- ``CDX_FORCE=p1:wN=cK`` or ``=s``
reproduces it -- the remaining work is finding the source edit that puts the
allocator in that state without the force. In one campaign's late closes that
search was nearly always a hand-written sweep of 50 to 500 cells drawn from a
small catalogue of transforms that emit no instruction of their own and change
only what the IR looks like to uopt. This module is that catalogue, and the
oracle that recognises a cell which reached the forced state.

The catalogue (:data:`LEVERS`), each entry naming the mechanism it moves:

``dead_read``      ``x = READ;`` into a local that is dead there. The read's
                   address expression enters uopt's table; a bare dead read
                   is inert, so none is generated.
``dead_masked``    ``x = READ & 0xFFFF;`` into a dead integer local: the load
                   goes to a scratch temporary, the copy is deleted, and the
                   web can still deny a register in its block.
``keep_alive``     ``x |= 0;`` / ``x ^= 0;`` after ``x = <expression>;``: kills
                   uopt's substitution of the symbol.
``noop_redef``     ``x = (T) x;`` with ``T`` the declared type: deleted, but it
                   kills forward substitution into a later use.
``narrow_type``    a narrower (or wider) integer type for one local.
``subscript``      ``[E]`` -> ``[(E) & 0xFFFF]``, and ``&X[E]`` -> a byte-scaled
                   address, which draws a second scratch register.
``boundary``       ``do { S } while (0);`` around one statement, and an empty
                   ``if (v) {}`` at a position, which keeps ``v`` live there.
``global_reread``  after ``G = x;`` the next read of ``x`` reads ``G`` instead.
``zero_def``       ``k = 0;`` for a dead integer local right after a loop: a def
                   between two loops changes uopt's loop exit test.
``split_local``    one local becomes two names from a dominating redefinition.
``merge_locals``   two same-typed locals with disjoint ranges become one.
``reorder``        two adjacent independent statements swapped.
``loop_move``      the statement before a loop moved into its head, or the
                   body's first statement hoisted out.
``const_iv``       ``K = C; for (v = K; ...)`` for ``for (v = C; ...)``.

Every lever marked ``check`` in :class:`Cell` can change behaviour: read a
winner against the whole enclosing scope before adopting it. "Dead" is decided
conservatively from the statement tree: the next mention of the local after the
position must be a plain ``x = ...`` not reading ``x``, at a level every later
path passes, with no ``goto``/label/escaping ``break`` in between, and every
enclosing loop must re-kill ``x`` before its back edge reads it.

The parser is a statement-level C reader, not a compiler: it finds one function
definition, its compound statements, declarations and simple statements, and
leaves expressions as text. Preprocessor lines inside a body are kept and
skipped. An inserted statement goes on the physical line of the statement it
follows unless ``own_line`` is set, so every other line keeps its number (as1's
scheduling tie-break reads source lines).

The oracle half (:func:`decision_rows`, :func:`oracle_targets`,
:func:`oracle_status`) reads CDX records through :mod:`.web_report`. Web numbers
are not stable across source edits -- a dead statement renumbers them -- so a
forced web is re-found in every cell by its ``webexpr`` expression and the
source lines of its blocks (Jaccard overlap), never by number, and a tie that
disagrees about the outcome reads ``ambiguous`` rather than yes or no.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .instrument_uopt import ForceEntry, parse_force_specification
from .web_report import build_web_report, parse_records

__all__ = [
    "LEVERS",
    "BiasEntry",
    "Cell",
    "Function",
    "LeverSweepError",
    "VarInfo",
    "bias_targets",
    "dead_at",
    "decision_rows",
    "find_function",
    "force_acceptance",
    "generate_cells",
    "interleave",
    "oracle_label",
    "oracle_status",
    "oracle_targets",
    "parse_bias",
    "parse_forces",
    "parse_structs",
]


class LeverSweepError(ValueError):
    """A source, oracle or record set could not support the sweep asked for."""


KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "default",
        "break",
        "continue",
        "return",
        "goto",
        "sizeof",
        "struct",
        "union",
        "enum",
        "typedef",
        "static",
        "extern",
        "const",
        "volatile",
        "register",
        "auto",
        "signed",
        "unsigned",
        "void",
        "char",
        "short",
        "int",
        "long",
        "float",
        "double",
        "NULL",
    }
)
INT_TYPES = frozenset(
    {
        "s8",
        "u8",
        "s16",
        "u16",
        "s32",
        "u32",
        "s64",
        "u64",
        "int",
        "char",
        "short",
        "long",
        "unsigned",
        "signed",
        "unsigned int",
        "unsigned char",
        "unsigned short",
        "unsigned long",
        "signed char",
        "signed short",
        "signed int",
        "short int",
        "long int",
    }
)
FLOAT_TYPES = frozenset({"f32", "f64", "float", "double"})

#: Integer retypings tried by ``narrow_type``, in both the stdint-style
#: spellings decompilation projects typedef and the plain C ones.
NARROW: dict[str, tuple[str, ...]] = {
    "s32": ("s16", "u16", "u8", "s8", "u32"),
    "u32": ("s32", "u16", "s16", "u8"),
    "s16": ("s32", "u16", "u8"),
    "u16": ("s32", "s16", "u8"),
    "u8": ("s32", "u16", "s16"),
    "s8": ("s32", "s16"),
    "int": ("short", "unsigned short", "unsigned char", "unsigned int"),
    "unsigned int": ("int", "unsigned short", "short", "unsigned char"),
    "short": ("int", "unsigned short", "unsigned char"),
    "unsigned short": ("int", "short", "unsigned char"),
    "unsigned char": ("int", "unsigned short", "short"),
    "char": ("int", "short"),
    "signed char": ("int", "short"),
}

_TYPE_QUALIFIERS = (
    r"(?:(?:const|volatile|static|register|unsigned|signed|struct|union|enum)\s+)*"
)
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
DECL_RE = re.compile(
    r"^\s*"
    + _TYPE_QUALIFIERS
    + r"[A-Za-z_]\w*[\s*]+[A-Za-z_]\w*\s*(?:\[[^\]]*\]\s*)*(?:=|;|,)",
    re.S,
)
BASE_TYPE_RE = re.compile(
    r"^(" + _TYPE_QUALIFIERS + r"[A-Za-z_]\w*(?:\s+(?:int|char|short|long))?)"
)
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=(?!=)(.*);\s*$", re.S)
STORE_RE = re.compile(r"^\s*(.+?)\s*=(?!=)\s*([A-Za-z_]\w*)\s*;\s*$", re.S)
READ_RE = re.compile(
    r"(?<![\w.>])(?:\*\s*[A-Za-z_]\w*|[A-Za-z_]\w*"
    r"(?:\s*(?:->|\.)\s*[A-Za-z_]\w*|\s*\[[^\[\]]*\])+)"
)
SUBSCRIPT_RE = re.compile(r"\[([^\[\]]+)\]")
ADDR_SUB_RE = re.compile(
    r"&\s*([A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*)\s*\[([^\[\]]+)\]"
)
CONSTANT_RE = re.compile(r"-?(0x[0-9A-Fa-f]+|\d+)[uUlL]*")
STRUCT_RE = re.compile(r"(?:typedef\s+)?(struct|union)\s*(\w*)\s*\{")


# ----------------------------------------------------------------- lexing


def skip_ws(text: str, index: int) -> int:
    """Skip whitespace and comments."""

    length = len(text)
    while index < length:
        if text[index].isspace():
            index += 1
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
        else:
            break
    return index


def _skip_literal(text: str, index: int) -> int:
    quote = text[index]
    index += 1
    while index < len(text) and text[index] != quote:
        index += 2 if text[index] == "\\" else 1
    return index + 1


def match_close(text: str, index: int) -> int:
    """``index`` at an opening bracket: the index after its partner."""

    depth = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "\"'":
            index = _skip_literal(text, index)
            continue
        if text.startswith("/*", index) or text.startswith("//", index):
            index = skip_ws(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise LeverSweepError("unbalanced brackets in the function")


def _scan_to(text: str, index: int, stop: str) -> int:
    length = len(text)
    while index < length:
        char = text[index]
        if char in "\"'":
            index = _skip_literal(text, index)
            continue
        if text.startswith("/*", index) or text.startswith("//", index):
            index = skip_ws(text, index)
            continue
        if char in "([{":
            index = match_close(text, index)
            continue
        if char == stop:
            return index + 1
        index += 1
    raise LeverSweepError(f"no {stop!r} before the end of the function")


def _word_at(text: str, index: int) -> str:
    found = IDENT_RE.match(text, index)
    return found.group(0) if found else ""


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def identifiers(text: str) -> list[str]:
    """Variable-like identifiers: not member names, keywords or literals."""

    text = strip_comments(text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    found: list[str] = []
    for match in IDENT_RE.finditer(text):
        before = text[: match.start()].rstrip()
        if before.endswith(".") or before.endswith("->"):
            continue
        if match.group(0) in KEYWORDS:
            continue
        if match.start() and text[match.start() - 1].isdigit():
            continue
        found.append(match.group(0))
    return found


# ----------------------------------------------------------------- statement tree


@dataclass(eq=False)
class Node:
    """One statement: compound, simple, decl, if, loop, switch, label, pp, jump."""

    kind: str
    start: int
    end: int
    children: list[Node] = field(default_factory=list)
    header: tuple[int, int] | None = None
    loop: str = ""
    parent: Node | None = None
    declarations: int = 0

    def text(self, source: str) -> str:
        return source[self.start : self.end]


def _parse_statement(text: str, index: int) -> Node:
    index = skip_ws(text, index)
    if index >= len(text):
        raise LeverSweepError("statement runs past the end of the function")
    if text[index] == "#":
        position = index
        while True:
            newline = text.find("\n", position)
            if newline < 0:
                return Node("pp", index, len(text))
            if text[newline - 1] != "\\":
                return Node("pp", index, newline)
            position = newline + 1
    if text[index] == "{":
        return _parse_compound(text, index)
    if text[index] == ";":
        return Node("simple", index, index + 1)
    word = _word_at(text, index)
    if word == "if":
        head_start = skip_ws(text, index + 2)
        head_end = match_close(text, head_start)
        then = _parse_statement(text, head_end)
        node = Node("if", index, then.end, [then], (head_start, head_end))
        after = skip_ws(text, then.end)
        if _word_at(text, after) == "else":
            other = _parse_statement(text, after + 4)
            node.children.append(other)
            node.end = other.end
        return node
    if word in ("for", "while", "switch"):
        head_start = skip_ws(text, index + len(word))
        head_end = match_close(text, head_start)
        body = _parse_statement(text, head_end)
        return Node(
            "switch" if word == "switch" else "loop",
            index,
            body.end,
            [body],
            (head_start, head_end),
            loop=word,
        )
    if word == "do":
        body = _parse_statement(text, index + 2)
        after = skip_ws(text, body.end)
        if _word_at(text, after) != "while":
            raise LeverSweepError("do without while")
        head_start = skip_ws(text, after + 5)
        head_end = match_close(text, head_start)
        end = _scan_to(text, head_end, ";")
        return Node("loop", index, end, [body], (head_start, head_end), loop="do")
    if word in ("case", "default"):
        return Node("label", index, _scan_to(text, index, ":"))
    if word and word not in KEYWORDS:
        after = skip_ws(text, index + len(word))
        if (
            after < len(text)
            and text[after] == ":"
            and text[after + 1 : after + 2] != ":"
        ):
            return Node("label", index, after + 1)
    end = _scan_to(text, index, ";")
    kind = "jump" if word in ("break", "continue", "goto", "return") else "simple"
    return Node(kind, index, end)


def _parse_compound(text: str, index: int) -> Node:
    close = match_close(text, index) - 1
    node = Node("compound", index, close + 1)
    position = index + 1
    leading = True
    while True:
        position = skip_ws(text, position)
        if position >= close:
            break
        child = _parse_statement(text, position)
        if (
            child.kind == "simple"
            and leading
            and DECL_RE.match(child.text(text))
            and _word_at(text, child.start) != "return"
        ):
            child.kind = "decl"
            node.declarations = len(node.children) + 1
        elif child.kind != "pp":
            leading = False
        node.children.append(child)
        position = child.end
    return node


def _link(node: Node, parent: Node | None = None) -> None:
    node.parent = parent
    for child in node.children:
        _link(child, node)


def walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from walk(child)


@dataclass
class VarInfo:
    """A declared variable: base type, pointer depth, array-ness."""

    type: str
    ptr: int = 0
    array: bool = False
    decl: Node | None = None

    def category(self) -> str:
        if self.array:
            return "array"
        if self.ptr:
            return "pointer"
        if self.type in FLOAT_TYPES:
            return "float"
        if self.type in INT_TYPES:
            return "int"
        return "other"

    def spelled(self) -> str:
        return self.type + (" " + "*" * self.ptr if self.ptr else "")


@dataclass
class Function:
    """One parsed C function definition inside its translation unit."""

    text: str
    name: str
    body: Node
    signature: tuple[int, int]
    locals: dict[str, VarInfo]
    params: dict[str, VarInfo]

    def line_of(self, offset: int) -> int:
        return self.text.count("\n", 0, offset) + 1


def _split_top(text: str, separator: str = ",") -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _declarator(base: str, text: str) -> tuple[str, VarInfo] | None:
    text = text.split("=", 1)[0].strip()
    stars = len(text) - len(text.lstrip("* "))
    pointer = text[:stars].count("*")
    found = IDENT_RE.match(text.lstrip("* ").strip())
    if not found:
        return None
    return found.group(0), VarInfo(
        re.sub(r"\s+", " ", base.strip()), pointer, "[" in text
    )


def _collect_locals(text: str, body: Node) -> dict[str, VarInfo]:
    found: dict[str, VarInfo] = {}
    for node in walk(body):
        if node.kind != "decl":
            continue
        declaration = strip_comments(node.text(text)).strip().rstrip(";")
        parts = _split_top(declaration)
        match = BASE_TYPE_RE.match(parts[0].strip())
        if not match:
            continue
        base = match.group(1)
        first = parts[0].strip()[len(base) :]
        for item in [first, *parts[1:]]:
            parsed = _declarator(base, item)
            if parsed:
                name, info = parsed
                info.decl = node
                found[name] = info
    return found


def _parse_params(text: str) -> dict[str, VarInfo]:
    found: dict[str, VarInfo] = {}
    for part in _split_top(text):
        part = part.strip()
        if not part or part == "void":
            continue
        match = re.search(r"([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*$", part)
        if match:
            base = re.sub(r"\s+", " ", part[: match.start()].replace("*", "").strip())
            base = re.sub(r"^(?:const|volatile)\s+", "", base)
            found[match.group(1)] = VarInfo(base, part.count("*"), bool(match.group(2)))
    return found


def find_function(text: str, name: str) -> Function:
    """Parse the C definition of ``name`` (a prototype is skipped)."""

    pattern = re.compile(rf"^[\w \t\*]*\b{re.escape(name)}\s*\(", re.M)
    for match in pattern.finditer(text):
        open_paren = match.end() - 1
        try:
            close_paren = match_close(text, open_paren)
        except LeverSweepError:
            continue
        brace = skip_ws(text, close_paren)
        if brace < len(text) and text[brace] == "{":
            body = _parse_compound(text, brace)
            _link(body)
            return Function(
                text=text,
                name=name,
                body=body,
                signature=(open_paren, close_paren),
                locals=_collect_locals(text, body),
                params=_parse_params(text[open_paren + 1 : close_paren - 1]),
            )
    raise LeverSweepError(f"no C definition of {name} in the source")


# ----------------------------------------------------------------- expression types


def parse_structs(
    text: str, into: dict[str, dict[str, VarInfo]] | None = None
) -> dict[str, dict[str, VarInfo]]:
    """Tag and typedef name -> field table, for flat struct and union bodies.

    A nested aggregate is skipped, so a field inside one is simply unknown,
    and an unknown type never pairs with anything.
    """

    table: dict[str, dict[str, VarInfo]] = {} if into is None else into
    text = strip_comments(text)
    for match in STRUCT_RE.finditer(text):
        try:
            close = match_close(text, match.end() - 1)
        except LeverSweepError:
            continue
        body = text[match.end() : close - 1]
        flat: list[str] = []
        depth = 0
        for char in body:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif depth == 0:
                flat.append(char)
        fields: dict[str, VarInfo] = {}
        for declaration in "".join(flat).split(";"):
            declaration = declaration.strip()
            base_match = BASE_TYPE_RE.match(declaration)
            if not base_match:
                continue
            base = base_match.group(1)
            for item in _split_top(declaration[len(base) :]):
                parsed = _declarator(base, item.split(":")[0])
                if parsed:
                    fields[parsed[0]] = parsed[1]
        names = [match.group(2)] if match.group(2) else []
        tail = re.match(r"\s*(\w+)\s*;", text[close:])
        if tail:
            names.append(tail.group(1))
        for name in names:
            table.setdefault(name, fields)
    return table


def _bare_type(name: str) -> str:
    return re.sub(r"^(?:(?:struct|union|enum|const|volatile)\s+)+", "", name.strip())


def expression_type(
    function: Function, expression: str, structs: Mapping[str, Mapping[str, VarInfo]]
) -> VarInfo | None:
    """Declared type of a read expression, or ``None`` when unknown."""

    expression = expression.strip()
    derefs = 0
    while expression.startswith("*"):
        derefs += 1
        expression = expression[1:].strip()
    root = IDENT_RE.match(expression)
    if not root:
        return None
    info = function.locals.get(root.group(0)) or function.params.get(root.group(0))
    if info is None:
        return None
    current = VarInfo(info.type, info.ptr, info.array)
    rest = expression[root.end() :]
    ops = re.findall(r"->\s*\w+|\.\s*\w+|\[[^\[\]]*\]", rest)
    if "".join(op.replace(" ", "") for op in ops) != re.sub(r"\s+", "", rest):
        return None
    for op in ops:
        if op.startswith("["):
            if current.array:
                current.array = False
            elif current.ptr > 0:
                current.ptr -= 1
            else:
                return None
        else:
            arrow = op.startswith("->")
            if current.array or current.ptr != (1 if arrow else 0):
                return None
            fields = structs.get(_bare_type(current.type))
            member = fields.get(op.lstrip("->.").strip()) if fields else None
            if member is None:
                return None
            current = VarInfo(member.type, member.ptr, member.array)
    for _ in range(derefs):
        if current.ptr > 0:
            current.ptr -= 1
        elif current.array:
            current.array = False
        else:
            return None
    return current


def compatible(local: VarInfo, read: VarInfo | None) -> bool:
    """May ``local = <read>;`` compile as a plain assignment? Unknown never pairs."""

    if read is None or read.array or local.array:
        return False
    left = VarInfo(_bare_type(local.type), local.ptr)
    right = VarInfo(_bare_type(read.type), read.ptr)
    category = left.category()
    if category != right.category():
        return False
    if category == "int":
        return True
    if category == "float":
        return left.type == right.type
    if category == "pointer":
        return left.ptr == right.ptr and (
            left.type == right.type or "void" in (left.type, right.type)
        )
    return left.type == right.type and left.ptr == right.ptr


# ----------------------------------------------------------------- flow helpers


def simple_statements(function: Function) -> list[Node]:
    return [node for node in walk(function.body) if node.kind in ("simple", "jump")]


def _ancestors(node: Node) -> list[Node]:
    found: list[Node] = []
    while node.parent is not None:
        node = node.parent
        found.append(node)
    return found


def _mentions(function: Function, node: Node, name: str) -> bool:
    return name in identifiers(node.text(function.text))


def _is_kill(function: Function, node: Node, name: str) -> bool:
    """``name = <expr not reading name>;``, or a ``for`` whose init is that."""

    if node.kind == "loop" and node.loop == "for" and node.header:
        start, end = node.header
        init = function.text[start + 1 : end - 1].split(";", 1)[0]
        match = re.match(
            r"^\s*([A-Za-z_]\w*)\s*=(?!=)(.*)$", strip_comments(init), re.S
        )
        return (
            bool(match)
            and match is not None
            and match.group(1) == name
            and name not in identifiers(match.group(2))
            and "," not in match.group(2)
        )
    if node.kind != "simple":
        return False
    match = ASSIGN_RE.match(strip_comments(node.text(function.text)))
    return (
        bool(match)
        and match is not None
        and match.group(1) == name
        and (name not in identifiers(match.group(2)))
    )


def _escapes(
    function: Function, node: Node, in_loop: bool = False, in_switch: bool = False
) -> bool:
    if node.kind == "label":
        return True
    if node.kind == "jump":
        word = _word_at(function.text, node.start)
        return (
            word == "goto"
            or (word == "continue" and not in_loop)
            or (word == "break" and not (in_loop or in_switch))
        )
    loop = in_loop or node.kind == "loop"
    switch = in_switch or node.kind == "switch"
    return any(_escapes(function, child, loop, switch) for child in node.children)


def insertion_offset(compound: Node, index: int) -> int:
    if index == 0:
        return compound.start + 1
    return compound.children[index - 1].end


def dead_at(function: Function, compound: Node, index: int, name: str) -> bool:
    """Is a value written to ``name`` at ``index`` of ``compound`` never read?"""

    text = function.text
    offset = insertion_offset(compound, index)
    current: Node = compound
    position = index
    while True:
        for statement in current.children[position:]:
            if _escapes(function, statement):
                return False
            if not _mentions(function, statement, name):
                continue
            return _is_kill(function, statement, name)
        child: Node = current
        parent = current.parent
        while parent is not None and parent.kind != "compound":
            if parent.kind == "loop" and parent.header:
                start, end = parent.header
                if name in identifiers(text[start:end]):
                    return False
                body = parent.children[0]
                for statement in body.children if body.kind == "compound" else [body]:
                    if statement.start >= offset:
                        break
                    if statement.end > offset:
                        if name in identifiers(text[statement.start : offset]):
                            return False
                        break
                    if _mentions(function, statement, name):
                        if not _is_kill(function, statement, name):
                            return False
                        break
            child, parent = parent, parent.parent
        if parent is None:
            return True
        current, position = parent, parent.children.index(child) + 1


def positions(function: Function) -> list[tuple[Node, int]]:
    """Every ``(compound, index)`` where a statement can be inserted."""

    found: list[tuple[Node, int]] = []
    for node in walk(function.body):
        if node.kind == "compound":
            found.extend(
                (node, index)
                for index in range(node.declarations, len(node.children) + 1)
            )
    return found


def _position_line(function: Function, compound: Node, index: int) -> int:
    return function.line_of(insertion_offset(compound, index))


def insert_at(
    function: Function, compound: Node, index: int, statement: str, own_line: bool
) -> str:
    text = function.text
    offset = insertion_offset(compound, index)
    if own_line:
        anchor = (
            compound.children[index].start if index < len(compound.children) else offset
        )
        line_start = text.rfind("\n", 0, anchor) + 1
        indent_match = re.match(r"[ \t]*", text[line_start:])
        indent = indent_match.group(0) if indent_match else ""
        return text[:offset] + "\n" + indent + statement + text[offset:]
    return text[:offset] + " " + statement + text[offset:]


def _window_reads(
    function: Function, statements: Sequence[Node], center: int, width: int
) -> list[str]:
    seen: list[str] = []
    for statement in statements[max(0, center - width) : center + width]:
        body = strip_comments(statement.text(function.text))
        for match in READ_RE.finditer(body):
            if match.group(0).startswith("*"):
                previous = body[: match.start()].rstrip()[-1:]
                if previous and (previous.isalnum() or previous in ")]_"):
                    continue  # a multiplication, not a dereference
            read = re.sub(r"\s+", " ", match.group(0)).strip()
            if read not in seen:
                seen.append(read)
    return seen


def _writes_reads(
    function: Function, node: Node
) -> tuple[str | None, set[str], bool, bool]:
    """(written root identifier, identifiers read, has a call, stores to memory)."""

    body = strip_comments(node.text(function.text))
    match = re.match(r"^\s*(.+?)\s*([-+*/&|^%]|<<|>>)?=(?!=)(.*);\s*$", body, re.S)
    call = bool(re.search(r"[A-Za-z_]\w*\s*\(", body.replace("sizeof", "")))
    if not match:
        return None, set(identifiers(body)), call, False
    left = match.group(1)
    memory = bool(re.search(r"->|\[|\*|\.", left))
    names = identifiers(left)
    root = names[0] if names else None
    reads = set(identifiers(match.group(3))) | (set(names[1:]) if memory else set())
    if match.group(2) and root:
        reads.add(root)
    return root, reads, call, memory


# ----------------------------------------------------------------- levers


@dataclass
class Cell:
    """One generated candidate: the whole edited translation unit."""

    lever: str
    line: int
    edit: str
    text: str
    semantics: str = "safe"

    def as_dict(self) -> dict[str, Any]:
        return {
            "lever": self.lever,
            "line": self.line,
            "edit": self.edit,
            "semantics": self.semantics,
        }


@dataclass
class _Context:
    positions: list[tuple[Node, int]]
    statements: list[Node]
    in_lines: Callable[[int], bool]
    own_line: bool
    window: int
    max_reads: int
    mentioned: set[str]
    structs: dict[str, dict[str, VarInfo]]


def _statement_index(statements: Sequence[Node], offset: int) -> int:
    for index, statement in enumerate(statements):
        if statement.start >= offset:
            return index
    return len(statements)


def _lever_dead_read(
    function: Function, context: _Context, masked: bool = False
) -> list[Cell]:
    cells: list[Cell] = []
    for compound, index in context.positions:
        line = _position_line(function, compound, index)
        center = _statement_index(context.statements, insertion_offset(compound, index))
        reads = _window_reads(function, context.statements, center, context.window)[
            : context.max_reads
        ]
        for name, info in function.locals.items():
            category = info.category()
            if category not in ("int", "pointer", "float") or (
                masked and category != "int"
            ):
                continue
            if name not in context.mentioned or not dead_at(
                function, compound, index, name
            ):
                continue
            for read in reads:
                if re.match(rf"^\*?\s*{re.escape(name)}\b", read):
                    continue
                if not compatible(
                    info, expression_type(function, read, context.structs)
                ):
                    continue
                statement = (
                    f"{name} = {read} & 0xFFFF;" if masked else f"{name} = {read};"
                )
                cells.append(
                    Cell(
                        "dead_masked" if masked else "dead_read",
                        line,
                        statement,
                        insert_at(
                            function, compound, index, statement, context.own_line
                        ),
                    )
                )
    return cells


def _lever_dead_masked(function: Function, context: _Context) -> list[Cell]:
    return _lever_dead_read(function, context, masked=True)


def _lever_keep_alive(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    for statement in context.statements:
        if statement.kind != "simple" or not context.in_lines(
            function.line_of(statement.start)
        ):
            continue
        match = ASSIGN_RE.match(strip_comments(statement.text(function.text)))
        if not match or match.group(1) not in function.locals:
            continue
        if function.locals[match.group(1)].category() != "int":
            continue
        right = match.group(2).strip()
        if re.fullmatch(r"[A-Za-z_]\w*", right) or CONSTANT_RE.fullmatch(right):
            continue
        compound = statement.parent
        if compound is None or compound.kind != "compound":
            continue
        index = compound.children.index(statement) + 1
        for op in ("|=", "^="):
            text = f"{match.group(1)} {op} 0;"
            cells.append(
                Cell(
                    "keep_alive",
                    function.line_of(statement.start),
                    text,
                    insert_at(function, compound, index, text, context.own_line),
                )
            )
    return cells


def _lever_noop_redef(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    for name, info in function.locals.items():
        if info.category() not in ("int", "pointer"):
            continue
        occurrences = [
            statement.start
            for statement in context.statements
            if name in identifiers(statement.text(function.text))
        ]
        if not occurrences:
            continue
        first, last = min(occurrences), max(occurrences)
        for compound, index in context.positions:
            offset = insertion_offset(compound, index)
            if not first < offset <= last:
                continue
            text = f"{name} = ({info.spelled()}) {name};"
            cells.append(
                Cell(
                    "noop_redef",
                    _position_line(function, compound, index),
                    text,
                    insert_at(function, compound, index, text, context.own_line),
                )
            )
    return cells


def _prefixed(replacement: str) -> Callable[[re.Match[str]], str]:
    def substitute(found: re.Match[str]) -> str:
        return found.group(1) + replacement

    return substitute


def _lever_narrow_type(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for name, info in function.locals.items():
        if (
            info.category() != "int"
            or name not in context.mentioned
            or info.decl is None
        ):
            continue
        declaration = info.decl
        original = declaration.text(text)
        if "," in strip_comments(original):
            continue  # multi-declarator lines are left alone
        for replacement in NARROW.get(info.type, ()):
            edited = re.sub(
                rf"^(\s*){re.escape(info.type)}\b",
                _prefixed(replacement),
                original,
                count=1,
            )
            if edited == original:
                continue
            cells.append(
                Cell(
                    "narrow_type",
                    function.line_of(declaration.start),
                    f"{replacement} {name}",
                    text[: declaration.start] + edited + text[declaration.end :],
                    "check",
                )
            )
    return cells


def _lever_subscript(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for statement in context.statements:
        line = function.line_of(statement.start)
        if not context.in_lines(line):
            continue
        body = statement.text(text)
        for match in SUBSCRIPT_RE.finditer(body):
            index = match.group(1).strip()
            if CONSTANT_RE.fullmatch(index) or "0xFFFF" in index:
                continue
            edited = (
                body[: match.start()] + f"[({index}) & 0xFFFF]" + body[match.end() :]
            )
            cells.append(
                Cell(
                    "subscript",
                    line,
                    f"[{index}] -> [({index}) & 0xFFFF]",
                    text[: statement.start] + edited + text[statement.end :],
                    "check",
                )
            )
        for match in ADDR_SUB_RE.finditer(body):
            base, index = match.group(1).strip(), match.group(2).strip()
            scaled = f"(void *) ((char *) ({base}) + ({index}) * sizeof(({base})[0]))"
            edited = body[: match.start()] + scaled + body[match.end() :]
            cells.append(
                Cell(
                    "subscript",
                    line,
                    f"&{base}[{index}] -> byte-scaled",
                    text[: statement.start] + edited + text[statement.end :],
                )
            )
    return cells


def _lever_boundary(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for statement in context.statements:
        if statement.kind != "simple" or not context.in_lines(
            function.line_of(statement.start)
        ):
            continue
        if statement.parent is None or statement.parent.kind != "compound":
            continue
        body = statement.text(text)
        cells.append(
            Cell(
                "boundary",
                function.line_of(statement.start),
                "do { S } while (0)",
                text[: statement.start]
                + "do { "
                + body
                + " } while (0);"
                + text[statement.end :],
            )
        )
    for compound, index in context.positions:
        center = _statement_index(context.statements, insertion_offset(compound, index))
        near: set[str] = set()
        for statement in context.statements[
            max(0, center - context.window) : center + context.window
        ]:
            near.update(identifiers(statement.text(text)))
        for name in sorted(near):
            info = function.locals.get(name) or function.params.get(name)
            if info is None or info.category() not in ("int", "pointer"):
                continue
            edit = f"if ({name}) {{}}"
            cells.append(
                Cell(
                    "boundary",
                    _position_line(function, compound, index),
                    edit,
                    insert_at(function, compound, index, edit, context.own_line),
                )
            )
    return cells


def _lever_global_reread(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for statement in context.statements:
        if statement.kind != "simple" or not context.in_lines(
            function.line_of(statement.start)
        ):
            continue
        match = STORE_RE.match(strip_comments(statement.text(text)))
        if not match:
            continue
        left, name = match.group(1).strip(), match.group(2)
        root = IDENT_RE.match(left.lstrip("*( "))
        if (
            name not in function.locals
            or left in function.locals
            or left in function.params
        ):
            continue
        if root and root.group(0) == name:
            continue
        compound = statement.parent
        if compound is None or compound.kind != "compound":
            continue
        for later in compound.children[compound.children.index(statement) + 1 :]:
            if not _mentions(function, later, name):
                continue
            is_return = later.kind == "jump" and _word_at(text, later.start) == "return"
            if (later.kind != "simple" and not is_return) or (
                not is_return and _writes_reads(function, later)[0] == name
            ):
                break
            body = later.text(text)
            assignment = ASSIGN_RE.match(strip_comments(body))
            region = (body.index("=") + 1) if assignment else 0
            hit = re.compile(rf"(?<![\w.>]){re.escape(name)}\b").search(body, region)
            if hit is None:
                break
            edited = body[: hit.start()] + left + body[hit.end() :]
            cells.append(
                Cell(
                    "global_reread",
                    function.line_of(later.start),
                    f"{name} -> {left}",
                    text[: later.start] + edited + text[later.end :],
                    "check",
                )
            )
            break
    return cells


def _lever_zero_def(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    for node in walk(function.body):
        if node.kind != "loop" or node.parent is None or node.parent.kind != "compound":
            continue
        compound = node.parent
        index = compound.children.index(node) + 1
        line = _position_line(function, compound, index)
        if not context.in_lines(line) and not context.in_lines(
            function.line_of(node.start)
        ):
            continue
        for name, info in function.locals.items():
            if info.category() != "int" or not dead_at(function, compound, index, name):
                continue
            edit = f"{name} = 0;"
            cells.append(
                Cell(
                    "zero_def",
                    line,
                    edit,
                    insert_at(function, compound, index, edit, context.own_line),
                )
            )
    return cells


def _rename_from(text: str, start: int, end: int, old: str, new: str) -> str:
    segment = re.sub(rf"(?<![\w.>]){re.escape(old)}\b", new, text[start:end])
    return text[:start] + segment + text[end:]


def _lever_split_local(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    top = function.body
    for name, info in function.locals.items():
        if info.category() not in ("int", "pointer", "float") or info.decl is None:
            continue
        if info.decl.parent is not top:
            continue
        seen_before = False
        for statement in top.children[top.declarations :]:
            if _is_kill(function, statement, name) and seen_before:
                new = f"{name}_b"
                if new not in function.locals and context.in_lines(
                    function.line_of(statement.start)
                ):
                    edited = _rename_from(text, statement.start, top.end, name, new)
                    edited = (
                        edited[: info.decl.end]
                        + f" {info.spelled()} {new};"
                        + edited[info.decl.end :]
                    )
                    cells.append(
                        Cell(
                            "split_local",
                            function.line_of(statement.start),
                            f"{name} -> {new} from here",
                            edited,
                        )
                    )
            if _mentions(function, statement, name):
                seen_before = True
    return cells


def _lever_merge_locals(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    occurrences: dict[str, list[Node]] = {}
    for name in function.locals:
        hits = [s for s in context.statements if name in identifiers(s.text(text))]
        if hits:
            occurrences[name] = hits
    for first_name, first_hits in occurrences.items():
        for second_name, second_hits in occurrences.items():
            first, second = function.locals[first_name], function.locals[second_name]
            if (
                first_name == second_name
                or first.type != second.type
                or first.ptr != second.ptr
                or first.category() not in ("int", "pointer", "float")
            ):
                continue
            if max(s.start for s in first_hits) >= min(s.start for s in second_hits):
                continue
            opening = min(second_hits, key=lambda s: s.start)
            if not _is_kill(function, opening, second_name):
                continue
            last_first = max(first_hits, key=lambda s: s.start)
            loops_first = {id(a) for a in _ancestors(last_first) if a.kind == "loop"}
            loops_second = {id(a) for a in _ancestors(opening) if a.kind == "loop"}
            if loops_first & loops_second:
                continue
            line = function.line_of(opening.start)
            if not context.in_lines(line):
                continue
            cells.append(
                Cell(
                    "merge_locals",
                    line,
                    f"{second_name} -> {first_name} (declaration kept)",
                    _rename_from(
                        text, opening.start, function.body.end, second_name, first_name
                    ),
                    "check",
                )
            )
            declaration = second.decl
            if declaration is not None and "," not in strip_comments(
                declaration.text(text)
            ):
                cut = declaration.end - declaration.start
                dropped = text[: declaration.start] + text[declaration.end :]
                cells.append(
                    Cell(
                        "merge_locals",
                        line,
                        f"{second_name} -> {first_name} (declaration dropped)",
                        _rename_from(
                            dropped,
                            opening.start - cut,
                            function.body.end - cut,
                            second_name,
                            first_name,
                        ),
                        "check",
                    )
                )
    return cells


def _lever_reorder(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for compound in walk(function.body):
        if compound.kind != "compound":
            continue
        children = compound.children
        for index in range(compound.declarations, len(children) - 1):
            first, second = children[index], children[index + 1]
            if first.kind != "simple" or second.kind != "simple":
                continue
            if not context.in_lines(function.line_of(first.start)):
                continue
            write_a, read_a, call_a, memory_a = _writes_reads(function, first)
            write_b, read_b, call_b, memory_b = _writes_reads(function, second)
            if call_a or call_b or write_a is None or write_b is None:
                continue
            if not memory_a and (
                write_a in read_b or (not memory_b and write_a == write_b)
            ):
                continue
            if not memory_b and (
                write_b in read_a or (not memory_a and write_a == write_b)
            ):
                continue
            loads_a = bool(
                re.search(
                    r"->|\[|\*", strip_comments(first.text(text)).split("=", 1)[-1]
                )
            )
            loads_b = bool(
                re.search(
                    r"->|\[|\*", strip_comments(second.text(text)).split("=", 1)[-1]
                )
            )
            semantics = (
                "check"
                if (memory_a and (memory_b or loads_b)) or (memory_b and loads_a)
                else "safe"
            )
            edited = (
                text[: first.start]
                + second.text(text)
                + text[first.end : second.start]
                + first.text(text)
                + text[second.end :]
            )
            cells.append(
                Cell(
                    "reorder",
                    function.line_of(first.start),
                    "swap with next",
                    edited,
                    semantics,
                )
            )
    return cells


def _lever_loop_move(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for loop in walk(function.body):
        if loop.kind != "loop" or loop.parent is None or loop.parent.kind != "compound":
            continue
        body = loop.children[0]
        if body.kind != "compound" or not context.in_lines(
            function.line_of(loop.start)
        ):
            continue
        header = loop.header or (loop.start, loop.start)
        compound = loop.parent
        index = compound.children.index(loop)
        line = function.line_of(loop.start)
        previous = (
            compound.children[index - 1] if index > compound.declarations else None
        )
        written = (
            _writes_reads(function, previous)[0]
            if previous is not None and previous.kind == "simple"
            else None
        )
        if (
            previous is not None
            and written
            and written not in identifiers(text[header[0] : header[1]])
        ):
            head = (
                body.children[body.declarations - 1].end
                if body.declarations
                else body.start + 1
            )
            edited = (
                text[: previous.start]
                + text[previous.end : head]
                + " "
                + previous.text(text)
                + text[head:]
            )
            cells.append(
                Cell(
                    "loop_move",
                    line,
                    "previous statement into the loop head",
                    edited,
                    "check",
                )
            )
        if (
            len(body.children) > body.declarations
            and body.children[body.declarations].kind == "simple"
        ):
            first = body.children[body.declarations]
            match = ASSIGN_RE.match(strip_comments(first.text(text)))
            if match:
                assigned: set[str] = set()
                for statement in walk(body):
                    if statement.kind == "simple" and statement is not first:
                        target = _writes_reads(function, statement)[0]
                        if target:
                            assigned.add(target)
                assigned.update(identifiers(text[header[0] : header[1]]))
                if (
                    not (set(identifiers(match.group(2))) & assigned)
                    and match.group(1) not in assigned
                ):
                    edited = (
                        text[: loop.start]
                        + first.text(text)
                        + " "
                        + text[loop.start : first.start]
                        + text[first.end :]
                    )
                    cells.append(
                        Cell(
                            "loop_move",
                            line,
                            "first body statement hoisted",
                            edited,
                            "check",
                        )
                    )
    return cells


def _lever_const_iv(function: Function, context: _Context) -> list[Cell]:
    cells: list[Cell] = []
    text = function.text
    for loop in walk(function.body):
        if (
            loop.kind != "loop"
            or loop.loop != "for"
            or loop.header is None
            or loop.parent is None
            or loop.parent.kind != "compound"
        ):
            continue
        start, end = loop.header
        head = text[start + 1 : end - 1]
        match = re.match(
            r"\s*([A-Za-z_]\w*)\s*=\s*(-?(?:0x[0-9A-Fa-f]+|\d+))\s*;", head
        )
        if not match or not context.in_lines(function.line_of(loop.start)):
            continue
        compound = loop.parent
        index = compound.children.index(loop)
        for name, info in function.locals.items():
            if name == match.group(1) or info.category() != "int":
                continue
            if _mentions(function, loop, name) or not dead_at(
                function, compound, index + 1, name
            ):
                continue
            new_head = head[: match.start(2)] + name + head[match.end(2) :]
            edited = (
                text[: loop.start]
                + f"{name} = {match.group(2)}; "
                + text[loop.start : start + 1]
                + new_head
                + text[end - 1 :]
            )
            cells.append(
                Cell(
                    "const_iv",
                    function.line_of(loop.start),
                    f"{name} = {match.group(2)}; init through {name}",
                    edited,
                )
            )
    return cells


LeverFunction = Callable[[Function, _Context], list[Cell]]

#: The catalogue, in the order a default run generates it.
LEVERS: dict[str, LeverFunction] = {
    "dead_read": _lever_dead_read,
    "dead_masked": _lever_dead_masked,
    "keep_alive": _lever_keep_alive,
    "noop_redef": _lever_noop_redef,
    "narrow_type": _lever_narrow_type,
    "subscript": _lever_subscript,
    "boundary": _lever_boundary,
    "global_reread": _lever_global_reread,
    "zero_def": _lever_zero_def,
    "split_local": _lever_split_local,
    "merge_locals": _lever_merge_locals,
    "reorder": _lever_reorder,
    "loop_move": _lever_loop_move,
    "const_iv": _lever_const_iv,
}


def generate_cells(
    function: Function,
    levers: Sequence[str],
    lines: set[int] | None = None,
    *,
    own_line: bool = False,
    window: int = 3,
    max_reads: int = 16,
    headers: Sequence[str] = (),
) -> list[Cell]:
    """Every candidate cell of the chosen levers, deduplicated by text.

    ``headers`` are extra C texts (a project's headers) read only for struct
    field types, so a dead read through ``p->field`` can be typed.
    """

    unknown = [name for name in levers if name not in LEVERS]
    if unknown:
        raise LeverSweepError(
            f"unknown lever(s) {', '.join(unknown)}; known: {', '.join(LEVERS)}"
        )

    def in_lines(line: int) -> bool:
        return not lines or line in lines

    structs: dict[str, dict[str, VarInfo]] = {}
    for header in headers:
        parse_structs(header, structs)
    parse_structs(function.text, structs)
    statements = simple_statements(function)
    mentioned: set[str] = set()
    for statement in statements:
        mentioned.update(identifiers(statement.text(function.text)))
    context = _Context(
        positions=[
            (compound, index)
            for compound, index in positions(function)
            if in_lines(_position_line(function, compound, index))
        ],
        statements=statements,
        in_lines=in_lines,
        own_line=own_line,
        window=window,
        max_reads=max_reads,
        mentioned=mentioned,
        structs=structs,
    )
    seen = {hashlib.sha256(function.text.encode()).hexdigest()}
    cells: list[Cell] = []
    for name in levers:
        for cell in LEVERS[name](function, context):
            key = hashlib.sha256(cell.text.encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            cells.append(cell)
    return cells


def interleave(cells: Sequence[Cell], limit: int) -> list[Cell]:
    """Round-robin across levers so a cap leaves every lever represented."""

    if limit <= 0 or len(cells) <= limit:
        return list(cells)
    by_lever: OrderedDict[str, list[Cell]] = OrderedDict()
    for cell in cells:
        by_lever.setdefault(cell.lever, []).append(cell)
    chosen: list[Cell] = []
    while len(chosen) < limit and by_lever:
        for lever in list(by_lever):
            if by_lever[lever]:
                chosen.append(by_lever[lever].pop(0))
                if len(chosen) == limit:
                    break
            else:
                del by_lever[lever]
    return chosen


# ----------------------------------------------------------------- oracle


def parse_forces(spec: str) -> list[ForceEntry]:
    """``p1:w387=s,p2:w131=c21`` -> force entries; empty for an empty spec."""

    return parse_force_specification(spec) if spec.strip() else []


@dataclass(frozen=True)
class BiasEntry:
    """One ``CDX_BIAS`` entry: add ``delta`` to a p1 web's selection save."""

    web: int
    delta: float

    def __str__(self) -> str:
        return f"{self.web}={self.delta:g}"


def parse_bias(spec: str) -> list[BiasEntry]:
    entries: list[BiasEntry] = []
    for item in (part.strip() for part in spec.split(",")):
        if not item:
            continue
        match = re.fullmatch(r"w?(\d+)=(-?\d+(?:\.\d+)?)", item)
        if not match:
            raise LeverSweepError(
                f"bias {item!r} is not web=delta (for example 387=-4.5)"
            )
        entries.append(BiasEntry(int(match.group(1)), float(match.group(2))))
    return entries


def _cdx_rows(text: str) -> list[tuple[str, dict[str, str]]]:
    return [
        (kind, fields)
        for kind, fields in parse_records(text)
        if kind in ("p1dec", "p2dec", "p1color", "p2color")
    ]


def force_acceptance(trace: str, proc: int, forces: Sequence[ForceEntry]) -> str | None:
    """``None`` when every force was applied, else why not.

    A colour force needs exactly one decision and one colour record for its
    web, the colour record carrying the requested colour and ``forced`` equal
    to it or ``-1``. A split force needs every decision row of its web (pieces
    keep the parent's number) to say ``forced=-1`` and no colour row.
    """

    rows = _cdx_rows(trace)
    wanted = str(proc)
    if not any(
        kind.endswith("dec") and fields.get("proc") == wanted for kind, fields in rows
    ):
        return f"no allocator decisions for procedure {proc}"
    for force in forces:
        web = str(force.web)
        decisions = [
            fields
            for kind, fields in rows
            if kind == force.phase + "dec"
            and fields.get("proc") == wanted
            and fields.get("web") == web
        ]
        colours = [
            fields
            for kind, fields in rows
            if kind == force.phase + "color"
            and fields.get("proc") == wanted
            and fields.get("web") == web
        ]
        if force.color is None:
            if not decisions:
                return f"{force}: no decision record for web {web}"
            if any(row.get("forced") != "-1" for row in decisions) or colours:
                states = [row.get("forced", "missing") for row in decisions]
                return (
                    f"{force}: not applied (forced={states}, "
                    f"colour rows={len(colours)})"
                )
            continue
        if len(decisions) != 1 or len(colours) != 1:
            return f"{force}: expected one decision and one colour record for web {web}"
        colour = str(force.color)
        row = colours[0]
        if row.get("forced") not in {colour, "-1"} or row.get("color") != colour:
            return f"{force}: not applied (forced={row.get('forced', 'missing')})"
    return None


def decision_rows(
    trace: str, proc: int
) -> tuple[list[dict[str, Any]], dict[int, list[int]]]:
    """Decision rows of one procedure, each with its expression and source lines."""

    report = build_web_report(parse_records(trace), proc)
    rows: list[dict[str, Any]] = []
    for decision in report.decisions:
        blocks = [
            int(item)
            for item in decision.blocks.get("bbs", "").split(",")
            if item.strip().isdigit()
        ]
        lines: set[int] = set()
        for number in blocks:
            block = report.blocks.get(number)
            if block is not None:
                lines.update(block.lines)
        rows.append(
            {
                "web": decision.web,
                "phase": decision.phase,
                "expr": decision.expression.get("expr"),
                "kind": decision.expression.get("kind"),
                "blocks": blocks,
                "lines": sorted(lines),
                "decision": decision.fields.get("decision"),
                "forced": decision.fields.get("forced"),
                "colour": decision.colour_number,
            }
        )
    return rows, {number: block.lines for number, block in report.blocks.items()}


def _signature(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "expr": row["expr"],
        "kind": row["kind"],
        "lines": set(row["lines"]),
        "decision": row.get("decision"),
        "colour": row.get("colour"),
    }


def oracle_targets(
    forced: Sequence[Mapping[str, Any]], forces: Sequence[ForceEntry]
) -> list[dict[str, Any]]:
    """Every decision row a force touched in the forced base, with its outcome."""

    targets: list[dict[str, Any]] = []
    for force in forces:
        rows = [
            row
            for row in forced
            if row["phase"] == force.phase
            and row["web"] == force.web
            and row["forced"] == "-1"
        ] or [
            row
            for row in forced
            if row["phase"] == force.phase and row["web"] == force.web
        ]
        if not rows:
            raise LeverSweepError(
                f"oracle {force}: no decision for that web in the forced base"
            )
        if any(row["expr"] is None for row in rows):
            raise LeverSweepError(
                f"oracle {force}: the forced base has no webexpr record for that "
                "web, so it cannot be re-found after an edit renumbers it "
                "(CDX_WEBREPORT needed)"
            )
        targets.append(
            {
                "spec": str(force),
                "want": "s" if force.color is None else f"c{force.color}",
                "rows": [_signature(row) for row in rows],
            }
        )
    return targets


def _p1_order(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[int] = set()
    order: list[Mapping[str, Any]] = []
    for row in rows:
        if row["phase"] == "p1" and row["web"] not in seen:
            seen.add(row["web"])
            order.append(row)
    return order


def bias_targets(
    unbiased: Sequence[Mapping[str, Any]],
    biased: Sequence[Mapping[str, Any]],
    bias: Sequence[BiasEntry],
) -> list[dict[str, Any]]:
    """Pairs of p1 webs whose decision order the bias reversed against the base."""

    before = {row["web"]: index for index, row in enumerate(_p1_order(unbiased))}
    biased_rows = _p1_order(biased)
    after = {row["web"]: index for index, row in enumerate(biased_rows)}
    by_web = {row["web"]: row for row in biased_rows}
    targets: list[dict[str, Any]] = []
    for entry in bias:
        if entry.web not in after:
            raise LeverSweepError(
                f"bias w{entry.web}: no p1 decision for that web in the biased base"
            )
        for other in after:
            if other == entry.web or entry.web not in before or other not in before:
                continue
            if (before[entry.web] < before[other]) != (after[entry.web] < after[other]):
                first, second = (
                    (entry.web, other)
                    if after[entry.web] < after[other]
                    else (other, entry.web)
                )
                targets.append(
                    {
                        "spec": f"w{first} before w{second}",
                        "want": "order",
                        "first": _signature(by_web[first]),
                        "second": _signature(by_web[second]),
                    }
                )
    if not targets:
        raise LeverSweepError(
            "the bias reverses no p1 decision order against the unbiased base; "
            "there is nothing for the oracle to price"
        )
    return targets


def _jaccard(left: set[int], right: set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _find_rows(
    candidates: Sequence[Mapping[str, Any]], row: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    """Rows that can be the forced row: same expression and kind over >= 0.3 of
    its lines, else the same kind over >= 0.6 of them; best overlap first."""

    lines = set(row["lines"])
    same = [
        item
        for item in candidates
        if item["expr"] == row["expr"]
        and item["kind"] == row["kind"]
        and _jaccard(set(item["lines"]), lines) >= 0.3
    ]
    if not same:
        same = [
            item
            for item in candidates
            if item["kind"] == row["kind"]
            and _jaccard(set(item["lines"]), lines) >= 0.6
        ]
    return sorted(same, key=lambda item: -_jaccard(set(item["lines"]), lines))


def _tied(
    rows: Sequence[Mapping[str, Any]], row: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    if not rows:
        return []
    lines = set(row["lines"])
    top = _jaccard(set(rows[0]["lines"]), lines)
    tied: list[Mapping[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in rows:
        if top - _jaccard(set(item["lines"]), lines) > 0.05:
            break
        key = (item["phase"], item["web"])
        if key not in seen:
            seen.add(key)
            tied.append(item)
    return tied


def _name(row: Mapping[str, Any]) -> str:
    return f"{row['phase']}:w{row['web']}"


def _order_status(
    candidates: Sequence[Mapping[str, Any]], target: Mapping[str, Any]
) -> dict[str, Any]:
    order = {row["web"]: index for index, row in enumerate(_p1_order(candidates))}
    phase_one = [row for row in candidates if row["phase"] == "p1"]
    ends = [
        _tied(_find_rows(phase_one, target[side]), target[side])
        for side in ("first", "second")
    ]
    if not ends[0] or not ends[1]:
        return {
            "spec": target["spec"],
            "ok": False,
            "ambiguous": False,
            "candidates": [],
        }
    verdicts = {
        order[a["web"]] < order[b["web"]]
        for a in ends[0]
        for b in ends[1]
        if a["web"] != b["web"] and a["web"] in order and b["web"] in order
    }
    ambiguous = len(verdicts) > 1
    return {
        "spec": target["spec"],
        "ok": verdicts == {True},
        "ambiguous": ambiguous,
        "candidates": [_name(row) for row in ends[0] + ends[1]] if ambiguous else [],
    }


def oracle_status(
    candidates: Sequence[Mapping[str, Any]], targets: Sequence[Mapping[str, Any]]
) -> tuple[int, list[dict[str, Any]]]:
    """How many oracle states an unforced cell's decision rows reproduce.

    A colour target's row must carry that colour. A split target reads as
    memory: every same-expression row over those lines must be uncoloured, and
    a piece that is never formed counts as reproduced. An order target (from a
    bias) must decide its two webs in the biased order. When the leading rows
    tie on overlap and disagree, the target is ``ambiguous``: neither a hit nor
    a miss, with the candidates listed.
    """

    hits = 0
    detail: list[dict[str, Any]] = []
    for target in targets:
        if target["want"] == "order":
            status = _order_status(candidates, target)
            hits += bool(status["ok"] and not status["ambiguous"])
            detail.append(status)
            continue
        all_ok = True
        ambiguous = False
        matches: list[dict[str, Any]] = []
        names: list[str] = []
        for row in target["rows"]:
            same = _find_rows(candidates, row)
            if target["want"] == "s":
                ok = all(item["colour"] is None for item in same)
                all_ok &= ok
                matches.append(
                    {
                        "match": [_name(item) for item in same],
                        "colour": [item["colour"] for item in same],
                        "ok": ok,
                    }
                )
                continue
            if not same:
                all_ok = False
                matches.append({"match": None, "ok": False})
                continue
            want = int(str(target["want"])[1:])
            ties = _tied(same, row)
            if len({item["colour"] == want for item in ties}) > 1:
                ambiguous = True
                names.extend(f"{_name(item)}(c{item['colour']})" for item in ties)
            best = ties[0]
            ok = best["colour"] == want
            all_ok &= ok
            matches.append(
                {
                    "match": _name(best),
                    "jaccard": round(
                        _jaccard(set(best["lines"]), set(row["lines"])), 2
                    ),
                    "decision": best["decision"],
                    "colour": best["colour"],
                    "ok": ok,
                }
            )
        hits += bool(all_ok and not ambiguous)
        detail.append(
            {
                "spec": target["spec"],
                "ok": all_ok and not ambiguous,
                "ambiguous": ambiguous,
                "rows": matches,
                "candidates": names,
            }
        )
    return hits, detail


def oracle_label(hits: int, total: int, ambiguous: int = 0) -> str:
    if ambiguous:
        return "ambiguous"
    if hits == total:
        return "yes"
    return "no" if hits == 0 else f"{hits}/{total}"
