"""Attribute differing words to the source constructs that emitted them.

Every campaign rebuilds this by hand, and it is the single most repeated
manual step in a late-stage investigation: "which source lines own these
rows". The answer has to come out of an object with no debug information, so
it comes out of the one signal such an object still carries -- its call
relocations.

The mechanism
-------------
A direct call to a symbol the assembler could not resolve leaves an
``R_MIPS_26`` relocation carrying the callee's *name*. Read in ascending
section offset, those relocations are the object's call sequence. Scanning the
C source for call expressions gives a second sequence, in file order. Aligning
the two *by name* pairs object offsets with source lines, and each pair is an
anchor. A differing word is then reported as lying between the two anchors
that bracket it.

Three decisions make this honest rather than merely plausible.

**The object is ground truth and the source is a hypothesis.** The source-side
scan is a regex, and a regex cannot tell a call from a macro, a declaration,
or a cast. It does not have to. Only the *alignment* is trusted: a spurious
source-side name has no matching relocation, falls out of the alignment, and
is discarded. That is what lets a cheap scanner be safe.

**Ambiguity is dropped, not guessed.** Text order and emission order disagree
whenever a call is nested -- ``f(g(x))`` reads outer-first and emits
inner-first. Those pairs are dropped from the anchor set and counted, rather
than force-matched into a wrong line. One real campaign lost 14 of 318 anchors
exactly this way, and reported 304 rather than pretending to 318.

**The answer is a bracket, never a point.** Instruction density per source line
varies by an order of magnitude -- a ``sqrtf`` call is two instructions, a
matrix build is two hundred -- so interpolating a line number between two
anchors would be fabrication. A row that falls between calls sixty lines apart
gets a sixty-line answer, and the report says how wide its brackets are.

What this cannot do
-------------------
Calls to ``static`` functions in the same translation unit, and calls the
compiler inlined, emit no relocation and therefore no anchor. Stretches of the
object built entirely from them are bracketed only by whatever calls surround
them, which can be far away. That is reported as coverage, not hidden.

And ranking by count is not the same as ranking by work: when the two objects
disagree on instruction count, every branch immediate after the divergence
differs mechanically. Fourteen of one campaign's forty-two "constant" rows
were that shadow, and would have vanished for free from one upstream fix. The
report says so whenever the counts differ, because a ranking that presents
shadow rows as a top region is worse than no ranking.
"""

from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .model import Instruction

#: The MIPS relocation a direct `jal` to an unresolved symbol leaves behind.
#: This is the only signal used for anchoring: it is present with no debug
#: information, it is ordered, and it carries the callee's name.
CALL_RELOCATION = "R_MIPS_26"

#: Site classes excluded from attribution. Relocation differences are symbol
#: naming, not emitted code, and counting them would swamp the ranking with
#: rows no source edit moves.
EXCLUDED_CLASSES = ("relocation-layout", "relocation-controlled")

#: Identifiers that can be followed by `(` without being a call.
_NOT_CALLS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "switch",
        "return",
        "sizeof",
        "do",
        "case",
        "defined",
        "typedef",
        "struct",
        "union",
        "enum",
        "static",
        "const",
        "volatile",
        "unsigned",
        "signed",
        "void",
        "char",
        "short",
        "int",
        "long",
        "float",
        "double",
        "register",
        "extern",
        "goto",
        "break",
        "continue",
    }
)

_CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_RE = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")


class RegionError(ValueError):
    """Region attribution could not be performed, with the reason why."""


@dataclass(frozen=True)
class Anchor:
    """One object offset paired with the source line that emitted it."""

    address: int
    line: int
    symbol: str

    def as_dict(self) -> dict[str, Any]:
        return {"address": self.address, "line": self.line, "symbol": self.symbol}


