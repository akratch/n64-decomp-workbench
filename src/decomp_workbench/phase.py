"""Ring phase as a vector over named row slots, with its coset always declared.

A late-stage float-heavy function is often not "wrong" so much as *rotated*:
the compiler allocated the same values to the same scratch ring, starting at a
different register. Whole regions then differ in every row while being one
renaming away from exact. Two campaign habits grew up around that, and both of
them lie in a way that costs stages:

**Quotienting silently.** A band scorer that reports the best-fit permutation's
mismatch count prints a small, encouraging number for an object that is
positionally enormous. One campaign's headline "39 -> 29" was really 1045
positional rows once the ring had rotated globally, and the tool that printed
it never said so. Here a slot's quotiented count is never printed bare: it
carries the coset that produced it, and the positional count beside it, and
when any slot is non-identity the report says in words that the two numbers
measure different things.

**Naming bands that do not cover the object.** The scorer family this replaces
partitioned a 4641-row object into eight named ranges that between them left
105 rows unnamed, so a mismatch landing in the gap was absent from the total --
one candidate scored ``RAW=1`` with two real mismatches. Slots here are
*checked* to partition the row space exactly: a hole or an overlap is an error
that names the rows, not a convention the reader is trusted to maintain.

Two further properties follow from the same idea that a phase is a vector, not
a number:

* the state is one coset **per slot** -- eight named sub-zones of one campaign's
  object each rotated independently, and a single global permutation cannot
  express that;
* a slot with too few rows whose match status depends on the coset has *no
  evidence* about its phase, and is reported as ``no-evidence`` rather than
  being assigned the first permutation that happens to win. Classifying a
  small slot in isolation is how one campaign dropped a working construct from
  every catalogue it kept.

Scoring is shift-tolerant by construction: rows are paired through
:mod:`decomp_workbench.shift_align`, so an inserted instruction moves the
comparison rather than destroying it.
"""

from __future__ import annotations

import functools
import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .compare import mismatch_ranges
from .model import Instruction
from .shift_align import ShiftDiff, comparable_text, relocation_rows

__all__ = [
    "COSET_FAMILIES",
    "DEFAULT_RING",
    "Coset",
    "PhaseError",
    "PhaseReport",
    "Slot",
    "SlotScore",
    "build_phase_report",
    "parse_ring",
    "parse_slots",
    "ring_cosets",
    "ring_pattern",
    "validate_partition",
]

#: JSON identity for :meth:`PhaseReport.as_dict`.
PHASE_SCHEMA = "decomp-workbench-phase-v1"

#: The IDO 5.3 single-precision scratch ring: the four coprocessor-1 registers
#: the allocator cycles through for unnamed temporaries. Measured, not assumed
#: -- see the compiler-laws page on the float ring's width.
DEFAULT_RING = ("$f4", "$f6", "$f8", "$f10")

#: Which renamings count as "the same allocation, rotated".
#:
#: ``all``
#:     Every permutation of the ring. The complete answer, and the one three
#:     campaign scorers used.
#: ``paired``
#:     The identity plus every renaming that swaps the ring's registers in
#:     disjoint pairs. For a four-register ring that is the four physically
#:     plausible cosets a profiler used: cheaper, and it cannot report a
#:     permutation the hardware's even-register pairing makes impossible.
COSET_FAMILIES = ("all", "paired")

#: Above this, ``--cosets all`` is refused rather than run: the search is
#: ``n!`` and a reader who asks for it on a large ring wants ``paired``.
MAX_ALL_RING = 7

#: One MIPS register token, in the spelling GNU objdump prints. Any ring is
#: allowed, not only the float one: the integer temporaries rotate the same way
#: and a candidate whose `$t6..$t9` have shifted round is the same fact about a
#: different pool.
_RING_REGISTER_RE = re.compile(
    r"^\$(?:f\d+|zero|at|v[01]|a[0-3]|t\d|s[0-8]|k[01]|gp|sp|fp|ra)$"
)
_SLOT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]*)=(?P<start>\d+)\.\.(?P<stop>\d+)$"
)


