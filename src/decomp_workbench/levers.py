"""The source edit a residual's evidence supports, or the proof there is none.

`diagnose` names the mechanism, the owning pass, and how close a source edit
gets to it. It stops one step short of the thing an analyst actually types.
Across 22 Mickey's Speedway USA targets with measured work on 2026-09-02/03,
four residual classes closed ten -- six exact, four proved unreachable -- and
in every one of them the distance between the verdict on screen and the edit in
the file was a piece of arithmetic somebody did by hand, from evidence the tool
already held or could read from a trace it already parses.

This module does that arithmetic, and only that arithmetic:

* **`stack-home`** reads the frame pair and, when a CDX frame ladder is
  supplied, the declared-local count. Homes descend from the frame top in
  declaration order, so a displaced home is a *position in the declaration
  list*, and a frame delta is a *count*.
* **`temp-ring`** reads the `DKWB_UGEN_TRACE` free-list records, which carry
  ugen's current source line, and reports pops per line against the target's
  temp lane. A pop is bought and sold by three known constructs.
* **`line-order`** reads the `DKWB-EMIT-V1` emit-provenance records and the
  line-order conflicts already computed from them, which name the pair as1's
  minimised line key decides and the join that removes the separation.
* **`pool-rotation`** / **`pool-population`** read the two pool lanes'
  *lengths* first. Equal lengths make a colour-only residual a rotation, and
  a rotation is decided by web numbering under whichever sweep owns the webs
  -- which the CDX colouring records name and two disassemblies cannot.
  Unequal lengths make it a population difference, which no colour lever
  reaches, and that gate is the one `overlay43FilterImage` spent a lane
  proving is needed.
* **`unreachable`** carries the four proofs that closed a target by ruling it
  out, so the next analyst does not spend a day re-deriving one. Three are
  catalogue entries keyed on the owning pass; the fourth, as1 readiness, is a
  *measurement* when a `cc -Wa,-R` trace is supplied, because the deciding key
  of a selection says outright whether the line lever can reach it.

**The honesty rule, and it is the whole design.** A class is named from
evidence or not at all. Where the deciding input is a trace nobody captured,
the report says which trace, in the command that captures it, and leaves
`edit_family` null. Guessing an edit family from a residual's shape would
reproduce exactly the failure this module was built from: `overlay40UpdateEntries`
was recorded "not reachable by statement placement" on 2026-09-02 by an analyst
with four regressed variants and no emit trace, and matched the same day once
the trace existed. The verdict was a false floor, and it was manufactured by
answering a question the evidence had not been asked.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .as1_reorganize import Selection
from .cascade import CdxLog
from .emit_provenance import EmitEvent, line_order_conflicts
from .frame_ladder import Ladder
from .globalcolor import (
    AllocatorWebDecision,
    color_for_register,
    optional_integer,
)
from .trace import TraceEvent, register_name
from .view import (
    OWNING_PASS_CFE,
    OWNING_PASS_G0_SCHEDULER,
    OWNING_PASS_STACK_HOME,
    OWNING_PASS_UGEN_RING,
    OWNING_PASS_UOPT_COLOR,
    MechanismView,
)

__all__ = [
    "CONSTRUCT_VALUES",
    "FORCE_REACHABILITY_VALUES",
    "LEVER_CLASS_VALUES",
    "LEVER_LINE_ORDER",
    "LEVER_NONE_KNOWN",
    "LEVER_POOL_POPULATION",
    "LEVER_POOL_ROTATION",
    "LEVER_SCHEMA",
    "LEVER_STACK_HOME",
    "LEVER_TEMP_RING",
    "LEVER_UNREACHABLE",
    "LINE_ORDER_FAMILIES",
    "POOL_ROTATION_FAMILIES",
    "REACHABILITY_PROVEN",
    "REACHABILITY_UNREACHABLE",
    "STACK_HOME_FAMILIES",
    "TEMP_RING_FAMILIES",
    "UNREACHABLE_PROOFS",
    "EditFamily",
    "Lever",
    "SweepRecord",
    "UnreachableProof",
    "classify_construct",
    "force_reachability",
    "format_lever",
    "lever_for",
    "pops_by_line",
    "readiness_keys",
    "sweep_records",
    "tie_groups",
]

#: The sub-document this module contributes. It is merged into a host report
#: under `lever`/`lever_schema` and never renames its host.
LEVER_SCHEMA = "decomp-workbench-lever-v1"

LEVER_STACK_HOME = "stack-home"
LEVER_TEMP_RING = "temp-ring"
LEVER_LINE_ORDER = "line-order"
LEVER_POOL_ROTATION = "pool-rotation"
LEVER_POOL_POPULATION = "pool-population"
LEVER_UNREACHABLE = "unreachable"
LEVER_NONE_KNOWN = "none-known"

#: Every value `lever_class` can take, in the order this module tries them.
LEVER_CLASS_VALUES: tuple[str, ...] = (
    LEVER_UNREACHABLE,
    LEVER_STACK_HOME,
    LEVER_TEMP_RING,
    LEVER_LINE_ORDER,
    LEVER_POOL_POPULATION,
    LEVER_POOL_ROTATION,
    LEVER_NONE_KNOWN,
)

#: What a recorded `CDX_FORCE` experiment says about the target's assignment.
#:
#: These are answers about the *web graph*, not about the source: `proven`
#: says uopt accepted the forced colours and the object went to words=0, so
#: every colour in the residual is legal and what is missing is a spelling;
#: `unreachable` says the pass declined the force or paid for it in
#: instructions, so no renumbering reaches it. Absent a recorded force there
#: is no third value -- the field is null and the block asks for the run.
REACHABILITY_PROVEN = "proven"
REACHABILITY_UNREACHABLE = "unreachable"

FORCE_REACHABILITY_VALUES: tuple[str, ...] = (
    REACHABILITY_PROVEN,
    REACHABILITY_UNREACHABLE,
)


@dataclass(frozen=True)
class EditFamily:
    """One source edit, when it applies, and the target that proved it."""

    name: str
    edit: str
    #: What in the measurement selects this family over its siblings. Printed
    #: beside every alternative, so a reader picking between two of them is
    #: picking on a number rather than on which one was listed first.
    discriminator: str
    citation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "family": self.name,
            "edit": self.edit,
            "discriminator": self.discriminator,
            "citation": self.citation,
        }


@dataclass(frozen=True)
class UnreachableProof:
    """Why a residual is not a source edit, and what would reopen it."""

    name: str
    proof: str
    citation: str
    reopens_when: str
    #: The residual shape this proof was measured on, in one sentence. When a
    #: predicate in :data:`PROOF_PRECONDITIONS` can see that shape in the
    #: evidence at hand, the proof *is* the verdict; otherwise it is printed
    #: under `see_also` and the reader checks the sentence themselves.
    precondition: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "unreachable_class": self.name,
            "proof": self.proof,
            "citation": self.citation,
            "reopens_when": self.reopens_when,
            "precondition": self.precondition,
        }


#: What a traced source line actually contains, as far as a line of C can be
#: read without a parser.
#:
#: This exists because the block once named `read-the-field-directly` for a
#: line whose local carries a cast integer constant. The pop count was right
#: and the edit was inert -- three spellings, one byte-identical object --
#: because L76 is measured on a *struct field* read through a local, and
#: nothing had checked that the line was one. A pop count says a line is the
#: one to edit; it does not say which law applies to it.
CONSTRUCT_FIELD_THROUGH_LOCAL = "field-through-local"
CONSTRUCT_SCALED_INDEX = "scaled-index"
CONSTRUCT_FUSED_ACCUMULATE = "fused-accumulate"
CONSTRUCT_CONSTANT = "constant"
CONSTRUCT_UNCLASSIFIED = "unclassified"

CONSTRUCT_VALUES: tuple[str, ...] = (
    CONSTRUCT_FIELD_THROUGH_LOCAL,
    CONSTRUCT_SCALED_INDEX,
    CONSTRUCT_FUSED_ACCUMULATE,
    CONSTRUCT_CONSTANT,
    CONSTRUCT_UNCLASSIFIED,
)

_COMMENT_RE = re.compile(r"/\*.*?\*/|//.*$")
_ASSIGN_RE = re.compile(r"(?<![=!<>+\-*/%&|^])=(?!=)")
_CAST_RE = re.compile(r"\(\s*[A-Za-z_][A-Za-z0-9_ *]*\)")
_LITERAL_RE = re.compile(
    r"^[-+~()\s]*(?:0[xX][0-9a-fA-F]+|\d+)[uUlLfF]*[-+*/|&^()\s0-9xXa-fA-FuUlL]*$"
)
_SUBSCRIPT_RE = re.compile(r"\[([^\]]*)\]")
#: A binary multiply: a `*` with a value, not a type or a statement, to its
#: left. Distinguishes `a * b` from the `*q` of a dereference.
_MULTIPLY_RE = re.compile(r"[A-Za-z0-9_\)\]]\s*\*")


def classify_construct(line: str) -> str:
    """Name the construct on one line of C, for the pop-cost rules only.

    Deliberately shallow, and the shallowness is the contract: this decides
    whether a law's *precondition* is visibly met, never what the line means.
    Anything it cannot place is `unclassified`, which suppresses the family
    rather than picking the nearest one.
    """

    text = _COMMENT_RE.sub("", line).strip().rstrip(";").strip()
    if not text:
        return CONSTRUCT_UNCLASSIFIED
    match = _ASSIGN_RE.search(text)
    right = text[match.end() :].strip() if match else text
    if not right:
        return CONSTRUCT_UNCLASSIFIED
    for subscript in _SUBSCRIPT_RE.findall(right):
        if "*" in subscript or "<<" in subscript:
            return CONSTRUCT_SCALED_INDEX
    bare = _CAST_RE.sub("", right).strip()
    # The fused accumulate is checked before the plain field read because its
    # shape contains one: `x = field + a * b` is L78's construct, and reading
    # it as L76's would name the wrong edit for the same line. The `*` has to
    # be a binary multiply: `n = *q + 1` is a dereference and an add, and
    # reading it as an accumulate names `split-the-accumulate` for a line the
    # rule was never measured on.
    if _MULTIPLY_RE.search(bare) and re.search(r"[+\-]", bare):
        return CONSTRUCT_FUSED_ACCUMULATE
    if "->" in right or re.search(r"[A-Za-z_0-9\])]\s*\.\s*[A-Za-z_]", right):
        return CONSTRUCT_FIELD_THROUGH_LOCAL
    if _LITERAL_RE.match(bare):
        return CONSTRUCT_CONSTANT
    return CONSTRUCT_UNCLASSIFIED


#: The three declaration-list edits that closed a stack-home residual.
#:
#: All three move the same quantity -- which slot a value lands on -- and they
#: differ only in whether the declared count falls, rises, or stays. That is
#: the discriminator, and it is readable from the frame pair without a trace.
STACK_HOME_FAMILIES: tuple[EditFamily, ...] = (
    EditFamily(
        name="drop-a-declared-local",
        edit=(
            "stop naming the value and repeat its expression at both uses, "
            "so it becomes a call-crossing common subexpression and is homed "
            "in the compiler-temp region instead of the declared one"
        ),
        discriminator=(
            "the candidate frame is larger than the target's, or one homed "
            "value sits one word from the target's home with the frame equal"
        ),
        citation=(
            "overlay34InitStorage, Mickey's Speedway USA, 2026-09-03: "
            "46/50 words to exact; the home moves sp+0x18 to sp+0x1C"
        ),
    ),
    EditFamily(
        name="reuse-an-existing-local-as-carrier",
        edit=(
            "carry the value in a local that is already dead at that point "
            "instead of declaring a second one; the declared count falls by "
            "one and a later spill moves one slot, at an unchanged "
            "instruction count"
        ),
        discriminator=(
            "the frames are equal and the displaced home moves by exactly one "
            "word while the instruction counts agree"
        ),
        citation=(
            "func_overlay_026_F0000B18_187AF10, Mickey's Speedway USA, "
            "2026-09-03: 129/131 words to exact, 131 words on both sides; "
            "the spill moves sp+0x40 to sp+0x44"
        ),
    ),
    EditFamily(
        name="declare-the-pair-later",
        edit=(
            "move the displaced declarations below the local whose slots they "
            "must follow; homes descend from the frame top in declaration "
            "order, so the fix is a position in the list and not a property "
            "of the values"
        ),
        discriminator=(
            "the frames are equal and two or more adjacent homes are "
            "displaced by the same amount"
        ),
        citation=(
            "overlay84InitializeAndUpdate, Mickey's Speedway USA, 2026-09-03: "
            "172/179 words to exact; the pair moves sp+0x4C/0x48 to "
            "sp+0x44/0x40"
        ),
    ),
)

#: The three constructs measured to buy or sell exactly one ugen ring pop.
TEMP_RING_FAMILIES: tuple[EditFamily, ...] = (
    EditFamily(
        name="read-the-field-directly",
        edit=(
            "read the struct field at its use instead of through a named "
            "local: a field read through a local costs one ring pop that a "
            "direct read does not"
        ),
        discriminator=(
            "a source line whose pops exceed the target's ring advance names "
            "a local that only carries a field"
        ),
        citation=(
            "overlay20UpdateObjectResource, Mickey's Speedway USA, "
            "2026-09-03: 90/98 words to exact, composed with the second family"
        ),
    ),
    EditFamily(
        name="scale-the-index-twice",
        edit=(
            "type the table as pairs and index the pair, so the index is "
            "scaled twice; the second scale burns an invisible temp between "
            "the base load and the shift and costs one more pop than a "
            "single scale, at an unchanged instruction count"
        ),
        discriminator=(
            "the candidate is one pop short of the target's ring advance at "
            "an indexed table read"
        ),
        citation=(
            "overlay20UpdateObjectResource and func_overlay_070_F00000D8, "
            "Mickey's Speedway USA, 2026-09-03: 165/171 words to exact on the "
            "second"
        ),
    ),
    EditFamily(
        name="split-the-accumulate",
        edit=(
            "split a fused expression into a pool-carried accumulate -- "
            "`x = a;` then `x += b * c;` -- so the field stays in the coloured "
            "web instead of being loaded into a ring temp; the pop count "
            "moves with it"
        ),
        discriminator=(
            "the pool lane differs in length as well as in content, so the "
            "residual is a web population difference and not a rotation"
        ),
        citation=(
            "func_overlay_070_F00000D8, Mickey's Speedway USA, 2026-09-03: "
            "the split makes the pool and fp lanes exact"
        ),
    ),
)

#: Which pop-cost rule each construct qualifies for.
#:
#: A construct with no entry here has no measured pop cost, and that is a
#: finding rather than a gap: the block says the line does not fit a rule
#: instead of naming the nearest family.
CONSTRUCT_FAMILIES: dict[str, str] = {
    CONSTRUCT_FIELD_THROUGH_LOCAL: "read-the-field-directly",
    CONSTRUCT_SCALED_INDEX: "scale-the-index-twice",
    CONSTRUCT_FUSED_ACCUMULATE: "split-the-accumulate",
}

#: The two ways a residual separated only by ugen's line stamps is closed.
LINE_ORDER_FAMILIES: tuple[EditFamily, ...] = (
    EditFamily(
        name="join-the-initialiser-to-the-loop-header",
        edit=(
            "put the initialiser on the loop header's physical line -- "
            "`count = 7; do {`, `entry = &table; do {` -- so the hoisted "
            "invariant, which carries the header's line, stops losing as1's "
            "minimised line key to a statement written above it"
        ),
        discriminator=(
            "a line-order conflict whose earlier record is an initialiser and "
            "whose later record is a loop-invariant address"
        ),
        citation=(
            "overlay40UpdateEntries, Mickey's Speedway USA, 2026-09-02: "
            "44/46 words to exact; func_overlay_047_F00009D0, 2026-09-03: "
            "10 to 6 words, one join per loop"
        ),
    ),
    EditFamily(
        name="change-the-hoist-birth-order",
        edit=(
            "spell the bound inline in the loop test instead of keeping it in "
            "a local, so it is hoisted after the count rather than before it; "
            "hoisted addresses are materialised in ugen's birth order and "
            "birth order follows source statement order"
        ),
        discriminator=(
            "the preheader materialises several invariant addresses and the "
            "conflict is between two of them, not between an initialiser and "
            "one of them"
        ),
        citation=(
            "func_overlay_014_F0000000, Mickey's Speedway USA, 2026-09-03: "
            "4 words to exact, composed with the line join"
        ),
    ),
)

#: The four proofs, keyed by the name a report prints.
#:
#: These exist so an analyst stops retrying them. Each one cost a day and
#: several builds, and each is a statement about a *mechanism*, not about a
#: function: the citation is the function it was measured on.
UNREACHABLE_PROOFS: dict[str, UnreachableProof] = {
    "as1-readiness": UnreachableProof(
        name="as1-readiness",
        proof=(
            "the two instructions are separated by as1's readiness keys, not "
            "by their source lines. In a block of N pre-branch nodes whose "
            "branch becomes ready at cycle N-1, exactly one node is left over "
            "and a leftover node always wins the delay slot; reaching the "
            "target's fill needs one fewer or one more node in the block, "
            "which is an instruction-count change and not a placement change"
        ),
        citation=(
            "overlay1FindNextAngle and its twin overlay1FindPreviousAngle "
            "(2 words each, 7 as1 traces and 3 full builds), "
            "overlay11UpdateMenu "
            "(every node in the block stamped with one line, so the line key "
            "has nothing to discriminate on), overlay33InitializeBuffers (the "
            "two nodes differ on aftercycles), overlay1ResolvePathPoint "
            "(equal aftercycles, decided on besttime) -- Mickey's Speedway "
            "USA, 2026-09-02/03"
        ),
        reopens_when=(
            "as1's besttime derivation is modelled, so a candidate's release "
            "order can be predicted instead of only observed"
        ),
        precondition=(
            "an as1 trace in which every selection in scope is decided above "
            "the line key"
        ),
    ),
    "uopt-address-folding": UnreachableProof(
        name="uopt-address-folding",
        proof=(
            "uopt reassociates an induction base against whichever live "
            "pointer it folds with, and the fold is insensitive to where the "
            "definition is written: moving the definition below the field "
            "stores, into the loop's init clause, and removing the local "
            "entirely all leave it intact, and one of those compiled "
            "byte-identically to the form it replaced"
        ),
        citation=(
            "func_overlay_038_F0000000, Mickey's Speedway USA, 2026-09-03: "
            "7 words, of which 6 are the emission order that follows from the "
            "base"
        ),
        reopens_when=(
            "a source shape exists in which the target pointer is not a "
            "constant offset from a live base at the point the induction "
            "variable is formed"
        ),
        precondition=(
            "the two sides form one address from different base pointers, "
            "which two disassemblies do not distinguish from a colour "
            "difference -- check it by hand"
        ),
    ),
    "uopt-coalescing-tie-break": UnreachableProof(
        name="uopt-coalescing-tie-break",
        proof=(
            "the web is coloured on a tie between the call's argument "
            "register and the return register, and the two locals the pool "
            "lane suggests merging are already coalesced -- merging them by "
            "hand produced a byte-identical object -- so no source form "
            "expresses the choice"
        ),
        citation=(
            "overlay59PrepareEntry, Mickey's Speedway USA, 2026-09-03: "
            "9 words, one web at 7 sites"
        ),
        reopens_when=(
            "a forced-colour oracle is available: an instrumented uopt "
            "carrying the CDX globalcolor profile, which decides the tie "
            "directly"
        ),
        precondition=(
            "the colourer owns the residual and it is one consistent web "
            "substitution across its sites, between the registers a call "
            "takes its argument in and returns in"
        ),
    ),
    "cfe-pointer-add-order": UnreachableProof(
        name="cfe-pointer-add-order",
        proof=(
            "at the mismatching pointer-add expression the shard records "
            "typed-pointer commutations, casts and assignment forms as "
            "exhausted. Byte-offset arithmetic is the one spelling that did "
            "move the temp order, and it is already retained: it takes the "
            "baseline's pointer/mask/scale to mask/scale/pointer, where the "
            "target wants mask/pointer/scale"
        ),
        citation=(
            "levelFreeAll, Mickey's Speedway USA, undated triage shard: "
            "114/117 words after the retained rewrite, up from 112/117; "
            "36/36 relocation offsets, types and identities exact; a "
            "fidelity-gated ugen source-line trace supplied the order. A "
            "resident function, not part of the overlay lever cohort"
        ),
        reopens_when=(
            "a source form yields mask, pointer, scale -- the one order no "
            "tried spelling produced"
        ),
        precondition=(
            "the residual is the temp order at a pointer add, which needs "
            "the expression in front of you -- check it by hand"
        ),
    ),
}


#: The registers a call's argument and return values are coloured into, and
#: the only ones L82's tie is between.
ARGUMENT_RETURN_REGISTERS: frozenset[str] = frozenset(
    {"v0", "v1", "a0", "a1", "a2", "a3"}
)


def _coalescing_tie_applies(view: MechanismView) -> bool:
    """Whether the coalescing tie-break's measured shape is the one on screen.

    One web, substituted consistently wherever it appears, under the colourer
    -- and both of its registers drawn from the argument/return set, because
    that is the tie the proof is about. `overlay59PrepareEntry` colours one
    web into the argument register where the target uses the return register;
    `debug_text_width` is `v1`/`v0`. A lone `s0`->`s1` web is also one web
    under the colourer and this proof says nothing about it, so it is left
    where an unmet precondition belongs: under `see_also`.
    """

    if len(view.webs) != 1:
        return False
    web = view.webs[0]
    return {web.target, web.candidate} <= ARGUMENT_RETURN_REGISTERS


#: When a catalogue proof's precondition is decidable from the evidence the
#: view already carries, it is checked here and the proof becomes the verdict.
#:
#: Only the shapes that are genuinely visible in two disassemblies appear. A
#: proof with no entry stays under `see_also`, with its `precondition`
#: sentence for the reader to check -- printing it as a verdict from a shape
#: nobody measured would be the guess this module refuses.
PROOF_PRECONDITIONS: dict[str, Callable[[MechanismView], bool]] = {
    "uopt-coalescing-tie-break": _coalescing_tie_applies,
}

#: Which catalogue proof an owning pass points at when nothing else fired.
#:
#: Keyed on the owning pass because that is what `diagnose` already measures
#: or reads off the shape; naming a proof from the residual's shape alone
#: would be the guess this module refuses to make, so these are printed as
#: `see_also`, never as the diagnosis.
PASS_PROOFS: dict[str, tuple[str, ...]] = {
    OWNING_PASS_CFE: ("cfe-pointer-add-order",),
    OWNING_PASS_UOPT_COLOR: (
        "uopt-coalescing-tie-break",
        "uopt-address-folding",
    ),
    OWNING_PASS_G0_SCHEDULER: ("as1-readiness",),
}

#: What to run when the class is named but its deciding evidence is absent.
CAPTURE_LADDER = (
    "declared-local count: rebuild with CDX_SYMTAB=1 on the instrumented "
    "uopt and pass the log as --ladder (decomp-workbench frame-ladder reads "
    "the same file)"
)
CAPTURE_RING = (
    "pops per source line: rebuild with DKWB_UGEN_TRACE=1 on a cc carrying "
    "instrument-ugen's free-list hooks and pass the log as --ring-trace"
)
CAPTURE_SOURCE = (
    "the traced line's construct: pass the candidate's C with --source, so "
    "the pop-cost rule a line qualifies for is checked rather than assumed"
)
CAPTURE_EMIT = (
    "line-order conflicts: rebuild with DKWB_UGEN_SCHED=1 on a cc carrying "
    "instrument-ugen --emit-provenance and pass the log as --emit-trace"
)
CAPTURE_AS1 = (
    "as1 selection keys: rebuild the same compile with cc -Wa,-R and pass "
    "the assembler's trace as --as1-trace (no patched compiler; the object "
    "is byte-identical with -R on)"
)

#: The pool-rotation edits, in the order this module ranks them.
#:
#: Both are renumbering edits in the sense that matters: neither adds or
#: removes an instruction, and both are aimed at *which web number* a value
#: gets, because that is the only input either colouring sweep reads once the
#: saves are equal. The second is ranked below the first and says so: changing
#: a save means changing use counts or loop depth, which changes the
#: instruction stream, and a rotation is by definition a residual in which the
#: instruction stream is already right.
POOL_ROTATION_FAMILIES: tuple[EditFamily, ...] = (
    EditFamily(
        name="store-site-truncation",
        edit=(
            "declare the truncated local at its narrow type and drop the "
            "explicit cast, so the truncation happens at the STORE rather "
            "than in the expression: uopt numbers the synthetic truncation "
            "temp where the truncation is written, and a store is numbered "
            "LHS before RHS. Preconditions, both required and both measured: "
            "the value must not be passed on after the narrowing store (on "
            "`overlay4UpdateObjectMotion` the else-branch store to the local "
            "was dropped and the call result passed directly, an edit already "
            "proved byte-identical, so the `s16` store "
            "could not truncate a value the call still needed), and the "
            "truncation must survive cfe -- confirm it with a second capture"
        ),
        discriminator=(
            "one of the webs in the residual is the synthetic intermediate "
            "of a two-step narrowing cast, which `CDX_DETAIL_WEB` reports as "
            "a type=4 expression web with no symbol"
        ),
        citation=(
            "overlay4UpdateObjectMotion, Mickey's Speedway USA, 2026-09-03: "
            "8 differing words to 3, seven builds. Declaring `delta` as "
            "`s16` renumbered the truncation temp 48 -> 49 and closed both "
            "threshold webs, frame unchanged at -0x60, and the result "
            "reproduced byte-identically under the stock toolchain "
            "(sha1 8f11fe39ee5d)"
        ),
    ),
    EditFamily(
        name="change-the-save-cost",
        edit=(
            "change the web's use count or its loop depth so its save "
            "crosses the boundary that orders it -- and expect the "
            "instruction stream to move with it, which is why this is ranked "
            "last"
        ),
        discriminator=(
            "the two webs are NOT tied on save: p1 takes the largest save "
            "first and reads the web number only inside a tie group, so "
            "nothing that renumbers reorders them"
        ),
        citation=(
            "overlay4UpdateObjectMotion, Mickey's Speedway USA, 2026-09-03: "
            "the p1 selection order is saves 7.0, 4.0, 3.0, 2.0, 1.714 and "
            "then five webs tied at 1.5 taken in ascending web number, so a "
            "pair either side of a save boundary is out of numbering's reach"
        ),
    ),
)

#: Ranked below both, and stated because it is what the evidence shows: two
#: spellings on this class moved no web number at all.
POOL_ROTATION_INERT: tuple[str, ...] = (
    "declaration order, for register-resident locals: swapping two `s32` "
    "declarations on overlay4UpdateObjectMotion was byte-identical",
    "relational operand order: cfe canonicalises it, so writing "
    "`threshold >= delta` for `delta <= threshold` was byte-identical and "
    "LHS-before-RHS does not apply at a comparison",
    "an added local: it shifts every downstream web number by a constant "
    "(22 -> 25, 48 -> 51, 50 -> 53) and never reorders a pair -- and it cost "
    "a stack home, 8 words to 22",
)

CAPTURE_CDX = (
    "the owning sweep: rebuild the TU with CDX_LOG=1 CDX_OUT=<file> on the "
    "instrumented uopt, scoped with CDX_PROC=<ordinal>, and pass the log as "
    "--ladder. p1 and p2 order their webs differently and take different "
    "levers, and two disassemblies do not say which owns a colour"
)
CAPTURE_FORCE = (
    "reachability: pin the residual's webs with "
    "CDX_FORCE=p1:w<web>=c<colour> (comma-separated for a set) over the same "
    "compile, compare with the project's own comparison, and pass the "
    "resulting oracle sweep JSON as --force-result. words=0 proves every "
    "colour in the residual is legal in this web graph"
)
CONFIRM_CAPTURE = (
    "a CONFIRMING second capture after the edit: re-run CDX_LOG=1 and check "
    "that the web numbers, or the saves, actually moved. Two spellings chosen "
    "from the numbering "
    "model on overlay4UpdateObjectMotion compiled byte-identically because "
    "cfe had already coalesced the store the model depended on, and one "
    "upstream web number shifted while none of the four in the residual did"
)


@dataclass(frozen=True)
class SweepRecord:
    """One coloured web, as the sweep that coloured it recorded it."""

    #: `p1` (callee-saved, repeated max-save selection) or `p2` (caller-saved,
    #: ascending web number). The distinction is the whole point of the
    #: record: it decides which lever the rotation takes.
    phase: str
    web: int
    save: float | None
    color: int | None
    register: str | None
    interference: int | None
    forbidden: tuple[int, ...]
    #: `webdetail`'s `type`. 4 is an expression web: no symbol behind it, so
    #: it is a compiler-minted intermediate -- which is what the synthetic
    #: temp of a two-step narrowing cast is, and what tells the truncation
    #: family its precondition is visibly met.
    web_type: int | None = None
    #: The web's basic block, from `webdetail`. The `line=` field reports the
    #: same line for every web in a procedure and identifies nothing.
    block: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "web": self.web,
            "save": self.save,
            "color": self.color,
            "register": self.register,
            "interference": self.interference,
            "forbidden": list(self.forbidden),
            "web_type": self.web_type,
            "block": self.block,
        }


def _record_register(decision: AllocatorWebDecision) -> str | None:
    """Name the register a decision landed on, preferring the log's own word.

    `p1color`/`p2color` print the register the pass resolved, which is the
    one to believe; the colour table is the fallback for a trace that carries
    only a colour number. Reading the table first would report a colour the
    log itself contradicts.
    """

    for key in ("actualreg", "bestreg"):
        value = decision.fields.get(key)
        if value and value not in {"?", "-"}:
            return value.removeprefix("$")
    return decision.assigned_register


def _float_field(decision: AllocatorWebDecision, key: str) -> float | None:
    value = decision.fields.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def sweep_records(log: CdxLog, *, proc: int | None = None) -> tuple[SweepRecord, ...]:
    """Read every coloured web out of a CDX log, in decision order."""

    records: list[SweepRecord] = []
    for decision in log.trace.allocator_webs(proc=proc):
        phase = decision.phase_tag
        if phase not in {"p1", "p2"}:
            continue
        records.append(
            SweepRecord(
                phase=phase,
                web=decision.web,
                save=_float_field(decision, "save"),
                color=decision.assigned_color,
                register=_record_register(decision),
                interference=optional_integer(decision.fields.get("numintf")),
                forbidden=tuple(decision.forbidden_colors),
                web_type=optional_integer(decision.detail.get("type")),
                block=optional_integer(decision.detail.get("bb")),
            )
        )
    return tuple(records)


def tie_groups(records: Iterable[SweepRecord]) -> dict[float, tuple[int, ...]]:
    """Group p1 webs by save, which is the only thing p1 orders on.

    p1 re-scans every uncoloured web each round and takes the largest save,
    with ascending web number as the tie-break, so webs sharing a save are
    the webs a renumbering edit can reorder and no others.
    """

    groups: dict[float, list[int]] = {}
    for record in records:
        if record.phase != "p1" or record.save is None:
            continue
        groups.setdefault(record.save, []).append(record.web)
    return {save: tuple(sorted(webs)) for save, webs in sorted(groups.items())}


def force_reachability(payload: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    """Read a recorded force experiment as a statement about the web graph.

    Three outcomes, and the middle one is why this is not a boolean. A row at
    `words=0` proves the target's assignment is legal: the pass accepted
    every forced colour and emitted the target's instruction words. A row the
    pass declined, or one that bought its colour with extra instructions, is
    the opposite proof -- the colour is not available in this web graph at
    this cost. Anything else is a measurement and not a proof, and is
    reported as evidence with the field left null.
    """

    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        return None, []
    baseline = payload.get("baseline")
    baseline_instructions = None
    if isinstance(baseline, dict) and isinstance(baseline.get("comparison"), dict):
        baseline_instructions = baseline["comparison"].get("candidate_instructions")
    notes: list[str] = []
    best: int | None = None
    declined = 0
    added = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        force = row.get("force")
        comparison = row.get("comparison")
        if not isinstance(comparison, dict):
            declined += 1
            continue
        words = comparison.get("words")
        instructions = comparison.get("candidate_instructions")
        if (
            baseline_instructions is not None
            and isinstance(instructions, int)
            and instructions > baseline_instructions
        ):
            added += 1
            continue
        if isinstance(words, int):
            if words == 0:
                notes.append(
                    f"force {force} reached words=0: every colour in the "
                    "residual is legal in this web graph and the pass added "
                    "no instruction"
                )
                return REACHABILITY_PROVEN, notes
            best = words if best is None else min(best, words)
    if declined or added:
        notes.append(
            f"{declined} force(s) declined by the pass and {added} paid for "
            "in extra instructions, and none reached words=0"
        )
        return REACHABILITY_UNREACHABLE, notes
    if best is not None:
        notes.append(
            f"{len(rows)} force(s) recorded, best residual {best} word(s): a "
            "measurement, not a proof -- neither words=0 nor a declined force"
        )
    return None, notes


#: What each reachability answer means for the next build.
FORCE_REACHABILITY_ADVICE: dict[str, str] = {
    REACHABILITY_PROVEN: (
        "a recorded force reached words=0, so the whole residual is colours "
        "and every one of them is legal: what is missing is a source "
        "spelling, not a different web graph"
    ),
    REACHABILITY_UNREACHABLE: (
        "the pass declined the force or paid for it in instructions, so the "
        "target's assignment is not available in this web graph and no "
        "renumbering reaches it -- a different web STRUCTURE is required"
    ),
}


#: The keys of as1's selection chain that no source line can reach.
#:
#: `lineno` is the one key with a source lever attached. A selection decided
#: above it was decided on readiness or on the critical path, and moving a
#: statement cannot change either -- which is the whole of the as1-readiness
#: proof, stated as a predicate over a trace the assembler already ships.
READINESS_KEYS: frozenset[str] = frozenset(
    {"start-time", "besttime", "aftercycles", "latency"}
)


@dataclass(frozen=True)
class Lever:
    """The edit class one residual's evidence supports, and what it rests on."""

    lever_class: str
    reason: str
    family: EditFamily | None = None
    unreachable: UnreachableProof | None = None
    evidence: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    measurements: Mapping[str, Any] = field(default_factory=dict)
    alternatives: tuple[EditFamily, ...] = ()
    see_also: tuple[UnreachableProof, ...] = ()
    #: What a recorded force experiment proved about the *web graph*, one of
    #: :data:`FORCE_REACHABILITY_VALUES`, or null when none was supplied. It
    #: is deliberately separate from `edit_family`: a residual can be proved
    #: reachable and still have no known spelling, which is the state
    #: `overlay4UpdateObjectMotion` was left in.
    reachability: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "lever_class": self.lever_class,
            "reason": self.reason,
            "reachability": self.reachability,
            "edit_family": None if self.family is None else self.family.name,
            "edit": None if self.family is None else self.family.edit,
            "citation": None if self.family is None else self.family.citation,
            "evidence": list(self.evidence),
            "needs": list(self.needs),
            "measurements": dict(self.measurements),
            "alternatives": [item.as_dict() for item in self.alternatives],
            "see_also": [item.as_dict() for item in self.see_also],
        }
        payload["unreachable"] = (
            None if self.unreachable is None else self.unreachable.as_dict()
        )
        return payload


