"""Two source-level questions the tooling could not ask, and paid for.

**Are these two reads the same value?** One campaign's closing lever was a
source fact: a local whose address is never taken, read twice with no
intervening definition, is the same value at both reads — so two expressions
spelled differently were provably equal. Five stages searched the register
allocator for a decline that the pass's own arithmetic makes impossible,
while the answer was one `grep` and one brace match. Nothing named the check,
so nobody ran it.

**Where can a statement that emits nothing change the allocation?** A
discarded read — `if (v != 0.0f);` — costs zero instructions and still adds
an occurrence to the symbol's web, which can be exactly what drives the web
memory-resident. It leaves no trace in the object, so a disassembly-driven
search cannot see it; eleven stages of the same campaign did not. Sweeping it
over every statement position found 305 zero-difference candidates out of 999
positions.

Both are **probes**, not proofs, and the reports say so in their own words.
The reasoning is textual and structural: it reads the block structure
(:mod:`decomp_workbench.csource`), not a parsed AST, and every limit is
listed in :data:`EQUALITY_LIMITS` and :data:`DEADREAD_LIMITS` rather than
left for the reader to discover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .csource import (
    CSourceError,
    Statement,
    declaration_line,
    definition_lines,
    identifiers,
    reads,
    scan_statements,
    strip_noncode,
    takes_address,
)

__all__ = [
    "DEADREAD_LIMITS",
    "EQUALITY_LIMITS",
    "SPELLINGS",
    "Spelling",
    "dead_read_report",
    "value_equality_report",
]

EQUALITY_SCHEMA = "decomp-workbench-value-equality-v1"
DEADREAD_SCHEMA = "decomp-workbench-dead-read-v1"

#: What the equality report does not know. Printed with every report, because
#: a reader who takes "same value" for a proof will plan a build on it.
EQUALITY_LIMITS: tuple[str, ...] = (
    "Definitions are found by text: an assignment, a compound assignment, an "
    "increment, or an address-of. A write through a pointer the text does not "
    "spell is not seen.",
    "A callee can only write a local whose address escapes, so the purity "
    "argument is exactly the address-of check -- and it is a whole-file check, "
    "not a per-call one.",
    "`goto` is not followed, and neither is `switch` fallthrough. A label "
    "or a jump inside a range makes textual order stop describing the "
    "control flow, and the range is flagged rather than trusted.",
    "A loop back-edge means a read late in the body and a read early in it are "
    "not one range, even with no definition between them in the text.",
    "Nothing here reads types, so a union member or a pun that reaches the "
    "same storage under another name is a different identifier to this probe.",
)

#: What the dead-read probe does not know.
DEADREAD_LIMITS: tuple[str, ...] = (
    "A candidate is a position where the variable is in scope and structurally "
    "reached by a definition. Whether the construct actually moves the "
    "allocator is measured by building it, not decided here.",
    "Positions inside a loop body are listed separately and never ranked "
    "first: the same construct that costs nothing outside a loop emitted real "
    "code inside one in every case measured.",
    "The spelling table's footprints are one compiler's measurements (IDO 5.3, "
    "one function, 3930 builds). Re-measure them before trusting them on "
    "another compiler.",
    "Insertion is textual, at the start of the named line. A line holding two "
    "statements gets one candidate, at its start.",
)


@dataclass(frozen=True)
class Spelling:
    """One way to spell a discarded read, with what it measured."""

    text: str
    footprint: str
    note: str

    def rendered(self, variable: str) -> str:
        return self.text.replace("V", variable)


#: Measured on IDO 5.3 over 3930 builds of one function. `V` stands in for the
#: variable. The value-guarded forms are the ones to try first: the bare
#: `if (V);` merges with a neighbouring empty-body guard and costs the
#: guard's `bc1f`+`nop` pair, which reads as "the lever cost two instructions"
#: when it is the spelling that cost them.
SPELLINGS: tuple[Spelling, ...] = (
    Spelling("if (V != 0.0f);", "0", "value-guarded; preferred"),
    Spelling("if (V < 0.0f);", "0", "value-guarded"),
    Spelling("if (V > 0.0f);", "0", "value-guarded"),
    Spelling("if (V >= 0.0f);", "0", "value-guarded"),
    Spelling("if (0.0f < V);", "0", "value-guarded, operands reversed"),
    Spelling("if ((s32) V);", "0", "value-guarded through an integer cast"),
    Spelling(
        "if (V);",
        "0 or +2",
        "bare; merges with a neighbouring empty guard and can cost its bc1f+nop pair",
    ),
    Spelling("V;", "0", "INERT: never became an occurrence in any build"),
    Spelling("(void) V;", "0", "INERT"),
    Spelling("V = V;", "0", "INERT: a self-assignment is eliminated"),
    Spelling(
        "V = 0.0f;",
        "0",
        "INERT: a dead store is eliminated before it can be an occurrence "
        "(986 of 999 positions, zero kills)",
    ),
)

#: The spellings worth building first.
GUARDED = tuple(item for item in SPELLINGS if item.note.startswith("value-guarded"))

_CALL_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\s*\(")
_LABEL_RE = re.compile(r"^\s*[A-Za-z_]\w*\s*:\s*(?:$|[^:=])")


def _read_lines(path: str | Path) -> tuple[list[str], list[str]]:
    """Return the file's raw lines and its comment/string-blanked lines."""

    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise CSourceError(f"cannot read {path}: {error}") from None
    if not text.strip():
        raise CSourceError(f"{path} is empty")
    return text.splitlines(), strip_noncode(text)