class PhaseError(ValueError):
    """A phase report could not be built from the inputs as given.

    Every message names what was wrong and what to pass instead, because the
    two most common mistakes -- a slot table with a hole and a ring the object
    does not use -- both produce a plausible-looking number if they are not
    caught.
    """


@dataclass(frozen=True)
class Slot:
    """One named, inclusive range of target rows."""

    name: str
    start: int
    stop: int

    @property
    def rows(self) -> int:
        return self.stop - self.start + 1

    def contains(self, row: int) -> bool:
        return self.start <= row <= self.stop

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "start": self.start, "stop": self.stop}


def parse_slots(text: str) -> tuple[Slot, ...]:
    """Parse ``NAME=LO..HI,NAME=LO..HI`` into slots, in the order given."""

    slots: list[Slot] = []
    for item in text.split(","):
        entry = item.strip()
        if not entry:
            continue
        match = _SLOT_RE.match(entry)
        if match is None:
            raise PhaseError(
                f"invalid slot {entry!r}; write each slot as NAME=LO..HI, for "
                "example --slots 'head=0..1573,body=1574..4640'"
            )
        start = int(match.group("start"))
        stop = int(match.group("stop"))
        if stop < start:
            raise PhaseError(
                f"slot {match.group('name')!r} ends before it starts "
                f"({start}..{stop}); write the lower row first"
            )
        slots.append(Slot(name=match.group("name"), start=start, stop=stop))
    if not slots:
        raise PhaseError(
            "--slots was empty; pass at least one NAME=LO..HI, or omit the "
            "option to score the whole object as one slot"
        )
    names = [slot.name for slot in slots]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise PhaseError(
            "slot names must be unique; repeated: " + ", ".join(duplicates)
        )
    return tuple(slots)


def validate_partition(slots: Sequence[Slot], *, first: int, last: int) -> None:
    """Raise unless ``slots`` covers ``first..last`` exactly once each.

    The check the band scorers never had. A slot table is a claim about which
    rows the report accounts for; an uncovered row is a mismatch that can never
    appear in any total, and an overlapped row is one counted twice.
    """

    ordered = sorted(slots, key=lambda slot: (slot.start, slot.stop))
    problems: list[str] = []
    for earlier, later in itertools.pairwise(ordered):
        if later.start <= earlier.stop:
            problems.append(
                f"{earlier.name} ({earlier.start}..{earlier.stop}) and "
                f"{later.name} ({later.start}..{later.stop}) overlap at rows "
                f"{later.start}..{min(earlier.stop, later.stop)}"
            )
    covered: list[tuple[int, int]] = []
    for slot in ordered:
        if slot.start > last or slot.stop < first:
            problems.append(
                f"{slot.name} ({slot.start}..{slot.stop}) lies outside the "
                f"object's rows {first}..{last}"
            )
            continue
        covered.append((max(slot.start, first), min(slot.stop, last)))
    holes: list[tuple[int, int]] = []
    cursor = first
    for start, stop in sorted(covered):
        if start > cursor:
            holes.append((cursor, start - 1))
        cursor = max(cursor, stop + 1)
    if cursor <= last:
        holes.append((cursor, last))
    if holes:
        described = ", ".join(
            f"{start}..{stop} ({stop - start + 1} row(s))" for start, stop in holes
        )
        problems.append(
            f"these rows belong to no slot, so a mismatch there would be "
            f"absent from every total: {described}"
        )
    if problems:
        raise PhaseError(
            "the slot table does not partition rows "
            f"{first}..{last}:\n  - " + "\n  - ".join(problems)
        )


@dataclass(frozen=True)
class Coset:
    """One renaming of the scratch ring, as a substitution on the candidate.

    ``image[i]`` is the register the candidate's ``ring[i]`` must be rewritten
    to for the candidate to read like the target. The identity coset rewrites
    nothing, and is the only one under which a quotiented count and a
    positional count are the same question.
    """

    ring: tuple[str, ...]
    image: tuple[str, ...]

    @property
    def is_identity(self) -> bool:
        return self.ring == self.image

    @property
    def label(self) -> str:
        if self.is_identity:
            return "id"
        return "/".join(name.lstrip("$") for name in self.image)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(zip(self.ring, self.image, strict=True))

    def apply(self, text: str) -> str:
        if self.is_identity:
            return text
        table = self.mapping
        return ring_pattern(self.ring).sub(lambda match: table[match.group(0)], text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "identity": self.is_identity,
            "ring": list(self.ring),
            "image": list(self.image),
        }