def pops_by_line(
    events: Iterable[TraceEvent], *, proc: int | None = None
) -> dict[int, int]:
    """Count ring pops per ugen source line.

    A pop is an allocation off the free list. The line is ugen's own current
    source line, stamped on the record, which is what ties one pop to one
    construct: the line consuming two pops where the target's ring advances
    once is the statement to edit, and there is no other way to find it.
    """

    counts: dict[int, int] = {}
    for event in events:
        if event.action != "allocate" or event.source_line is None:
            continue
        if proc is not None and event.procedure is not None and event.procedure != proc:
            continue
        counts[event.source_line] = counts.get(event.source_line, 0) + 1
    return dict(sorted(counts.items()))


def _ring_order(events: Iterable[TraceEvent], *, proc: int | None = None) -> list[str]:
    """The registers the ring handed out, in the order it handed them out."""

    order: list[str] = []
    for event in events:
        if event.action != "allocate" or event.register is None:
            continue
        if proc is not None and event.procedure is not None and event.procedure != proc:
            continue
        order.append(register_name(event.register))
    return order


def readiness_keys(selections: Iterable[Selection]) -> dict[str, int]:
    """Tally which key decided each as1 selection.

    The tally, not the selections: an analyst asking whether the line lever
    reaches a block is asking whether any selection in it was decided *below*
    `lineno`, and one number per key answers that without reprinting a trace.
    """

    tally: dict[str, int] = {}
    for selection in selections:
        tally[selection.tie] = tally.get(selection.tie, 0) + 1
    return dict(sorted(tally.items()))


