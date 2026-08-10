"""The empirical half of the shiftability instrumentation: the referee.

``shift audit`` reads one image and ranks how confidently each address-shaped
word is a *reference*. It cannot say which of them a link would actually move,
and says so: a linked N64 ROM keeps no relocations, so a pointer the linker
resolved and a constant somebody typed are the same four bytes. This module
answers the question the audit hands off -- by building the same objects twice
against two linker scripts that differ by an inserted pad, and explaining every
byte of the difference.

Its headline is a pair. ``unexplained_changed`` is S0's gate: a word that
changed for a reason no class accounts for is either a bug in the census or a
build that is not the controlled experiment it claims to be, and S0 measured
zero of them across two deltas on DKR ``us.v77``. ``stale_confirmed`` is this
stage's own: a word the static audit ranked ``high`` -- compiled data landing
exactly on a symbol's start -- that a real shift left sitting where it was.
That is the hardcoded-pointer finding in its strongest available form, and on
a correct reference build there must be none of those either.

Four properties of the problem shape everything here, and every one of them
was measured rather than assumed.

**Pairing is corrected, not positional.** Words below the insertion compare
positionally; words at or above it compare against the shifted image offset by
delta. S0 measured what the naive alternative costs: ~2.8M differing words
instead of 20,687.

**The insertion point is derived.** Typing a ROM offset that is off by one
word silently reclassifies the entire image, so `derive_anchor` reads it out
of the two maps -- the lowest VRAM at which shared symbols begin differing by
delta -- and reports the boundary it straddles as evidence. The derivation is
restricted to the map's own movable window on purpose: a cascade script
assigns a dozen ``ABSOLUTE`` size symbols (``main_TEXT_SIZE`` and friends)
that also grow by exactly delta while living nowhere near VRAM, and the
unrestricted minimum picks one of those.

**Static confidence and empirical movement are two axes, not one.** Neither
alone is a finding. A ``high``-tier word that moved is a healthy reference; a
``low``-tier word that did not move is one of the false-positive families S0
catalogued (packed shorts, matched-garbage archaeology, fixed-point table
values). Only the corner where the two disagree -- ranked ``high``, did not
move -- is worth a human's attention, and `MERGE_TIERS` is that merge, printed
with the report so a reader can see the rule rather than infer it.

**Some words are written by a build step, not a compiler.** CRC header words
and ``calc_func_checksums`` storage are position-keyed and must be recognised
before any decode or value test, or the census explains them wrongly. Which
leads to the rule this module exists to carry:

**The checksum-consistency rule.** DKR embeds, for a handful of hand-picked
functions, a byte-sum of that function's own compiled code, and a post-link
step recomputes and patches it. In 2021 one audio function was left off that
step's allowlist (``ab9510e``); under a shift its bytes changed, its frozen
checksum did not, the game's own runtime self-check failed, and the symptom
was "cursed audio". S2's archaeology (``s2/TIMETRAVEL.md``, bug 8) concluded
that neither a static scan nor a generic stale-word detector can see it --
the word holds a byte-sum, not an address, so there is nothing for either
mechanism to key off -- but that it maps onto one nameable rule: *if any word
inside a protected function's body changed, that function's checksum word must
have changed too*. `checksum_verdicts` implements exactly that, plus the
inverse (`checksum-orphan`: the checksum moved and the body did not), and
reports a status for every pair rather than staying silent about the ones that
pass.

Nothing here is a verdict about a project's correctness. It is evidence:
counts, coordinates, and the rule that produced each label.
"""

from __future__ import annotations

import struct
import subprocess
from bisect import bisect_right
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ldmap import (
    ElfSymbols,
    LdMap,
    MovementAudit,
    SymbolMovement,
    audit_symbol_movement,
)
from .mips_refs import (
    GeneratedSpec,
    RangeModel,
    RegionSpec,
    WordCensus,
    build_word_census,
    check_image_delta,
)
from .pins import default_pin_model
from .shift_audit import (
    Hit,
    MovableWindow,
    Region,
    build_region_table,
    movable_window,
    scan_regions,
)

__all__ = [
    "CHECKSUM_RULES",
    "MERGE_TIERS",
    "SHADOWING_PIN",
    "SHIFT_REHEARSE_SCHEMA",
    "SYMBOL_RULES",
    "SYMBOL_STALE",
    "WRAPPER_CONTRACT",
    "Anchor",
    "ChecksumRule",
    "ChecksumVerdict",
    "Disagreement",
    "Orchestration",
    "PaddedScript",
    "Rehearsal",
    "RunRecord",
    "StaleVerdict",
    "SymbolCensus",
    "SymbolFinding",
    "SymbolRule",
    "build_rehearsal",
    "checksum_verdicts",
    "cross_delta_disagreements",
    "derive_anchor",
    "orchestrate",
    "orchestrate_lines",
    "pad_ld_script",
    "parse_checksum_pair",
    "parse_mapping",
    "parse_offsets",
    "reconcile",
    "rehearse_lines",
    "symbol_census",
    "symbol_extent",
]

#: JSON identity for both modes' reports. One schema, two shapes, told apart
#: by ``mode``: an orchestration is a list of analyses plus the comparison
#: between them, and a consumer that can read one can read the other.
SHIFT_REHEARSE_SCHEMA = "decomp-workbench-shift-rehearse-v1"

#: What an unmoved word means at each static-confidence tier. The merge is the
#: whole point of running both halves: a ``high`` word that did not move is the
#: finding, and a ``low`` one is the noise floor S0 measured (1,494 of DKR's
#: 1,501 stale candidates). ``medium`` is neither -- it is the review queue,
#: and S2's calibration puts 650 of 657 ``medium`` hits among the words a real
#: shift moved, so the seven that stay put are worth a look and not an alarm.
MERGE_TIERS: dict[str, str] = {
    "high": "stale-confirmed",
    "medium": "stale-review",
    "low": "noise",
}

#: What a word that *did* move is called, at any tier: the reference worked.
TRACKS = "tracks"

#: What a word that changed by something other than the delta is called. No
#: tier makes this benign -- it is an address-shaped word that moved by the
#: wrong amount, which is a different question from either headline.
CHANGED_OTHER = "changed-other"


@dataclass(frozen=True)
class ChecksumRule:
    """One published outcome the checksum-consistency rule can report."""

    name: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence}


#: The rule table, shipped inside every report. Four outcomes, because
#: "nothing to say" is not one of them: a pair that passes says so, with the
#: basis it passed on.
CHECKSUM_RULES: tuple[ChecksumRule, ...] = (
    ChecksumRule(
        "pass",
        "the body and the checksum word agree: either the shift touched "
        "neither (basis inert) or it changed both (basis tracked)",
    ),
    ChecksumRule(
        "checksum-stale",
        "the function's body changed and its checksum word did not -- the "
        "2021 cursed-audio class, where a protected function was left off "
        "the post-link patcher's allowlist and the game's own runtime "
        "self-check failed",
    ),
    ChecksumRule(
        "checksum-orphan",
        "the checksum word changed while the function's body did not: the "
        "patcher wrote a value the body does not explain, so either the "
        "extent read from the map is wrong or the word is not what it is "
        "named",
    ),
    ChecksumRule(
        "unresolved",
        "a named symbol is missing from the map, has no ROM placement, or "
        "has no extent the map can bound -- reported rather than skipped",
    ),
)


