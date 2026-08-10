"""Resolve %hi/%lo address arithmetic and classify the words a shift moved.

S0's hand-rolled census (a ~180-line spike run against a live DKR image --
see the shift-instrumentation campaign's S0-RESULT.md) surfaced two
properties either of which breaks a generalized resolver that does not model
them explicitly.

**Signed %lo wraps into %hi.** IDO's assembler does not split an address at
the 16-bit boundary; it splits the low 16 bits off as a *signed* add
immediate and folds the borrow into the high half, so ``%hi(addr)`` is one
greater than ``addr >> 16`` whenever ``%lo(addr)`` is negative. An insertion
that nudges an address across that boundary can move ``%lo`` between
``0xFFF0`` and ``0x0000`` while its paired ``lui`` -- correctly -- does not
move at all: naive splitting misreads that as two unrelated changes. The
signed arithmetic here (``hi16_for``/``lo16_for``/``compose``) is what keeps
the pairing legible. S0 hit this exactly once, at
``__CSPPostNextSeqEvent+0x25c`` (DKR us.v77, ROM ``0x0bccd8``), and a naive
``addr >> 16`` split would have reported it ``unexplained``.

**Value-first classification misattributes text.** A word whose full 32-bit
value happens to move by exactly the shift delta is not necessarily a data
pointer: a ``%lo`` immediate in a ``lw``/``sw``/``addiu`` whose displacement
did not sign-wrap moves by the *same* amount and is numerically
indistinguishable from a pointer, from the value alone. S0's own spike
classified value-first for the whole image and, by its own account, "absorbs
simple %lo immediates whose word-delta equals delta" into an abs32 bucket
that is honest about its count but not about what the words are. This module
classifies by *section* first -- decode a text word before ever comparing
its value -- which is the fix S0's own writeup called for. Run against the
same DKR image, this reclassifies most of that bucket: see
``build_word_census``.

Everything here reads raw big-endian words, never a disassembly: the whole
point of a shift census is to run before a candidate compiles, often against
retail bytes with no debug information at all.
"""

from __future__ import annotations

import struct
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "OPCODE_J",
    "OPCODE_JAL",
    "OPCODE_LUI",
    "OPCODE_SPECIAL",
    "DifferingWord",
    "GeneratedSpec",
    "NamedRange",
    "RangeModel",
    "RegionSpec",
    "StaleCandidate",
    "WhitelistEntry",
    "WordCensus",
    "WordRef",
    "alignment",
    "build_word_census",
    "check_image_delta",
    "compose",
    "decode_word",
    "default_n64_windows",
    "hi16_for",
    "lo16_for",
]

#: The MIPS opcode field (bits 31:26) values this module gives special
#: handling. Everything else decodes as the generic imm16 shape or, for
#: `SPECIAL`, as `"other"` (its low bits are a funct/shamt field, not an
#: address-shaped immediate).
OPCODE_J = 0x02
OPCODE_JAL = 0x03
OPCODE_LUI = 0x0F
OPCODE_SPECIAL = 0x00


# ---------------------------------------------------------------------------
# %hi/%lo arithmetic
# ---------------------------------------------------------------------------


def hi16_for(addr: int) -> int:
    """The ``%hi(addr)`` field: the ``lui`` immediate IDO's assembler emits.

    Adding ``0x8000`` before shifting is not rounding -- it is undoing the
    sign extension ``lo16_for`` is about to apply. Without it, an address
    whose low 16 bits are negative (``>= 0x8000``) would recombine one whole
    ``0x10000`` short of itself once the CPU sign-extends the ``%lo``
    immediate at run time.
    """

    return ((addr + 0x8000) >> 16) & 0xFFFF


def lo16_for(addr: int) -> int:
    """The ``%lo(addr)`` field, as the signed value it arithmetically is.

    The raw 16-bit encoding is ``lo16_for(addr) & 0xFFFF``; this returns the
    signed interpretation (``-0x8000..0x7FFF``) because that is what changes
    continuously as ``addr`` moves, and a caller comparing two ``%lo``
    values by their signed difference is what correctly spots a shift
    without being fooled by the sign-boundary wrap.
    """

    lo = addr & 0xFFFF
    return lo - 0x10000 if lo >= 0x8000 else lo