@functools.cache
def ring_pattern(ring: tuple[str, ...]) -> re.Pattern[str]:
    """Return the substitution pattern for one ring.

    Built from the ring itself, with a word boundary, so ``$f1`` can never
    match inside ``$f10``: a substring test would rewrite the wrong register
    and quietly change what the coset means.
    """

    return re.compile(
        "|".join(
            re.escape(name) + r"\b" for name in sorted(ring, key=len, reverse=True)
        )
    )


def parse_ring(text: str) -> tuple[str, ...]:
    """Parse a comma-separated ring such as ``$f4,$f6,$f8,$f10``."""

    names: list[str] = []
    for item in text.split(","):
        entry = item.strip()
        if not entry:
            continue
        register = entry if entry.startswith("$") else f"${entry}"
        if not _RING_REGISTER_RE.fullmatch(register):
            raise PhaseError(
                f"invalid ring register {entry!r}; the ring is a list of MIPS "
                "registers, for example --ring '$f4,$f6,$f8,$f10' for the "
                "float scratch ring, or --ring '$t6,$t7,$t8,$t9' for the "
                "integer temporaries"
            )
        names.append(register)
    if len(names) < 2:
        raise PhaseError(
            "--ring needs at least two registers; a one-register ring has only "
            "the identity coset and nothing to report"
        )
    if len(set(names)) != len(names):
        raise PhaseError("--ring must not repeat a register")
    return tuple(names)


def _paired_images(ring: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Return the identity plus every disjoint-pair swap of the ring."""

    images: list[tuple[str, ...]] = [ring]
    if len(ring) % 2:
        return images
    indices = list(range(len(ring)))

    def pairings(remaining: list[int]) -> list[list[tuple[int, int]]]:
        if not remaining:
            return [[]]
        first, rest = remaining[0], remaining[1:]
        result: list[list[tuple[int, int]]] = []
        for position, other in enumerate(rest):
            tail = rest[:position] + rest[position + 1 :]
            result.extend([(first, other), *item] for item in pairings(tail))
        return result

    for pairing in pairings(indices):
        image = list(ring)
        for left, right in pairing:
            image[left], image[right] = ring[right], ring[left]
        candidate = tuple(image)
        if candidate not in images:
            images.append(candidate)
    return images


def ring_cosets(ring: tuple[str, ...], *, family: str = "all") -> tuple[Coset, ...]:
    """Return the cosets to search, identity first."""

    if family not in COSET_FAMILIES:
        raise PhaseError(
            f"unknown coset family {family!r}; expected one of "
            + ", ".join(COSET_FAMILIES)
        )
    if family == "paired":
        images = _paired_images(ring)
    else:
        if len(ring) > MAX_ALL_RING:
            raise PhaseError(
                f"--cosets all searches every permutation of the ring, which "
                f"is {len(ring)}! for this ring; pass --cosets paired, or a "
                f"ring of at most {MAX_ALL_RING} registers"
            )
        images = [
            ring,
            *(item for item in itertools.permutations(ring) if item != ring),
        ]
    return tuple(Coset(ring=ring, image=image) for image in images)


@dataclass(frozen=True)
class SlotScore:
    """One slot's phase reading and the two counts that come with it."""

    slot: Slot
    compared: int
    masked: int
    unpaired: int
    informative: int
    coset: Coset
    coset_evidence: str
    tied: tuple[str, ...]
    quotiented: int
    positional: int
    quotiented_rows: tuple[int, ...]
    positional_rows: tuple[int, ...]
    healed: int = 0
    broken: int = 0
    healed_rows: tuple[int, ...] = ()
    broken_rows: tuple[int, ...] = ()

    @property
    def diverges(self) -> bool:
        """Whether quotienting this slot changed the number it reports."""

        return self.quotiented != self.positional

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot.name,
            "start": self.slot.start,
            "stop": self.slot.stop,
            "compared": self.compared,
            "masked": self.masked,
            "unpaired": self.unpaired,
            "informative": self.informative,
            "coset": self.coset.as_dict(),
            "coset_evidence": self.coset_evidence,
            "tied_cosets": list(self.tied),
            "quotiented": self.quotiented,
            "positional": self.positional,
            "quotiented_rows": list(self.quotiented_rows),
            "positional_rows": list(self.positional_rows),
            "healed": self.healed,
            "broken": self.broken,
            "healed_rows": list(self.healed_rows),
            "broken_rows": list(self.broken_rows),
        }


