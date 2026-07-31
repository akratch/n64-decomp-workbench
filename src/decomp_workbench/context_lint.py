"""Preprocessor-conditional audit: undefined-identifier collapse in `#if`/`#elif`.

The SDK source for one SSB64 function guarded a switch case with
``#if BUILD_VERSION >= VERSION_J``. In any translation unit where *neither*
macro was defined -- true for the isolated harness every human tried first --
the C preprocessor substitutes ``0`` for both identifiers, and ``0 >= 0`` is
true. The guard reads as excluding the case; the preprocessor silently
compiles it in. The result was +109 instructions and a jump table nobody
asked for, and a structure-mismatch diff that gave no honest hint the cause
was a single stale conditional. One ``#include`` that defined ``BUILD_VERSION``
collapsed the residual to size-exact.

The general trap: any ``#if``/``#elif`` whose expression's identifiers are
*all* undefined evaluates to a constant the author almost certainly did not
intend, especially for comparisons and equality (``A >= B`` and ``A == B``
both collapse to true when both sides go to zero). This module scans C
sources for exactly that shape, given the macros a caller says are defined
plus whatever the scanned files themselves ``#define`` along the way.

**Placement.** This is its own module, not folded into ``scratch_check.py``,
because the trap is not decomp.me-specific: it can hide in any project header
or translation unit, independent of any scratch export. ``scratch_check.py``
imports and calls it for the ctx.c + code.c case, because that pairing is a
natural two-file scan with `metadata.json`'s `-D` flags seeded in; the CLI
also exposes it directly as ``decomp-workbench context lint FILE...`` so it
can be pointed at ordinary project sources that never touch decomp.me.

**Honest limitations of this single-pass, stdlib-only approximation:**

* Macro state is accumulated in one forward pass over the files in the order
  given. A ``#define`` is recorded unconditionally, regardless of whether the
  branch it sits in would actually be taken by a real preprocessor -- this
  scanner does not evaluate branches to decide which ``#define`` lines really
  execute, it just reads every one it encounters. This can both over- and
  under-count macros relative to a real ``cpp`` run; it is the same
  approximation a human skimming top-to-bottom would make, made explicit.
* A macro defined with no replacement text (bare ``#define NAME`` or a bare
  ``--define NAME``) is treated as the value ``1`` for arithmetic purposes,
  matching the common ``-DNAME`` compiler-flag convention. Real cpp expands
  such a macro to nothing, which is usually a syntax error if the macro is
  used as a value rather than with ``defined()`` -- this scanner would rather
  give a plausible answer than refuse to evaluate the expression at all.
* A macro whose replacement text is not itself a constant expression this
  evaluator can parse (a function-like macro, a string, a cast, an unbalanced
  fragment) is recorded as "defined, value unknown" and also treated as `1`
  when referenced bare. `defined(NAME)` is unaffected by this: it only checks
  presence in the macro table.
* Function-like macro invocations inside an expression (`FOO(x, y)`) are
  parsed just enough to skip balanced parentheses and collect any identifiers
  used as arguments; the call itself is not expanded and evaluates to the
  same substitution rule as a bare reference to `FOO`. Real cpp does not
  accept this shape for an undefined `FOO` at all (the invocation becomes
  `0(0, 0)`, a syntax error) -- this scanner favors a usable answer.
* Only `#if` and `#elif` expressions are evaluated. `#ifdef`/`#ifndef` do not
  have an expression that can "collapse" the same way -- they ask a single
  presence question -- so they are tracked only for nesting depth, not
  evaluated as findings.
* Line continuations (`\\` at end of line) are spliced before scanning;
  C-style and C++-style comments are stripped first, with a simple
  string/char-literal-aware scanner. Trigraphs and digraphs are not handled.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "CONTEXT_LINT_SCHEMA",
    "ExpressionAnalysis",
    "Finding",
    "LintReport",
    "analyze_expression",
    "file_scope_definitions",
    "lint_files",
    "lint_sources",
    "parse_defines",
    "render_report",
    "scan_conditionals",
    "strip_comments",
]

CONTEXT_LINT_SCHEMA = "decomp-workbench-context-lint-v1"

#: Severity, most actionable first. `render_report` and `LintReport.findings`
#: both sort against this so "findings sorted most-severe first" is one fact,
#: not a promise kept separately by two renderers.
_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "info": 2, "note": 3}


# ---------------------------------------------------------------------------
# Comment stripping and line splicing
# ---------------------------------------------------------------------------


def strip_comments(text: str) -> str:
    """Replace `//` and `/* */` comment content with spaces, keeping newlines.

    Line count is preserved exactly (every input `\\n` survives), so line
    numbers computed against the result still index the original source.
    String and character literals are tracked so a `//` or `/*` inside a
    quoted string is not mistaken for a comment start.
    """

    out: list[str] = []
    i, n = 0, len(text)
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    while i < n:
        ch = text[i]
        two = text[i : i + 2]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if two == "*/":
                out.append("  ")
                in_block_comment = False
                i += 2
                continue
            out.append(ch if ch == "\n" else " ")
            i += 1
            continue
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue
        if two == "//":
            in_line_comment = True
            out.append("  ")
            i += 2
            continue
        if two == "/*":
            in_block_comment = True
            out.append("  ")
            i += 2
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            in_char = True
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


@dataclass(frozen=True)
class _LogicalLine:
    """One directive line, possibly spliced from several backslash-continued
    physical lines. `start`/`end` are 1-indexed physical line numbers."""

    text: str
    start: int
    end: int


def _logical_lines(text: str) -> list[_LogicalLine]:
    physical = text.split("\n")
    result: list[_LogicalLine] = []
    i = 0
    n = len(physical)
    while i < n:
        start = i + 1
        parts = [physical[i]]
        while parts[-1].rstrip().endswith("\\") and i + 1 < n:
            parts[-1] = parts[-1].rstrip()[:-1]
            i += 1
            parts.append(physical[i])
        end = i + 1
        result.append(_LogicalLine(text="\n".join(parts), start=start, end=end))
        i += 1
    return result


# ---------------------------------------------------------------------------
# Expression tokenizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    kind: str  # "NUMBER" | "IDENT" | "OP" | "EOF"
    value: Any


class ExpressionError(ValueError):
    """A `#if`/`#elif` expression this evaluator's cpp subset cannot parse."""