# ---------------------------------------------------------------------------
# Where the pad went in
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """The insertion point, and the evidence it was derived from."""

    vram: int
    rom: int
    source: str
    """``"auto"`` (read out of the two maps) or ``"symbol"`` (the caller
    named one)."""
    symbol: str | None
    highest_unmoved: int | None
    """The highest in-window VRAM *any* shared symbol kept -- assignment
    symbols included, unlike `lowest_moved` (WB-142). With `lowest_moved` it
    normally brackets the true insertion point; a wide bracket means the maps
    place no symbol near the pad.

    It can also come out *above* `lowest_moved`, which is not a bracket
    failure but a finding showing through: an absolute pin above the
    insertion that the relink did not move is exactly what
    ``symbol_stale``/``shadowing_pins`` count (pilotwings64 reports
    ``0x803571f0`` here, the pin S6 convicted). Reported unrestricted for
    that reason -- narrowing it to object-backed symbols would hide the one
    shape worth seeing."""

    lowest_moved: int | None
    """The lowest in-window VRAM an **object-backed** shared symbol moved
    `delta` from: the auto anchor. See `derive_anchor` for why the
    restriction."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor_vram": self.vram,
            "anchor_rom": self.rom,
            "anchor_source": self.source,
            "anchor_symbol": self.symbol,
            "anchor_highest_unmoved": self.highest_unmoved,
            "anchor_lowest_moved": self.lowest_moved,
        }


def derive_anchor(
    base: LdMap,
    shifted: LdMap,
    *,
    delta: int,
    window_lo: int,
    window_hi: int,
    symbol: str | None = None,
) -> Anchor:
    """Locate the insertion point, from a named symbol or from the two maps.

    Auto-derivation is the lowest VRAM at which shared symbols start
    differing by `delta`, restricted twice: to ``[window_lo, window_hi)``,
    and -- **WB-142** -- to symbols that are not linker-script assignments.

    The window restriction is not cosmetic: a cascade script's ``ABSOLUTE``
    size symbols grow by exactly delta too, and DKR's ``main_TEXT_SIZE`` sits
    at ``0xd08e0`` -- the unrestricted minimum, and 2 GB away from the
    answer.

    **WB-142, filed from S6's pilotwings64 run (``s6/PW64-SHIFT-CONFIG.md``
    §3.3).** ``--anchor auto`` refused there with *"the anchor VRAM
    0x00001050 has no ROM placement in the base map"*, because splat emits
    ``<seg>_ROM_START``/``_ROM_END`` for every segment unconditionally, those
    hold small ROM offsets that look like low VRAM, and every one of them
    above the pad grows by exactly delta. ``entry_ROM_END = 0x1050`` was the
    numeric minimum, and the anchor derivation followed it out of the layout
    entirely. S7's `~decomp_workbench.shift_audit.MOVABLE_FLOOR_MIN` has
    since raised the window floor above every such value, so that exact
    refusal no longer reproduces -- but the class it exposed is general, and
    the fix belongs one level down from the window:

    **an assignment names a boundary; only an object-backed symbol names a
    byte.** The anchor is a byte -- the first one the pad moved -- and it has
    to translate through an ``AT()`` placement to a ROM offset. A
    ``<seg>_ROM_*`` symbol's value is a ROM offset already and translates to
    nothing; a ``<seg>_SIZE`` symbol's value is a length; and even a perfectly
    ordinary in-window boundary symbol collides with the insertion point from
    the wrong side. pilotwings64 has six shared symbols at the true anchor
    ``0x802000a0`` and five of them are assignments: without this restriction
    the reported ``anchor_symbol`` is ``entry_BSS_END`` -- the *end of the
    segment below the pad*, which reads as though the pad went in before the
    entrypoint. With it, the answer is ``func_802000A0``, the first byte that
    actually moved, and it agrees with the anchor S6 chose by hand
    (``--anchor kernel_TEXT_START``, ``anchor_rom=0x1050``).

    `highest_unmoved` stays unrestricted -- see `Anchor`.

    Raises `ValueError` rather than guessing: an anchor that is wrong by one
    word reclassifies the whole image, so there is no safe fallback.
    """

    shared = base.symbol_names() & shifted.symbol_names()
    moved: list[int] = []
    unmoved: list[int] = []
    for name in shared:
        placed = base.symbol(name)
        relinked = shifted.symbol(name)
        assert placed is not None and relinked is not None  # from shared names
        if not window_lo <= placed.address < window_hi:
            continue
        movement = relinked.address - placed.address
        if movement == delta and not placed.is_assignment:
            moved.append(placed.address)
        elif movement == 0:
            unmoved.append(placed.address)

    highest_unmoved = max(unmoved) if unmoved else None
    lowest_moved = min(moved) if moved else None

    if symbol is not None:
        placed = base.symbol(symbol)
        if placed is None:
            raise ValueError(f"--anchor {symbol!r} is not a symbol the base map places")
        vram, source, named = placed.address, "symbol", symbol
    else:
        if lowest_moved is None:
            raise ValueError(
                f"no object-backed symbol inside the movable window "
                f"[0x{window_lo:08x}, 0x{window_hi:08x}) moved by the declared "
                f"delta 0x{delta:x}: either the delta is wrong, the two maps "
                "do not describe the same relink, or this map places nothing "
                "but linker-script assignments in its own window "
                "(pass --anchor <symbol> to name the insertion point yourself)"
            )
        vram, source = lowest_moved, "auto"
        named = min(
            name
            for name in shared
            if (placed := base.symbol(name)) is not None
            and not placed.is_assignment
            and placed.address == lowest_moved
            and (relinked := shifted.symbol(name)) is not None
            and relinked.address - placed.address == delta
        )

    rom = base.rom_for_vram(vram)
    if rom is None:
        raise ValueError(
            f"the anchor VRAM 0x{vram:08x} has no ROM placement in the base "
            "map: only a section that declared AT() can be translated"
        )
    return Anchor(
        vram=vram,
        rom=rom,
        source=source,
        symbol=named,
        highest_unmoved=highest_unmoved,
        lowest_moved=lowest_moved,
    )


# ---------------------------------------------------------------------------
# The checksum-consistency rule
# ---------------------------------------------------------------------------


def symbol_extent(ldmap: LdMap, name: str) -> tuple[int, int] | None:
    """Return one symbol's ``[start, end)`` VRAM extent, or ``None``.

    A linker map carries no symbol sizes, so the end is the next symbol the
    map places above this one -- the same approximation DKR's own
    ``calc_func_checksums.py`` makes when it derives a protected function's
    length to checksum it. The containing input-section record caps the
    result, so the last symbol in an object cannot swallow the next object's
    contribution.
    """

    symbol = ldmap.symbol(name)
    if symbol is None:
        return None
    ordered = ldmap.symbols_sorted()
    addresses = [item.address for item in ordered]
    index = bisect_right(addresses, symbol.address)
    end = addresses[index] if index < len(addresses) else None
    record = ldmap.input_section_containing(symbol.address)
    if record is not None and record.size:
        end = record.end if end is None else min(end, record.end)
    if end is None or end <= symbol.address:
        return None
    return symbol.address, end


@dataclass(frozen=True)
class ChecksumVerdict:
    """One ``FUNCTION=VARIABLE`` pair, checked against the shift."""

    function: str
    variable: str
    function_vram: int | None
    function_rom: int | None
    function_size: int | None
    body_words: int
    body_changed: int
    variable_rom: int | None
    variable_base: int | None
    variable_shifted: int | None
    variable_changed: bool
    status: str
    """``"pass"``, ``"checksum-stale"``, ``"checksum-orphan"``, or
    ``"unresolved"`` -- every one of them in `CHECKSUM_RULES`."""
    basis: str
    """``"inert"`` (neither side changed), ``"tracked"`` (both did), or
    ``"-"``. A pass that does not say which of the two it was is indis-
    tinguishable from a check that never ran."""
    note: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "variable": self.variable,
            "function_vram": self.function_vram,
            "function_rom": self.function_rom,
            "function_size": self.function_size,
            "body_words": self.body_words,
            "body_changed": self.body_changed,
            "variable_rom": self.variable_rom,
            "variable_base": self.variable_base,
            "variable_shifted": self.variable_shifted,
            "variable_changed": self.variable_changed,
            "status": self.status,
            "basis": self.basis,
            "note": self.note,
        }


def _paired(
    base: bytes, shifted: bytes, offset: int, *, insertion: int, delta: int
) -> tuple[int, int] | None:
    """Read one word from both images through the corrected pairing."""

    other = offset + delta if offset >= insertion else offset
    if offset + 4 > len(base) or other + 4 > len(shifted):
        return None
    return (
        struct.unpack_from(">I", base, offset)[0],
        struct.unpack_from(">I", shifted, other)[0],
    )


def checksum_verdicts(
    pairs: Sequence[tuple[str, str]],
    *,
    base_ldmap: LdMap,
    base_image: bytes,
    shifted_image: bytes,
    insertion: int,
    delta: int,
) -> tuple[ChecksumVerdict, ...]:
    """Apply the checksum-consistency rule to every named pair.

    The rule, from S2's reconstruction of the 2021 cursed-audio commit: a
    protected function whose body words changed must have a changed checksum
    word. The inverse is reported too -- a checksum that moved over an
    unchanged body is not a known bug class, but it means the pair's
    coordinates or the map's extent are not what they appear to be, and a
    referee that stays quiet about that is not a referee.
    """

    found: list[ChecksumVerdict] = []
    for function, variable in pairs:
        extent = symbol_extent(base_ldmap, function)
        variable_symbol = base_ldmap.symbol(variable)
        variable_rom = (
            base_ldmap.rom_for_vram(variable_symbol.address)
            if variable_symbol is not None
            else None
        )
        if extent is None or variable_rom is None:
            missing = []
            if extent is None:
                missing.append(f"{function} has no bounded extent in the base map")
            if variable_symbol is None:
                missing.append(f"{variable} is not a symbol the base map places")
            elif variable_rom is None:
                missing.append(f"{variable} has no ROM placement in the base map")
            found.append(
                ChecksumVerdict(
                    function=function,
                    variable=variable,
                    function_vram=extent[0] if extent else None,
                    function_rom=None,
                    function_size=extent[1] - extent[0] if extent else None,
                    body_words=0,
                    body_changed=0,
                    variable_rom=variable_rom,
                    variable_base=None,
                    variable_shifted=None,
                    variable_changed=False,
                    status="unresolved",
                    basis="-",
                    note="; ".join(missing),
                )
            )
            continue

        start, end = extent
        function_rom = base_ldmap.rom_for_vram(start)
        if function_rom is None:
            found.append(
                ChecksumVerdict(
                    function=function,
                    variable=variable,
                    function_vram=start,
                    function_rom=None,
                    function_size=end - start,
                    body_words=0,
                    body_changed=0,
                    variable_rom=variable_rom,
                    variable_base=None,
                    variable_shifted=None,
                    variable_changed=False,
                    status="unresolved",
                    basis="-",
                    note=f"{function} has no ROM placement in the base map",
                )
            )
            continue

        body_words = 0
        body_changed = 0
        for offset in range(function_rom, function_rom + (end - start), 4):
            words = _paired(
                base_image, shifted_image, offset, insertion=insertion, delta=delta
            )
            if words is None:
                break
            body_words += 1
            if words[0] != words[1]:
                body_changed += 1

        variable_words = _paired(
            base_image, shifted_image, variable_rom, insertion=insertion, delta=delta
        )
        if variable_words is None:
            found.append(
                ChecksumVerdict(
                    function=function,
                    variable=variable,
                    function_vram=start,
                    function_rom=function_rom,
                    function_size=end - start,
                    body_words=body_words,
                    body_changed=body_changed,
                    variable_rom=variable_rom,
                    variable_base=None,
                    variable_shifted=None,
                    variable_changed=False,
                    status="unresolved",
                    basis="-",
                    note=f"{variable} lies past the end of one of the images",
                )
            )
            continue

        variable_base, variable_shifted = variable_words
        variable_changed = variable_base != variable_shifted
        if body_changed and not variable_changed:
            status, basis = "checksum-stale", "-"
        elif variable_changed and not body_changed:
            status, basis = "checksum-orphan", "-"
        else:
            status = "pass"
            basis = "tracked" if body_changed else "inert"
        found.append(
            ChecksumVerdict(
                function=function,
                variable=variable,
                function_vram=start,
                function_rom=function_rom,
                function_size=end - start,
                body_words=body_words,
                body_changed=body_changed,
                variable_rom=variable_rom,
                variable_base=variable_base,
                variable_shifted=variable_shifted,
                variable_changed=variable_changed,
                status=status,
                basis=basis,
                note=None,
            )
        )
    return tuple(found)


# ---------------------------------------------------------------------------
# The merge: static confidence x empirical movement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StaleVerdict:
    """One statically-ranked word, judged by whether the shift moved it."""

    rom: int
    vram: int
    value: int
    shifted_value: int
    region: str
    residence: str
    resident_symbol: str | None
    resident_offset: int | None
    target_symbol: str | None
    target_offset: int | None
    tier: str
    rule: str
    verdict: str
    """``"moved"``, ``"unmoved"``, or ``"changed-other"``."""
    outcome: str
    """What that verdict means at this tier: `TRACKS`, one of `MERGE_TIERS`'
    values, or `CHANGED_OTHER`."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rom": self.rom,
            "vram": self.vram,
            "value": self.value,
            "shifted_value": self.shifted_value,
            "region": self.region,
            "residence": self.residence,
            "resident_symbol": self.resident_symbol,
            "resident_offset": self.resident_offset,
            "target_symbol": self.target_symbol,
            "target_offset": self.target_offset,
            "tier": self.tier,
            "rule": self.rule,
            "verdict": self.verdict,
            "outcome": self.outcome,
        }


