"""Statement-line (`.loc`) boundaries under a `schedule` residual.

`verdict=schedule-mismatch` — the same instruction multiset in a different
order, register allocation identical — has one documented lever in this
project's field guide: rebuild at `-g0` and see whether the region collapses
(lever 3).  That probe is *vacuous for a project that already builds `-g0`*,
and a reader who runs it, sees nothing move, and concludes "the compiler must
be exotic" has been sent to a dead family by the tool.  One campaign spent
hours there: IDO 5.2, 5.3, 6.0, 7.1 and MIPSpro 7.4.4, every `as1` flag and
pipeline model, all producing byte-identical output.

The property that actually owned the residue is not in any manual:

    cfe takes each statement's source line number from its *preprocessed*
    input, and uopt/ugen treat a statement line boundary as an instruction
    scheduling barrier -- at `-g0` as well as at `-g3`.

So the same token stream compiles two ways depending only on which source line
each statement is attributed to.  cfe's internal cpp puts every statement of a
multi-line macro expansion on the invocation's first line; IDO's external
`acpp` puts them on the invocation's successive lines.  On SSB64 `drawbitmap`
(1479 instructions) that difference alone was 59 schedule-swapped words, and
preprocessing with `acpp` took it to zero.

This module makes that mechanism *visible* rather than folkloric.  Given the
assembly listing ugen wrote for the candidate (`ugen -l`, or the `.s` the IDO
driver keeps with `-K`), it reports, for each schedule-divergent site, the
`.loc` statement lines of the instructions involved -- and therefore whether
the reordering crosses a statement boundary at all.

Matching strategy, and what it cannot do
----------------------------------------

The listing is *pre-as1*: `li` is still a macro, delay slots are not yet
filled, and registers may be spelled numerically.  Its instruction stream is
therefore close to, but not the same as, the disassembly the diagnosis was
built from.  Sites are mapped in two passes, mirroring `view._skeleton`:

1. align the candidate disassembly against the listing on *normalized
   instruction text* (lowercased, whitespace collapsed).  These are strong
   anchors: an instruction that survives as1 unchanged pairs exactly;
2. inside each region the first pass could not pair, align again on the
   *mnemonic alone*, which pairs an instruction whose operands were respelled;
3. anything still unpaired is **unmapped**, and is reported as unmapped.  It is
   never guessed at by position, because a guessed statement line is worse than
   a missing one -- it would invent the very evidence this screen exists to
   supply.

A site's window is the candidate instructions its hunk covers.  A hunk holding
fewer than two of them -- which is the ordinary shape of an adjacent
transposition, where the aligner reports one insertion and one deletion around
a matched anchor -- is widened by one candidate instruction on each side, since
a single instruction cannot show what it was reordered past.  Widening is
recorded per site and printed.

A hunk with no candidate instruction at all (a pure target-side deletion) is
**not** a site: the listing describes the candidate, and nothing in it can say
which statement the *target's* instruction came from.  Those hunks are counted
and named in the output rather than dropped.

Limitations, stated rather than hidden: the listing must be the one that
produced this candidate object (nothing here verifies that); the majority rule
below is a heuristic for routing, not a proof; and a function whose listing
mnemonics diverge wholesale from its disassembly will report mostly unmapped
sites, which is the honest answer.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .field_guide import next_steps
from .source_correlation import LISTING_FILE_RE, LISTING_LOC_RE, _quoted_path
from .terminal import Painter
from .view import SCHEDULE, MechanismView

__all__ = [
    "LOC_BOUNDARIES_SCHEMA",
    "MISSING_LISTING_STEPS",
    "PLAYBOOK",
    "ListingFunction",
    "ListingInstruction",
    "LocBoundaryReport",
    "SiteAnnotation",
    "annotate_schedule_sites",
    "listing_function_names",
    "parse_listing",
    "render_loc_boundaries",
    "report_guidance",
    "schedule_class_count",
    "select_function",
]

LOC_BOUNDARIES_SCHEMA = "decomp-workbench-loc-boundaries-v1"

#: The playbook a boundary-dominated site population routes to.
PLAYBOOK = "line-assignment-probe"

#: What a `schedule` verdict must say when no listing was supplied.
#:
#: A flag nobody knows about is a flag nobody uses, and this is precisely the
#: verdict whose documented next step is vacuous for a `-g0` project. The
#: footer therefore names the option *and* says where the file comes from.
MISSING_LISTING_STEPS: tuple[str, ...] = (
    "statement lines are not in evidence here: re-run with "
    "--candidate-listing LISTING.s to test whether the reordered instructions "
    "straddle a .loc statement boundary (field guide lever 23).",
    "that listing is the assembly ugen wrote for this candidate: keep it with "
    "`cc -K`, which leaves the driver's intermediates beside the object, or "
    "run `ugen -l` directly.",
)

_ENT_RE = re.compile(r"^\s*\.ent\s+(?P<name>[A-Za-z_.$][\w.$]*)")
_END_RE = re.compile(r"^\s*\.end\s+(?P<name>[A-Za-z_.$][\w.$]*)")
_LABEL_RE = re.compile(r"^\s*(?P<label>[A-Za-z_.$][\w.$]*)\s*:\s*(?P<rest>.*)$")

#: Directives that carry no instruction and no statement line.
#:
#: Listed by *shape* rather than by name: IDO emits `.livereg`, `.option`,
#: `.frame`, `.mask`, `.fmask`, `.align`, `.globl`, `.set`, `.bgnb`, `.endb`
#: and more, and a whitelist would silently start parsing the next one as an
#: instruction. Anything whose first token starts with `.` is a directive.
_DIRECTIVE_PREFIX = "."


@dataclass(frozen=True)
class ListingInstruction:
    """One listing instruction under the `.loc` record governing it."""

    index: int
    mnemonic: str
    text: str
    file: str | None
    file_index: int | None
    line: int | None
    listing_line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "mnemonic": self.mnemonic,
            "text": self.text,
            "file": self.file,
            "file_index": self.file_index,
            "line": self.line,
            "listing_line": self.listing_line,
        }


@dataclass(frozen=True)
class ListingFunction:
    """One `.ent name` ... `.end name` region of a ugen listing."""

    name: str
    instructions: tuple[ListingInstruction, ...]
    start_line: int
    end_line: int

    @property
    def lines(self) -> tuple[int | None, ...]:
        return tuple(item.line for item in self.instructions)


def _normalized(text: str) -> str:
    """Return one instruction as `mnemonic operands` with no stray whitespace.

    Both sides of the match are written by different programs for different
    readers -- ugen indents with tabs and spaces after commas, objdump does
    neither -- so the text is only an anchor once that difference is gone.
    """

    stripped = text.strip()
    if not stripped:
        return ""
    parts = stripped.split(maxsplit=1)
    mnemonic = parts[0].lower()
    if len(parts) == 1:
        return mnemonic
    operands = "".join(parts[1].split()).lower()
    return f"{mnemonic} {operands}"


def _mnemonic(text: str) -> str:
    stripped = text.strip()
    return stripped.split(maxsplit=1)[0].lower() if stripped else ""


def _strip_comment(line: str) -> str:
    """Drop a trailing assembler comment, keeping the instruction."""

    index = line.find("#")
    return line if index < 0 else line[:index]


def parse_listing(text: str) -> tuple[ListingFunction, ...]:
    """Return every `.ent`-delimited function of a ugen listing, in order.

    A listing that was hand-trimmed to one function and lost its `.ent` still
    parses: the instructions found outside any `.ent` become a single function
    with an empty name, which `select_function` accepts when no symbol was
    asked for. Refusing that input would only teach readers to paste more.
    """

    files: dict[int, str] = {}
    functions: list[ListingFunction] = []
    open_name: str | None = None
    open_line = 0
    collected: list[ListingInstruction] = []
    loose: list[ListingInstruction] = []
    file_index: int | None = None
    line_number: int | None = None
    last_line = 0

    def record(target: list[ListingInstruction], body: str, physical: int) -> None:
        target.append(
            ListingInstruction(
                index=len(target),
                mnemonic=_mnemonic(body),
                text=" ".join(body.split()),
                file=files.get(file_index) if file_index is not None else None,
                file_index=file_index,
                line=line_number,
                listing_line=physical,
            )
        )

    for physical, raw in enumerate(text.splitlines(), 1):
        last_line = physical
        stripped = _strip_comment(raw).strip()
        if not stripped:
            continue
        if stripped.startswith(_DIRECTIVE_PREFIX):
            location = LISTING_LOC_RE.match(stripped)
            if location is not None:
                file_index = int(location.group("file"))
                line_number = int(location.group("line"))
                continue
            file_directive = LISTING_FILE_RE.match(stripped)
            if file_directive is not None:
                number = file_directive.group("number")
                index = int(number) if number else max(files, default=0) + 1
                files[index] = _quoted_path(file_directive.group("file"))
                continue
            entry = _ENT_RE.match(stripped)
            if entry is not None:
                open_name, open_line, collected = entry.group("name"), physical, []
                continue
            exit_directive = _END_RE.match(stripped)
            if exit_directive is not None and open_name is not None:
                functions.append(
                    ListingFunction(
                        name=open_name,
                        instructions=tuple(collected),
                        start_line=open_line,
                        end_line=physical,
                    )
                )
                open_name, collected = None, []
                continue
            continue
        label = _LABEL_RE.match(stripped)
        if label is not None:
            stripped = label.group("rest").strip()
            if not stripped or stripped.startswith(_DIRECTIVE_PREFIX):
                continue
        record(collected if open_name is not None else loose, stripped, physical)

    if open_name is not None:
        # An unterminated `.ent` is a truncated listing, not a parse error: the
        # instructions before the truncation are still evidence.
        functions.append(
            ListingFunction(
                name=open_name,
                instructions=tuple(collected),
                start_line=open_line,
                end_line=last_line,
            )
        )
    if not functions and loose:
        functions.append(
            ListingFunction(
                name="",
                instructions=tuple(loose),
                start_line=1,
                end_line=last_line,
            )
        )
    return tuple(functions)


def listing_function_names(functions: Sequence[ListingFunction]) -> str:
    """Return the function names a listing offers, for an error message."""

    return ", ".join(item.name or "<unnamed>" for item in functions) or "none"


def select_function(
    functions: Sequence[ListingFunction], symbol: str | None
) -> ListingFunction:
    """Return the requested listing function, or say what the file holds."""

    if not functions:
        raise ValueError(
            "the listing holds no instructions; expected ugen assembly with "
            ".ent/.end and .loc records (cc -K keeps it, ugen -l writes it)"
        )
    if symbol is not None:
        for item in functions:
            if item.name == symbol:
                return item
        raise ValueError(
            f"function {symbol!r} is not in the listing; it holds: "
            f"{listing_function_names(functions)}"
        )
    if len(functions) > 1:
        raise ValueError(
            "the listing holds several functions and no --symbol was given; "
            f"it holds: {listing_function_names(functions)}"
        )
    return functions[0]


def map_to_listing(
    candidate: Sequence[str], function: ListingFunction
) -> tuple[int | None, ...]:
    """Return the listing index for each candidate instruction, or `None`.

    Two passes, strong anchors first: normalized text, then mnemonic inside the
    regions text could not pair. See this module's docstring for why nothing is
    paired by position alone.
    """

    listing = function.instructions
    left = [_normalized(item) for item in candidate]
    right = [_normalized(item.text) for item in listing]
    mapping: list[int | None] = [None] * len(candidate)
    blocks = difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes()
    for tag, left_start, left_end, right_start, right_end in blocks:
        if tag == "equal":
            for offset in range(left_end - left_start):
                mapping[left_start + offset] = right_start + offset
            continue
        if tag in {"delete", "insert"}:
            continue
        inner = difflib.SequenceMatcher(
            a=[_mnemonic(item) for item in candidate[left_start:left_end]],
            b=[item.mnemonic for item in listing[right_start:right_end]],
            autojunk=False,
        ).get_opcodes()
        for inner_tag, a_start, a_end, b_start, _ in inner:
            if inner_tag != "equal":
                continue
            for offset in range(a_end - a_start):
                mapping[left_start + a_start + offset] = right_start + b_start + offset
    return tuple(mapping)


@dataclass(frozen=True)
class SiteAnnotation:
    """One schedule-divergent site, with the statement lines it spans."""

    site: int
    hunk: int
    rows: tuple[int, int]
    candidate_range: tuple[int, int]
    window: tuple[int, int]
    widened: bool
    lines: tuple[int | None, ...]
    mapped: int
    unmapped: int
    status: str

    @property
    def boundary(self) -> bool:
        return self.status == "boundary"

    @property
    def decidable(self) -> bool:
        return self.status in {"boundary", "same-line"}

    @property
    def distinct_lines(self) -> tuple[int, ...]:
        return tuple(sorted({item for item in self.lines if item is not None}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "hunk": self.hunk,
            "rows": list(self.rows),
            "candidate": list(self.candidate_range),
            "window": list(self.window),
            "widened": self.widened,
            "lines": list(self.lines),
            "distinct_lines": list(self.distinct_lines),
            "mapped": self.mapped,
            "unmapped": self.unmapped,
            "status": self.status,
            "boundary": self.boundary,
        }


@dataclass(frozen=True)
class LocBoundaryReport:
    """What the candidate's listing says about its schedule-divergent sites."""

    listing: str
    function: str
    listing_instructions: int
    candidate_instructions: int
    mapped_instructions: int
    sites: tuple[SiteAnnotation, ...]
    target_only_hunks: tuple[int, ...]
    schedule_rows: int

    @property
    def boundary_sites(self) -> int:
        return sum(1 for site in self.sites if site.boundary)

    @property
    def decidable_sites(self) -> int:
        return sum(1 for site in self.sites if site.decidable)

    @property
    def unmapped_sites(self) -> int:
        return len(self.sites) - self.decidable_sites

    @property
    def majority(self) -> bool:
        """Whether most *decidable* sites sit at a statement-line boundary.

        Decidable, not total: a site the listing could not attribute is not
        evidence for the mechanism and must not be counted against it either.
        `unmapped_sites` is printed beside this number so the denominator is
        never silent.
        """

        return self.decidable_sites > 0 and self.boundary_sites * 2 > (
            self.decidable_sites
        )

    @property
    def summary_line(self) -> str:
        if not self.schedule_rows:
            return (
                "no aligned row is schedule-class here, so there is no "
                "reordering for a statement line to explain"
            )
        if not self.sites:
            return (
                "no schedule-divergent site carries a candidate instruction; "
                "there is nothing for a listing to attribute to a statement"
            )
        return (
            f"{self.boundary_sites} of {len(self.sites)} schedule-divergent "
            "sites sit at statement-line boundaries (.loc changes between "
            "reordered instructions)"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": LOC_BOUNDARIES_SCHEMA,
            "listing": self.listing,
            "function": self.function,
            "listing_instructions": self.listing_instructions,
            "candidate_instructions": self.candidate_instructions,
            "mapped_instructions": self.mapped_instructions,
            "schedule_rows": self.schedule_rows,
            "sites": [site.as_dict() for site in self.sites],
            "boundary_sites": self.boundary_sites,
            "decidable_sites": self.decidable_sites,
            "unmapped_sites": self.unmapped_sites,
            "target_only_hunks": list(self.target_only_hunks),
            "majority": self.majority,
            "playbook": PLAYBOOK if self.majority else None,
            "summary": self.summary_line,
        }