def _temp_lane(view: MechanismView) -> Any:
    for lane in view.lanes:
        if lane.classification == "temp":
            return lane
    return None


def _pool_lane(view: MechanismView) -> Any:
    for lane in view.lanes:
        if lane.classification == "pool":
            return lane
    return None


def _displaced_homes(view: MechanismView) -> tuple[int, int]:
    """Rows differing only in a stack displacement, and distinct homes moved.

    The two numbers answer different questions and conflating them picks the
    wrong edit family. A single home that is stored once and reloaded twice
    produces three rows; what the declaration list moved is still one slot.
    The family discriminator is the distinct count.
    """

    from .view import STACK_HOME_RE

    rows = 0
    moved: set[tuple[str, str]] = set()
    for row in view.rows:
        if row.classification != "constant":
            continue
        target = STACK_HOME_RE.findall(row.target or "")
        candidate = STACK_HOME_RE.findall(row.candidate or "")
        if target and candidate and target != candidate:
            rows += 1
            for pair in zip(target, candidate, strict=False):
                if pair[0] != pair[1]:
                    moved.add(pair)
    return rows, len(moved)


#: How the stack-home directions are ranked, in the order the rules are read.
#:
#: Lane evidence first, frame arithmetic second. The frame says how much
#: storage moved; the pool lane says *which value* one side colours and the
#: other does not, and that is nearer the declaration list than a byte count
#: is. Ranked on the frame alone, `func_80005868` put the direction its own
#: printed pool lane named -- one surplus web at slot 0 -- third of three; the
#: two directions above it were inapplicable, and the answer was to declare an
#: index and a pointer ahead of a large buffer, 8 words to 6.
STACK_HOME_RANKING: tuple[str, ...] = (
    "a pool lane of unequal length: the side carrying the surplus web names "
    "the direction, because a value one side colours and the other homes is "
    "a declaration-list fact",
    "the frame delta: a whole 8-byte quantum in either direction",
    "the number of displaced homes: more than one is a position in the list "
    "rather than a count",
)