@dataclass(frozen=True)
class PhaseReport:
    """The full phase reading for one candidate against one target."""

    target_name: str
    candidate_name: str
    symbol: str | None
    ring: tuple[str, ...]
    coset_family: str
    target_rows: int
    candidate_rows: int
    slots: tuple[SlotScore, ...]
    shift: ShiftDiff
    base_source: str | None = None
    base_sha256: str | None = None
    context_name: str | None = None
    context_slots: tuple[SlotScore, ...] = ()
    baseline_name: str | None = None
    cache_notes: tuple[str, ...] = ()

    @property
    def quotiented(self) -> int:
        return sum(item.quotiented for item in self.slots)

    @property
    def positional(self) -> int:
        return sum(item.positional for item in self.slots)

    @property
    def healed(self) -> int:
        return sum(item.healed for item in self.slots)

    @property
    def broken(self) -> int:
        return sum(item.broken for item in self.slots)

    @property
    def instruction_delta(self) -> int:
        return self.candidate_rows - self.target_rows

    @property
    def non_identity_slots(self) -> tuple[SlotScore, ...]:
        return tuple(item for item in self.slots if not item.coset.is_identity)

    @property
    def quotiented_is_bare(self) -> bool:
        """Whether the quotiented total may be read as a plain score.

        Only when every slot is at the identity coset. Anywhere else the
        number assumes a register renaming the object has not performed, and
        printing it alone is the defect this report exists to prevent.
        """

        return not self.non_identity_slots

    @property
    def phase_vector(self) -> tuple[str, ...]:
        """The per-slot coset labels: the object's phase state, in order."""

        return tuple(item.coset.label for item in self.slots)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PHASE_SCHEMA,
            "target": self.target_name,
            "candidate": self.candidate_name,
            "symbol": self.symbol,
            "ring": list(self.ring),
            "coset_family": self.coset_family,
            "target_rows": self.target_rows,
            "candidate_rows": self.candidate_rows,
            "instruction_delta": self.instruction_delta,
            "phase_vector": list(self.phase_vector),
            "quotiented": self.quotiented,
            "positional": self.positional,
            "quotiented_is_bare": self.quotiented_is_bare,
            "slots": [item.as_dict() for item in self.slots],
            "shift": self.shift.as_dict(),
            "base_source": self.base_source,
            "base_sha256": self.base_sha256,
            "context": self.context_name,
            "context_slots": [item.as_dict() for item in self.context_slots],
            "baseline": self.baseline_name,
            "healed": self.healed if self.baseline_name else None,
            "broken": self.broken if self.baseline_name else None,
            "cache_notes": list(self.cache_notes),
        }


@dataclass(frozen=True)
class _RowEvidence:
    """Per-row match status under each coset, computed once."""

    #: Rows whose match status does not depend on the coset, and whether they
    #: match. A row is here when neither side mentions a ring register.
    fixed: dict[int, bool]
    #: For each coset index, the set of ring rows that match under it.
    matches: tuple[frozenset[int], ...]
    #: Rows that carry a ring register on either side.
    ring_rows: frozenset[int]
    #: Rows excluded because one side's word is the linker's.
    masked: frozenset[int]
    #: Target rows the aligner could not pair with any candidate row.
    unpaired: frozenset[int]