_NUMBER_RE = re.compile(r"0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*")
_SUFFIX_RE = re.compile(r"[uUlL]*")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_CHAR_RE = re.compile(r"'(?:\\.|[^'\\])+'")
_TWO_CHAR_OPS = {"<<", ">>", "<=", ">=", "==", "!=", "&&", "||"}
_ONE_CHAR_OPS = set("()!~-+*/%<>^&|?:,")

_CHAR_ESCAPES = {
    "n": 10,
    "t": 9,
    "r": 13,
    "0": 0,
    "a": 7,
    "b": 8,
    "f": 12,
    "v": 11,
    "\\": 92,
    "'": 39,
    '"': 34,
}


def _int_literal_value(literal: str) -> int:
    if literal[:2] in ("0x", "0X"):
        return int(literal, 16)
    if len(literal) > 1 and literal[0] == "0":
        return int(literal, 8)
    return int(literal, 10)


def _char_literal_value(literal: str) -> int:
    body = literal[1:-1]
    if body.startswith("\\") and len(body) > 1:
        escape = body[1]
        if escape == "x":
            return int(body[2:] or "0", 16)
        if escape in _CHAR_ESCAPES:
            return _CHAR_ESCAPES[escape]
        if escape.isdigit():
            return int(body[1:], 8)
        return ord(escape)
    return ord(body[0]) if body else 0


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "'":
            match = _CHAR_RE.match(expr, i)
            if match is None:
                raise ExpressionError(
                    f"unterminated character constant near {expr[i : i + 12]!r}"
                )
            tokens.append(_Token("NUMBER", _char_literal_value(match.group(0))))
            i = match.end()
            continue
        match = _NUMBER_RE.match(expr, i)
        if match is not None:
            end = match.end()
            suffix = _SUFFIX_RE.match(expr, end)
            if suffix is not None:
                end = suffix.end()
            tokens.append(_Token("NUMBER", _int_literal_value(match.group(0))))
            i = end
            continue
        match = _IDENT_RE.match(expr, i)
        if match is not None:
            tokens.append(_Token("IDENT", match.group(0)))
            i = match.end()
            continue
        two = expr[i : i + 2]
        if two in _TWO_CHAR_OPS:
            tokens.append(_Token("OP", two))
            i += 2
            continue
        if ch in _ONE_CHAR_OPS:
            tokens.append(_Token("OP", ch))
            i += 1
            continue
        raise ExpressionError(f"unexpected character {ch!r} in preprocessor expression")
    tokens.append(_Token("EOF", None))
    return tokens


