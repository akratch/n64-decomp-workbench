"""Per-web allocator report: why each web of one procedure got its colour.

`trace cascade` follows one site through every round; `trace growth` reads one
split. Neither answers the question an analyst holding a forced oracle asks
first: *for this web, which references bought its priority, which register
bits did it start the decision already denied, and -- if it split -- which
block refused to join the piece?* A campaign answered that by hand for each
web, from five record kinds, and got the join wrong in the ways the cascade
module documents. This module is the one join.

Per decision of the selected procedure it reports:

1. **Identity.** The web's value as an expression over the procedure's own
   locals (``(col & 7)``, ``*(grid + 12)``), whether it is a symbol or an
   expression temporary, its priority (``save``), ``nocs``, ``totalsave``, the
   p1/p2 decision, the colour it was given, the order it was offered a colour
   in, and the ``forced`` state of both records.
2. **References.** One row per occurrence block, with uses, defs, loop weight
   and term. The decision record prints only the total; this breakdown says
   which reference to add or remove to move it. ``gross - chargeA - chargeB``
   is checked against ``net``, and ``net`` against the decision's
   ``totalsave``, so the breakdown is the decision's own arithmetic and not a
   reconstruction.
3. **Splits.** For a split web, every growth test of every piece, each verdict
   re-checked against the split growth rule (IDO 5.3 L161: accept iff
   ``new < left_before`` and ``2*left_after >= numintf + new``), with the first
   refused block named.
4. **The forbidden seed.** Per block of the web, the register mask folded into
   its forbidden set before any neighbour is coloured, and for each bit the
   precoloured value that put it there -- a web pinned in that block, or a
   value held over its range -- or, when no web owns it, a register bound
   outside any web. Bits in the decision's ``forbidden0`` beyond the seed are
   neighbours' colours.

Dependency, stated plainly: ``p1dec``/``p2dec``, ``p1color``/``p2color``,
``webblocks`` and the growth rows come from the shipped ``instrument-uopt``
globalcolor profile. The seven records in :data:`WEBREPORT_RECORDS` do **not**;
they come from a campaign-local ``uopt.c`` patch switched on by
``CDX_WEBREPORT=1``, whose disabled state must be byte-identical to the profile
without it. The grammar this module reads is :data:`RECORD_GRAMMAR`, so a
differently-patched instrument can be checked against it without running
anything, and a log that carries none of those records is refused by name
rather than printed as an empty report.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .globalcolor import (
    decode_forbidden_colors,
    optional_integer,
    parse_globalcolor_trace,
    register_for_color,
)
from .growth import RULE, rule_verdict
from .ucode import OPCODE_NAMES

__all__ = [
    "RECORD_GRAMMAR",
    "WEBREPORT_RECORDS",
    "WEB_REPORT_SCHEMA",
    "Decision",
    "Namer",
    "WebReport",
    "WebReportError",
    "build_web_report",
    "choose_procedure",
    "colour_name",
    "procedures_with_lines",
    "render_web_report",
]

WEB_REPORT_SCHEMA = "decomp-workbench-web-report-v1"

#: The campaign-local records this reader needs beyond the shipped profile.
WEBREPORT_RECORDS = (
    "bbline",
    "bbpin",
    "rangepin",
    "saveocc",
    "savedetail",
    "webexpr",
    "forbidseed",
)

#: One line per record kind this module reads. Fields beyond these are kept
#: but never interpreted. ``lr`` is the live-range pointer: an opaque,
#: invocation-local join key, never a portable identity.
RECORD_GRAMMAR: dict[str, str] = {
    "p1dec": "SHIPPED. One phase-1 decision. proc web save nocs totalsave "
    "bestcost forbidden0 regsleft numintf decision forced.",
    "p2dec": "SHIPPED. One phase-2 decision; same fields as p1dec.",
    "p1color": "SHIPPED. The colour a phase-1 decision resolved to. proc web "
    "color reg forced.",
    "p2color": "SHIPPED. Same, phase 2.",
    "webblocks": "SHIPPED. The blocks a web spans. proc web role lr bbs aux.",
    "seed": "SHIPPED. A split piece seeded at one block. proc lr bb.",
    "grow": "SHIPPED. One growth test. proc lr bb new left_before left_after "
    "numintf strict.",
    "growv": "SHIPPED. The verdict of the preceding grow row. proc lr bb accepted.",
    "bbline": "CAMPAIGN-LOCAL (CDX_WEBREPORT). One basic block. proc bb weight "
    "entry lines mask1 mask2: the loop weight, the source line in effect at "
    "entry, the comma list of lines the block's own statements carry (`-` for "
    "none) and the two pinned-register masks.",
    "bbpin": "CAMPAIGN-LOCAL. A web precoloured in one block. proc bb web color expr.",
    "rangepin": "CAMPAIGN-LOCAL. A value held in a register over a range that "
    "includes this block. proc bb mask0 expr.",
    "saveocc": "CAMPAIGN-LOCAL. One reference block inside a web's save "
    "arithmetic. proc lr bb weight uses defs term [nl o22 o23]. Precedes the "
    "savedetail that sums it.",
    "savedetail": "CAMPAIGN-LOCAL. A web's save arithmetic. proc lr gross "
    "chargeA chargeB net nocs save.",
    "webexpr": "CAMPAIGN-LOCAL. The value a decision's web holds. proc phase web "
    "lr kind expr [role]. Follows the decision it describes.",
    "forbidseed": "CAMPAIGN-LOCAL. The register mask one block folds into a "
    "web's forbidden set before any neighbour is coloured. proc lr bb own "
    "mask0.",
}

#: `webexpr` kind codes, as the campaign patch prints them.
KINDS: dict[int, str] = {
    1: "address",
    2: "constant",
    3: "symbol",
    4: "expression temporary",
    5: "address",
    6: "symbol",
    8: "constant",
}

#: Ucode operators rendered infix.
INFIX: dict[str, str] = {
    "add": "+",
    "sub": "-",
    "mpy": "*",
    "div": "/",
    "and": "&",
    "ior": "|",
    "xor": "^",
    "shl": "<<",
    "shr": ">>",
    "rem": "%",
    "mod": "%",
    "equ": "==",
    "neq": "!=",
    "les": "<",
    "leq": "<=",
    "grt": ">",
    "geq": ">=",
}

GPR_NAMES = (
    "zero",
    "at",
    "v0",
    "v1",
    "a0",
    "a1",
    "a2",
    "a3",
    "t0",
    "t1",
    "t2",
    "t3",
    "t4",
    "t5",
    "t6",
    "t7",
    "s0",
    "s1",
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "t8",
    "t9",
    "k0",
    "k1",
    "gp",
    "sp",
    "s8",
    "ra",
)


class WebReportError(ValueError):
    """A log could not answer the question asked of it."""


def colour_name(colour: int) -> str:
    """The register a colour names on the pinned profile, else ``c<N>``."""

    register = register_for_color(colour)
    return register.removeprefix("$") if register else f"c{colour}"


def _hex(value: str | None) -> int:
    if not value or value == "-":
        return 0
    return int(value.split(",")[0], 16)


def _float(value: str | None) -> float:
    try:
        return float(value) if value is not None else math.nan
    except ValueError:
        return math.nan


def _lines(value: str | None) -> list[int]:
    if not value or value == "-":
        return []
    return [int(item) for item in value.split(",") if item]


# ----------------------------------------------------------------- naming


class Namer:
    """Render a ``webexpr`` expression over the procedure's own names.

    Names are optional and come from the caller: frame offsets of locals, and
    of parameters, as the record prints them (cfe assigns frame offsets before
    optimisation, so these are the offsets a ``-g`` compile's symbol table
    gives). Without names a local prints as ``auto[-28]``.
    """

    def __init__(
        self,
        locals_by_offset: Mapping[int, Sequence[str]] | None = None,
        params_by_offset: Mapping[int, str] | None = None,
        opcode_names: Sequence[str] = OPCODE_NAMES,
    ) -> None:
        self.locals = {
            key: list(value) for key, value in (locals_by_offset or {}).items()
        }
        self.params = dict(params_by_offset or {})
        self.ops = tuple(opcode_names)

    def var(self, offset: int, storage: int) -> str:
        if storage == 1 and offset in self.locals:
            return "/".join(self.locals[offset])
        if storage == 2 and offset in self.params:
            return self.params[offset]
        if storage == 3 and 0 <= offset < len(GPR_NAMES):
            return f"${GPR_NAMES[offset]}"
        if storage == 3 and 32 <= offset < 64:
            return f"$f{offset - 32}"
        if storage == 1:
            return f"auto[{offset}]"
        if storage == 2:
            return f"param[{offset}]"
        return f"var[{offset}:{storage}]"

    def variables(self, expression: str) -> list[str]:
        """The named locals and parameters an expression reads."""

        names: list[str] = []
        for offset, storage in re.findall(r"var:(-?\d+):(\d+):\d+", expression):
            name = self.var(int(offset), int(storage))
            names.extend(item for item in name.split("/") if re.fullmatch(r"\w+", item))
        return sorted(set(names))

    def render(self, expression: str) -> str:
        """``op4(var:-28:1:4,const:7)`` -> ``(col & 7)``; unknown text verbatim."""

        renderer = _Renderer(expression, self)
        try:
            return renderer.parse()
        except (IndexError, ValueError):
            return expression


class _Renderer:
    def __init__(self, text: str, namer: Namer) -> None:
        self.text = text
        self.pos = 0
        self.namer = namer

    def _match(self, pattern: str) -> re.Match[str] | None:
        found = re.match(pattern, self.text[self.pos :])
        if found:
            self.pos += found.end()
        return found

    def parse(self) -> str:
        found = self._match(r"op(\d+)\(")
        if found:
            arguments = [self.parse()]
            while self.text[self.pos] == ",":
                self.pos += 1
                arguments.append(self.parse())
            if self.text[self.pos] != ")":
                raise ValueError("unbalanced expression")
            self.pos += 1
            code = int(found.group(1))
            ops = self.namer.ops
            name = ops[code] if code < len(ops) else f"op{code}"
            if name in INFIX and len(arguments) == 2:
                return f"({arguments[0]} {INFIX[name]} {arguments[1]})"
            if name == "ilod":
                offset = (
                    arguments[1][1:]
                    if len(arguments) > 1 and arguments[1].startswith("@")
                    else "0"
                )
                return (
                    f"*({arguments[0]} + {offset})"
                    if offset != "0"
                    else f"*{arguments[0]}"
                )
            if name == "cvt":
                return f"(cvt){arguments[0]}"
            if name == "ixa" and len(arguments) == 2:
                return f"{arguments[0]}[{arguments[1]}]"
            return f"{name}({', '.join(arguments)})"
        found = self._match(r"s?var:(-?\d+):(\d+):(\d+)")
        if found:
            return self.namer.var(int(found.group(1)), int(found.group(2)))
        found = self._match(r"@(-?\d+)")
        if found:
            return found.group(0)
        found = self._match(r"const:(-?\d+)")
        if found:
            return found.group(1)
        found = self._match(r"k[15]:0x([0-9a-fA-F]+)")
        if found:
            return f"&[0x{found.group(1)}]"
        found = self._match(r"[^,()]+")
        if found:
            return found.group(0)
        raise ValueError("empty expression term")


# ----------------------------------------------------------------- model


@dataclass
class Block:
    number: int
    weight: int
    entry: int
    lines: list[int]
    mask1: int
    mask2: int

    def span(self) -> str:
        lines = sorted(set(self.lines))
        if not lines:
            return f"(no line of its own; {self.entry} in effect)"
        if len(lines) > 2 and lines == list(range(lines[0], lines[-1] + 1)):
            return f"{lines[0]}-{lines[-1]}"
        return ",".join(map(str, lines))


@dataclass
class Decision:
    """One p1/p2 decision joined with every record that explains it."""

    index: int
    phase: str
    web: int
    fields: dict[str, str]
    order: int = 0
    expression: dict[str, str] = field(default_factory=dict)
    blocks: dict[str, str] = field(default_factory=dict)
    colour: dict[str, str] | None = None
    save: tuple[dict[str, str], list[dict[str, str]]] | None = None
    forbid: list[dict[str, str]] = field(default_factory=list)
    growth: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    @property
    def live_range(self) -> str | None:
        return self.expression.get("lr") or self.blocks.get("lr")

    @property
    def colour_number(self) -> int | None:
        return optional_integer(self.colour.get("color")) if self.colour else None


@dataclass
class WebReport:
    proc: int
    blocks: dict[int, Block]
    pins: dict[int, list[dict[str, str]]]
    rangepins: dict[int, list[dict[str, str]]]
    decisions: list[Decision]
    pieces: dict[str, Decision]
    missing_records: tuple[str, ...]


def _phase(kind: str) -> str:
    return kind[:2]


def procedures_with_lines(
    records: Sequence[tuple[str, dict[str, str]]],
) -> dict[int, set[int]]:
    """Every procedure that carries ``bbline`` source lines, with those lines."""

    found: dict[int, set[int]] = defaultdict(set)
    for kind, fields in records:
        proc = optional_integer(fields.get("proc"))
        if kind == "bbline" and proc is not None:
            found[proc].update(_lines(fields.get("lines")))
    return {proc: lines for proc, lines in found.items() if lines}


def choose_procedure(
    records: Sequence[tuple[str, dict[str, str]]], span: tuple[int, int] | None
) -> int | None:
    """The procedure whose first source line falls inside ``span``, or the only one."""

    found = procedures_with_lines(records)
    if span is not None:
        hits = [
            proc for proc, lines in found.items() if span[0] <= min(lines) <= span[1]
        ]
        if len(hits) == 1:
            return hits[0]
        return None
    if len(found) == 1:
        return next(iter(found))
    decided = {
        proc
        for kind, fields in records
        if kind in ("p1dec", "p2dec")
        if (proc := optional_integer(fields.get("proc"))) is not None
    }
    return next(iter(decided)) if len(decided) == 1 else None


def parse_records(text: str) -> list[tuple[str, dict[str, str]]]:
    """Every ``[CDX]`` record of a log, in order, as (kind, fields)."""

    trace = parse_globalcolor_trace(text)
    return [(item.phase, dict(item.fields)) for item in trace.decisions]


def build_web_report(
    records: Sequence[tuple[str, dict[str, str]]], proc: int
) -> WebReport:
    """Join one procedure's records into decisions with their evidence."""

    wanted = str(proc)
    blocks: dict[int, Block] = {}
    pins: dict[int, list[dict[str, str]]] = defaultdict(list)
    rangepins: dict[int, list[dict[str, str]]] = defaultdict(list)
    decisions: list[Decision] = []
    colours: dict[tuple[str, int], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    saves: dict[str, list[tuple[int, dict[str, str], list[dict[str, str]]]]] = (
        defaultdict(list)
    )
    forbid: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    growth: list[tuple[int, str, dict[str, str]]] = []
    pending: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[str] = set()
    for index, (kind, fields) in enumerate(records):
        if fields.get("proc") != wanted:
            continue
        seen.add(kind)
        if kind == "bbline":
            number = int(fields["bb"])
            blocks[number] = Block(
                number=number,
                weight=int(fields.get("weight", "0")),
                entry=int(fields.get("entry", "0")),
                lines=_lines(fields.get("lines")),
                mask1=_hex(fields.get("mask1")),
                mask2=_hex(fields.get("mask2")),
            )
        elif kind == "bbpin":
            pins[int(fields["bb"])].append(fields)
        elif kind == "rangepin":
            rangepins[int(fields["bb"])].append(fields)
        elif kind == "saveocc":
            pending[fields.get("lr", "?")].append(fields)
        elif kind == "savedetail":
            key = fields.get("lr", "?")
            saves[key].append((index, fields, pending.pop(key, [])))
        elif kind == "forbidseed":
            forbid[fields.get("lr", "?")].append((index, fields))
        elif kind in ("p1dec", "p2dec"):
            web = optional_integer(fields.get("web"))
            if web is not None:
                decisions.append(Decision(index, _phase(kind), web, fields))
        elif kind in ("webexpr", "webblocks") and decisions:
            last = decisions[-1]
            if (
                fields.get("web") == str(last.web)
                and fields.get("phase", last.phase) == last.phase
                and fields.get("role", "target") == "target"
            ):
                if kind == "webexpr":
                    last.expression = fields
                else:
                    last.blocks = fields
        elif kind in ("p1color", "p2color"):
            web = optional_integer(fields.get("web"))
            if web is not None:
                colours[(_phase(kind), web)].append((index, fields))
        elif kind in ("seed", "grow", "growv"):
            growth.append((index, kind, fields))
    for order, decision in enumerate(decisions, 1):
        decision.order = order
        following = decisions[order].index if order < len(decisions) else len(records)
        later = [
            row
            for position, row in colours.get((decision.phase, decision.web), [])
            if decision.index < position < following
        ]
        decision.colour = later[0] if later else None
        live_range = decision.live_range
        if live_range is None:
            continue
        for position, detail, occurrences in saves.get(live_range, []):
            if position < decision.index:
                decision.save = (detail, occurrences)
        previous = max(
            (
                other.index
                for other in decisions
                if other.live_range == live_range and other.index < decision.index
            ),
            default=-1,
        )
        decision.forbid = [
            row
            for position, row in forbid.get(live_range, [])
            if previous < position < decision.index
        ]
    splits = [item for item in decisions if item.fields.get("decision") == "split"]
    for position, kind, fields in growth:
        owner = None
        for decision in splits:
            if decision.index < position:
                owner = decision
        if owner is not None:
            owner.growth.append((kind, fields))
    pieces = {item.live_range: item for item in decisions if item.live_range}
    missing = tuple(kind for kind in WEBREPORT_RECORDS if kind not in seen)
    return WebReport(
        proc=proc,
        blocks=blocks,
        pins=dict(pins),
        rangepins=dict(rangepins),
        decisions=decisions,
        pieces={key: value for key, value in pieces.items() if key is not None},
        missing_records=missing,
    )


# ----------------------------------------------------------------- reading


def _seed_sources(report: WebReport, block: int, colour: int, namer: Namer) -> str:
    found: list[str] = []
    for pin in report.pins.get(block, []):
        if optional_integer(pin.get("color")) == colour:
            found.append(
                f"web {pin.get('web', '?')} {namer.render(pin.get('expr', '?'))}"
            )
    for pin in report.rangepins.get(block, []):
        if colour in decode_forbidden_colors(_hex(pin.get("mask0")), 0):
            found.append(f"{namer.render(pin.get('expr', '?'))} held over its range")
    return "; ".join(found) or "no web (a constant or address bound to the register)"


def _naming_lines(
    block: Block | None, names: list[str], source: Sequence[str]
) -> list[int]:
    if block is None or not names or not source:
        return []
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    return [
        number
        for number in sorted(set(block.lines))
        if 0 < number <= len(source) and pattern.search(source[number - 1])
    ]


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-3)