_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}


def reconcile(
    hits: Sequence[Hit],
    *,
    base_image: bytes,
    shifted_image: bytes,
    insertion: int,
    delta: int,
    moved_range: tuple[int, int],
) -> tuple[StaleVerdict, ...]:
    """Judge every static hit inside the moved range against the relink.

    Only hits whose *value* falls in ``[anchor, window_hi)`` are judged: a
    word pointing below the insertion is not supposed to move, so asking
    whether it did would manufacture a finding out of a correct reference.
    """

    found: list[StaleVerdict] = []
    for hit in hits:
        if not moved_range[0] <= hit.value < moved_range[1]:
            continue
        words = _paired(
            base_image, shifted_image, hit.rom, insertion=insertion, delta=delta
        )
        if words is None:
            continue
        old, new = words
        if old == new:
            verdict, outcome = "unmoved", MERGE_TIERS.get(hit.tier, "noise")
        elif new - old == delta:
            verdict, outcome = "moved", TRACKS
        else:
            verdict, outcome = CHANGED_OTHER, CHANGED_OTHER
        found.append(
            StaleVerdict(
                rom=hit.rom,
                vram=hit.vram,
                value=hit.value,
                shifted_value=new,
                region=hit.region,
                residence=hit.residence,
                resident_symbol=hit.resident_symbol,
                resident_offset=hit.resident_offset,
                target_symbol=hit.target_symbol,
                target_offset=hit.target_offset,
                tier=hit.tier,
                rule=hit.rule,
                verdict=verdict,
                outcome=outcome,
            )
        )
    return tuple(found)


# ---------------------------------------------------------------------------
# WB-143: the symbol-side census
# ---------------------------------------------------------------------------

#: A symbol naming an address the shift moved that did not move with it.
SYMBOL_STALE = "symbol-stale"
#: An absolute symbol that overrode an object's own definition of the same
#: name. Spelled the same as :data:`decomp_workbench.pins.SHADOWING_PIN`, on
#: purpose: the static audit and the rehearsal find the same defect from two
#: directions and a plan that merges them must not have to translate.
SHADOWING_PIN = "shadowing-pin"


@dataclass(frozen=True)
class SymbolRule:
    """One published reason a symbol-side finding is classed where it is."""

    name: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence}


#: The symbol-side rule table, shipped inside every report that carries a
#: census. Two classes, tried in this order: a shadowing pin is a stale
#: symbol with a *known* remediation, so naming it as one rather than folding
#: it into the generic count is what lets `shift plan` rank it as a free win.
SYMBOL_RULES: tuple[SymbolRule, ...] = (
    SymbolRule(
        SHADOWING_PIN,
        "an absolute (SHN_ABS) symbol carrying a non-zero st_size: GNU ld "
        "let a linker-script assignment override an object's definition of "
        "the same name, silently, and kept the overridden definition's size "
        "and type on the surviving symbol. The object still defines it, so "
        "deleting the assignment is byte-identical at the current layout -- "
        "proved by ablation on pilotwings64's ten, which rebuilt to the same "
        "sha1",
    ),
    SymbolRule(
        SYMBOL_STALE,
        "a symbol naming an address inside the range this shift moved, which "
        "did not move by the delta. Every reference resolved through it now "
        "points at whatever the relink put in its place",
    ),
)


