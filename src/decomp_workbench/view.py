"""Aligned mechanism view: LCS alignment, class lanes, and hunk taxonomy.

Positional diffing lies.  One upstream register-role swap on a live campaign
function turned into roughly 76 phantom scattered differences under positional
comparison; the LCS-aligned truth was roughly 43 hunks.  Every count produced
here is therefore an *aligned* count, never a positional one.

The pipeline is two passes of ``difflib.SequenceMatcher`` (``autojunk=False``
is mandatory: instruction streams are full of repeats that the junk heuristic
would discard), plus a classification step:

1. Anchor on the normalized instruction *text*.  Identical text is
   interchangeable, so these anchors carry no ambiguity.
2. Inside each unmatched region, pair by *opcode*, so an operand-level
   difference is classified rather than shown as a deletion beside an
   insertion.  Anything left unpaired is structure or schedule.
3. Classify every pair: register, commutative-order, constant, relocation,
   displacement, or match.

The ad-hoc aligners three campaigns built in one day ran the opcode pass
first.  That order cannot resolve a run of repeated opcodes -- eight ``addu``
instructions with one inserted among them align position by position, and four
correct instructions are then reported as register differences beside a
phantom insertion -- so the text pass anchors first here.

Register lanes are extracted from the *whole* aligned stream, including the
instructions that match.  That is not an optimization: the decisive signal in
the modLoadAnimActual campaign was in the temps that matched, and a view that
only shows mismatched instructions hides the queue.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .compare import (
    frame_size,
    is_commutative_swap,
    register_operands,
    relocation_field_mask,
)
from .field_guide import next_steps
from .literal_pool import (
    PoolAccess,
    PoolComparison,
    comparable,
    compare_pool_accesses,
    pool_accesses,
)
from .model import Instruction
from .schema import VIEW_METRICS_BY_KEY

__all__ = [
    "DEFAULT_REGISTER_PROFILE",
    "REGISTER_CLASS_PROFILES",
    "REGISTER_PROFILE_EVIDENCE",
    "AlignedRow",
    "Hunk",
    "Lane",
    "MechanismView",
    "Web",
    "aligned_class_counts",
    "build_view",
    "classify_pair",
    "destination_register",
    "schema_keys",
]


# ---------------------------------------------------------------------------
# Schema: one vocabulary, two renderings.
#
# Human output prints ``key=value`` using these exact keys, and JSON output
# uses the same keys, so the two audiences can never drift apart again.  List
# valued keys render as a count in the human header and as the list in JSON.
# The names live in the shared metric registry beside the comparison and
# campaign keys, so ``--explain-keys`` explains this command too and there is
# one place a key can be added.
# ---------------------------------------------------------------------------


def schema_keys() -> frozenset[str]:
    """Return every key the human and JSON renderings are allowed to print."""

    return frozenset(VIEW_METRICS_BY_KEY)


# ---------------------------------------------------------------------------
# Register class tables (per-compiler-era profile data, not hardcoded policy).
#
# The split between "a register uopt colored a web into" and "a register ugen
# handed out as a block-local temp" is *era-specific*, and getting it wrong
# sends the reader to the wrong pass.  `--register-profile` selects the era;
# `REGISTER_PROFILE_EVIDENCE` records what each table is actually made of, so
# an unprobed release is never quoted as if it had been measured.
# ---------------------------------------------------------------------------

#: The pre-probe table, kept verbatim.  It is the conservative default for any
#: release with no probe of its own: six recorded campaigns were read against
#: it, so it is the behavior a reader with an unmeasured compiler already has,
#: and changing that silently would relabel their evidence.
UNVERIFIED_CLASSES: dict[str, tuple[str, ...]] = {
    "pool": ("v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5"),
    "temp": ("t6", "t7", "t8", "t9", "s8"),
}

#: IDO 5.3 at ``-O2 -mips2``, probed with nine forced-color experiments during
#: the `object_interaction` campaign and confirmed against instrumented ugen.
#:
#: uopt hands out only ``v0``/``v1``/``a0-a3``/``s0-s8`` and
#: ``f0``/``f2``/``f12-f24``.  ``t0-t9`` and ``f4/f6/f8/f10`` are *always* ugen
#: block-local temps -- never pool colors -- which is the fact three campaign
#: agents assumed the other way round.
#:
#: The temp tables are in *ring order*, not register-number order, because
#: ugen's free list is a least-recently-freed FIFO seeded ``t6 t7 t8 t9 t0 ..
#: t5`` (int) and ``f4 f6 f8 f10`` (float).  A rotation through the ring is
#: therefore a contiguous run of the table, which is what `_rotation_cycle`
#: requires.
#:
#: The float ring is **four wide**, and that is a measurement, not a
#: simplification.  ugen initializes ``ffree`` with six entries -- ``f4 f6 f8
#: f10 f16 f18`` -- but withdraws ``f16``/``f18`` before the first allocation,
#: and an instrumented trace of a whole procedure shows 1460 of 1460 float
#: allocations landing in ``f4``-``f10``.  ``f16``/``f18`` are uopt colors
#: (c28/c29) and belong in ``fp-pool``.  Reading the six-entry initializer as
#: the ring instead widens ``fp-temp`` onto two registers uopt owns, and a
#: ``f12 -> f16`` difference then reports as a temp-ring closure that is really
#: a coloring change: that misreading cost one campaign stage about fifteen
#: builds and an adoption path that had to be withdrawn.
IDO53_CLASSES: dict[str, tuple[str, ...]] = {
    "pool": (
        "v0",
        "v1",
        "a0",
        "a1",
        "a2",
        "a3",
        "s0",
        "s1",
        "s2",
        "s3",
        "s4",
        "s5",
        "s6",
        "s7",
        "s8",
    ),
    "temp": ("t6", "t7", "t8", "t9", "t0", "t1", "t2", "t3", "t4", "t5"),
    "fp-pool": ("f0", "f2", "f12", "f14", "f16", "f18", "f20", "f22", "f24"),
    "fp-temp": ("f4", "f6", "f8", "f10"),
}

REGISTER_CLASS_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "ido53": IDO53_CLASSES,
    "unverified": UNVERIFIED_CLASSES,
}

#: What each profile is made of, quoted wherever the profile is named.  A
#: reader who cannot tell a probed table from an inherited one cannot tell a
#: finding from an assumption.
REGISTER_PROFILE_EVIDENCE: dict[str, str] = {
    "ido53": (
        "IDO 5.3 -O2 -mips2, probed (nine forced-color experiments) and "
        "confirmed against instrumented ugen; temp tables are in ugen "
        "free-list ring order, and the float ring is the four registers ugen "
        "actually hands out (f16/f18 are initialized into ffree, withdrawn "
        "before the first allocation, and are uopt colors)"
    ),
    "unverified": (
        "pre-probe table, not measured against any single release; the "
        "conservative choice for a compiler with no probe of its own"
    ),
}

DEFAULT_REGISTER_PROFILE = "ido53"

# Opcodes whose first register operand is a source, not a destination.  A lane
# records definitions only: a store or a branch reads its registers and would
# otherwise inject phantom slots into the sequence.
NO_DESTINATION_OPCODES = frozenset(
    {
        "b",
        "bal",
        "bc1f",
        "bc1fl",
        "bc1t",
        "bc1tl",
        "beq",
        "beql",
        "beqz",
        "bgez",
        "bgezal",
        "bgezl",
        "bgtz",
        "bgtzl",
        "blez",
        "blezl",
        "bltz",
        "bltzal",
        "bltzl",
        "bne",
        "bnel",
        "bnez",
        "break",
        "cache",
        "ctc1",
        "ddiv",
        "ddivu",
        "div",
        "divu",
        "dmtc1",
        "dmult",
        "dmultu",
        "j",
        "jal",
        "jalr",
        "jr",
        "mtc0",
        "mtc1",
        "mthi",
        "mtlo",
        "mult",
        "multu",
        "nop",
        "sb",
        "sc",
        "scd",
        "sd",
        "sdc1",
        "sdc2",
        "sdl",
        "sdr",
        "sh",
        "sw",
        "swc1",
        "swc2",
        "swl",
        "swr",
        "sync",
        "syscall",
        "teq",
        "tne",
    }
)

SYMBOL_OPERAND_RE = re.compile(r"\b([0-9a-fA-F]+)\s+<([^>]+)>")
IMMEDIATE_RE = re.compile(r"(?<![A-Za-z0-9_$.])-?(?:0x[0-9a-fA-F]+|\d+)\b")
SELF_BRANCH_OPCODES = frozenset({"b", "j", "bal"})
#: A branch or jump destination objdump rendered as a bare address because no
#: symbol covered it. A stripped, positional target prints ``b 0x485c`` and
#: ``jal 0x0`` where a symbolized candidate prints ``b 485c <fn+0x485c>`` and
#: ``jal 0 <fn>``; the words are identical and only the symbol table differs.
#: Classing that asymmetry as evidence produced 692 phantom relocation rows on
#: one recorded campaign, which buried the real relocation differences under
#: them.  It is matched at the end of the operand list because on a branch or a
#: jump the destination is the last operand.
BARE_DESTINATION_RE = re.compile(r"(?<=[\s,])(0x)?([0-9a-fA-F]+)\s*$")
#: Opcodes whose last operand is a destination address rather than a value.
JUMP_OPCODES = frozenset({"j", "jal", "jalx"})
#: Placeholder written in place of a branch destination that resolves inside
#: the function, so destinations compare by aligned row instead of by address.
ALIGNED_TARGET = "@row"

MATCH = "match"
DISPLACEMENT = "displacement"
STRUCTURAL = "structural"
SCHEDULE = "schedule"
REGISTER = "register"
CONSTANT = "constant"
COMMUTATIVE = "commutative"
RELOCATION = "relocation"
#: The same literal-pool slot, anchored differently.  A target that names one
#: external symbol per literal and a candidate that emits one dense anonymous
#: pool print every shared slot as a different ``(symbol, addend)`` pair; the
#: words differ, the datum read does not, and no source change controls the
#: difference.  See :mod:`decomp_workbench.literal_pool`.
POOL = "pool"
#: A literal-pool access the two objects do *not* agree on: a different
#: resolved offset, a different access width, or an anchor correspondence that
#: is not one-to-one.  This is the real question the phantom rows used to bury.
POOL_LAYOUT = "pool_layout"

#: Classes in report order.  ``match`` is deliberately first: the header leads
#: with how much already agrees.
CLASS_ORDER: tuple[str, ...] = (
    MATCH,
    DISPLACEMENT,
    STRUCTURAL,
    SCHEDULE,
    REGISTER,
    CONSTANT,
    COMMUTATIVE,
    RELOCATION,
    POOL,
    POOL_LAYOUT,
)

#: Classes whose rows a pool resolution may relabel.  Both are "the aligned
#: words differ only in a field the linker fills": ``relocation`` when the two
#: sides printed the same operand text, ``constant`` when the printed pool
#: offset itself differed.  Nothing else is eligible, so a row that also moved
#: a register can never be absorbed into a pool verdict.
POOL_RELABEL_FROM: frozenset[str] = frozenset({RELOCATION, CONSTANT})

#: Precedence for composite verdicts.  Constants cascade, so they are fixed
#: first; register classes are last because they are usually downstream.
MIXED_PRECEDENCE: tuple[str, ...] = (
    CONSTANT,
    STRUCTURAL,
    SCHEDULE,
    COMMUTATIVE,
    REGISTER,
)

#: The classes a source change controls, and therefore the ones a residual
#: count may include.  ``match`` is agreement; ``displacement`` is an encoded
#: branch offset that moved because something was inserted elsewhere; and
#: ``relocation`` is a linker-supplied field.  None of the three is a number a
#: candidate should be ranked on, and counting them would re-introduce exactly
#: the phantom volume the alignment exists to remove.
RESIDUAL_CLASSES: tuple[str, ...] = (
    STRUCTURAL,
    SCHEDULE,
    REGISTER,
    CONSTANT,
    COMMUTATIVE,
)


#: Where a residual should be taken next, as one machine-readable word.
#:
#: A verdict names the *mechanism*. It has never named the **tool**, and the
#: gap cost a campaign about a million tokens: "interference-forbidden colour"
#: and "list-scheduler slot-fill -- no source lever" were read as proof that a
#: function could not be matched, bespoke instrumentation was funded to explain
#: why, and then a twenty-minute permuter run matched two of those functions
#: anyway. An allocation or schedule tie is exactly what a randomized search is
#: for, and no analysis of two disassemblies can rule one out.
ROUTING_PERMUTER_FIRST = "permuter-first"
ROUTING_STRUCTURAL = "structural"
ROUTING_IMPORT_FIX = "import-fix"
ROUTING_NONE = "none"

#: Every value the `routing` field may take, for a consumer switching on it.
ROUTING_VALUES: tuple[str, ...] = (
    ROUTING_PERMUTER_FIRST,
    ROUTING_STRUCTURAL,
    ROUTING_IMPORT_FIX,
    ROUTING_NONE,
)

#: The sentence every no-hand-lever verdict owes the reader.
#:
#: "HAND" is capitalized because that is the whole correction: the analysis
#: found no lever *a human types into the C file*, which is a fact about the
#: search space a source edit can reach, not a fact about the function.
PERMUTER_ROUTING_SENTENCE = (
    "no HAND lever found -- this is a permuter target; run the sweep before "
    "concluding a wall."
)

#: The command that sentence names, so the reader does not have to look it up.
PERMUTER_ROUTING_STEPS: tuple[str, ...] = (
    PERMUTER_ROUTING_SENTENCE,
    "decomp-workbench permute-doctor FUNCTION, then permute-sweep QUEUE. An "
    "allocation or schedule tie is a search problem; record it as a wall only "
    "after a measured search has been flat (permute classify).",
    # The doctor exists because of this law; naming it here is what stops a
    # flat search from being read as a fact about the function.
    "law L69: a permuter that finds nothing instantly is a setup fault, not a "
    "hard function -- decomp-workbench guide laws ido53 L69",
)

#: Verdicts whose residual is an allocation, colour, or schedule tie.
#:
#: These are the ones whose guidance can otherwise read as a wall. `constant`,
#: `structure` and the pool verdicts are not here: those name a difference a
#: reader can act on directly, and sending them to a randomized search first
#: would be the opposite error.
PERMUTER_ROUTED_VERDICTS: frozenset[str] = frozenset(
    {
        "allocation",
        "phase-shift",
        "register-permutation",
        "register-ring-only",
        "schedule",
    }
)

#: Residual classes that route to a search when they dominate a mixed verdict.
PERMUTER_ROUTED_CLASSES: frozenset[str] = frozenset({REGISTER, SCHEDULE})


def routing_for(
    verdict: str,
    counts: Mapping[str, int],
    warnings: Sequence[str] = (),
) -> str:
    """Return where this residual should be taken next.

    Three answers, in the order they are asked:

    * `import-fix` -- the two inputs were not comparable in the first place
      (a selection warning: a different symbol, a missing section). Nothing
      downstream of that is evidence about the source, so neither a lever nor
      a search is the next move.
    * `permuter-first` -- an allocation, colour, or schedule tie. A search is
      cheap and has matched functions whose hand analysis said they could not
      be.
    * `structural` -- a constant, a structural hunk, a pool slot, a frame:
      differences a reader acts on directly, where a randomized search would
      be the expensive way to find what the diff already shows.

    An exact pair routes nowhere.
    """

    if warnings:
        return ROUTING_IMPORT_FIX
    if verdict in ("exact", "words-identical"):
        return ROUTING_NONE
    if verdict in PERMUTER_ROUTED_VERDICTS:
        return ROUTING_PERMUTER_FIRST
    if verdict.startswith("mixed("):
        primary = _primary_class(dict(counts))
        if primary in PERMUTER_ROUTED_CLASSES:
            return ROUTING_PERMUTER_FIRST
    return ROUTING_STRUCTURAL


@dataclass(frozen=True)
class AlignedRow:
    """One row of the LCS alignment, with its operand-level classification."""

    index: int
    classification: str
    target_index: int | None = None
    candidate_index: int | None = None
    target: str | None = None
    candidate: str | None = None
    target_address: int | None = None
    candidate_address: int | None = None
    target_registers: tuple[str, ...] = ()
    candidate_registers: tuple[str, ...] = ()
    substitutions: tuple[tuple[str, str], ...] = ()

    @property
    def matched(self) -> bool:
        """Whether the two sides are byte-identical."""

        return self.classification == MATCH

    @property
    def reported(self) -> bool:
        """Whether this row belongs in a hunk.

        A displacement row differs in bytes but not in anything a source change
        controls, so it is counted and annotated in context without opening a
        hunk of its own.  A ``pool`` row is the same shape of fact one level
        further out: the two objects read the same pool slot through different
        anchors, which is a property of the two symbol tables.
        """

        return self.classification not in {MATCH, DISPLACEMENT, POOL}


@dataclass(frozen=True)
class Hunk:
    """A contiguous run of non-matching aligned rows."""

    hunk: int
    classification: str
    start: int
    end: int
    target_range: tuple[int, int] | None
    candidate_range: tuple[int, int] | None
    target_bytes: tuple[int, int] | None
    candidate_bytes: tuple[int, int] | None
    classes: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "hunk": self.hunk,
            "class": self.classification,
            "rows": [self.start, self.end],
            "target": list(self.target_range) if self.target_range else None,
            "candidate": list(self.candidate_range) if self.candidate_range else None,
            "target_bytes": _byte_range(self.target_bytes),
            "candidate_bytes": _byte_range(self.candidate_bytes),
            "classes": dict(self.classes),
        }


@dataclass(frozen=True)
class Lane:
    """A per-class register assignment sequence, matching instructions included."""

    classification: str
    target: tuple[str, ...]
    candidate: tuple[str, ...]
    target_rows: tuple[int, ...]
    candidate_rows: tuple[int, ...]
    divergence: int | None
    divergence_row: int | None
    rotation: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "class": self.classification,
            "target": list(self.target),
            "candidate": list(self.candidate),
            "rows": list(self.target_rows),
            # `slot` and `aligned_row` are two different units, and spelling
            # them `divergence` and `index` made them read as one coordinate
            # pair. The screen and the payload rename together: one vocabulary
            # is the whole point of the metric registry.
            "slot": self.divergence,
            "aligned_row": self.divergence_row,
            "rotation": self.rotation,
        }


@dataclass(frozen=True)
class Web:
    """One consistent register substitution across the aligned stream."""

    web: str
    target: str
    candidate: str
    count: int
    rows: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "web": self.web,
            "target": self.target,
            "candidate": self.candidate,
            "count": self.count,
            "rows": list(self.rows),
        }

    def ring_only_target(
        self, register_profile: str = DEFAULT_REGISTER_PROFILE
    ) -> bool:
        """Whether no coloring outcome can put a value in this target register."""

        return bool(uncolorable_targets((self,), register_profile))


@dataclass(frozen=True)
class MechanismView:
    """The aligned mechanism view of one target/candidate pair."""

    symbol: str | None
    target: str
    candidate: str
    register_profile: str
    target_instructions: int
    candidate_instructions: int
    target_frame_size: int | None
    candidate_frame_size: int | None
    counts: dict[str, int]
    verdict: str
    playbook: str
    signature: tuple[str, ...]
    prefix_exact: int | None
    rows: tuple[AlignedRow, ...]
    hunks: tuple[Hunk, ...]
    lanes: tuple[Lane, ...]
    webs: tuple[Web, ...]
    guidance: tuple[str, ...]
    #: Reasons not to trust the verdict, as opposed to findings about the
    #: code. Rendered ahead of everything else by the commands that own the
    #: screen; carried here so `--json` consumers see them too.
    warnings: tuple[str, ...] = ()
    #: How the literal-pool accesses were resolved, and what they said.
    #: ``None`` when neither object relocates a data reference.
    pool: PoolComparison | None = None

    @property
    def aligned_rows(self) -> int:
        return len(self.rows)

    @property
    def routing(self) -> str:
        """Where this residual goes next: a search, a source edit, or the import.

        Derived, never stored: a verdict and its routing that could disagree
        would be two claims about one residual, and the one a reader acts on
        is whichever printed last.
        """

        return routing_for(self.verdict, self.counts, self.warnings)

    @property
    def register_first_divergence(self) -> bool:
        """Whether the first divergence is a register-class divergence.

        Two disassembly streams are the only evidence this command has, so a
        state divergence that leaves the bytes alone is not observable here:
        anything that changes a lane also changes an instruction.  What *is*
        observable, and what redirected a campaign that had spent 13 variants
        on the visible block, is that the first divergence is a register-class
        divergence rather than a structural one -- which says the decision was
        made upstream even though it surfaces here.  Proving where upstream
        needs a pool trace, which this command does not read.
        """

        return "register-first-divergence" in self.signature

    def register_report(self) -> list[dict[str, Any]]:
        """Per aligned row register operands, including the matching rows.

        This is the readout a campaign agent otherwise reconstructs by running
        objdump and a regular expression once per variant.
        """

        return [
            {
                "index": row.index,
                "class": row.classification,
                "target": list(row.target_registers),
                "candidate": list(row.candidate_registers),
            }
            for row in self.rows
        ]

    def as_dict(self, *, report_regs: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "target": self.target,
            "candidate": self.candidate,
            "register_profile": self.register_profile,
            # What that table is made of. A reader who cannot tell a probed
            # split from an inherited one cannot tell a finding from an
            # assumption, and the pool/temp attribution is exactly where that
            # confusion sent three campaign agents to the wrong pass.
            "register_profile_evidence": REGISTER_PROFILE_EVIDENCE.get(
                self.register_profile, "unknown profile"
            ),
            "target_instructions": self.target_instructions,
            "candidate_instructions": self.candidate_instructions,
            "aligned_rows": self.aligned_rows,
            "target_frame_size": self.target_frame_size,
            "candidate_frame_size": self.candidate_frame_size,
            "verdict": self.verdict,
            "playbook": self.playbook,
            # Which tool this residual belongs to, as one word. The verdict
            # names the mechanism; nothing before this named the next tool,
            # and readers filled that gap with "unmatchable".
            "routing": self.routing,
            "signature": list(self.signature),
            "prefix_exact": self.prefix_exact,
            "hunks": [item.as_dict() for item in self.hunks],
            "lanes": [item.as_dict() for item in self.lanes],
            "webs": [item.as_dict() for item in self.webs],
            # Whether a color lever can reach the target's registers at all.
            # A residual whose target registers are ring-only makes every
            # reweighting and tie-break lever unreachable, and nothing else in
            # this payload says so.
            "ring_only_targets": [
                item.target
                for item in uncolorable_targets(self.webs, self.register_profile)
            ],
            "next": list(self.guidance),
            "warnings": list(self.warnings),
        }
        for name in CLASS_ORDER:
            payload[name] = self.counts.get(name, 0)
        payload["pool_resolution"] = (
            self.pool.resolution if self.pool is not None else None
        )
        payload["pool_slots"] = (
            [self.pool.target_slots, self.pool.candidate_slots]
            if self.pool is not None
            else None
        )
        if report_regs:
            payload["register_report"] = self.register_report()
        return payload


def _byte_range(value: tuple[int, int] | None) -> list[str] | None:
    return None if value is None else [f"0x{value[0]:x}", f"0x{value[1]:x}"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _address_index(instructions: Sequence[Instruction]) -> dict[int, int]:
    return {item.address: index for index, item in enumerate(instructions)}


def normalized_text(
    instruction: Instruction,
    *,
    address_index: dict[int, int],
    row_of_index: dict[int, int],
) -> str:
    """Return comparison text with alignment-relative branch destinations.

    A symbolized operand is rewritten to the *aligned row* of its destination
    when it resolves inside this function, so inserting an instruction does not
    turn every later branch into a phantom difference.  Relocated operands are
    never resolved that way: their address field is linker-supplied, and
    ``jal 0 <helper>`` would otherwise resolve to row 0.

    Whether objdump printed a destination symbolically at all is a property of
    the *symbol table*, not of the code: a stripped, positional target renders
    ``b 0x485c`` for the same word a symbolized candidate renders as
    ``b 485c <fn+0x485c>``.  Both spellings are therefore normalized to the
    same token, and a relocated destination is named by its own relocation
    record rather than by whichever enclosing symbol objdump reached for.
    """

    relocated = bool(instruction.relocations)
    opcode = instruction.opcode
    self_branch = opcode in SELF_BRANCH_OPCODES or opcode.startswith("b")

    def resolved(address: int, name: str | None) -> str:
        index = address_index.get(address)
        if index is None:
            return f"<{name}>" if name else f"<0x{address:x}>"
        row = row_of_index.get(index)
        return f"{ALIGNED_TARGET}{row}" if row is not None else f"@insn{index}"

    def relocation_name() -> str:
        names = sorted({item.symbol for item in instruction.relocations if item.symbol})
        return f"<{','.join(names)}>" if names else "<relocated>"

    def replace(match: re.Match[str]) -> str:
        name = match.group(2)
        if relocated:
            # Only a destination operand is renamed from the relocation. A
            # `lui`/`lw` pair also carries a relocation, and its printed
            # spelling is compared elsewhere as relocation layout.
            if self_branch or opcode in JUMP_OPCODES:
                return relocation_name()
            return f"<{name.split('+')[0]}>"
        if not self_branch:
            return f"<{name.split('+')[0]}>"
        return resolved(int(match.group(1), 16), name)

    text = SYMBOL_OPERAND_RE.sub(replace, instruction.assembly)
    if self_branch or opcode in JUMP_OPCODES:
        bare = BARE_DESTINATION_RE.search(text)
        if bare is not None:
            token = (
                relocation_name()
                if relocated
                else resolved(int(bare.group(2), 16), None)
                if self_branch
                else f"<0x{int(bare.group(2), 16):x}>"
            )
            text = text[: bare.start()] + token
    return text.replace("$", "")


def _relocation_signature(
    instruction: Instruction,
) -> tuple[tuple[str, str | None], ...]:
    return tuple((item.kind, item.symbol) for item in instruction.relocations)


def _relocation_kind_signature(instruction: Instruction) -> tuple[str, ...]:
    """Return the relocation layout used by the object-exact comparator."""

    return tuple(item.kind for item in instruction.relocations)


def _relocation_equivalent(target: Instruction, candidate: Instruction) -> bool:
    """Return whether the two words agree outside linker-controlled bits."""

    target_mask, target_unknown = relocation_field_mask(target)
    candidate_mask, candidate_unknown = relocation_field_mask(candidate)
    if target_unknown or candidate_unknown:
        return False
    keep = ~(target_mask | candidate_mask) & 0xFFFFFFFF
    return (target.word_value & keep) == (candidate.word_value & keep)


def _immediates(text: str) -> list[str]:
    return IMMEDIATE_RE.findall(SYMBOL_OPERAND_RE.sub("SYM", text))


def destination_register(assembly: str) -> str | None:
    """Return the register an instruction defines, or ``None``.

    Lane extraction records definitions in emission order; stores, branches and
    jumps read their operands and must not add slots.
    """

    if not assembly:
        return None
    opcode = assembly.split(maxsplit=1)[0]
    if opcode in NO_DESTINATION_OPCODES or opcode.startswith("c."):
        return None
    operands = register_operands(assembly)
    return operands[0] if operands else None


def classify_pair(
    target: Instruction,
    candidate: Instruction,
    *,
    target_text: str,
    candidate_text: str,
) -> str:
    """Classify one aligned instruction pair by the cheapest explanation."""

    if target_text == candidate_text:
        if target.word == candidate.word and _relocation_signature(
            target
        ) == _relocation_signature(candidate):
            return MATCH
        if ALIGNED_TARGET in target_text:
            # A branch to the same aligned row whose encoded displacement moved
            # because something was inserted between here and there.  Treating
            # it as a source difference would re-introduce the phantom cascade
            # the alignment removes, and calling it `match` would overclaim
            # byte identity, so it gets its own name.
            return DISPLACEMENT
        if _relocation_equivalent(target, candidate):
            return RELOCATION
        return STRUCTURAL
    target_registers = register_operands(target.assembly)
    candidate_registers = register_operands(candidate.assembly)
    if target_registers != candidate_registers:
        if is_commutative_swap(target, candidate):
            return COMMUTATIVE
        return REGISTER
    if _immediates(target_text) != _immediates(candidate_text):
        if _relocation_kind_signature(target) == _relocation_kind_signature(
            candidate
        ) and _relocation_equivalent(target, candidate):
            # The differing field is supplied by the linker, not by the source.
            # GNU objdump can name one side through a local jump-table symbol
            # and the other through its section symbol plus an encoded addend;
            # the object comparator deliberately compares relocation layout,
            # not those unstable spellings.
            return RELOCATION
        return CONSTANT
    return STRUCTURAL


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------


def alignment_key(instruction: Instruction) -> str:
    """Return the text an instruction is anchored on during alignment.

    Symbolized operands collapse to the bare symbol: the numeric address and
    the ``+0x..`` offset both move when anything upstream changes size, and an
    anchor that moves is not an anchor.  Destinations are compared properly
    later, against the alignment this produces.
    """

    return SYMBOL_OPERAND_RE.sub(
        lambda match: f"<{match.group(2).split('+')[0]}>", instruction.assembly
    ).replace("$", "")


def _blocks(
    left: Sequence[str], right: Sequence[str]
) -> list[tuple[str, int, int, int, int]]:
    matcher = difflib.SequenceMatcher(a=list(left), b=list(right), autojunk=False)
    return list(matcher.get_opcodes())


def _skeleton(
    target: Sequence[Instruction], candidate: Sequence[Instruction]
) -> list[tuple[str, int | None, int | None]]:
    """Pair the two streams, choosing between two anchorings by evidence.

    Neither anchoring is safe alone, and both failures are real:

    * anchoring on opcodes cannot resolve a run of repeated opcodes.  Eight
      ``addu`` instructions with one inserted among them align position by
      position, and four correct instructions are then reported as register
      differences beside a phantom insertion;
    * anchoring on instruction text inherits ``difflib``'s greedy longest-block
      anchor.  On a stream whose text repeats -- a 64-instruction idiom copied
      down a long function -- the longest single common run can sit on the far
      side of the change, and the aligner throws away everything before it.

    So both are built and the one that explains more of the function as
    identical wins.  Ties go to the text anchoring, which is the one that
    cannot mispair by construction.
    """

    target_opcodes = [item.opcode for item in target]
    candidate_opcodes = [item.opcode for item in candidate]
    if len(target) == len(candidate) and target_opcodes == candidate_opcodes:
        # There is stronger evidence than an inferred subsequence alignment:
        # every emitted position has the same mnemonic. In long, repetitive
        # functions SequenceMatcher can align identical-looking rows across a
        # sibling block and invent an insertion/deletion pair. That turns a
        # pure allocation residual into false structural guidance. Lock the
        # observed positions when opcode shape proves they correspond.
        return [("equal", index, index) for index in range(len(target))]

    target_keys = [alignment_key(item) for item in target]
    candidate_keys = [alignment_key(item) for item in candidate]
    anchored = _pair(target_keys, candidate_keys, target_opcodes, candidate_opcodes)
    best = _alignment_score(anchored, target_keys, candidate_keys)
    if best[0] == min(len(target), len(candidate)):
        # Every instruction of the shorter side is already explained as
        # identical.  No alignment can beat that, so the second pass is skipped:
        # this is the common shape near the end of a campaign.
        return anchored
    alternative = _pair(target_opcodes, candidate_opcodes, target_keys, candidate_keys)
    if _alignment_score(alternative, target_keys, candidate_keys) > best:
        return alternative
    return anchored


def _alignment_score(
    rows: Sequence[tuple[str, int | None, int | None]],
    target_keys: Sequence[str],
    candidate_keys: Sequence[str],
) -> tuple[int, int]:
    """Score an alignment: identical pairs first, then compactness.

    This is the objective the greedy anchor only approximates -- explain as
    many instructions as possible as unchanged -- evaluated directly.
    """

    identical = sum(
        1
        for _, target_index, candidate_index in rows
        if target_index is not None
        and candidate_index is not None
        and target_keys[target_index] == candidate_keys[candidate_index]
    )
    return identical, -len(rows)


def _pair(
    target_primary: Sequence[str],
    candidate_primary: Sequence[str],
    target_secondary: Sequence[str],
    candidate_secondary: Sequence[str],
) -> list[tuple[str, int | None, int | None]]:
    """Align on the primary key, then pair inside each gap on the secondary."""

    rows: list[tuple[str, int | None, int | None]] = []
    for tag, target_start, target_end, candidate_start, candidate_end in _blocks(
        target_primary, candidate_primary
    ):
        if tag == "equal":
            rows.extend(
                ("equal", target_start + offset, candidate_start + offset)
                for offset in range(target_end - target_start)
            )
            continue
        rows.extend(
            _pair_within(
                target_secondary[target_start:target_end],
                candidate_secondary[candidate_start:candidate_end],
                target_offset=target_start,
                candidate_offset=candidate_start,
            )
        )
    return rows


def _pair_within(
    target: Sequence[str],
    candidate: Sequence[str],
    *,
    target_offset: int,
    candidate_offset: int,
) -> list[tuple[str, int | None, int | None]]:
    """Pair instructions inside one unmatched region on the secondary key.

    A pair produced here shares the secondary key but not the primary one, so
    it is exactly the population that operand-level classification exists for:
    same opcode, different registers or immediates.
    """

    rows: list[tuple[str, int | None, int | None]] = []
    for tag, target_start, target_end, candidate_start, candidate_end in _blocks(
        target, candidate
    ):
        width = (
            target_end - target_start
            if tag == "equal"
            else max(target_end - target_start, candidate_end - candidate_start)
        )
        for offset in range(width):
            target_index = target_start + offset
            candidate_index = candidate_start + offset
            rows.append(
                (
                    tag,
                    target_offset + target_index if target_index < target_end else None,
                    candidate_offset + candidate_index
                    if candidate_index < candidate_end
                    else None,
                )
            )
    return rows


def _substitutions(
    target_registers: Sequence[str], candidate_registers: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    if len(target_registers) != len(candidate_registers):
        return ()
    return tuple(
        (left, right)
        for left, right in zip(target_registers, candidate_registers, strict=True)
        if left != right
    )


# ---------------------------------------------------------------------------
# Lanes, webs, and signatures
# ---------------------------------------------------------------------------


def _register_class(register: str, profile: dict[str, tuple[str, ...]]) -> str | None:
    for name, members in profile.items():
        if register in members:
            return name
    return None


#: Evidence bar for calling a lane difference a rotation.  A constant cyclic
#: offset is findable over almost any small set of registers -- every swap of
#: two registers is trivially a rotation of a two-element cycle -- so a claim
#: this specific has to be paid for.  Both thresholds are deliberately blunt.
MINIMUM_ROTATION_CYCLE = 3
MINIMUM_ROTATION_SLOTS = 3


def _rotation_cycle(
    members: Sequence[str], observed: set[str]
) -> tuple[str, ...] | None:
    """Return the rotation cycle a lane is turning through, if there is one.

    The cycle is the observed registers in profile order, and it must be a
    *contiguous* run of the class table.  Measuring against the whole table
    would hide a real rotation whenever a function leaves part of the ring
    unused -- most do; the IDO 5.3 int ring is ten registers long and a short
    function turns through four of them -- while accepting an arbitrary subset
    would let any two cherry-picked registers manufacture a cycle.  Contiguity
    is what a queue actually produces, which is why the temp tables are stored
    in ugen free-list order rather than register-number order.
    """

    positions = [index for index, name in enumerate(members) if name in observed]
    if len(positions) < MINIMUM_ROTATION_CYCLE:
        return None
    if positions != list(range(positions[0], positions[-1] + 1)):
        return None
    return tuple(members[index] for index in positions)


def _lane_rotation(
    target: Sequence[str], candidate: Sequence[str], cycle: Sequence[str], start: int
) -> int | None:
    """Return the constant cyclic offset mapping the target tail onto the candidate.

    A temp rotation whose phase entered the block one slot early shows up as a
    single non-zero offset shared by every later slot: one upstream event, not
    N independent allocation decisions.  Fewer than
    ``MINIMUM_ROTATION_SLOTS`` diverging slots is not a phase; it is a swap
    that happens to be describable as one.
    """

    if len(target) != len(candidate) or not cycle or start >= len(target):
        return None
    if len(target) - start < MINIMUM_ROTATION_SLOTS:
        return None
    size = len(cycle)
    order = {name: index for index, name in enumerate(cycle)}
    offsets = set()
    for slot in range(start, len(target)):
        left = order.get(target[slot])
        right = order.get(candidate[slot])
        if left is None or right is None:
            return None
        offsets.add((right - left) % size)
    if len(offsets) != 1:
        return None
    offset = offsets.pop()
    return offset or None


def _build_lanes(
    rows: Sequence[AlignedRow], profile: dict[str, tuple[str, ...]]
) -> tuple[Lane, ...]:
    target_lanes: dict[str, list[tuple[str, int]]] = {name: [] for name in profile}
    candidate_lanes: dict[str, list[tuple[str, int]]] = {name: [] for name in profile}
    for row in rows:
        for assembly, bucket in (
            (row.target, target_lanes),
            (row.candidate, candidate_lanes),
        ):
            if assembly is None:
                continue
            register = destination_register(assembly)
            if register is None:
                continue
            name = _register_class(register, profile)
            if name is not None:
                bucket[name].append((register, row.index))

    lanes: list[Lane] = []
    for name in profile:
        target_slots = tuple(item[0] for item in target_lanes[name])
        candidate_slots = tuple(item[0] for item in candidate_lanes[name])
        target_rows = tuple(item[1] for item in target_lanes[name])
        candidate_rows = tuple(item[1] for item in candidate_lanes[name])
        if not target_slots and not candidate_slots:
            continue
        divergence: int | None = None
        for slot in range(max(len(target_slots), len(candidate_slots))):
            left = target_slots[slot] if slot < len(target_slots) else None
            right = candidate_slots[slot] if slot < len(candidate_slots) else None
            if left != right:
                divergence = slot
                break
        divergence_row: int | None = None
        if divergence is not None:
            candidates_rows = [
                rows_[divergence]
                for rows_ in (target_rows, candidate_rows)
                if divergence < len(rows_)
            ]
            divergence_row = min(candidates_rows) if candidates_rows else None
        cycle = _rotation_cycle(profile[name], set(target_slots) | set(candidate_slots))
        rotation = (
            None
            if divergence is None or cycle is None
            else _lane_rotation(target_slots, candidate_slots, cycle, divergence)
        )
        lanes.append(
            Lane(
                classification=name,
                target=target_slots,
                candidate=candidate_slots,
                target_rows=target_rows,
                candidate_rows=candidate_rows,
                divergence=divergence,
                divergence_row=divergence_row,
                rotation=rotation,
            )
        )
    return tuple(lanes)


def _build_webs(rows: Sequence[AlignedRow]) -> tuple[Web, ...]:
    """Group register substitutions so one swap reads as one web, not N sites."""

    order: list[tuple[str, str]] = []
    sites: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        if row.classification not in {REGISTER, COMMUTATIVE}:
            continue
        for pair in dict.fromkeys(row.substitutions):
            if pair not in sites:
                sites[pair] = []
                order.append(pair)
            sites[pair].append(row.index)
    return tuple(
        Web(
            web=f"w{number}",
            target=pair[0],
            candidate=pair[1],
            count=len(sites[pair]),
            rows=tuple(sites[pair]),
        )
        for number, pair in enumerate(order, 1)
    )


#: The classes a coloring pass can put a value in. A register outside these is
#: reachable only by the block-local temp allocator, so no reweighting, tie-break
#: or forced-color probe can steer a value into it -- the value has to become a
#: different kind of value first.
COLORABLE_CLASSES = ("pool", "fp-pool")


def colorable_registers(register_profile: str = DEFAULT_REGISTER_PROFILE) -> set[str]:
    """Return every register the era's coloring pass can hand out.

    The complement within the profile is the allocator ring: for IDO 5.3 that
    is ``t0-t9`` and ``f4/f6/f8/f10``, which uopt never colors.
    """

    profile = REGISTER_CLASS_PROFILES.get(
        register_profile, REGISTER_CLASS_PROFILES[DEFAULT_REGISTER_PROFILE]
    )
    return {
        register for name in COLORABLE_CLASSES for register in profile.get(name, ())
    }


def uncolorable_targets(
    webs: Sequence[Web], register_profile: str = DEFAULT_REGISTER_PROFILE
) -> tuple[Web, ...]:
    """Return the substitutions whose *target* register no coloring can reach.

    This is the question a register residual has to answer before any color
    lever is worth running, and the tool did not ask it. On a function whose
    first divergence wants ``t6``, ``t6`` is not in uopt's phase-2 palette at
    all, so "reach it by allocation" was impossible from the start and every
    reweighting and tie-break lever in `pool-position` and
    `forced-color-oracle` was dead on arrival. One campaign learned it by
    reading raw cost lines out of an instrumented compiler.

    A register the profile does not classify at all is not reported: an
    unmeasured register is not evidence of unreachability.
    """

    colorable = colorable_registers(register_profile)
    profile = REGISTER_CLASS_PROFILES.get(
        register_profile, REGISTER_CLASS_PROFILES[DEFAULT_REGISTER_PROFILE]
    )
    return tuple(
        web
        for web in webs
        if _register_class(web.target, profile) is not None
        and web.target not in colorable
    )


def _consistent_permutation(webs: Sequence[Web]) -> bool:
    """Return whether the register substitutions form one bijection."""

    if not webs:
        return False
    forward: dict[str, str] = {}
    backward: dict[str, str] = {}
    for web in webs:
        if forward.setdefault(web.target, web.candidate) != web.candidate:
            return False
        if backward.setdefault(web.candidate, web.target) != web.target:
            return False
    return True


def _prefix_exact(rows: Sequence[AlignedRow]) -> int | None:
    """Return the first aligned row whose instruction words differ."""

    for row in rows:
        if row.classification in {MATCH, RELOCATION, DISPLACEMENT, POOL}:
            continue
        return row.index
    return None


# ---------------------------------------------------------------------------
# Verdict and guidance
# ---------------------------------------------------------------------------


def _phase_shift(lanes: Sequence[Lane]) -> bool:
    """Return whether the lanes support a phase-shift claim.

    `phase-shift` is the most specific register verdict in the taxonomy and it
    dispatches the reader to a very particular lever (perturb the preceding
    block).  Being wrong about it is expensive, so it requires that *every*
    diverging lane is explained by a rotation.  One class turning while another
    diverges arbitrarily is two mechanisms, and the honest name for two
    mechanisms is `allocation`.
    """

    diverging = [lane for lane in lanes if lane.divergence is not None]
    if not diverging:
        return False
    return all(lane.rotation for lane in diverging)


def _verdict(
    counts: dict[str, int],
    lanes: Sequence[Lane],
    webs: Sequence[Web],
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> tuple[str, str]:
    present = [name for name in MIXED_PRECEDENCE if counts.get(name)]
    if not present:
        if counts.get(POOL_LAYOUT):
            # The pool question, once the anchoring phantoms are out of the
            # way: the two objects read genuinely different literal slots.
            return "pool-layout", "constant-audit"
        if counts.get(RELOCATION) or counts.get(DISPLACEMENT) or counts.get(POOL):
            return "words-identical", "relocation-only"
        return "exact", "done"
    if present == [REGISTER]:
        if _phase_shift(lanes):
            return "phase-shift", "temp-fifo-phase"
        # Asked before any color question, because it decides whether a color
        # question exists. When every register the target uses is outside the
        # era's colorable set, no coloring outcome reaches it and both color
        # playbooks are dead on arrival; the residual is about which values
        # became ring temps, not about what color they were given.
        unreachable = uncolorable_targets(webs, register_profile)
        if webs and len(unreachable) == len(webs):
            return "register-ring-only", "temp-fifo-phase"
        if _consistent_permutation(webs):
            return "register-permutation", "forced-color-oracle"
        return "allocation", "pool-position"
    if len(present) == 1:
        single = present[0]
        return {
            CONSTANT: ("constant", "constant-audit"),
            STRUCTURAL: ("structure", "structure-buckets"),
            SCHEDULE: ("schedule", "g0-schedule-probe"),
            COMMUTATIVE: ("commutative-order", "ast-shape"),
        }[single]
    composition = ", ".join(f"{name}:{counts[name]}" for name in present)
    _, playbook = _verdict(
        {present[0]: counts[present[0]]}, lanes, webs, register_profile
    )
    return f"mixed({composition})", playbook


def _frame_layout_only(
    rows: Sequence[AlignedRow],
    target_frame_size: int | None,
    candidate_frame_size: int | None,
) -> bool:
    """Recognize the symmetric prologue/epilogue frame-size pair.

    This is intentionally stricter than "two constants plus a different frame":
    both differing instructions must be ``addiu sp,sp`` and their immediates
    must be exactly the extracted negative/positive frame sizes.  Any other
    constant remains a constant audit.
    """

    if (
        target_frame_size is None
        or candidate_frame_size is None
        or target_frame_size == candidate_frame_size
    ):
        return False
    differing = [
        row
        for row in rows
        if row.classification not in {MATCH, RELOCATION, DISPLACEMENT, POOL}
    ]
    if len(differing) != 2 or any(row.classification != CONSTANT for row in differing):
        return False

    pattern = re.compile(
        r"^addiu\s+\$?sp,\$?sp,(-?(?:0x[0-9a-f]+|\d+))$", re.IGNORECASE
    )

    def immediate(text: str | None) -> int | None:
        if text is None:
            return None
        match = pattern.match(text.replace("\t", " ").strip())
        return int(match.group(1), 0) if match else None

    pairs = [(immediate(row.target), immediate(row.candidate)) for row in differing]
    expected = {
        (target_frame_size, candidate_frame_size),
        (-target_frame_size, -candidate_frame_size),
    }
    return set(pairs) == expected


def _primary_class(counts: dict[str, int]) -> str | None:
    for name in MIXED_PRECEDENCE:
        if counts.get(name):
            return name
    if counts.get(POOL_LAYOUT):
        return POOL_LAYOUT
    return RELOCATION if counts.get(RELOCATION) else None


def _ring_only_caution(webs: Sequence[Web], register_profile: str) -> tuple[str, ...]:
    """Name the ring-only targets inside a residual that also has colored ones.

    The whole-residual case gets its own verdict. This is the mixed one, where
    a color lever is still worth running for part of the residual and cannot
    possibly move the rest.
    """

    unreachable = uncolorable_targets(webs, register_profile)
    if not unreachable or len(unreachable) == len(webs):
        return ()
    named = ", ".join(web.target for web in unreachable)
    return (
        f"NOTE: {len(unreachable)} of {len(webs)} substitutions want a "
        f"ring-only target register ({named}), which the era's coloring pass "
        "never hands out.",
        "      No color lever can move those sites; they are a "
        "web-existence question. Expect any color probe to close only the "
        "rest.",
    )


def _guidance(
    verdict: str,
    counts: dict[str, int],
    lanes: Sequence[Lane],
    webs: Sequence[Web],
    hunks: Sequence[Hunk],
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> tuple[str, ...]:
    """Return the lever family for the dominant class.

    Every line here is a field-note finding, not general advice: the point of
    the footer is to stop the next round from being spent on a dead family.

    These lines name the mechanism; they do not give the reader an address.
    `build_view` appends `field_guide.next_steps` for the playbook, which turns
    each named concept into a lever number, a one-line action, and a command to
    paste. The two are kept apart because this half is evidence-shaped -- it
    quotes counts and lanes from the run -- and that half is a fixed table.
    """

    lines: list[str] = []
    if verdict.startswith("mixed("):
        lines.append(
            "mixed residual: fix constants first (they cascade), structure "
            "second, register classes last."
        )
    if verdict == "frame-layout":
        return (
            "allocation and opcode schedule are exact; only the entry/exit "
            "stack adjustment differs.",
            "preserve the allocator-winning live ranges and recover the frame "
            "separately by shrinking, reusing, or eliminating local stack homes.",
            "ablate locals one at a time and retain a two-axis Pareto set "
            "(normalized residue, frame size); do not audit unrelated literals.",
        )
    primary = _primary_class(counts)
    if primary is None:
        return (
            "aligned instructions and relocation layout are identical for this "
            "function.",
            "run the project's normal collateral and full-output verification.",
        )
    if primary == POOL_LAYOUT:
        return (
            f"{counts[POOL_LAYOUT]} literal-pool access(es) resolve to a "
            "different slot, width, or anchor correspondence; the remaining "
            "pool sites agree and are not reported.",
            "this is a literal question, not an allocation one: audit the "
            "constants and their order, and check whether the candidate emits "
            "a slot the target does not (or shares one it does not share).",
        )
    if primary == RELOCATION:
        return (
            "every aligned difference is a linker-controlled relocation field.",
            "do not mutate source; verify with the project's link or ROM check.",
        )
    if primary == CONSTANT:
        lines.extend(
            [
                "audit the flag, enum, or literal against the target assembly "
                "FIRST: the assembly encodes the truth.",
                "one wrong identifier can present as a large structural cascade "
                "(183 words from a single flag mix-up).",
                "after fixing a constant, re-derive any fakes: they may have "
                "been fitted to the wrong body.",
                "a literal search is outside decomp_permuter's mutation space; "
                "this is hand work.",
            ]
        )
    elif primary == STRUCTURAL:
        first = hunks[0].hunk if hunks else 1
        lines.extend(
            [
                f"work the largest hunk first (hunk {first} is the earliest); "
                "bucket by region above ~500 instructions.",
                "if a hunk starts at a constant materialization (lui/andi/li), "
                "audit that constant before anything else.",
                "hold allocator experiments until the instruction count and "
                "opcode schedule stabilize.",
            ]
        )
    elif primary == SCHEDULE:
        lines.extend(
            [
                "equal instruction multiset in a different order: this is late "
                "scheduling, not allocation.",
                "recompile the candidate with -g0 as an ownership probe. A "
                "collapse proves debug line metadata constrains the -g3 "
                "schedule and that as1 can reach the target ordering.",
                "a -g0 collapse does not prove source correctness: a freer "
                "scheduler can rescue a non-original expression or statement "
                "shape. Compare topology and line tags before ending source "
                "search.",
                "statement and expression grouping is the source lever; "
                "replay-as1 tests whether as1 owns the ordering.",
            ]
        )
    elif primary == COMMUTATIVE:
        lines.extend(
            [
                "same opcode and operand multiset with the pair swapped: front-end "
                "AST shape, not allocation.",
                "`a | b` versus `b | a` canonicalizes identically (dead family); "
                "`x |= y` is a distinct AST and flips the emitted operand order.",
                "do not trace the allocator for this residual.",
            ]
        )
    elif verdict == "phase-shift":
        lane = next(
            (item for item in lanes if item.rotation and item.divergence is not None),
            None,
        )
        where = ""
        if lane is not None and lane.divergence is not None:
            where = (
                f" ({lane.classification} lane, slot {lane.divergence}, "
                f"aligned row {lane.divergence_row}, rotation +{lane.rotation})"
            )
        lines.extend(
            [
                f"one upstream event, not {counts.get(REGISTER, 0)} sites{where}.",
                "perturb the PRECEDING block: hoist a call-argument expression "
                "into a named local, which reorders value deaths.",
                "or materialize a phantom pool get with `(x == C) != 0` inside a "
                "real `if`; a bare discarded expression is dropped with no "
                "codegen effect.",
                "do not fix the divergent sites individually; declaration-order "
                "permutation is a dead family here.",
            ]
        )
    elif verdict == "register-ring-only":
        unreachable = uncolorable_targets(webs, register_profile)
        named = ", ".join(
            f"{web.target} (candidate {web.candidate})" for web in unreachable
        )
        lines.extend(
            [
                f"every target register here is ring-only: {named}. The era's "
                "coloring pass never hands these out, so no color reaches "
                "them.",
                "this is a web-existence problem, not a color problem: the "
                "question is which values became block-local temps, not what "
                "color a colored web was given.",
                "`forced-color-oracle` and `pool-position` are dead families "
                "for this residual -- a forced color cannot cross the "
                "boundary between the two allocators.",
                "run `decomp-workbench view --register-profile` to confirm "
                "the era table this claim rests on before spending a round on "
                "it.",
            ]
        )
    elif verdict == "register-permutation":
        mapping = ", ".join(f"{web.target}->{web.candidate}" for web in webs)
        lines.extend(
            [
                f"all visible register differences form one bijection ({mapping}): "
                "report one downstream allocation outcome, not N sites.",
                "one visible bijection does NOT prove one source web or one source "
                "edit: inspect the desired color's interference producers; a "
                "staggered ladder of invisible blockers can cause the outcome.",
                "callee-saved tie-breaks resist blind source search; use a forced "
                "color probe to measure the smallest causal web set before choosing "
                "more variants.",
            ]
        )
        lines.extend(_ring_only_caution(webs, register_profile))
    else:
        lines.extend(
            [
                "register allocation differs with no consistent permutation. "
                "Name the family before searching:",
                "  temp-queue phase: perturb the preceding block, since value "
                "deaths set the phase entering it.",
                "  pool position: dead-web placement (`if (g) {}`) takes the NEXT "
                "FREE slot and cannot reach past a live web.",
                "  coalescing: return type (void versus implicit int) or CSE "
                "multiplicity.",
                "capture a globalcolor or ugen pool trace only if an instrumented "
                "toolchain is already configured.",
            ]
        )
        lines.extend(_ring_only_caution(webs, register_profile))
    return tuple(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _hunks(rows: Sequence[AlignedRow]) -> tuple[Hunk, ...]:
    hunks: list[Hunk] = []
    current: list[AlignedRow] = []

    def flush() -> None:
        if not current:
            return
        classes: dict[str, int] = {}
        for row in current:
            classes[row.classification] = classes.get(row.classification, 0) + 1
        if len(classes) == 1:
            label = next(iter(classes))
        else:
            label = (
                "mixed("
                + ", ".join(
                    f"{name}:{classes[name]}" for name in CLASS_ORDER if name in classes
                )
                + ")"
            )
        target_indexes = [
            row.target_index for row in current if row.target_index is not None
        ]
        candidate_indexes = [
            row.candidate_index for row in current if row.candidate_index is not None
        ]
        target_addresses = [
            row.target_address for row in current if row.target_address is not None
        ]
        candidate_addresses = [
            row.candidate_address
            for row in current
            if row.candidate_address is not None
        ]
        hunks.append(
            Hunk(
                hunk=len(hunks) + 1,
                classification=label,
                start=current[0].index,
                end=current[-1].index,
                target_range=(
                    (min(target_indexes), max(target_indexes))
                    if target_indexes
                    else None
                ),
                candidate_range=(
                    (min(candidate_indexes), max(candidate_indexes))
                    if candidate_indexes
                    else None
                ),
                target_bytes=(
                    (min(target_addresses), max(target_addresses))
                    if target_addresses
                    else None
                ),
                candidate_bytes=(
                    (min(candidate_addresses), max(candidate_addresses))
                    if candidate_addresses
                    else None
                ),
                classes=classes,
            )
        )
        current.clear()

    for row in rows:
        if row.reported:
            current.append(row)
        else:
            flush()
    flush()
    return tuple(hunks)


def _runs(labels: Sequence[str]) -> list[tuple[int, int]]:
    """Return inclusive ranges of consecutive rows that need reporting.

    ``match``, ``displacement``, ``relocation`` and the two pool classes do not
    start a run: none is a source difference of the kind a run describes.
    Letting an alignment-controlled branch offset open a run would scatter one
    insertion across every branch that spans it; letting a relocated or
    pool-anchored row open one would relabel linker metadata as schedule.
    """

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, label in enumerate(labels):
        if label in {MATCH, DISPLACEMENT, RELOCATION, POOL, POOL_LAYOUT}:
            if start is not None:
                runs.append((start, index - 1))
                start = None
        elif start is None:
            start = index
    if start is not None:
        runs.append((start, len(labels) - 1))
    return runs


def _relabel_reorderings(
    labels: list[str],
    skeleton: Sequence[tuple[str, int | None, int | None]],
    target_keys: Sequence[str],
    candidate_keys: Sequence[str],
) -> None:
    """Promote pure reorderings from ``structural`` to ``schedule``.

    Opcode-level LCS reports a swap of two differently-named instructions as an
    adjacent delete and insert, which reads as new structure by volume.  A run
    whose two sides carry the same instructions in a different order is a late
    scheduling decision. Keys mask linker-controlled relocation fields, so
    unrelated jump-table addends elsewhere in the function cannot hide that
    fact.
    """

    def sides(start: int, end: int) -> tuple[list[str], list[str]]:
        left = [
            target_keys[index]
            for _, index, _ in skeleton[start : end + 1]
            if index is not None
        ]
        right = [
            candidate_keys[index]
            for _, _, index in skeleton[start : end + 1]
            if index is not None
        ]
        return sorted(left), sorted(right)

    runs = _runs(labels)
    if runs and sorted(target_keys) == sorted(candidate_keys) and target_keys:
        # Whole-function reordering: equal instruction multiset, different order.
        # The run labels are irrelevant here.  Two same-opcode instructions that
        # swapped places pair up as register differences, not as a delete beside
        # an insert, and counting those as allocation sends the reader to the
        # allocator for a scheduling decision.
        for start, end in runs:
            for index in range(start, end + 1):
                labels[index] = SCHEDULE
        return
    for start, end in runs:
        left, right = sides(start, end)
        if left and left == right:
            for index in range(start, end + 1):
                labels[index] = SCHEDULE
    _relabel_displaced_rows(labels, skeleton, target_keys, candidate_keys)


def _relabel_displaced_rows(
    labels: list[str],
    skeleton: Sequence[tuple[str, int | None, int | None]],
    target_keys: Sequence[str],
    candidate_keys: Sequence[str],
) -> None:
    """Promote a moved instruction whose delete and insert land in two runs.

    An instruction that slides several slots inside a block produces one LCS
    deletion and one insertion with matching rows between them, so they fall in
    *different* runs and neither run's own two sides balance. The whole-function
    rule does not reach it either, because it requires the entire function's
    multisets to agree and any unrelated register residual breaks that.

    The rows left over were labelled `structural`, which routes the reader to
    "fix structure first" for what is a scheduling decision -- the wrong order
    of work, and a different playbook. So the balance is checked over exactly
    the rows in question: if everything deleted is also inserted, nothing was
    added or removed and every one of those rows is a move.
    """

    deleted: list[str] = []
    inserted: list[str] = []
    displaced: list[int] = []
    for index, (_, target_index, candidate_index) in enumerate(skeleton):
        if labels[index] != STRUCTURAL:
            continue
        if target_index is not None and candidate_index is None:
            deleted.append(target_keys[target_index])
            displaced.append(index)
        elif candidate_index is not None and target_index is None:
            inserted.append(candidate_keys[candidate_index])
            displaced.append(index)
    if not displaced or sorted(deleted) != sorted(inserted):
        return
    for index in displaced:
        labels[index] = SCHEDULE


def _pool_operand_only(target_text: str, candidate_text: str) -> bool:
    """Return whether two aligned rows differ in nothing but their immediates.

    The pool resolution may only speak for the operand it resolved.  Masking
    every immediate and requiring the rest of the text to be identical keeps a
    row that also moved a register, or changed an opcode, out of the pool
    verdict entirely -- it stays whatever the classifier called it.
    """

    return IMMEDIATE_RE.sub("@imm", target_text) == IMMEDIATE_RE.sub(
        "@imm", candidate_text
    )


def _relabel_pool_rows(
    labels: list[str],
    skeleton: Sequence[tuple[str, int | None, int | None]],
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    target_text: Sequence[str],
    candidate_text: Sequence[str],
) -> PoolComparison | None:
    """Re-class relocated literal accesses by the slot they resolve to.

    Whether a literal is reached through one named symbol per datum or through
    one section symbol plus an addend is a property of the two symbol tables,
    not of the code, and it is decided before either object is written.  The
    rows it produces used to be counted as `relocation` evidence -- 88 of them
    on one recorded pair whose pool accesses agree at every site.

    Rows whose slots correspond become `pool` and stop being reported; rows
    whose slots do not become `pool_layout`, which is the question those 88
    rows were burying.
    """

    target_pool = pool_accesses(target)
    candidate_pool = pool_accesses(candidate)
    if not target_pool or not candidate_pool:
        return None
    pairs: list[tuple[int, PoolAccess, PoolAccess]] = []
    eligible: list[int] = []
    for row, (_, target_index, candidate_index) in enumerate(skeleton):
        if target_index is None or candidate_index is None:
            continue
        left = target_pool.get(target_index)
        right = candidate_pool.get(candidate_index)
        if left is None or right is None or not comparable(left, right):
            continue
        pairs.append((row, left, right))
        if labels[row] in POOL_RELABEL_FROM and _pool_operand_only(
            target_text[target_index], candidate_text[candidate_index]
        ):
            eligible.append(row)
    comparison = compare_pool_accesses(
        pairs,
        target_accesses=target_pool,
        candidate_accesses=candidate_pool,
    )
    for row in eligible:
        if row in comparison.agreeing:
            labels[row] = POOL
        elif row in comparison.differing:
            labels[row] = POOL_LAYOUT
    return comparison


def _schedule_identity(instruction: Instruction, normalized: str) -> str:
    """Return an instruction identity stable across linker-controlled fields."""

    if ALIGNED_TARGET in normalized:
        return normalized
    mask, unknown = relocation_field_mask(instruction)
    if unknown:
        return f"{instruction.word}:{normalized}"
    kept_word = instruction.word_value & (~mask & 0xFFFFFFFF)
    kinds = ",".join(_relocation_kind_signature(instruction))
    return f"{kept_word:08x}:{kinds}"


def _unknown_relocations(*streams: Sequence[Instruction]) -> list[str]:
    """Return relocation kinds with no known field mask.

    Guessing a mask would turn a linker-controlled field into a false source
    problem, or worse, excuse a real one.  The classifier stays conservative and
    the signature says so out loud.
    """

    kinds: set[str] = set()
    for stream in streams:
        for item in stream:
            kinds.update(relocation_field_mask(item)[1])
    return sorted(kinds)


def _signature(
    rows: Sequence[AlignedRow],
    lanes: Sequence[Lane],
    prefix_exact: int | None,
    unknown_relocations: Sequence[str] = (),
) -> tuple[str, ...]:
    signature: list[str] = []
    signature.append(
        "prefix-exact@all" if prefix_exact is None else f"prefix-exact@{prefix_exact}"
    )
    for lane in lanes:
        if lane.divergence is not None:
            signature.append(
                f"state-divergence@{lane.classification}:{lane.divergence}"
            )
    if prefix_exact is not None:
        row = rows[prefix_exact]
        earliest = [
            lane.divergence_row for lane in lanes if lane.divergence_row is not None
        ]
        if (
            row.classification in {REGISTER, COMMUTATIVE}
            and earliest
            and min(earliest) <= prefix_exact
        ):
            signature.append("register-first-divergence")
    signature.extend(f"unknown-relocation:{kind}" for kind in unknown_relocations)
    return tuple(signature)


def build_view(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None = None,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
    warnings: Sequence[str] = (),
) -> MechanismView:
    """Align two instruction streams and classify the residual by mechanism."""

    try:
        profile = REGISTER_CLASS_PROFILES[register_profile]
    except KeyError:
        known = ", ".join(sorted(REGISTER_CLASS_PROFILES))
        raise ValueError(
            f"unknown register profile {register_profile!r}; known profiles: {known}"
        ) from None
    if not target or not candidate:
        missing = "target" if not target else "candidate"
        raise ValueError(
            f"no instructions to align on the {missing} side; "
            "check the symbol name and the section"
        )

    skeleton = _skeleton(target, candidate)
    row_of_target = {
        target_index: row
        for row, (_, target_index, _) in enumerate(skeleton)
        if target_index is not None
    }
    row_of_candidate = {
        candidate_index: row
        for row, (_, _, candidate_index) in enumerate(skeleton)
        if candidate_index is not None
    }
    target_addresses = _address_index(target)
    candidate_addresses = _address_index(candidate)
    target_text = [
        normalized_text(
            item, address_index=target_addresses, row_of_index=row_of_target
        )
        for item in target
    ]
    candidate_text = [
        normalized_text(
            item, address_index=candidate_addresses, row_of_index=row_of_candidate
        )
        for item in candidate
    ]
    target_schedule_keys = [
        _schedule_identity(item, text)
        for item, text in zip(target, target_text, strict=True)
    ]
    candidate_schedule_keys = [
        _schedule_identity(item, text)
        for item, text in zip(candidate, candidate_text, strict=True)
    ]

    labels: list[str] = []
    for tag, target_index, candidate_index in skeleton:
        if tag == "equal" and target_index is not None and candidate_index is not None:
            labels.append(
                classify_pair(
                    target[target_index],
                    candidate[candidate_index],
                    target_text=target_text[target_index],
                    candidate_text=candidate_text[candidate_index],
                )
            )
        else:
            labels.append(STRUCTURAL)
    _relabel_reorderings(
        labels,
        skeleton,
        target_schedule_keys,
        candidate_schedule_keys,
    )
    pool = _relabel_pool_rows(
        labels, skeleton, target, candidate, target_text, candidate_text
    )

    rows: list[AlignedRow] = []
    counts: dict[str, int] = {name: 0 for name in CLASS_ORDER}
    for index, (_, target_index, candidate_index) in enumerate(skeleton):
        target_item = target[target_index] if target_index is not None else None
        candidate_item = (
            candidate[candidate_index] if candidate_index is not None else None
        )
        classification = labels[index]
        target_registers = (
            tuple(register_operands(target_item.assembly))
            if target_item is not None
            else ()
        )
        candidate_registers = (
            tuple(register_operands(candidate_item.assembly))
            if candidate_item is not None
            else ()
        )
        rows.append(
            AlignedRow(
                index=index,
                classification=classification,
                target_index=target_index,
                candidate_index=candidate_index,
                target=target_item.assembly if target_item is not None else None,
                candidate=(
                    candidate_item.assembly if candidate_item is not None else None
                ),
                target_address=(
                    target_item.address if target_item is not None else None
                ),
                candidate_address=(
                    candidate_item.address if candidate_item is not None else None
                ),
                target_registers=target_registers,
                candidate_registers=candidate_registers,
                substitutions=(
                    _substitutions(target_registers, candidate_registers)
                    if classification in {REGISTER, COMMUTATIVE}
                    else ()
                ),
            )
        )
        counts[classification] = counts.get(classification, 0) + 1

    lanes = _build_lanes(rows, profile)
    webs = _build_webs(rows)
    hunks = _hunks(rows)
    prefix_exact = _prefix_exact(rows)
    target_frame = frame_size(_joined(target))
    candidate_frame = frame_size(_joined(candidate))
    verdict, playbook = _verdict(counts, lanes, webs, register_profile)
    if _frame_layout_only(rows, target_frame, candidate_frame):
        verdict, playbook = "frame-layout", "stack-frame-recovery"
    return MechanismView(
        symbol=symbol,
        target=target_name,
        candidate=candidate_name,
        register_profile=register_profile,
        target_instructions=len(target),
        candidate_instructions=len(candidate),
        target_frame_size=target_frame,
        candidate_frame_size=candidate_frame,
        counts=counts,
        verdict=verdict,
        playbook=playbook,
        signature=_signature(
            rows,
            lanes,
            prefix_exact,
            _unknown_relocations(target, candidate),
        ),
        prefix_exact=prefix_exact,
        rows=tuple(rows),
        hunks=hunks,
        lanes=lanes,
        webs=webs,
        guidance=(
            _guidance(verdict, counts, lanes, webs, hunks, register_profile)
            + next_steps(playbook)
            # Last, on purpose: the levers above are what to try, and this is
            # what to do when they run out. A reader who stops at the end of
            # the footer used to stop at "no source lever".
            + (
                PERMUTER_ROUTING_STEPS
                if routing_for(verdict, counts, warnings) == ROUTING_PERMUTER_FIRST
                else ()
            )
        ),
        warnings=tuple(warnings),
        pool=pool,
    )


def aligned_class_counts(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> dict[str, int]:
    """Return the aligned residual counts for one pair of instruction streams.

    This is the analysis :func:`build_view` already performs, reduced to the
    numbers a comparison reports.  It exists so that ``compare`` can rank on
    aligned counts without growing a second aligner: two LCS implementations of
    one idea would eventually put different numbers under the same name in two
    commands, which is the class of defect the shared commutative predicate and
    the shared metric registry were introduced to end.
    """

    view = build_view(
        target,
        candidate,
        target_name="",
        candidate_name="",
        register_profile=register_profile,
    )
    return {name: view.counts.get(name, 0) for name in RESIDUAL_CLASSES}


def _joined(instructions: Iterable[Instruction]) -> str:
    return "\n".join(item.assembly for item in instructions)