def _require_variable(code: list[str], variable: str) -> tuple[int | None, list[int]]:
    declared = declaration_line(code, variable)
    written = definition_lines(code, variable)
    mentioned = any(variable in identifiers(line) for line in code)
    if not mentioned:
        raise CSourceError(
            f"no line mentions {variable!r}. This probe reasons about a local "
            "this file declares; check the spelling, and remember that a "
            "struct or union member is a different identifier to it."
        )
    return declared, written


def value_equality_report(
    path: str | Path,
    *,
    variable: str,
    positions: tuple[int, ...] = (),
) -> dict[str, Any]:
    """Report the ranges over which every read of `variable` is one value.

    The argument, stated once: a local whose address never escapes cannot be
    written by a callee, so between two of its definitions its value is fixed,
    and every read in that span reads the same value. Two expressions built
    from reads in one span are equal whatever they are spelled.
    """

    _raw, code = _read_lines(path)
    declared, written = _require_variable(code, variable)
    escapes = takes_address(code, variable)
    statements = scan_statements(code)
    by_line = {item.line: item for item in statements}
    read_lines = [
        number
        for number, line in enumerate(code, 1)
        if reads(line, variable) and number not in written
    ]
    labels = [
        number
        for number, line in enumerate(code, 1)
        if _LABEL_RE.match(line) or line.strip().startswith("goto ")
    ]

    boundaries = sorted(set(written))
    ranges: list[dict[str, Any]] = []
    for index, start in enumerate(boundaries):
        end = boundaries[index + 1] - 1 if index + 1 < len(boundaries) else len(code)
        members = [number for number in read_lines if start <= number <= end]
        loops = sorted(
            {
                loop
                for number in members
                for loop in (by_line[number].loops if number in by_line else ())
            }
        )
        crossing = [number for number in labels if start <= number <= end]
        ranges.append(
            {
                "index": index + 1,
                "defined_at": start,
                "first_line": start,
                "last_line": end,
                "reads": members,
                "read_count": len(members),
                "loops": loops,
                "control_breaks": crossing,
                "single_valued": not crossing and not loops,
            }
        )

    calls = sorted(
        {
            name
            for number, line in enumerate(code, 1)
            for name in _CALL_RE.findall(line)
            if name not in {"if", "for", "while", "switch", "return", "sizeof"}
        }
    )
    report: dict[str, Any] = {
        "schema": EQUALITY_SCHEMA,
        "source": str(path),
        "variable": variable,
        "declared_at": declared,
        "definitions": boundaries,
        "reads": read_lines,
        "address_taken_at": escapes,
        "callee_safe": not escapes,
        "callee_safe_reason": (
            f"{variable}'s address is never taken in this file, so no callee "
            "can write it: a call between two reads cannot have changed the "
            "value"
            if not escapes
            else f"{variable}'s address is taken at line(s) "
            + ", ".join(str(item) for item in escapes)
            + ", so a callee may write it and no range below is a claim about "
            "calls"
        ),
        "called_functions": calls,
        "ranges": ranges,
        "limits": list(EQUALITY_LIMITS),
    }
    if positions:
        report["pairs"] = _pairs(
            positions, ranges=ranges, by_line=by_line, report=report
        )
    return report