@dataclass(frozen=True)
class SymbolFinding:
    """One symbol the shift left behind, with the evidence it was judged on."""

    name: str
    value: int
    shifted_value: int
    kind: str
    binding: str
    size: int
    absolute: bool
    symbol_section: str | None
    """The section the ELF says owns this symbol, or ``None`` for an absolute
    one -- which is the point: an absolute symbol is owned by nothing and
    therefore follows nothing."""

    owning_section: str | None
    """The section whose extent actually contains `value`. The evidence a
    remediation is built from: a pin resolving into ``.app_bss`` needs a home
    in ``.app_bss``, and one resolving into nothing at all is residue."""

    classification: str

    @property
    def movement(self) -> int:
        return self.shifted_value - self.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "shifted_value": self.shifted_value,
            # Spelled `delta` rather than `movement`: the movement-audit rows
            # above already use that key for the same quantity, and `movement`
            # is taken by the anomaly list itself.
            "delta": self.movement,
            "kind": self.kind,
            "binding": self.binding,
            "size": self.size,
            "absolute": self.absolute,
            "symbol_section": self.symbol_section,
            "owning_section": self.owning_section,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class SymbolCensus:
    """Every shared symbol above the insertion, judged against the relink.

    **The instrument S6 measured the need for.** ``shift rehearse``'s
    ``stale_confirmed`` is the *data-side* answer: it can only convict a word
    the static scan read, and the scan does not read text regions, because a
    MIPS address is split across a ``lui``/``%lo`` pair that no single word
    carries (see :meth:`Rehearsal.stale_unattributed` and S6 §4.5). On
    pilotwings64 that hid seven RSP-microcode pins, a kernel bss pin carrying
    ten relocations, and the boot stack pointer -- every one of them consumed
    only from code. The data side convicted exactly one word; the symbol side
    finds thirteen more plus ten shadowing pins, and neither subsumes the
    other.

    This is the symbol-side answer, and it needs no scan at all: read both
    ELFs' symbol tables and require that every shared symbol naming an
    address the shift moved moved with it.
    """

    base_path: str | None
    shifted_path: str | None
    delta: int
    range_lo: int
    """The insertion VRAM. Exclusive -- see `symbol_census`."""

    range_hi: int
    """The movable window's high bound. Inclusive -- see `symbol_census`."""

    checked: int
    moved: int
    findings: tuple[SymbolFinding, ...]
    boundary_symbols: int
    """Shared symbols sitting exactly *on* the insertion address, excluded
    from the census and counted here rather than absorbed. Both answers are
    correct at that one address at once and no rule can tell them apart --
    see `symbol_census`."""

    only_in_base: int
    only_in_shifted: int

    def by_classification(self, classification: str) -> tuple[SymbolFinding, ...]:
        return tuple(
            item for item in self.findings if item.classification == classification
        )

    @property
    def symbol_stale(self) -> int:
        return len(self.by_classification(SYMBOL_STALE))

    @property
    def shadowing_pins(self) -> int:
        return len(self.by_classification(SHADOWING_PIN))

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        shown = self.findings[: max(0, limit)]
        return {
            "base_elf": self.base_path,
            "shifted_elf": self.shifted_path,
            "symbol_range_lo": self.range_lo,
            "symbol_range_hi": self.range_hi,
            "symbol_checked": self.checked,
            "symbol_moved": self.moved,
            "symbol_stale": self.symbol_stale,
            "shadowing_pins": self.shadowing_pins,
            "symbol_boundary": self.boundary_symbols,
            "symbol_only_in_base": self.only_in_base,
            "symbol_only_in_shifted": self.only_in_shifted,
            "symbol_findings_shown": len(shown),
            "symbol_findings": [item.as_dict() for item in shown],
            "symbol_rules": [item.as_dict() for item in SYMBOL_RULES],
        }