def describe_decision(
    report: WebReport,
    decision: Decision,
    namer: Namer,
    source: Sequence[str] = (),
    block_filter: int | None = None,
) -> dict[str, Any]:
    """One decision as a JSON-ready mapping: identity, references, seed, growth."""

    fields = decision.fields
    expression = decision.expression.get("expr", "")
    kind = optional_integer(decision.expression.get("kind"))
    colour = decision.colour_number
    result: dict[str, Any] = {
        "web": decision.web,
        "phase": decision.phase,
        "order": decision.order,
        "live_range": decision.live_range,
        "expression": expression or None,
        "rendered": namer.render(expression) if expression else None,
        "kind": KINDS.get(kind, "unknown") if kind is not None else None,
        "save": _float(fields.get("save")),
        "nocs": optional_integer(fields.get("nocs")),
        "totalsave": _float(fields.get("totalsave")),
        "bestcost": _float(fields.get("bestcost")),
        "numintf": optional_integer(fields.get("numintf")),
        "regsleft": optional_integer(fields.get("regsleft")),
        "decision": fields.get("decision"),
        "colour": colour,
        "register": colour_name(colour) if colour is not None else None,
        "forced_decision": optional_integer(fields.get("forced")),
        "forced_colour": (
            optional_integer(decision.colour.get("forced")) if decision.colour else None
        ),
    }
    if decision.save is None:
        result["references"] = None
    else:
        detail, occurrences = decision.save
        gross, charge_a, charge_b = (
            _float(detail.get("gross")),
            _float(detail.get("chargeA")),
            _float(detail.get("chargeB")),
        )
        net = _float(detail.get("net"))
        names = namer.variables(expression)
        rows: list[dict[str, Any]] = []
        for occurrence in occurrences:
            number = int(occurrence["bb"])
            block = report.blocks.get(number)
            rows.append(
                {
                    "block": number,
                    "weight": _float(occurrence.get("weight")),
                    "uses": optional_integer(occurrence.get("uses")),
                    "defs": optional_integer(occurrence.get("defs")),
                    "term": _float(occurrence.get("term")),
                    "lines": block.span() if block else None,
                    "naming_lines": _naming_lines(block, names, source),
                    "flags": [
                        key
                        for key in ("nl", "o22", "o23")
                        if occurrence.get(key) == "1"
                    ],
                    "shown": block_filter is None or number == block_filter,
                }
            )
        terms = sum(row["term"] for row in rows)
        result["references"] = {
            "gross": gross,
            "chargeA": charge_a,
            "chargeB": charge_b,
            "net": net,
            "nocs": optional_integer(detail.get("nocs")),
            "save": _float(detail.get("save")),
            "names": names,
            "rows": rows,
            "terms_sum_to_gross": _close(terms, gross) if rows else None,
            "net_is_gross_minus_charges": _close(gross - charge_a - charge_b, net),
            "net_is_totalsave": _close(net, result["totalsave"]),
        }
    seed = 0
    contributions: dict[int, list[int]] = defaultdict(list)
    for row in decision.forbid:
        own = optional_integer(row.get("own"))
        mask = _hex(row.get("mask0"))
        if own is not None and 0 < own < 32:
            mask &= ~(1 << (31 - own))
        seed |= mask
        for bit in decode_forbidden_colors(mask, 0):
            contributions[bit].append(int(row["bb"]))
    decided = _hex(fields.get("forbidden0"))
    result["forbidden"] = {
        "seed": f"0x{seed:08x}",
        "at_decision": f"0x{decided:08x}",
        "neighbours_add": [
            colour_name(c) for c in decode_forbidden_colors(decided & ~seed, 0)
        ],
        "sources": [
            {
                "colour": bit,
                "register": colour_name(bit),
                "blocks": [
                    {
                        "block": number,
                        "source": _seed_sources(report, number, bit, namer),
                    }
                    for number in numbers
                    if block_filter is None or number == block_filter
                ],
            }
            for bit, numbers in sorted(contributions.items())
        ],
        "live_in_filtered_block": (
            None
            if block_filter is None
            else any(int(row["bb"]) == block_filter for row in decision.forbid)
        ),
    }
    result["growth"] = _growth(report, decision, block_filter)
    return result


