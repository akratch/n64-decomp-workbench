"""Read a project's linker-input symbol files and say where each pin came from.

A decompilation project hands the linker two kinds of address. One is
*derived*: ``gMainMemoryPool = main_BSS_END`` names a place in the layout and
follows it wherever the layout goes. The other is *pinned*: ``D_B0000574 =
0xB0000574`` writes an address down, and stays written down after the layout
moves out from under it. A project that wants to survive an insertion needs to
know which of its pins are which, and the file that answers the question --
DKR's ``ver/symbols/undefined_syms.txt``, splat's ``symbol_addrs`` -- is the
first thing ``shift audit`` reads.

The distinction this module refuses to collapse is *pinned* versus *wrong*.
Three of the four classes below are absolute addresses and only one of them is
a problem:

* **derived** -- the right-hand side names a symbol. Healthy by construction:
  whatever the linker decides, this follows.
* **authentic-fixed** -- an absolute address the console fixes, not the
  project: a memory-mapped register in ``kseg1`` (``SP_STATUS_REG =
  0xA4040010``), or an address on the caller's whitelist. DKR pins the
  libultra boot globals at ``0x80000300``-``0x8000031C`` and the entrypoint at
  ``0x80000400`` because the hardware and the boot code put them there; those
  are as fixed as a hardware register and are only distinguishable from an
  artifact by a caller saying so, which is what the whitelist is for.
* **artifact-suspect** -- an absolute address in a window the project itself
  owns: a bare ``kseg0`` RAM address, or the cart domain ``0xB0000000`` (which
  in DKR is literally commented "fake symbols we just need until things are
  properly matched"). These are the entries a shift can break.
* **unclassified** -- an absolute value in no window this model names, or an
  expression this reader could not fold. Reported as itself rather than
  guessed into one of the three above.

Two things this parser gets right that a ``grep '='`` does not. The comment
beside a pin is evidence -- DKR's own file admits what its two cart-window
symbols are, in a comment, one line above them -- so both the trailing comment
and the standalone comment heading the block a pin sits in are carried on the
record. And a splat ``symbol_addrs`` line puts *machine* attributes in the
same position (``aspMainTextStart = 0x800D7600; // size:0xEC0
name_end:aspMainTextEnd``), so a trailing comment whose every token is
``key:value`` is parsed as attributes rather than filed as prose.

A note on what a full ``symbol_addrs`` file means, because the count is
alarming and the conclusion is not: every entry in one is an absolute address,
by construction -- that is what the file is. It is the project's *record* of
where a not-yet-decompiled symbol lives in one particular build, and the
project regenerates it. It is not, on its own, evidence of a shiftability
problem, which is why ``shift audit`` reports the pin classes per file and
never sums them into a verdict.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mips_refs import NamedRange, RangeModel, WhitelistEntry, default_n64_windows

__all__ = [
    "ARTIFACT_SUSPECT",
    "AUTHENTIC_FIXED",
    "CLASSIFICATIONS",
    "DERIVED",
    "UNCLASSIFIED",
    "Pin",
    "PinCatalogue",
    "boot_globals_whitelist",
    "classify_absolute",
    "default_pin_model",
    "parse_pin_text",
    "parse_whitelist_text",
    "read_pin_files",
]

#: The right-hand side names a symbol: the pin follows the layout.
DERIVED = "derived"
#: An absolute address the console or the caller's whitelist fixes.
AUTHENTIC_FIXED = "authentic-fixed"
#: An absolute address in a window the project itself owns.
ARTIFACT_SUSPECT = "artifact-suspect"
#: No window named it, or the expression did not fold. Reported, not guessed.
UNCLASSIFIED = "unclassified"

#: Report order: the interesting end first, so a capped list spends its budget
#: on the entries a reader is looking for.
CLASSIFICATIONS: tuple[str, ...] = (
    ARTIFACT_SUSPECT,
    UNCLASSIFIED,
    AUTHENTIC_FIXED,
    DERIVED,
)

_CART_REASON = (
    "cart domain (0xB0000000 PI address space): an address written down in "
    "place of data the project has not matched yet"
)
_HARDWARE_REASON = (
    "memory-mapped hardware register window: fixed by the console, not by "
    "this project's layout"
)
_KSEG0_REASON = (
    "kseg0 RAM address written as a constant: it does not move when the layout moves"
)

#: The one whitelist entry nearly every N64 project needs, offered by name
#: rather than shipped by default -- `RangeModel` deliberately never carries a
#: whitelist, because only the caller knows which of its own addresses are
#: load-bearing. The high bound is one past ``entrypoint``: a half-open
#: reading of "0x80000300 to 0x80000400" would leave out the single address
#: every one of these files pins by hand.
BOOT_GLOBALS_LO = 0x80000300
BOOT_GLOBALS_HI = 0x80000404


def boot_globals_whitelist() -> WhitelistEntry:
    """The libultra boot globals and the fixed entrypoint, as one entry."""

    return WhitelistEntry(
        lo=BOOT_GLOBALS_LO,
        hi=BOOT_GLOBALS_HI,
        reason=(
            "N64 boot globals (osTvType..osAppNMIBuffer) and the fixed "
            "entrypoint: written by the boot ROM before any of this project "
            "runs"
        ),
    )


def default_pin_model(
    *,
    whitelist: Iterable[WhitelistEntry] = (),
    windows: Sequence[NamedRange] | None = None,
) -> RangeModel:
    """Build the address model a pin catalogue is classified against.

    The windows default to the console's fixed-mapping segments; the
    whitelist defaults to empty, because an address a project declares
    authentic is a claim the project makes, not one this module can infer.
    """

    return RangeModel(
        windows=tuple(windows) if windows is not None else default_n64_windows(),
        whitelist=tuple(whitelist),
    )


def classify_absolute(
    value: int, *, model: RangeModel
) -> tuple[str, str | None, str | None]:
    """Return ``(classification, window, reason)`` for one absolute address.

    The whitelist is checked first and wins outright: an address the caller
    has declared authentic is authentic whichever window it happens to fall
    in, which is exactly the DKR boot-globals case (``kseg0``, and fixed).
    """

    window, whitelisted, reason = model.classify_value(value)
    if whitelisted:
        return AUTHENTIC_FIXED, window, reason
    if window == "cart":
        return ARTIFACT_SUSPECT, window, _CART_REASON
    if window == "kseg1":
        return AUTHENTIC_FIXED, window, _HARDWARE_REASON
    if window == "kseg0":
        return ARTIFACT_SUSPECT, window, _KSEG0_REASON
    return UNCLASSIFIED, window, None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

#: ``NAME = expression``. The name must start like a C identifier, which is
#: what keeps the location counter (``. = ALIGN (., 0x10);``) out of the
#: catalogue: it shares the shape exactly and is not a pin.
_ASSIGNMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_$.]*)\s*=\s*(?P<rhs>.+)$", re.S
)

#: An identifier that is not part of a numeric literal. The lookbehind is what
#: stops ``0x80000300`` from reading as a reference to a symbol called
#: ``x80000300``.
_IDENTIFIER_RE = re.compile(r"(?<![\w$.])[A-Za-z_$][A-Za-z0-9_$.]*")

#: GNU ld expression functions. They appear in the identifier position and are
#: not references to a project symbol.
_LD_BUILTINS = frozenset(
    {
        "ABSOLUTE",
        "ADDR",
        "ALIGN",
        "ALIGNOF",
        "BLOCK",
        "CONSTANT",
        "DATA_SEGMENT_ALIGN",
        "DEFINED",
        "LENGTH",
        "LOADADDR",
        "MAX",
        "MIN",
        "ORIGIN",
        "SEGMENT_START",
        "SIZEOF",
        "SIZEOF_HEADERS",
    }
)

#: One ``key:value`` token of a splat attribute comment.
_ATTRIBUTE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:\S+$")


@dataclass(frozen=True)
class _Comment:
    line: int
    text: str
    trailing: bool
    """True when code preceded the comment on its own line."""


def _condense(text: str) -> str:
    return " ".join(text.split())


def _strip_comments(text: str) -> tuple[str, tuple[_Comment, ...]]:
    """Blank every comment out of `text` and return them separately.

    The returned text is the same length as the input with comment bytes
    replaced by spaces and newlines preserved, so an offset into it still
    resolves to the right line -- which is what lets a pin report the line it
    was written on without a second pass.
    """

    pieces: list[str] = []
    comments: list[_Comment] = []
    index = 0
    line = 1
    line_has_code = False
    size = len(text)
    while index < size:
        char = text[index]
        if char == "\n":
            pieces.append("\n")
            line += 1
            line_has_code = False
            index += 1
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            stop = size if close < 0 else close + 2
            body = text[index + 2 : (size if close < 0 else close)]
            comments.append(_Comment(line, _condense(body), line_has_code))
            span = text[index:stop]
            pieces.append("".join("\n" if item == "\n" else " " for item in span))
            line += span.count("\n")
            index = stop
            continue
        if text.startswith("//", index):
            close = text.find("\n", index)
            stop = size if close < 0 else close
            comments.append(
                _Comment(line, _condense(text[index + 2 : stop]), line_has_code)
            )
            pieces.append(" " * (stop - index))
            index = stop
            continue
        if not char.isspace():
            line_has_code = True
        pieces.append(char)
        index += 1
    return "".join(pieces), tuple(comments)


def _fold(node: ast.AST) -> int | None:
    """Evaluate a constant linker expression, or return None.

    Deliberately tiny: literals, the arithmetic and bitwise operators an ld
    script actually uses, and ``ABSOLUTE(x)`` (which is a no-op for a value).
    Anything else -- a call this reader does not model, a ternary, a location
    counter -- returns None and the pin is reported ``unresolved`` rather than
    folded into a number nobody can check.
    """

    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp):
        operand = _fold(node.operand)
        if operand is None:
            return None
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.Invert):
            return ~operand
        return None
    if isinstance(node, ast.BinOp):
        left, right = _fold(node.left), _fold(node.right)
        if left is None or right is None:
            return None
        operator = node.op
        if isinstance(operator, ast.Add):
            return left + right
        if isinstance(operator, ast.Sub):
            return left - right
        if isinstance(operator, ast.Mult):
            return left * right
        if isinstance(operator, ast.Div | ast.FloorDiv):
            return left // right if right else None
        if isinstance(operator, ast.Mod):
            return left % right if right else None
        if isinstance(operator, ast.LShift):
            return left << right
        if isinstance(operator, ast.RShift):
            return left >> right
        if isinstance(operator, ast.BitAnd):
            return left & right
        if isinstance(operator, ast.BitOr):
            return left | right
        if isinstance(operator, ast.BitXor):
            return left ^ right
        return None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ABSOLUTE"
        and len(node.args) == 1
    ):
        return _fold(node.args[0])
    return None


def _resolve(expression: str) -> tuple[str, int | None, tuple[str, ...]]:
    """Return ``(form, value, references)`` for one right-hand side."""

    references: list[str] = []
    for match in _IDENTIFIER_RE.finditer(expression):
        name = match.group(0).rstrip(".")
        if name and name not in _LD_BUILTINS and name not in references:
            references.append(name)
    if references:
        return "derived", None, tuple(references)
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        return "unresolved", None, ()
    value = _fold(tree.body)
    if value is None:
        return "unresolved", None, ()
    return "absolute", value & 0xFFFFFFFF, ()


@dataclass(frozen=True)
class Pin:
    """One ``NAME = expression`` assignment, classified and sourced."""

    name: str
    expression: str
    form: str
    """``"absolute"``, ``"derived"``, or ``"unresolved"``."""

    classification: str
    value: int | None
    window: str | None
    reason: str | None
    references: tuple[str, ...]
    source: str | None
    line: int
    comment: str | None
    """Prose written after the assignment on its own line, or ``None``."""

    context: str | None
    """The standalone comment heading the block this pin sits in."""

    attributes: tuple[tuple[str, str], ...] = ()
    """splat ``key:value`` attributes parsed out of a trailing comment."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expression": self.expression,
            "form": self.form,
            "classification": self.classification,
            "value": self.value,
            "window": self.window,
            "reason": self.reason,
            "references": list(self.references),
            "source": self.source,
            "line": self.line,
            "comment": self.comment,
            "context": self.context,
            "attributes": dict(self.attributes),
        }


