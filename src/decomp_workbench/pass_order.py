"""uopt's pass order on one variable, as a model and as a reader of `cc -S`.

The last fact the Mickey's Speedway USA whale needed (2026-09-16) was a def
that is redundant *before* copy propagation. Nothing instrumented saw it: the
globalcolor profile starts after the passes that decided it. What settled it
was about sixty two-loop mini translation units, each compiled with `cc -S` in
about 50 ms and read line by line, from which six rules came out (L162-L167 on
the IDO 5.3 laws page):

1. dead-store elimination runs first and counts only reads that survive the
   early constant fold, which crosses calls (L162);
2. a read followed by a def of the same variable in its block is not folded
   (L163);
3. the redundant-store pass deletes a store only as its block's first
   reference to the variable (L164);
4. the strength-reduction init fold uses the loop preheader block's own def,
   not propagated knowledge, and a call between that def and the loop kills
   it (L165);
5. a conditional store of a known value is deleted before strength reduction
   (L166);
6. a self-reading def (`i &= 0`) is not a dead-store candidate (L167).

This module makes that method a command. A mini TU marks the statements under
study with `@pass` comments stating the facts a listing cannot show -- which
basic block a statement is in, what role it plays for which variable, whether
its stored value is a known constant. :func:`replay` runs the six rules in
pass order over those statements and names, per statement, the rule that
decides it and the fate it predicts. :func:`observe` reads the `cc -S` listing
(ugen's output, whose `.loc` records say which source line each instruction
came from) and reports what each annotated line actually emitted. A statement
whose observed fate disagrees with the model is reported as unexplained,
because the listing is the measurement and the model is only a model.

What the listing can and cannot show is stated per role. A def's fate is
observable -- its line either emits a store or it does not. A read's fate
(counted or folded) is not observable on its own line, because a counted read
of `i & 0` may emit nothing either way; its effect is the fate of the def it
reads, and that is where the model is checked. The strength-reduction fold is
reported as the loop line's instruction count beside the prediction.

The annotation grammar, one per statement, in a comment on its line::

    i = 0;            /* @pass def i block=184 value=0 */
    x += i & 0;       /* @pass read i block=181 */
    i &= 0;           /* @pass selfdef i block=181 */
    if (c) i = 0;     /* @pass cond i block=183 value=0 */
    h(1);             /* @pass call block=181 */
    do { ... arr[i] } /* @pass loop i block=184 */

`value=` is the stored constant (`?` for a value the fold cannot know; the
default for `def` is `?`). A `loop` statement's `block` is its preheader. The
model reads statements in source order as one path, which is the shape of a
mini TU; it is not a data-flow analysis and is not offered as one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .loc_boundaries import ListingFunction, parse_listing, select_function

__all__ = [
    "PASS_ORDER_SCHEMA",
    "ROLES",
    "RULES",
    "Statement",
    "observe",
    "parse_annotations",
    "pass_order_report",
    "replay",
]

PASS_ORDER_SCHEMA = "decomp-workbench-pass-order-v1"

ROLES = ("def", "read", "selfdef", "cond", "call", "loop")

#: Rule identifiers, the law each is banked as, and the one-line statement.
RULES: dict[str, tuple[str, str]] = {
    "early-fold": (
        "L162",
        "the early constant fold removed this read: the variable's value is a "
        "known constant here, and the fold crosses calls",
    ),
    "dse-no-counted-read": (
        "L162",
        "dead-store elimination deleted this def: no read that survives the "
        "early fold reaches it before the next def",
    ),
    "dse-counted-read": (
        "L162",
        "dead-store elimination kept this def: a counted read reaches it",
    ),
    "read-before-def-in-block": (
        "L163",
        "this read is not folded: a def of the same variable follows it in "
        "its block, so it counts for dead-store elimination",
    ),
    "redundant-first-reference": (
        "L164",
        "the redundant-store pass deleted this store: the variable already "
        "holds the value and this is the block's first reference to it",
    ),
    "redundant-blocked": (
        "L164",
        "the redundant-store pass kept this store: an earlier reference to "
        "the variable in its block makes it not the first",
    ),
    "sr-own-block-def": (
        "L165",
        "the strength-reduction init folds to the bare base: the preheader "
        "block holds its own surviving def of the index",
    ),
    "sr-no-own-block-def": (
        "L165",
        "the strength-reduction init stays base + index*scale: the preheader "
        "block holds no surviving def of its own, whatever is known",
    ),
    "sr-call-kills-fold": (
        "L165",
        "the strength-reduction init stays unfolded: a call sits between the "
        "preheader's def and the loop",
    ),
    "conditional-known-store": (
        "L166",
        "this conditional store of an already-known value is deleted before "
        "strength reduction by the if-body no-op rule, and folds nothing",
    ),
    "self-reading-def": (
        "L167",
        "a self-reading def is not a dead-store candidate: its own read "
        "precedes its def, so it survives dead-store elimination and keeps "
        "the def it reads alive; whether its own store is later emitted is "
        "not decided by the recorded rules",
    ),
    "call-boundary": (
        "L165",
        "a call; between a preheader's def and its loop it kills the "
        "strength-reduction init fold",
    ),
    "live-store": (
        "L164",
        "this store is not redundant: the variable does not already hold its value",
    ),
}

ANNOTATION_RE = re.compile(r"@pass\s+(?P<role>\w+)(?P<rest>[^*\n]*)")
_FIELD_RE = re.compile(r"(\w+)=(\S+)")

#: Fates a listing can decide, by role.
OBSERVABLE = {"def": "store", "cond": "store"}


@dataclass(frozen=True)
class Statement:
    """One annotated statement of a mini TU."""

    line: int
    role: str
    variable: str | None
    block: int
    value: str = "?"
    label: str = ""

    @property
    def known(self) -> bool:
        return self.value != "?"


@dataclass
class Verdict:
    """The model's reading of one statement."""

    statement: Statement
    fate: str
    rule: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        law, sentence = RULES[self.rule]
        return {
            "line": self.statement.line,
            "role": self.statement.role,
            "variable": self.statement.variable,
            "block": self.statement.block,
            "value": self.statement.value,
            "label": self.statement.label or None,
            "predicted": self.fate,
            "rule": self.rule,
            "law": law,
            "because": sentence,
            "notes": list(self.notes),
        }