# ---------------------------------------------------------------------------
# Expression parser / evaluator
# ---------------------------------------------------------------------------


def _c_div(a: int, b: int) -> int:
    if b == 0:
        raise ExpressionError("division by zero in preprocessor expression")
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def _c_mod(a: int, b: int) -> int:
    if b == 0:
        raise ExpressionError("modulo by zero in preprocessor expression")
    return a - _c_div(a, b) * b


@dataclass
class _EvalContext:
    defines: Mapping[str, int | None]
    value_identifiers: set[str] = field(default_factory=set)
    defined_operand_identifiers: set[str] = field(default_factory=set)


class _Parser:
    """Recursive-descent evaluator for the `#if` constant-expression subset."""

    def __init__(self, tokens: list[_Token], context: _EvalContext) -> None:
        self._tokens = tokens
        self._pos = 0
        self._context = context

    def parse(self) -> int:
        value = self._conditional()
        if self._peek().kind != "EOF":
            raise ExpressionError(
                f"unexpected trailing token {self._peek().value!r}"
            )
        return value

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect_op(self, text: str) -> None:
        token = self._advance()
        if token.kind != "OP" or token.value != text:
            raise ExpressionError(f"expected {text!r}, found {token.value!r}")

    def _is_op(self, *values: str) -> bool:
        token = self._peek()
        return token.kind == "OP" and token.value in values

    def _conditional(self) -> int:
        condition = self._logical_or()
        if self._is_op("?"):
            self._advance()
            true_value = self._conditional()
            self._expect_op(":")
            false_value = self._conditional()
            return true_value if condition != 0 else false_value
        return condition

    def _logical_or(self) -> int:
        value = self._logical_and()
        while self._is_op("||"):
            self._advance()
            rhs = self._logical_and()
            value = 1 if (value != 0 or rhs != 0) else 0
        return value

    def _logical_and(self) -> int:
        value = self._bitor()
        while self._is_op("&&"):
            self._advance()
            rhs = self._bitor()
            value = 1 if (value != 0 and rhs != 0) else 0
        return value

    def _bitor(self) -> int:
        value = self._bitxor()
        while self._is_op("|"):
            self._advance()
            value |= self._bitxor()
        return value

    def _bitxor(self) -> int:
        value = self._bitand()
        while self._is_op("^"):
            self._advance()
            value ^= self._bitand()
        return value

    def _bitand(self) -> int:
        value = self._equality()
        while self._is_op("&"):
            self._advance()
            value &= self._equality()
        return value

    def _equality(self) -> int:
        value = self._relational()
        while self._is_op("==", "!="):
            op = self._advance().value
            rhs = self._relational()
            value = 1 if ((value == rhs) == (op == "==")) else 0
        return value

    def _relational(self) -> int:
        value = self._shift()
        while self._is_op("<", ">", "<=", ">="):
            op = self._advance().value
            rhs = self._shift()
            if op == "<":
                value = 1 if value < rhs else 0
            elif op == ">":
                value = 1 if value > rhs else 0
            elif op == "<=":
                value = 1 if value <= rhs else 0
            else:
                value = 1 if value >= rhs else 0
        return value

    def _shift(self) -> int:
        value = self._additive()
        while self._is_op("<<", ">>"):
            op = self._advance().value
            rhs = self._additive()
            value = value << rhs if op == "<<" else value >> rhs
        return value

    def _additive(self) -> int:
        value = self._multiplicative()
        while self._is_op("+", "-"):
            op = self._advance().value
            rhs = self._multiplicative()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _multiplicative(self) -> int:
        value = self._unary()
        while self._is_op("*", "/", "%"):
            op = self._advance().value
            rhs = self._unary()
            if op == "*":
                value = value * rhs
            elif op == "/":
                value = _c_div(value, rhs)
            else:
                value = _c_mod(value, rhs)
        return value

    def _unary(self) -> int:
        if self._is_op("!", "~", "-", "+"):
            op = self._advance().value
            operand = self._unary()
            if op == "!":
                return 1 if operand == 0 else 0
            if op == "~":
                return ~operand
            if op == "-":
                return -operand
            return operand
        return self._primary()

    def _primary(self) -> int:
        token = self._peek()
        if token.kind == "NUMBER":
            self._advance()
            return int(token.value)
        if token.kind == "IDENT":
            if token.value == "defined":
                return self._defined()
            return self._identifier()
        if self._is_op("("):
            self._advance()
            value = self._conditional()
            self._expect_op(")")
            return value
        if token.kind == "EOF":
            raise ExpressionError("unexpected end of preprocessor expression")
        raise ExpressionError(f"unexpected token {token.value!r}")

    def _defined(self) -> int:
        self._advance()  # consume "defined"
        parenthesized = self._is_op("(")
        if parenthesized:
            self._advance()
        name_token = self._advance()
        if name_token.kind != "IDENT":
            raise ExpressionError("defined() expects a macro name")
        if parenthesized:
            self._expect_op(")")
        self._context.defined_operand_identifiers.add(name_token.value)
        return 1 if name_token.value in self._context.defines else 0

    def _identifier(self) -> int:
        name = self._advance().value
        self._context.value_identifiers.add(name)
        if self._is_op("("):
            self._advance()
            if not self._is_op(")"):
                self._conditional()
                while self._is_op(","):
                    self._advance()
                    self._conditional()
            self._expect_op(")")
        defines = self._context.defines
        if name not in defines:
            return 0
        value = defines[name]
        return value if value is not None else 1