def symbol_census(
    base: ElfSymbols,
    shifted: ElfSymbols,
    *,
    delta: int,
    anchor_vram: int,
    window_hi: int,
) -> SymbolCensus:
    """Require every symbol above the insertion to move by `delta`.

    The judged range is ``(anchor_vram, window_hi]`` -- open at the bottom
    and closed at the top, and both ends are measured rather than chosen for
    symmetry.

    *Open at the bottom*, because the insertion address is the one address at
    which both answers are right. pilotwings64's pad goes in at the end of
    ``.entry``: ``entry_TEXT_END``, ``entry_DATA_START`` and four more sit at
    ``0x802000a0`` and correctly do **not** move, because ``.entry``'s
    contents did not grow -- while ``func_802000A0``, the first byte of
    ``.kernel``, sits at the same address and correctly does. Nothing about a
    symbol says which side of the pad it describes, so the address itself is
    excluded and the symbols on it are counted in `boundary_symbols` rather
    than reported as eight findings that are not findings.

    *Closed at the top*, because ``window_hi`` is one past the last movable
    byte and the symbol that names that boundary moves with it:
    pilotwings64's ``app_BSS_END`` is at ``0x803805e0`` and moves, and so
    does ``filetable_DATA_START`` beside it. The pin ``D_803805E0 =
    0x803805E0`` -- which S6 identified as the heap base read by
    ``src/kernel/memory.c`` -- sits on the same address and does not. A
    half-open top bound would drop exactly that finding.
    """

    shared = base.names() & shifted.names()
    checked = 0
    moved = 0
    boundary = 0
    findings: list[SymbolFinding] = []
    for name in sorted(shared):
        placed = base.symbol(name)
        relinked = shifted.symbol(name)
        assert placed is not None and relinked is not None  # from shared names
        if placed.value == anchor_vram:
            boundary += 1
            continue
        if not anchor_vram < placed.value <= window_hi:
            continue
        checked += 1
        if relinked.value - placed.value == delta:
            moved += 1
            continue
        owner = base.section_at(placed.value)
        findings.append(
            SymbolFinding(
                name=name,
                value=placed.value,
                shifted_value=relinked.value,
                kind=placed.kind,
                binding=placed.binding,
                size=placed.size,
                absolute=placed.is_absolute,
                symbol_section=placed.section,
                owning_section=owner.name if owner is not None else None,
                classification=(
                    SHADOWING_PIN if placed.shadows_definition else SYMBOL_STALE
                ),
            )
        )
    order = {item.name: index for index, item in enumerate(SYMBOL_RULES)}
    findings.sort(
        key=lambda item: (order.get(item.classification, len(order)), item.value)
    )
    return SymbolCensus(
        base_path=base.path,
        shifted_path=shifted.path,
        delta=delta,
        range_lo=anchor_vram,
        range_hi=window_hi,
        checked=checked,
        moved=moved,
        findings=tuple(findings),
        boundary_symbols=boundary,
        only_in_base=len(base.names() - shifted.names()),
        only_in_shifted=len(shifted.names() - base.names()),
    )


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rehearsal:
    """One base/shifted pair, fully explained."""

    base_map_path: str | None
    base_image_path: str | None
    shifted_map_path: str | None
    shifted_image_path: str | None
    delta: int
    base_image_bytes: int
    shifted_image_bytes: int
    anchor: Anchor
    window: MovableWindow
    regions: tuple[Region, ...]
    generated: tuple[GeneratedSpec, ...]
    movement: MovementAudit
    census: WordCensus
    reconciliation: tuple[StaleVerdict, ...]
    checksums: tuple[ChecksumVerdict, ...]
    symbols: SymbolCensus | None = None
    """WB-143's symbol-side census, when the caller handed in both ELFs.
    ``None`` when it did not -- and reported as ``symbol_census=off`` rather
    than as zero findings, because "nobody asked" and "nothing found" are the
    two answers this command exists to keep apart."""

    @property
    def movement_anomalies(self) -> tuple[SymbolMovement, ...]:
        return self.movement.anomalies

    @property
    def unexplained_changed(self) -> int:
        """The gate: changed words no class accounts for."""

        return self.census.unexplained_total

    @property
    def tier_verdicts(self) -> dict[str, dict[str, int]]:
        """The tier x movement matrix, with every cell present."""

        matrix = {
            tier: {"moved": 0, "unmoved": 0, CHANGED_OTHER: 0} for tier in MERGE_TIERS
        }
        for item in self.reconciliation:
            row = matrix.setdefault(
                item.tier, {"moved": 0, "unmoved": 0, CHANGED_OTHER: 0}
            )
            row[item.verdict] = row.get(item.verdict, 0) + 1
        return matrix

    def _outcome_total(self, outcome: str) -> int:
        return sum(1 for item in self.reconciliation if item.outcome == outcome)

    @property
    def stale_confirmed(self) -> int:
        """The headline: high-confidence address words the shift left behind."""

        return self._outcome_total("stale-confirmed")

    @property
    def stale_review(self) -> int:
        return self._outcome_total("stale-review")

    @property
    def stale_noise(self) -> int:
        return self._outcome_total("noise")

    @property
    def reconciled_total(self) -> int:
        return len(self.reconciliation)

    @property
    def moved_total(self) -> int:
        return sum(1 for item in self.reconciliation if item.verdict == "moved")

    @property
    def unmoved_total(self) -> int:
        return sum(1 for item in self.reconciliation if item.verdict == "unmoved")

    @property
    def changed_other_total(self) -> int:
        return sum(1 for item in self.reconciliation if item.verdict == CHANGED_OTHER)

    @property
    def stale_unattributed(self) -> int:
        """Stale candidates the static scan never saw.

        The census walks every word in the image; the audit scans only its
        data, blob and header regions. A stale candidate in a text region is
        therefore counted by one and not the other, and the shortfall is
        printed rather than quietly absorbed. S2 measured it at zero on DKR.
        """

        return self.census.stale_total - self.unmoved_total

    @property
    def checksum_pass(self) -> int:
        return sum(1 for item in self.checksums if item.status == "pass")

    @property
    def checksum_findings(self) -> int:
        return sum(1 for item in self.checksums if item.status != "pass")

    @property
    def symbol_stale(self) -> int:
        """The symbol-side headline. ``0`` when no census ran -- and
        ``symbol_census`` says which zero it is."""

        return 0 if self.symbols is None else self.symbols.symbol_stale

    @property
    def shadowing_pins(self) -> int:
        return 0 if self.symbols is None else self.symbols.shadowing_pins

    @property
    def findings(self) -> int:
        return (
            self.unexplained_changed
            + self.stale_confirmed
            + len(self.movement_anomalies)
            + self.checksum_findings
            + self.symbol_stale
            + self.shadowing_pins
        )

    def ranked_stale(self) -> tuple[StaleVerdict, ...]:
        """Every unmoved word, most confident first, then by ROM offset."""

        return tuple(
            sorted(
                (item for item in self.reconciliation if item.verdict == "unmoved"),
                key=lambda item: (_TIER_ORDER.get(item.tier, 3), item.rom),
            )
        )

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        cap = max(0, limit)
        stale = self.ranked_stale()[:cap]
        unexplained = self.census.unexplained[:cap]
        anomalies = self.movement_anomalies[:cap]
        payload: dict[str, Any] = {
            "schema": SHIFT_REHEARSE_SCHEMA,
            "mode": "analyze",
            "base_map": self.base_map_path,
            "base_image": self.base_image_path,
            "shifted_map": self.shifted_map_path,
            "shifted_image": self.shifted_image_path,
            "delta": self.delta,
            "base_image_bytes": self.base_image_bytes,
            "shifted_image_bytes": self.shifted_image_bytes,
            "region_count": len(self.regions),
            "regions": [item.as_dict() for item in self.regions],
            "generated_spans": [
                {"start": item.start, "end": item.end, "label": item.label}
                for item in self.generated
            ],
            "total_words": self.census.total_words,
            "differing_total": self.census.differing_total,
            "classes": dict(self.census.counts),
            "unexplained_changed": self.unexplained_changed,
            "unexplained_shown": len(unexplained),
            "unexplained": [item.as_dict() for item in unexplained],
            "stale_total": self.census.stale_total,
            "stale_confirmed": self.stale_confirmed,
            "stale_review": self.stale_review,
            "stale_noise": self.stale_noise,
            "stale_unattributed": self.stale_unattributed,
            "stale_shown": len(stale),
            "stale": [item.as_dict() for item in stale],
            "merge_tiers": dict(MERGE_TIERS),
            "tier_verdicts": self.tier_verdicts,
            "reconciled_total": self.reconciled_total,
            "moved_total": self.moved_total,
            "unmoved_total": self.unmoved_total,
            "changed_other_total": self.changed_other_total,
            "movement_shared": len(self.movement.movements),
            "movement_anomaly_total": len(self.movement_anomalies),
            "movement_anomaly_shown": len(anomalies),
            "movement": [item.as_dict() for item in anomalies],
            "movement_only_in_base": len(self.movement.only_in_base),
            "movement_only_in_shifted": len(self.movement.only_in_shifted),
            "checksum_total": len(self.checksums),
            "checksum_pass": self.checksum_pass,
            "checksum_findings": self.checksum_findings,
            "checksums": [item.as_dict() for item in self.checksums],
            "checksum_rules": [item.as_dict() for item in CHECKSUM_RULES],
            "findings": self.findings,
            "limit": limit,
        }
        payload.update(self.anchor.as_dict())
        payload.update(self.window.as_dict())
        payload["symbol_census"] = self.symbols is not None
        if self.symbols is not None:
            payload.update(self.symbols.as_dict(limit=cap))
        return payload