def parse_annotations(source: str) -> list[Statement]:
    """Read every `@pass` annotation in source order."""

    statements: list[Statement] = []
    for number, line in enumerate(source.splitlines(), 1):
        match = ANNOTATION_RE.search(line)
        if match is None:
            continue
        role = match.group("role")
        if role not in ROLES:
            raise ValueError(
                f"line {number}: unknown @pass role {role!r}; one of "
                + ", ".join(ROLES)
            )
        rest = match.group("rest")
        fields = dict(_FIELD_RE.findall(rest))
        words = [word for word in rest.split() if "=" not in word]
        variable = words[0] if words else None
        if role != "call" and variable is None:
            raise ValueError(f"line {number}: @pass {role} names no variable")
        if "block" not in fields:
            raise ValueError(f"line {number}: @pass {role} needs block=N")
        try:
            block = int(fields["block"], 0)
        except ValueError:
            raise ValueError(f"line {number}: block={fields['block']!r}") from None
        statements.append(
            Statement(
                line=number,
                role=role,
                variable=None if role == "call" else variable,
                block=block,
                value=fields.get("value", "?"),
                label=fields.get("label", ""),
            )
        )
    if not statements:
        raise ValueError(
            "the source carries no @pass annotations; mark each statement "
            "under study, e.g. `i = 0; /* @pass def i block=184 value=0 */`"
        )
    return statements


def _reads(statement: Statement, variable: str) -> bool:
    return statement.variable == variable and statement.role in {
        "read",
        "selfdef",
        "loop",
    }