@dataclass(frozen=True)
class Region:
    """One bracket of source, with the differing words attributed to it."""

    low_line: int | None
    high_line: int | None
    low_symbol: str | None
    high_symbol: str | None
    words: int
    classes: dict[str, int]
    first_address: int

    @property
    def width(self) -> int | None:
        """Source lines spanned, or ``None`` when the bracket is open-ended."""

        if self.low_line is None or self.high_line is None:
            return None
        return self.high_line - self.low_line

    def label(self, source: str) -> str:
        """Render the citation: ``file:lo-hi``, or an honest open end."""

        if self.low_line is None and self.high_line is None:
            return f"{source}:(unanchored)"
        if self.low_line is None:
            return f"{source}:1-{self.high_line} (before the first call)"
        if self.high_line is None:
            return f"{source}:{self.low_line}-end (after the last call)"
        if self.low_line == self.high_line:
            return f"{source}:{self.low_line}"
        return f"{source}:{self.low_line}-{self.high_line}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "low_line": self.low_line,
            "high_line": self.high_line,
            "low_symbol": self.low_symbol,
            "high_symbol": self.high_symbol,
            "words": self.words,
            "classes": dict(sorted(self.classes.items())),
            "first_address": self.first_address,
            "width": self.width,
        }


@dataclass(frozen=True)
class RegionReport:
    """Ranked region attribution, with the coverage that qualifies it."""

    source: str
    regions: tuple[Region, ...]
    anchors: tuple[Anchor, ...]
    object_calls: int
    source_calls: int
    dropped: tuple[str, ...]
    attributed_words: int
    excluded_words: int
    caveats: tuple[str, ...] = field(default_factory=tuple)

    @property
    def median_width(self) -> int | None:
        widths = sorted(
            region.width for region in self.regions if region.width is not None
        )
        if not widths:
            return None
        return widths[len(widths) // 2]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "method": "call-relocation anchoring",
            "regions": [region.as_dict() for region in self.regions],
            "object_calls": self.object_calls,
            "source_calls": self.source_calls,
            "anchors": len(self.anchors),
            "dropped_calls": list(self.dropped),
            "attributed_words": self.attributed_words,
            "excluded_words": self.excluded_words,
            "median_bracket_width": self.median_width,
            "caveats": list(self.caveats),
        }


def strip_noncode(text: str) -> str:
    """Blank out comments and string literals, preserving line numbering.

    Replacement keeps every newline so a match's line number is still the
    line it was written on. Nothing here needs to be a real preprocessor:
    the alignment discards whatever this gets wrong.
    """

    def blank(match: re.Match[str]) -> str:
        return "".join(
            "\n" if character == "\n" else " " for character in match.group()
        )

    text = _BLOCK_COMMENT_RE.sub(blank, text)
    text = _LINE_COMMENT_RE.sub(blank, text)
    return _STRING_RE.sub(blank, text)


def source_calls(text: str) -> list[tuple[int, str]]:
    """Return ``(line, callee)`` for every call-shaped expression, in file order.

    Deliberately permissive. A macro invocation or a declaration that looks
    like a call is a false positive here and is removed by the alignment,
    which is cheaper and safer than teaching this function C.
    """

    cleaned = strip_noncode(text)
    calls: list[tuple[int, str]] = []
    for match in _CALL_RE.finditer(cleaned):
        name = match.group("name")
        if name in _NOT_CALLS:
            continue
        line = cleaned.count("\n", 0, match.start()) + 1
        calls.append((line, name))
    return calls


def object_calls(instructions: list[Instruction]) -> list[tuple[int, str]]:
    """Return ``(address, callee)`` for every call relocation, in emission order."""

    calls: list[tuple[int, str]] = []
    for item in instructions:
        for relocation in item.relocations:
            if relocation.kind == CALL_RELOCATION and relocation.symbol:
                calls.append((item.address, relocation.symbol))
    return calls