@dataclass(frozen=True)
class ExpressionAnalysis:
    """The result of parsing and evaluating one `#if`/`#elif` expression."""

    expression: str
    ok: bool
    error: str | None
    value: int | None
    value_identifiers: tuple[str, ...]
    undefined_identifiers: tuple[str, ...]
    defined_identifiers: tuple[str, ...]


def analyze_expression(
    expression: str, defines: Mapping[str, int | None]
) -> ExpressionAnalysis:
    """Parse and evaluate one constant expression against a macro table."""

    stripped = expression.strip()
    try:
        tokens = _tokenize(stripped)
        context = _EvalContext(defines=defines)
        value = _Parser(tokens, context).parse()
    except ExpressionError as error:
        return ExpressionAnalysis(
            expression=stripped,
            ok=False,
            error=str(error),
            value=None,
            value_identifiers=(),
            undefined_identifiers=(),
            defined_identifiers=(),
        )
    value_identifiers = tuple(sorted(context.value_identifiers))
    undefined = tuple(name for name in value_identifiers if name not in defines)
    defined_ = tuple(name for name in value_identifiers if name in defines)
    return ExpressionAnalysis(
        expression=stripped,
        ok=True,
        error=None,
        value=value,
        value_identifiers=value_identifiers,
        undefined_identifiers=undefined,
        defined_identifiers=defined_,
    )


# ---------------------------------------------------------------------------
# --define parsing and #define accumulation
# ---------------------------------------------------------------------------

_DEFINE_NAME_RE = re.compile(r"\s*([A-Za-z_]\w*)(\()?")
_UNDEF_NAME_RE = re.compile(r"\s*([A-Za-z_]\w*)")
_DEFINE_ENTRY_NAME_RE = re.compile(r"[A-Za-z_]\w*")


def parse_defines(values: Iterable[str]) -> dict[str, int | None]:
    """Parse repeatable `--define NAME[=VALUE]` entries in order.

    A later entry may reference an earlier one (`--define A=2 --define B=A+1`),
    matching how command-line `-D` flags are conventionally read left to
    right. A value that is not a parseable constant expression is recorded as
    "defined, value unknown" rather than rejected outright.
    """

    result: dict[str, int | None] = {}
    for raw in values:
        name, separator, value = raw.partition("=")
        name = name.strip()
        if not name or not _DEFINE_ENTRY_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid --define entry: {raw!r}")
        if not separator:
            result[name] = None
            continue
        value = value.strip()
        if not value:
            result[name] = None
            continue
        analysis = analyze_expression(value, result)
        result[name] = analysis.value if analysis.ok else None
    return result