def _defines(statement: Statement, variable: str) -> bool:
    return statement.variable == variable and statement.role in {
        "def",
        "selfdef",
        "cond",
    }


def replay(statements: Sequence[Statement]) -> list[Verdict]:
    """Run the six rules in pass order and return one verdict per statement.

    Order: the early fold with its read-before-def exception (L162, L163),
    the if-body no-op deletion of known conditional stores (L166),
    dead-store elimination with self-reading defs exempt (L162, L167),
    the strength-reduction init fold (L165), then the redundant-store pass
    (L164).
    """

    ordered = list(statements)
    verdicts: dict[int, Verdict] = {}

    # Known value of each variable along the path, for the early fold.
    known: dict[str, str] = {}
    counted: set[int] = set()
    removed_conditionals: set[int] = set()
    for position, item in enumerate(ordered):
        variable = item.variable
        if variable is None:
            continue
        if item.role == "cond":
            if item.known and known.get(variable) == item.value:
                removed_conditionals.add(position)
                verdicts[position] = Verdict(item, "deleted", "conditional-known-store")
            else:
                known.pop(variable, None)
            continue
        if item.role in {"read", "loop"}:
            if item.role == "read":
                later_def = any(
                    _defines(other, variable) and other.block == item.block
                    for other in ordered[position + 1 :]
                )
                if later_def:
                    counted.add(position)
                    verdicts[position] = Verdict(
                        item, "counted", "read-before-def-in-block"
                    )
                elif variable in known:
                    verdicts[position] = Verdict(item, "folded", "early-fold")
                else:
                    counted.add(position)
                    verdicts[position] = Verdict(item, "counted", "dse-counted-read")
            else:
                counted.add(position)
            continue
        if item.role == "selfdef":
            counted.add(position)  # its own read precedes its def (L163)
            known[variable] = item.value if item.known else known.get(variable, "?")
            if known[variable] == "?":
                known.pop(variable)
            continue
        if item.role == "def":
            if item.known:
                known[variable] = item.value
            else:
                known.pop(variable, None)

    # Dead-store elimination over plain defs.
    surviving: set[int] = set()
    reached_by: dict[int, int] = {}
    for position, item in enumerate(ordered):
        if item.variable is None or position in verdicts:
            continue
        if item.role == "selfdef":
            surviving.add(position)
            verdicts[position] = Verdict(
                item,
                "survives-dse",
                "self-reading-def",
                [
                    "measured both ways: emitted as a zero store in the guard "
                    "block, deleted in a block after a call; the model does "
                    "not choose between them"
                ],
            )
            continue
        if item.role != "def":
            continue
        reached = False
        for later in range(position + 1, len(ordered)):
            other = ordered[later]
            if later in removed_conditionals:
                continue
            if later in counted and _reads(other, item.variable):
                reached = True
                reached_by[position] = other.line
                break
            if other.variable == item.variable and other.role == "def":
                break
        if reached:
            surviving.add(position)
        else:
            verdicts[position] = Verdict(item, "deleted", "dse-no-counted-read")

    # Strength-reduction init fold.
    for position, item in enumerate(ordered):
        if item.role != "loop" or item.variable is None:
            continue
        own = [
            index
            for index in range(position)
            if index in surviving
            and ordered[index].block == item.block
            and ordered[index].variable == item.variable
        ]
        if not own:
            verdicts[position] = Verdict(item, "unfolded-init", "sr-no-own-block-def")
            continue
        last = own[-1]
        if any(
            ordered[index].role == "call" and ordered[index].block == item.block
            for index in range(last + 1, position)
        ):
            verdicts[position] = Verdict(item, "unfolded-init", "sr-call-kills-fold")
        else:
            verdicts[position] = Verdict(item, "folded-init", "sr-own-block-def")

    # Redundant-store pass over surviving plain defs.
    holds: dict[str, str] = {}
    for position, item in enumerate(ordered):
        variable = item.variable
        if variable is None:
            continue
        if position in surviving and item.role == "def":
            redundant = item.known and holds.get(variable) == item.value
            if not redundant:
                verdicts[position] = Verdict(item, "emitted", "live-store")
            else:
                earlier = any(
                    ordered[index].block == item.block
                    and ordered[index].variable == variable
                    for index in range(position)
                    if index not in removed_conditionals
                )
                verdicts[position] = (
                    Verdict(item, "emitted", "redundant-blocked")
                    if earlier
                    else Verdict(item, "deleted", "redundant-first-reference")
                )
        if item.role in {"def", "selfdef"} and (
            position in surviving or item.role == "selfdef"
        ):
            if item.known:
                holds[variable] = item.value
            else:
                holds.pop(variable, None)
        elif item.role == "def" and not item.known:
            holds.pop(variable, None)

    for position, line in reached_by.items():
        verdicts[position].notes.insert(
            0,
            f"kept by dead-store elimination (L162): the counted read at line "
            f"{line} reaches it",
        )
    for position, item in enumerate(ordered):
        if item.role == "call":
            verdicts.setdefault(position, Verdict(item, "call", "call-boundary"))
        elif item.role == "cond":
            verdicts.setdefault(
                position,
                Verdict(
                    item,
                    "emitted",
                    "live-store",
                    [
                        "a conditional store of a value not already known is "
                        "outside the recorded rules; the prediction is the "
                        "default, not a law"
                    ],
                ),
            )
    return [verdicts[index] for index in range(len(ordered)) if index in verdicts]