def build_anchors(
    object_side: list[tuple[int, str]], source_side: list[tuple[int, str]]
) -> tuple[tuple[Anchor, ...], tuple[str, ...]]:
    """Align the two call sequences by name; keep only unambiguous pairs.

    A positional zip would "work" whenever the two sequences happen to be the
    same length, and be silently wrong wherever a nested call reordered them.
    The sequence alignment is what turns that silent error into a counted
    omission.
    """

    from difflib import SequenceMatcher

    object_names = [name for _address, name in object_side]
    source_names = [name for _line, name in source_side]
    matcher = SequenceMatcher(a=object_names, b=source_names, autojunk=False)
    anchors: list[Anchor] = []
    dropped: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                address, name = object_side[i1 + offset]
                line, _name = source_side[j1 + offset]
                anchors.append(Anchor(address=address, line=line, symbol=name))
        else:
            dropped.extend(object_names[i1:i2])
            dropped.extend(source_names[j1:j2])
    # Monotone by construction, but assert it: a non-monotone anchor list
    # would silently produce brackets that read backwards.
    monotone: list[Anchor] = []
    for anchor in anchors:
        if monotone and anchor.line < monotone[-1].line:
            dropped.append(anchor.symbol)
            continue
        monotone.append(anchor)
    return tuple(monotone), tuple(dropped)


def _bracket(
    address: int, addresses: list[int], anchors: tuple[Anchor, ...]
) -> tuple[Anchor | None, Anchor | None]:
    position = bisect.bisect_left(addresses, address)
    if position < len(addresses) and addresses[position] == address:
        return anchors[position], anchors[position]
    low = anchors[position - 1] if position > 0 else None
    high = anchors[position] if position < len(anchors) else None
    return low, high


def attribute_sites(
    sites: list[dict[str, Any]],
    candidate: list[Instruction],
    anchors: tuple[Anchor, ...],
) -> tuple[tuple[Region, ...], int, int]:
    """Group differing sites into bracketed regions, ranked by word count."""

    addresses = [anchor.address for anchor in anchors]
    buckets: dict[tuple[int | None, int | None], list[dict[str, Any]]] = {}
    keys: dict[tuple[int | None, int | None], tuple[Anchor | None, Anchor | None]] = {}
    attributed = 0
    excluded = 0
    for site in sites:
        classification = str(site.get("class", ""))
        if classification in EXCLUDED_CLASSES:
            excluded += 1
            continue
        index = int(site["index"])
        if index >= len(candidate):
            # A word the candidate does not have: an instruction-count site on
            # the target's side. It has no candidate address to anchor.
            address = candidate[-1].address if candidate else 0
        else:
            address = candidate[index].address
        low, high = _bracket(address, addresses, anchors)
        key = (low.line if low else None, high.line if high else None)
        buckets.setdefault(key, []).append(site)
        keys.setdefault(key, (low, high))
        attributed += 1

    regions: list[Region] = []
    for key, members in buckets.items():
        low, high = keys[key]
        classes = Counter(str(item.get("class", "")) for item in members)
        first = min(
            (
                candidate[int(item["index"])].address
                for item in members
                if int(item["index"]) < len(candidate)
            ),
            default=0,
        )
        regions.append(
            Region(
                low_line=key[0],
                high_line=key[1],
                low_symbol=low.symbol if low else None,
                high_symbol=high.symbol if high else None,
                words=len(members),
                classes=dict(sorted(classes.items())),
                first_address=first,
            )
        )
    regions.sort(key=lambda region: (-region.words, region.first_address))
    return tuple(regions), attributed, excluded


def build_region_report(
    *,
    source_path: str,
    source_text: str,
    candidate: list[Instruction],
    sites: list[dict[str, Any]],
    instruction_delta: int = 0,
) -> RegionReport:
    """Build the full ranked attribution for one candidate and its source."""

    object_side = object_calls(candidate)
    if not object_side:
        raise RegionError(
            "the candidate object carries no call relocations, so there is "
            "nothing to anchor source lines to. Calls to static functions in "
            "the same translation unit, and calls the compiler inlined, emit "
            "no relocation; a function built entirely from them cannot be "
            "attributed this way."
        )
    source_side = source_calls(source_text)
    if not source_side:
        raise RegionError(
            f"no call expressions were found in {source_path}; check that it "
            "is the C source that produced this object"
        )
    anchors, dropped = build_anchors(object_side, source_side)
    if not anchors:
        raise RegionError(
            f"none of the {len(object_side)} call relocation(s) in the object "
            f"matched any of the {len(source_side)} call expression(s) in "
            f"{source_path} by name. This usually means the source is not the "
            "one that produced this object."
        )
    regions, attributed, excluded = attribute_sites(sites, candidate, anchors)
    report = RegionReport(
        source=source_path,
        regions=regions,
        anchors=anchors,
        object_calls=len(object_side),
        source_calls=len(source_side),
        dropped=dropped,
        attributed_words=attributed,
        excluded_words=excluded,
    )
    return RegionReport(
        source=report.source,
        regions=report.regions,
        anchors=report.anchors,
        object_calls=report.object_calls,
        source_calls=report.source_calls,
        dropped=report.dropped,
        attributed_words=report.attributed_words,
        excluded_words=report.excluded_words,
        caveats=_caveats(report, instruction_delta=instruction_delta),
    )