def schedule_class_count(view: MechanismView) -> int:
    """Return how many aligned rows the view classified as `schedule`."""

    return view.counts.get(SCHEDULE, 0)


def _candidate_assembly(view: MechanismView) -> list[str]:
    stream = [""] * view.candidate_instructions
    for row in view.rows:
        if row.candidate_index is not None and row.candidate is not None:
            if 0 <= row.candidate_index < len(stream):
                stream[row.candidate_index] = row.candidate
    return stream


def _schedule_hunks(view: MechanismView) -> list[tuple[int, tuple[int, int]]]:
    """Return `(hunk number, row range)` for every hunk holding a schedule row."""

    found: list[tuple[int, tuple[int, int]]] = []
    for hunk in view.hunks:
        rows = view.rows[hunk.start : hunk.end + 1]
        if any(row.classification == SCHEDULE for row in rows):
            found.append((hunk.hunk, (hunk.start, hunk.end)))
    return found


def annotate_schedule_sites(
    view: MechanismView,
    listing_text: str,
    *,
    listing_name: str,
    symbol: str | None = None,
) -> LocBoundaryReport:
    """Annotate the view's schedule-divergent sites with their `.loc` lines."""

    functions = parse_listing(listing_text)
    function = select_function(functions, symbol or view.symbol)
    candidate = _candidate_assembly(view)
    mapping = map_to_listing(candidate, function)

    sites: list[SiteAnnotation] = []
    target_only: list[int] = []
    for number, (start, end) in _schedule_hunks(view):
        indexes = [
            row.candidate_index
            for row in view.rows[start : end + 1]
            if row.candidate_index is not None
        ]
        if not indexes:
            target_only.append(number)
            continue
        low, high = min(indexes), max(indexes)
        widened = high - low < 1
        window_low = max(0, low - 1) if widened else low
        window_high = min(len(candidate) - 1, high + 1) if widened else high
        lines: list[int | None] = []
        for index in range(window_low, window_high + 1):
            listing_index = mapping[index]
            lines.append(
                None
                if listing_index is None
                else function.instructions[listing_index].line
            )
        mapped = sum(1 for item in lines if item is not None)
        unmapped = len(lines) - mapped
        distinct = {item for item in lines if item is not None}
        if len(distinct) > 1:
            status = "boundary"
        elif mapped == 0:
            status = "unmapped"
        elif unmapped:
            status = "undetermined"
        else:
            status = "same-line"
        sites.append(
            SiteAnnotation(
                site=len(sites) + 1,
                hunk=number,
                rows=(start, end),
                candidate_range=(low, high),
                window=(window_low, window_high),
                widened=widened,
                lines=tuple(lines),
                mapped=mapped,
                unmapped=unmapped,
                status=status,
            )
        )
    return LocBoundaryReport(
        listing=listing_name,
        function=function.name,
        listing_instructions=len(function.instructions),
        candidate_instructions=len(candidate),
        mapped_instructions=sum(1 for item in mapping if item is not None),
        sites=tuple(sites),
        target_only_hunks=tuple(target_only),
        schedule_rows=schedule_class_count(view),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _line_cell(value: int | None) -> str:
    return "?" if value is None else str(value)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def render_loc_boundaries(
    report: LocBoundaryReport, painter: Painter | None = None
) -> list[str]:
    """Render the statement-line section, in the vocabulary of the JSON keys."""

    brush = painter or Painter(False)
    lines = [
        "",
        brush.bold("STATEMENT LINES")
        + "  "
        + " ".join(
            f"{key}={value}"
            for key, value in (
                ("listing", report.listing),
                ("function", report.function or "<unnamed>"),
                ("listing_instructions", report.listing_instructions),
                ("candidate_instructions", report.candidate_instructions),
                ("mapped_instructions", report.mapped_instructions),
            )
        ),
    ]
    if not report.sites and not report.target_only_hunks:
        lines.append(f"  {report.summary_line}")
        return lines
    for site in report.sites:
        detail = (
            ("site", site.site),
            ("hunk", site.hunk),
            ("candidate", f"{site.candidate_range[0]}..{site.candidate_range[1]}"),
            ("window", f"{site.window[0]}..{site.window[1]}"),
            ("widened", "yes" if site.widened else "no"),
            ("unmapped", site.unmapped),
            ("lines", ",".join(_line_cell(item) for item in site.lines)),
            ("status", site.status),
        )
        lines.append("  " + " ".join(f"{key}={value}" for key, value in detail))
    # The two legends print once each, and only when they apply: repeating them
    # on every row buried the numbers they exist to explain.
    if any(site.widened for site in report.sites):
        lines.append(
            "  widened=yes: the hunk covers one candidate instruction, so the "
            "window takes one instruction on each side - what it was reordered "
            "past."
        )
    if any(site.unmapped for site in report.sites):
        lines.append(
            "  ?: that instruction is not in the listing (a macro as1 expanded, "
            "a delay slot as1 filled). It is never guessed at by position."
        )
    if report.target_only_hunks:
        named = ", ".join(str(number) for number in report.target_only_hunks)
        lines.append(
            f"  {_plural(len(report.target_only_hunks), 'hunk')} hold no "
            f"candidate instruction ({named}): the candidate's listing cannot "
            "say which statement the target's instruction came from. Not "
            "counted as sites."
        )
    if report.unmapped_sites:
        lines.append(
            f"  {_plural(report.unmapped_sites, 'site')} could not be "
            "attributed to a statement and are excluded from the majority."
        )
    lines.append(f"  {report.summary_line}")
    return lines


def report_guidance(report: LocBoundaryReport) -> tuple[str, ...]:
    """Return the footer lines this report adds to the aligned view's `next:`."""

    if not report.sites:
        return (report.summary_line,)
    lead_in = [report.summary_line]
    if report.unmapped_sites:
        lead_in.append(
            f"{_plural(report.unmapped_sites, 'site')} could not be attributed "
            "to a statement; the majority below is over the sites that could."
        )
    if not report.decidable_sites:
        # Silence here would read as a negative result, and a negative result
        # is a decision the reader would act on. This is no result at all.
        lead_in.append(
            "no site could be attributed to a statement line at all: check "
            "that this listing is the one that produced this candidate. Until "
            "it is, nothing above rules the mechanism in or out."
        )
        return tuple(lead_in)
    if not report.majority:
        lead_in.append(
            "the reordered instructions mostly share one .loc line, so "
            "preprocessor line assignment does not own this residual; stay on "
            "playbook=g0-schedule-probe."
        )
        return tuple(lead_in)
    lead_in.append(
        "the reordered instructions carry different statement lines: uopt and "
        "ugen honor statement line boundaries even at -g0, so this is a "
        "preprocessor line-assignment residual, not a compiler-version one."
    )
    return next_steps(PLAYBOOK, lead_in=lead_in)
