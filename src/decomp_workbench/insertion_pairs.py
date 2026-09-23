"""Which IR construct emitted the extra word: the insertion-pair reader.

Every colour instrument in this package moves a register and never an
instruction, so a function four, eight or twelve bytes off its target was
routinely handed to a lane that could not move it. On such a function the
positional masked count is mostly shadow: one extra word shifts every word
after it until a missing word shifts them back (L155). The question the delta
asks is not "which colour" but "which word is extra or missing, and what in
our source emitted it". This module answers that from the two instruction
streams, an optional line table and an optional ugen trace.

What it measures, all from one alignment (the same `difflib` edit script
``align`` prints, so offsets agree with it by construction):

* **Pairs.** A pair opens at the first one-sided word after an index-aligned
  stretch and closes where the running shift (candidate-only minus
  target-only) is back to zero; one that never closes runs to the end. Two
  shifts that touch are two pairs.
* **Shadow**, per pair: positional differing rows inside the pair minus the
  aligned disagreement inside it (one-sided words plus paired rows that really
  differ). Outside every pair the streams are index-aligned, so there the two
  counts are equal by construction and the reader checks that they are
  (``outside_agrees``). ``aligned_after_shadow`` -- positional less every
  pair's shadow -- is the number of words a lane actually has to change, and
  the number a size-mismatch function should be ranked by.
* **Class** of each one-sided word from its encoding: move, stack-load,
  stack-store, load, store, alu, const, branch, call, frame, delay-nop, nop or
  other. Classes and offsets only; no instruction text is ever emitted.
* **Owner**: the source line from the candidate's own line table (objdump
  ``-l``), then the ugen construct that emitted a compatible word on that line,
  read from ``DKWB-EMIT-V1`` records under their ``DKWB-CALL`` stack. Every
  owner states its ``basis``: ``line``, ``prologue``, ``nearest`` (within
  three lines), ``as1`` (a nop), ``isa`` (an ISA hazard slot, never a source
  line), or ``neighbour`` for a target-only word placed only by the candidate
  line beside it -- the weakest.
* **Label** per word and per pair from a fixed vocabulary, a rule over class
  and owner (``missing-CSE``, ``spill/reload``, ...).

What it cannot do: it reads *our* compile. The target has no trace and no line
table, so a target-only word is owned by what our code does beside it. A label
names the word and the line, not the spelling that removes it.
"""

from __future__ import annotations

import collections
import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from .emit_provenance import DIRECTIVE_FUNCTIONS
from .model import Instruction
from .shift_align import ALIGNMENT_GRANULARITIES, DEFAULT_GRANULARITY, alignment_key

__all__ = [
    "CLASSES",
    "EDIT_KINDS",
    "GENERIC_LABELS",
    "LABELS",
    "PAIRS_CENSUS_SCHEMA",
    "PAIRS_SCHEMA",
    "SPECIFIC_LABELS",
    "LineTable",
    "Step",
    "TraceProcedure",
    "analyse_pairs",
    "census_rows",
    "classify_word",
    "edit_script",
    "pair_lines",
    "pairs_from_script",
    "parse_line_table",
    "parse_owner_trace",
    "summarise",
]

PAIRS_SCHEMA = "decomp-workbench-insertion-pairs-v1"
PAIRS_CENSUS_SCHEMA = "decomp-workbench-insertion-pairs-census-v1"
EVIDENCE = "diagnostic-insertion-pairs"

SP = 29
RA = 31
ARGUMENT_REGISTERS = (4, 5, 6, 7)
ARGUMENT_NAMES = {4: "a0", 5: "a1", 6: "a2", 7: "a3"}

# --------------------------------------------------------------------------
# Word classes, from opcode fields only.
# --------------------------------------------------------------------------

LOAD_OPS = frozenset({0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x31, 0x35, 0x37})
STORE_OPS = frozenset({0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x39, 0x3D, 0x3F})
BRANCH_OPS = frozenset({0x01, 0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17})
OP_SPECIAL, OP_JUMP, OP_CALL, OP_COP1 = 0x00, 0x02, 0x03, 0x11
OP_ADD_IMM, OP_ADD_IMM_U, OP_OR_IMM, OP_UPPER = 0x08, 0x09, 0x0D, 0x0F
FN_JR, FN_JALR = 0x08, 0x09
FN_ADD, FN_ADDU, FN_OR = 0x20, 0x21, 0x25
COP1_MFC1, COP1_MTC1, COP1_BRANCH = 0x00, 0x04, 0x08
COP1_FMT_S, COP1_FMT_D = 0x10, 0x11
COP1_FN_MOV = 0x06

CLASSES = (
    "move",
    "stack-load",
    "stack-store",
    "load",
    "store",
    "alu",
    "const",
    "branch",
    "call",
    "frame",
    "delay-nop",
    "nop",
    "other",
)


def _fields(word: int) -> tuple[int, int, int, int, int]:
    return (
        (word >> 26) & 0x3F,
        (word >> 21) & 0x1F,
        (word >> 16) & 0x1F,
        (word >> 11) & 0x1F,
        word & 0x3F,
    )


def is_control_transfer(word: int) -> bool:
    """A word with a delay slot after it."""

    op, rs, _rt, _rd, funct = _fields(word)
    if op in BRANCH_OPS or op in (OP_JUMP, OP_CALL):
        return True
    if op == OP_SPECIAL and funct in (FN_JR, FN_JALR):
        return True
    return op == OP_COP1 and rs == COP1_BRANCH


def is_call(word: int) -> bool:
    op, _rs, _rt, _rd, funct = _fields(word)
    return op == OP_CALL or (op == OP_SPECIAL and funct == FN_JALR)


def is_fp_compare(word: int) -> bool:
    """`c.cond.s` / `c.cond.d`: COP1, single or double format, funct 0x30-0x3F."""

    op, rs, _rt, _rd, funct = _fields(word)
    return op == OP_COP1 and rs in (COP1_FMT_S, COP1_FMT_D) and funct >= 0x30


