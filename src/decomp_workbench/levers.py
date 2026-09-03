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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .as1_reorganize import Selection
from .emit_provenance import EmitEvent, line_order_conflicts
from .frame_ladder import Ladder
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
    "LEVER_CLASS_VALUES",
    "LEVER_LINE_ORDER",
    "LEVER_NONE_KNOWN",
    "LEVER_SCHEMA",
    "LEVER_STACK_HOME",
    "LEVER_TEMP_RING",
    "LEVER_UNREACHABLE",
    "LINE_ORDER_FAMILIES",
    "STACK_HOME_FAMILIES",
    "TEMP_RING_FAMILIES",
    "UNREACHABLE_PROOFS",
    "EditFamily",
    "Lever",
    "UnreachableProof",
    "format_lever",
    "lever_for",
    "pops_by_line",
    "readiness_keys",
]

#: The sub-document this module contributes. It is merged into a host report
#: under `lever`/`lever_schema` and never renames its host.
LEVER_SCHEMA = "decomp-workbench-lever-v1"

LEVER_STACK_HOME = "stack-home"
LEVER_TEMP_RING = "temp-ring"
LEVER_LINE_ORDER = "line-order"
LEVER_UNREACHABLE = "unreachable"
LEVER_NONE_KNOWN = "none-known"

#: Every value `lever_class` can take, in the order this module tries them.
LEVER_CLASS_VALUES: tuple[str, ...] = (
    LEVER_UNREACHABLE,
    LEVER_STACK_HOME,
    LEVER_TEMP_RING,
    LEVER_LINE_ORDER,
    LEVER_NONE_KNOWN,
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

    def as_dict(self) -> dict[str, str]:
        return {
            "unreachable_class": self.name,
            "proof": self.proof,
            "citation": self.citation,
            "reopens_when": self.reopens_when,
        }


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
    ),
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
CAPTURE_EMIT = (
    "line-order conflicts: rebuild with DKWB_UGEN_SCHED=1 on a cc carrying "
    "instrument-ugen --emit-provenance and pass the log as --emit-trace"
)
CAPTURE_AS1 = (
    "as1 selection keys: rebuild the same compile with cc -Wa,-R and pass "
    "the assembler's trace as --as1-trace (no patched compiler; the object "
    "is byte-identical with -R on)"
)

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

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "lever_class": self.lever_class,
            "reason": self.reason,
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
    measurements: dict[str, Any] = {
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
    evidence.append(
        "every declared local reserves a home whether or not it is "
        "register-coloured, and the declared block rounds up to 8 bytes: "
        "measured over five builds on func_overlay_022_F0000000, 7 locals "
        "-> 0x58, 6 -> 0x58, 5 -> 0x50"
    )

    if delta is not None and delta > 0:
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


def _temp_ring_lever(
    view: MechanismView,
    ring_events: Sequence[TraceEvent] | None,
    proc: int | None,
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
    # Which family applies is a *direction*: buy a pop or sell one. That
    # direction is the temp lane's rotation, and where the lane did not
    # rotate the pop trace says how many pops each line took but not which
    # way the residual runs -- so no family is named. Defaulting to one of
    # them would state a direction from nothing.
    rotation = measurements["temp_lane_rotation"]
    primary: EditFamily | None
    needs: tuple[str, ...] = ()
    if lengths:
        primary = TEMP_RING_FAMILIES[2]
        reason = (
            "the pool lane differs in length, so the residual is a web "
            "population difference before it is a rotation"
        )
    elif rotation is None:
        primary = None
        reason = (
            "the pop counts are read, but no temp lane rotated, so which "
            "way the ring runs against the target is unmeasured and the "
            "direction that picks between the families below with it"
        )
        needs = (
            "a temp-lane rotation: compare against a target disassembly in "
            "which the temp lane diverges, so the sign of the rotation names "
            "whether the edit buys a pop or sells one",
        )
    elif rotation < 0:
        primary = TEMP_RING_FAMILIES[1]
        reason = (
            "the candidate is short of the target's ring advance, so the "
            "edit must buy a pop"
        )
    else:
        primary = TEMP_RING_FAMILIES[0]
        reason = (
            "the candidate spends a pop the target does not, so the edit must sell one"
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
    ring_events: Sequence[TraceEvent] | None = None,
    emit_events: Sequence[EmitEvent] | None = None,
    as1_selections: Sequence[Selection] | None = None,
    proc: int | None = None,
) -> Lever:
    """Name the source-edit class this residual's evidence supports.

    The order is the order of decisiveness, not of frequency. An as1 trace
    settles the line question outright, so it is read first; a frame delta is
    an arithmetic fact about two prologues and needs nothing; a ring rotation
    and a line-order conflict each need their own trace and say so.
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
        return _temp_ring_lever(view, ring_events, proc)
    if owning == OWNING_PASS_G0_SCHEDULER or emit_events is not None:
        return _line_order_lever(view, emit_events, proc)

    proofs = tuple(UNREACHABLE_PROOFS[name] for name in PASS_PROOFS.get(owning, ()))
    return Lever(
        lever_class=LEVER_NONE_KNOWN,
        reason=(
            f"no lever class is supported by this evidence: the owning pass "
            f"reads {owning}, the frames agree, and no home, ring or "
            "line-order measurement is present"
        ),
        needs=(CAPTURE_RING, CAPTURE_EMIT, CAPTURE_AS1),
        measurements={
            "owning_pass": owning,
            "displaced_home_rows": rows,
        },
        see_also=proofs,
    )


def format_lever(lever: Lever) -> tuple[str, ...]:
    """Render the lever block as the lines `diagnose` prints under MECHANISM."""

    lines = [f"lever: {lever.lever_class} -- {lever.reason}"]
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
    return tuple(lines)