def _row_evidence(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    shift: ShiftDiff,
    cosets: Sequence[Coset],
    ring: tuple[str, ...],
) -> _RowEvidence:
    """Compare every pairable row under every coset, once."""

    target_relocations = relocation_rows(target)
    candidate_relocations = relocation_rows(candidate)
    inverse = shift.pairing.target_of_candidate
    candidate_addresses = {
        item.address: inverse[index]
        for index, item in enumerate(candidate)
        if index in inverse
    }

    pattern = ring_pattern(ring)
    fixed: dict[int, bool] = {}
    ring_rows: set[int] = set()
    masked: set[int] = set()
    unpaired: set[int] = set()
    pending: dict[int, tuple[str, str]] = {}

    for target_row in range(len(target)):
        candidate_row = shift.pairing.candidate_row(target_row)
        if candidate_row is None:
            unpaired.add(target_row)
            continue
        # Two relocation spaces, never one: a target row is masked by the
        # target's relocations and a candidate row by the candidate's. Testing
        # both indices against a single merged set drops genuine mismatches
        # near a shift boundary.
        if target_row in target_relocations or candidate_row in candidate_relocations:
            masked.add(target_row)
            continue
        left = comparable_text(target[target_row])
        right = comparable_text(
            candidate[candidate_row], row_of_address=candidate_addresses
        )
        if pattern.search(left) or pattern.search(right):
            ring_rows.add(target_row)
            pending[target_row] = (left, right)
        else:
            fixed[target_row] = left == right

    matches = tuple(
        frozenset(
            row for row, (left, right) in pending.items() if coset.apply(right) == left
        )
        for coset in cosets
    )
    return _RowEvidence(
        fixed=fixed,
        matches=matches,
        ring_rows=frozenset(ring_rows),
        masked=frozenset(masked),
        unpaired=frozenset(unpaired),
    )


def _score_slot(
    slot: Slot,
    evidence: _RowEvidence,
    *,
    cosets: Sequence[Coset],
    minimum_evidence: int,
    fixed_coset: int | None = None,
) -> SlotScore:
    """Score one slot, choosing its coset only when the rows are evidence."""

    rows = range(slot.start, slot.stop + 1)
    masked = sum(1 for row in rows if row in evidence.masked)
    unpaired = sum(1 for row in rows if row in evidence.unpaired)
    fixed_bad = [row for row in rows if evidence.fixed.get(row) is False]
    ring_rows = [row for row in rows if row in evidence.ring_rows]
    compared = sum(1 for row in rows if row in evidence.fixed) + len(ring_rows)

    # A row is evidence about the phase only when the coset actually changes
    # its verdict. Rows that match (or fail) under every coset say nothing, and
    # a slot made only of those has no phase to report.
    informative = sum(
        1
        for row in ring_rows
        if len({row in matched for matched in evidence.matches}) > 1
    )

    def mismatches(index: int) -> list[int]:
        matched = evidence.matches[index]
        return sorted([*fixed_bad, *(row for row in ring_rows if row not in matched)])

    positional_rows = mismatches(0)
    if fixed_coset is not None:
        chosen = fixed_coset
        tied: tuple[str, ...] = ()
        evidence_kind = "fixed-by-context"
    elif informative < max(minimum_evidence, 1):
        chosen = 0
        tied = ()
        evidence_kind = "no-evidence"
    else:
        scores = [len(mismatches(index)) for index in range(len(cosets))]
        best = min(scores)
        winners = [index for index, value in enumerate(scores) if value == best]
        # Identity wins every tie: reporting a rotation the evidence does not
        # single out is how a coset-flipped object gets recorded as a win.
        chosen = 0 if 0 in winners else winners[0]
        tied = (
            tuple(cosets[index].label for index in winners) if len(winners) > 1 else ()
        )
        evidence_kind = "ambiguous" if tied else "measured"

    quotiented_rows = mismatches(chosen)
    return SlotScore(
        slot=slot,
        compared=compared,
        masked=masked,
        unpaired=unpaired,
        informative=informative,
        coset=cosets[chosen],
        coset_evidence=evidence_kind,
        tied=tied,
        quotiented=len(quotiented_rows),
        positional=len(positional_rows),
        quotiented_rows=tuple(quotiented_rows),
        positional_rows=tuple(positional_rows),
    )