def observe(
    listing: str, statements: Sequence[Statement], *, symbol: str | None = None
) -> dict[int, int]:
    """Instructions ugen emitted per annotated source line, from `cc -S`."""

    function: ListingFunction = select_function(parse_listing(listing), symbol)
    counts: dict[int, int] = {statement.line: 0 for statement in statements}
    if not any(item.line is not None for item in function.instructions):
        raise ValueError(
            "the listing carries no .loc records, so no instruction can be "
            "attributed to a source line; compile with the project's flags "
            "and -S, and keep the listing ugen wrote"
        )
    for instruction in function.instructions:
        if instruction.line in counts:
            counts[instruction.line] += 1
    return counts


def _observed_fate(role: str, count: int | None) -> str | None:
    if count is None:
        return None
    if role in OBSERVABLE or role == "selfdef":
        return "emitted" if count else "deleted"
    if role == "loop":
        return f"{count} instruction(s)"
    return None


def pass_order_report(
    statements: Sequence[Statement],
    *,
    listing: str | None = None,
    symbol: str | None = None,
    source_name: str | None = None,
    compile_command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Replay the model and, with a listing, check it against what emitted."""

    verdicts = replay(statements)
    counts = observe(listing, statements, symbol=symbol) if listing else None
    rows = []
    unexplained = []
    for verdict in verdicts:
        row = verdict.as_dict()
        count = counts.get(verdict.statement.line) if counts is not None else None
        row["instructions"] = count
        row["observed"] = _observed_fate(verdict.statement.role, count)
        if verdict.statement.role in OBSERVABLE and row["observed"] is not None:
            row["agrees"] = row["observed"] == row["predicted"]
            if not row["agrees"]:
                unexplained.append(verdict.statement.line)
        else:
            row["agrees"] = None
        rows.append(row)
    return {
        "schema": PASS_ORDER_SCHEMA,
        "source": source_name,
        "compile_command": list(compile_command) if compile_command else None,
        "observed": counts is not None,
        "statements": rows,
        "unexplained": unexplained,
        "rules": {
            name: {"law": law, "rule": text} for name, (law, text) in RULES.items()
        },
        "boundary": (
            "The model is six measured rules run in pass order over the "
            "annotated statements as one path; the listing is the measurement. "
            "A def's fate is checked against its line's emitted instructions. "
            "A read's fate is never observable on its own line and is checked "
            "through the def it reads. An unexplained row means the model does "
            "not describe this mini TU, not that the compiler is wrong."
        ),
    }