def _growth(
    report: WebReport, decision: Decision, block_filter: int | None
) -> dict[str, Any] | None:
    if not decision.growth:
        return None
    pieces: list[dict[str, Any]] = []
    first_refused: dict[str, Any] | None = None
    pending: dict[str, str] | None = None
    current: dict[str, Any] | None = None
    for kind, fields in decision.growth:
        if kind == "seed":
            target = report.pieces.get(fields.get("lr", ""))
            current = {
                "live_range": fields.get("lr"),
                "seed_block": optional_integer(fields.get("bb")),
                "piece_web": target.web if target else None,
                "piece_decision": target.fields.get("decision") if target else None,
                "piece_register": (
                    colour_name(c)
                    if target and (c := target.colour_number) is not None
                    else None
                ),
                "tests": [],
            }
            pieces.append(current)
        elif kind == "grow":
            pending = fields
        elif kind == "growv" and pending is not None:
            test_fields, pending = pending, None
            accepted = fields.get("accepted") == "1"
            predicted = rule_verdict(
                new=int(test_fields["new"]),
                left_before=int(test_fields["left_before"]),
                left_after=int(test_fields["left_after"]),
                numintf=int(test_fields["numintf"]),
                strict=int(test_fields.get("strict", "1")),
            )
            block = int(test_fields["bb"])
            test = {
                "block": block,
                "new": int(test_fields["new"]),
                "left_before": int(test_fields["left_before"]),
                "left_after": int(test_fields["left_after"]),
                "numintf": int(test_fields["numintf"]),
                "accepted": accepted,
                "rule_agrees": predicted == accepted,
                "shown": block_filter is None or block == block_filter,
            }
            if current is None:
                current = {
                    "live_range": test_fields.get("lr"),
                    "seed_block": None,
                    "tests": [],
                }
                pieces.append(current)
            current["tests"].append(test)
            if not accepted and first_refused is None:
                first_refused = {"block": block, "live_range": test_fields.get("lr")}
    return {"rule": RULE, "pieces": pieces, "first_refused": first_refused}