def is_fp_branch(word: int) -> bool:
    op, rs, _rt, _rd, _funct = _fields(word)
    return op == OP_COP1 and rs == COP1_BRANCH


def classify_word(word: int, previous: int | None = None) -> str:
    """One of :data:`CLASSES` for one encoded word; `previous` decides delay-nop."""

    if word == 0:
        if previous is not None and is_control_transfer(previous):
            return "delay-nop"
        return "nop"
    op, rs, rt, rd, funct = _fields(word)
    if op in LOAD_OPS:
        return "stack-load" if rs == SP else "load"
    if op in STORE_OPS:
        return "stack-store" if rs == SP else "store"
    if op in BRANCH_OPS or op == OP_JUMP:
        return "branch"
    if op == OP_CALL:
        return "call"
    if op == OP_SPECIAL:
        if funct == FN_JR:
            return "frame" if rs == RA else "branch"
        if funct == FN_JALR:
            return "call"
        if funct in (FN_ADD, FN_ADDU, FN_OR) and rd and (rs == 0 or rt == 0):
            return "move"
        return "alu"
    if op in (OP_ADD_IMM, OP_ADD_IMM_U):
        if rs == SP and rt == SP:
            return "frame"
        return "const" if rs == 0 else "alu"
    if op == OP_UPPER or (op == OP_OR_IMM and rs == 0):
        return "const"
    if 0x0A <= op <= 0x0E:
        return "alu"
    if op == OP_COP1:
        if rs == COP1_BRANCH:
            return "branch"
        if rs in (COP1_MFC1, COP1_MTC1):
            return "move"
        if rs >= 0x10 and funct == COP1_FN_MOV:
            return "move"
        return "alu"
    return "other"


def destination(word: int) -> int | None:
    """The general-purpose register a word writes, when it writes one."""

    op, rs, rt, rd, funct = _fields(word)
    if word == 0:
        return None
    if op == OP_SPECIAL:
        if funct in (FN_JR, 0x18, 0x19, 0x1A, 0x1B):  # jr, mult*, div*
            return None
        if funct == FN_JALR:
            return rd
        return rd or None
    if op in LOAD_OPS and op not in (0x31, 0x35):  # lwc1/ldc1 write an FPR
        return rt or None
    if op in (OP_ADD_IMM, OP_ADD_IMM_U, OP_UPPER) or 0x0A <= op <= 0x0E:
        return rt or None
    if op == OP_COP1 and rs == COP1_MFC1:
        return rt or None
    return None


def sources(word: int) -> frozenset[int]:
    """The general-purpose registers a word reads (zero excluded)."""

    op, rs, rt, _rd, funct = _fields(word)
    read: set[int] = set()
    if op == OP_SPECIAL:
        if funct in (0x00, 0x02, 0x03):  # shifts by immediate read rt only
            read.add(rt)
        else:
            read.update((rs, rt))
    elif op in STORE_OPS:
        read.update((rs, rt) if op not in (0x39, 0x3D) else (rs,))
    elif op in BRANCH_OPS:
        read.update((rs, rt) if op in (0x04, 0x05, 0x14, 0x15) else (rs,))
    elif op in LOAD_OPS or op in (OP_ADD_IMM, OP_ADD_IMM_U) or 0x0A <= op <= 0x0E:
        read.add(rs)
    elif op == OP_COP1 and rs == COP1_MTC1:
        read.add(rt)
    read.discard(0)
    return frozenset(read)


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def stack_offset(word: int) -> int | None:
    """The `$sp`-relative offset of a stack load or store."""

    op, rs, _rt, _rd, _funct = _fields(word)
    if rs == SP and (op in LOAD_OPS or op in STORE_OPS):
        return _signed16(word)
    return None


def frame_size(words: Sequence[int]) -> int:
    """The frame the first `addiu sp,sp,-N` allocates; 0 for a frameless body."""

    for word in words:
        op, rs, rt, _rd, _funct = _fields(word)
        if op in (OP_ADD_IMM, OP_ADD_IMM_U) and rs == SP and rt == SP:
            immediate = _signed16(word)
            if immediate < 0:
                return -immediate
    return 0


def branch_target_rows(words: Sequence[int]) -> frozenset[int]:
    """Rows a local PC-relative branch in this stream lands on."""

    targets: set[int] = set()
    for row, word in enumerate(words):
        op, rs, _rt, _rd, _funct = _fields(word)
        if op in BRANCH_OPS or (op == OP_COP1 and rs == COP1_BRANCH):
            targets.add(row + 1 + _signed16(word))
    return frozenset(targets)


def _register_erased(word: int) -> int:
    op = (word >> 26) & 0x3F
    if op == OP_SPECIAL:
        return word & ~(0x1F << 21 | 0x1F << 16 | 0x1F << 11)
    if op == OP_COP1:
        return word & ~(0x1F << 16 | 0x1F << 11 | 0x1F << 6)
    if op in (OP_JUMP, OP_CALL):
        return word
    return word & ~(0x1F << 21 | 0x1F << 16)


def _immediate_erased(word: int) -> int:
    op = (word >> 26) & 0x3F
    if op == OP_SPECIAL:
        return word & ~(0x1F << 6)
    if op in (OP_JUMP, OP_CALL):
        return word & ~0x03FFFFFF
    if op == OP_COP1:
        return word
    return word & ~0xFFFF