def parse_pin_text(
    text: str, *, path: str | None = None, model: RangeModel
) -> tuple[Pin, ...]:
    """Parse one ld-script or ``symbol_addrs`` file's text into pins."""

    code, comments = _strip_comments(text)
    trailing = {item.line: item for item in comments if item.trailing}
    standalone = [item for item in comments if not item.trailing]

    pins: list[Pin] = []
    start = 0
    for index, char in enumerate(code):
        if char != ";":
            continue
        statement = code[start:index]
        offset = start + (len(statement) - len(statement.lstrip()))
        first_line = 1 + code.count("\n", 0, offset)
        last_line = 1 + code.count("\n", 0, index)
        start = index + 1

        match = _ASSIGNMENT_RE.match(statement)
        if match is None:
            continue
        expression = _condense(match.group("rhs"))
        form, value, references = _resolve(expression)
        if form == "derived":
            classification, window, reason = DERIVED, None, None
        elif form == "absolute":
            assert value is not None  # from _resolve
            classification, window, reason = classify_absolute(value, model=model)
        else:
            classification, window, reason = UNCLASSIFIED, None, None

        note = trailing.get(last_line)
        comment_text: str | None = None
        attributes: tuple[tuple[str, str], ...] = ()
        if note is not None and note.text:
            tokens = note.text.split()
            if tokens and all(_ATTRIBUTE_RE.match(item) for item in tokens):
                attributes = tuple(
                    (key, rest)
                    for key, _, rest in (item.partition(":") for item in tokens)
                )
            else:
                comment_text = note.text
        heading = [item for item in standalone if item.line < first_line]

        pins.append(
            Pin(
                name=match.group("name"),
                expression=expression,
                form=form,
                classification=classification,
                value=value,
                window=window,
                reason=reason,
                references=references,
                source=path,
                line=first_line,
                comment=comment_text,
                context=heading[-1].text if heading else None,
                attributes=attributes,
            )
        )
    return tuple(pins)


