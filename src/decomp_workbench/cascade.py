"""Every round of one allocator site's decision cascade, from a CDX log.

Five hand-rolled versions of "dump the decision trail for one web" existed in
a single campaign, and three of them were wrong in ways that changed what a
stage believed:

* **Only the last round was printed.** One site's residue was the tail of a
  four-round `f_split` cascade whose *parent* had already declined on cost.
  Five stages reasoned about the child in isolation, and one stage's brief was
  written on the premise that the fused range did not exist. A cascade is
  every round or it is misleading; :class:`Cascade` has no other mode.
* **The web was located by a hard-coded symbol number.** `sym=1042` became
  `sym=1039` on a rebase, and the script that grepped for the old number
  printed `WEB-ABSENT` -- which reads exactly like the kill the stage was
  hoping for. Seven stages re-reported this one bug. Sites here are located
  by **frame offset**, which a renumbering does not move, and an offset that
  matches nothing is an error that says so rather than a silent absence.
* **The colour printed was the pre-resolution one.** `bestcolor` on `p1dec`
  is the allocator's natural choice *before* a force or a split resolves the
  web. On a forced run it shows the unforced colour; on a split web it shows
  the parent's. The post-resolution record is `p1color`, and it is joined here
  by web number -- not by position, which mis-attributes as soon as the log
  interleaves two webs' colourings.

The arithmetic these records carry is specified once, in
``docs/p1-decision-arithmetic.md``. This module reports it; that page explains
it.

Dependency, stated plainly: `savedetail` and `saveocc` are **not** part of the
instrumentation profile the workbench ships (`instrument-uopt`). They come
from a campaign-local `uopt.c` patch. Everything here reads a log file, so it
works against any build that emits the grammar in :data:`RECORD_GRAMMAR`, and
the commands say which records a log was missing rather than printing an empty
table. See ``docs/cdx-cascade.md``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from .globalcolor import (
    ColorDecision,
    GlobalColorTrace,
    decode_forbidden_colors,
    decode_mincost_tie_colors,
    is_ineligible_allocator_cost,
    optional_integer,
    parse_globalcolor_trace,
    register_for_color,
)

__all__ = [
    "RECORD_GRAMMAR",
    "Cascade",
    "CascadeError",
    "CdxLog",
    "Occurrence",
    "Round",
    "SaveDetail",
    "Site",
    "block_report",
    "color_order_report",
    "format_frame_offset",
    "parse_frame_offset",
    "rom_color_occupancy",
]


class CascadeError(ValueError):
    """A site could not be located, or a log did not carry what was asked."""


#: The record grammar these commands read, one line per kind. Every field name
#: below appears verbatim in a real trace; a reader with a differently-patched
#: instrument can check compatibility against this table without running
#: anything. Records the workbench's own `instrument-uopt` profile emits are
#: marked SHIPPED; the rest are campaign-local extensions (WB-15).
RECORD_GRAMMAR: dict[str, str] = {
    "p1dec": (
        "SHIPPED. One decision. phase proc web sym class save nocs totalsave "
        "bestcost bestcolor bestreg forbidden0/1 regsleft numintf "
        "available0/1 allcallersave taken1 taken2 decision forced. "
        "`class` here is the REGISTER class: 1 integer, 2 floating point."
    ),
    "p1color": (
        "SHIPPED. The colour the web actually received, after any force or "
        "split resolved it. phase proc web sym color reg forced."
    ),
    "p1cost": (
        "SHIPPED. One candidate colour's measured cost at one decision. "
        "phase proc web color reg kind cost best_before."
    ),
    "p1cand": (
        "SHIPPED. One entry of the priority sweep that orders the decisions. "
        "phase proc web sym save nocs best."
    ),
    "webdetail": (
        "SHIPPED. The web's identity. phase proc role web sym type dtype "
        "table chain exprtable exprchain bb line raw10 raw14 raw18 raw20. "
        "For a stack-resident web `raw10` is the FRAME OFFSET, which is the "
        "only identity in the whole grammar that survives renumbering."
    ),
    "savedetail": (
        "CAMPAIGN-LOCAL (WB-15). The save arithmetic for one web at one "
        "round. proc web sym occ gross chargeA chargeB net divisor nocs "
        "dtype save class forced. `class` here is NOT the register class: it "
        "is 1 while net > 0 and 2 once net <= 0, i.e. 2 means the piece is "
        "memory-resident."
    ),
    "saveocc": (
        "CAMPAIGN-LOCAL (WB-15). One occurrence inside that arithmetic. "
        "proc web occ usesdefs weight term bb uses defs occp nl bb5 o22 o23 "
        "w34."
    ),
}

#: Records without which a cascade cannot be built at all.
REQUIRED_RECORDS = ("p1dec", "webdetail")

_RANGE_RE = re.compile(r"^\s*(-?\w+)\s*\.\.\s*(-?\w+)\s*$")
_REGISTER_RE = re.compile(r"\$(?:f\d+|\w+)")


def parse_frame_offset(value: str) -> int:
    """Return one signed frame offset from any spelling a trace or reader uses.

    A trace prints `raw10=0xfffffdf8`; a person says `-520`; a person holding
    the frame size says "slot 1184 of a -1704 frame". All three name the same
    site, and refusing two of them would send the reader back to a calculator
    -- which is where the hard-coded symbol numbers came from.
    """

    text = value.strip().lower()
    try:
        number = int(text, 0)
    except ValueError:
        raise CascadeError(
            f"{value!r} is not a frame offset; write it as the trace prints it "
            "(0xfffffdf8), as a signed number (-520), or give --slot with "
            "--frame"
        ) from None
    if 0x80000000 <= number <= 0xFFFFFFFF:
        number -= 0x100000000
    return number


def format_frame_offset(offset: int) -> str:
    """Render an offset the way the trace does, with the signed value beside it."""

    word = offset & 0xFFFFFFFF
    return f"0x{word:08x} ({offset:+d})"


def _float(value: str | None) -> float:
    if value is None:
        return math.nan
    try:
        return float(value)
    except ValueError:
        return math.nan


def _number(value: float) -> float | str:
    return value if math.isfinite(value) else "nan"


def parse_row_range(value: str) -> tuple[int, int]:
    """Parse one inclusive ``LO..HI`` row range."""

    match = _RANGE_RE.match(value)
    if match is None:
        raise CascadeError(f"{value!r} is not a row range; write it as LO..HI")
    try:
        low, high = int(match.group(1), 0), int(match.group(2), 0)
    except ValueError:
        raise CascadeError(
            f"{value!r} is not a row range; write it as LO..HI"
        ) from None
    if low > high:
        raise CascadeError(f"row range {value!r} runs backwards; write it as LO..HI")
    return low, high


@dataclass(frozen=True)
class Occurrence:
    """One `saveocc` record: a single occurrence inside a web's save sum."""

    web: int
    index: int
    block: int
    uses: int
    defs: int
    weight: float
    term: float
    nl: int
    o22: int
    o23: int
    w34: int

    @property
    def charges_b(self) -> bool:
        """Whether this occurrence satisfies the `chargeB` gate (L92).

        ``w34 AND NOT o23 AND o22 AND (defs != 0 OR nl == 0)`` -- a definition
        whose value does not provably reach every successor block. Three
        campaign stages theorised `chargeB` as a loop term and planned sweeps
        around loops; it is a store-placement term, and a straight-line
        definition fires it just as legitimately, at weight 1 instead of 10.
        """

        return bool(
            self.w34 and not self.o23 and self.o22 and (self.defs or not self.nl)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "web": self.web,
            "occurrence": self.index,
            "block": self.block,
            "uses": self.uses,
            "defs": self.defs,
            "weight": _number(self.weight),
            "term": _number(self.term),
            "nl": self.nl,
            "o22": self.o22,
            "o23": self.o23,
            "w34": self.w34,
            "charges_b": self.charges_b,
        }