def compose(hi: int, lo: int) -> int:
    """Rebuild the 32-bit address one ``lui``/``%lo`` pair encodes.

    ``hi`` and ``lo`` are the raw 16-bit fields as they appear in the two
    instruction words (e.g. ``word & 0xFFFF``); ``lo`` is sign-extended
    before being added, mirroring what the CPU does executing the pair.
    ``compose(hi16_for(addr), lo16_for(addr) & 0xFFFF) == addr`` for every
    ``addr``, including across the sign boundary the module docstring
    describes.
    """

    signed_lo = lo16_for(lo & 0xFFFF)
    return (((hi & 0xFFFF) << 16) + signed_lo) & 0xFFFFFFFF


def alignment(value: int) -> int:
    """``value % 4``, named for the question a caller is really asking.

    A "pointer" that is not a multiple of 4 cannot be one -- it is exactly
    the "matched-garbage archaeology" S0 found sitting in
    ``gAudioHeapStack``: retail build-machine leftovers that merely look
    address-shaped (``0x8007ba73``, alignment 3). Cheapest signal that rules
    a stale-candidate value in or out before any window lookup.
    """

    return value % 4


# ---------------------------------------------------------------------------
# Minimal raw-word reference decoder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WordRef:
    """What one 32-bit big-endian instruction word says about an address.

    Not a disassembler: only the fields a reference-resolver needs are
    decoded, and `kind` says which of them are meaningful. `raw` is kept so
    a caller can always fall back to reading the word itself.
    """

    kind: str
    """``"j"``, ``"jal"``, ``"lui"``, ``"imm16"``, or ``"other"``."""

    raw: int
    opcode: int
    rs: int | None = None
    rt: int | None = None
    imm16: int | None = None
    """Raw unsigned 16-bit field (``lui``, ``imm16``)."""
    simm16: int | None = None
    """Signed interpretation of `imm16` (``imm16`` kind only)."""
    target26: int | None = None
    """Raw 26-bit word-index field (``j``/``jal`` only)."""

    def target(self, *, region: int) -> int | None:
        """The full 32-bit jump target, or `None` off a non-jump word.

        MIPS ``j``/``jal`` encode only a word index; the top 4 address bits
        come from the delay slot's own PC, not from the instruction. Pass
        that PC (or any address sharing its segment) as `region` -- only
        its high nibble is read.
        """

        if self.target26 is None:
            return None
        return (region & 0xF0000000) | (self.target26 << 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "raw": self.raw,
            "opcode": self.opcode,
            "rs": self.rs,
            "rt": self.rt,
            "imm16": self.imm16,
            "simm16": self.simm16,
            "target26": self.target26,
        }


def decode_word(word: int) -> WordRef:
    """Classify one big-endian 32-bit word by its instruction shape.

    Every I-type opcode (everything but `SPECIAL`, `j`, `jal`, and `lui`)
    shares the same ``rs``/``rt``/``imm16`` layout regardless of what it
    actually does -- a `beq`'s "immediate" is a branch offset, not an
    address -- and this function does not tell them apart. That is
    deliberate: reference extraction only needs the bit shape, and a
    census that classifies by section (see `build_word_census`) is what
    supplies the semantics this decoder withholds.
    """

    word &= 0xFFFFFFFF
    opcode = word >> 26
    if opcode in (OPCODE_J, OPCODE_JAL):
        return WordRef(
            kind="jal" if opcode == OPCODE_JAL else "j",
            raw=word,
            opcode=opcode,
            target26=word & 0x3FFFFFF,
        )
    if opcode == OPCODE_LUI:
        return WordRef(
            kind="lui",
            raw=word,
            opcode=opcode,
            rt=(word >> 16) & 0x1F,
            imm16=word & 0xFFFF,
        )
    if opcode == OPCODE_SPECIAL:
        return WordRef(kind="other", raw=word, opcode=opcode)
    imm16 = word & 0xFFFF
    return WordRef(
        kind="imm16",
        raw=word,
        opcode=opcode,
        rs=(word >> 21) & 0x1F,
        rt=(word >> 16) & 0x1F,
        imm16=imm16,
        simm16=imm16 - 0x10000 if imm16 >= 0x8000 else imm16,
    )


