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
* **rom-offset** -- an absolute value too small to be any run-time address
  and inside the ROM the map placed: a raw offset into the cartridge image.
  Splat projects are full of them (Banjo-Kazooie pins
  ``boot_core1_rzip_ROM_START = 0xF19250`` and asset-table entries like
  ``D_5E90 = 0x5E90``), and they are a class of their own rather than a
  failure to classify -- see `ROM_OFFSET`.
* **unclassified** -- an absolute value in no window this model names and not
  a ROM offset either, or an expression this reader could not fold. Reported
  as itself rather than guessed into one of the four above.

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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .mips_refs import NamedRange, RangeModel, WhitelistEntry, default_n64_windows

__all__ = [
    "ARTIFACT_SUSPECT",
    "AUTHENTIC_FIXED",
    "CLASSIFICATIONS",
    "DERIVED",
    "HARDWARE_WINDOWS",
    "ROM_OFFSET",
    "SHADOWING_PIN",
    "UNCLASSIFIED",
    "VRAM_WINDOW_FLOOR",
    "WHITELIST_REVIEW_MARKER",
    "WHITELIST_TEMPLATE_RULES",
    "Pin",
    "PinCatalogue",
    "WhitelistCandidate",
    "WhitelistRule",
    "boot_globals_whitelist",
    "classify_absolute",
    "default_pin_model",
    "parse_pin_text",
    "parse_whitelist_text",
    "read_pin_files",
    "reclassify_rom_offsets",
    "reclassify_shadowing_pins",
    "whitelist_candidates",
    "whitelist_template_text",
]

#: The right-hand side names a symbol: the pin follows the layout.
DERIVED = "derived"
#: An absolute address the console or the caller's whitelist fixes.
AUTHENTIC_FIXED = "authentic-fixed"
#: An absolute address in a window the project itself owns.
ARTIFACT_SUSPECT = "artifact-suspect"
#: A raw offset into the cartridge image: too small to be any run-time
#: address, and inside the extent the map placed. See `classify_absolute`.
ROM_OFFSET = "rom-offset"
#: An absolute pin that overrode an object's own definition of the same name.
#: See `reclassify_shadowing_pins` -- and note the spelling is shared with
#: :data:`decomp_workbench.shift_rehearse.SHADOWING_PIN`, deliberately: the
#: static audit and the rehearsal find the same defect from two directions.
SHADOWING_PIN = "shadowing-pin"
#: No window named it, it is not a ROM offset, or the expression did not
#: fold. Reported, not guessed.
UNCLASSIFIED = "unclassified"