def web_report_payload(
    report: WebReport,
    namer: Namer,
    *,
    source: Sequence[str] = (),
    webs: set[int] | None = None,
    block_filter: int | None = None,
) -> dict[str, Any]:
    """The machine-readable report, ``decomp-workbench-web-report-v1``."""

    block = report.blocks.get(block_filter) if block_filter is not None else None
    return {
        "schema": WEB_REPORT_SCHEMA,
        "proc": report.proc,
        "decision_count": len(report.decisions),
        "missing_records": list(report.missing_records),
        "block": (
            None
            if block_filter is None
            else {
                "block": block_filter,
                "weight": block.weight if block else None,
                "lines": block.span() if block else None,
                "pinned": (
                    [
                        colour_name(c)
                        for c in decode_forbidden_colors(block.mask1 | block.mask2, 0)
                    ]
                    if block
                    else None
                ),
            }
        ),
        "decisions": [
            describe_decision(report, decision, namer, source, block_filter)
            for decision in report.decisions
            if not webs or decision.web in webs
        ],
    }


def _number(value: Any) -> str:
    if isinstance(value, float):
        return "nan" if math.isnan(value) else f"{value:g}"
    return "-" if value is None else str(value)


def render_web_report(payload: Mapping[str, Any], header: str) -> list[str]:
    """Terminal lines for a :func:`web_report_payload`."""

    lines = [header]
    block = payload.get("block")
    if block:
        pinned = " ".join(block["pinned"] or []) or "none"
        lines.append(
            f"bb{block['block']}: weight {_number(block['weight'])}, lines "
            f"{block['lines'] or '?'}, pinned registers {pinned}"
        )
    if payload["missing_records"]:
        lines.append("missing records: " + " ".join(payload["missing_records"]))
    for item in payload["decisions"]:
        lines.append("")
        lines.extend(_decision_lines(item, payload["decision_count"]))
    return lines


