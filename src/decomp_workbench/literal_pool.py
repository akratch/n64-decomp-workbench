"""Resolve literal-pool accesses so symbol-naming density stops being evidence.

A decomp target and its candidate almost never anchor their read-only data the
same way.  On the recorded ``object_interaction`` campaign the target object
carried one *named external* symbol per literal (``D_80052A9C``,
``D_80052AA0``, ...) with a zero addend, while the candidate the compiler
produced carried a single dense anonymous ``.rodata`` section symbol with the
slot number in the addend.  Every one of the 59 pool sites therefore rendered
as a different ``(symbol, addend)`` pair -- and 29 of them additionally as a
different printed ``N(at)`` offset -- even though both objects load *the same
slot of the same pool* at every one of those sites.

Classing that as evidence produced 88 rows against a pair whose pool accesses
agree site for site, and cost the campaign a planned work item ("fix the
literal pool") that had nothing to fix.

This module resolves each literal access to a slot that survives the naming
density, in two tiers, and says which tier it used:

``absolute``
    Both sides anchor on a *section* symbol, so the relocation resolves to a
    byte offset inside a named section.  Two sites agree iff their
    ``(section kind, byte offset, access width)`` agree.  This is the strong
    answer and it catches a genuinely permuted or resized pool.

``anchor-correspondence``
    At least one side anchors on opaque named symbols, whose addresses this
    object does not contain -- so no absolute offset exists to compare, and
    inventing one from a symbol-name convention would be a guess.  What *is*
    checkable without a link map is whether the two objects' pool anchors are
    in one-to-one correspondence: site for site, the same target anchor must
    always meet the same candidate anchor and vice versa, at the same access
    width.  A candidate that folded two of the target's slots into one, split
    one into two, or read a different slot at some site breaks the bijection
    exactly at the offending rows.

Neither tier claims the two pools hold the same *bytes*: the campaign's target
object has no ``.rodata`` section at all, so that claim is not available from
the objects and is left to the project's link or ROM check.  What the caller
gets is an honest statement about the *accesses*, plus the two slot counts so a
reader can see a pool that changed size.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .model import Instruction

__all__ = [
    "ABSOLUTE",
    "ACCESS_WIDTHS",
    "CORRESPONDENCE",
    "SECTION_KINDS",
    "UNRESOLVED",
    "PoolAccess",
    "PoolComparison",
    "PoolReport",
    "comparable",
    "compare_pool_accesses",
    "pool_accesses",
]

#: ELF section names collapsed to the *kind* of pool they are.  A candidate may
#: emit ``.rodata`` where a target emits ``.rdata`` purely because the two
#: assemblers spell the same read-only section differently; that is a spelling,
#: not a difference in what the code reads.
SECTION_KINDS: dict[str, str] = {
    ".rodata": "rodata",
    ".rdata": "rodata",
    ".srodata": "rodata",
    ".lit4": "rodata",
    ".lit8": "rodata",
    ".data": "data",
    ".sdata": "data",
    ".bss": "bss",
    ".sbss": "bss",
    ".text": "text",
}

#: Bytes an access reads or writes, by opcode.  ``0`` means the instruction
#: materializes the *address* (``addiu``/``ori`` after a ``lui``) rather than
#: touching the pool, which is a different kind of site and must not be
#: matched against a load of the same slot.
ACCESS_WIDTHS: dict[str, int] = {
    "lb": 1,
    "lbu": 1,
    "sb": 1,
    "lh": 2,
    "lhu": 2,
    "sh": 2,
    "ll": 4,
    "lw": 4,
    "lwc1": 4,
    "lwl": 4,
    "lwr": 4,
    "lwu": 4,
    "sc": 4,
    "sw": 4,
    "swc1": 4,
    "swl": 4,
    "swr": 4,
    "ld": 8,
    "ldc1": 8,
    "ldl": 8,
    "ldr": 8,
    "sd": 8,
    "sdc1": 8,
    "sdl": 8,
    "sdr": 8,
}

#: Relocation kinds whose instruction carries the high half of an address.
HIGH_KINDS = frozenset({"R_MIPS_HI16"})
#: Relocation kinds whose instruction carries the low half, and the access.
LOW_KINDS = frozenset({"R_MIPS_LO16"})
#: Relocation kinds that address the pool in one instruction, with no pair.
DIRECT_KINDS = frozenset({"R_MIPS_GPREL16", "R_MIPS_LITERAL"})

#: Resolution tiers, in decreasing strength.  Reported beside the counts so a
#: reader knows which question was actually answered.
ABSOLUTE = "absolute"
CORRESPONDENCE = "anchor-correspondence"
UNRESOLVED = "unresolved"


#: What a relocated site contributes.  An ``access`` carries the addend that
#: selects the datum; an ``anchor`` is the ``lui`` half, whose printed field is
#: entirely the linker's and which therefore names a pool without selecting a
#: slot in it.
ACCESS = "access"
ANCHOR = "anchor"


@dataclass(frozen=True)
class PoolAccess:
    """One instruction's relocated reference into a data pool."""

    index: int
    #: ``access`` or ``anchor``; see above.
    role: str
    #: The pool kind when the anchor is a section symbol, else ``None``.
    section: str | None
    #: The relocation's symbol spelling, as objdump printed it.
    anchor: str
    #: The signed 16-bit addend selecting the slot, for an ``access``; ``0``
    #: for an ``anchor``.  The low half alone is deliberate: it is what the
    #: instruction actually encodes, it is unambiguous, and a literal pool
    #: addressed through one ``lui`` reaches 32KB either way.  Deriving a full
    #: address instead would require pairing each ``lui`` with its load, and
    #: that pairing is *not* recoverable from an object whose pool sites all
    #: share one section symbol -- the campaign pair holds an interleaved
    #: ``hi(A) hi(B) lo(B) lo(A)`` group that any per-symbol rule mispairs.
    offset: int
    #: Bytes the access touches; ``0`` for an anchor or for an ``addiu``-style
    #: address materialization, which is a different kind of site.
    width: int

    @property
    def slot(self) -> tuple[str, int]:
        """The object-local identity of the datum this site reads."""

        return (self.anchor, self.offset)