@dataclass(frozen=True)
class SaveDetail:
    """One `savedetail` record: the save arithmetic for a web at one round."""

    web: int
    symbol: int
    occurrence_count: int
    gross: float
    charge_a: float
    charge_b: float
    net: float
    nocs: int
    dtype: int | None
    save: float
    piece_class: int | None
    occurrences: tuple[Occurrence, ...] = ()

    @property
    def memory_resident(self) -> bool:
        """Whether this piece was already priced out of a colour (`class=2`).

        `savedetail`'s `class` is not `p1dec`'s: this one is 1 while
        ``net > 0`` and 2 once ``net <= 0`` (487/487 and 407/407 on the
        campaign's own logs), so 2 means "this piece will not be coloured".
        `p1dec`'s `class` is the register file: 1 integer, 2 floating point.
        One reader who carries both meanings under one name will eventually
        report a float web as memory-resident.
        """

        return self.piece_class == 2

    @property
    def charge_b_contributors(self) -> tuple[Occurrence, ...]:
        """The occurrences that satisfy the `chargeB` gate (L92)."""

        return tuple(item for item in self.occurrences if item.charges_b)

    @property
    def charge_b_accounted(self) -> bool:
        """Whether the gate's weights reproduce the recorded `chargeB`.

        A check, not an assumption: on the campaign this grammar comes from
        it holds on every record where the occurrence list is complete. When
        it does not hold, the reader is told rather than shown a derived
        attribution that the pass does not agree with.
        """

        if not self.occurrences or not math.isfinite(self.charge_b):
            return False
        total = sum(item.weight for item in self.charge_b_contributors)
        return abs(total - self.charge_b) <= 1e-6

    def as_dict(self) -> dict[str, Any]:
        return {
            "web": self.web,
            "symbol": self.symbol,
            "occurrence_count": self.occurrence_count,
            "gross": _number(self.gross),
            "charge_a": _number(self.charge_a),
            "charge_b": _number(self.charge_b),
            "net": _number(self.net),
            "nocs": self.nocs,
            "dtype": self.dtype,
            "save": _number(self.save),
            "piece_class": self.piece_class,
            "memory_resident": self.memory_resident,
            "charge_b_accounted": self.charge_b_accounted,
            "occurrences": [item.as_dict() for item in self.occurrences],
        }