def _with_baseline(score: SlotScore, baseline: SlotScore) -> SlotScore:
    """Attach the healed/broken split against a previous candidate.

    "This edit healed nine rows and broke four elsewhere" is a different fact
    from "the score moved by five", and the second one hides the trade every
    time. Both sides are measured on positional rows, which are comparable
    between two candidates; quotiented rows are not, because each candidate
    chooses its own coset.
    """

    before = set(baseline.positional_rows)
    after = set(score.positional_rows)
    healed = sorted(before - after)
    broken = sorted(after - before)
    return SlotScore(
        slot=score.slot,
        compared=score.compared,
        masked=score.masked,
        unpaired=score.unpaired,
        informative=score.informative,
        coset=score.coset,
        coset_evidence=score.coset_evidence,
        tied=score.tied,
        quotiented=score.quotiented,
        positional=score.positional,
        quotiented_rows=score.quotiented_rows,
        positional_rows=score.positional_rows,
        healed=len(healed),
        broken=len(broken),
        healed_rows=tuple(healed),
        broken_rows=tuple(broken),
    )


def build_phase_report(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    shift: ShiftDiff,
    slots: Sequence[Slot] | None = None,
    ring: tuple[str, ...] = DEFAULT_RING,
    coset_family: str = "all",
    minimum_evidence: int = 1,
    target_name: str = "target",
    candidate_name: str = "candidate",
    symbol: str | None = None,
    context: Sequence[Instruction] | None = None,
    context_shift: ShiftDiff | None = None,
    context_name: str | None = None,
    baseline: Sequence[Instruction] | None = None,
    baseline_shift: ShiftDiff | None = None,
    baseline_name: str | None = None,
    base_source: str | None = None,
    base_sha256: str | None = None,
    cache_notes: Sequence[str] = (),
) -> PhaseReport:
    """Read one candidate's phase vector against a target, slot by slot."""

    if not target:
        raise PhaseError("the target has no instruction rows to score against")
    last = len(target) - 1
    table = tuple(slots) if slots else (Slot(name="all", start=0, stop=last),)
    validate_partition(table, first=0, last=last)
    cosets = ring_cosets(ring, family=coset_family)

    evidence = _row_evidence(target, candidate, shift=shift, cosets=cosets, ring=ring)
    context_scores: tuple[SlotScore, ...] = ()
    fixed: dict[str, int] = {}
    if context is not None and context_shift is not None:
        context_evidence = _row_evidence(
            target, context, shift=context_shift, cosets=cosets, ring=ring
        )
        context_scores = tuple(
            _score_slot(
                slot,
                context_evidence,
                cosets=cosets,
                minimum_evidence=minimum_evidence,
            )
            for slot in table
        )
        fixed = {
            item.slot.name: cosets.index(item.coset)
            for item in context_scores
            if item.coset_evidence == "measured"
        }

    scores = [
        _score_slot(
            slot,
            evidence,
            cosets=cosets,
            minimum_evidence=minimum_evidence,
            fixed_coset=fixed.get(slot.name),
        )
        for slot in table
    ]

    if baseline is not None and baseline_shift is not None:
        baseline_evidence = _row_evidence(
            target, baseline, shift=baseline_shift, cosets=cosets, ring=ring
        )
        baseline_scores = [
            _score_slot(
                slot,
                baseline_evidence,
                cosets=cosets,
                minimum_evidence=minimum_evidence,
            )
            for slot in table
        ]
        scores = [
            _with_baseline(score, previous)
            for score, previous in zip(scores, baseline_scores, strict=True)
        ]

    return PhaseReport(
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        ring=ring,
        coset_family=coset_family,
        target_rows=len(target),
        candidate_rows=len(candidate),
        slots=tuple(scores),
        shift=shift,
        base_source=base_source,
        base_sha256=base_sha256,
        context_name=context_name,
        context_slots=context_scores,
        baseline_name=baseline_name,
        cache_notes=tuple(cache_notes),
    )


def coset_warning(report: PhaseReport) -> str | None:
    """Return the divergence warning when quotienting changed the answer."""

    rotated = [item for item in report.non_identity_slots if item.diverges]
    if not rotated:
        return None
    named = ", ".join(f"{item.slot.name}={item.coset.label}" for item in rotated)
    return (
        f"COSET: {len(rotated)} slot(s) sit at a non-identity ring coset "
        f"({named}), so the quotiented total ({report.quotiented}) and the "
        f"positional total ({report.positional}) are answers to different "
        "questions. Quotiented is what the object would score if the whole "
        "ring were renamed -- which it has not been. Rank candidates on "
        "positional; read quotiented to size the renaming."
    )