# --------------------------------------------------------------------------
# The edit script and the pairs.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One row of the word-level edit script.

    ``op`` is ``equal`` or ``replace`` for a paired row, ``candidate`` for a
    word only the candidate has, ``target`` for one only the target has.
    """

    op: str
    candidate: int | None
    target: int | None

    @property
    def one_sided(self) -> bool:
        return self.op in ("candidate", "target")


def edit_script(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    granularity: str = DEFAULT_GRANULARITY,
) -> list[Step]:
    """Expand `align`'s block edit script into one step per word.

    A ``replace`` block of unequal length pairs its rows positionally as far
    as the shorter side reaches -- the rule `align`'s row pairing uses -- and
    the rest of the longer side is one-sided.
    """

    if granularity not in ALIGNMENT_GRANULARITIES:
        raise ValueError(
            f"unknown alignment granularity {granularity!r}; expected one of "
            + ", ".join(ALIGNMENT_GRANULARITIES)
        )
    matcher = difflib.SequenceMatcher(
        a=[alignment_key(item, granularity=granularity) for item in target],
        b=[alignment_key(item, granularity=granularity) for item in candidate],
        autojunk=False,
    )
    steps: list[Step] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            steps.extend(Step("equal", j1 + k, i1 + k) for k in range(i2 - i1))
            continue
        span = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        steps.extend(Step("replace", j1 + k, i1 + k) for k in range(span))
        steps.extend(Step("target", None, i) for i in range(i1 + span, i2))
        steps.extend(Step("candidate", j, None) for j in range(j1 + span, j2))
    return steps


@dataclass
class Pair:
    """One run of index misalignment between the two streams."""

    lo: int
    hi: int | None = None
    closed: bool = False
    steps: list[int] = field(default_factory=list)
    positional_in: int = 0
    aligned_in: int = 0
    naming_in: int = 0
    shadow: int = 0
    span_words: int = 0
    words: list[dict[str, Any]] = field(default_factory=list)
    label: str = "unowned"


def pairs_from_script(script: Sequence[Step]) -> list[Pair]:
    """Group one-sided words into pairs of index misalignment.

    ``lo``/``hi`` are positional indices: the compared range whose two words
    are not each other's alignment partners. ``hi`` is None for a pair that
    runs to the end.
    """

    pairs: list[Pair] = []
    shift = 0
    current: Pair | None = None
    for index, step in enumerate(script):
        if step.one_sided:
            position = step.candidate if step.op == "candidate" else step.target
            assert position is not None
            if current is None:
                # Index-aligned up to here, so both sides sit at `position`.
                current = Pair(lo=position)
                pairs.append(current)
            shift += 1 if step.op == "candidate" else -1
            current.steps.append(index)
            if shift == 0:
                # Aligned again from the next word; a further one-sided word
                # right here opens a NEW pair.
                current.hi = position + 1
                current.closed = True
                current = None
        elif current is not None:
            current.steps.append(index)
    return pairs


# --------------------------------------------------------------------------
# Line table and ugen trace.
# --------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"^\s*([0-9a-fA-F]+):\s")
_LINE_RE = re.compile(r"^(\S[^:]*):(\d+)(?: \(discriminator \d+\))?\s*$")
_SYMBOL_RE = re.compile(r"^\s*[0-9a-fA-F]+\s+<(?P<name>[^>]+)>:\s*$")


@dataclass(frozen=True)
class LineTable:
    """Function-relative byte offset to source line, from `objdump -d -l`.

    A line from a file other than :attr:`source` is kept as ``name:line`` so
    it is never matched against the translation unit's own lines.
    """

    source: str | None
    lines: Mapping[int, int | str]

    @property
    def own_lines(self) -> tuple[int, ...]:
        return tuple(sorted({v for v in self.lines.values() if isinstance(v, int)}))

    @property
    def bounds(self) -> tuple[int, int] | None:
        own = self.own_lines
        return (own[0], own[-1]) if own else None


def parse_line_table(
    text: str,
    *,
    symbol: str | None = None,
    start: int | None = None,
    source: str | None = None,
) -> LineTable:
    """Read the ``file:line`` headers `objdump -d -l` interleaves.

    Only the address column and the headers are read; instruction text is
    never kept. Offsets are relative to ``start`` when given, else to the
    first address under ``symbol``'s header (or the first address at all).
    ``source`` names the translation unit; without it the file owning the
    most addresses is taken as the unit, and the choice is reported.
    """

    raw: list[tuple[int, str, int]] = []
    current: tuple[str, int] | None = None
    inside = symbol is None
    for line in text.splitlines():
        header = _SYMBOL_RE.match(line)
        if header is not None:
            inside = symbol is None or header.group("name") == symbol
            continue
        match = _LINE_RE.match(line)
        if match is not None:
            current = (PurePath(match.group(1)).name, int(match.group(2)))
            continue
        address = _ADDRESS_RE.match(line)
        if address is None or not inside or current is None:
            continue
        if "R_MIPS" in line:
            continue
        raw.append((int(address.group(1), 16), current[0], current[1]))
    if not raw:
        return LineTable(source=source, lines={})
    origin = start if start is not None else raw[0][0]
    unit = PurePath(source).name if source else None
    if unit is None:
        counts = collections.Counter(name for _address, name, _line in raw)
        unit = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    table: dict[int, int | str] = {}
    for location, name, number in raw:
        if location < origin:
            continue
        table[location - origin] = number if name == unit else f"{name}:{number}"
    return LineTable(source=unit, lines=table)


_FIELD_RE = re.compile(r"(\w+)=(\S+)")
_EXTRA_DIRECTIVES = frozenset(
    {"f_demit_dir0", "f_demit_dir1", "f_demit_dir2", "f_demit_mask", "f_demit_frame"}
)
_MEMORY_PARENTS = frozenset({"f_iloadistore", "f_loadstore", "f_unaligned_loadstore"})


def emitter_family(fn: str, stack: Sequence[str]) -> str | None:
    """Instruction family of one ugen emission, or None for a directive."""

    if fn in DIRECTIVE_FUNCTIONS or fn in _EXTRA_DIRECTIVES:
        return None
    frames = set(stack)
    if "f_gen_reg_save_restore" in frames:
        return "save"
    if "f_gen_entry_exit" in frames:
        return "frame"
    if frames & _MEMORY_PARENTS or fn in ("f_emit_rab", "f_emit_rob", "f_demit_rob_"):
        return "memory"
    if fn in (
        "f_emit_rill",
        "f_emit_rrll",
        "f_emit_ll",
        "f_emit_rllb",
        "f_emit_branch_rrll",
        "f_emit_branch_rill",
    ):
        return "branch"
    if fn == "f_emit_a":
        return "call"
    if fn in ("f_emit_ri_", "f_emit_ra", "f_emit_rfi"):
        return "const"
    if fn == "f_emit_rr" and "f_move_to_dest" in frames:
        return "move"
    return "alu"


def handler_of(stack: Sequence[str]) -> str:
    """The innermost frame that is not an emitter: the ugen construct."""

    for frame in reversed(stack):
        if frame.startswith(("f_emit", "f_demit", "f_dw_emit")):
            continue
        return frame[2:] if frame.startswith("f_") else frame
    return "unknown"


@dataclass
class TraceProcedure:
    """One procedure's instruction emissions, keyed by source line."""

    index: int
    emits: dict[int, list[dict[str, str]]] = field(default_factory=dict)

    def emissions(self) -> int:
        return sum(len(rows) for rows in self.emits.values())