def _accumulate_define(rest: str, defines: dict[str, int | None]) -> None:
    match = _DEFINE_NAME_RE.match(rest)
    if match is None:
        return
    name = match.group(1)
    if match.group(2):  # function-like macro: NAME( immediately follows
        defines[name] = None
        return
    remainder = rest[match.end() :].strip()
    if not remainder:
        defines[name] = None
        return
    analysis = analyze_expression(remainder, defines)
    defines[name] = analysis.value if analysis.ok else None


def _accumulate_undef(rest: str, defines: dict[str, int | None]) -> None:
    match = _UNDEF_NAME_RE.match(rest)
    if match is not None:
        defines.pop(match.group(1), None)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

#: What to DO for each finding class -- every finding earns an imperative.
_ACTIONS: dict[str, str] = {
    "always-true-by-absence": (
        "define {undefined} explicitly (--define or an earlier #define), "
        "include the header that defines it, or delete this guard if the "
        "region should always compile in"
    ),
    "always-false-by-absence": (
        "if this region should ever compile in, define {undefined} (or "
        "include its header); otherwise this guard is dead and the region "
        "can be deleted"
    ),
    "mixed-defined-undefined": (
        "{undefined} is undefined here while {defined} is defined; define "
        "{undefined} explicitly or confirm the guard is meant to depend on "
        "partial definition"
    ),
    "unparseable-expression": (
        "audit this guard by hand; the scanner could not parse its "
        "expression ({error})"
    ),
}

_SEVERITY_FOR_KIND: dict[str, str] = {
    "always-true-by-absence": "high",
    "mixed-defined-undefined": "medium",
    "always-false-by-absence": "info",
    "unparseable-expression": "note",
}


def _join(names: Sequence[str]) -> str:
    return ", ".join(names) if names else "(none)"


def _action_for(kind: str, analysis: ExpressionAnalysis) -> str:
    template = _ACTIONS[kind]
    return template.format(
        undefined=_join(analysis.undefined_identifiers),
        defined=_join(analysis.defined_identifiers),
        error=analysis.error or "unknown error",
    )


@dataclass(frozen=True)
class Finding:
    """One `#if`/`#elif` whose truth was decided by an absent identifier."""

    kind: str
    severity: str
    source: str
    directive: str
    line: int
    expression: str
    value: int | None
    undefined_identifiers: tuple[str, ...]
    defined_identifiers: tuple[str, ...]
    region_first_line: int
    region_last_line: int
    region_line_count: int
    region_first_source_line: str
    action: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "source": self.source,
            "directive": self.directive,
            "line": self.line,
            "expression": self.expression,
            "value": self.value,
            "undefined_identifiers": list(self.undefined_identifiers),
            "defined_identifiers": list(self.defined_identifiers),
            "region": {
                "first_line": self.region_first_line,
                "last_line": self.region_last_line,
                "line_count": self.region_line_count,
                "first_source_line": self.region_first_source_line,
            },
            "action": self.action,
            "error": self.error,
        }


def _classify(analysis: ExpressionAnalysis) -> str | None:
    if not analysis.ok:
        return "unparseable-expression"
    if not analysis.value_identifiers:
        return None
    if len(analysis.undefined_identifiers) == len(analysis.value_identifiers):
        if analysis.value != 0:
            return "always-true-by-absence"
        return "always-false-by-absence"
    if analysis.undefined_identifiers:
        return "mixed-defined-undefined"
    return None


@dataclass
class _PendingBranch:
    directive: str  # "if" | "elif"
    expression: str
    line: int
    region_start: int


@dataclass
class _Frame:
    pending: _PendingBranch | None