def _decision_lines(item: Mapping[str, Any], total: int) -> list[str]:
    chosen = (
        f"{item['register']} (c{item['colour']})"
        if item["colour"] is not None
        else "none (memory)"
    )
    out = [
        f"web {item['web']} {item['phase']}  {item['rendered'] or '?'}  "
        f"[{item['kind'] or 'no webexpr'}]   decision {item['order']} of {total}",
        f"  priority save {_number(item['save'])}  nocs {_number(item['nocs'])}  "
        f"totalsave {_number(item['totalsave'])}  "
        f"bestcost {_number(item['bestcost'])}  "
        f"numintf {_number(item['numintf'])}  regsleft {_number(item['regsleft'])}",
        f"  {item['decision']} -> {chosen}   "
        f"forced: dec={_number(item['forced_decision'])} "
        f"color={_number(item['forced_colour'])}  (-2 never forced, -1 accepted)",
    ]
    references = item["references"]
    if references is None:
        out.append("  references: no savedetail record (a log without CDX_WEBREPORT?)")
    else:
        out.append(
            f"  references: gross {_number(references['gross'])} - chargeA "
            f"{_number(references['chargeA'])} - chargeB "
            f"{_number(references['chargeB'])} = net {_number(references['net'])}  "
            f"(/ nocs {_number(references['nocs'])} "
            f"= save {_number(references['save'])})"
        )
        checks = []
        if references["terms_sum_to_gross"] is False:
            checks.append("occurrence terms do not sum to gross")
        if not references["net_is_gross_minus_charges"]:
            checks.append("net is not gross minus the charges")
        if not references["net_is_totalsave"]:
            checks.append("net differs from the decision's totalsave")
        if checks:
            out.append("    CHECK: " + "; ".join(checks) + " -- read the records")
        names = "/".join(references["names"])
        for row in references["rows"]:
            if not row["shown"]:
                continue
            text = (
                f"    bb{row['block']:<4} x{_number(row['weight']):<6} uses "
                f"{_number(row['uses'])} defs {_number(row['defs'])} -> "
                f"{_number(row['term'])}   lines {row['lines'] or '?'}"
            )
            if row["naming_lines"]:
                text += f"   naming {names}: {','.join(map(str, row['naming_lines']))}"
            if row["flags"]:
                text += f"   [{' '.join(row['flags'])}]"
            out.append(text)
    forbidden = item["forbidden"]
    added = " ".join(forbidden["neighbours_add"]) or "nothing"
    out.append(
        f"  forbidden seed {forbidden['seed']}  at decision {forbidden['at_decision']}"
        f"  (neighbours add {added})"
    )
    for source in forbidden["sources"]:
        if source["blocks"]:
            out.append(
                f"    {source['register']} from "
                + ", ".join(
                    f"bb{entry['block']} <- {entry['source']}"
                    for entry in source["blocks"]
                )
            )
    if forbidden["live_in_filtered_block"] is False:
        out.append("    (web is not live in the selected block)")
    growth = item["growth"]
    if growth:
        out.append(f"  split growth ({growth['rule']}):")
        for piece in growth["pieces"]:
            target = ""
            if piece.get("piece_web") is not None:
                target = f" -> web {piece['piece_web']} {piece['piece_decision']}"
                if piece.get("piece_register"):
                    target += f" {piece['piece_register']}"
            out.append(
                f"    piece {piece['live_range']} seeded at "
                f"bb{_number(piece['seed_block'])}" + target
            )
            for test in piece["tests"]:
                if not test["shown"]:
                    continue
                out.append(
                    f"      bb{test['block']:<4} new {test['new']} left "
                    f"{test['left_before']}->{test['left_after']} numintf "
                    f"{test['numintf']}  "
                    + ("accepted" if test["accepted"] else "REFUSED")
                    + (
                        ""
                        if test["rule_agrees"]
                        else "  (rule disagrees: read the record)"
                    )
                )
        if growth["first_refused"]:
            refused = growth["first_refused"]
            out.append(
                f"    first refused block: bb{refused['block']} "
                f"(piece {refused['live_range']})"
            )
    return out