@dataclass(frozen=True)
class PinCatalogue:
    """Every pin the caller's files declare, with counts per class."""

    entries: tuple[Pin, ...]
    sources: tuple[str, ...]

    @property
    def counts(self) -> dict[str, int]:
        """One count per class, every class present even at zero.

        A class that vanishes when it is empty is a class a reader cannot
        tell from a class this module forgot to look for.
        """

        found = dict.fromkeys(CLASSIFICATIONS, 0)
        for item in self.entries:
            found[item.classification] = found.get(item.classification, 0) + 1
        return found

    def by_classification(self, classification: str) -> tuple[Pin, ...]:
        return tuple(
            item for item in self.entries if item.classification == classification
        )

    def ranked(self) -> tuple[Pin, ...]:
        """Every pin, suspects first, then in file order within a class."""

        order = {name: index for index, name in enumerate(CLASSIFICATIONS)}
        return tuple(
            sorted(
                self.entries,
                key=lambda item: (order.get(item.classification, len(order)),),
            )
        )

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        """The report payload, with the cap on its own detail list named."""

        counts = self.counts
        shown = self.ranked()[: max(0, limit)]
        return {
            "pin_sources": list(self.sources),
            "pins_total": len(self.entries),
            "pins_derived": counts[DERIVED],
            "pins_authentic": counts[AUTHENTIC_FIXED],
            "pins_artifact": counts[ARTIFACT_SUSPECT],
            "pins_unclassified": counts[UNCLASSIFIED],
            "pins_shown": len(shown),
            "limit": max(0, limit),
            "pins": [item.as_dict() for item in shown],
        }