def shift_lines(report: PhaseReport) -> list[str]:
    """Describe the row shift and what it does to the slot boundaries."""

    shift = report.shift
    if report.instruction_delta == 0 and shift.edit_distance == 0:
        return ["shift: none -- the two streams align row for row"]
    lines = [
        f"ni: target {report.target_rows} candidate {report.candidate_rows} "
        f"({report.instruction_delta:+d})"
        + (" SHIFTED" if report.instruction_delta else "")
    ]
    if report.instruction_delta:
        lines.append(
            "  a row-for-row scorer would compare every row after the first "
            "insertion against its neighbour; rows below are paired through "
            "the alignment instead"
        )
    if shift.insertion_only and shift.cuts:
        lines.append(
            f"shift: insertion-only, {len(shift.cuts)} cut(s) at target row(s) "
            f"{sorted(set(shift.cuts))} -- slot scores are shift-compensated"
        )
    elif shift.blocks:
        lines.append(
            f"shift: not insertion-only ({shift.replaced} replaced, "
            f"{shift.deleted} deleted) -- rows inside those blocks are "
            "genuinely different instructions, not displaced ones"
        )
    return lines


def phase_lines(report: PhaseReport, *, detail: bool = False) -> list[str]:
    """Render one phase report for a terminal."""

    lines = [
        f"phase: {report.candidate_name} against {report.target_name}"
        + (f" ({report.symbol})" if report.symbol else ""),
    ]
    if report.base_sha256:
        lines.append(f"base: {report.base_source} sha256={report.base_sha256[:16]}")
    lines.extend(shift_lines(report))
    searched = len(ring_cosets(report.ring, family=report.coset_family))
    lines.append(
        f"ring: {' '.join(report.ring)} "
        f"({report.coset_family}; {searched} coset(s) searched)"
    )
    lines.append(
        f"slots: {len(report.slots)} named, partitioning target rows "
        f"0..{report.target_rows - 1} with no holes"
    )
    if report.context_name:
        lines.append(
            f"context: {report.context_name} -- each slot is scored at the "
            "coset the context measures, not at its own best fit"
        )
    lines.append("")

    name_width = max(6, max(len(item.slot.name) for item in report.slots))
    coset_width = max(
        len("no-evidence"),
        max(len(item.coset.label) + 1 for item in report.slots),
    )
    header = (
        f"{'slot'.ljust(name_width)}  {'rows':>6s} {'masked':>6s} {'info':>6s}  "
        f"{'coset'.ljust(coset_width)}  {'quotiented':>10s} {'positional':>10s}"
    )
    if report.baseline_name:
        header += f" {'healed':>7s} {'broken':>7s}"
    lines.append(header)
    for item in report.slots:
        label = item.coset.label
        if item.coset_evidence == "no-evidence":
            label = "no-evidence"
        elif item.coset_evidence == "ambiguous":
            label = f"{label}?"
        row = (
            f"{item.slot.name.ljust(name_width)}  {item.slot.rows:6d} "
            f"{item.masked:6d} {item.informative:6d}  {label.ljust(coset_width)}  "
            f"{item.quotiented:10d} {item.positional:10d}"
        )
        if report.baseline_name:
            row += f" {item.healed:7d} {item.broken:7d}"
        lines.append(row)
    total = (
        f"{'total'.ljust(name_width)}  {report.target_rows:6d} "
        f"{sum(item.masked for item in report.slots):6d} "
        f"{sum(item.informative for item in report.slots):6d}  "
        f"{('identity' if report.quotiented_is_bare else 'MIXED').ljust(coset_width)}  "
        f"{report.quotiented:10d} {report.positional:10d}"
    )
    if report.baseline_name:
        total += f" {report.healed:7d} {report.broken:7d}"
    lines.append(total)
    lines.append("")
    lines.append(
        "phase vector: "
        + " ".join(
            f"{item.slot.name}="
            + ("?" if item.coset_evidence == "no-evidence" else item.coset.label)
            for item in report.slots
        )
    )
    if report.quotiented_is_bare:
        lines.append(
            f"free={report.quotiented} (every slot at the identity coset, so "
            "this is also the positional count)"
        )
    else:
        rotated = ", ".join(
            f"{item.slot.name}={item.coset.label}" for item in report.non_identity_slots
        )
        lines.append(
            f"free={report.quotiented} [COSET {rotated}; "
            f"positional {report.positional}]"
        )
    warning = coset_warning(report)
    if warning:
        lines.extend(("", warning))
    ambiguous = [item for item in report.slots if item.coset_evidence == "ambiguous"]
    if ambiguous:
        lines.append("")
        for item in ambiguous:
            lines.append(
                f"AMBIGUOUS: slot {item.slot.name} scores the same under "
                f"{len(item.tied)} cosets ({', '.join(item.tied)}); its label "
                "is the identity of that tie, not a measurement"
            )
    blind = [item for item in report.slots if item.coset_evidence == "no-evidence"]
    if blind:
        lines.append("")
        for item in blind:
            lines.append(
                f"NO EVIDENCE: slot {item.slot.name} has {item.informative} row(s) "
                "whose match depends on the coset, so its phase is not "
                "measured here. Score it in a composition that uses the ring, "
                "or widen the slot -- do not record it as identity."
            )
    if report.context_slots:
        drifted = [
            (item, other)
            for item, other in zip(report.slots, report.context_slots, strict=True)
            if item.coset_evidence == "fixed-by-context"
            and other.coset.label != item.coset.label
        ]
        for item, other in drifted:  # pragma: no cover - defensive
            lines.append(
                f"CONTEXT: slot {item.slot.name} reads {item.coset.label} in "
                f"context and {other.coset.label} in isolation"
            )
    if report.baseline_name:
        lines.append("")
        lines.append(
            f"against {report.baseline_name}: healed {report.healed} row(s), "
            f"broke {report.broken} row(s), net "
            f"{report.broken - report.healed:+d} positional row(s)"
        )
    if report.cache_notes:
        lines.append("")
        lines.extend(report.cache_notes)
    if detail:
        lines.extend(_detail_lines(report))
    return lines