def build_rehearsal(
    *,
    base_ldmap: LdMap,
    base_image: bytes,
    shifted_ldmap: LdMap,
    shifted_image: bytes,
    delta: int,
    anchor: str | None = None,
    blobs: Iterable[str] = (),
    header_sections: Iterable[str] = (".header",),
    crc_words: Iterable[int] = (),
    checksum_pairs: Sequence[tuple[str, str]] = (),
    base_elf: ElfSymbols | None = None,
    shifted_elf: ElfSymbols | None = None,
    model: RangeModel | None = None,
    detail_cap: int = 200,
    base_map_path: str | None = None,
    base_image_path: str | None = None,
    shifted_map_path: str | None = None,
    shifted_image_path: str | None = None,
) -> Rehearsal:
    """Explain one relink: movement, census, reconciliation, checksums.

    The pipeline is fixed and each step feeds the next. The region table and
    the movable window come from the *base* map (`shift_audit`'s derivation,
    reused rather than re-derived, so the two commands cannot disagree about
    what a region is). The anchor comes from both maps. The census pairs the
    two images through that anchor. The reconciliation judges the static
    scan's own hits against the same pairing. Nothing here decides whether a
    project is correct; it decides what changed and why.
    """

    # WB QA: checked here, before anchor derivation, not left for
    # `build_word_census` to find later. A wrong delta usually means no
    # symbol moved by it, so an auto-derived anchor fails first and vaguer
    # ("no object-backed symbol ... moved by the declared delta") -- the
    # same fact `check_image_delta` names with the actual arithmetic, and
    # it must win whether or not `--anchor` was given.
    check_image_delta(base_image, shifted_image, delta=delta)

    range_model = model if model is not None else default_pin_model()
    regions = build_region_table(
        base_ldmap,
        image_size=len(base_image),
        blobs=blobs,
        header_sections=header_sections,
    )
    window = movable_window(regions)
    found_anchor = derive_anchor(
        base_ldmap,
        shifted_ldmap,
        delta=delta,
        window_lo=window.lo,
        window_hi=window.hi,
        symbol=anchor,
    )
    movement = audit_symbol_movement(
        base_ldmap, shifted_ldmap, allowed_deltas=(0, delta)
    )

    specs = tuple(
        RegionSpec(start=item.rom, end=item.rom + item.size, kind=item.kind)
        for item in regions
        if item.rom is not None and item.kind != "bss"
    )
    generated: list[GeneratedSpec] = [
        GeneratedSpec(start=offset, end=offset + 4, label="crc-header")
        for offset in sorted(set(crc_words))
    ]
    for _, variable in checksum_pairs:
        symbol = base_ldmap.symbol(variable)
        placement = base_ldmap.rom_for_vram(symbol.address) if symbol else None
        if placement is not None:
            generated.append(
                GeneratedSpec(start=placement, end=placement + 4, label="checksum-gen")
            )

    census = build_word_census(
        base_image,
        shifted_image,
        insertion_offset=found_anchor.rom,
        delta=delta,
        regions=specs,
        generated=tuple(generated),
        moved_range=(found_anchor.vram, window.hi),
        range_model=range_model,
        detail_cap=detail_cap,
    )
    hits = scan_regions(
        base_image, regions, window=window, ldmap=base_ldmap, model=range_model
    )
    reconciliation = reconcile(
        hits,
        base_image=base_image,
        shifted_image=shifted_image,
        insertion=found_anchor.rom,
        delta=delta,
        moved_range=(found_anchor.vram, window.hi),
    )
    checksums = checksum_verdicts(
        checksum_pairs,
        base_ldmap=base_ldmap,
        base_image=base_image,
        shifted_image=shifted_image,
        insertion=found_anchor.rom,
        delta=delta,
    )
    # WB-143: the symbol side, only when the caller handed in both ELFs. One
    # ELF alone cannot answer it -- movement is a two-link question -- and
    # refusing here rather than half-running keeps `symbol_census=false` from
    # ever meaning "you gave me one".
    if (base_elf is None) != (shifted_elf is None):
        raise ValueError(
            "--base-elf and --shifted-elf go together: whether a symbol moved "
            "is a question about two links, and one of them cannot answer it"
        )
    symbols = (
        symbol_census(
            base_elf,
            shifted_elf,
            delta=delta,
            anchor_vram=found_anchor.vram,
            window_hi=window.hi,
        )
        if base_elf is not None and shifted_elf is not None
        else None
    )
    return Rehearsal(
        base_map_path=base_map_path,
        base_image_path=base_image_path,
        shifted_map_path=shifted_map_path,
        shifted_image_path=shifted_image_path,
        delta=delta,
        base_image_bytes=len(base_image),
        shifted_image_bytes=len(shifted_image),
        anchor=found_anchor,
        window=window,
        regions=regions,
        generated=tuple(sorted(generated, key=lambda item: item.start)),
        movement=movement,
        census=census,
        reconciliation=reconciliation,
        checksums=checksums,
        symbols=symbols,
    )


# ---------------------------------------------------------------------------
# Cross-delta consistency
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Disagreement:
    """One number two deltas did not agree on."""

    name: str
    values: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "values": dict(self.values)}


#: The scalars every delta must agree on, beyond the per-class counts. A
#: shift's class census is a property of the *layout*, not of how far it
#: moved: S0 measured byte-identical counts at 0x10 and 0x40, and a delta that
#: disagrees is evidence that one of the builds is not the controlled
#: experiment it claims to be -- or that a coincidence at one delta hid a bug
#: the other one exposes (S2's class 3).
CONSISTENCY_KEYS: tuple[str, ...] = (
    "differing_total",
    "unexplained_changed",
    "stale_total",
    "stale_confirmed",
    "stale_review",
    "stale_noise",
    "movement_anomaly_total",
    "checksum_findings",
    "anchor_vram",
)


def cross_delta_disagreements(
    analyses: Sequence[Rehearsal],
) -> tuple[Disagreement, ...]:
    """Report every count two or more deltas did not agree on."""

    if len(analyses) < 2:
        return ()
    labels = [f"0x{item.delta:x}" for item in analyses]
    rows: dict[str, dict[str, int]] = {}
    for name in sorted({key for item in analyses for key in item.census.counts}):
        rows[name] = {
            label: item.census.counts.get(name, 0)
            for label, item in zip(labels, analyses, strict=True)
        }
    scalars: dict[str, Callable[[Rehearsal], int]] = {
        "differing_total": lambda item: item.census.differing_total,
        "unexplained_changed": lambda item: item.unexplained_changed,
        "stale_total": lambda item: item.census.stale_total,
        "stale_confirmed": lambda item: item.stale_confirmed,
        "stale_review": lambda item: item.stale_review,
        "stale_noise": lambda item: item.stale_noise,
        "movement_anomaly_total": lambda item: len(item.movement_anomalies),
        "checksum_findings": lambda item: item.checksum_findings,
        "anchor_vram": lambda item: item.anchor.vram,
    }
    for name in CONSISTENCY_KEYS:
        rows[name] = {
            label: scalars[name](item)
            for label, item in zip(labels, analyses, strict=True)
        }
    return tuple(
        Disagreement(name=name, values=values)
        for name, values in rows.items()
        if len(set(values.values())) > 1
    )


# ---------------------------------------------------------------------------
# Padded linker scripts and the relink driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaddedScript:
    """One linker script with ``. += DELTA;`` inserted after an anchor line."""

    text: str
    line: int
    """The 0-based index of the inserted line in the rendered text."""
    anchor_line: str

    def as_dict(self) -> dict[str, Any]:
        return {"line": self.line, "anchor_line": self.anchor_line}


def pad_ld_script(text: str, *, anchor_object: str, delta: int) -> PaddedScript:
    """Insert ``. += DELTA;`` directly after the anchor object's line.

    S0's rehearsal primitive, done once: relink the *same objects* against a
    script with one line added, and everything after that line moves by
    exactly delta. The insertion is textual on purpose -- a linker script is
    not a grammar this repository wants to own, and one line after one
    matched line is the whole edit.

    Exactly one line must mention `anchor_object`. Zero is a typo and two is
    ambiguous (a cascade script lists the same object once per input section),
    and both raise rather than pick: an anchor in the wrong place produces a
    build that looks fine and a census that is nonsense.
    """

    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if anchor_object in line]
    if not matches:
        raise ValueError(
            f"no line of the linker script mentions the anchor object "
            f"{anchor_object!r}; the pad has nowhere to go"
        )
    if len(matches) > 1:
        numbers = ", ".join(str(index + 1) for index in matches)
        raise ValueError(
            f"the anchor object {anchor_object!r} matches {len(matches)} lines "
            f"({numbers}); name one that appears exactly once, because a pad "
            "in the wrong input section moves the wrong half of the image"
        )
    index = matches[0]
    anchor_line = lines[index]
    indent = anchor_line[: len(anchor_line) - len(anchor_line.lstrip())]
    padded = [*lines[: index + 1], f"{indent}. += 0x{delta:x};", *lines[index + 1 :]]
    return PaddedScript(
        text="\n".join(padded) + "\n", line=index + 1, anchor_line=anchor_line.strip()
    )


@dataclass(frozen=True)
class RunRecord:
    """One invocation of the caller's relink wrapper."""

    label: str
    delta: int
    ld_script: str
    out_dir: str
    image: str
    map: str
    exit_status: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "delta": self.delta,
            "ld_script": self.ld_script,
            "out_dir": self.out_dir,
            "image": self.image,
            "map": self.map,
            "exit_status": self.exit_status,
        }


#: How the wrapper is called. Documented here and in ``--help`` because it is
#: the one part of this command a project has to implement itself.
WRAPPER_CONTRACT = (
    "the wrapper is invoked as `SCRIPT LDSCRIPT_PATH OUT_DIR` and must leave "
    "the linked image and its `ld -Map` file in OUT_DIR under the names given "
    "by --image-name and --map-name. It should relink only -- the objects are "
    "the controlled constant of this experiment, and rebuilding them changes "
    "the question."
)


def _last_line(completed: subprocess.CompletedProcess[str]) -> str:
    """The wrapper's own last word, so a build failure reads as one.

    A relink that died inside `ld` says why on its last line; repeating the
    whole stream would bury it, and repeating none of it would make this
    command look like the thing that broke.
    """

    text = (completed.stderr or completed.stdout or "").strip()
    return text.splitlines()[-1] if text else "no diagnostic"


