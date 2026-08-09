"""Commutative operand order, named as a lever and looked for one row back.

The workbench has always *classified* a swapped commutative pair -- ``add.s
$f4,$f6,$f8`` against ``add.s $f4,$f8,$f6`` counts as ``aligned_commutative``
and the verdict mentions the class. What it never did was say which pair, in
which expression, so the count sat in a screen line for hundreds of builds with
no action attached to it. This module turns the classification into the edit:
the operands, the rows that produced them, and the sentence a reader can act
on.

It also fixes where the classifier looks. IDO canonicalizes ``a + b`` and
``b + a`` to the same arithmetic instruction, so a wrong operand order in the
source frequently does **not** show up on the arithmetic row at all -- that row
is byte-identical -- and surfaces only in the two *operand loads* above it,
whose destination registers are crossed. A classifier that looks only at the
differing row flags the loads as an ordinary register difference and sends the
reader to the allocator for a front-end question. One campaign found the
one-line fix by hand-reading the disassembly; another measured it as worth
fifteen rows.

Two findings are reported, and they are different edits:

``operand-order``
    The arithmetic row itself differs by a swapped source pair.
``operand-load``
    The arithmetic row matches, and the rows that define its two sources are
    crossed. The expression's operand order is still what to change; the row
    that differs is not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CommutativeFinding",
    "OperandDefinition",
    "commutative_findings",
]

#: How far back a definition is looked for. A commutative operand pair is
#: materialized close to its use -- the campaign's case was the immediately
#: preceding two rows -- and an unbounded scan would happily pair an arithmetic
#: row with a load two hundred rows earlier that some intervening branch
#: already invalidated.
DEFINITION_LOOKBACK = 8


@dataclass(frozen=True)
class OperandDefinition:
    """The aligned row that produced one of a commutative pair's sources."""

    register: str
    aligned_row: int
    target: str
    candidate: str
    crossed_with: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "register": self.register,
            "aligned_row": self.aligned_row,
            "target": self.target,
            "candidate": self.candidate,
            "crossed_with": self.crossed_with,
        }


@dataclass(frozen=True)
class CommutativeFinding:
    """One commutative operand pair, with the edit that would fix it."""

    kind: str
    aligned_row: int
    target_row: int | None
    candidate_row: int | None
    opcode: str
    target: str
    candidate: str
    sources: tuple[str, str]
    definitions: tuple[OperandDefinition, ...] = ()

    @property
    def lever(self) -> str:
        left, right = self.sources
        if self.kind == "operand-order":
            return (
                f"swap the two operands of the {self.opcode} at aligned row "
                f"{self.aligned_row}: the target computes it as "
                f"({left} op {right}). This is expression shape -- a compound "
                "assignment or an operand order in the source -- not register "
                "allocation."
            )
        rows = ", ".join(str(item.aligned_row) for item in self.definitions)
        return (
            f"the {self.opcode} at aligned row {self.aligned_row} matches; its "
            f"two operand loads at rows {rows} are crossed. Swap the operand "
            "order of the expression this row computes -- the differing rows "
            "are the symptom, and reallocating them is the wrong repair."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "aligned_row": self.aligned_row,
            "target_row": self.target_row,
            "candidate_row": self.candidate_row,
            "opcode": self.opcode,
            "target": self.target,
            "candidate": self.candidate,
            "sources": list(self.sources),
            "definitions": [item.as_dict() for item in self.definitions],
            "lever": self.lever,
        }


def _source_pair(operands: Sequence[str]) -> tuple[str, str] | None:
    """Return the two interchangeable sources of a commutative instruction.

    Both operand shapes: ``mult rs,rt`` writes ``hi``/``lo`` and has no
    destination operand, while ``or rd,rs,rt`` does.
    """

    if len(operands) == 2:
        return operands[0], operands[1]
    if len(operands) == 3:
        return operands[1], operands[2]
    return None


def commutative_findings(
    rows: Sequence[Any],
) -> tuple[CommutativeFinding, ...]:
    """Return every commutative operand finding in one aligned view.

    ``rows`` are :class:`decomp_workbench.view.AlignedRow` values, in aligned
    order. Reading the alignment rather than raw positions is what lets the
    look-back find the real definition rows on a candidate whose length
    differs from the target's, and ``row.matched`` -- byte identity, decided
    once, in the view -- is what makes "the arithmetic row is clean" a fact
    rather than a re-derivation. Row text is the view's normalized spelling,
    the same one ``aligned_diff_sites`` publishes.
    """

    # Imported here rather than at module scope: `view` and `compare` both
    # read this module's output, and importing either at the top would close
    # the cycle.
    from .compare import COMMUTATIVE_OPCODES, commutative_swap, register_operands
    from .view import destination_register

    findings: list[CommutativeFinding] = []
    for position, row in enumerate(rows):
        target_text = row.target
        candidate_text = row.candidate
        if not target_text or not candidate_text:
            continue
        opcode = target_text.split(maxsplit=1)[0]
        if opcode not in COMMUTATIVE_OPCODES:
            continue
        if candidate_text.split(maxsplit=1)[0] != opcode:
            continue
        target_operands = register_operands(target_text)
        candidate_operands = register_operands(candidate_text)
        sources = _source_pair(target_operands)
        if sources is None:
            continue

        if commutative_swap(opcode, target_operands, candidate_operands):
            findings.append(
                CommutativeFinding(
                    kind="operand-order",
                    aligned_row=row.index,
                    target_row=row.target_index,
                    candidate_row=row.candidate_index,
                    opcode=opcode,
                    target=target_text,
                    candidate=candidate_text,
                    sources=sources,
                )
            )
            continue

        if not row.matched:
            # The row differs for some other reason; a crossed-load reading
            # would be a guess about which difference explains which.
            continue
        definitions = _crossed_definitions(
            rows, position, sources, destination_register
        )
        if definitions:
            findings.append(
                CommutativeFinding(
                    kind="operand-load",
                    aligned_row=row.index,
                    target_row=row.target_index,
                    candidate_row=row.candidate_index,
                    opcode=opcode,
                    target=target_text,
                    candidate=candidate_text,
                    sources=sources,
                    definitions=definitions,
                )
            )
    return tuple(findings)


def _crossed_definitions(
    rows: Sequence[Any],
    position: int,
    sources: tuple[str, str],
    destination_register: Any,
) -> tuple[OperandDefinition, ...]:
    """Return the two definition rows when they are crossed, else nothing.

    "Crossed" means: the row that defines the target's first source defines
    the candidate's *second* source, and vice versa. That is a swapped operand
    order in the source expression, seen one row earlier than the arithmetic
    that consumes it.
    """

    left, right = sources
    if left == right:
        return ()
    found: dict[str, Any] = {}
    start = max(0, position - DEFINITION_LOOKBACK)
    for previous in range(position - 1, start - 1, -1):
        row = rows[previous]
        if not row.target or not row.candidate:
            continue
        defined = destination_register(row.target)
        if defined in (left, right) and defined not in found:
            found[defined] = row
        if len(found) == 2:
            break
    if len(found) != 2:
        return ()

    left_row, right_row = found[left], found[right]
    if destination_register(left_row.candidate) != right:
        return ()
    if destination_register(right_row.candidate) != left:
        return ()
    return (
        OperandDefinition(
            register=left,
            aligned_row=left_row.index,
            target=left_row.target,
            candidate=left_row.candidate,
            crossed_with=right,
        ),
        OperandDefinition(
            register=right,
            aligned_row=right_row.index,
            target=right_row.target,
            candidate=right_row.candidate,
            crossed_with=left,
        ),
    )