#: Residual runs quoted per slot before the rest are summarized. A slot that
#: is hundreds of runs deep is not being read row by row; the count and the
#: first runs are what locate the work.
DETAIL_RUNS = 20


def _detail_lines(report: PhaseReport) -> list[str]:
    """Per-slot residual runs: where inside a slot the mismatches actually live."""

    lines = ["", "residual by slot (quotiented rows, collapsed into runs):"]
    for item in report.slots:
        if not item.quotiented_rows:
            lines.append(f"  {item.slot.name}: clean")
            continue
        runs = mismatch_ranges(list(item.quotiented_rows))
        rendered = ", ".join(
            f"{start}" if start == stop else f"{start}..{stop} ({stop - start + 1})"
            for start, stop in runs[:DETAIL_RUNS]
        )
        if len(runs) > DETAIL_RUNS:
            rendered += f", ... {len(runs) - DETAIL_RUNS} more run(s)"
        lines.append(
            f"  {item.slot.name}: {item.quotiented} row(s) in {len(runs)} "
            f"run(s): {rendered}"
        )
    if report.baseline_name:
        lines.append("")
        lines.append("healed and broken rows by slot, collapsed into runs:")
        for item in report.slots:
            if not item.healed_rows and not item.broken_rows:
                continue
            lines.append(
                f"  {item.slot.name}: healed {_runs(item.healed_rows)}; "
                f"broke {_runs(item.broken_rows)}"
            )
    return lines


def _runs(rows: Sequence[int]) -> str:
    """Render row numbers as bounded, collapsed runs.

    A healed set can be a thousand rows wide, and a thousand row numbers on a
    terminal is not evidence anybody reads. The count leads, the first runs
    locate the work, and `--json` carries every number.
    """

    if not rows:
        return "none"
    ranges = mismatch_ranges(list(rows))
    rendered = ", ".join(
        f"{start}" if start == stop else f"{start}..{stop}"
        for start, stop in ranges[:DETAIL_RUNS]
    )
    if len(ranges) > DETAIL_RUNS:
        rendered += f", ... {len(ranges) - DETAIL_RUNS} more run(s)"
    return f"{len(rows)} row(s): {rendered}"