def _stack_home_lever(
    view: MechanismView,
    ladder: Ladder | None,
    rows: int,
    homes: int,
) -> Lever:
    target_frame = view.target_frame_size
    candidate_frame = view.candidate_frame_size
    # `frame_size` reports the prologue's signed adjustment, which is
    # negative. The quantity a declaration count moves is the frame's *size*,
    # so the delta is taken over magnitudes: a positive delta means the
    # candidate reserves more, whichever sign the adjustment carried.
    delta = (
        None
        if target_frame is None or candidate_frame is None
        else abs(candidate_frame) - abs(target_frame)
    )
    declared = None if ladder is None else len(ladder.named)
    pool = _pool_lane(view)
    pool_delta = None if pool is None else len(pool.candidate) - len(pool.target)
    measurements: dict[str, Any] = {
        "pool_lane_length_delta": pool_delta,
        "target_frame_size": target_frame,
        "candidate_frame_size": candidate_frame,
        "frame_delta": delta,
        "frame_delta_words": None if delta is None else delta // 4,
        "declared_locals": declared,
        "displaced_home_rows": rows,
        "displaced_homes": homes,
        "instruction_counts_agree": (
            view.target_instructions == view.candidate_instructions
        ),
    }
    evidence: list[str] = []
    if delta is not None:
        evidence.append(
            f"frame: target {abs(target_frame or 0)} bytes, candidate "
            f"{abs(candidate_frame or 0)} bytes, delta {delta:+d}"
        )
    if rows:
        evidence.append(
            f"{rows} aligned row(s) differ only in a stack displacement, "
            f"over {homes} distinct home(s): a frame fact, not an immediate"
        )
    if declared is not None:
        evidence.append(
            f"frame ladder: {declared} declared local slot(s) above the "
            "compiler-temp region"
        )
    if pool_delta:
        evidence.append(
            f"pool lane differs in length by {pool_delta:+d}: the "
            + ("candidate" if pool_delta > 0 else "target")
            + " colours a web the other side does not, which is a "
            "declaration-list difference and outranks the frame arithmetic"
        )
    evidence.append(
        "every declared local reserves a home whether or not it is "
        "register-coloured, and the declared block rounds up to 8 bytes: "
        "measured over five builds on func_overlay_022_F0000000, 7 locals "
        "-> 0x58, 6 -> 0x58, 5 -> 0x50"
    )

    if pool_delta:
        primary = STACK_HOME_FAMILIES[0 if pool_delta > 0 else 2]
        reason = (
            "the pool lane is "
            + (
                "longer on the candidate, so it"
                if pool_delta > 0
                else "shorter on the candidate, so the target"
            )
            + " colours a web the other side does not; that names the "
            "declaration the list is wrong about, and lane evidence is "
            "ranked ahead of the frame arithmetic"
        )
    elif delta is not None and delta > 0:
        primary = STACK_HOME_FAMILIES[0]
        reason = (
            "the candidate's frame is larger than the target's by at least "
            "one 8-byte quantum, so the candidate homes something the target "
            "does not -- how many declarations that is depends on where the "
            "block already sat, and the frame is the measurement, not the "
            "declaration count"
        )
    elif delta is not None and delta < 0:
        primary = STACK_HOME_FAMILIES[2]
        reason = (
            "the target's frame is larger than the candidate's by at least "
            "one 8-byte quantum, so the target homes something the candidate "
            "does not -- read the family below in reverse, adding a "
            "declaration rather than moving one"
        )
    elif homes > 1:
        primary = STACK_HOME_FAMILIES[2]
        reason = (
            "the frames agree and more than one home is displaced, which is "
            "a position in the declaration list rather than a count"
        )
    else:
        primary = STACK_HOME_FAMILIES[1]
        reason = (
            "the frames agree and one home is displaced at an unchanged "
            "instruction count, which is one declaration too many"
        )

    needs: list[str] = []
    if declared is None:
        needs.append(CAPTURE_LADDER)
    if delta is None:
        needs.append(
            "frame sizes: neither prologue exposed an immediate frame "
            "adjustment, so the count half of this diagnosis is unmeasured"
        )
    return Lever(
        lever_class=LEVER_STACK_HOME,
        reason=reason,
        family=primary,
        evidence=tuple(evidence),
        needs=tuple(needs),
        measurements=measurements,
        alternatives=tuple(
            item for item in STACK_HOME_FAMILIES if item.name != primary.name
        ),
    )


