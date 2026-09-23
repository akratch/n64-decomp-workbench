"""Split growth and per-web block sets, read from the globalcolor profile.

When globalcolor cannot colour a live range it splits it: `split()` seeds a
piece at one reference block and `addadjacents()` grows it breadth-first over
the range's blocks, testing each candidate. With the strict flag set (it reads
1 on the pinned IDO 5.3 profile) a block is accepted iff

    new < left_before   and   2 * left_after >= numintf + new

where `new` is the interferences the block would add, `left_*` the colours the
piece could still take before and after folding the block's held colours in,
and `numintf` the piece's interference count so far. With the flag clear any
block that leaves a colour is accepted.

That rule was the last unread mechanism on Mickey's Speedway USA's largest
function: `webdetail` carries `bb=-1` for every address-constant web, so the
block set of exactly the webs whose splits made the residual was invisible,
and three campaign lanes reasoned about "numintf >= 25 offers a2" as a
pressure rule. It was the shadow of this test. Once the profile emitted the
growth rows (commit d0830b8), every remaining fragment read as one verdict
off by one, and the rule agreed with all 477 recorded tests of one body.

This module is the reader. It joins a web to its decided piece through the
live-range pointer of the web's **last** `webblocks` row (a piece shares its
web number with the parent it was carved from), prints each growth test with
both margins, checks every recorded verdict against the rule, and -- for a
web captured with `CDX_DETAIL_WEB=<web>` -- lists the interferers at each of
its decisions and what changed between them. A margin of -1 is the number a
reader needs: it names how far the verdict is from flipping, and the
neighbour list names what to remove.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .globalcolor import (
    ColorDecision,
    GlobalColorTrace,
    optional_integer,
    register_for_color,
)

__all__ = [
    "GROWTH_RECORDS",
    "GROWTH_SCHEMA",
    "NEIGHBOUR_SCHEMA",
    "BlockSet",
    "GrowthError",
    "GrowthIndex",
    "GrowthTest",
    "growth_report",
    "index_growth",
    "neighbour_report",
    "parse_blocks",
    "rule_census",
    "rule_verdict",
]

GROWTH_SCHEMA = "decomp-workbench-split-growth-v1"
NEIGHBOUR_SCHEMA = "decomp-workbench-neighbours-v1"

#: The records this reader consumes, all SHIPPED by `instrument-uopt`'s
#: globalcolor profile. `webblocks` needs `CDX_DETAIL_WEB` (`all`, or one web
#: for the neighbour rows too); the growth rows need only `CDX_LOG`.
GROWTH_RECORDS = ("webblocks", "seed", "seedcand", "grow", "growv", "livbb")

RULE = (
    "accept iff new < left_before and 2*left_after >= numintf + new "
    "(strict=1); with strict=0 any block that leaves a colour is accepted"
)


class GrowthError(ValueError):
    """A log did not carry what a growth reading needs."""


def parse_blocks(text: str | None) -> tuple[int, ...]:
    """Decode a `bbs=`/`aux=` field: comma-separated blocks, `-` for none."""

    if not text or text == "-":
        return ()
    return tuple(int(item) for item in text.split(",") if item.strip())


@dataclass(frozen=True)
class BlockSet:
    """A decided web's live-range block sets.

    `span` is the member set (every block the range is live in) and
    `passthrough` the auxiliary vector (blocks it passes through with no
    reference), so `references` -- span minus passthrough -- holds the
    original references plus, for a split piece, where the piece begins and
    ends.
    """

    web: int
    live_range: str
    span: tuple[int, ...]
    passthrough: tuple[int, ...]
    decisions: int

    @property
    def references(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.span) - set(self.passthrough)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "web": self.web,
            "live_range": self.live_range,
            "span": list(self.span),
            "passthrough": list(self.passthrough),
            "references": list(self.references),
            "decisions": self.decisions,
        }


def rule_verdict(
    *, new: int, left_before: int, left_after: int, numintf: int, strict: int
) -> bool:
    """What the growth rule predicts for one candidate block."""

    if not strict:
        return left_after > 0
    return new < left_before and 2 * left_after >= numintf + new


@dataclass(frozen=True)
class GrowthTest:
    """One `grow` row joined with the `growv` verdict that followed it."""

    block: int
    new: int
    left_before: int
    left_after: int
    numintf: int
    strict: int
    accepted: bool | None

    @property
    def headroom(self) -> int:
        """`left_before - new`: the first clause holds while this is > 0."""

        return self.left_before - self.new

    @property
    def margin(self) -> int:
        """`2*left_after - numintf - new`: the second clause holds at >= 0."""

        return 2 * self.left_after - self.numintf - self.new

    @property
    def shortfall(self) -> int:
        """How far the recorded inputs are from acceptance; 0 when accepted.

        The larger of the two clauses' deficits, so a rejection "by one" reads
        as 1 whichever clause refused it.
        """

        if not self.strict:
            return max(0, 1 - self.left_after)
        return max(0, 1 - self.headroom, -self.margin)

    @property
    def predicted(self) -> bool:
        return rule_verdict(
            new=self.new,
            left_before=self.left_before,
            left_after=self.left_after,
            numintf=self.numintf,
            strict=self.strict,
        )

    @property
    def agrees(self) -> bool | None:
        return None if self.accepted is None else self.accepted == self.predicted

    def as_dict(self) -> dict[str, Any]:
        return {
            "block": self.block,
            "new": self.new,
            "left_before": self.left_before,
            "left_after": self.left_after,
            "numintf": self.numintf,
            "strict": self.strict,
            "headroom": self.headroom,
            "margin": self.margin,
            "shortfall": self.shortfall,
            "accepted": self.accepted,
            "predicted": self.predicted,
            "agrees": self.agrees,
        }


@dataclass
class GrowthIndex:
    """One procedure's block sets and growth rows, indexed for a query."""

    proc: int | None
    blocks: dict[int, list[dict[str, str]]] = field(default_factory=dict)
    growth: dict[str, list[ColorDecision]] = field(default_factory=dict)
    kinds: dict[str, int] = field(default_factory=dict)

    def block_set(self, web: int) -> BlockSet | None:
        rows = self.blocks.get(web)
        if not rows:
            return None
        last = rows[-1]
        return BlockSet(
            web=web,
            live_range=last.get("lr", "?"),
            span=parse_blocks(last.get("bbs")),
            passthrough=parse_blocks(last.get("aux")),
            decisions=len(rows),
        )

    def tests_of(self, live_range: str) -> list[GrowthTest]:
        return _tests(self.growth.get(live_range, []))