@dataclass(frozen=True)
class Round:
    """One `p1dec` decision with everything the log says about it."""

    ordinal: int
    index: int
    web: int
    symbol: int
    register_class: int | None
    save: float
    nocs: int
    net: float
    best_cost: float
    natural_color: int | None
    resolved_color: int | None
    decision: str
    forced: int | None
    forbidden: tuple[int, ...]
    mincost_tie: tuple[int, ...]
    registers_left: int | None
    interference: int | None
    entering: SaveDetail | None
    pieces: tuple[SaveDetail, ...]

    @property
    def natural_register(self) -> str | None:
        return register_for_color(self.natural_color)

    @property
    def resolved_register(self) -> str | None:
        return register_for_color(self.resolved_color)

    @property
    def declined(self) -> bool:
        return self.decision != "color"

    @property
    def resolution_differs(self) -> bool:
        """Whether the colour actually taken is not the natural best colour."""

        return (
            self.resolved_color is not None
            and self.natural_color is not None
            and self.resolved_color != self.natural_color
        )

    @property
    def inequality(self) -> str:
        """The decision as the one inequality it is (L28).

        `totalsave` and `net` are the same number under two names, and a
        printer that lists five loose fields makes the reader recombine them.
        """

        if not math.isfinite(self.net) or not math.isfinite(self.best_cost):
            return f"net ? <= bestcost ? -> {self.decision}"
        answer = "YES" if self.net <= self.best_cost else "NO"
        outcome = (
            "split (memory-resident, no colour)" if answer == "YES" else "colour it"
        )
        return (
            f"net {self.net:.3f} <= bestcost {self.best_cost:.3f} ?  "
            f"{answer} -> {outcome}"
        )

    @property
    def deficit(self) -> float:
        """How far `net` still has to fall for this web to be declined."""

        if not math.isfinite(self.net) or not math.isfinite(self.best_cost):
            return math.nan
        return self.net - self.best_cost

    def color_name(self, color: int | None) -> str:
        if color is None or color < 0:
            return "-"
        register = register_for_color(color)
        return f"c{color}/{register}" if register else f"c{color}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "round": self.index,
            "web": self.web,
            "symbol": self.symbol,
            "register_class": self.register_class,
            "save": _number(self.save),
            "nocs": self.nocs,
            "net": _number(self.net),
            "best_cost": _number(self.best_cost),
            "decision": self.decision,
            "inequality": self.inequality,
            "deficit": _number(self.deficit),
            "natural_color": self.natural_color,
            "natural_register": self.natural_register,
            "resolved_color": self.resolved_color,
            "resolved_register": self.resolved_register,
            "resolution_differs": self.resolution_differs,
            "forced": self.forced,
            "forbidden_colors": list(self.forbidden),
            "forbidden_registers": [
                {"color": color, "register": register_for_color(color)}
                for color in self.forbidden
            ],
            "mincost_tie_colors": list(self.mincost_tie),
            "registers_left": self.registers_left,
            "interference": self.interference,
            "entering": None if self.entering is None else self.entering.as_dict(),
            "pieces": [item.as_dict() for item in self.pieces],
        }


@dataclass(frozen=True)
class Site:
    """One allocator site: a frame offset, its symbol, and its web family."""

    key: str
    symbol: int | None
    frame_offset: int | None
    webs: tuple[int, ...]
    detail: dict[str, str]
    caution: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "symbol": self.symbol,
            "frame_offset": self.frame_offset,
            "frame_offset_text": (
                None
                if self.frame_offset is None
                else format_frame_offset(self.frame_offset)
            ),
            "webs": list(self.webs),
            "caution": self.caution,
        }