def _family(name: str) -> EditFamily:
    return next(item for item in TEMP_RING_FAMILIES if item.name == name)


def _traced_constructs(
    counts: dict[int, int], source: Sequence[str] | None
) -> dict[int, str]:
    """Classify each line the ring trace charged a pop to."""

    if source is None:
        return {}
    constructs: dict[int, str] = {}
    for line in counts:
        text = source[line - 1] if 0 < line <= len(source) else ""
        constructs[line] = classify_construct(text)
    return constructs


def _temp_ring_lever(
    view: MechanismView,
    ring_events: Sequence[TraceEvent] | None,
    proc: int | None,
    source: Sequence[str] | None = None,
) -> Lever:
    temp = _temp_lane(view)
    pool = _pool_lane(view)
    measurements: dict[str, Any] = {
        "target_temp_lane": list(temp.target) if temp is not None else None,
        "candidate_temp_lane": list(temp.candidate) if temp is not None else None,
        "temp_lane_rotation": None if temp is None else temp.rotation,
        "temp_lane_length_delta": (
            None if temp is None else len(temp.candidate) - len(temp.target)
        ),
        "pool_lane_length_delta": (
            None if pool is None else len(pool.candidate) - len(pool.target)
        ),
        "pops_by_line": None,
        "pop_total": None,
        "ring_order": None,
        "constructs_by_line": None,
    }
    evidence: list[str] = []
    if temp is not None and temp.rotation is not None:
        evidence.append(
            f"temp lane rotates by {temp.rotation:+d} from slot "
            f"{temp.divergence}, which is one pop and not "
            f"{len(temp.target)} decisions"
        )
    lengths = measurements["pool_lane_length_delta"]
    if lengths:
        evidence.append(
            f"pool lane differs in length by {lengths:+d}: a web population "
            "difference, so a construct is carried in a coloured web on one "
            "side and in a ring temp on the other"
        )

    if ring_events is None:
        return Lever(
            lever_class=LEVER_TEMP_RING,
            reason=(
                "the residual is a ring rotation, and which construct bought "
                "or sold the pop is a property of the free-list trace, not of "
                "the disassembly"
            ),
            evidence=tuple(evidence),
            needs=(CAPTURE_RING,),
            measurements=measurements,
            alternatives=TEMP_RING_FAMILIES,
        )

    counts = pops_by_line(ring_events, proc=proc)
    order = _ring_order(ring_events, proc=proc)
    measurements["pops_by_line"] = {str(line): count for line, count in counts.items()}
    measurements["pop_total"] = sum(counts.values())
    measurements["ring_order"] = order
    doubled = [line for line, count in counts.items() if count > 1]
    if doubled:
        evidence.append(
            "source line(s) "
            + ", ".join(str(line) for line in doubled)
            + " consume more than one pop each; a line whose pops exceed the "
            "target's ring advance is the statement to edit"
        )
    # Two independent gates, and a family is named only when both pass.
    #
    # The *direction* -- buy a pop or sell one -- is the temp lane's rotation.
    # The *precondition* is what the charged line actually contains: each
    # pop-cost rule was measured on one construct, and a pop count says which
    # line to edit without saying which law reaches it. Naming a family from
    # the count alone is what made `read-the-field-directly` the answer for a
    # line holding a cast integer constant, at three inert builds.
    charged = doubled or sorted(counts)
    constructs = _traced_constructs(counts, source)
    if constructs:
        measurements["constructs_by_line"] = {
            str(line): value for line, value in sorted(constructs.items())
        }
        named = sorted(
            {
                CONSTRUCT_FAMILIES[constructs[line]]
                for line in charged
                if constructs.get(line) in CONSTRUCT_FAMILIES
            }
        )
        evidence.append(
            "charged line construct(s): "
            + ", ".join(f"{line} {constructs.get(line, '?')}" for line in charged)
        )
    else:
        named = []

    rotation = measurements["temp_lane_rotation"]
    primary: EditFamily | None = None
    needs: tuple[str, ...] = ()
    if source is None:
        reason = (
            "the pop counts are read and the line to edit is named, but "
            "which pop-cost rule that line qualifies for is a property of "
            "the construct on it, and no source was supplied to check one"
        )
        needs = (CAPTURE_SOURCE,)
    elif not named:
        reason = (
            "the charged line(s) hold no construct with a measured pop cost "
            "-- "
            + ", ".join(f"{line} is {constructs.get(line, '?')}" for line in charged)
            + " -- so no family below applies to them, and the nearest one "
            "is not an answer"
        )
    elif len(named) > 1:
        reason = (
            "the charged lines hold more than one construct with a measured "
            "pop cost (" + ", ".join(named) + "), so which of them carries "
            "the residual is not decided by the counts alone"
        )
    elif rotation is None and not lengths:
        reason = (
            "the construct on the charged line names a rule, but no temp "
            "lane rotated and the pool lane is the same length, so which way "
            "the ring runs against the target is unmeasured"
        )
        needs = (
            "a temp-lane rotation: compare against a target disassembly in "
            "which the temp lane diverges, so the sign of the rotation names "
            "whether the edit buys a pop or sells one",
        )
    else:
        primary = _family(named[0])
        # The line that *selected* the family, which is not always the first
        # charged one: a `constant` at line 41 beside a field read at 42
        # names one family, and reporting line 41's construct beside it would
        # say a constant is the construct that rule was measured on.
        selected = next(
            line
            for line in charged
            if CONSTRUCT_FAMILIES.get(constructs.get(line, "")) == named[0]
        )
        direction = (
            "the pool lane differs in length, so the residual is a web "
            "population difference before it is a rotation"
            if lengths
            else "the candidate is short of the target's ring advance, so "
            "the edit must buy a pop"
            if rotation is not None and rotation < 0
            else "the candidate spends a pop the target does not, so the "
            "edit must sell one"
        )
        reason = (
            f"{direction}; line {selected} is a "
            f"{constructs[selected]}, which is the construct "
            f"{primary.name} was measured on"
        )
    return Lever(
        lever_class=LEVER_TEMP_RING,
        reason=reason,
        family=primary,
        needs=needs,
        evidence=tuple(
            (
                *evidence,
                "two pops off means two of these, and either alone is a large "
                "regression: overlay20UpdateObjectResource measured 25 "
                "differing words on the direct field read alone and exact "
                "with the double scale composed onto it",
            )
        ),
        measurements=measurements,
        alternatives=tuple(
            item
            for item in TEMP_RING_FAMILIES
            if primary is None or item.name != primary.name
        ),
    )