@dataclass(frozen=True)
class PoolComparison:
    """What the two objects' literal-pool accesses say about each other."""

    resolution: str
    agreeing: frozenset[int]
    differing: frozenset[int]
    target_slots: int
    candidate_slots: int

    @property
    def slots_differ(self) -> bool:
        return self.target_slots != self.candidate_slots

    def as_dict(self) -> dict[str, object]:
        return {
            "resolution": self.resolution,
            "agreeing_sites": len(self.agreeing),
            "differing_sites": len(self.differing),
            "target_slots": self.target_slots,
            "candidate_slots": self.candidate_slots,
        }


@dataclass(frozen=True)
class PoolReport:
    """The literal-pool reading a comparison reports, with its row counts.

    The counts come from the *classification*, not from the reading: a site the
    reading calls differing may still be owned by a larger difference at the
    same row (a moved register), in which case it keeps that class and is not
    counted here.
    """

    resolution: str
    matches: int
    layout_mismatches: int
    target_slots: int
    candidate_slots: int


def _low_half(instruction: Instruction) -> int:
    return instruction.word_value & 0xFFFF


def _signed(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _width(instruction: Instruction) -> int:
    return ACCESS_WIDTHS.get(instruction.opcode, 0)


def pool_accesses(instructions: Sequence[Instruction]) -> dict[int, PoolAccess]:
    """Return every relocated data reference, keyed by instruction index.

    No ``hi``/``lo`` pairing happens here, on purpose: see ``PoolAccess.offset``
    for why the pairing is not recoverable from a dense pool.  A ``lui`` is
    recorded as an ``anchor`` (which pool) and the load or store as an
    ``access`` (which slot of it), and the comparison judges each kind by what
    it actually encodes.
    """

    accesses: dict[int, PoolAccess] = {}
    for index, item in enumerate(instructions):
        for relocation in item.relocations:
            if relocation.kind in HIGH_KINDS:
                role, offset, width = ANCHOR, 0, 0
            elif relocation.kind in LOW_KINDS or relocation.kind in DIRECT_KINDS:
                role = ACCESS
                offset, width = _signed(_low_half(item)), _width(item)
            else:
                continue
            symbol = relocation.symbol or ""
            accesses[index] = PoolAccess(
                index=index,
                role=role,
                section=SECTION_KINDS.get(symbol),
                anchor=symbol,
                offset=offset,
                width=width,
            )
            break
    return accesses


def _slot_count(accesses: dict[int, PoolAccess]) -> int:
    return len({item.slot for item in accesses.values() if item.role == ACCESS})


def comparable(left: PoolAccess, right: PoolAccess) -> bool:
    """Return whether two sites may be judged against each other at all.

    Two ``anchor`` halves naming the *same* symbol are excluded: the only thing
    that can differ between them is the ``lui`` immediate, which the linker
    overwrites, and which the relocation classifier already reports correctly.
    A pool verdict there would claim to have resolved something it did not.
    """

    if left.role != right.role:
        return False
    return left.role == ACCESS or left.anchor != right.anchor


def compare_pool_accesses(
    pairs: Sequence[tuple[int, PoolAccess, PoolAccess]],
    *,
    target_accesses: dict[int, PoolAccess],
    candidate_accesses: dict[int, PoolAccess],
) -> PoolComparison:
    """Decide, per aligned row, whether the two sides read the same slot.

    ``pairs`` must carry *every* aligned row where both sides have a comparable
    site -- including the rows that already agree byte for byte.  Those rows
    are what pins the correspondence down: a row that agrees proves its two
    slots are one datum, and a later row that pairs one of them with a
    different slot is then a real difference rather than a free choice.

    The correspondence is established in row order, so the first spelling wins
    and later conflicts are reported at the rows that conflict.
    """

    target_slots = _slot_count(target_accesses)
    candidate_slots = _slot_count(candidate_accesses)
    access_pairs = [item for item in pairs if item[1].role == ACCESS]
    if not access_pairs:
        return PoolComparison(
            resolution=UNRESOLVED,
            agreeing=frozenset(),
            differing=frozenset(),
            target_slots=target_slots,
            candidate_slots=candidate_slots,
        )
    agreeing: set[int] = set()
    differing: set[int] = set()
    #: Anchor pairs the access rows justified, and by how much they are
    #: displaced.  An `anchor` row is judged against this and nothing else: a
    #: `lui` says *which pool*, and the loads under it say which slots.
    displacement: dict[tuple[str, str], int] = {}

    if all(
        left.section is not None and right.section is not None
        for _, left, right in access_pairs
    ):
        for row, left, right in access_pairs:
            if (left.section, left.offset, left.width) == (
                right.section,
                right.offset,
                right.width,
            ):
                agreeing.add(row)
                displacement.setdefault((left.anchor, right.anchor), 0)
            else:
                differing.add(row)
        resolution = ABSOLUTE
    else:
        # Three rules, and an access row has to survive all three.
        #
        # * An anchor meeting *itself* is the strict case: an identical symbol
        #   names an identical address in both objects, so the two addends are
        #   directly comparable and must be equal.
        # * Otherwise the two objects' slots must be in one-to-one
        #   correspondence.  The correspondence is over *slots*, not anchor
        #   names, precisely because the sparse side has one anchor per slot
        #   and the dense side has one anchor for all of them; keying it on
        #   names would report the whole dense pool as a collision.
        # * The displacement between one anchor pair must be constant.  This is
        #   what the slot bijection alone cannot see: two target slots four
        #   bytes apart landing ninety-two bytes apart in the candidate is a
        #   one-to-one map and still a different pool.
        forward: dict[tuple[str, int], tuple[str, int]] = {}
        backward: dict[tuple[str, int], tuple[str, int]] = {}
        for row, left, right in access_pairs:
            delta = right.offset - left.offset
            if left.width != right.width:
                differing.add(row)
            elif left.anchor == right.anchor:
                (agreeing if delta == 0 else differing).add(row)
            elif (
                forward.setdefault(left.slot, right.slot) != right.slot
                or backward.setdefault(right.slot, left.slot) != left.slot
                or displacement.setdefault((left.anchor, right.anchor), delta) != delta
            ):
                differing.add(row)
            else:
                agreeing.add(row)
        resolution = CORRESPONDENCE

    for row, left, right in pairs:
        if left.role != ANCHOR:
            continue
        if (left.anchor, right.anchor) in displacement:
            agreeing.add(row)
        else:
            differing.add(row)
    return PoolComparison(
        resolution=resolution,
        agreeing=frozenset(agreeing),
        differing=frozenset(differing),
        target_slots=target_slots,
        candidate_slots=candidate_slots,
    )