def parse_owner_trace(text: str) -> dict[int, TraceProcedure]:
    """Per procedure: ugen's instruction emissions, keyed by line.

    Reads ``DKWB-EMIT-V1`` records under the ``DKWB-CALL`` stack the ugen
    profile prints around them. Emissions sharing one ``(block, emit)`` index
    are one instruction written through a wrapper; only the first is kept.
    Backward-buffer records are data, not instructions, and are skipped.
    Unrelated lines are ignored, so a raw compiler stderr can be passed.
    """

    procedures: dict[int, TraceProcedure] = {}
    seen: set[tuple[int, str | None, str | None]] = set()
    stack: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("DKWB-CALL "):
            parts = raw.split()
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            depth = int(parts[1])
            del stack[max(depth - 1, 0) :]
            if parts[2] == ">" and len(parts) > 3:
                stack.append(parts[3])
            continue
        if "DKWB-EMIT-V1" not in raw:
            continue
        fields = dict(_FIELD_RE.findall(raw))
        if fields.get("buffer", "fwd") != "fwd":
            continue
        family = emitter_family(fields.get("fn", ""), stack)
        if family is None:
            continue
        try:
            index = int(fields.get("proc", "-1"))
            line = int(fields.get("line", "-1"))
        except ValueError:
            continue
        key = (index, fields.get("block"), fields.get("emit"))
        if key in seen:
            continue
        seen.add(key)
        procedure = procedures.setdefault(index, TraceProcedure(index=index))
        procedure.emits.setdefault(line, []).append(
            {"family": family, "handler": handler_of(stack)}
        )
    return procedures


def pick_procedure(
    procedures: Mapping[int, TraceProcedure], lines: Iterable[int]
) -> tuple[int | None, str]:
    """The procedure whose emissions fall on this function's lines.

    The trace's ordinal carries no name, so it is matched by line: the
    procedure with the most emissions inside the function's line bounds,
    strictly more than any other. A tie is ambiguity, reported, not guessed.
    """

    own = sorted(set(lines))
    if not own:
        return None, "no line table for this function"
    low, high = own[0], own[-1]
    scores = sorted(
        (
            (
                sum(
                    len(rows)
                    for line, rows in procedure.emits.items()
                    if low <= line <= high
                ),
                index,
            )
            for index, procedure in procedures.items()
        ),
        reverse=True,
    )
    scores = [item for item in scores if item[0]]
    if not scores:
        return None, "no traced procedure emits on this function's lines"
    if len(scores) > 1 and scores[0][0] == scores[1][0]:
        return None, "two traced procedures tie on this function's lines"
    return scores[0][1], "matched by line"


COMPATIBLE: dict[str, frozenset[str]] = {
    "move": frozenset({"move", "alu"}),
    "stack-load": frozenset({"memory", "save", "frame"}),
    "stack-store": frozenset({"memory", "save", "frame"}),
    "load": frozenset({"memory"}),
    "store": frozenset({"memory"}),
    "alu": frozenset({"alu", "move", "const"}),
    "const": frozenset({"const", "memory", "alu", "call"}),
    "branch": frozenset({"branch"}),
    "call": frozenset({"call"}),
    "frame": frozenset({"frame", "save"}),
    "other": frozenset(
        {"alu", "memory", "move", "const", "branch", "call", "frame", "save"}
    ),
}

NEAREST_LINES = 3