CAPTURE_DETAIL = (
    "which web carries the site: re-run with CDX_DETAIL_WEB=<web>, whose "
    "records name each web's basic block. The block is what identifies a "
    "web; the `line=` field reports the same line for every web in the "
    "procedure and identifies nothing"
)


def _substitutions(view: MechanismView) -> dict[str, str]:
    """The residual's register substitutions, candidate register to target."""

    return {
        web.candidate: web.target
        for web in view.webs
        if web.candidate and web.target and web.candidate != web.target
    }


def _rotation_direction(
    records: Sequence[SweepRecord], substitutions: Mapping[str, str]
) -> tuple[SweepRecord | None, SweepRecord | None, str]:
    """Which web must be numbered earlier, under lowest-free-colour.

    Both sweeps hand a web the lowest colour still free when they reach it,
    so between two webs contesting two colours the one that must end up with
    the LOWER colour is the one that must be visited first. That is the whole
    derivation, and it holds only for a transposition -- two substitutions
    that are each other's inverse -- with exactly one coloured web on each
    side. Anything else is reported as what it is rather than resolved into a
    direction the records do not carry.
    """

    pairs = sorted(substitutions.items())
    if len(pairs) != 2 or pairs[0][1] != pairs[1][0] or pairs[1][1] != pairs[0][0]:
        return (
            None,
            None,
            "the residual is not a two-register transposition, so "
            "lowest-free-colour does not name which web must move: it says "
            "which of two contested colours is taken first, and that is a "
            "statement about a pair",
        )
    holders: dict[str, list[SweepRecord]] = {}
    for record in records:
        register = record.register
        if register is not None and register in substitutions:
            holders.setdefault(register, []).append(record)
    ambiguous = {
        register: [item.web for item in found]
        for register, found in holders.items()
        if len(found) > 1
    }
    if ambiguous:
        rendered = "; ".join(
            f"{register} is held by webs " + ", ".join(str(web) for web in sorted(webs))
            for register, webs in sorted(ambiguous.items())
        )
        return (
            None,
            None,
            f"more than one coloured web holds a register in the residual "
            f"({rendered}), so which of them carries these sites is not in "
            "the decision records",
        )
    missing = sorted(set(substitutions) - set(holders))
    if missing:
        return (
            None,
            None,
            "the log records no coloured web on "
            + ", ".join(missing)
            + ", so the sweep that owns the residual is not in this capture "
            "-- check CDX_PROC selected the right procedure ordinal",
        )
    ranked: list[tuple[int, SweepRecord]] = []
    for register, found in holders.items():
        desired = color_for_register(substitutions[register])
        if desired is None:
            return (
                None,
                None,
                f"the colour of {substitutions[register]} is not in the "
                "pinned colour table, so the two sides cannot be ordered",
            )
        ranked.append((desired, found[0]))
    ranked.sort(key=lambda item: item[0])
    earlier, later = ranked[0][1], ranked[1][1]
    return (
        earlier,
        later,
        f"web {earlier.web} must take colour c{ranked[0][0]} and web "
        f"{later.web} colour c{ranked[1][0]}; the lower colour is handed out "
        f"first, so web {earlier.web} must be visited before web "
        f"{later.web} -- today it is "
        + ("already" if earlier.web < later.web else "not")
        + " the lower-numbered of the two",
    )