def _range_of(line: int, ranges: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in ranges:
        if item["first_line"] <= line <= item["last_line"]:
            return item
    return None


def _pairs(
    positions: tuple[int, ...],
    *,
    ranges: list[dict[str, Any]],
    by_line: dict[int, Statement],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Answer the pairwise question the campaign actually asked."""

    results: list[dict[str, Any]] = []
    ordered = sorted(set(positions))
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            left, right = _range_of(first, ranges), _range_of(second, ranges)
            reasons: list[str] = []
            same = left is not None and right is not None and left is right
            if left is None or right is None:
                reasons.append(
                    "one of the lines is before the variable's first "
                    "definition, so it has no value to compare"
                )
            elif not same:
                reasons.append(
                    f"a definition at line {right['defined_at']} sits between "
                    "them, so the second read is a different value"
                )
            if same and not report["callee_safe"]:
                same = False
                reasons.append(report["callee_safe_reason"])
            if same and left is not None and left["control_breaks"]:
                same = False
                reasons.append(
                    "a label or goto between them means textual order does "
                    "not describe the control flow here"
                )
            if same and left is not None and left["loops"]:
                loops_between = {
                    loop
                    for line in (first, second)
                    if line in by_line
                    for loop in by_line[line].loops
                }
                if loops_between:
                    same = False
                    reasons.append(
                        "both reads are inside a loop body, so a back-edge "
                        "can carry a definition between them"
                    )
            results.append(
                {
                    "lines": [first, second],
                    "same_value": same,
                    "verdict": "SAME-VALUE" if same else "NOT-PROVEN",
                    "reasons": reasons
                    or [
                        "no definition between them, and no callee can write "
                        "a local whose address never escapes"
                    ],
                }
            )
    return results


#: How much of the file a candidate position may come from.
#:
#: ``dominating`` keeps only positions a definition structurally reaches, so
#: the inserted read is a read of a value the program really assigned.
#: ``textual`` keeps every position after the first definition line, which is
#: what the campaign's own sweep did -- and it found kills at positions where
#: the definition sits in a branch that has since closed. Those are still
#: zero-footprint allocator probes, but the read is not a value-safe edit, so
#: the wider set is opt-in and each such row is marked.
REACH_MODES = ("dominating", "textual")


def dead_read_report(
    path: str | Path,
    *,
    variable: str,
    spellings: tuple[Spelling, ...] = GUARDED,
    limit: int | None = None,
    reach: str = "dominating",
) -> dict[str, Any]:
    """List the positions where a zero-footprint discarded read can be tried."""

    if reach not in REACH_MODES:
        raise CSourceError(
            f"unknown reach {reach!r}; choose {' or '.join(REACH_MODES)}"
        )

    raw, code = _read_lines(path)
    declared, written = _require_variable(code, variable)
    if not written:
        raise CSourceError(
            f"no line in {path} assigns {variable}. A discarded read only "
            "creates an occurrence where the variable already holds a value; "
            "at a position no definition reaches, there is nothing to read."
        )
    statements = scan_statements(code)
    by_line = {item.line: item for item in statements}
    definitions = [by_line[number] for number in written if number in by_line]

    candidates: list[dict[str, Any]] = []
    excluded = {"before-any-definition": 0, "not-a-statement": 0, "on-a-definition": 0}
    for item in statements:
        if item.line in written:
            excluded["on-a-definition"] += 1
            continue
        if not _is_statement_position(item):
            excluded["not-a-statement"] += 1
            continue
        reaching = [
            definition.line
            for definition in definitions
            if item.reached_from(definition)
        ]
        earlier = [number for number in written if number < item.line]
        if not reaching and (reach == "dominating" or not earlier):
            excluded["before-any-definition"] += 1
            continue
        candidates.append(
            {
                "line": item.line,
                "depth": item.depth,
                "in_loop": item.in_loop,
                "reached_by": reaching or earlier,
                "dominated": bool(reaching),
                "before": item.text,
                "raw": raw[item.line - 1] if item.line <= len(raw) else "",
            }
        )

    # Outside a loop first: the same construct emitted real code inside one in
    # every case measured, so a ranked list that mixes them mixes a free
    # experiment with an expensive one.
    candidates.sort(
        key=lambda item: (item["in_loop"], not item["dominated"], item["line"])
    )
    shown = candidates if limit is None else candidates[:limit]
    for entry in shown:
        source_line = str(entry["raw"])
        indent = source_line[: len(source_line) - len(source_line.lstrip())]
        entry["patches"] = [
            {
                "spelling": spelling.text,
                "insert": indent + spelling.rendered(variable),
                "footprint": spelling.footprint,
            }
            for spelling in spellings
        ]
    return {
        "schema": DEADREAD_SCHEMA,
        "source": str(path),
        "variable": variable,
        "declared_at": declared,
        "definitions": written,
        "statement_positions": len(statements),
        "reach": reach,
        "candidate_count": len(candidates),
        "loop_free_count": sum(1 for item in candidates if not item["in_loop"]),
        "dominated_count": sum(1 for item in candidates if item["dominated"]),
        "excluded": excluded,
        "candidates": shown,
        "spellings": [
            {"spelling": item.text, "footprint": item.footprint, "note": item.note}
            for item in SPELLINGS
        ],
        "limits": list(DEADREAD_LIMITS),
    }


def _is_statement_position(item: Statement) -> bool:
    """Whether a statement can be inserted before this line.

    A brace, a label, an `else`, and a preprocessor line are all positions
    where inserting a statement changes the program's structure rather than
    adding to it.
    """

    text = item.text
    if not text or text.startswith(("#", "}", "{")):
        return False
    if text.startswith(("else", "case ", "default:")):
        return False
    if _LABEL_RE.match(text):
        return False
    # A `for`/`while`/`if` header without a brace owns the next line as its
    # body; inserting before that line would steal the body.
    return not text.endswith((",", "\\"))


def write_variants(
    report: dict[str, Any],
    *,
    directory: str | Path,
    spelling: str,
    variable: str,
    source: str | Path,
) -> list[dict[str, str]]:
    """Write one variant source per candidate, inserting the named spelling.

    The workbench does not own this project's build, so it stops here: one
    file per candidate, named by the line it edits, ready for whatever sweep
    driver the project already has.
    """

    chosen = next((item for item in SPELLINGS if item.text == spelling), None)
    if chosen is None:
        known = ", ".join(item.text for item in SPELLINGS)
        raise CSourceError(f"unknown spelling {spelling!r}; choose one of: {known}")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    lines = Path(source).read_text(encoding="utf-8").splitlines(keepends=True)
    written: list[dict[str, str]] = []
    stem = Path(source).stem
    for item in report["candidates"]:
        number = int(item["line"])
        indent = item["raw"][: len(item["raw"]) - len(item["raw"].lstrip())]
        body = list(lines)
        body.insert(number - 1, f"{indent}{chosen.rendered(variable)}\n")
        out = target / f"{stem}.L{number}.c"
        out.write_text("".join(body), encoding="utf-8")
        written.append({"line": str(number), "path": str(out)})
    return written