# ---------------------------------------------------------------------------
# Address-shape model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NamedRange:
    """One named ``[lo, hi)`` window in the 32-bit address space."""

    name: str
    lo: int
    hi: int


@dataclass(frozen=True)
class WhitelistEntry:
    """One address or address range accepted as authentic, with why.

    An exact address is written ``lo=addr, hi=addr + 1``: there is no
    separate "exact" shape, because a single address is just the range with
    the tightest possible width, and giving it one keeps `classify_value` a
    single lookup instead of two. Use `exact` to build one without doing
    the ``+ 1`` by hand.
    """

    lo: int
    hi: int
    reason: str

    @classmethod
    def exact(cls, addr: int, *, reason: str) -> WhitelistEntry:
        return cls(lo=addr, hi=addr + 1, reason=reason)


@dataclass(frozen=True)
class RangeModel:
    """Named address windows plus an explain-away whitelist.

    `classify_value` answers two independent questions about one 32-bit
    value read out of a word: which memory-map *window* it falls in (kseg0
    RAM, kseg1 hardware, ...), for free -- and whether it is on a whitelist
    of addresses known to be authentic despite looking like a stale
    pointer (a CIC boot address, a ucode-embedded default, ...). The
    whitelist is entirely the caller's business: only the caller knows
    which of its own hardcoded addresses are load-bearing, so this class
    never ships one.
    """

    windows: tuple[NamedRange, ...] = ()
    whitelist: tuple[WhitelistEntry, ...] = ()

    def classify_value(self, value: int) -> tuple[str | None, bool, str | None]:
        """Return ``(window_name, whitelisted, reason)`` for one value.

        `windows` are checked in the order given and the first match wins,
        so a caller that wants a narrower window (say ``cart``) to take
        precedence over a broader one it is nested inside (``kseg1``) lists
        the narrower one first.
        """

        window = None
        for candidate in self.windows:
            if candidate.lo <= value < candidate.hi:
                window = candidate.name
                break
        for entry in self.whitelist:
            if entry.lo <= value < entry.hi:
                return window, True, entry.reason
        return window, False, None


def default_n64_windows() -> tuple[NamedRange, ...]:
    """The N64 CPU's fixed-mapping segments, in `RangeModel` priority order.

    ``cart`` is the top half of ``kseg1`` (the PI cartridge domain,
    ``0xB0000000-0xBFFFFFFF``), so it is listed before the broader
    ``kseg1`` it is nested inside. ``segmented`` is a heuristic, not an
    authoritative N64 segment: some overlay/asset systems address memory as
    ``0x0X000000`` segment-relative, and this window flags values that
    merely *look* like that.
    """

    return (
        NamedRange("cart", 0xB0000000, 0xC0000000),
        NamedRange("kseg1", 0xA0000000, 0xC0000000),
        NamedRange("kseg0", 0x80000000, 0xA0000000),
        NamedRange("segmented", 0x00000000, 0x08000000),
    )


# ---------------------------------------------------------------------------
# Two-image pairing + word census
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionSpec:
    """One ``[start, end)`` ROM-offset span and how its words should read.

    ``kind`` is ``"text"``, ``"data"``, ``"blob"``, or ``"header"``. Only
    ``"text"`` changes behaviour in `build_word_census` -- it decodes a word
    before ever comparing its value; every other kind is value-first. The
    four names exist for a caller's own bookkeeping and report labels, not
    because this module treats them differently from one another.
    """

    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class GeneratedSpec:
    """One ``[start, end)`` ROM-offset span whose words are caller-generated.

    CRC header words and `calc_func_checksums` storage are the two S0 found:
    words a build step (not the compiler) writes, whose content a shift
    census must not try to explain by decoding or by value arithmetic.
    Checked before section-kind classification for every differing word, so
    a checksum word that happens to look lo16-shaped is never mislabeled.
    """

    start: int
    end: int
    label: str