def _selected(item: ColorDecision, proc: int | None) -> bool:
    return proc is None or optional_integer(item.fields.get("proc")) == proc


def index_growth(trace: GlobalColorTrace, *, proc: int | None = None) -> GrowthIndex:
    """Index every block-set and growth record of one procedure, in log order."""

    index = GrowthIndex(proc=proc)
    for item in trace.decisions:
        if item.phase not in GROWTH_RECORDS or not _selected(item, proc):
            continue
        index.kinds[item.phase] = index.kinds.get(item.phase, 0) + 1
        if item.phase == "webblocks":
            if item.fields.get("role", "target") != "target":
                continue
            web = optional_integer(item.fields.get("web"))
            if web is not None:
                index.blocks.setdefault(web, []).append(dict(item.fields))
            continue
        index.growth.setdefault(item.fields.get("lr", "?"), []).append(item)
    return index


def _integer(fields: Mapping[str, str], key: str) -> int:
    value = optional_integer(fields.get(key))
    return 0 if value is None else value


def _tests(rows: Sequence[ColorDecision]) -> list[GrowthTest]:
    tests: list[GrowthTest] = []
    pending: dict[str, str] | None = None
    for item in rows:
        if item.phase == "grow":
            if pending is not None:
                tests.append(_test(pending, None))
            pending = dict(item.fields)
        elif item.phase == "growv" and pending is not None:
            if item.fields.get("bb") == pending.get("bb"):
                tests.append(_test(pending, item.fields.get("accepted") == "1"))
                pending = None
    if pending is not None:
        tests.append(_test(pending, None))
    return tests


def _test(fields: Mapping[str, str], accepted: bool | None) -> GrowthTest:
    return GrowthTest(
        block=_integer(fields, "bb"),
        new=_integer(fields, "new"),
        left_before=_integer(fields, "left_before"),
        left_after=_integer(fields, "left_after"),
        numintf=_integer(fields, "numintf"),
        strict=_integer(fields, "strict"),
        accepted=accepted,
    )


def _require(index: GrowthIndex, kinds: Iterable[str], purpose: str) -> None:
    missing = [kind for kind in kinds if not index.kinds.get(kind)]
    if missing:
        present = ", ".join(sorted(index.kinds)) or "none of the growth records"
        raise GrowthError(
            f"the log carries no {'/'.join(missing)} record(s), which {purpose} "
            f"needs (present: {present}). They are part of the globalcolor "
            "profile: capture with CDX_LOG=1, CDX_OUT=<file> and "
            "CDX_DETAIL_WEB=all (or =<web>) on a compiler instrumented after "
            "the block-set revision"
        )


def growth_report(index: GrowthIndex, web: int) -> dict[str, Any]:
    """The decided piece of one web: its block sets and every growth test."""

    _require(index, ("webblocks",), "a block-set reading")
    blocks = index.block_set(web)
    if blocks is None:
        raise GrowthError(
            f"web {web} has no webblocks row; it was not decided in this "
            "procedure, or the capture's CDX_DETAIL_WEB did not include it"
        )
    rows = index.growth.get(blocks.live_range, [])
    seed = next(
        (
            optional_integer(item.fields.get("bb"))
            for item in rows
            if item.phase == "seed"
        ),
        None,
    )
    tests = _tests(rows)
    moves = [
        {
            "op": item.fields.get("op"),
            "block": optional_integer(item.fields.get("bb")),
            "refs": optional_integer(item.fields.get("refs")),
        }
        for item in rows
        if item.phase == "livbb"
    ]
    candidates = [
        {
            "pass": optional_integer(item.fields.get("pass")),
            "block": optional_integer(item.fields.get("bb")),
            "maskdiff": optional_integer(item.fields.get("maskdiff")),
        }
        for item in rows
        if item.phase == "seedcand"
    ]
    rejected = [test for test in tests if test.accepted is False]
    nearest = (
        min(rejected, key=lambda test: (test.shortfall, test.block))
        if rejected
        else None
    )
    return {
        "schema": GROWTH_SCHEMA,
        "proc": index.proc,
        "web": web,
        "blocks": blocks.as_dict(),
        "split": bool(rows),
        "seed": seed,
        "seed_candidates": candidates,
        "tests": [test.as_dict() for test in tests],
        "liveblock_moves": moves,
        "disagreements": [test.block for test in tests if test.agrees is False],
        "nearest_rejection": nearest.as_dict() if nearest is not None else None,
        "rule": RULE,
    }