def _run_wrapper(
    wrapper: str, ld_script: Path, out_dir: Path, *, label: str
) -> subprocess.CompletedProcess[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return subprocess.run(
            [wrapper, str(ld_script), str(out_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise ValueError(f"cannot run the wrapper for {label}: {error}") from None


@dataclass(frozen=True)
class Orchestration:
    """One base build, N shifted builds, and the comparison between them."""

    wrapper: str
    ld_script: str
    anchor_object: str
    workdir: str
    image_name: str
    map_name: str
    runs: tuple[RunRecord, ...]
    analyses: tuple[Rehearsal, ...]
    disagreements: tuple[Disagreement, ...]

    @property
    def findings(self) -> int:
        return sum(item.findings for item in self.analyses) + len(self.disagreements)

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        return {
            "schema": SHIFT_REHEARSE_SCHEMA,
            "mode": "orchestrate",
            "wrapper": self.wrapper,
            "ld_script": self.ld_script,
            "anchor_object": self.anchor_object,
            "workdir": self.workdir,
            "image_name": self.image_name,
            "map_name": self.map_name,
            "deltas": [f"0x{item.delta:x}" for item in self.analyses],
            "runs": [item.as_dict() for item in self.runs],
            "analyses": [item.as_dict(limit=limit) for item in self.analyses],
            "classes_agree": not self.disagreements,
            "disagreements": [item.as_dict() for item in self.disagreements],
            "findings": self.findings,
            "limit": limit,
        }


def orchestrate(
    *,
    wrapper: str,
    ld_script: Path,
    anchor_object: str,
    deltas: Sequence[int],
    workdir: Path,
    image_name: str,
    map_name: str,
    analyze: Callable[..., Rehearsal],
) -> Orchestration:
    """Generate, relink, analyze, and compare -- in that order.

    Every padded script is generated **before** any build runs, so an anchor
    that matches nothing or matches twice costs nothing but a message. The
    base build uses the caller's own script unmodified: the experiment is a
    one-line difference, and copying the base script would be one more thing
    that could differ.
    """

    text = ld_script.read_text(encoding="utf-8")
    padded = {
        delta: pad_ld_script(text, anchor_object=anchor_object, delta=delta)
        for delta in deltas
    }

    workdir.mkdir(parents=True, exist_ok=True)
    runs: list[RunRecord] = []

    def build(label: str, delta: int, script: Path) -> RunRecord:
        out_dir = workdir / ("base" if delta == 0 else f"delta-{label}")
        completed = _run_wrapper(wrapper, script, out_dir, label=label)
        if completed.returncode != 0:
            raise ValueError(
                f"the wrapper failed for {label} with exit "
                f"{completed.returncode}: {_last_line(completed)}"
            )
        image, mapping = out_dir / image_name, out_dir / map_name
        for produced in (image, mapping):
            if not produced.is_file():
                raise ValueError(
                    f"the wrapper for {label} left no {produced.name} in "
                    f"{out_dir}: {WRAPPER_CONTRACT}"
                )
        return RunRecord(
            label=label,
            delta=delta,
            ld_script=str(script),
            out_dir=str(out_dir),
            image=str(image),
            map=str(mapping),
            exit_status=completed.returncode,
        )

    runs.append(build("base", 0, ld_script))
    for delta in deltas:
        script = workdir / f"shifted-0x{delta:x}.ld"
        script.write_text(padded[delta].text, encoding="utf-8")
        runs.append(build(f"0x{delta:x}", delta, script))

    base = runs[0]
    analyses = tuple(
        analyze(
            base_map=Path(base.map),
            base_image=Path(base.image),
            shifted_map=Path(run.map),
            shifted_image=Path(run.image),
            delta=run.delta,
        )
        for run in runs[1:]
    )
    return Orchestration(
        wrapper=wrapper,
        ld_script=str(ld_script),
        anchor_object=anchor_object,
        workdir=str(workdir),
        image_name=image_name,
        map_name=map_name,
        runs=tuple(runs),
        analyses=analyses,
        disagreements=cross_delta_disagreements(analyses),
    )


# ---------------------------------------------------------------------------
# Human rendering
# ---------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render one column-aligned table, the same shape `shift audit` prints.

    An empty table prints its header and then ``none`` -- a bare header row
    reads as a table that failed to render, not one with nothing in it. WB
    QA: a healthy run's "movement anomalies" and "unexplained" tables are
    empty by construction, and a page of bare headers with no data under any
    of them was one of the ways a clean report read as noisy.
    """

    if not rows:
        return [" ".join(header), "none"]
    widths = [
        max(len(header[column]), *(len(row[column]) for row in rows))
        for column in range(len(header))
    ]
    lines = [
        "  ".join(
            header[column].ljust(widths[column]) for column in range(len(header))
        ).rstrip()
    ]
    for row in rows:
        lines.append(
            "  ".join(
                row[column].ljust(widths[column]) for column in range(len(row))
            ).rstrip()
        )
    return lines


def _named(symbol: str | None, offset: int | None) -> str:
    if symbol is None:
        return "-"
    return symbol if not offset else f"{symbol}+0x{offset:x}"


def _symbol_census_lines(found: SymbolCensus | None, *, limit: int) -> list[str]:
    """Render WB-143's symbol-side census, or say why there is none."""

    if found is None:
        return [
            "",
            "symbol_census=off -- pass --base-elf and --shifted-elf to run it. "
            "The data-side referee above can only judge words the static scan "
            "read, and it does not read text: a reference consumed only from "
            "a lui/%lo pair is invisible to it. The symbol census answers "
            "that half, and on pilotwings64 it found 13x more blockers than "
            "the data side did.",
        ]
    lines = [
        "",
        f"symbol_census=on  symbol_checked={found.checked:,}  "
        f"symbol_moved={found.moved:,}  symbol_stale={found.symbol_stale:,}  "
        f"shadowing_pins={found.shadowing_pins:,}",
        f"symbol_range=(0x{found.range_lo:08x}, 0x{found.range_hi:08x}]  "
        f"symbol_boundary={found.boundary_symbols:,}  "
        f"symbol_only_in_base={found.only_in_base:,}  "
        f"symbol_only_in_shifted={found.only_in_shifted:,}",
        "",
        f"symbol findings ({min(len(found.findings), max(0, limit))} of "
        f"{len(found.findings):,}, --limit)",
    ]
    lines.extend(
        _table(
            (
                "name",
                "value",
                "shifted",
                "class",
                "kind",
                "size",
                "owning_section",
            ),
            [
                (
                    item.name,
                    f"0x{item.value:08x}",
                    f"0x{item.shifted_value:08x}",
                    item.classification,
                    item.kind,
                    f"{item.size:,}",
                    item.owning_section or "-",
                )
                for item in found.findings[: max(0, limit)]
            ],
        )
    )
    lines.append("")
    for rule in SYMBOL_RULES:
        lines.append(f"  {rule.name}: {rule.evidence}")
    return lines


def rehearse_lines(found: Rehearsal, *, limit: int) -> list[str]:
    """Render the human report: the same numbers `as_dict` carries."""

    anchor, window = found.anchor, found.window
    lines = [
        f"shift rehearse  base={found.base_map_path or '-'}  "
        f"shifted={found.shifted_map_path or '-'}  delta=0x{found.delta:x}",
        "",
        f"unexplained_changed={found.unexplained_changed:,}  "
        f"stale_confirmed={found.stale_confirmed:,}  "
        + (
            ""
            if found.symbols is None
            else f"symbol_stale={found.symbol_stale:,}  "
            f"shadowing_pins={found.shadowing_pins:,}  "
        )
        + f"findings={found.findings:,}",
        "",
        f"anchor_vram=0x{anchor.vram:08x}  anchor_rom=0x{anchor.rom:06x}  "
        f"anchor_source={anchor.source}  anchor_symbol={anchor.symbol or '-'}  "
        f"anchor_highest_unmoved="
        + (
            "-" if anchor.highest_unmoved is None else f"0x{anchor.highest_unmoved:08x}"
        ),
        f"window_lo=0x{window.lo:08x}  window_hi=0x{window.hi:08x}  "
        f"base_image_bytes={found.base_image_bytes:,}  "
        f"shifted_image_bytes={found.shifted_image_bytes:,}  "
        f"total_words={found.census.total_words:,}",
        "",
        f"movement_shared={len(found.movement.movements):,}  "
        f"movement_anomaly_total={len(found.movement_anomalies):,}  "
        f"movement_only_in_base={len(found.movement.only_in_base):,}  "
        f"movement_only_in_shifted={len(found.movement.only_in_shifted):,}",
        "",
        f"movement anomalies ({min(len(found.movement_anomalies), max(0, limit))} "
        f"of {len(found.movement_anomalies):,}, --limit)",
    ]
    lines.extend(
        _table(
            ("name", "base_address", "shifted_address", "delta"),
            [
                (
                    item.name,
                    f"0x{item.base_address:08x}",
                    f"0x{item.shifted_address:08x}",
                    f"{item.delta:+#x}",
                )
                for item in found.movement_anomalies[: max(0, limit)]
            ],
        )
    )

    lines.extend(
        ("", f"differing_total={found.census.differing_total:,}", "", "classes")
    )
    lines.extend(
        _table(
            ("label", "count"),
            [(name, f"{count:,}") for name, count in found.census.counts.items()],
        )
    )

    lines.extend(("", "generated_spans"))
    lines.extend(
        _table(
            ("start", "end", "label"),
            [
                (f"0x{item.start:06x}", f"0x{item.end:06x}", item.label)
                for item in found.generated
            ],
        )
    )

    unexplained = found.census.unexplained[: max(0, limit)]
    lines.extend(
        (
            "",
            f"unexplained ({len(unexplained)} of "
            f"{found.unexplained_changed:,}, --limit)",
        )
    )
    lines.extend(
        _table(
            ("offset", "old", "new", "label"),
            [
                (
                    f"0x{item.offset:06x}",
                    f"{item.old:08x}",
                    f"{item.new:08x}",
                    item.label,
                )
                for item in unexplained
            ],
        )
    )

    lines.extend(
        (
            "",
            f"checksum_total={len(found.checksums)}  "
            f"checksum_pass={found.checksum_pass}  "
            f"checksum_findings={found.checksum_findings}",
            "",
            "checksums",
        )
    )
    lines.extend(
        _table(
            (
                "function",
                "variable",
                "status",
                "basis",
                "body_words",
                "body_changed",
            ),
            [
                (
                    item.function,
                    item.variable,
                    item.status,
                    item.basis,
                    f"{item.body_words:,}",
                    f"{item.body_changed:,}",
                )
                for item in found.checksums
            ],
        )
    )
    for item in found.checksums:
        if item.note:
            lines.append(f"  {item.function}: {item.note}")

    lines.extend(
        (
            "",
            f"reconciled_total={found.reconciled_total:,}  "
            f"moved_total={found.moved_total:,}  "
            f"unmoved_total={found.unmoved_total:,}  "
            f"changed_other_total={found.changed_other_total:,}  "
            f"stale_total={found.census.stale_total:,}  "
            f"stale_unattributed={found.stale_unattributed:,}",
            "",
            "tier_verdicts",
        )
    )
    lines.extend(
        _table(
            ("tier", "verdict", "count", "outcome"),
            [
                (
                    tier,
                    verdict,
                    f"{count:,}",
                    TRACKS
                    if verdict == "moved"
                    else CHANGED_OTHER
                    if verdict == CHANGED_OTHER
                    else MERGE_TIERS.get(tier, "noise"),
                )
                for tier, row in found.tier_verdicts.items()
                for verdict, count in row.items()
            ],
        )
    )

    # WB QA: a healthy run -- nothing stale-confirmed -- collapses the stale
    # table to one line instead of printing up to --limit rows that are, at
    # worst, "worth a look and not an alarm" (MERGE_TIERS). A run that found
    # a stale-confirmed word prints the full table unconditionally: that is
    # the finding, and it never hides behind a summary line.
    if found.stale_confirmed == 0 and found.unmoved_total:
        breakdown = (
            "all noise"
            if found.stale_review == 0
            else (
                f"none confirmed ({found.stale_review:,} review, "
                f"{found.stale_noise:,} noise)"
            )
        )
        lines.extend(
            (
                "",
                f"stale candidates: {found.unmoved_total:,}, {breakdown} -- "
                f"pass --limit {found.unmoved_total:,} to list them",
            )
        )
    else:
        stale = found.ranked_stale()[: max(0, limit)]
        lines.extend(("", f"stale ({len(stale)} of {found.unmoved_total:,}, --limit)"))
        lines.extend(
            _table(
                (
                    "rom",
                    "value",
                    "tier",
                    "rule",
                    "outcome",
                    "region",
                    "target_symbol",
                ),
                [
                    (
                        f"0x{item.rom:06x}",
                        f"0x{item.value:08x}",
                        item.tier,
                        item.rule,
                        item.outcome,
                        item.region,
                        _named(item.target_symbol, item.target_offset),
                    )
                    for item in stale
                ],
            )
        )

    lines.extend(_symbol_census_lines(found.symbols, limit=limit))

    lines.extend(
        (
            "",
            "a stale-confirmed word is one the static audit ranked high -- "
            "compiled data landing exactly on a symbol's start -- that this "
            "relink did not move. It is the strongest available evidence for "
            "a hardcoded pointer, and still evidence rather than a verdict: "
            "read the coordinates, not the label.",
            "",
            "checksum-stale means a protected function's body changed and its "
            "checksum word did not. That is the 2021 cursed-audio class: the "
            "post-link patcher's allowlist missed the function, the frozen "
            "value stopped describing the code, and the game's own runtime "
            "self-check failed.",
        )
    )
    return lines


def orchestrate_lines(found: Orchestration, *, limit: int) -> list[str]:
    """Render the driver's own report, with each analysis under it."""

    lines = [
        f"shift rehearse orchestrate  wrapper={found.wrapper}  "
        f"ld_script={found.ld_script}  anchor_object={found.anchor_object}",
        "",
        f"workdir={found.workdir}  image_name={found.image_name}  "
        f"map_name={found.map_name}  findings={found.findings:,}",
        "",
        "runs",
    ]
    lines.extend(
        _table(
            ("label", "delta", "exit_status", "out_dir"),
            [
                (item.label, f"0x{item.delta:x}", str(item.exit_status), item.out_dir)
                for item in found.runs
            ],
        )
    )
    lines.extend(
        (
            "",
            f"classes_agree={'yes' if not found.disagreements else 'no'}  "
            f"disagreements={len(found.disagreements)}",
            "",
            "disagreements",
        )
    )
    lines.extend(
        _table(
            ("name", "values"),
            [
                (
                    item.name,
                    " ".join(
                        f"{label}={count:,}" for label, count in item.values.items()
                    ),
                )
                for item in found.disagreements
            ],
        )
    )
    for analysis in found.analyses:
        lines.extend(("", "-" * 8, ""))
        lines.extend(rehearse_lines(analysis, limit=limit))
    return lines


def parse_checksum_pair(value: str) -> tuple[str, str]:
    """Parse one ``FUNCTION=VARIABLE`` argument."""

    function, separator, variable = value.partition("=")
    if not separator or not function.strip() or not variable.strip():
        raise ValueError(
            f"--checksum-pair {value!r} is not FUNCTION=VARIABLE: name the "
            "protected function and the variable its byte-sum is patched into"
        )
    return function.strip(), variable.strip()


def parse_offsets(value: str) -> tuple[int, ...]:
    """Parse a comma-separated list of ROM offsets or deltas."""

    found: list[int] = []
    for item in value.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            found.append(int(text, 0))
        except ValueError:
            raise ValueError(f"{text!r} is not a number") from None
    return tuple(found)


def parse_mapping(rows: Iterable[str]) -> tuple[tuple[str, str], ...]:
    """Parse every ``FUNCTION=VARIABLE`` argument, in the order given."""

    return tuple(parse_checksum_pair(row) for row in rows)