def _caveats(report: RegionReport, *, instruction_delta: int) -> tuple[str, ...]:
    """State what this attribution is, and what it is not, every time."""

    caveats: list[str] = [
        "attribution is call-relocation anchoring: each row is placed between "
        "the two calls that bracket it, never interpolated to a line. A row "
        "between calls 60 lines apart gets a 60-line answer."
    ]
    unmatched = report.object_calls - len(report.anchors)
    if unmatched > 0:
        caveats.append(
            f"{len(report.anchors)} of {report.object_calls} call relocation(s) "
            f"anchored; {unmatched} dropped where the object's call order and "
            "the source's text order disagree. That is normally a nested call "
            "-- f(g(x)) reads outer-first and emits inner-first -- and dropping "
            "it is deliberate: a guessed line is worse than a wider bracket."
        )
    width = report.median_width
    if width is not None:
        caveats.append(
            f"median bracket is {width} source line(s) wide. Static and "
            "inlined callees emit no relocation, so stretches built from them "
            "are bracketed only by whatever calls surround them."
        )
    if instruction_delta:
        caveats.append(
            f"the two objects differ by {abs(instruction_delta)} instruction(s), "
            "so rows after the divergence are shifted and their branch "
            "immediates differ mechanically. Some of the counts below are that "
            "shadow rather than independent work, and will vanish when the "
            "count is fixed -- rank with that in mind."
        )
    if report.excluded_words:
        caveats.append(
            f"{report.excluded_words} relocation-class word(s) excluded: they "
            "are symbol naming, not emitted code, and no source edit moves them."
        )
    return tuple(caveats)


def render_region_report(
    report: RegionReport, *, limit: int | None = None
) -> list[str]:
    """Render the ranked regions, then the coverage that qualifies them."""

    lines = [
        f"by-region: {report.attributed_words} differing word(s) across "
        f"{len(report.regions)} region(s) of {report.source}",
        f"anchors: {len(report.anchors)} of {report.object_calls} object call(s) "
        f"matched against {report.source_calls} source call expression(s)",
        "",
    ]
    shown = report.regions if limit is None else report.regions[:limit]
    if shown:
        width = max(len(region.label(report.source)) for region in shown)
        for region in shown:
            classes = " ".join(
                f"{name}={count}" for name, count in region.classes.items()
            )
            lines.append(
                f"  {region.label(report.source).ljust(width)}  "
                f"{str(region.words).rjust(5)} word(s)  {classes}"
            )
    else:
        lines.append("  (no differing words outside the relocation classes)")
    if limit is not None and len(report.regions) > limit:
        lines.append(
            f"  ({len(report.regions) - limit} further region(s); "
            "pass --by-region-limit 0 for all)"
        )
    if report.caveats:
        lines.append("")
        lines.append("how to read this:")
        for caveat in report.caveats:
            lines.extend(_wrap(caveat))
    return [line.rstrip() for line in lines]


def _wrap(text: str, *, width: int = 78) -> list[str]:
    lines: list[str] = []
    current = "  - "
    for word in text.split():
        if len(current) + len(word) + 1 > width and current.strip(" -"):
            lines.append(current.rstrip())
            current = "    "
        current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    return lines