def _pool_lever(
    view: MechanismView,
    log: CdxLog | None,
    force: Mapping[str, Any] | None,
    proc: int | None,
) -> Lever:
    """Name the class of a colour-only residual, gated on pool-lane length.

    The gate is first and it is not a formality. `overlay43FilterImage` was
    recorded as "one cyclic pool rotation" for as long as nobody compared the
    lane lengths: 18 slots on the target against 15 on the candidate, with
    the target's temp lane correspondingly shorter. Forcing the rotation to
    the target's colours made the first five pool slots exact and improved 33
    words to 26 -- and raised opcode mismatches from 8 to 10, because the
    three values the target colours are in our temp ring and no colour
    reaches them.
    """

    pool = _pool_lane(view)
    target = tuple(pool.target) if pool is not None else ()
    candidate = tuple(pool.candidate) if pool is not None else ()
    delta = len(candidate) - len(target)
    substitutions = _substitutions(view)
    reachability, force_notes = (
        force_reachability(force) if force is not None else (None, [])
    )
    measurements: dict[str, Any] = {
        "target_pool_lane": list(target),
        "candidate_pool_lane": list(candidate),
        "target_pool_slots": len(target),
        "candidate_pool_slots": len(candidate),
        "pool_lane_length_delta": delta,
        "substitutions": dict(sorted(substitutions.items())),
        "owning_sweep": None,
        "sweep_decisions": None,
        "tie_group": None,
        "move_earlier": None,
        "move_later": None,
        "reachability": reachability,
    }

    if delta:
        surplus = "target" if delta < 0 else "candidate"
        return Lever(
            lever_class=LEVER_POOL_POPULATION,
            reason=(
                f"the pool lanes are {len(target)} and {len(candidate)} slots "
                f"long, so this is a web population difference and not a "
                f"rotation: the {surplus} colours "
                f"{abs(delta)} value(s) the other side leaves in the temp "
                "ring, and no colour lever reaches a web that does not exist"
            ),
            evidence=(
                "equal pool-lane lengths are the precondition for calling a "
                "residual a rotation, and this pair does not meet it",
                "on overlay43FilterImage (Mickey's Speedway USA, "
                "2026-09-03) the same shape -- 18 target slots against 15 -- "
                "was recorded as a rotation; forcing the four-web rotation "
                "to the target's colours improved 33 words to 26 and raised "
                "opcode mismatches from 8 to 10",
                *force_notes,
            ),
            needs=(CAPTURE_RING,),
            measurements=measurements,
            reachability=reachability,
        )

    if log is None:
        return Lever(
            lever_class=LEVER_POOL_ROTATION,
            reason=(
                f"the pool lanes are the same length ({len(target)} slots) "
                "and their contents differ, which is a rotation; which sweep "
                "coloured these webs is a property of the allocator's own "
                "records and not of two disassemblies, and p1 and p2 take "
                "different levers"
            ),
            evidence=(
                "p2, the caller-saved sweep, visits webs in ascending web "
                "number and gives each the lowest free colour; p1, the "
                "callee-saved sweep, is repeated max-save selection with "
                "ascending web number only as the tie-break",
                *force_notes,
            ),
            needs=(CAPTURE_CDX,) + ((CAPTURE_FORCE,) if force is None else ()),
            measurements=measurements,
            alternatives=POOL_ROTATION_FAMILIES,
            reachability=reachability,
        )

    records = sweep_records(log, proc=proc)
    involved = [record for record in records if record.register in substitutions]
    sweeps = sorted({record.phase for record in involved})
    owning = sweeps[0] if len(sweeps) == 1 else ("mixed" if sweeps else None)
    measurements["owning_sweep"] = owning
    measurements["sweep_decisions"] = {
        phase: sum(1 for record in records if record.phase == phase)
        for phase in ("p1", "p2")
    }
    measurements["involved_webs"] = [record.as_dict() for record in involved]
    earlier, later, note = _rotation_direction(involved, substitutions)
    evidence: list[str] = [
        f"pool lanes equal at {len(target)} slot(s), so the residual is a "
        "rotation and not a population difference",
        note,
        *force_notes,
    ]
    needs: list[str] = []
    family: EditFamily | None = None

    if owning is None:
        evidence.insert(
            0,
            "no coloured web in this capture holds a register the residual substitutes",
        )
        needs.append(CAPTURE_CDX)
    elif owning == "mixed":
        evidence.insert(
            0,
            "the residual's registers were coloured in BOTH sweeps, which "
            "take different levers: p2 reads web number alone, p1 reads it "
            "only inside a tie group",
        )
    else:
        evidence.insert(
            0,
            f"the residual's registers were coloured in {owning}, "
            + (
                "which visits webs in ascending web number and gives each "
                "the lowest free colour -- save cost is inert there, "
                "measured as bestcost=0.000000 on every decision of "
                "overlay43FilterImage and overlay60ReassignChoiceSlots while "
                "the saves ranged 3.7 to 1400.0"
                if owning == "p2"
                else "which takes the largest save each round and reads the "
                "web number only to break a tie"
            ),
        )

    tied = False
    if owning == "p1" and earlier is not None and later is not None:
        groups = tie_groups(records)
        for save, webs in groups.items():
            if earlier.web in webs and later.web in webs:
                tied = True
                measurements["tie_group"] = {
                    "save": save,
                    "webs": list(webs),
                }
                evidence.append(
                    f"webs {earlier.web} and {later.web} are in the same p1 "
                    f"tie group: save {save}, members "
                    + ", ".join(str(web) for web in webs)
                    + ", ordered by web number alone"
                )
                break
        if not tied:
            evidence.append(
                f"webs {earlier.web} and {later.web} are not tied on save "
                f"({earlier.save} against {later.save}), so p1's max-save "
                "selection orders them and no renumbering reorders them"
            )

    orderable = earlier is not None and later is not None and owning in {"p1", "p2"}
    if earlier is not None and later is not None:
        # The direction is a fact about the two colours whether or not a
        # renumbering edit can act on it; a p1 pair across a save boundary
        # still has an order the target wants, and the cost family is how it
        # is reached.
        measurements["move_earlier"] = earlier.web
        measurements["move_later"] = later.web
    if orderable and owning == "p1" and not tied:
        family = POOL_ROTATION_FAMILIES[1]
    elif orderable:
        blocked = [
            record
            for record in (earlier, later)
            if record is not None
            and color_for_register(substitutions.get(record.register or "", ""))
            in record.forbidden
        ]
        if blocked:
            evidence.append(
                "the colour the residual wants is in the interference mask "
                "of web "
                + ", ".join(str(record.web) for record in blocked)
                + ", so the pass would decline it: this is not a numbering "
                "residual"
            )
        elif any(
            record is not None and record.web_type == 4 for record in (earlier, later)
        ):
            family = POOL_ROTATION_FAMILIES[0]
        else:
            evidence.append(
                "neither web is a type=4 expression web, and the one "
                "measured renumbering spelling was measured on the synthetic "
                "temp of a narrowing cast; naming it here would apply a rule "
                "to a shape it was never measured on"
            )
    if earlier is None:
        needs.append(CAPTURE_DETAIL)
    if force is None:
        needs.append(CAPTURE_FORCE)
    # A renumbering edit is never named without the capture that confirms it.
    # Both spellings tried on `overlay4UpdateObjectMotion` were plausible from
    # the numbering model and neither moved a web number: cfe had already
    # coalesced the store one of them depended on, and the diff cannot show
    # that. The capture would have cost nothing and saved both builds.
    if family is not None:
        needs.append(CONFIRM_CAPTURE)

    if family is not None:
        reason = (
            f"the pool lanes are equal at {len(target)} slot(s) and the "
            f"residual's webs were coloured in {owning}, where "
            + (
                "the visit order is the web number"
                if owning == "p2"
                else "a tie on save leaves the web number as the only order"
                if tied
                else "the saves differ, so only the cost reorders them"
            )
            + f"; {note}"
        )
    elif orderable:
        reason = (
            f"the rotation is real and the direction is named, but no "
            f"measured source spelling applies to these webs; {note}"
        )
    else:
        reason = (
            "the pool lanes are equal in length, so the residual is a "
            f"rotation, and {note}"
        )
    return Lever(
        lever_class=LEVER_POOL_ROTATION,
        reason=reason,
        family=family,
        evidence=tuple(evidence),
        needs=tuple(dict.fromkeys(needs)),
        measurements=measurements,
        alternatives=tuple(
            item
            for item in POOL_ROTATION_FAMILIES
            if family is None or item.name != family.name
        ),
        reachability=reachability,
    )


