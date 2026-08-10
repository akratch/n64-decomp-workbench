"""The variant families a search actually needs, and the carrier pool they draw from.

Six generators, each one a class in :data:`decomp_workbench.sweep.GENERATOR_CLASSES`,
each emitting sources through the composer so that every edit states the base it
was written against and the zones it must not touch.

The one that matters most is the cheapest. **N -- null-hypothesis removal**:
every stage inherits its predecessor's construction as "the base" and attacks
only the residue, so the single highest-value experiment available at any point
-- rebuild the base with each accumulated lever *removed* -- is almost never
run. One campaign ran it once, twelve builds and ninety seconds, and found that
a whole four-atom supplier set was phase-neutral dead weight costing ten rows on
the live base. Ten rows of pure cost had been carried for several stages because
nobody re-tested an inherited construction.

The rest are the shapes that mint deltas nothing else does: the deep operand
hoist (a leaf of a *nested* subexpression, which can avoid disturbing the local
ring where a shallow hoist does not), the compound-assignment and call-argument
hoists that no generator library had, the commutative flip, the copy
elimination, and the live-range fusion.

Every one of them draws its carrier from the same pool, and that is deliberate.
A fresh local costs frame bytes and the frame gate forbids it; a *recycled dead
local* costs nothing. Five stages of one campaign reimplemented that pool by
hand, and the sweeps that forgot it spent their budget on candidates the gate
was always going to reject.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compose import ComposeError, Edit, EditPlan, apply_plan, source_sha256
from .coverage import SweepCoverage
from .csource import (
    CSourceError,
    Statement,
    declarations,
    defines,
    definition_lines,
    identifiers,
    reads,
    scan_statements,
    strip_noncode,
    takes_address,
)
from .sweep import SweepError, SweepManifest, Variant, VariantKey

__all__ = [
    "Carrier",
    "CarrierPool",
    "carrier_pool",
    "commutative_family",
    "copy_family",
    "fusion_family",
    "hoist_family",
    "parse_construct",
    "removal_family",
]

#: What every generator here does not know, printed with every manifest.
GENERATOR_LIMITS: tuple[str, ...] = (
    "Edits are textual and structural. Nothing here parses or types C, so a "
    "variant is a proposal to build, not a proven-equivalent program.",
    "Liveness is read from the text: a definition is an assignment, a compound "
    "assignment, an increment or an address-of. A write through a pointer the "
    "text does not spell is not seen.",
    "A carrier is only ever an existing dead local. A fresh declaration mints a "
    "new frame slot (8 bytes for an f32 on the one compiler this was measured "
    "on) and the frame gate rejects it, so the pool never proposes one.",
    "Review a winner before adopting it: `decomp-workbench experiment "
    "review-mutation BASE WINNER`.",
)


def _read_source(path: str | Path) -> tuple[list[str], list[str]]:
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as error:
        raise CSourceError(f"cannot read {path}: {error}") from None
    if not text.strip():
        raise CSourceError(f"{path} is empty")
    return text.splitlines(), strip_noncode(text)


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


# --------------------------------------------------------------------------
# The carrier pool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Carrier:
    """One candidate carrier, with the verdict that decides whether it is free."""

    name: str
    declaration_line: int
    declaration_index: int
    type_text: str
    verdict: str
    reason: str
    last_read: int | None = None
    next_use: int | None = None

    @property
    def usable(self) -> bool:
        return self.verdict == "dead"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "declaration_line": self.declaration_line,
            "declaration_index": self.declaration_index,
            "type": self.type_text,
            "verdict": self.verdict,
            "reason": self.reason,
            "last_read": self.last_read,
            "next_use": self.next_use,
            "usable": self.usable,
        }


@dataclass(frozen=True)
class CarrierPool:
    """The dead locals available at one site, in declaration order."""

    source: str
    at: int
    carriers: tuple[Carrier, ...]
    declared: int
    wanted_type: str | None = None

    @property
    def usable(self) -> tuple[Carrier, ...]:
        return tuple(item for item in self.carriers if item.usable)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "decomp-workbench-carrier-pool-v1",
            "source": self.source,
            "at": self.at,
            "wanted_type": self.wanted_type,
            "declared": self.declared,
            "pool_size": len(self.usable),
            "carriers": [item.as_dict() for item in self.carriers],
            "rule": (
                "A carrier is an existing local that is dead at this site. A "
                "fresh declaration mints a frame slot the frame gate rejects, "
                "and an unused pad has no web to merge into -- so declared "
                "symbols are enumerated first and a pad is never proposed."
            ),
            "limits": list(GENERATOR_LIMITS),
        }


def carrier_pool(
    path: str | Path,
    *,
    at: int,
    wanted_type: str | None = None,
) -> CarrierPool:
    """Return the locals that are dead at line `at`, in declaration order.

    Dead means: from this line onward, nothing reads the local before
    something writes it. That is the condition under which a hoist may recycle
    it for free -- no new frame slot, no new web, no cost the gate can see.

    A local whose deciding read or write sits inside a loop that also encloses
    the site is reported ``unproven`` rather than ``dead``: a back-edge can
    carry the old value back to a read that textually precedes the write.
    """

    code = _read_source(path)[1]
    if not 1 <= at <= len(code):
        raise CSourceError(f"{path} has {len(code)} line(s); --at names line {at}")
    statements = scan_statements(code)
    by_line = {item.line: item for item in statements}
    site = by_line.get(at)
    site_loops = set(site.loops) if site is not None else set()

    found: list[Carrier] = []
    for declaration in declarations(code):
        if declaration.is_array:
            continue
        if declaration.line >= at:
            continue
        if wanted_type and declaration.type_text != wanted_type:
            continue
        name = declaration.name
        if takes_address(code, name):
            found.append(
                Carrier(
                    name=name,
                    declaration_line=declaration.line,
                    declaration_index=declaration.index,
                    type_text=declaration.type_text,
                    verdict="escapes",
                    reason=(
                        "its address is taken somewhere in this file, so a "
                        "callee may hold a pointer to it"
                    ),
                )
            )
            continue
        verdict, reason, next_use = _liveness_at(code, name, at=at, by_line=by_line)
        if verdict == "dead" and next_use is not None:
            statement = by_line.get(next_use)
            if statement is not None and set(statement.loops) - site_loops:
                verdict = "unproven"
                reason = (
                    f"the write at line {next_use} that would make it dead is "
                    "inside a loop the site is not in; a back-edge can carry "
                    "the old value to a read that precedes it textually"
                )
        reads_before = [
            number for number, line in enumerate(code, 1) if reads(line, name)
        ]
        found.append(
            Carrier(
                name=name,
                declaration_line=declaration.line,
                declaration_index=declaration.index,
                type_text=declaration.type_text,
                verdict=verdict,
                reason=reason,
                last_read=max(reads_before) if reads_before else None,
                next_use=next_use,
            )
        )
    order = {"dead": 0, "unproven": 1, "live": 2, "escapes": 3}
    found.sort(key=lambda item: (order[item.verdict], item.declaration_index))
    return CarrierPool(
        source=str(path),
        at=at,
        carriers=tuple(found),
        declared=len(declarations(code)),
        wanted_type=wanted_type,
    )


def _liveness_at(
    code: list[str],
    name: str,
    *,
    at: int,
    by_line: dict[int, Statement],
) -> tuple[str, str, int | None]:
    """Classify `name` at line `at`: dead, live, or unproven."""

    for number in range(at, len(code) + 1):
        line = code[number - 1]
        if not reads(line, name) and not defines(line, name):
            continue
        if defines(line, name) and not _reads_own_value(line, name):
            return (
                "dead",
                f"line {number} writes it before anything reads it, so its "
                "value here is not observed",
                number,
            )
        return (
            "live",
            f"line {number} reads it before anything writes it, so recycling "
            "it here would change that read",
            number,
        )
    return ("dead", "nothing reads or writes it after this site", None)


def _reads_own_value(line: str, name: str) -> bool:
    """Whether a write to `name` also reads it (`x += y`, `x = x + 1`, `x++`)."""

    quoted = re.escape(name)
    compound = rf"(?<![\w.>]){quoted}\s*(?:\[[^\];]*\])?\s*(?:[-+*/%&|^]=|<<=|>>=)"
    if re.search(compound, line):
        return True
    step = rf"(?:\+\+|--)\s*{quoted}\b|{quoted}\s*(?:\+\+|--)"
    if re.search(step, line):
        return True
    _, _, rhs = line.partition("=")
    return bool(rhs) and name in identifiers(rhs)


# --------------------------------------------------------------------------
# N -- the null hypothesis
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Construct:
    """One accumulated lever, named by the lines that spell it."""

    first: int
    last: int
    label: str

    @property
    def lines(self) -> range:
        return range(self.first, self.last + 1)

    @property
    def site(self) -> str:
        if self.first == self.last:
            return f"L{self.first}"
        return f"L{self.first}-{self.last}"


def parse_construct(text: str) -> Construct:
    """Parse ``LO..HI=label``, ``LO..HI`` or ``N`` into a construct."""

    spec, _, label = text.partition("=")
    raw = spec.strip()
    if not raw:
        raise SweepError(f"{text!r} names no lines; write LO..HI or N")
    low_text, _, high_text = raw.partition("..") if ".." in raw else (raw, "", raw)
    try:
        first, last = int(low_text), int(high_text)
    except ValueError:
        raise SweepError(
            f"{text!r} is not a construct; write LO..HI[=label] or N[=label]"
        ) from None
    if first < 1 or last < first:
        raise SweepError(
            f"{text!r} is not a line range: lines start at 1 and LO must not exceed HI"
        )
    return Construct(first=first, last=last, label=label.strip())


def removal_family(
    path: str | Path,
    *,
    constructs: tuple[Construct, ...],
    order: int = 1,
    frozen: tuple[tuple[int, int], ...] = (),
) -> SweepManifest:
    """Emit the removal lattice: each construct deleted, singly and jointly.

    The control -- the base itself, unedited -- is always the first variant.
    A price is a difference, and a difference needs both terms measured in the
    same run by the same wrapper; a remembered score from an earlier session is
    what made this experiment skippable in the first place.
    """

    if not constructs:
        raise SweepError(
            "name at least one construct to remove: --construct LO..HI=label. "
            "The constructs are the levers this base has accumulated; the "
            "sweep prices each of them on the base as it stands now."
        )
    raw, code = _read_source(path)
    for item in constructs:
        if item.last > len(raw):
            raise SweepError(
                f"{path} has {len(raw)} line(s); construct {item.label or item.site} "
                f"names line {item.last}"
            )
    if order < 1:
        raise SweepError("--order must be at least 1")

    base_sha = source_sha256(path)
    stem = Path(path).stem
    variants: list[Variant] = [
        Variant(
            key=VariantKey(site="control", generator_class="N", carrier="-"),
            filename=f"{stem}.N.control.c",
            text="".join(f"{line}\n" for line in raw),
            description=(
                "the base, unedited: the control every price is measured against"
            ),
            detail={"removed": [], "control": True},
        )
    ]
    dropped: list[dict[str, str]] = []

    subsets: list[tuple[Construct, ...]] = []
    for size in range(1, min(order, len(constructs)) + 1):
        subsets.extend(itertools.combinations(constructs, size))
    if len(constructs) > order:
        subsets.append(tuple(constructs))

    for subset in subsets:
        removed = sorted({line for item in subset for line in item.lines})
        site = "+".join(item.site for item in subset)
        label = "+".join(item.label or item.site for item in subset)
        try:
            composed = apply_plan(
                EditPlan(
                    base=Path(path),
                    base_sha256=base_sha,
                    edits=tuple(
                        Edit(line=number, expect=raw[number - 1], label=label)
                        for number in removed
                    ),
                    frozen=frozen,
                    label=label,
                )
            )
        except ComposeError as error:
            dropped.append({"site": site, "reason": str(error).splitlines()[0]})
            continue
        variants.append(
            Variant(
                key=VariantKey(site=site, generator_class="N", carrier="-"),
                filename=f"{stem}.N.{_slug(site)}.c",
                text=composed.text,
                description=f"removed: {label}",
                detail={
                    "removed": removed,
                    "constructs": [item.label or item.site for item in subset],
                    "order": len(subset),
                    "semantics": _removal_semantics(code, removed),
                },
            )
        )

    space = 2 ** len(constructs)
    return SweepManifest(
        generator="regress",
        base=str(path),
        base_sha256=base_sha,
        variants=tuple(variants),
        coverage=SweepCoverage(
            basis=f"subsets of {len(constructs)} construct(s) up to order {order}",
            space=space,
            covered=len(variants),
            excluded=len(dropped),
        ),
        dropped=tuple(dropped),
        limits=GENERATOR_LIMITS,
    )


def _removal_semantics(code: list[str], removed: list[int]) -> str:
    """Name the one shape a removal can break: a definition something reads."""

    gone = set(removed)
    survivors = [
        line if number not in gone else "" for number, line in enumerate(code, 1)
    ]
    broken: list[str] = []
    for number in removed:
        for name in identifiers(code[number - 1]):
            if not defines(code[number - 1], name):
                continue
            still_defined = [
                other for other in definition_lines(code, name) if other not in gone
            ]
            still_read = any(
                reads(line, name) for index, line in enumerate(survivors, 1) if line
            )
            if still_read and not still_defined:
                broken.append(name)
    if broken:
        return "read-before-definition: " + ", ".join(sorted(set(broken)))
    return "ok"


# --------------------------------------------------------------------------
# H / O / P / A -- the hoists
# --------------------------------------------------------------------------

_ASSIGN_RE = re.compile(r"^(?P<lhs>[^=;]+?)\s*=(?!=)\s*(?P<rhs>.+);\s*$")
_COMPOUND_ASSIGN_RE = re.compile(
    r"^(?P<lhs>[^=;]+?)\s*(?P<op>[-+*/%&|^]=|<<=|>>=)\s*(?P<rhs>.+);\s*$"
)
_LEAF_RE = re.compile(r"[A-Za-z_]\w*(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)*(?:\s*\[[^\]]*\])?")
_BINARY_RE = re.compile(r"\s(?P<op>[-+*/]|<<|>>)\s")


def hoist_family(
    path: str | Path,
    *,
    line: int,
    classes: tuple[str, ...] = ("O",),
    carriers: tuple[str, ...] = (),
    frozen: tuple[tuple[int, int], ...] = (),
) -> SweepManifest:
    """Emit hoists of one statement's operands into every available carrier.

    The carrier is part of the key, not an implementation detail: at one line
    of one campaign, two carriers drawn from different declaration indices
    produced two entirely different cost deltas.
    """

    raw, _code = _read_source(path)
    if not 1 <= line <= len(raw):
        raise SweepError(f"{path} has {len(raw)} line(s); --line names line {line}")
    for letter in classes:
        if letter not in {"H", "O", "P", "A"}:
            raise SweepError(
                f"{letter!r} is not a hoist class; choose from H (top-level "
                "operand), O (deep operand), P (compound assignment), "
                "A (call argument)"
            )
    pool = carrier_pool(path, at=line)
    names = carriers or tuple(item.name for item in pool.usable)
    if not names:
        raise SweepError(
            f"no local is dead at line {line}, so there is no carrier to hoist "
            "into. Run `decomp-workbench sweep carriers` to see why each "
            "declared local was refused; a fresh declaration is not an answer, "
            "because it mints a frame slot the gate rejects."
        )
    declared = {item.name for item in pool.carriers}
    unknown = [name for name in names if name not in declared]
    if unknown:
        raise SweepError(
            f"{path} does not declare {', '.join(unknown)}; a carrier must be "
            "an existing local"
        )

    text = raw[line - 1]
    indent = _indent(text)
    base_sha = source_sha256(path)
    stem = Path(path).stem
    variants: list[Variant] = []
    dropped: list[dict[str, str]] = []
    proposals = _hoist_proposals(text.strip(), classes=classes)
    if not proposals:
        raise SweepError(
            f"{path}:{line} offers no hoist of class {', '.join(classes)}: "
            f"{text.strip()!r}. H and O need an assignment with a compound "
            "right-hand side, P a compound assignment, A a call with an "
            "expression argument."
        )
    for proposal in proposals:
        for name in names:
            carrier = next(item for item in pool.carriers if item.name == name)
            site = f"L{line}.{proposal.token}"
            statement = proposal.rewrite(name)
            try:
                composed = apply_plan(
                    EditPlan(
                        base=Path(path),
                        base_sha256=base_sha,
                        edits=(
                            Edit(
                                line=line,
                                expect=text,
                                replace=indent + statement,
                                insert=(f"{indent}{name} = {proposal.leaf};",),
                                label=f"{proposal.generator_class} hoist into {name}",
                            ),
                        ),
                        frozen=frozen,
                        anchors=(),
                        label=site,
                    )
                )
            except ComposeError as error:
                dropped.append({"site": site, "reason": str(error).splitlines()[0]})
                continue
            variants.append(
                Variant(
                    key=VariantKey(
                        site=site,
                        generator_class=proposal.generator_class,
                        carrier=name,
                    ),
                    filename=f"{stem}.{proposal.generator_class}.{_slug(site)}.{name}.c",
                    text=composed.text,
                    description=(
                        f"hoist {proposal.leaf!r} into {name} "
                        f"(declaration index {carrier.declaration_index})"
                    ),
                    detail={
                        "leaf": proposal.leaf,
                        "carrier_verdict": carrier.verdict,
                        "carrier_declaration_index": carrier.declaration_index,
                        "line": line,
                    },
                )
            )
    return SweepManifest(
        generator="hoist",
        base=str(path),
        base_sha256=base_sha,
        variants=tuple(variants),
        coverage=SweepCoverage(
            basis=(
                f"{len(proposals)} hoist site(s) at line {line} x "
                f"{len(names)} carrier(s)"
            ),
            space=len(proposals) * len(names),
            covered=len(variants),
            excluded=len(dropped),
        ),
        dropped=tuple(dropped),
        limits=GENERATOR_LIMITS,
    )


@dataclass(frozen=True)
class _Hoist:
    generator_class: str
    token: str
    leaf: str
    before: str
    after: str

    def rewrite(self, carrier: str) -> str:
        return self.before + carrier + self.after


def _hoist_proposals(statement: str, *, classes: tuple[str, ...]) -> list[_Hoist]:
    """Enumerate the hoists available in one statement, by class."""

    found: list[_Hoist] = []
    compound = _COMPOUND_ASSIGN_RE.match(statement)
    if "P" in classes and compound is not None:
        rhs = compound.group("rhs")
        head = statement[: statement.index(rhs)]
        found.append(_Hoist("P", "rhs", rhs, head, ";"))
    assignment = _ASSIGN_RE.match(statement)
    if assignment is not None and compound is None:
        rhs = assignment.group("rhs")
        offset = statement.index(rhs)
        if "H" in classes:
            split = _BINARY_RE.search(rhs)
            if split is not None:
                left, right = rhs[: split.start()], rhs[split.end() :]
                found.append(
                    _Hoist(
                        "H",
                        "lhs",
                        left.strip(),
                        statement[:offset],
                        rhs[split.start() :] + ";",
                    )
                )
                found.append(
                    _Hoist(
                        "H",
                        "rhs",
                        right.strip(),
                        statement[:offset] + rhs[: split.end()],
                        ";",
                    )
                )
        if "O" in classes:
            for index, match in enumerate(_maximal_leaves(rhs)):
                start, end = match
                leaf = rhs[start:end]
                if leaf.strip() == rhs.strip():
                    continue
                found.append(
                    _Hoist(
                        "O",
                        f"k{index}",
                        leaf.strip(),
                        statement[: offset + start],
                        statement[offset + end :],
                    )
                )
    if "A" in classes:
        for index, (start, end) in enumerate(_call_arguments(statement)):
            argument = statement[start:end].strip()
            if not argument or (_LEAF_RE.fullmatch(argument) and "." not in argument):
                continue
            found.append(
                _Hoist("A", f"a{index}", argument, statement[:start], statement[end:])
            )
    return found


def _maximal_leaves(text: str) -> list[tuple[int, int]]:
    """Every maximal leaf token of an expression, as (start, end) offsets.

    A leaf is an identifier chain with its member selections and one optional
    subscript: `obj->pos.x`, `table[i]`, `speed`. Hoisting one of these out of
    a *nested* subexpression is a different class from splitting the top-level
    binary operator, and prices differently -- a deep hoist can leave the local
    ring rotation undisturbed where a shallow one does not.
    """

    spans: list[tuple[int, int]] = []
    for match in _LEAF_RE.finditer(text):
        leaf = match.group()
        if leaf.split(".")[0].split("->")[0].strip().isdigit():
            continue
        if text[match.end() : match.end() + 1] == "(":
            continue
        spans.append((match.start(), match.end()))
    return spans


def _call_arguments(statement: str) -> list[tuple[int, int]]:
    """Every top-level argument span of the first call in the statement."""

    open_index = statement.find("(")
    if open_index < 0:
        return []
    depth = 0
    start = open_index + 1
    spans: list[tuple[int, int]] = []
    for index in range(open_index, len(statement)):
        char = statement[index]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
            if depth == 0:
                spans.append((start, index))
                break
        elif char == "," and depth == 1:
            spans.append((start, index))
            start = index + 1
    return spans


# --------------------------------------------------------------------------
# C -- the commutative flip
# --------------------------------------------------------------------------

#: The operators whose two operands may be exchanged without changing the
#: value. Addition and multiplication are commutative in IEEE 754 even though
#: they are not associative -- which is why only the *immediate* operands of
#: one operator are ever exchanged here.
COMMUTATIVE_OPERATORS = ("*", "+", "&", "|", "^")

_ATOM_RE = re.compile(
    r"^\s*(?:[A-Za-z_]\w*(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)*(?:\s*\[[^\]]*\])?"
    r"|\(.*\)|-?\d+\.?\d*[fFuUlL]*)\s*$"
)


def commutative_family(
    path: str | Path,
    *,
    lines: tuple[int, ...] = (),
    operators: tuple[str, ...] = COMMUTATIVE_OPERATORS,
    frozen: tuple[tuple[int, int], ...] = (),
) -> SweepManifest:
    """Emit one variant per commutative operand pair, exchanged.

    The classifier that names a commutative row is shipped; this is the lever
    it never had. Roughly two hundred builds and half a minute of wall time on
    one campaign's function, and worth fifteen rows there.

    Only pairs whose exchange is *textually pure* are generated. Exchanging the
    operands of one operator preserves the value; reassociating does not, and a
    swap that would need new parentheses to stay associative-safe is refused
    and named in `dropped` rather than emitted with the parentheses added --
    the added parentheses would themselves be an untested second edit.
    """

    raw, code = _read_source(path)
    base_sha = source_sha256(path)
    stem = Path(path).stem
    wanted = set(lines) if lines else None
    declared_at = {item.line for item in declarations(code)}
    variants: list[Variant] = []
    dropped: list[dict[str, str]] = []
    space = 0
    for number, text in enumerate(code, 1):
        if wanted is not None and number not in wanted:
            continue
        if number in declared_at:
            continue
        for index, (start, end, left, operator, right) in enumerate(
            _commutative_pairs(text, operators)
        ):
            space += 1
            site = f"L{number}.p{index}"
            if not _ATOM_RE.match(left) or not _ATOM_RE.match(right):
                dropped.append(
                    {
                        "site": site,
                        "reason": (
                            f"exchanging {left.strip()!r} and {right.strip()!r} "
                            "would need parentheses to stay associative-safe; "
                            "the parentheses are a second, untested edit"
                        ),
                    }
                )
                continue
            source_line = raw[number - 1]
            # Exchange the two operand texts and nothing else. The whitespace
            # around the pair and around the operator is the file's, not this
            # tool's: a re-spaced line is a second edit, and the sweep is
            # supposed to be measuring one.
            left_head, left_core, left_tail = _spaced(left)
            right_head, right_core, right_tail = _spaced(right)
            middle = source_line[start + len(left) : end - len(right)]
            replaced = (
                source_line[:start]
                + left_head
                + right_core
                + left_tail
                + middle
                + right_head
                + left_core
                + right_tail
                + source_line[end:]
            )
            try:
                composed = apply_plan(
                    EditPlan(
                        base=Path(path),
                        base_sha256=base_sha,
                        edits=(
                            Edit(
                                line=number,
                                expect=source_line,
                                replace=replaced,
                                label=(
                                    f"exchange {left.strip()} {operator} "
                                    f"{right.strip()}"
                                ),
                            ),
                        ),
                        frozen=frozen,
                        label=site,
                    )
                )
            except ComposeError as error:
                dropped.append({"site": site, "reason": str(error).splitlines()[0]})
                continue
            variants.append(
                Variant(
                    key=VariantKey(site=site, generator_class="C", carrier=operator),
                    filename=f"{stem}.C.{_slug(site)}.c",
                    text=composed.text,
                    description=(
                        f"line {number}: {left.strip()} {operator} "
                        f"{right.strip()} exchanged"
                    ),
                    detail={"line": number, "operator": operator},
                )
            )
    if not variants and not dropped:
        where = (
            f" on line(s) {', '.join(str(item) for item in sorted(wanted))}"
            if wanted
            else ""
        )
        raise SweepError(f"{path} has no exchangeable commutative operand pair{where}")
    return SweepManifest(
        generator="commute",
        base=str(path),
        base_sha256=base_sha,
        variants=tuple(variants),
        coverage=SweepCoverage(
            basis=f"commutative operand pairs over {', '.join(operators)}",
            space=space,
            covered=len(variants),
            excluded=len(dropped),
        ),
        dropped=tuple(dropped),
        limits=GENERATOR_LIMITS,
    )


#: C's binary precedence for the operators an arithmetic expression can hold.
#: Only used to decide whether a pair really *is* the two operands of one
#: operator: in `a + b * c` the pair `a + b` is not, and exchanging it would
#: reassociate rather than commute.
_PRECEDENCE = {
    "*": 5,
    "/": 5,
    "%": 5,
    "+": 4,
    "-": 4,
    "<<": 3,
    ">>": 3,
    "&": 2,
    "^": 1,
    "|": 0,
}

#: Anything here at depth zero means the region is not plain arithmetic --
#: a comparison, a ternary, a logical operator -- and no pair is offered from
#: it. Refusing is cheap; a wrong swap is a wrong candidate that scores.
_BAIL = ("&&", "||", "?", ":", "==", "!=", "<=", ">=", "!", "=")


def _commutative_pairs(
    text: str, operators: tuple[str, ...]
) -> list[tuple[int, int, str, str, str]]:
    """Return (start, end, left, operator, right) for each exchangeable pair.

    A pair is offered only when it is genuinely one operator's two operands:
    the operator to its left must bind more loosely, and the one to its right
    no more tightly. Otherwise exchanging the two texts reassociates the
    expression, and floating-point addition and multiplication are commutative
    but *not* associative -- the swap would change the value, not the shape.
    """

    found: list[tuple[int, int, str, str, str]] = []
    pending = list(_arithmetic_regions(text))
    while pending:
        start, end = pending.pop(0)
        region = text[start:end]
        # A parenthesized sub-expression is its own region: `a * (b + c)` holds
        # two exchangeable pairs, and only the outer one is visible at depth
        # zero.
        pending.extend(
            (start + low, start + high) for low, high in _parenthesized(region)
        )
        operands, tokens = _split_expression(region)
        if not tokens:
            continue
        for index, (position, operator) in enumerate(tokens):
            if operator not in operators:
                continue
            left_prec = _PRECEDENCE[tokens[index - 1][1]] if index else -1
            right_prec = (
                _PRECEDENCE[tokens[index + 1][1]] if index + 1 < len(tokens) else -1
            )
            if left_prec >= _PRECEDENCE[operator]:
                continue
            if right_prec > _PRECEDENCE[operator]:
                continue
            left_span, right_span = operands[index], operands[index + 1]
            found.append(
                (
                    start + left_span[0],
                    start + right_span[1],
                    region[left_span[0] : left_span[1]],
                    operator,
                    region[right_span[0] : right_span[1]],
                )
            )
            del position
    return found


def _spaced(text: str) -> tuple[str, str, str]:
    """Split one operand into its leading space, its text, and its trailing space."""

    core = text.strip()
    head = text[: len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()) :]
    return head, core, tail


def _parenthesized(region: str) -> list[tuple[int, int]]:
    """The interiors of the depth-zero parenthesized groups in `region`."""

    spans: list[tuple[int, int]] = []
    depth = 0
    opened = 0
    for index, char in enumerate(region):
        if char == "(":
            depth += 1
            if depth == 1:
                opened = index + 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index > opened:
                if region[max(0, opened - 2) : opened - 1].strip()[-1:].isalnum():
                    continue  # a call's argument list, not a grouping
                spans.append((opened, index))
        elif char in "[":
            depth += 1
        elif char in "]":
            depth -= 1
    return spans


def _arithmetic_regions(text: str) -> list[tuple[int, int]]:
    """The spans of one statement worth scanning for an operand pair.

    An assignment's right-hand side, or the arguments of its first call.
    Nothing else: a `for` header and a function signature both hold a `*` that
    is a declarator, and one campaign-shaped generator that scanned whole
    lines proposed exchanging `Object * obj`.
    """

    statement = text.rstrip()
    if not statement.endswith(";"):
        return []
    body = statement[: statement.rindex(";")]
    depth = 0
    for index, char in enumerate(body):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif (
            depth == 0
            and char == "="
            and body[index + 1 : index + 2] != "="
            and body[index - 1 : index] not in {"=", "!", "<", ">", "+", "-", "*", "/"}
        ):
            return [(index + 1, len(body))]
    return _call_arguments(statement)


def _split_expression(
    region: str,
) -> tuple[list[tuple[int, int]], list[tuple[int, str]]]:
    """Split one arithmetic region into depth-zero operands and operators."""

    for marker in _BAIL:
        if _contains_at_top_level(region, marker):
            return [], []
    operands: list[tuple[int, int]] = []
    tokens: list[tuple[int, str]] = []
    depth = 0
    start = 0
    index = 0
    while index < len(region):
        char = region[index]
        if char in "([":
            depth += 1
            index += 1
            continue
        if char in ")]":
            depth -= 1
            index += 1
            continue
        if depth:
            index += 1
            continue
        if region.startswith("->", index):
            index += 2
            continue
        token = None
        if region.startswith(("<<", ">>"), index):
            token = region[index : index + 2]
        elif char in "*/%+-&|^":
            token = char
        if token is None:
            index += 1
            continue
        if not region[start:index].strip():
            # A unary `*`, `&` or `-` opening the operand, not a binary one.
            index += len(token)
            continue
        operands.append((start, index))
        tokens.append((index, token))
        start = index + len(token)
        index += len(token)
    operands.append((start, len(region)))
    return operands, tokens


def _contains_at_top_level(region: str, marker: str) -> bool:
    depth = 0
    index = 0
    while index < len(region):
        char = region[index]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0 and region.startswith(marker, index):
            if marker == "=" and region[index + 1 : index + 2] == "=":
                index += 1
                continue
            return True
        index += 1
    return False


# --------------------------------------------------------------------------
# K -- copy elimination
# --------------------------------------------------------------------------

_COPY_RE = re.compile(
    r"^\s*(?P<target>[A-Za-z_]\w*)\s*=\s*(?P<source>[A-Za-z_]\w*)\s*;\s*$"
)


def copy_family(
    path: str | Path,
    *,
    frozen: tuple[tuple[int, int], ...] = (),
) -> SweepManifest:
    """Emit one variant per removable copy `Y = X;`, rehosting Y's reads on X.

    The shape is mechanically detectable and was worth nine rows in one case
    and fifteen in another: where `X`'s allocated register already matches the
    target at that row and `Y`'s does not, deleting the copy and reading `X`
    hands the target's register to the reads that wanted it.

    A copy is only emitted when the rehosting is provable from the text: `X`
    is not written again while `Y` is still read, `Y` is not written again at
    all, and neither address escapes. Everything else is refused and named.
    """

    raw, code = _read_source(path)
    base_sha = source_sha256(path)
    stem = Path(path).stem
    declared = {item.name: item for item in declarations(code)}
    variants: list[Variant] = []
    dropped: list[dict[str, str]] = []
    space = 0
    for number, text in enumerate(code, 1):
        match = _COPY_RE.match(text)
        if match is None:
            continue
        target, origin = match.group("target"), match.group("source")
        if target not in declared or origin not in declared:
            continue
        space += 1
        site = f"L{number}"
        reason = _copy_refusal(code, target=target, origin=origin, at=number)
        if reason is not None:
            dropped.append({"site": site, "reason": reason})
            continue
        edits = [
            Edit(
                line=number,
                expect=raw[number - 1],
                label=f"drop {target} = {origin}",
            )
        ]
        rehosted: list[int] = []
        for other in range(number + 1, len(code) + 1):
            if not reads(code[other - 1], target):
                continue
            rehosted.append(other)
            edits.append(
                Edit(
                    line=other,
                    expect=raw[other - 1],
                    replace=_rename(raw[other - 1], target, origin),
                    label=f"read {origin} instead of {target}",
                )
            )
        try:
            composed = apply_plan(
                EditPlan(
                    base=Path(path),
                    base_sha256=base_sha,
                    edits=tuple(edits),
                    frozen=frozen,
                    label=site,
                )
            )
        except ComposeError as error:
            dropped.append({"site": site, "reason": str(error).splitlines()[0]})
            continue
        variants.append(
            Variant(
                key=VariantKey(site=site, generator_class="K", carrier=origin),
                filename=f"{stem}.K.{_slug(site)}.{origin}.c",
                text=composed.text,
                description=(
                    f"line {number}: drop {target} = {origin} and read "
                    f"{origin} at {len(rehosted)} later line(s)"
                ),
                detail={
                    "line": number,
                    "target": target,
                    "origin": origin,
                    "rehosted": rehosted,
                },
            )
        )
    if not space:
        raise SweepError(
            f"{path} holds no copy of the form `Y = X;` between two declared locals"
        )
    return SweepManifest(
        generator="copies",
        base=str(path),
        base_sha256=base_sha,
        variants=tuple(variants),
        coverage=SweepCoverage(
            basis="copies of the form Y = X between two declared locals",
            space=space,
            covered=len(variants),
            excluded=len(dropped),
        ),
        dropped=tuple(dropped),
        limits=GENERATOR_LIMITS,
    )


def _copy_refusal(code: list[str], *, target: str, origin: str, at: int) -> str | None:
    if takes_address(code, target) or takes_address(code, origin):
        return f"{target} or {origin} has its address taken; a callee may write it"
    later_reads = [
        number
        for number in range(at + 1, len(code) + 1)
        if reads(code[number - 1], target)
    ]
    later_writes = [
        number
        for number in range(at + 1, len(code) + 1)
        if defines(code[number - 1], target)
    ]
    if later_writes:
        return (
            f"{target} is written again at line {later_writes[0]}, so its later "
            "reads are not all this copy's value"
        )
    if not later_reads:
        return f"nothing reads {target} after line {at}; the copy is already dead"
    origin_writes = [
        number
        for number in range(at + 1, max(later_reads) + 1)
        if defines(code[number - 1], origin)
    ]
    if origin_writes:
        return (
            f"{origin} is written at line {origin_writes[0]}, before "
            f"{target}'s last read at line {max(later_reads)}"
        )
    return None


def _rename(text: str, old: str, new: str) -> str:
    return re.sub(rf"(?<![\w.])(?<!->){re.escape(old)}\b", new, text)


# --------------------------------------------------------------------------
# F -- live-range fusion
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Donor:
    """One fusion candidate, with the live-range fact that decides it."""

    name: str
    declaration_line: int
    declaration_index: int
    type_text: str
    first: int
    last: int
    disjoint: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "declaration_line": self.declaration_line,
            "declaration_index": self.declaration_index,
            "type": self.type_text,
            "live_from": self.first,
            "live_to": self.last,
            "disjoint": self.disjoint,
            "reason": self.reason,
        }


def _live_range(code: list[str], name: str) -> tuple[int, int] | None:
    """First write to last read.

    A bare declaration is not a definition -- `definition_lines` and `reads`
    both already say so -- and counting it would stretch every local's range
    back to the declaration block, where they all overlap and no donor is ever
    fusable.
    """

    touched = set(definition_lines(code, name))
    touched.update(number for number, line in enumerate(code, 1) if reads(line, name))
    if not touched:
        return None
    return min(touched), max(touched)


def fusion_donors(path: str | Path, *, target: str) -> tuple[Donor, ...]:
    """Rank every local by whether its live range avoids the target's.

    This is the half of the donor table that needs no build: a donor whose
    live range overlaps the target's cannot be fused into it, whatever the
    stack traffic says. Pair it with `decomp-workbench slots` for the other
    half -- how many rows touch the donor's slot, which is its price.
    """

    code = _read_source(path)[1]
    declared = {item.name: item for item in declarations(code)}
    if target not in declared:
        raise CSourceError(
            f"{path} does not declare {target!r}; a fusion target must be a "
            "local this file declares"
        )
    span = _live_range(code, target)
    if span is None:
        raise CSourceError(f"nothing in {path} reads or writes {target}")
    low, high = span
    found: list[Donor] = []
    for declaration in declarations(code):
        if declaration.name == target or declaration.is_array:
            continue
        donor_span = _live_range(code, declaration.name)
        if donor_span is None:
            continue
        first, last = donor_span
        if takes_address(code, declaration.name):
            disjoint = False
            reason = "its address is taken; a callee may hold a pointer"
        elif declaration.type_text != declared[target].type_text:
            disjoint, reason = (
                False,
                f"type {declaration.type_text} is not the target's "
                f"{declared[target].type_text}",
            )
        elif last < low:
            disjoint = True
            reason = f"dies at line {last}, before the target lives at {low}"
        elif first > high:
            disjoint = True
            reason = f"lives from line {first}, after the target dies at {high}"
        else:
            disjoint, reason = (
                False,
                f"live {first}..{last} overlaps the target's {low}..{high}",
            )
        found.append(
            Donor(
                name=declaration.name,
                declaration_line=declaration.line,
                declaration_index=declaration.index,
                type_text=declaration.type_text,
                first=first,
                last=last,
                disjoint=disjoint,
                reason=reason,
            )
        )
    found.sort(key=lambda item: (not item.disjoint, item.declaration_index))
    return tuple(found)


def fusion_family(
    path: str | Path,
    *,
    target: str,
    donors: tuple[str, ...] = (),
    frozen: tuple[tuple[int, int], ...] = (),
) -> SweepManifest:
    """Emit one variant per donor fused into the target.

    Fusing means the donor's declaration goes and its occurrences read the
    target instead: two webs become one, and the donor's stack slot is
    reclaimed. Only donors whose live range provably avoids the target's are
    emitted; the rest are named in `dropped` with the overlap that refused
    them.
    """

    raw, code = _read_source(path)
    base_sha = source_sha256(path)
    stem = Path(path).stem
    table = fusion_donors(path, target=target)
    by_name = {item.name: item for item in table}
    wanted = donors or tuple(item.name for item in table if item.disjoint)
    unknown = [name for name in wanted if name not in by_name]
    if unknown:
        raise SweepError(f"{path} declares no fusable local named {', '.join(unknown)}")
    if not wanted:
        raise SweepError(
            f"no local's live range avoids {target}'s in {path}. Run "
            "`decomp-workbench sweep donors` to see each local's range and the "
            "overlap that refused it."
        )
    variants: list[Variant] = []
    dropped: list[dict[str, str]] = []
    for name in wanted:
        donor = by_name[name]
        site = f"{name}->{target}"
        if not donor.disjoint:
            dropped.append({"site": site, "reason": donor.reason})
            continue
        edits: list[Edit] = []
        for number in range(1, len(code) + 1):
            line = code[number - 1]
            if number == donor.declaration_line:
                edits.append(
                    Edit(
                        line=number,
                        expect=raw[number - 1],
                        replace=_drop_declarator(raw[number - 1], name),
                        label=f"drop the declaration of {name}",
                    )
                )
                continue
            if reads(line, name) or defines(line, name):
                edits.append(
                    Edit(
                        line=number,
                        expect=raw[number - 1],
                        replace=_rename(raw[number - 1], name, target),
                        label=f"{name} becomes {target}",
                    )
                )
        try:
            composed = apply_plan(
                EditPlan(
                    base=Path(path),
                    base_sha256=base_sha,
                    edits=tuple(edits),
                    frozen=frozen,
                    label=site,
                )
            )
        except ComposeError as error:
            dropped.append({"site": site, "reason": str(error).splitlines()[0]})
            continue
        variants.append(
            Variant(
                key=VariantKey(site=site, generator_class="F", carrier=target),
                filename=f"{stem}.F.{_slug(name)}.{_slug(target)}.c",
                text=composed.text,
                description=(
                    f"fuse {name} (live {donor.first}..{donor.last}) into "
                    f"{target}: {donor.reason}"
                ),
                detail=donor.as_dict(),
            )
        )
    return SweepManifest(
        generator="fuse",
        base=str(path),
        base_sha256=base_sha,
        variants=tuple(variants),
        coverage=SweepCoverage(
            basis=f"locals whose live range avoids {target}'s",
            space=len(table),
            covered=len(variants),
            excluded=len(table) - len(variants),
        ),
        dropped=tuple(dropped),
        limits=GENERATOR_LIMITS,
    )


def _drop_declarator(text: str, name: str) -> str | None:
    """Remove one declarator from a declaration, or the whole line."""

    stripped = text.strip()
    body = stripped.rstrip(";")
    parts = [item.strip() for item in body.split(",")]
    if len(parts) <= 1:
        return None
    head, _, first = parts[0].rpartition(" ")
    kept = [
        item
        for item in parts
        if re.sub(r"^\**", "", item.split("=")[0].strip()) != name
        and item is not parts[0]
    ]
    if re.sub(r"^\**", "", first.split("=")[0].strip()) == name:
        if not kept:
            return None
        return _indent(text) + head + " " + ", ".join(kept) + ";"
    return _indent(text) + ", ".join([parts[0], *kept]) + ";"


_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text).strip("-") or "x"