def scan_conditionals(
    text: str, source: str, defines: dict[str, int | None]
) -> list[Finding]:
    """Scan one file's `#if`/`#elif` guards, mutating `defines` as it goes.

    `defines` is both an input (macros already known, e.g. from `--define` or
    a file scanned earlier) and an output (this file's own `#define`s are
    folded in for whatever is scanned next) -- the single-pass accumulation
    the module docstring describes.
    """

    original_lines = text.split("\n")
    stripped = strip_comments(text)
    logical = _logical_lines(stripped)
    stack: list[_Frame] = []
    findings: list[Finding] = []

    def close(frame: _Frame, end_line: int) -> None:
        pending = frame.pending
        if pending is None:
            return
        region_last = max(end_line - 1, pending.region_start - 1)
        line_count = max(0, region_last - pending.region_start + 1)
        first_source_line = ""
        if line_count > 0:
            index = pending.region_start - 1
            if 0 <= index < len(original_lines):
                first_source_line = original_lines[index].strip()
        analysis = analyze_expression(pending.expression, defines)
        kind = _classify(analysis)
        if kind is not None:
            findings.append(
                Finding(
                    kind=kind,
                    severity=_SEVERITY_FOR_KIND[kind],
                    source=source,
                    directive=pending.directive,
                    line=pending.line,
                    expression=analysis.expression,
                    value=analysis.value,
                    undefined_identifiers=analysis.undefined_identifiers,
                    defined_identifiers=analysis.defined_identifiers,
                    region_first_line=pending.region_start,
                    region_last_line=region_last,
                    region_line_count=line_count,
                    region_first_source_line=first_source_line,
                    action=_action_for(kind, analysis),
                    error=analysis.error,
                )
            )
        frame.pending = None

    directive_re = re.compile(r"^[ \t]*#[ \t]*([A-Za-z_]+)(.*)$", re.DOTALL)
    for line in logical:
        match = directive_re.match(line.text)
        if match is None:
            continue
        keyword = match.group(1).strip().lower()
        rest = match.group(2)
        if keyword == "if":
            frame = _Frame(pending=None)
            frame.pending = _PendingBranch("if", rest, line.start, line.end + 1)
            stack.append(frame)
        elif keyword in ("ifdef", "ifndef"):
            stack.append(_Frame(pending=None))
        elif keyword == "elif":
            if not stack:
                continue
            frame = stack[-1]
            close(frame, line.start)
            frame.pending = _PendingBranch("elif", rest, line.start, line.end + 1)
        elif keyword == "else":
            if not stack:
                continue
            close(stack[-1], line.start)
        elif keyword == "endif":
            if not stack:
                continue
            close(stack[-1], line.start)
            stack.pop()
        elif keyword == "define":
            _accumulate_define(rest, defines)
        elif keyword == "undef":
            _accumulate_undef(rest, defines)
        # Any other directive (#include, #error, #pragma, ...) is not this
        # scanner's concern.

    eof_line = len(original_lines) + 1
    while stack:
        close(stack.pop(), eof_line)

    return findings


# ---------------------------------------------------------------------------
# Multi-file orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintReport:
    """Findings for one lint run, plus the macro table it ended with."""

    files: tuple[str, ...]
    findings: tuple[Finding, ...]
    defines: dict[str, int | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTEXT_LINT_SCHEMA,
            "files": list(self.files),
            "findings": [finding.as_dict() for finding in self.findings],
            "defines": dict(self.defines),
        }


def _sort_key(finding: Finding) -> tuple[int, str, int]:
    return (_SEVERITY_ORDER[finding.severity], finding.source, finding.line)


def lint_sources(
    sources: Sequence[tuple[str, str]],
    defines: Mapping[str, int | None] | None = None,
) -> LintReport:
    """Scan `(label, text)` pairs in order, accumulating macros across them."""

    table: dict[str, int | None] = dict(defines or {})
    findings: list[Finding] = []
    for name, text in sources:
        findings.extend(scan_conditionals(text, name, table))
    findings.sort(key=_sort_key)
    return LintReport(
        files=tuple(name for name, _ in sources),
        findings=tuple(findings),
        defines=table,
    )


def lint_files(
    paths: Sequence[str | Path],
    defines: Mapping[str, int | None] | None = None,
) -> LintReport:
    """Read and scan files from disk in the order given."""

    sources: list[tuple[str, str]] = []
    for raw_path in paths:
        path = Path(raw_path)
        text = path.read_text(encoding="utf-8")
        sources.append((str(raw_path), text))
    return lint_sources(sources, defines)


# ---------------------------------------------------------------------------
# File-scope definitions (used by scratch_check.py's duplicate-symbol pass)
# ---------------------------------------------------------------------------