def _line_order_lever(
    view: MechanismView,
    emit_events: Sequence[EmitEvent] | None,
    proc: int | None,
) -> Lever:
    measurements: dict[str, Any] = {
        "line_order_conflicts": None,
        "first_conflict": None,
    }
    if emit_events is None:
        return Lever(
            lever_class=LEVER_LINE_ORDER,
            reason=(
                "the residual is an ordering of instructions the target also "
                "emits, and whether their lines separate them is a property "
                "of ugen's emit records"
            ),
            needs=(CAPTURE_EMIT, CAPTURE_AS1),
            measurements=measurements,
            alternatives=LINE_ORDER_FAMILIES,
        )
    scoped = [event for event in emit_events if proc is None or event.proc == proc]
    conflicts = line_order_conflicts(scoped)
    measurements["line_order_conflicts"] = len(conflicts)
    measurements["first_conflict"] = conflicts[0] if conflicts else None
    if not conflicts:
        return Lever(
            lever_class=LEVER_NONE_KNOWN,
            reason=(
                "the emit trace holds no adjacent instruction pair whose "
                "lines could reverse their order, so nothing here is "
                "separated by a line stamp and the join has nothing to join"
            ),
            evidence=(f"{len(scoped)} emit record(s) read, 0 line-order conflicts",),
            measurements=measurements,
            needs=(CAPTURE_AS1,),
        )
    first = conflicts[0]
    return Lever(
        lever_class=LEVER_LINE_ORDER,
        reason=(
            "an adjacent instruction pair is emitted in one order and "
            "stamped with lines that put it in the other, which is the pair "
            "as1's minimised line key decides"
        ),
        family=LINE_ORDER_FAMILIES[0],
        evidence=(
            f"{len(conflicts)} line-order conflict(s); the first is proc "
            f"{first['proc']} block {first['block']}, emit "
            f"{first['earlier']['emit']} at line {first['earlier']['line']} "
            f"before emit {first['later']['emit']} at line "
            f"{first['later']['line']} (gap {first['line_gap']})",
            "a loop-invariant hoisted into a preheader carries the loop "
            "header's line, so every initialiser written above the loop wins "
            "the line key with no dependence edge behind it",
        ),
        measurements=measurements,
        alternatives=(LINE_ORDER_FAMILIES[1],),
    )


def _as1_lever(selections: Sequence[Selection]) -> Lever | None:
    """Classify from an as1 trace, which decides this outright or not at all."""

    tally = readiness_keys(selections)
    measurements: dict[str, Any] = {
        "selections": len(selections),
        "deciding_keys": tally,
    }
    readiness = sum(count for key, count in tally.items() if key in READINESS_KEYS)
    by_line = tally.get("lineno", 0)
    if by_line:
        return Lever(
            lever_class=LEVER_LINE_ORDER,
            reason=(
                "as1 decided at least one selection in this scope on the "
                "source line, which is the one key in its chain with a source "
                "lever attached"
            ),
            family=LINE_ORDER_FAMILIES[0],
            evidence=(
                f"{by_line} of {len(selections)} selection(s) decided on lineno",
            ),
            measurements=measurements,
            alternatives=(LINE_ORDER_FAMILIES[1],),
        )
    if readiness and readiness == len(selections):
        return Lever(
            lever_class=LEVER_UNREACHABLE,
            reason=(
                "every selection in this scope was decided above the line "
                "key, on readiness or on the critical path, and no statement "
                "placement changes either"
            ),
            unreachable=UNREACHABLE_PROOFS["as1-readiness"],
            evidence=(
                f"{readiness} of {len(selections)} selection(s) decided on "
                + ", ".join(
                    f"{key} ({count})"
                    for key, count in tally.items()
                    if key in READINESS_KEYS
                ),
            ),
            measurements=measurements,
        )
    return None


def lever_for(
    view: MechanismView,
    *,
    ladder: Ladder | None = None,
    cdx_log: CdxLog | None = None,
    force_result: Mapping[str, Any] | None = None,
    ring_events: Sequence[TraceEvent] | None = None,
    emit_events: Sequence[EmitEvent] | None = None,
    as1_selections: Sequence[Selection] | None = None,
    source: Sequence[str] | None = None,
    proc: int | None = None,
) -> Lever:
    """Name the source-edit class this residual's evidence supports.

    The order is the order of decisiveness, not of frequency. An as1 trace
    settles the line question outright, so it is read first; a frame delta is
    an arithmetic fact about two prologues and needs nothing; a ring rotation
    and a line-order conflict each need their own trace and say so.

    `source` is the candidate's C, split into lines. It is not a trace and it
    decides nothing on its own: it is read only to check whether the line a
    ring trace charged holds the construct a pop-cost rule was measured on.

    `cdx_log` is the same file `--ladder` reads, read for its colouring
    records rather than its itable: a colour-only residual is owned by one of
    two sweeps that order their webs differently, and nothing in two
    disassemblies says which. `force_result` is a recorded `CDX_FORCE`
    experiment, which answers a different question again -- whether the
    target's assignment is legal at all -- and is never inferred from the
    absence of one.
    """

    if as1_selections:
        decided = _as1_lever(as1_selections)
        if decided is not None:
            return decided

    rows, homes = _displaced_homes(view)
    frames_differ = (
        view.target_frame_size is not None
        and view.candidate_frame_size is not None
        and view.target_frame_size != view.candidate_frame_size
    )
    owning = view.owning_pass

    if frames_differ or rows or owning == OWNING_PASS_STACK_HOME:
        return _stack_home_lever(view, ladder, rows, homes)
    if owning == OWNING_PASS_UGEN_RING:
        return _temp_ring_lever(view, ring_events, proc, source)
    if owning == OWNING_PASS_G0_SCHEDULER or emit_events is not None:
        return _line_order_lever(view, emit_events, proc)

    pool = _pool_lane(view)
    rotated = pool is not None and tuple(pool.target) != tuple(pool.candidate)
    unequal = pool is not None and len(pool.target) != len(pool.candidate)
    # The length gate runs before every catalogue proof, because a population
    # difference wearing a rotation's clothes is what the gate exists for and
    # a proof promoted over it would rule out the edit that actually applies.
    if owning == OWNING_PASS_UOPT_COLOR and unequal:
        return _pool_lever(view, cdx_log, force_result, proc)

    proofs = tuple(UNREACHABLE_PROOFS[name] for name in PASS_PROOFS.get(owning, ()))
    measurements = {
        "owning_pass": owning,
        "displaced_home_rows": rows,
        "webs": len(view.webs),
    }
    # A catalogue proof whose precondition the evidence already meets is the
    # verdict, not a footnote. Printed under `see_also` beside `none-known`
    # and three capture lines, it read as background and cost a build that
    # reproduced the proof exactly.
    met = [
        proof
        for proof in proofs
        if proof.name in PROOF_PRECONDITIONS and PROOF_PRECONDITIONS[proof.name](view)
    ]
    if len(met) == 1:
        settled = met[0]
        return Lever(
            lever_class=LEVER_UNREACHABLE,
            reason=(
                f"the owning pass reads {owning} and the residual has the "
                f"shape {settled.name} was measured on: {settled.precondition}"
            ),
            unreachable=settled,
            evidence=(
                f"{len(view.webs)} consistent web substitution(s) over "
                f"{sum(item.count for item in view.webs)} site(s)",
            ),
            measurements=measurements,
            see_also=tuple(item for item in proofs if item is not settled),
        )
    if owning == OWNING_PASS_UOPT_COLOR and rotated:
        return _pool_lever(view, cdx_log, force_result, proc)
    return Lever(
        lever_class=LEVER_NONE_KNOWN,
        reason=(
            f"no lever class is supported by this evidence: the owning pass "
            f"reads {owning}, the frames agree, and no home, ring or "
            "line-order measurement is present"
        ),
        needs=(CAPTURE_RING, CAPTURE_EMIT, CAPTURE_AS1),
        measurements=measurements,
        see_also=proofs,
    )


def format_lever(lever: Lever) -> tuple[str, ...]:
    """Render the lever block as the lines `diagnose` prints under MECHANISM."""

    lines = [f"lever: {lever.lever_class} -- {lever.reason}"]
    if lever.reachability is not None:
        lines.append(
            f"  reachability: {lever.reachability} -- "
            + FORCE_REACHABILITY_ADVICE[lever.reachability]
        )
    if lever.family is not None:
        lines.append(f"  edit ({lever.family.name}): {lever.family.edit}")
        lines.append(f"  proved on: {lever.family.citation}")
    if lever.unreachable is not None:
        lines.append(
            f"  unreachable ({lever.unreachable.name}): {lever.unreachable.proof}"
        )
        lines.append(f"  measured on: {lever.unreachable.citation}")
        lines.append(f"  reopens when: {lever.unreachable.reopens_when}")
    for line in lever.evidence:
        lines.append(f"  evidence: {line}")
    for line in lever.needs:
        lines.append(f"  capture: {line}")
    for family in lever.alternatives:
        lines.append(f"  or ({family.name}) when {family.discriminator}")
    for proof in lever.see_also:
        lines.append(f"  see also ({proof.name}): {proof.proof}")
        if proof.precondition:
            lines.append(f"    applies when: {proof.precondition}")
    return tuple(lines)