def _construct(rows: Sequence[Mapping[str, str]]) -> tuple[str, int]:
    handlers = collections.Counter(row["handler"] for row in rows)
    return sorted(handlers.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def own(
    word_class: str,
    line: int | str | None,
    procedure: TraceProcedure | None,
    bounds: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Owner of one one-sided word: a line plus a construct, or unowned.

    Tried in order, and the one that answered is ``basis``: ``as1`` for a
    nop; ``line`` for a compatible emission on the word's own line;
    ``prologue`` for a stack or frame word on the function's first or last
    line (ugen emits the prologue at the procedure's end, so the trace stamps
    it with the last line while the line table puts it on the first);
    ``nearest`` for one within :data:`NEAREST_LINES` lines, nearest first.
    """

    def unowned(reason: str) -> dict[str, Any]:
        return {
            "owned": False,
            "line": line,
            "construct": None,
            "basis": None,
            "reason": reason,
        }

    if line is None:
        return unowned("no line")
    if word_class in ("nop", "delay-nop"):
        return {
            "owned": True,
            "line": line,
            "construct": "as1",
            "basis": "as1",
            "reason": "assembler fill",
        }
    if not isinstance(line, int):
        return unowned("line outside the translation unit's source")
    if procedure is None:
        return {**unowned("no trace"), "line": line}

    def compatible(at: int) -> list[dict[str, str]]:
        return [
            row
            for row in procedure.emits.get(at, [])
            if row["family"] in COMPATIBLE[word_class]
        ]

    def owned(
        rows: Sequence[Mapping[str, str]], basis: str, reason: str, at: int
    ) -> dict[str, Any]:
        construct, count = _construct(rows)
        return {
            "owned": True,
            "line": line,
            "construct": construct,
            "basis": basis,
            "construct_line": at,
            "reason": reason.format(count=count, total=len(rows), at=at),
        }

    rows = compatible(line)
    if rows:
        return owned(rows, "line", "{count} of {total} compatible emissions", line)
    if (
        bounds
        and line in bounds
        and word_class in ("stack-load", "stack-store", "frame")
    ):
        rows = [
            row
            for group in procedure.emits.values()
            for row in group
            if row["family"] in ("save", "frame")
        ]
        if rows:
            return owned(
                rows,
                "prologue",
                "prologue/epilogue, traced at the procedure's end",
                line,
            )
    for distance in range(1, NEAREST_LINES + 1):
        for at in (line - distance, line + distance):
            if bounds and not bounds[0] <= at <= bounds[1]:
                continue
            rows = compatible(at)
            if rows:
                return owned(
                    rows,
                    "nearest",
                    "no compatible emission on its line; nearest at line {at}",
                    at,
                )
    return unowned(f"no compatible emission within {NEAREST_LINES} lines")


# --------------------------------------------------------------------------
# Labels.
# --------------------------------------------------------------------------

#: Labels a deciding check names. Each was measured as a recurring cause on
#: the Mickey's Speedway USA small-delta wave (backlog items 33, 34, 39, 40)
#: and each beats the generic label when its check fires.
SPECIFIC_LABELS: tuple[str, ...] = ()

#: Rule labels over class and owner, the reader's original vocabulary.
GENERIC_LABELS = (
    "hoist",
    "unrolled-loop",
    "extra-ILOD",
    "extra-ISTR",
    "missing-CSE",
    "split-not-copy",
    "spill/reload",
    "callee-save",
    "control-flow",
    "delay-slot",
    "other",
    "unowned",
)

#: The whole vocabulary; order breaks ties.
LABELS = SPECIFIC_LABELS + GENERIC_LABELS

CLASS_LABEL = {
    "load": "extra-ILOD",
    "store": "extra-ISTR",
    "stack-load": "spill/reload",
    "stack-store": "spill/reload",
    "move": "split-not-copy",
    "alu": "missing-CSE",
    "const": "missing-CSE",
    "branch": "control-flow",
    "delay-nop": "delay-slot",
    "nop": "delay-slot",
    "call": "other",
    "frame": "other",
    "other": "other",
}

#: What kind of edit each label asks for. The census sorts by this, never by
#: positional words.
EDIT_KINDS: dict[str, str] = {
    "split-not-copy": "carrier-deletion",
    "spill/reload": "reload",
    "callee-save": "save",
    "missing-CSE": "expression",
    "extra-ILOD": "expression",
    "extra-ISTR": "expression",
    "hoist": "expression",
    "unrolled-loop": "unroll",
    "control-flow": "control-flow",
    "delay-slot": "control-flow",
    "other": "unknown",
    "unowned": "unknown",
}


@dataclass(frozen=True)
class _Streams:
    target: Sequence[Instruction]
    candidate: Sequence[Instruction]
    target_words: tuple[int, ...]
    candidate_words: tuple[int, ...]
    script: Sequence[Step]

    def side(self, name: str) -> tuple[int, ...]:
        return self.candidate_words if name == "candidate" else self.target_words

    def instructions(self, name: str) -> Sequence[Instruction]:
        return self.candidate if name == "candidate" else self.target


def word_label(word: Mapping[str, Any]) -> str:
    if word.get("specific"):
        return str(word["specific"])
    if not word["owner"]["owned"] and word["owner"].get("reason") != "no trace":
        # A word with a line but no trace to read is still labelled by its
        # class: the label is a rule over class and owner, and the owner
        # half is reported as missing rather than guessed.
        return "unowned"
    if word["owner"].get("construct") == "gen_reg_save_restore":
        return "callee-save"
    return CLASS_LABEL[word["class"]]


def pair_label(pair: Pair) -> str:
    """The pair's label. The rule, applied in this order:

    specific       any word whose deciding check fired: the most common such
                   label, ties to the candidate side's word, then LABELS order.
    hoist          a closed pair whose candidate-only and target-only words
                   have the same class multiset (nops aside).
    unrolled-loop  one side carries two or more one-sided branches of the
                   same register-erased shape: a duplicated loop test.
    otherwise      the majority of the per-word labels, ties to the candidate
                   side's word -- what our source emits and can delete -- then
                   LABELS order.
    """

    def ranked(labels: Iterable[tuple[str, str]]) -> str | None:
        votes: collections.Counter[str] = collections.Counter()
        first: dict[str, int] = {}
        for label, side in labels:
            votes[label] += 1
            first.setdefault(label, 0 if side == "candidate" else 1)
        if not votes:
            return None
        return sorted(
            votes.items(), key=lambda kv: (-kv[1], first[kv[0]], LABELS.index(kv[0]))
        )[0][0]

    specific = ranked(
        (str(w["specific"]), str(w["side"])) for w in pair.words if w.get("specific")
    )
    if specific is not None:
        return specific

    def classes(side: str) -> collections.Counter[str]:
        return collections.Counter(
            w["class"]
            for w in pair.words
            if w["side"] == side and w["class"] not in ("nop", "delay-nop")
        )

    candidate, target = classes("candidate"), classes("target")
    if pair.closed and candidate and candidate == target:
        return "hoist"
    for side in ("candidate", "target"):
        shapes = collections.Counter(
            w["shape"]
            for w in pair.words
            if w["side"] == side and w["class"] == "branch"
        )
        if any(count > 1 for count in shapes.values()):
            return "unrolled-loop"
    return ranked((word_label(w), str(w["side"])) for w in pair.words) or "unowned"


def function_label(pairs: Sequence[Pair]) -> str:
    """The label of the pair that costs the most shadow."""

    if not pairs:
        return "none"
    best = sorted(
        pairs, key=lambda p: (-p.shadow, -len(p.words), LABELS.index(p.label))
    )[0]
    return best.label


def word_kind(word: Mapping[str, Any]) -> str:
    """Move, reload, save, fill, or a real operation (backlog item 28)."""

    klass = word["class"]
    if klass in ("nop", "delay-nop"):
        return "fill"
    if klass == "move":
        return "move"
    construct = word["owner"].get("construct")
    if construct == "gen_reg_save_restore" or klass == "frame":
        return "save"
    if klass in ("stack-load", "stack-store"):
        return "reload"
    return "operation"


# --------------------------------------------------------------------------
# The analysis.
# --------------------------------------------------------------------------


def _differs(target: Instruction, candidate: Instruction) -> tuple[bool, str | None]:
    """Whether a paired row differs, and in which bucket.

    A row either side relocates is masked: its low bits are the linker's.
    """

    if target.relocations or candidate.relocations:
        return False, None
    left, right = target.word_value, candidate.word_value
    if left == right:
        return False, None
    if _register_erased(left) == _register_erased(right):
        return True, "naming"
    if _immediate_erased(left) == _immediate_erased(right):
        return True, "immediate"
    return True, "structural"


def analyse_pairs(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str = "target",
    candidate_name: str = "candidate",
    symbol: str | None = None,
    granularity: str = DEFAULT_GRANULARITY,
    lines: LineTable | None = None,
    trace: Mapping[int, TraceProcedure] | None = None,
    trace_note: str | None = None,
    proc: int | None = None,
    source: Sequence[str] | None = None,
    context: Sequence[str] = (),
) -> dict[str, Any]:
    """Pairs, shadow, classes, owners and labels for one function.

    ``source`` is the candidate's C split into lines and ``context`` its
    headers, kept for the checks that read a statement or a declaration.
    """

    script = edit_script(target, candidate, granularity=granularity)
    streams = _Streams(
        target=target,
        candidate=candidate,
        target_words=tuple(item.word_value for item in target),
        candidate_words=tuple(item.word_value for item in candidate),
        script=script,
    )
    buckets = {"naming": 0, "immediate": 0, "structural": 0}
    differing: set[int] = set()
    naming: set[int] = set()
    for index, step in enumerate(script):
        if step.one_sided:
            continue
        assert step.target is not None and step.candidate is not None
        differs, bucket = _differs(target[step.target], candidate[step.candidate])
        if differs and bucket is not None:
            differing.add(index)
            buckets[bucket] += 1
            if bucket == "naming":
                naming.add(index)

    n_min = min(len(target), len(candidate))
    extra = abs(len(target) - len(candidate))
    positional = {k for k in range(n_min) if _differs(target[k], candidate[k])[0]}

    pairs = pairs_from_script(script)
    covered: set[int] = set()
    in_pair_steps: set[int] = set()
    for pair in pairs:
        steps = set(pair.steps)
        in_pair_steps |= steps
        hi = pair.hi if pair.hi is not None else n_min
        pair.aligned_in = sum(1 for s in steps if script[s].one_sided or s in differing)
        pair.positional_in = sum(1 for k in positional if pair.lo <= k < hi)
        if pair.hi is None:
            pair.positional_in += extra
        pair.naming_in = len(steps & naming)
        pair.shadow = pair.positional_in - pair.aligned_in
        pair.span_words = hi - pair.lo + (extra if pair.hi is None else 0)
        covered.update(range(pair.lo, hi))
    aligned_outside = sum(1 for s in differing if s not in in_pair_steps)
    positional_outside = sum(1 for k in positional if k not in covered)
    total_positional = len(positional) + extra
    shadow = sum(pair.shadow for pair in pairs)

    table = lines.lines if lines is not None else {}
    bounds = lines.bounds if lines is not None else None
    procedure: TraceProcedure | None = None
    proc_note = "no trace"
    if trace:
        if proc is not None:
            procedure = trace.get(proc)
            proc_note = (
                "selected with --proc"
                if procedure
                else f"no procedure {proc} in the trace"
            )
        else:
            chosen, proc_note = pick_procedure(
                trace, lines.own_lines if lines is not None else ()
            )
            procedure = trace.get(chosen) if chosen is not None else None
            proc = chosen

    # The candidate row aligned just before each step (else just after), for
    # placing a target-only word by its neighbour's line.
    last_candidate: list[int | None] = []
    seen: int | None = None
    for step in script:
        if step.candidate is not None:
            seen = step.candidate
        last_candidate.append(seen)

    for pair in pairs:
        words: list[dict[str, Any]] = []
        for index in pair.steps:
            step = script[index]
            if step.op == "candidate" and step.candidate is not None:
                row = step.candidate
                previous = streams.candidate_words[row - 1] if row else None
                klass = classify_word(streams.candidate_words[row], previous)
                owner = own(klass, table.get(row * 4), procedure, bounds)
                words.append(
                    {
                        "side": "candidate",
                        "row": row,
                        "offset": row * 4,
                        "class": klass,
                        "shape": _register_erased(streams.candidate_words[row]),
                        "owner": owner,
                        "via": "own",
                    }
                )
            elif step.op == "target" and step.target is not None:
                row = step.target
                previous = streams.target_words[row - 1] if row else None
                klass = classify_word(streams.target_words[row], previous)
                near = last_candidate[index]
                if near is None:
                    near = step.target if step.target < len(candidate) else None
                line = table.get(near * 4) if near is not None else None
                owner = own(klass, line, procedure, bounds)
                if (
                    not owner["owned"]
                    and isinstance(line, int)
                    and procedure is not None
                    and procedure.emits.get(line)
                ):
                    construct, _count = _construct(procedure.emits[line])
                    owner = {
                        "owned": True,
                        "line": line,
                        "construct": construct,
                        "basis": "neighbour",
                        "construct_line": line,
                        "reason": "neighbour line; no same-family emission near it",
                    }
                words.append(
                    {
                        "side": "target",
                        "row": row,
                        "offset": row * 4,
                        "class": klass,
                        "shape": _register_erased(streams.target_words[row]),
                        "owner": owner,
                        "via": "neighbour",
                    }
                )
        for word in words:
            word["specific"] = None
            word["check"] = None
            word["lever"] = None
            word["label"] = word_label(word)
            word["kind"] = word_kind(word)
        pair.words = words
        pair.label = pair_label(pair)

    candidate_frame = frame_size(streams.candidate_words)
    target_frame = frame_size(streams.target_words)
    all_words = [word for pair in pairs for word in pair.words]
    owning_lines = sorted(
        {
            str(word["owner"]["line"])
            for word in all_words
            if word["owner"]["owned"] and word["owner"]["line"] is not None
        }
    )
    label = function_label(pairs)
    return {
        "schema": PAIRS_SCHEMA,
        "evidence": EVIDENCE,
        "target": target_name,
        "candidate": candidate_name,
        "symbol": symbol,
        "granularity": granularity,
        "target_rows": len(target),
        "candidate_rows": len(candidate),
        "size_delta": (len(candidate) - len(target)) * 4,
        "candidate_frame": candidate_frame,
        "target_frame": target_frame,
        "frame_delta": candidate_frame - target_frame,
        "buckets": buckets,
        "positional": total_positional,
        "shadow": shadow,
        "aligned_after_shadow": total_positional - shadow,
        "aligned_outside": aligned_outside,
        "positional_outside": positional_outside,
        "outside_agrees": aligned_outside == positional_outside,
        "naming_in_pairs": sum(pair.naming_in for pair in pairs),
        "line_table": {
            "source": lines.source if lines is not None else None,
            "words": len(table),
            "bounds": list(bounds) if bounds else None,
        },
        "trace": {
            "status": trace_note or ("supplied" if trace else "not supplied"),
            "proc": proc if procedure is not None else None,
            "note": proc_note,
        },
        "pairs": [
            {
                "positional_lo": pair.lo * 4,
                "positional_hi": pair.hi * 4 if pair.hi is not None else None,
                "closed": pair.closed,
                "span_words": pair.span_words,
                "positional_in": pair.positional_in,
                "aligned_in": pair.aligned_in,
                "naming_in": pair.naming_in,
                "shadow": pair.shadow,
                "label": pair.label,
                "edit": EDIT_KINDS.get(pair.label, "unknown"),
                "words": [
                    {
                        key: value
                        for key, value in word.items()
                        if key not in ("shape", "row", "specific")
                    }
                    for word in pair.words
                ],
            }
            for pair in pairs
        ],
        "one_sided_words": len(all_words),
        "owned": all(word["owner"]["owned"] for word in all_words),
        "owning_lines": len(owning_lines),
        "label": label,
        "edit": EDIT_KINDS.get(label, "none" if label == "none" else "unknown"),
        "labels": dict(
            sorted(collections.Counter(word["label"] for word in all_words).items())
        ),
        "classes": dict(
            sorted(collections.Counter(word["class"] for word in all_words).items())
        ),
        "kinds": dict(
            sorted(collections.Counter(word["kind"] for word in all_words).items())
        ),
        "basis": dict(
            sorted(
                collections.Counter(
                    word["owner"].get("basis") or "unowned" for word in all_words
                ).items()
            )
        ),
    }


def pair_lines(report: Mapping[str, Any]) -> list[str]:
    """Terminal rendering: classes, offsets and owners, never instruction text."""

    buckets = report["buckets"]
    title = report["symbol"] or report["candidate"]
    out = [
        f"{title}: size delta {report['size_delta']:+d} bytes, frame delta "
        f"{report['frame_delta']:+d} ({report['candidate_frame']} vs "
        f"{report['target_frame']})",
        f"  aligned rows: naming {buckets['naming']}, immediate "
        f"{buckets['immediate']}, structural {buckets['structural']}, "
        f"one-sided {report['one_sided_words']}",
        f"  positional {report['positional']}, shadow {report['shadow']}, "
        f"aligned after shadow {report['aligned_after_shadow']} "
        f"({report['naming_in_pairs']} of it naming rows inside pairs)",
        f"  outside pairs: aligned {report['aligned_outside']} vs positional "
        f"{report['positional_outside']}"
        + ("" if report["outside_agrees"] else "   <-- DISAGREE"),
        f"  lines: {report['line_table']['words']} word(s) from "
        f"{report['line_table']['source'] or 'no line table'}; trace: "
        f"{report['trace']['status']} ({report['trace']['note']})",
    ]
    if not report["pairs"]:
        out.append("  no one-sided words: the streams align word for word")
        return out
    out.append("")
    for number, pair in enumerate(report["pairs"], 1):
        hi = pair["positional_hi"]
        span = (
            f"+0x{pair['positional_lo']:X}..+0x{hi:X}"
            if hi is not None
            else f"+0x{pair['positional_lo']:X}..end"
        )
        out.append(
            f"  pair {number}: {span} ({pair['span_words']} words, "
            f"{'closed' if pair['closed'] else 'open to end'})  label "
            f"{pair['label']} [{pair['edit']}]"
        )
        out.append(
            f"    positional {pair['positional_in']}, aligned {pair['aligned_in']} "
            f"({pair['naming_in']} naming), shadow {pair['shadow']}"
        )
        for word in pair["words"]:
            owner = word["owner"]
            where = f"line {owner['line']}" if owner["line"] is not None else "no line"
            what = owner["construct"] if owner["owned"] else "unowned"
            basis = owner.get("basis") or "unowned"
            out.append(
                f"    {word['side']:<9} +0x{word['offset']:X}  {word['class']:<11} "
                f"{word['label']:<18} {where} [{basis}]: {what} -- {owner['reason']}"
            )
            if word.get("check"):
                out.append(f"      check: {word['check']}")
                out.append(f"      lever: {word['lever']}")
    out.append("")
    out.append(
        "  ownership basis: "
        + ", ".join(f"{key} {value}" for key, value in report["basis"].items())
    )
    out.append(
        f"  function label {report['label']} [{report['edit']}]; "
        f"{'owned' if report['owned'] else 'NOT fully owned'}; "
        f"{report['owning_lines']} owning line(s)"
    )
    out.append(
        "  a label names the word and the line, not the spelling that removes "
        "it; confirm with a source edit and run the reader again"
    )
    return out


# --------------------------------------------------------------------------
# The census.
# --------------------------------------------------------------------------


def census_rows(
    document: Any, *, max_delta: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select the small-delta rows of a ranking, and the ones it cannot read.

    A ranking is a list of rows or an object holding them under
    ``functions``. A row names its function under ``symbol``, ``name`` or
    ``function``; a row with a ``size_delta`` of 0 or beyond ``max_delta``
    bytes is out of scope, and a row without one is measured and filtered on
    the measured delta instead.
    """

    rows = document.get("functions") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise ValueError("a ranking is a list of rows or an object with `functions`")
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            rejected.append({"symbol": None, "error": "row is not an object"})
            continue
        name = row.get("symbol") or row.get("name") or row.get("function")
        if not isinstance(name, str) or not name:
            rejected.append({"symbol": None, "error": "row names no function"})
            continue
        delta = row.get("size_delta")
        if delta is not None:
            if not isinstance(delta, int):
                rejected.append(
                    {"symbol": name, "error": "size_delta is not an integer"}
                )
                continue
            if delta == 0 or abs(delta) > max_delta:
                continue
        selected.append({**row, "symbol": name})
    return selected, rejected


def summarise(
    report: Mapping[str, Any], *, size_bytes: int | None = None
) -> dict[str, Any]:
    """One census row: counts and labels only, no offsets, no words."""

    return {
        "symbol": report["symbol"],
        "bytes": size_bytes if size_bytes is not None else report["target_rows"] * 4,
        "delta": report["size_delta"],
        "frame_delta": report["frame_delta"],
        "pairs": len(report["pairs"]),
        "one_sided": report["one_sided_words"],
        "positional": report["positional"],
        "shadow": report["shadow"],
        "aligned_after_shadow": report["aligned_after_shadow"],
        "naming_in_pairs": report["naming_in_pairs"],
        "label": report["label"],
        "edit": "frame-cell"
        if report["frame_delta"] and report["edit"] in ("reload", "unknown")
        else report["edit"],
        "kinds": dict(report["kinds"]),
        "owned": report["owned"],
        "owning_lines": report["owning_lines"],
        "outside_agrees": report["outside_agrees"],
        "basis": dict(report["basis"]),
    }


EDIT_ORDER = (
    "compiler-flag",
    "declaration",
    "carrier-deletion",
    "frame-cell",
    "lifetime",
    "reload",
    "save",
    "expression",
    "unroll",
    "control-flow",
    "unknown",
    "none",
)


def census_report(
    results: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    *,
    ranking: str,
    max_delta: int,
) -> dict[str, Any]:
    ordered = sorted(
        results, key=lambda r: (r["aligned_after_shadow"], str(r["symbol"]))
    )
    by_edit: dict[str, dict[str, Any]] = {}
    for row in ordered:
        group = by_edit.setdefault(
            row["edit"],
            {
                "functions": 0,
                "bytes": 0,
                "aligned_after_shadow": 0,
                "owned": 0,
                "labels": {},
            },
        )
        group["functions"] += 1
        group["bytes"] += row["bytes"]
        group["aligned_after_shadow"] += row["aligned_after_shadow"]
        group["owned"] += 1 if row["owned"] else 0
        group["labels"][row["label"]] = group["labels"].get(row["label"], 0) + 1
    kinds: collections.Counter[str] = collections.Counter()
    for row in ordered:
        kinds.update(row["kinds"])
    return {
        "schema": PAIRS_CENSUS_SCHEMA,
        "evidence": EVIDENCE,
        "ranking": ranking,
        "max_delta": max_delta,
        "measured": len(ordered),
        "not_measured": len(errors),
        "bytes": sum(row["bytes"] for row in ordered),
        "positional": sum(row["positional"] for row in ordered),
        "shadow": sum(row["shadow"] for row in ordered),
        "aligned_after_shadow": sum(row["aligned_after_shadow"] for row in ordered),
        "kinds": dict(sorted(kinds.items())),
        "by_edit": {
            edit: by_edit[edit]
            for edit in sorted(
                by_edit, key=lambda e: EDIT_ORDER.index(e) if e in EDIT_ORDER else 99
            )
        },
        "results": ordered,
        "errors": list(errors),
    }


def census_lines(report: Mapping[str, Any]) -> list[str]:
    """The census as a tracked-safe Markdown summary: classes and counts only."""

    out = [
        "# Small-delta census",
        "",
        f"Scope: rows of `{report['ranking']}` with 0 < |size_delta| <= "
        f"{report['max_delta']}: measured {report['measured']} "
        f"({report['bytes']:,} bytes), not measured {report['not_measured']}.",
        "",
        f"Positional {report['positional']:,}, shadow {report['shadow']:,}, "
        f"aligned after shadow {report['aligned_after_shadow']:,}. One-sided "
        "words by kind: "
        + (", ".join(f"{k} {v}" for k, v in report["kinds"].items()) or "none")
        + ".",
        "",
        "## By the edit each needs",
        "",
        "| edit | functions | bytes | aligned after shadow | owned | labels |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for edit, group in report["by_edit"].items():
        labels = ", ".join(f"{k} {v}" for k, v in sorted(group["labels"].items()))
        out.append(
            f"| {edit} | {group['functions']} | {group['bytes']:,} | "
            f"{group['aligned_after_shadow']:,} | {group['owned']} | {labels} |"
        )
    out += [
        "",
        "## Functions, by aligned residual after shadow",
        "",
        "| symbol | bytes | delta | frame | pairs | shadow | aligned | label "
        "| edit | owned |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in report["results"]:
        out.append(
            f"| `{row['symbol']}` | {row['bytes']:,} | {row['delta']:+d} | "
            f"{row['frame_delta']:+d} | {row['pairs']} | {row['shadow']} | "
            f"{row['aligned_after_shadow']} | {row['label']} | {row['edit']} | "
            f"{'yes' if row['owned'] else 'no'} |"
        )
    if report["errors"]:
        out += ["", "## Not measured", "", "| symbol | reason |", "|---|---|"]
        for error in report["errors"]:
            reason = " ".join(str(error.get("error")).split())
            out.append(f"| `{error.get('symbol')}` | {reason} |")
    return out