def read_pin_files(paths: Iterable[str | Path], *, model: RangeModel) -> PinCatalogue:
    """Read every named pin file into one catalogue, in the order given."""

    entries: list[Pin] = []
    sources: list[str] = []
    for path in paths:
        name = str(path)
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        entries.extend(parse_pin_text(text, path=name, model=model))
        sources.append(name)
    return PinCatalogue(entries=tuple(entries), sources=tuple(sources))


# ---------------------------------------------------------------------------
# Whitelist files
# ---------------------------------------------------------------------------

_WHITELIST_RE = re.compile(
    r"^\s*(?P<lo>0[xX][0-9a-fA-F]+|\d+)"
    r"(?:\s*-\s*(?P<hi>0[xX][0-9a-fA-F]+|\d+))?"
    r"\s+(?P<reason>\S.*?)\s*$"
)


def parse_whitelist_text(text: str) -> tuple[WhitelistEntry, ...]:
    """Parse ``0xADDR reason`` / ``0xLO-0xHI reason`` lines.

    The high bound is **inclusive**, the way a person writes an address range
    on a whiteboard; `WhitelistEntry` stores the half-open form. Getting this
    backwards is not a rounding error: ``0x80000300-0x80000400`` written
    half-open excludes ``entrypoint``, which is the single address the range
    exists to cover.

    A reason is required. An address with no reason is a number somebody will
    have to re-derive later, which is the failure this whole command exists
    to prevent.
    """

    entries: list[WhitelistEntry] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _WHITELIST_RE.match(line)
        if match is None:
            raise ValueError(
                f"whitelist line {number} is not `0xADDR reason` or "
                f"`0xLO-0xHI reason`: {line!r}"
            )
        low = int(match.group("lo"), 0)
        high_text = match.group("hi")
        high = int(high_text, 0) if high_text else low
        if high < low:
            raise ValueError(
                f"whitelist line {number} ends below where it starts "
                f"(0x{low:x}-0x{high:x}); the low address comes first"
            )
        entries.append(
            WhitelistEntry(lo=low, hi=high + 1, reason=match.group("reason"))
        )
    return tuple(entries)