def rule_census(index: GrowthIndex) -> dict[str, Any]:
    """Every recorded growth test in the procedure, checked against the rule."""

    _require(index, ("grow", "growv"), "a rule census")
    tests = [test for rows in index.growth.values() for test in _tests(rows)]
    judged = [test for test in tests if test.agrees is not None]
    disagree = [test for test in judged if not test.agrees]
    return {
        "schema": GROWTH_SCHEMA,
        "mode": "census",
        "proc": index.proc,
        "pieces": sum(
            1 for rows in index.growth.values() if any(r.phase == "grow" for r in rows)
        ),
        "tests": len(tests),
        "judged": len(judged),
        "agree": len(judged) - len(disagree),
        "disagree": [test.as_dict() for test in disagree],
        "unjudged": len(tests) - len(judged),
        "margin_histogram": _histogram(test.margin for test in tests),
        "rule": RULE,
    }


def _histogram(values: Iterable[int]) -> dict[str, int]:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {f"{key:+d}": counts[key] for key in sorted(counts)}


def neighbour_report(
    trace: GlobalColorTrace,
    *,
    web: int,
    proc: int | None = None,
    phase: str = "p1",
    window: Sequence[int] = (),
) -> dict[str, Any]:
    """The interferers at each decision of one web, and what changed between.

    Reads the `intf` rows and the `webblocks role=neighbor` rows a capture made
    with `CDX_DETAIL_WEB=<web>` prints after each of that web's decisions.
    `window` keeps only neighbours live in at least one of those blocks, which
    is how a growth test's `new` is traced to the webs that make it.
    """

    wanted = set(window)
    decisions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for item in trace.decisions:
        if not _selected(item, proc):
            continue
        if item.phase in {f"{phase}dec", f"{phase}cand"}:
            if current is not None:
                decisions.append(current)
                current = None
            if (
                item.phase == f"{phase}dec"
                and optional_integer(item.fields.get("web")) == web
            ):
                current = {
                    "decision": item.fields.get("decision"),
                    "save": item.fields.get("save"),
                    "numintf": optional_integer(item.fields.get("numintf")),
                    "regsleft": optional_integer(item.fields.get("regsleft")),
                    "neighbours": {},
                }
            continue
        if current is None:
            continue
        if item.phase == "intf" and optional_integer(item.fields.get("web")) == web:
            other = optional_integer(item.fields.get("other"))
            if other is None:
                continue
            assigned = optional_integer(item.fields.get("assigned")) or 0
            entry = current["neighbours"].setdefault(other, {"web": other})
            entry["sym"] = optional_integer(item.fields.get("sym"))
            entry["assigned"] = assigned
            entry["register"] = register_for_color(assigned) if assigned > 0 else None
        elif item.phase == "webblocks" and item.fields.get("role") == "neighbor":
            other = optional_integer(item.fields.get("web"))
            if other is None:
                continue
            entry = current["neighbours"].setdefault(other, {"web": other})
            entry["blocks"] = list(parse_blocks(item.fields.get("bbs")))
    if current is not None:
        decisions.append(current)
    if not decisions:
        raise GrowthError(
            f"web {web} has no {phase}dec record"
            + ("" if proc is None else f" in proc {proc}")
            + "; a neighbour reading needs a capture made with "
            f"CDX_DETAIL_WEB={web}"
        )
    rendered = []
    previous: set[int] | None = None
    for number, decision in enumerate(decisions):
        neighbours = [
            {
                **entry,
                "in_window": sorted(set(entry.get("blocks", [])) & wanted)
                if wanted
                else None,
            }
            for _, entry in sorted(decision["neighbours"].items())
            if not wanted or set(entry.get("blocks", [])) & wanted
        ]
        present = {entry["web"] for entry in neighbours}
        rendered.append(
            {
                "index": number,
                "decision": decision["decision"],
                "save": decision["save"],
                "numintf": decision["numintf"],
                "regsleft": decision["regsleft"],
                "neighbours": neighbours,
                "gone": sorted(previous - present) if previous is not None else [],
                "new": sorted(present - previous) if previous is not None else [],
            }
        )
        previous = present
    return {
        "schema": NEIGHBOUR_SCHEMA,
        "proc": proc,
        "phase": phase,
        "web": web,
        "window": sorted(wanted),
        "decisions": rendered,
    }