#: Report order: the interesting end first, so a capped list spends its budget
#: on the entries a reader is looking for. `SHADOWING_PIN` leads because it is
#: the only class that carries a *proven-free* remediation -- the object
#: already defines the symbol, so deleting the pin is byte-identical at the
#: current layout, which S6 demonstrated by ablation rather than argued.
#: `ROM_OFFSET` sits between the suspects and the unclassified because it is
#: the same *kind* of finding as a suspect -- a written-down number with a
#: named remediation -- while being strictly better understood than an entry
#: nothing could name at all.
CLASSIFICATIONS: tuple[str, ...] = (
    SHADOWING_PIN,
    ARTIFACT_SUSPECT,
    ROM_OFFSET,
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
_ROM_OFFSET_REASON = (
    "raw ROM offset: below every run-time RAM window and inside the extent "
    "this map places, so it addresses the cartridge image rather than memory. "
    "Symbolize it against the linker's own <segment>_ROM_START/_ROM_END "
    "symbols and it follows the layout instead of being written down"
)

#: The lowest address any window in `default_n64_windows` calls run-time RAM.
#: Derived from the windows at or above this floor rather than from "the
#: lowest window there is" on purpose: that model's ``segmented`` window
#: (``0x00000000-0x08000000``) is a heuristic about how some asset systems
#: address memory, not a RAM segment, and a value inside it is exactly the
#: shape `ROM_OFFSET` exists to name.
VRAM_WINDOW_FLOOR = 0x80000000


def _vram_floor(model: RangeModel) -> int:
    """The lowest run-time-RAM window start `model` names."""

    return min(
        (item.lo for item in model.windows if item.lo >= VRAM_WINDOW_FLOOR),
        default=VRAM_WINDOW_FLOOR,
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
    value: int, *, model: RangeModel, rom_extent: int | None = None
) -> tuple[str, str | None, str | None]:
    """Return ``(classification, window, reason)`` for one absolute address.

    The whitelist is checked first and wins outright: an address the caller
    has declared authentic is authentic whichever window it happens to fall
    in, which is exactly the DKR boot-globals case (``kseg0``, and fixed).

    ``rom_extent`` is the map's own placed extent (see
    :attr:`~decomp_workbench.shift_audit.ConsistencyCheck.max_placed_extent`),
    and it is what turns a whole family of "the model has no name for this"
    entries into `ROM_OFFSET`. A splat project pins raw cartridge offsets by
    the dozen -- Banjo-Kazooie's ``rzip_dummy_addrs`` writes
    ``boot_core1_rzip_ROM_START = 0xF19250`` and its level tables write
    ``D_5E90 = 0x5E90`` -- and every one of them lands *below* the lowest
    run-time RAM window (`VRAM_WINDOW_FLOOR`) and *inside* what the map
    placed. Neither half alone is evidence: a small number could be anything,
    and "inside the ROM" is true of every kseg0 address once you mask the
    segment off. Together they are specific, and they carry a remediation an
    unclassified entry does not (`_ROM_OFFSET_REASON`).

    Handing no ``rom_extent`` keeps the four-class answer this function gave
    before -- a caller with no map cannot bound the ROM and is not asked to
    guess one.
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
    if rom_extent is not None and 0 <= value < min(rom_extent, _vram_floor(model)):
        return ROM_OFFSET, window, _ROM_OFFSET_REASON
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
    text: str,
    *,
    path: str | None = None,
    model: RangeModel,
    rom_extent: int | None = None,
) -> tuple[Pin, ...]:
    """Parse one ld-script or ``symbol_addrs`` file's text into pins.

    ``rom_extent`` is forwarded to `classify_absolute` for the `ROM_OFFSET`
    class. A caller that reads its pins before it has a map (``shift audit``
    does, so a misspelled census key costs nothing) leaves it out here and
    runs `reclassify_rom_offsets` once the map's extent is known.
    """

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
            classification, window, reason = classify_absolute(
                value, model=model, rom_extent=rom_extent
            )
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
            "pins_rom_offset": counts[ROM_OFFSET],
            "pins_shadowing": counts[SHADOWING_PIN],
            "pins_unclassified": counts[UNCLASSIFIED],
            "pins_shown": len(shown),
            "limit": max(0, limit),
            "pins": [item.as_dict() for item in shown],
        }


def read_pin_files(
    paths: Iterable[str | Path], *, model: RangeModel, rom_extent: int | None = None
) -> PinCatalogue:
    """Read every named pin file into one catalogue, in the order given."""

    entries: list[Pin] = []
    sources: list[str] = []
    for path in paths:
        name = str(path)
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        entries.extend(
            parse_pin_text(text, path=name, model=model, rom_extent=rom_extent)
        )
        sources.append(name)
    return PinCatalogue(entries=tuple(entries), sources=tuple(sources))


def reclassify_rom_offsets(
    catalogue: PinCatalogue, *, model: RangeModel, rom_extent: int
) -> PinCatalogue:
    """Re-answer the `ROM_OFFSET` question once the map's extent is known.

    ``shift audit`` reads its pin files before it reads the map, on purpose:
    a sweep that misspells a ``--census`` key or a ``--whitelist`` line
    should learn about it without paying for a 10 MB image. That order means
    the pins are first classified with no ROM bound at all, which is honest
    but leaves every raw cartridge offset sitting in `UNCLASSIFIED`. This is
    the second pass, run once, from
    :func:`~decomp_workbench.shift_audit.build_shift_audit`.

    Only `UNCLASSIFIED` absolutes are re-examined. Nothing a window already
    named can move -- `classify_absolute` answers the window branches before
    it ever looks at the ROM extent, so re-running it on an entry that landed
    in one of them would return the same answer, and restricting the pass
    makes that a property of the code rather than of the reader's memory.
    """

    entries: list[Pin] = []
    for item in catalogue.entries:
        if item.classification != UNCLASSIFIED or item.value is None:
            entries.append(item)
            continue
        classification, window, reason = classify_absolute(
            item.value, model=model, rom_extent=rom_extent
        )
        if classification != ROM_OFFSET:
            entries.append(item)
            continue
        entries.append(
            replace(item, classification=classification, window=window, reason=reason)
        )
    return PinCatalogue(entries=tuple(entries), sources=catalogue.sources)


_SHADOWING_REASON = (
    "an object in this link already defines this symbol, and the linker "
    "script's assignment silently overrode it (GNU ld does that with no "
    "warning). The linked ELF still carries the losing definition's size and "
    "type on the surviving absolute symbol, which is how this was detected. "
    "Deleting the pin restores the object's own definition, which follows the "
    "layout for free -- and is byte-identical at the current layout, since "
    "both spellings resolve to the same address today"
)


def reclassify_shadowing_pins(catalogue: PinCatalogue, *, elf: Any) -> PinCatalogue:
    """WB-143b: re-answer a pin's class against the ELF the link produced.

    ``elf`` is a :class:`~decomp_workbench.ldmap.ElfSymbols` (typed loosely
    to keep this module free of an import cycle with the reader it is handed
    from). A pin is reclassified `SHADOWING_PIN` when the ELF's symbol of the
    same name is absolute *and* carries a non-zero size -- see
    :attr:`~decomp_workbench.ldmap.ElfSymbol.shadows_definition` for why that
    is the evidence and not a heuristic.

    **This is statically detectable with no shift at all**, which is the
    whole point of putting it in the audit as well as the rehearsal. S6 found
    pilotwings64's ten by relinking twice, running ``nm`` over both ELFs by
    hand, and then ablating the pin file to prove causation; the same ten
    fall out of one shipped ``.elf`` and one pin file here. Measured on that
    project: 10 of 37, no misses, no false positives.

    Every class is re-examined, unlike `reclassify_rom_offsets` -- because
    this evidence outranks every window-based answer. ``D_803571F0`` is a
    kseg0 constant and would otherwise stay `ARTIFACT_SUSPECT` forever: true,
    but strictly weaker than "an object already defines it, delete it".
    Derived pins are the one exception: a pin whose right-hand side names a
    symbol already follows the layout, and a name collision with an object
    would be a different (and much louder) problem than this one.
    """

    entries: list[Pin] = []
    for item in catalogue.entries:
        symbol = elf.symbol(item.name) if item.form != "derived" else None
        if symbol is None or not symbol.shadows_definition:
            entries.append(item)
            continue
        entries.append(
            replace(
                item,
                classification=SHADOWING_PIN,
                reason=_SHADOWING_REASON,
            )
        )
    return PinCatalogue(entries=tuple(entries), sources=catalogue.sources)


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


# ---------------------------------------------------------------------------
# Whitelist templates
# ---------------------------------------------------------------------------

#: What every drafted line in an emitted template is prefixed with. The
#: entries are emitted **commented out**, and this is why: a whitelist entry
#: is a claim the project makes about its own addresses ("this one is fixed
#: by the console, not by my layout"), and nothing that reads a linker map
#: can make that claim on the project's behalf. A file whose lines are live
#: on arrival would let a caller declare a hundred pins authentic by
#: redirecting one command into `--whitelist`, which is precisely the
#: re-derive-it-later failure the whitelist grammar's mandatory reason exists
#: to prevent. Uncommenting a line is the smallest possible act of reading
#: it.
WHITELIST_REVIEW_MARKER = "# REVIEW:"


@dataclass(frozen=True)
class WhitelistRule:
    """One published reason a pin was drafted into a whitelist template."""

    name: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence}


#: The evidence families `whitelist_candidates` drafts from, as data for the
#: same reason `shift_audit.TIER_RULES` is: a reader has to be able to see
#: which shapes the tool looked for, and a new one should be one entry rather
#: than a new code path. Both are *candidacy* rules -- they say a pin has the
#: shape of an authentic fixed address, never that it is one.
WHITELIST_TEMPLATE_RULES: tuple[WhitelistRule, ...] = (
    WhitelistRule(
        "hardware-window",
        "the value falls in a memory-mapped hardware window (kseg1, or the "
        "cart domain inside it): an address the console fixes, which no "
        "layout change can move",
    ),
    WhitelistRule(
        "below-window-floor",
        "a kseg0 constant below the movable window's own floor: it cannot be "
        "an address this layout owns, and it is the shape of the libultra "
        "boot globals the boot ROM writes before any of this project runs",
    ),
)

#: Windows whose members the `hardware-window` rule drafts.
HARDWARE_WINDOWS: tuple[str, ...] = ("kseg1", "cart")


@dataclass(frozen=True)
class WhitelistCandidate:
    """One drafted template line, with the pin it was drafted from."""

    value: int
    name: str
    rule: str
    reason: str
    """The drafted right-hand side of the whitelist line: prose a human
    rewrites, never a claim this module is entitled to make."""

    window: str | None
    source: str | None
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "name": self.name,
            "rule": self.rule,
            "reason": self.reason,
            "window": self.window,
            "source": self.source,
            "line": self.line,
        }


def whitelist_candidates(
    catalogue: PinCatalogue, *, window_lo: int
) -> tuple[WhitelistCandidate, ...]:
    """Draft one template line per pin that has an authentic-fixed shape.

    ``window_lo`` is the movable window's floor (see
    :func:`~decomp_workbench.shift_audit.movable_window`), and it is what
    makes the second rule evidence rather than a guess: a ``kseg0`` constant
    *below* the lowest address an insertion could move is, by construction,
    not an address this project's layout places.

    A pin the caller's existing whitelist already covers is not drafted
    again. Those arrive classified `AUTHENTIC_FIXED` while still sitting in a
    project-owned window, which is a shape only a whitelist hit produces --
    re-emitting them would ask a reader to review a decision they have
    already made and written down.
    """

    found: list[WhitelistCandidate] = []
    for pin in catalogue.entries:
        if pin.form != "absolute" or pin.value is None:
            continue
        if pin.window in HARDWARE_WINDOWS:
            rule = "hardware-window"
            reason = (
                f"{pin.name}: memory-mapped hardware address in the "
                f"{pin.window} window, fixed by the console rather than by "
                "this project's layout"
            )
        elif pin.window == "kseg0" and pin.value < window_lo:
            if pin.classification == AUTHENTIC_FIXED:
                continue  # already on the caller's whitelist, with a reason
            rule = "below-window-floor"
            reason = (
                f"{pin.name}: kseg0 constant below the movable window floor "
                f"0x{window_lo:08x}, so no insertion moves it -- boot-globals "
                "shaped"
            )
        else:
            continue
        found.append(
            WhitelistCandidate(
                value=pin.value,
                name=pin.name,
                rule=rule,
                reason=reason,
                window=pin.window,
                source=pin.source,
                line=pin.line,
            )
        )
    return tuple(sorted(found, key=lambda item: (item.value, item.name)))


def whitelist_template_text(
    catalogue: PinCatalogue,
    *,
    window_lo: int,
    window_lo_section: str | None = None,
) -> str:
    """Render a skeleton whitelist file from a catalogue's own evidence.

    Every drafted entry is emitted commented out and marked
    `WHITELIST_REVIEW_MARKER`, with the pin, file and line it came from on
    the line above it. The file therefore parses to *no* entries until a
    human has removed a ``# `` -- `parse_whitelist_text` reads it happily and
    finds nothing, which is the correct answer for a template nobody has
    reviewed yet.
    """

    candidates = whitelist_candidates(catalogue, window_lo=window_lo)
    floor = f"0x{window_lo:08x}"
    if window_lo_section:
        floor = f"{floor} ({window_lo_section})"
    lines = [
        "# shift audit --emit-whitelist: a skeleton, not a whitelist.",
        "#",
        "# Format: `0xADDR reason` or `0xLO-0xHI reason`, one per line, high",
        "# bound inclusive, # comments ignored. A reason is required: an",
        "# address with no reason is one somebody re-derives later.",
        "#",
        "# Every entry below is COMMENTED OUT. A whitelist entry is a claim",
        "# your project makes about its own addresses, and reading a linker",
        "# map does not entitle this command to make it for you. Delete the",
        "# lines that are not authentic, rewrite the reasons on the ones",
        "# that are, and remove the leading `# ` to turn one on.",
        "#",
        f"# movable window floor: {floor}",
    ]
    for source in catalogue.sources:
        lines.append(f"# pin_sources: {source}")
    lines.append(f"# pins_total: {len(catalogue.entries)}")
    lines.append(f"# candidates: {len(candidates)}")
    for rule in WHITELIST_TEMPLATE_RULES:
        drafted = sum(1 for item in candidates if item.rule == rule.name)
        lines.append(f"#   {rule.name} ({drafted}): {rule.evidence}")
    if not candidates:
        lines.extend(
            (
                "#",
                "# No pin in these files has either shape. That is a result,",
                "# not an error: this project writes down no hardware address",
                "# and no constant below its own movable window floor.",
                "",
            )
        )
        return "\n".join(lines)
    for item in candidates:
        where = item.source or "-"
        lines.extend(
            (
                "",
                f"{WHITELIST_REVIEW_MARKER} {item.name} "
                f"({where}:{item.line}), rule {item.rule}",
                f"# 0x{item.value:08X} {item.reason}",
            )
        )
    lines.append("")
    return "\n".join(lines)