_DECL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "do",
    "else",
    "goto",
    "case",
    "default",
    "break",
    "continue",
    "struct",
    "union",
    "enum",
    "void",
    "static",
    "const",
    "volatile",
    "extern",
    "register",
    "unsigned",
    "signed",
    "inline",
    "auto",
    "typedef",
}
_ARRAY_RE = re.compile(r"\[[^\]]*\]")


def _line_brace_delta(line: str) -> int:
    delta = 0
    in_string = in_char = False
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        elif ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1
        i += 1
    return delta


def _extract_declaration_name(statement: str) -> str | None:
    statement = statement.strip()
    if not statement:
        return None
    if statement.startswith("typedef"):
        typedef_idents: list[str] = [
            token
            for token in _IDENT_RE.findall(statement)
            if token not in _DECL_KEYWORDS
        ]
        return typedef_idents[-1] if typedef_idents else None
    head = statement.split("=", 1)[0]
    head = _ARRAY_RE.sub(" ", head)
    if "(" in head:
        return None  # looks like a prototype, not a definition
    idents: list[str] = [
        token for token in _IDENT_RE.findall(head) if token not in _DECL_KEYWORDS
    ]
    if len(idents) < 2:
        return None
    return idents[-1]


def _extract_function_name(signature: str) -> str | None:
    signature = signature.strip()
    if "(" not in signature:
        return None
    match = re.match(r"^[^()]*?([A-Za-z_]\w*)\s*\(", signature)
    if match is None:
        return None
    name = match.group(1)
    return None if name in _DECL_KEYWORDS else name


def file_scope_definitions(text: str) -> dict[str, int]:
    """Best-effort map of file-scope symbol name to its first defining line.

    This is a regex/brace-depth heuristic, not a parser: it recognizes the
    common single-line shapes (`static int *foo = 0;`, `TYPE name(args) {`),
    and it deliberately misses more (multi-line declarations, brace-list
    initializers, comma-separated declarators, K&R signatures split across
    lines). False negatives are expected and documented; the goal is to catch
    the shape that actually broke a decomp.me paste, not to be a C parser.
    """

    stripped = strip_comments(text)
    names: dict[str, int] = {}
    depth = 0
    for lineno, raw_line in enumerate(stripped.splitlines(), start=1):
        line = raw_line.strip()
        start_depth = depth
        depth = max(0, depth + _line_brace_delta(raw_line))
        if start_depth != 0 or not line or line.startswith("#"):
            continue
        if line.startswith("extern"):
            continue
        if line.endswith("{") and depth > start_depth:
            name = _extract_function_name(line)
            if name is not None:
                names.setdefault(name, lineno)
            continue
        if line.endswith(";") and depth == start_depth:
            name = _extract_declaration_name(line[:-1])
            if name is not None:
                names.setdefault(name, lineno)
    return names


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_report(report: LintReport) -> list[str]:
    """Render a lint report the way the CLI and scratch-check embedding do.

    Zero findings is one calm line, never silence -- a reader who ran the
    scanner deserves to know it ran, not just that nothing printed.
    """

    lines = [
        f"context lint: {len(report.findings)} finding(s) across "
        f"{len(report.files)} file(s)"
    ]
    if not report.findings:
        lines.append("no undefined-identifier collapse found in #if/#elif guards")
        return lines
    for finding in report.findings:
        header = (
            f"[{finding.severity.upper()}] {finding.kind}  "
            f"{finding.source}:{finding.line}  "
            f"#{finding.directive} {finding.expression}"
        )
        lines.append(header)
        if finding.region_line_count > 0:
            lines.append(
                f"  guarded region: lines {finding.region_first_line}-"
                f"{finding.region_last_line} ({finding.region_line_count} line(s)), "
                f"first line: {finding.region_first_source_line!r}"
            )
        else:
            lines.append("  guarded region: empty")
        if finding.undefined_identifiers:
            lines.append(f"  undefined: {', '.join(finding.undefined_identifiers)}")
        if finding.defined_identifiers:
            lines.append(f"  defined: {', '.join(finding.defined_identifiers)}")
        lines.append(f"  do: {finding.action}")
    return lines