@dataclass(frozen=True)
class DifferingWord:
    """One word whose value differs between the two images, and why."""

    offset: int
    old: int
    new: int
    label: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "old": self.old,
            "new": self.new,
            "label": self.label,
        }


@dataclass(frozen=True)
class StaleCandidate:
    """One word that did *not* move, but holds a value shaped like it should.

    Equal in both images, yet the value falls inside the caller's
    moved-VRAM range -- the hardcoded-pointer suspect class S0's dossier
    describes. `alignment`/`window`/`whitelisted`/`reason` are the features
    S0 found actually discriminate real hits from packed non-pointer
    fields, matched-garbage archaeology, and fixed-point table values: they
    are attached here so a caller ranks on them instead of re-deriving them.
    """

    offset: int
    value: int
    alignment: int
    window: str | None
    whitelisted: bool
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "value": self.value,
            "alignment": self.alignment,
            "window": self.window,
            "whitelisted": self.whitelisted,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WordCensus:
    """The full paired-word classification of one base/shifted image pair."""

    delta: int
    insertion_offset: int
    total_words: int
    counts: dict[str, int]
    """Per-label counts for every *differing* word, generated-spec labels
    included. Does not include stale candidates -- see `stale_total`."""
    differing_total: int
    unexplained_total: int
    stale_total: int
    unexplained: tuple[DifferingWord, ...]
    """Capped sample of `"unexplained"`-labelled words; `unexplained_total`
    is the exact count regardless of the cap."""
    stale: tuple[StaleCandidate, ...]
    """Capped sample of stale candidates; `stale_total` is the exact count."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "delta": self.delta,
            "insertion_offset": self.insertion_offset,
            "total_words": self.total_words,
            "counts": dict(self.counts),
            "differing_total": self.differing_total,
            "unexplained_total": self.unexplained_total,
            "stale_total": self.stale_total,
            "unexplained": [item.as_dict() for item in self.unexplained],
            "stale": [item.as_dict() for item in self.stale],
        }


def _classify_text_word(old: int, new: int, delta: int) -> str:
    """Decode-first classification for a word inside a ``"text"`` region.

    Order matches the shape of the evidence, not the frequency of the
    classes: a word's opcode is checked before its value is ever compared,
    because a ``%lo`` immediate that moved by exactly `delta` is
    numerically identical to a data pointer that did the same thing, and
    only the decode tells them apart (see the module docstring).
    """

    op_o, op_n = old >> 26, new >> 26
    if op_o == op_n and op_o in (OPCODE_J, OPCODE_JAL):
        if (new & 0x3FFFFFF) - (old & 0x3FFFFFF) == delta >> 2:
            return "j26-tracks"
    if op_o == op_n:
        imm_d = (new & 0xFFFF) - (old & 0xFFFF)
        top_same = (old >> 16) == (new >> 16)
        if op_o == OPCODE_LUI and top_same and imm_d in (1, -0xFFFF):
            return "hi16-adjust"
        if top_same and imm_d in (delta, delta - 0x10000):
            return "lo16-tracks"
    if new - old == delta:
        return "abs32-tracks"
    return "unexplained"


def _classify_value_word(old: int, new: int, delta: int) -> str:
    """Value-first classification for a ``"data"``/``"blob"``/``"header"`` word.

    No decode: a data word's bit pattern is not an instruction, so the only
    honest test is whether its value moved by exactly the shift.
    """

    if new - old == delta:
        return "abs32-tracks"
    return "unexplained"


def _span_lookup(
    spans: Sequence[tuple[int, int, str]]
) -> tuple[list[int], list[tuple[int, int, str]]]:
    ordered = sorted(spans, key=lambda item: item[0])
    return [item[0] for item in ordered], ordered


def _label_at(
    offset: int, starts: list[int], ordered: list[tuple[int, int, str]]
) -> str | None:
    index = bisect_right(starts, offset) - 1
    if index >= 0 and offset < ordered[index][1]:
        return ordered[index][2]
    return None


def check_image_delta(base: bytes, shifted: bytes, *, delta: int) -> None:
    """Refuse a pair whose size does not account for the declared delta.

    Cheap, and the most legible failure this module can report -- two
    lengths and a subtraction -- so callers that derive other things from
    `delta` first (`derive_anchor` picks an insertion point; a wrong delta
    usually means no symbol moved by it) should run this check *before*
    that derivation, not after. An anchor failure is real but vague; this
    one names the arithmetic directly. QA found this buried behind an
    auto-derived anchor's own "no object-backed symbol ... moved by the
    declared delta" -- the same fact, reported one step later and vaguer.
    """

    if len(base) % 4 or len(shifted) % 4:
        raise ValueError("both images must be a whole number of 32-bit words")
    if len(shifted) - len(base) != delta:
        raise ValueError(
            f"shifted image is {len(shifted) - len(base):+d} bytes longer than "
            f"base, not the declared delta {delta:+d}"
        )


def build_word_census(
    base: bytes,
    shifted: bytes,
    *,
    insertion_offset: int,
    delta: int,
    regions: Sequence[RegionSpec] = (),
    generated: Sequence[GeneratedSpec] = (),
    default_kind: str = "data",
    moved_range: tuple[int, int] | None = None,
    range_model: RangeModel | None = None,
    detail_cap: int = 60,
) -> WordCensus:
    """Pair two images word-by-word and classify every difference.

    Pairing: words below `insertion_offset` compare positionally; words at
    or above it compare against `shifted` offset by `delta` -- the
    shift_align lesson at whole-image scale (see that module's docstring).

    Classification, per differing pair:

    1. A `generated` span covering the offset wins outright, labelled with
       its own `GeneratedSpec.label` -- checked before section kind, so a
       checksum word that happens to look lo16-shaped is never misdecoded.
    2. Otherwise the covering `regions` span's `kind` selects decode-first
       (`"text"`) or value-first (anything else) classification.
    3. An offset no `RegionSpec` covers falls back to `default_kind`.

    Equal pairs are never classified -- there is nothing to explain about a
    word that did not change -- except that a value inside `moved_range`
    (VRAM-space ``[lo, hi)``) is collected as a `StaleCandidate`: it should
    have moved and did not, so it is a suspect regardless of what section
    it lives in. `range_model`, when given, attaches a window/whitelist
    verdict to each one.
    """

    check_image_delta(base, shifted, delta=delta)

    region_starts, region_spans = _span_lookup(
        [(item.start, item.end, item.kind) for item in regions]
    )
    generated_starts, generated_spans = _span_lookup(
        [(item.start, item.end, item.label) for item in generated]
    )

    counts: dict[str, int] = {}
    unexplained: list[DifferingWord] = []
    stale: list[StaleCandidate] = []
    stale_total = 0

    n_words = len(base) // 4
    for index in range(n_words):
        offset = index * 4
        shifted_offset = offset + delta if offset >= insertion_offset else offset
        old = struct.unpack_from(">I", base, offset)[0]
        new = struct.unpack_from(">I", shifted, shifted_offset)[0]

        if old == new:
            if moved_range is not None and moved_range[0] <= old < moved_range[1]:
                stale_total += 1
                if len(stale) < detail_cap:
                    window = whitelisted = reason = None
                    if range_model is not None:
                        window, whitelisted, reason = range_model.classify_value(old)
                    stale.append(
                        StaleCandidate(
                            offset=offset,
                            value=old,
                            alignment=alignment(old),
                            window=window,
                            whitelisted=bool(whitelisted),
                            reason=reason,
                        )
                    )
            continue

        label = _label_at(offset, generated_starts, generated_spans)
        if label is None:
            kind = _label_at(offset, region_starts, region_spans) or default_kind
            classify = _classify_text_word if kind == "text" else _classify_value_word
            label = classify(old, new, delta)

        counts[label] = counts.get(label, 0) + 1
        if label == "unexplained" and len(unexplained) < detail_cap:
            unexplained.append(
                DifferingWord(offset=offset, old=old, new=new, label=label)
            )

    return WordCensus(
        delta=delta,
        insertion_offset=insertion_offset,
        total_words=n_words,
        counts=dict(sorted(counts.items())),
        differing_total=sum(counts.values()),
        unexplained_total=counts.get("unexplained", 0),
        stale_total=stale_total,
        unexplained=tuple(unexplained),
        stale=tuple(stale),
    )