@dataclass(frozen=True)
class Cascade:
    """Every round of one site's decision cascade, in log order."""

    name: str
    site: Site
    rounds: tuple[Round, ...]
    occurrences: dict[int, tuple[Occurrence, ...]]
    costs: dict[int, tuple[dict[str, str], ...]]
    undecided: tuple[SaveDetail, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def killed(self) -> bool:
        """Whether no web of this site ever received a colour.

        The decisive bit at a contested site, and the one every stage
        re-derived by hand from a `grep -c`.
        """

        return not any(item.resolved_color is not None for item in self.rounds)

    @property
    def final(self) -> Round | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def colored(self) -> tuple[Round, ...]:
        return tuple(item for item in self.rounds if item.resolved_color is not None)

    def kill_line(self) -> str:
        """The one-line kill signal a sweep column carries."""

        symbol = "-" if self.site.symbol is None else str(self.site.symbol)
        if self.killed:
            return (
                f"kill: YES {self.name} sym={symbol} rounds={len(self.rounds)} colors=0"
            )
        taken = self.colored
        last = taken[-1]
        return (
            f"kill: NO {self.name} sym={symbol} rounds={len(self.rounds)} "
            f"colors={len(taken)} final=w{last.web}:"
            f"{last.color_name(last.resolved_color)}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "log": self.name,
            "site": self.site.as_dict(),
            "killed": self.killed,
            "kill_line": self.kill_line(),
            "round_count": len(self.rounds),
            "rounds": [item.as_dict() for item in self.rounds],
            "undecided_pieces": [item.as_dict() for item in self.undecided],
            "warnings": list(self.warnings),
            "occurrences": {
                str(web): [item.as_dict() for item in items]
                for web, items in sorted(self.occurrences.items())
            },
        }


def _fields(record: ColorDecision) -> dict[str, str]:
    return record.fields


class CdxLog:
    """One parsed CDX log, indexed the way a site query needs it."""

    def __init__(self, text: str, *, name: str) -> None:
        self.name = name
        self.trace: GlobalColorTrace = parse_globalcolor_trace(text)
        self.records: list[ColorDecision] = list(self.trace.decisions)
        self.kinds: dict[str, int] = {}
        for record in self.records:
            self.kinds[record.phase] = self.kinds.get(record.phase, 0) + 1

    @classmethod
    def read(cls, path: str) -> CdxLog:
        from pathlib import Path

        location = Path(path)
        try:
            text = location.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise CascadeError(f"cannot read {path}: {error}") from None
        if "[CDX]" not in text:
            raise CascadeError(
                f"{path} holds no [CDX] records. A cascade needs an "
                "instrumented build: compile with CDX_LOG=1 and keep the "
                "compiler's stderr. `decomp-workbench trace-cascade "
                "--grammar` prints the records this reads."
            )
        return cls(text, name=location.name)

    def of(self, kind: str) -> Iterator[ColorDecision]:
        for record in self.records:
            if record.phase == kind:
                yield record

    def missing(self, kinds: Iterable[str]) -> list[str]:
        return [kind for kind in kinds if not self.kinds.get(kind)]

    def require(self, kinds: Iterable[str], *, purpose: str) -> None:
        absent = self.missing(kinds)
        if not absent:
            return
        raise CascadeError(
            f"{self.name} carries no {'/'.join(absent)} record(s), which "
            f"{purpose} needs. Present: "
            f"{', '.join(sorted(self.kinds)) or 'nothing'}. The "
            f"{'/'.join(absent)} grammar is a campaign-local uopt patch, not "
            "part of the shipped `instrument-uopt` profile -- see "
            "`trace-cascade --grammar`."
        )

    # -- site location -------------------------------------------------

    def frame_offsets(self) -> dict[int, set[int]]:
        """Return every frame offset a `webdetail` names, to its symbols."""

        found: dict[int, set[int]] = {}
        for record in self.of("webdetail"):
            raw = record.fields.get("raw10")
            symbol = optional_integer(record.fields.get("sym"))
            if raw is None or symbol is None:
                continue
            try:
                offset = parse_frame_offset(raw)
            except CascadeError:
                continue
            found.setdefault(offset, set()).add(symbol)
        return found

    def webs_of_symbol(self, symbol: int) -> tuple[int, ...]:
        """Return every web the log attributes to one symbol, in first-seen order."""

        seen: dict[int, None] = {}
        for record in self.records:
            if optional_integer(record.fields.get("sym")) != symbol:
                continue
            web = optional_integer(record.fields.get("web"))
            if web is not None:
                seen.setdefault(web, None)
        return tuple(seen)

    def symbol_of_web(self, web: int) -> int | None:
        for record in self.records:
            if optional_integer(record.fields.get("web")) == web:
                symbol = optional_integer(record.fields.get("sym"))
                if symbol is not None:
                    return symbol
        return None

    def web_detail(self, web: int) -> dict[str, str]:
        for record in self.of("webdetail"):
            if optional_integer(record.fields.get("web")) == web:
                return dict(record.fields)
        return {}

    def resolve(
        self,
        *,
        frame_offset: int | None = None,
        symbol: int | None = None,
        web: int | None = None,
    ) -> Site:
        """Locate one site, by frame offset for preference."""

        given = [
            name
            for name, value in (
                ("--frame-offset/--slot", frame_offset),
                ("--symbol", symbol),
                ("--web", web),
            )
            if value is not None
        ]
        if len(given) != 1:
            raise CascadeError(
                "name exactly one site: --frame-offset (or --slot with "
                "--frame), --web, or --symbol"
                + (f"; got {', '.join(given)}" if given else "")
            )
        if frame_offset is not None:
            return self._resolve_offset(frame_offset)
        if web is not None:
            return self._resolve_web(web)
        assert symbol is not None
        return self._resolve_symbol(symbol, caution=_SYMBOL_CAUTION)

    def _resolve_offset(self, offset: int) -> Site:
        self.require(("webdetail",), purpose="locating a site by frame offset")
        table = self.frame_offsets()
        symbols = table.get(offset)
        if not symbols:
            raise CascadeError(_no_offset_message(self.name, offset, table))
        if len(symbols) > 1:
            listed = ", ".join(str(item) for item in sorted(symbols))
            raise CascadeError(
                f"frame offset {format_frame_offset(offset)} is claimed by "
                f"{len(symbols)} symbols in {self.name} ({listed}). Two "
                "symbols sharing one stack home is a real allocator outcome, "
                "not a lookup failure; pass --symbol to say which one you "
                "mean."
            )
        symbol = next(iter(symbols))
        site = self._resolve_symbol(symbol, caution=None)
        return Site(
            key=f"frame offset {format_frame_offset(offset)}",
            symbol=symbol,
            frame_offset=offset,
            webs=site.webs,
            detail=site.detail,
        )

    def _resolve_symbol(self, symbol: int, *, caution: str | None) -> Site:
        webs = self.webs_of_symbol(symbol)
        if not webs:
            raise CascadeError(
                f"no record in {self.name} names sym={symbol}. Symbol numbers "
                "are trace-local and renumber whenever the source is rebased "
                "-- one campaign's sym=1042 became sym=1039 and the script "
                "that grepped the old number reported a kill that had not "
                "happened. Locate the site by --frame-offset instead."
            )
        detail = self.web_detail(webs[0])
        offset = None
        raw = detail.get("raw10")
        if raw is not None:
            try:
                offset = parse_frame_offset(raw)
            except CascadeError:
                offset = None
        return Site(
            key=f"symbol {symbol}",
            symbol=symbol,
            frame_offset=offset,
            webs=webs,
            detail=detail,
            caution=caution,
        )

    def _resolve_web(self, web: int) -> Site:
        symbol = self.symbol_of_web(web)
        if symbol is None:
            raise CascadeError(
                f"no record in {self.name} names web={web}. Web numbers are "
                "trace-local: they change with any edit that changes the "
                "number of live ranges. Locate the site by --frame-offset."
            )
        site = self._resolve_symbol(symbol, caution=None)
        return Site(
            key=f"web {web}",
            symbol=symbol,
            frame_offset=site.frame_offset,
            webs=site.webs,
            detail=site.detail,
        )

    # -- cascade construction -------------------------------------------

    def cascade(self, site: Site) -> Cascade:
        """Build every round of one site's cascade, in log order."""

        self.require(REQUIRED_RECORDS, purpose="a cascade")
        family = set(site.webs)
        decisions: list[tuple[int, int, dict[str, str]]] = []
        saves: dict[int, list[tuple[int, SaveDetail]]] = {}
        colors: dict[int, list[int]] = {}
        costs: dict[int, list[dict[str, str]]] = {}
        occurrences: dict[int, list[Occurrence]] = {}
        pending_occurrences: dict[int, list[Occurrence]] = {}
        decision_ordinal = 0

        for position, record in enumerate(self.records):
            web = optional_integer(record.fields.get("web"))
            if record.phase in {"p1dec", "p2dec"}:
                decision_ordinal += 1
            if web is None or web not in family:
                continue
            if record.phase == "savedetail":
                detail = _save_detail(record.fields)
                if detail is not None:
                    # `saveocc` records precede the `savedetail` that sums
                    # them, so the buffer standing open for this web is
                    # exactly this round's occurrence list -- not the union
                    # over every round, which is what a per-web dictionary
                    # would give and which no arithmetic here would balance.
                    detail = SaveDetail(
                        **{
                            **detail.__dict__,
                            "occurrences": tuple(pending_occurrences.pop(web, ())),
                        }
                    )
                    saves.setdefault(web, []).append((position, detail))
                    occurrences.setdefault(web, []).extend(detail.occurrences)
            elif record.phase == "saveocc":
                item = _occurrence(record.fields)
                if item is not None:
                    pending_occurrences.setdefault(web, []).append(item)
            elif record.phase in {"p1cost", "p2cost"}:
                costs.setdefault(web, []).append(dict(record.fields))
            elif record.phase in {"p1dec", "p2dec"}:
                decisions.append((position, decision_ordinal, dict(record.fields)))
            elif record.phase in {"p1color", "p2color"}:
                color = optional_integer(record.fields.get("color"))
                if color is not None:
                    colors.setdefault(web, []).append(color)

        # A `savedetail` before a decision is the state that decision reads; a
        # `savedetail` after it, and before the same web's next decision, is a
        # piece `f_split` carved out. Pairing them positionally per web is
        # what keeps a four-round cascade from reading as one round with a
        # mystery recomputation attached.
        claimed: set[int] = set()
        rounds: list[Round] = []
        for index, (position, ordinal, fields) in enumerate(decisions, start=1):
            web = optional_integer(fields.get("web"))
            history = saves.get(web, []) if web is not None else []
            entering = None
            for save_position, detail in history:
                if save_position < position and save_position not in claimed:
                    entering = (save_position, detail)
            if entering is not None:
                claimed.add(entering[0])
            rounds.append(
                _round(
                    fields,
                    ordinal=ordinal,
                    index=index,
                    entering=None if entering is None else entering[1],
                )
            )
        # Second pass, now that every entering record is claimed: whatever
        # savedetail is left between this decision and the next one -- any
        # web's -- is a piece this split carved off and left memory-resident.
        # `f_split` gives one piece a fresh web number, so the window has to
        # be the whole family's, not this web's.
        ordered = sorted(
            (position, detail)
            for web_saves in saves.values()
            for position, detail in web_saves
        )
        bounded: list[Round] = []
        for index, (position, _ordinal, _fields) in enumerate(decisions):
            following = decisions[index + 1][0] if index + 1 < len(decisions) else None
            pieces = tuple(
                detail
                for save_position, detail in ordered
                if save_position > position
                and (following is None or save_position < following)
                and save_position not in claimed
            )
            claimed.update(
                save_position
                for save_position, _detail in ordered
                if save_position > position
                and (following is None or save_position < following)
            )
            bounded.append(Round(**{**rounds[index].__dict__, "pieces": pieces}))

        undecided = tuple(
            detail for position, detail in ordered if position not in claimed
        )
        return Cascade(
            name=self.name,
            site=site,
            rounds=tuple(_attach_colors(bounded, colors)),
            occurrences={
                web: tuple(items) for web, items in sorted(occurrences.items())
            },
            costs={web: tuple(items) for web, items in sorted(costs.items())},
            undecided=undecided,
            warnings=tuple(_net_warnings(bounded)),
        )


#: Printed whenever a site is located the way seven campaign stages found out
#: not to.
_SYMBOL_CAUTION = (
    "located by symbol number, which is trace-local: a rebase renumbers it "
    "and this lookup then silently names a different variable, or nothing. "
    "Use --frame-offset (or --slot with --frame) for anything you will "
    "compare across builds."
)


def _no_offset_message(name: str, offset: int, table: dict[int, set[int]]) -> str:
    """Say what an absent offset means, and what the nearby ones are.

    "No web at this offset" and "this web was killed" are different facts and
    one campaign's tooling printed them identically for four stages.
    """

    plausible = sorted(
        (item for item in table if -0x4000 < item < 0x4000),
        key=lambda item: (abs(item - offset), item),
    )
    nearest = ", ".join(format_frame_offset(item) for item in plausible[:5])
    return (
        f"no web in {name} sits at frame offset {format_frame_offset(offset)}. "
        "This is NOT a kill: a killed web still has a webdetail record. It "
        "means the offset is wrong, or the frame moved under you. "
        + (
            f"Nearest offsets present: {nearest}."
            if nearest
            else "No stack-resident webs are recorded at all."
        )
    )


def _save_detail(fields: dict[str, str]) -> SaveDetail | None:
    web = optional_integer(fields.get("web"))
    symbol = optional_integer(fields.get("sym"))
    if web is None:
        return None
    return SaveDetail(
        web=web,
        symbol=-1 if symbol is None else symbol,
        occurrence_count=optional_integer(fields.get("occ")) or 0,
        gross=_float(fields.get("gross")),
        charge_a=_float(fields.get("chargeA")),
        charge_b=_float(fields.get("chargeB")),
        net=_float(fields.get("net")),
        nocs=optional_integer(fields.get("nocs")) or 0,
        dtype=optional_integer(fields.get("dtype")),
        save=_float(fields.get("save")),
        piece_class=optional_integer(fields.get("class")),
    )


def _occurrence(fields: dict[str, str]) -> Occurrence | None:
    web = optional_integer(fields.get("web"))
    if web is None:
        return None
    return Occurrence(
        web=web,
        index=optional_integer(fields.get("occ")) or 0,
        block=optional_integer(fields.get("bb")) or 0,
        uses=optional_integer(fields.get("uses")) or 0,
        defs=optional_integer(fields.get("defs")) or 0,
        weight=_float(fields.get("weight")),
        term=_float(fields.get("term")),
        nl=optional_integer(fields.get("nl")) or 0,
        o22=optional_integer(fields.get("o22")) or 0,
        o23=optional_integer(fields.get("o23")) or 0,
        w34=optional_integer(fields.get("w34")) or 0,
    )


def _round(
    fields: dict[str, str],
    *,
    ordinal: int,
    index: int,
    entering: SaveDetail | None,
) -> Round:
    forbidden0 = optional_integer(fields.get("forbidden0"))
    forbidden1 = optional_integer(fields.get("forbidden1")) or 0
    available0 = optional_integer(fields.get("available0"))
    available1 = optional_integer(fields.get("available1")) or 0
    natural = optional_integer(fields.get("bestcolor"))
    web = optional_integer(fields.get("web"))
    symbol = optional_integer(fields.get("sym"))
    # `totalsave` and `net` are one number under two names (L28), verified
    # 1454/1454 on the campaign this grammar comes from. `totalsave` is on the
    # shipped record, so it is the one read; any disagreement with the
    # campaign-local `savedetail` is surfaced as a warning rather than
    # silently preferred one way.
    net = _float(fields.get("totalsave"))
    return Round(
        ordinal=ordinal,
        index=index,
        web=-1 if web is None else web,
        symbol=-1 if symbol is None else symbol,
        register_class=optional_integer(fields.get("class")),
        save=_float(fields.get("save")),
        nocs=optional_integer(fields.get("nocs")) or 0,
        net=net,
        best_cost=_float(fields.get("bestcost")),
        natural_color=None if natural is None or natural < 0 else natural,
        resolved_color=None,
        decision=fields.get("decision", "?"),
        forced=optional_integer(fields.get("forced")),
        forbidden=(
            ()
            if forbidden0 is None
            else tuple(decode_forbidden_colors(forbidden0, forbidden1))
        ),
        mincost_tie=(
            ()
            if available0 is None
            else tuple(decode_mincost_tie_colors(available0, available1))
        ),
        registers_left=optional_integer(fields.get("regsleft")),
        interference=optional_integer(fields.get("numintf")),
        entering=entering,
        pieces=(),
    )


def _net_warnings(rounds: Sequence[Round]) -> list[str]:
    """Report any round where `totalsave` and `savedetail net` disagree."""

    notes: list[str] = []
    for item in rounds:
        entering = item.entering
        if entering is None or not math.isfinite(entering.net):
            continue
        if not math.isfinite(item.net) or abs(item.net - entering.net) <= 1e-6:
            continue
        notes.append(
            f"round {item.index} (w{item.web}): p1dec totalsave "
            f"{item.net:.6f} but savedetail net {entering.net:.6f}. L28 says "
            "these are one number; a log where they differ is either a "
            "different instrument revision or a mis-paired record."
        )
    return notes


def _attach_colors(rounds: list[Round], colors: dict[int, list[int]]) -> list[Round]:
    """Join `p1color` to the rounds of its own web, in order.

    By web number and round order, never by position in the decision list: a
    positional join mis-attributes the moment two webs' colourings interleave,
    which is the defect that made one prototype's "final colour" the parent's.
    """

    pending = {web: list(items) for web, items in colors.items()}
    resolved: list[Round] = []
    for item in reversed(rounds):
        queue = pending.get(item.web)
        color = queue.pop() if queue else None
        resolved.append(Round(**{**item.__dict__, "resolved_color": color}))
    return list(reversed(resolved))


# -- reports over a whole log, not one site ----------------------------


def color_order_report(
    log: CdxLog,
    *,
    limit: int | None = None,
    register_class: int | None = None,
) -> dict[str, Any]:
    """Rank the p1 colouring order, with the same-save tie groups named.

    The single most useful fact about a stuck row is which webs are decided
    before it and by how much it would have to gain to overtake each. Ties are
    reported because p1 breaks them by ascending web number (L31), which turns
    a "must beat" threshold into a "must reach".
    """

    log.require(("p1dec",), purpose="a colour-order report")
    entries: list[dict[str, Any]] = []
    for position, record in enumerate(log.of("p1dec"), start=1):
        fields = record.fields
        item_class = optional_integer(fields.get("class"))
        if register_class is not None and item_class != register_class:
            continue
        color = optional_integer(fields.get("bestcolor"))
        entries.append(
            {
                "position": position,
                "web": optional_integer(fields.get("web")),
                "symbol": optional_integer(fields.get("sym")),
                "register_class": item_class,
                "save": _number(_float(fields.get("save"))),
                "nocs": optional_integer(fields.get("nocs")),
                "net": _number(_float(fields.get("totalsave"))),
                "best_cost": _number(_float(fields.get("bestcost"))),
                "color": color,
                "register": register_for_color(color),
                "interference": optional_integer(fields.get("numintf")),
                "registers_left": optional_integer(fields.get("regsleft")),
                "decision": fields.get("decision", "?"),
            }
        )
    shown = entries if limit is None else entries[:limit]
    groups: dict[float, list[dict[str, Any]]] = {}
    for item in shown:
        value = item["save"]
        if isinstance(value, float):
            groups.setdefault(round(value, 6), []).append(item)
    ties = [
        {
            "save": value,
            "members": [
                {"position": item["position"], "web": item["web"]} for item in members
            ],
        }
        for value, members in sorted(groups.items(), reverse=True)
        if len(members) > 1
    ]
    return {
        "log": log.name,
        "decision_count": len(entries),
        "shown": len(shown),
        "register_class": register_class,
        "order": shown,
        "tie_groups": ties,
    }


def block_report(
    log: CdxLog, *, webs: Sequence[int], blocks: Sequence[int]
) -> dict[str, Any]:
    """Report each web's occurrence-block set, and where the sets meet.

    "Which web interferes with which" was argued from `numintf` deltas across
    five stages of one campaign; the answer is a set intersection over
    `saveocc bb=` values.
    """

    log.require(("saveocc",), purpose="a block report")
    per_web: dict[int, set[int]] = {}
    detail: dict[int, list[Occurrence]] = {}
    for record in log.of("saveocc"):
        item = _occurrence(record.fields)
        if item is None:
            continue
        per_web.setdefault(item.web, set()).add(item.block)
        detail.setdefault(item.web, []).append(item)

    selected: list[int]
    wanted = set(blocks)
    if webs:
        missing = [web for web in webs if web not in per_web]
        if missing:
            raise CascadeError(
                f"{log.name} records no occurrences for web(s) "
                f"{', '.join(str(item) for item in missing)}; a web with no "
                "saveocc record never entered the save sum"
            )
        selected = list(webs)
    elif wanted:
        selected = sorted(web for web, items in per_web.items() if items & wanted)
    else:
        raise CascadeError("name the webs with --web, or the blocks with --block")

    intersection: list[int] = []
    if len(selected) > 1:
        common = set.intersection(*(per_web[web] for web in selected))
        intersection = sorted(common)
    return {
        "log": log.name,
        "webs": [
            {
                "web": web,
                "block_count": len(per_web[web]),
                "blocks": sorted(per_web[web]),
                "selected_blocks": sorted(per_web[web] & wanted) if wanted else [],
                "occurrences": [item.as_dict() for item in detail[web]],
            }
            for web in selected
        ],
        "queried_blocks": sorted(wanted),
        "intersection": intersection,
        "disjoint": len(selected) > 1 and not intersection,
    }


def rom_color_occupancy(
    instructions: Sequence[Any],
    *,
    colors: Sequence[int],
    rows: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Report which of these colours' registers the reference object uses.

    One campaign spent four stages driving `forbidden0` to `0xff` at a gate
    whose free colours the ROM's own disassembly never mentions -- meaning the
    ROM declined that web on cost, not colour, and the whole barrier hunt was
    aimed at a barrier that was not there.

    The reading is **occupancy**, not liveness: a register that appears
    nowhere in the range cannot be live in it, which is the direction the
    conclusion needs; a register that does appear may still be dead at any
    particular point, and this does not claim otherwise.
    """

    low, high = rows if rows is not None else (1, len(instructions))
    seen: set[str] = set()
    for index, item in enumerate(instructions, start=1):
        if not low <= index <= high:
            continue
        for token in _REGISTER_RE.findall(getattr(item, "assembly", "")):
            seen.add(token.lower())
    present: list[dict[str, Any]] = []
    absent: list[dict[str, Any]] = []
    for color in colors:
        register = register_for_color(color)
        if register is None:
            continue
        entry: dict[str, Any] = {"color": color, "register": register}
        (present if register.lower() in seen else absent).append(entry)
    return {
        "rows": [low, min(high, len(instructions))],
        "present": present,
        "absent": absent,
        "reading": (
            "occupancy over the named rows, not a liveness analysis: absence "
            "is proof the colour was free, presence is not proof it was taken"
        ),
    }


def cost_rows(costs: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Normalise `p1cost` records, flagging IDO's unavailable-cost sentinel."""

    rows: list[dict[str, Any]] = []
    for entry in costs:
        color = optional_integer(entry.get("color"))
        value = _float(entry.get("cost"))
        rows.append(
            {
                "color": color,
                "register": register_for_color(color),
                "kind": entry.get("kind"),
                "cost": _number(value),
                "eligible": math.isfinite(value)
                and not is_ineligible_allocator_cost(value),
            }
        )
    return rows
