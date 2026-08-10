"""The static shiftability inventory: where a project's addresses come from.

``shift audit`` reads one linker map, one linked image, and the project's own
linker-input symbol files, and answers two questions without building
anything. Which of the project's pinned addresses follow the layout and which
are written down (:mod:`decomp_workbench.pins`). And, of the words already in
the image, which ones hold a value shaped like an address into the region an
insertion would move.

**The second question has no honest yes/no answer from one image, and this
module does not pretend otherwise.** A linked N64 ROM has no relocations left
in it: a pointer the linker resolved and a constant somebody typed are the
same four bytes. Only a relink can tell them apart, which is `shift rehearse`'s
job -- it is the empirical referee, and this command's text
coverage line points at it). What this module ranks is something it *can*
measure: how confidently a given word is an address **reference** at all,
against the false-positive families S0's hand rehearsal found by measuring
them.

S0's taxonomy, and the feature each family turned into:

* packed non-pointer fields -- ``gTrackSelectBgData+0x30,0x6c,0xa8,0xe4``
  holding ``0x80000800, 0x80001002, 0x80001804, 0x80002006``, an arithmetic
  progression of packed shorts at a constant stride -> **cluster detection**;
* matched-garbage archaeology -- Rare's build-machine leftovers in the ROM's
  data image, holding odd-valued "pointers" -> **alignment**;
* struct-constant families -- one repeated value across many arrays ->
  **repeat detection**;
* fixed-point table values -- ``gSineTable+0x7fc = 0x80008000`` -> **round
  constant**;
* opaque segments -- IPL3, DMA'd asset blobs -> **residence kind**;
* and the one signal that points the other way: a value landing exactly on a
  symbol's start address -> **points-at-symbol-start**, which S0 explicitly
  asked this classifier to elevate.

The rules are data (`TIER_RULES`, `RESIDENCE_SCORES`, `TIER_THRESHOLDS`),
travel inside every report, and work in two stages. Four *suppressors* are
terminal: a word matching one is ``low`` and is not scored, because each of
them is a reason the word is not an address at all. Everything else is scored
by where it lives (compiled data outranks an opaque blob) plus a bonus for
landing on a symbol start, and the score picks the tier.

Calibrated, not asserted: run against DKR ``us.v77`` and then checked against
S0's real 0x10 shift, all 38 ``high`` hits and 650 of the 657 ``medium`` ones
are words the shift actually moved -- real references, every one. The ``low``
tier is where the ambiguity lives, which is what a suppressor is for. Read a
tier as "how sure are we this is an address", never as "how dangerous is
this": a shifted build is what answers the second question.

One correction to S0 falls out of reading the map properly. S0's residue dump
attributed every ROM offset through ``.main``'s VRAM mapping, so words inside
the ``.assets`` segment came back labelled ``gAudioHeapStack+0x...``. They are
asset bytes. This module attributes residence per region, through that
region's own ``AT()`` placement, and refuses to name a symbol inside a blob at
all -- a DMA'd segment's VMA is a load target, not a place code lives.

Two more corrections, from S5's first real-patient run (``shift audit``
against Banjo-Kazooie's ``us.v10``, which has neither of DKR's simplifying
properties: it carries debug-info sections and it links overlays).

* **A section with no bytes in the running image is not a region.** GNU ld
  still prints ``.mdebug`` (and its non-``SHF_ALLOC`` kin: ``.pdr``,
  ``.comment``, ``.gptab*``, ``.reginfo``, ``.options``, ``.debug*``,
  ``.line``, ``.rel.*``) in the map's section-by-section body as though it
  were ordinary output, VMA and all -- BK's carries 706 per-object
  ``.mdebug`` records starting at VMA ``0``. Undetected, that VMA-0 section
  became a 762,123-word ``data`` region read at ``rom_source=vma-as-rom``
  (ROM offset == VMA, since it declares no ``AT()``) -- and, because
  ``movable_window`` also saw a ``kind="data"`` region starting at ``0``, the
  whole movable window's low bound followed it there too.
  `NON_ALLOC_SECTION_FAMILIES` is the name-pattern list `build_region_table`
  checks a section against *before* it ever becomes a region: a match
  becomes one ``kind="non-alloc"`` region carrying no ROM placement at all
  (``rom=None``, ``rom_source="excluded-non-alloc"``) -- visible in every
  region listing, excluded from scanning by construction (`SCANNED_KINDS`
  does not name ``"non-alloc"``) and from `movable_window` the same way. Name
  matching is the only signal available: a text ``ld -Map`` carries no
  ``SHF_ALLOC`` flag column. A section that matches by name but declares an
  explicit ``AT()`` load address is *not* excluded -- consistent with this
  whole module's rule (see :mod:`decomp_workbench.ldmap`) that an explicit
  placement always outranks an inferred one.

* **Region ROM placement was never the ambiguous half.** BK's map places
  fourteen overlay sections (``.CC``, ``.GV``, ``.MMM``, and eleven more) at
  one shared VMA, ``0x803863f0``, each with its own distinct ``AT()`` load
  address -- the filed hypothesis was that `build_region_table` resolved
  each one's ROM placement by looking that shared VMA up (ambiguous, by
  construction, across fourteen candidates). It does not: every region's
  ``(kind, start, end)`` run is already keyed off the *specific*
  `.OutputSection` object the parser positionally attached its input records
  to (`.ldmap.LdMap` groups `.InputSection` records by the output-section
  name in effect when the parser read them, never by address), and
  `_placement` reads that object's own ``load_address`` directly. Rerunning
  the audit against BK confirms it: every overlay region and ``.core2``'s
  ``data`` subregion resolve to ``rom_source="load-address"`` with the
  correct ROM value with zero change to this function. The bad first run's
  ``rom_source=unplaced`` on those same regions had a different cause
  entirely -- the image handed to the scan was the compressed, 16 MiB
  retail ``.z64``, but BK's ``AT()`` load addresses describe positions in
  the *uncompressed* linked layout (which runs to ~16.74 MiB, since overlay
  code is compressed by a post-link build step); any placement past 16 MiB
  read as out-of-bounds and was honestly reported ``unplaced``, exactly as
  it should be for whatever image is actually handed in. The real,
  standing gap this stage found is one level down, in
  :mod:`decomp_workbench.ldmap`: :meth:`~decomp_workbench.ldmap.LdMap.rom_for_vram`
  and friends resolve a *bare address* against every section that contains
  it, and a shared-VMA overlay group is exactly the shape that makes that
  resolution ambiguous (never exercised by this module's own region
  derivation, which keys off section identity, not address -- but real for
  any caller, such as ``shift rehearse``, that resolves an address inside an
  overlay window through those methods). See that module's docstring and
  :meth:`~decomp_workbench.ldmap.LdMap.sections_containing` for the honest
  version.

WB-140 (fresh-eyes QA on this branch, filed the day after S5's real-patient
run above): the module's every remaining number was honest about what it
counted, but nothing checked whether the *inputs* were the pair they claimed
to be. Three shapes, one root cause -- no post-parse sanity or caller-input
validation -- and all three are hard errors now rather than a confident
wrong answer.

* **A non-map file parses to zero sections.** :func:`~decomp_workbench.ldmap.
  parse_ld_map` is a permissive regex reader by design (see that module's
  docstring): text that never matches an output-section header simply
  contributes nothing, which is correct for a stray blank line and silently
  wrong for a whole file that is not a linker map at all -- QA's repro was
  passing a ``.z64`` image as ``--map``. `require_parsed_map` refuses a
  zero-section map before any region, window, or scan is derived from it,
  and sniffs the file's first bytes for a NUL (a linker map is text; a
  ROM's first bytes never are) to name the likely mistake.
* **A real map paired with an image from a different build.** Measured on
  the S0 artifacts: DKR's ``nm-base`` map against the ``shift-0x10`` image
  (a real 0x10 relink, not a corrupt file) produced a full, plausible,
  exit-0 report with ``scan_total`` ballooned from 3,443 to 1,323,680 -- the
  worst shape a wrong input pair can take, because nothing about the report
  *looks* wrong. `check_map_image_consistency` compares the image's actual
  length against the map's own maximum placed extent (``rom + size``,
  maximised over every region the map placed) and hard-errors when the two
  disagree in a way that is not benign cart padding.
* **A typo'd ``--blob`` name silently matches nothing.** ``.assets`` and
  ``.assets1`` are both valid-looking section-name shapes, and a name that
  matches no section changes the region table (the section keeps its
  default kind) without a whisper. `build_region_table` refuses any
  ``blobs`` entry that does not name a section the map actually has, which
  covers `shift rehearse` too: `build_rehearsal` calls this same function to
  derive its region table, so one fix serves both commands' ``--blob``.

S7 is about the *first* run rather than a wrong one. Running this command on
a project nobody has audited before means answering two questions out of
band -- which output sections are opaque, and where the movable window really
starts -- and S5's two community bring-ups each got one of them wrong in a
way the report could not show.

* **The map already knows which sections are blobs.** `suggest_blobs` reads
  the input records and names every output section all of whose objects are
  raw binaries (`BLOB_OBJECT_RULES`, data, two entries because two build
  conventions spell the same ``objcopy`` step differently). Measured: DKR's
  three, Banjo-Kazooie's seven and pilotwings64's six -- which is every
  ``--blob`` those projects have ever been audited with, plus pilotwings64's
  ``.ipl3``, which has the identical shape and which S5's operator simply
  did not think to name. The suggestion is printed and carried in JSON on
  every run and applied on none; ``--blobs auto`` is the caller saying yes,
  ``--no-blob`` is the caller disagreeing about one section, and the two
  compose (`resolve_blobs`).
* **A section placed at a ROM offset is not a movable-window floor.**
  pilotwings64's IPL3 arrives as ``build/bin/ipl3.o`` and derives as an
  ordinary ``data`` region at VMA ``0x00000040`` -- a boot block has no
  run-time address, so the map places it at its ROM offset. `movable_window`
  used to take the lowest movable region's VMA whatever it was, and reported
  a window starting at ``0x40``: two gigabytes wider at the bottom than the
  layout it describes, which counted 974,964 small integers in the
  filesystem blob as in-window hits. The floor now comes from the lowest
  *RAM-resident* movable region (`MOVABLE_FLOOR_MIN`), which is a property
  of the map rather than of whether the caller happened to name the section
  ``--blob``. pilotwings64's ``scan_total`` goes from 977,512 to 2,548 with
  ``scan_high`` unchanged at 62.

WB-144 is about the inventory itself, filed the day after a coordinator ran
pilotwings64's own scorecard (S6/S7's, `--elf` and all) with two of its six
``-T`` files left off ``--pins`` -- splat's ``undefined_funcs_auto.txt`` and
``undefined_syms_auto.txt``. The run exited clean and reported
``pins_shadowing=7``. The true number, with every ``-T`` file the link
actually consumes, is 17 (``docs/shiftability-campaign.md`` Sec 0.4) -- and
nothing about a 7 printed with no ``--elf`` complaint *looks* incomplete, the
same shape WB-140's map/image mismatch took. `pins_shadowing` and every other
pin-class count can only be wrong about pins it was *given*; `find_missing_pin_sources`
is the other half, over pins the *link* was given and the inventory was not.
It reads the linked ELF's own absolute symbol table -- which already carries
the answer, no relink required, the same evidence `reclassify_shadowing_pins`
reads -- and reports every absolute symbol address-shaped enough to matter
(inside the movable window or the map's own placed ROM extent) whose name
appears in no supplied ``--pins``/``--symbol-addrs`` file.

Two edges, both measured against pilotwings64's and Banjo-Kazooie's real
links rather than assumed, because a false positive here is exactly the kind
of noise that gets the whole check turned off:

* **The ld script's own per-segment boundary symbols are not missing pins.**
  A cascade script computes ``<segment>_ROM_START``/``_ROM_END`` (from
  ``__romPos``) and ``<segment>_TEXT_SIZE``/``_DATA_SIZE``/``_RODATA_SIZE``/
  ``_BSS_SIZE`` (from ``ABSOLUTE ((X_END - X_START))``) for every segment it
  names, and none of that comes from a ``-T`` file -- it is the main script's
  own bookkeeping. These *are* map assignments (``ldmap.symbol(name).
  is_assignment``), the same as a real pin, which is exactly why
  `LD_SCRIPT_BOUNDARY_SUFFIXES` has to be a name-shape family rather than a
  blanket "is this a map assignment" exclusion: splat's own auto-file pins
  print in the map with the identical ``NAME = expression`` shape (see
  :mod:`decomp_workbench.ldmap`'s module docstring on how little provenance a
  text map keeps), so excluding every map assignment would have hidden the
  incident's own ten names along with the boundary symbols. Measured on both
  projects: pilotwings64's eight segments and Banjo-Kazooie's twenty-three
  (nine of them overlay groups) produce 45 and 142 such names, and every one
  is one of the six suffixes -- zero collisions with either project's pin
  files, zero unexplained residue.
* **Not every absolute symbol came from a script at all.** A handful are
  object-file-native: the assembler's `_MACRO_INC_GUARD` (one per translation
  unit pilotwings64 compiles, value ``1``, a C include-guard constant, not an
  address) and objcopy's own ``_binary_<path>_size`` beside the ``_start``/
  ``_end`` pair `BLOB_OBJECT_RULES` already reads (a blob's byte count, not a
  reference) -- absolute, in no ``-T`` file, and not a map assignment either
  (``ldmap.symbol`` returns ``None`` for both shapes). `ELF_BUILTIN_ABSOLUTES`
  is the measured, documented exclusion for these; widening it to a
  guess -- ``_gp``, ``__bss_start``, and their kin are the textbook shape but
  appear in neither project's own link -- is deliberately left undone until a
  real link shows one.

Size is not part of either edge's decision, on purpose: `reclassify_shadowing_
pins` uses a symbol's size as evidence of what it overrode, but a missing
inventory entry is missing regardless of whether the ELF happens to carry a
size on it, so this check treats a zero-size and a sized absolute symbol
identically once they clear the two exclusions above. And the domain itself
is narrower than "every absolute symbol" on purpose: a value neither inside
the movable window nor inside the map's placed ROM extent (a hardware
register in kseg1, say) is outside what this check can see at all -- the same
honesty `movable_window` and `ROM_OFFSET` already practice, not a gap this
module pretends is covered.

Two more affordances live next door, in :mod:`decomp_workbench.pins`, and are
wired up from here. :func:`~decomp_workbench.pins.reclassify_rom_offsets`
runs against this module's own ``max_placed_extent`` and turns the raw
cartridge offsets a splat project pins into a class with a remediation
(Banjo-Kazooie: 37 pins, from ``unclassified`` to ``rom-offset``). And
`ShiftAudit.whitelist_template` drafts the whitelist a first run has no way
to have written yet, from the evidence the same run already collected.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .ldmap import ElfSymbols, LdMap
from .mips_refs import RangeModel, alignment
from .pins import (
    ARTIFACT_SUSPECT,
    AUTHENTIC_FIXED,
    DERIVED,
    ROM_OFFSET,
    SHADOWING_PIN,
    UNCLASSIFIED,
    PinCatalogue,
    reclassify_rom_offsets,
    reclassify_shadowing_pins,
    whitelist_template_text,
)

__all__ = [
    "BLOB_ERROR_SECTION_LIMIT",
    "BLOB_OBJECT_RULES",
    "BLOB_SOURCE_AUTO",
    "BLOB_SOURCE_EXPLICIT",
    "BLOB_SOURCE_NONE",
    "CLUSTER_MINIMUM",
    "ELF_BUILTIN_ABSOLUTES",
    "LD_SCRIPT_BOUNDARY_SUFFIXES",
    "MAP_SNIFF_BYTES",
    "MOVABLE_FLOOR_MIN",
    "NON_ALLOC_KIND",
    "NON_ALLOC_ROM_SOURCE",
    "NON_ALLOC_SECTION_FAMILIES",
    "PADDING_PATTERN_MAX_PERIOD",
    "REPEAT_MINIMUM",
    "RESIDENCE_SCORES",
    "SCANNED_KINDS",
    "SYMBOL_START_BONUS",
    "TIER_RULES",
    "TIER_THRESHOLDS",
    "BlobPlan",
    "BlobRule",
    "BlobSuggestion",
    "ConsistencyCheck",
    "Hit",
    "MissingPin",
    "MovableWindow",
    "Region",
    "ShiftAudit",
    "TierRule",
    "build_region_table",
    "build_shift_audit",
    "check_map_image_consistency",
    "find_missing_pin_sources",
    "movable_window",
    "require_parsed_map",
    "resolve_blobs",
    "scan_regions",
    "shift_audit_lines",
    "suggest_blobs",
]

#: JSON identity for the report.
SHIFT_AUDIT_SCHEMA = "decomp-workbench-shift-audit-v1"

#: Region kinds whose bytes are read word by word. ``"text"`` is placed and
#: counted but never scanned -- an instruction word's address arithmetic is
#: split across a ``lui``/``%lo`` pair and only a relink resolves it, which is
#: the rehearsal's question and not this command's. ``"non-alloc"`` is placed
#: and counted the same way "text" is -- never scanned, because it carries no
#: bytes that are ever really in the running image at all (see
#: `NON_ALLOC_SECTION_FAMILIES`).
SCANNED_KINDS: tuple[str, ...] = ("data", "blob", "header")

#: The `Region.kind` a section from `NON_ALLOC_SECTION_FAMILIES` is given.
#: Deliberately absent from `SCANNED_KINDS` and from `movable_window`'s
#: movable-kind set (``"text"``, ``"data"``, ``"bss"``) -- excluded from both
#: by construction, not by a second check that could drift from the first.
NON_ALLOC_KIND = "non-alloc"

#: The `Region.rom_source` a `NON_ALLOC_KIND` region always carries. Never
#: derived through `_placement` -- a non-alloc section's VMA is not a ROM
#: offset candidate at all, so this never contributes a ``vma-as-rom`` guess
#: the way an ordinary unplaced section without ``AT()`` would.
NON_ALLOC_ROM_SOURCE = "excluded-non-alloc"

#: Section-name families GNU ld emits without ``SHF_ALLOC`` set -- debug
#: info and symbol-table metadata the linker prints in the map's
#: section-by-section body, VMA and all, exactly like a real output section,
#: but which is never resident in the running image no matter what VMA it
#: prints (BK's ``.mdebug`` prints VMA ``0`` -- indistinguishable, by extent
#: alone, from a genuine section placed at the ROM's own base). A text
#: ``ld -Map`` carries no ``SHF_ALLOC`` flag column, so name is the only
#: signal available; this list is data (checked by `_is_non_alloc_section`,
#: not spelled out as a chain of `if`s) so a caller can see exactly which
#: patterns this module knows about, and a new one is one entry, not a new
#: code path. Each entry is ``(pattern, "exact" | "prefix")``.
NON_ALLOC_SECTION_FAMILIES: tuple[tuple[str, str], ...] = (
    (".mdebug", "prefix"),  # .mdebug, .mdebug.abi32
    (".pdr", "exact"),
    (".comment", "exact"),
    (".gptab", "prefix"),  # .gptab.sdata, .gptab.rodata, ...
    (".reginfo", "exact"),
    (".options", "exact"),
    (".debug", "prefix"),  # .debug_info, .debug_line, .debug_abbrev, ...
    (".line", "exact"),
    (".rel.", "prefix"),  # .rel.text, .rel.data, ... (pre-final-link relocs)
)


def _is_non_alloc_section(name: str) -> bool:
    """Whether `name` matches a family `NON_ALLOC_SECTION_FAMILIES` names."""

    for pattern, kind in NON_ALLOC_SECTION_FAMILIES:
        if kind == "exact":
            if name == pattern:
                return True
        elif name.startswith(pattern):
            return True
    return False


#: How many hits at one constant stride, in arithmetic progression, make a
#: packed-field family rather than three coincidences.
CLUSTER_MINIMUM = 3

#: How many times one value must repeat to read as a struct constant.
REPEAT_MINIMUM = 4

#: What a word's residence is worth. Compiled data is where a real pointer
#: lives; an opaque blob is where S0 found every one of its false positives.
RESIDENCE_SCORES: dict[str, int] = {"data": 2, "header": 1, "blob": 0}

#: What landing exactly on a symbol's start address is worth. Two, so that it
#: lifts a blob resident clear of the blob's own noise floor without making
#: residence irrelevant.
SYMBOL_START_BONUS = 2

#: The score each tier needs. Read them together with `RESIDENCE_SCORES`:
#: compiled data plus a symbol start is ``high``; compiled data alone, or a
#: blob resident pointing at a symbol start, is ``medium``.
TIER_THRESHOLDS: dict[str, int] = {"high": 3, "medium": 2}


@dataclass(frozen=True)
class TierRule:
    """One published reason a hit is ranked where it is."""

    name: str
    tier: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tier": self.tier, "evidence": self.evidence}


#: The suppressors, in the order they are tried. Each is terminal: a word that
#: matches one is ``low`` and is never scored, because every one of them is a
#: reason to think the word is not an address. Order matters only for the
#: label a hit reports, not for the tier -- they all answer ``low``.
TIER_RULES: tuple[TierRule, ...] = (
    TierRule(
        "whitelisted",
        "low",
        "the caller declared this address authentic, with a reason attached",
    ),
    TierRule(
        "misaligned",
        "low",
        "the value is not a multiple of 4 and cannot be a MIPS data pointer "
        "(S0: build-machine leftovers in the retail data image)",
    ),
    TierRule(
        "progression-cluster",
        "low",
        f"{CLUSTER_MINIMUM} or more hits at one constant stride whose values "
        "form an arithmetic progression: packed fields, not pointers "
        "(S0: gTrackSelectBgData)",
    ),
    TierRule(
        "repeated-value",
        "low",
        f"the same value at {REPEAT_MINIMUM} or more hits anywhere, or at "
        f"{CLUSTER_MINIMUM} or more in one constant-stride run: one struct "
        "constant counted many times, not that many references "
        "(S0: 0x80020c00 across the TextElements arrays)",
    ),
    TierRule(
        "round-constant",
        "low",
        "the low half of the value is 0x0000 or 0x8000 and no symbol starts "
        "there: a fixed-point or packed constant (S0: gSineTable+0x7fc)",
    ),
)

#: The label a hit that survived every suppressor carries.
SCORED = "scored"


# ---------------------------------------------------------------------------
# WB-140 rule A: a map that parsed to nothing
# ---------------------------------------------------------------------------

#: Bytes sampled from the start of a candidate ``--map`` file to guess
#: whether it is binary rather than text, before either file is read in
#: full. A linker map is ASCII: addresses, section names, and object paths
#: are all printable. A single NUL byte this early is something no real map
#: ever prints and is also the first byte of an N64 ROM's boot-code region
#: -- cheap and specific enough to name the likely mistake without
#: decoding anything.
MAP_SNIFF_BYTES = 4096


def require_parsed_map(ldmap: LdMap, *, path: str, sample: bytes = b"") -> None:
    """WB-140 rule A: refuse a map that parsed to zero output sections.

    QA's repro: pass any ``.z64`` image as ``--map``. `parse_ld_map` is a
    permissive regex reader by design (see :mod:`decomp_workbench.ldmap`) --
    text that never matches an output-section header simply contributes
    nothing to the parse, which is correct for a stray blank line and
    silently wrong for an entire file that is not a linker map. Every
    downstream number (``region_count``, ``scan_total``, the pin counts) was
    then honestly, uselessly zero: a clean exit-0 report that answered no
    question at all. Zero sections is never a legitimate report for a
    linked project, so this refuses before a region, a window, or a scan is
    derived from a map that carries none.

    ``sample`` is the caller's own cheap sniff of the file's first bytes
    (see `MAP_SNIFF_BYTES`) -- checked only when there is something to
    refuse, so the swap hint names the likely mistake instead of leaving a
    reader to guess it.
    """

    if ldmap.sections:
        return
    hint = (
        " Is this a linker map? --map and --image may be swapped."
        if b"\x00" in sample
        else ""
    )
    raise ValueError(
        f"{path} parsed as no linker map: 0 output sections were found.{hint}"
    )


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------


def _kind_for_input(name: str) -> str:
    """Classify one input-section record by its name.

    ``.gptab.bss`` is why this asks whether ``bss`` appears anywhere in the
    name rather than comparing against a list: a cascade script concatenates
    whatever the compiler emitted, and the bss family has more spellings than
    a list will keep up with.
    """

    if name.startswith(".text"):
        return "text"
    if "bss" in name:
        return "bss"
    return "data"


@dataclass(frozen=True)
class Region:
    """One contiguous run of image bytes and how its words should be read."""

    output_section: str
    kind: str
    """``"text"``, ``"data"``, ``"blob"``, ``"header"``, ``"bss"``, or
    `NON_ALLOC_KIND` (``"non-alloc"``)."""

    vram: int
    size: int
    rom: int | None
    rom_source: str
    """``"load-address"`` (the section declared ``AT()``), ``"vma-as-rom"``
    (it did not, and its VMA is a plausible offset into this image),
    ``"unplaced"`` (it did not, and its VMA is not), ``"not-resident"`` (bss
    owns no image bytes), or `NON_ALLOC_ROM_SOURCE` (a
    `NON_ALLOC_SECTION_FAMILIES` name match: never resident, regardless of
    what VMA the map printed for it)."""

    @property
    def words(self) -> int:
        return self.size // 4

    @property
    def scanned(self) -> bool:
        return self.kind in SCANNED_KINDS and self.rom is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_section": self.output_section,
            "kind": self.kind,
            "vram": self.vram,
            "size": self.size,
            "rom": self.rom,
            "rom_source": self.rom_source,
            "words": self.words,
            "scanned": self.scanned,
        }


def _placement(
    section: Any, vma: int, kind: str, *, image_size: int
) -> tuple[int | None, str]:
    """Return ``(rom offset, how it was derived)`` for one region's start."""

    if kind == "bss":
        return None, "not-resident"
    if section.load_address is not None:
        offset, source = section.load_address + (vma - section.vma), "load-address"
    else:
        offset, source = vma, "vma-as-rom"
    # A placement past the end of the image means the map and the image do not
    # describe the same link. Report it rather than reading whatever bytes
    # happen to sit at the offset.
    if not 0 <= offset < image_size:
        return None, "unplaced"
    return offset, source


#: How many section names an unknown-``--blob`` error spells out before
#: falling back to "+N more" -- long enough that a typo is still obviously
#: absent from the list, short enough that a map with hundreds of sections
#: (BK's map has fourteen overlay output sections alone) does not print a
#: wall of names for one bad argument.
BLOB_ERROR_SECTION_LIMIT = 20


# ---------------------------------------------------------------------------
# Blob suggestion (S7): the map already knows which sections are opaque
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlobRule:
    """One published shape that makes an input object a raw binary."""

    name: str
    pattern: str
    match: str
    """``"suffix"`` (the object path ends with `pattern`) or ``"directory"``
    (one of the path's directory components is `pattern`)."""

    evidence: str

    def matches(self, object_path: str) -> bool:
        if self.match == "suffix":
            return object_path.endswith(self.pattern)
        return self.pattern in object_path.replace("\\", "/").split("/")[:-1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pattern": self.pattern,
            "match": self.match,
            "evidence": self.evidence,
        }


#: How a raw-binary object is recognised from its path alone, as data for the
#: same reason `TIER_RULES` is. Both entries describe the *same* build step --
#: ``objcopy``'ing a ``.bin`` file into a linkable object -- under the two
#: naming conventions the projects in front of this tool actually use, and
#: neither is a guess about content: a section every one of whose inputs came
#: out of that step has no compiled code or compiler-emitted data in it at
#: all, which is exactly what ``--blob`` means.
#:
#: A third signal exists and is deliberately not used: ``objcopy`` also emits
#: ``_binary_<path>_start``/``_end`` symbols, which every one of these
#: sections carries. It would be stronger evidence and it is not available
#: here -- a symbol proves the *object* is a raw binary, and the question
#: this rule answers is whether *every* input of one output section is, which
#: only the input-record table can answer. The path patterns answer it
#: directly, per record, and are checked against the section's whole input
#: list rather than against whichever symbol happened to land first.
BLOB_OBJECT_RULES: tuple[BlobRule, ...] = (
    BlobRule(
        "bin-object-suffix",
        ".bin.o",
        "suffix",
        "the object is named after a `.bin` file (splat's convention, and "
        "DKR's build/assets/boot.bin.o): objcopy'd raw bytes, never compiled "
        "code",
    ),
    BlobRule(
        "bin-directory",
        "bin",
        "directory",
        "the object was built in a `bin/` directory (pilotwings64's "
        "build/bin/filesys.o): the same objcopy'd raw bytes under a build "
        "that drops the `.bin` from the object name",
    ),
)


def _blob_rule_for(object_path: str) -> BlobRule | None:
    """The first `BLOB_OBJECT_RULES` entry `object_path` matches, or None."""

    for rule in BLOB_OBJECT_RULES:
        if rule.matches(object_path):
            return rule
    return None


@dataclass(frozen=True)
class BlobSuggestion:
    """One output section the map's own inputs say is opaque, and why."""

    output_section: str
    rule: str
    """The `BLOB_OBJECT_RULES` entry that matched. When a section's objects
    match different rules this names the first one in rule order, and
    `objects` carries every path, so the provenance never collapses to a
    single example."""

    objects: tuple[str, ...]
    input_records: int
    vram: int
    size: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_section": self.output_section,
            "rule": self.rule,
            "objects": list(self.objects),
            "input_records": self.input_records,
            "vram": self.vram,
            "size": self.size,
        }


def suggest_blobs(ldmap: LdMap) -> tuple[BlobSuggestion, ...]:
    """Derive the blob set from the map's input records, in map order.

    A section qualifies when it has input records at all and *every* one of
    them names a raw-binary object (`BLOB_OBJECT_RULES`). The "every" is the
    whole rule: Banjo-Kazooie's ``.core2`` holds three ``.bin.o`` objects
    among 398, mixed in with the compiled overlay it belongs to, and a
    section with one compiled input is a section whose words are worth
    attributing to symbols -- which is the one thing ``--blob`` turns off.

    This is a *suggestion*, never an application. `resolve_blobs` is where a
    caller says yes to it, because which sections are opaque is a claim about
    a project's build that the project gets to make; what this function does
    is stop the caller having to discover the answer by reading a linker map
    by hand, which is the cold-start friction it exists to remove.
    """

    by_output: dict[str, list[Any]] = {}
    for record in ldmap.input_sections:
        by_output.setdefault(record.output_section, []).append(record)

    found: list[BlobSuggestion] = []
    for section in ldmap.sections_sorted():
        records = by_output.get(section.name, [])
        if not records:
            continue
        rules = [_blob_rule_for(record.object_path) for record in records]
        if any(rule is None for rule in rules):
            continue
        order = {rule.name: index for index, rule in enumerate(BLOB_OBJECT_RULES)}
        named = sorted(
            {rule.name for rule in rules if rule is not None},
            key=lambda name: order[name],
        )
        found.append(
            BlobSuggestion(
                output_section=section.name,
                rule=named[0],
                objects=tuple(sorted({record.object_path for record in records})),
                input_records=len(records),
                vram=section.vma,
                size=section.size,
            )
        )
    return tuple(found)


#: `BlobPlan.source` when the caller named every blob with ``--blob``.
BLOB_SOURCE_EXPLICIT = "explicit"
#: `BlobPlan.source` when ``--blobs auto`` adopted the suggestion (with or
#: without extra ``--blob`` names and ``--no-blob`` exclusions on top).
BLOB_SOURCE_AUTO = "auto"
#: `BlobPlan.source` when no section is treated as opaque at all.
BLOB_SOURCE_NONE = "none"


@dataclass(frozen=True)
class BlobPlan:
    """Which sections this run treats as opaque, where that came from, and
    what the map would have suggested either way."""

    applied: tuple[str, ...]
    source: str
    suggestions: tuple[BlobSuggestion, ...]
    excluded: tuple[str, ...]

    @property
    def suggested(self) -> tuple[str, ...]:
        return tuple(item.output_section for item in self.suggestions)

    @property
    def unadopted(self) -> tuple[str, ...]:
        """Suggested sections this run is not treating as opaque."""

        return tuple(
            name for name in self.suggested if name not in frozenset(self.applied)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "blobs": list(self.applied),
            "blob_source": self.source,
            "blobs_excluded": list(self.excluded),
            "suggested_blobs": list(self.suggested),
            "blob_suggestions": [item.as_dict() for item in self.suggestions],
            "blob_rules": [item.as_dict() for item in BLOB_OBJECT_RULES],
        }


def resolve_blobs(
    ldmap: LdMap,
    *,
    blobs: Iterable[str] = (),
    auto: bool = False,
    excluded: Iterable[str] = (),
) -> BlobPlan:
    """Turn the caller's blob arguments and the map's suggestion into one set.

    ``--blob`` always adds and ``--no-blob`` always subtracts, whether or not
    ``--blobs auto`` is in play, so the two spellings compose rather than
    override: ``--blobs auto --no-blob .ipl3`` is the exact shape a project
    reaches for when the derivation is right about five of its six sections.

    Naming the same section both ways is refused rather than resolved by
    precedence. Whichever precedence this picked, half the readers of the
    command line would expect the other one -- and a caller who wrote both
    did not mean either.
    """

    suggestions = suggest_blobs(ldmap)
    named = tuple(dict.fromkeys(blobs))
    removed = tuple(dict.fromkeys(excluded))
    both = [name for name in named if name in set(removed)]
    if both:
        raise ValueError(
            f"--blob and --no-blob name the same section: {', '.join(sorted(both))}"
        )
    known_sections = [section.name for section in ldmap.sections_sorted()]
    unknown = sorted(set(removed) - set(known_sections))
    if unknown:
        raise ValueError(
            "--no-blob names a section this map does not have: "
            f"{', '.join(unknown)} (map sections: "
            f"{_section_name_list(known_sections)})"
        )

    applied = list(named)
    if auto:
        for item in suggestions:
            if item.output_section not in applied:
                applied.append(item.output_section)
    applied = [name for name in applied if name not in set(removed)]

    if not applied:
        source = BLOB_SOURCE_NONE
    elif auto:
        source = BLOB_SOURCE_AUTO
    else:
        source = BLOB_SOURCE_EXPLICIT
    return BlobPlan(
        applied=tuple(applied),
        source=source,
        suggestions=suggestions,
        excluded=removed,
    )


def _section_name_list(names: Sequence[str]) -> str:
    """Render a capped, comma-separated section-name list for an error."""

    shown = list(names[:BLOB_ERROR_SECTION_LIMIT])
    remainder = len(names) - len(shown)
    joined = ", ".join(shown) if shown else "no sections at all"
    return f"{joined}, ... (+{remainder} more)" if remainder > 0 else joined


def build_region_table(
    ldmap: LdMap,
    *,
    image_size: int,
    blobs: Iterable[str] = (),
    header_sections: Iterable[str] = (".header",),
) -> tuple[Region, ...]:
    """Derive the region table from the map, with the caller's overrides.

    An output section the caller named a blob becomes exactly one region
    covering the whole section: a blob is opaque by definition and splitting
    it by the input records that happen to be inside would claim a structure
    the caller just said is not there. Every other section is split into runs
    of like input records, so ``.main``'s ``.text`` never merges with the
    ``.data``/``.rodata`` that follow it -- which is what lets the scan skip
    instruction words without skipping the whole section.

    ROM placement is derived, never guessed twice. A section that declared
    ``AT()`` uses its load address. One that did not is placed at its own VMA
    *only* when that VMA is a plausible offset into this image (DKR's
    ``.header`` at 0 and ``.boot`` at 0x40 are), and is reported ``unplaced``
    otherwise rather than read from somewhere arbitrary.

    A section matching `NON_ALLOC_SECTION_FAMILIES` (BK's ``.mdebug`` and
    kin) is excluded before any of that: it becomes one `NON_ALLOC_KIND`
    region covering the whole section, with no ROM placement derived for it
    at all -- never a ``vma-as-rom`` guess at whatever VMA the map happened
    to print (``.mdebug`` prints ``0``, and an undetected VMA-0 ``data``
    region is indistinguishable from a real one at the ROM's own base). A
    section that matches by name but declares an explicit ``AT()`` is *not*
    excluded: an explicit placement always outranks the name-based
    inference, the same rule :mod:`decomp_workbench.ldmap` applies to every
    address it resolves.

    WB-140 rule C: every name in ``blobs`` must be an output section this
    map actually has, checked before any region is derived. A typo
    (``.assets1`` for ``.assets``) previously matched nothing and changed
    the region table -- and therefore the movable window and the scan --
    with no error at all, because an unmatched blob name and an
    intentionally-absent one look identical to a caller who only sees the
    downstream numbers move. `shift_rehearse.build_rehearsal` calls this
    same function to derive its own region table, so this one check covers
    both commands' ``--blob``.
    """

    blob_names = frozenset(blobs)
    known_sections = [section.name for section in ldmap.sections_sorted()]
    unknown_blobs = sorted(blob_names - set(known_sections))
    if unknown_blobs:
        raise ValueError(
            "--blob names a section this map does not have: "
            f"{', '.join(unknown_blobs)} (map sections: "
            f"{_section_name_list(known_sections)})"
        )
    header_names = frozenset(header_sections)
    by_output: dict[str, list[Any]] = {}
    for record in ldmap.input_sections:
        by_output.setdefault(record.output_section, []).append(record)

    regions: list[Region] = []
    for section in ldmap.sections_sorted():
        if section.load_address is None and _is_non_alloc_section(section.name):
            regions.append(
                Region(
                    output_section=section.name,
                    kind=NON_ALLOC_KIND,
                    vram=section.vma,
                    size=section.size,
                    rom=None,
                    rom_source=NON_ALLOC_ROM_SOURCE,
                )
            )
            continue

        records = sorted(
            (item for item in by_output.get(section.name, ()) if item.size),
            key=lambda item: item.vma,
        )

        if section.name in blob_names or section.name in header_names:
            kind = "blob" if section.name in blob_names else "header"
            rom, source = _placement(section, section.vma, kind, image_size=image_size)
            regions.append(
                Region(
                    output_section=section.name,
                    kind=kind,
                    vram=section.vma,
                    size=section.size,
                    rom=rom,
                    rom_source=source,
                )
            )
            continue

        if not records:
            rom, source = _placement(
                section, section.vma, "data", image_size=image_size
            )
            regions.append(
                Region(
                    output_section=section.name,
                    kind="data",
                    vram=section.vma,
                    size=section.size,
                    rom=rom,
                    rom_source=source,
                )
            )
            continue

        runs: list[list[Any]] = []
        for record in records:
            kind = _kind_for_input(record.name)
            if runs and runs[-1][0] == kind and record.vma >= runs[-1][2]:
                # Same kind and no overlap: extend across whatever alignment
                # filler `ld` inserted (which the map prints as a `*fill*`
                # pseudo-record this reader does not carry). Filler bytes are
                # scanned like any other -- they are in the image.
                runs[-1][2] = record.end
                continue
            runs.append([kind, record.vma, record.end])
        # Whatever the last run's records claimed, the section's own extent is
        # the authority on where it ends -- trailing alignment belongs to it.
        runs[-1][2] = max(runs[-1][2], section.end)
        for kind, start, end in runs:
            rom, source = _placement(section, start, kind, image_size=image_size)
            regions.append(
                Region(
                    output_section=section.name,
                    kind=kind,
                    vram=start,
                    size=end - start,
                    rom=rom,
                    rom_source=source,
                )
            )
    return tuple(regions)


@dataclass(frozen=True)
class MovableWindow:
    """The VRAM extent an insertion would move, and where it came from."""

    lo: int
    hi: int
    lo_section: str | None
    hi_section: str | None

    def contains(self, value: int) -> bool:
        return self.lo <= value < self.hi

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_lo": self.lo,
            "window_hi": self.hi,
            "window_lo_section": self.lo_section,
            "window_hi_section": self.hi_section,
        }


#: The lowest VMA `movable_window` will accept as its floor. Everything the
#: MIPS fixed-mapping segments call RAM starts at or above ``0x80000000``
#: (kseg0), so a movable-kind region printed below it is not resident at a
#: run-time address at all -- it is a ROM-space section the map placed by its
#: own offset. Shares its value with
#: :data:`decomp_workbench.pins.VRAM_WINDOW_FLOOR` and answers the same
#: question from the other side: that one asks whether a *value* is too small
#: to be an address, this one whether a *section* is.
MOVABLE_FLOOR_MIN = 0x80000000


def movable_window(regions: Sequence[Region]) -> MovableWindow:
    """Derive ``[first movable start, last bss end)`` from the region table.

    Blobs and the header are excluded from both ends. A DMA'd asset segment's
    VMA is the address it is copied *to* at run time, not an address anything
    is linked at -- DKR's ``.assets`` starts at the same VMA as
    ``.assets_lut`` and runs 10 MB past the end of RAM, which would make a
    nonsense of any window that believed it. `NON_ALLOC_KIND` regions are
    excluded the same way, for a sharper reason: they hold no bytes that are
    ever in the running image at all, so whatever VMA the map printed for one
    (BK's ``.mdebug`` prints ``0``) is not a movable address either -- this
    needs no separate check because ``"non-alloc"`` was never in the movable
    kind set below to begin with.

    **The floor comes from the first RAM-resident movable region, not from
    the first movable region.** S5's pilotwings64 run is why. That project's
    IPL3 arrives as ``build/bin/ipl3.o``, a raw binary the caller had no
    reason to name ``--blob``, so it derived as an ordinary ``data`` region
    -- at VMA ``0x00000040``, because a boot-block section is placed at its
    ROM offset and has no run-time address to be placed at. The window's low
    bound followed it there and the audit reported
    ``window_lo=0x00000040 window_lo_section=.ipl3``: a window two gigabytes
    wider at the bottom than the layout it describes, which counts every
    small integer in the image as an in-window hit. The correct floor is the
    first section an insertion could actually move, and no insertion moves
    anything below `MOVABLE_FLOOR_MIN` -- pilotwings64's is ``.entry`` at
    ``0x80200050``. Excluding the low section by *kind* (blob) would have
    depended on the caller having named it one; excluding it by residence
    does not, which is the difference between a fix and a workaround.

    A map with no RAM-resident movable region at all keeps the old answer --
    the lowest movable region there is. That is not a real N64 link, and
    inventing an empty window for one would hide the map rather than describe
    it.

    Both bounds name the section that set them, because a window derived from
    the wrong sections is the one way this whole scan can be quietly wrong,
    and a reader has to be able to see it.
    """

    movable = [item for item in regions if item.kind in ("text", "data", "bss")]
    if not movable:
        return MovableWindow(lo=0, hi=0, lo_section=None, hi_section=None)
    resident = [item for item in movable if item.vram >= MOVABLE_FLOOR_MIN]
    low = min(resident or movable, key=lambda item: item.vram)
    bss = [item for item in movable if item.kind == "bss"]
    high = max(bss or movable, key=lambda item: item.vram + item.size)
    return MovableWindow(
        lo=low.vram,
        hi=high.vram + high.size,
        lo_section=low.output_section,
        hi_section=high.output_section,
    )


# ---------------------------------------------------------------------------
# WB-140 rule B: does this image match this map?
# ---------------------------------------------------------------------------

#: The longest repeating unit `_is_uniform_padding` checks for, beyond the
#: single-byte case (0x00 blank cart space or 0xFF erased/unprogrammed
#: flash, checked first and separately because a cart's padding region can
#: run to megabytes and a byte-value check is the only one cheap enough
#: there). Chosen to comfortably cover word- and dword-periodic fill
#: without ever testing a candidate period anywhere near the excess's own
#: length -- real content does not come out periodic at a short period by
#: chance.
PADDING_PATTERN_MAX_PERIOD = 16


def _is_uniform_padding(data: bytes) -> bool:
    """Whether `data` reads as fill, not as two builds' worth of content."""

    if not data:
        return True
    if len(set(data)) == 1:
        return True
    for period in range(2, min(PADDING_PATTERN_MAX_PERIOD, len(data) // 2) + 1):
        if len(data) % period:
            continue
        unit = data[:period]
        if all(
            data[index : index + period] == unit
            for index in range(0, len(data), period)
        ):
            return True
    return False


@dataclass(frozen=True)
class ConsistencyCheck:
    """WB-140 rule B: is this image really the one the map describes?

    Measured on the S0 artifacts: DKR's ``nm-base`` map (the un-shifted
    build) against the ``shift-0x10`` image (a real, correctly-linked
    0x10-byte relink of the *same* project) is not a corrupt pair -- it is
    exactly the mistake a caller running a sweep across a project's own
    shift-rehearsal artifacts would make, and it produced a full, plausible,
    exit-0 report with ``scan_total`` ballooned from 3,443 to 1,323,680. A
    confident wrong answer about address safety is the worst shape this
    command can take, worse than a crash, because nothing about the report
    signals that anything is wrong.

    The check is one number handed against another. `max_placed_extent` is
    ``rom + size`` maximised over every region the map actually placed --
    the last byte the map claims the image should hold. An image longer
    than that is either benign cart padding (checked byte-for-byte,
    `_is_uniform_padding`) or content from a different build. An image
    shorter than that means some of what the map placed is not really
    there, which `check_map_image_consistency` counts per region
    (`regions_unplaced_past_eof`) rather than leaving to be inferred from
    a wall of ``rom_source=unplaced`` rows.
    """

    max_placed_extent: int
    """``rom + size``, maximised over every region the map placed (``rom``
    is not ``None``) -- the last byte the map claims the image should
    hold."""

    padding_bytes: int | None
    """Bytes the image runs past `max_placed_extent`, once that excess is
    confirmed uniform fill. ``None`` when the image is not longer than the
    map's placed extent -- there is no excess to characterise."""

    regions_unplaced_past_eof: int
    """Placeable regions (every kind but ``bss`` and `NON_ALLOC_KIND`,
    neither of which ever claims image bytes) whose claimed extent runs
    past the image actually handed in -- either because the map's own
    placement already resolved past the image (``rom_source="unplaced"``)
    or because a region starts inside the image but its declared size
    still carries its tail past the end. Nonzero here is the headline
    signal a truncated or mismatched image leaves, even though every
    individual region row can look unremarkable on its own (a region
    whose start is in-bounds keeps its ordinary ``rom_source`` no matter
    how far its tail overruns)."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_placed_extent": self.max_placed_extent,
            "padding_bytes": self.padding_bytes,
            "regions_unplaced_past_eof": self.regions_unplaced_past_eof,
        }


def check_map_image_consistency(
    regions: Sequence[Region],
    image: bytes,
    *,
    map_path: str | None = None,
    image_path: str | None = None,
) -> ConsistencyCheck:
    """WB-140 rule B, always on: refuse an image that does not match the map.

    Three outcomes, in the order they are tested. The image can run past
    the map's own extent (`image_bytes > max_placed_extent`): benign when
    the excess is uniform padding, a hard error naming both numbers
    otherwise -- QA's exact repro (the S0 ``nm-base`` map against the
    ``shift-0x10`` image) is a 16-byte, non-uniform excess and is the live
    test this rule exists to pass. The image can run short
    (`image_bytes < max_placed_extent`): never silently accepted, because
    more than half the map's placed regions landing past the end of the
    image is not an overlay quirk, it is the wrong image -- but *some*
    regions landing past EOF is common enough (a legitimately truncated
    debug build, an overlay that simply is not linked into this
    particular image) that it is reported rather than refused outright.
    Or the two agree exactly, the healthy case every conformance fixture in
    this test suite is built to hit.
    """

    max_extent = max(
        (item.rom + item.size for item in regions if item.rom is not None),
        default=0,
    )
    image_bytes = len(image)

    placeable = [item for item in regions if item.kind not in ("bss", NON_ALLOC_KIND)]
    past_eof = sum(
        1
        for item in placeable
        if item.rom is None or item.rom + item.size > image_bytes
    )

    if image_bytes > max_extent:
        excess = image[max_extent:]
        if not _is_uniform_padding(excess):
            details = [
                f"image_bytes={image_bytes:,}",
                f"map_placed_extent={max_extent:,}",
            ]
            if map_path:
                details.append(f"map={map_path}")
            if image_path:
                details.append(f"image={image_path}")
            raise ValueError(
                f"image extends {len(excess):,} bytes past the map's "
                "placed extent and the excess is not uniform padding "
                "-- the map and image are likely from different builds "
                f"({', '.join(details)})"
            )
        return ConsistencyCheck(
            max_placed_extent=max_extent,
            padding_bytes=len(excess),
            regions_unplaced_past_eof=past_eof,
        )

    if image_bytes < max_extent:
        if placeable and past_eof * 2 > len(placeable):
            details = [
                f"regions_unplaced_past_eof={past_eof}",
                f"placed_regions={len(placeable)}",
                f"image_bytes={image_bytes:,}",
                f"map_placed_extent={max_extent:,}",
            ]
            if map_path:
                details.append(f"map={map_path}")
            if image_path:
                details.append(f"image={image_path}")
            raise ValueError(
                f"{past_eof} of {len(placeable)} placed regions land past "
                "the end of the image -- that is not an overlay quirk, "
                f"that is the wrong image ({', '.join(details)})"
            )
        return ConsistencyCheck(
            max_placed_extent=max_extent,
            padding_bytes=None,
            regions_unplaced_past_eof=past_eof,
        )

    return ConsistencyCheck(
        max_placed_extent=max_extent,
        padding_bytes=0,
        regions_unplaced_past_eof=past_eof,
    )


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """One word holding a value inside the movable window, with its features."""

    rom: int
    vram: int
    value: int
    region: str
    residence: str
    resident_symbol: str | None
    resident_offset: int | None
    target_symbol: str | None
    target_offset: int | None
    alignment: int
    points_at_symbol_start: bool
    repeats: int
    cluster: int | None
    window: str | None
    whitelisted: bool
    reason: str | None
    score: int
    rule: str
    tier: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rom": self.rom,
            "vram": self.vram,
            "value": self.value,
            "region": self.region,
            "residence": self.residence,
            "resident_symbol": self.resident_symbol,
            "resident_offset": self.resident_offset,
            "target_symbol": self.target_symbol,
            "target_offset": self.target_offset,
            "alignment": self.alignment,
            "points_at_symbol_start": self.points_at_symbol_start,
            "repeats": self.repeats,
            "cluster": self.cluster,
            "window": self.window,
            "whitelisted": self.whitelisted,
            "reason": self.reason,
            "score": self.score,
            "rule": self.rule,
            "tier": self.tier,
        }


#: Tier order for ranking a capped list: the interesting end first.
_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}


def _clusters(rows: Sequence[tuple[int, int]]) -> dict[int, tuple[int, int]]:
    """Map ROM offset to ``(family id, value stride)`` for every stride run.

    A run is `CLUSTER_MINIMUM` or more hits sharing one constant offset
    stride *and* one constant value stride. The value stride is handed back
    rather than filtered on, because its sign of life decides which family a
    run belongs to: a non-zero difference is a packed-field progression, and
    a difference of zero is the same value written down repeatedly, which is
    the repeat family and is labelled as one. Naming both the same thing
    would put one family in two rows of the rule tally.
    """

    found: dict[int, tuple[int, int]] = {}
    index = 0
    count = len(rows)
    identifier = 0
    while index + CLUSTER_MINIMUM - 1 < count:
        offset_stride = rows[index + 1][0] - rows[index][0]
        value_stride = rows[index + 1][1] - rows[index][1]
        last = index + 1
        while (
            last + 1 < count
            and rows[last + 1][0] - rows[last][0] == offset_stride
            and rows[last + 1][1] - rows[last][1] == value_stride
        ):
            last += 1
        if last - index + 1 >= CLUSTER_MINIMUM:
            for position in range(index, last + 1):
                found[rows[position][0]] = (identifier, value_stride)
            identifier += 1
            index = last
            continue
        index += 1
    return found


def scan_regions(
    image: bytes,
    regions: Sequence[Region],
    *,
    window: MovableWindow,
    ldmap: LdMap,
    model: RangeModel,
) -> tuple[Hit, ...]:
    """Read every scannable region's words and rank the in-window ones."""

    raw: list[tuple[int, int, Region]] = []
    for region in regions:
        if not region.scanned:
            continue
        assert region.rom is not None  # from Region.scanned
        for index in range(region.words):
            offset = region.rom + index * 4
            if offset + 4 > len(image):
                break
            value = struct.unpack_from(">I", image, offset)[0]
            if window.contains(value):
                raw.append((offset, value, region))
    raw.sort(key=lambda item: item[0])

    clusters = _clusters([(offset, value) for offset, value, _ in raw])
    repeats: dict[int, int] = {}
    for _, value, _ in raw:
        repeats[value] = repeats.get(value, 0) + 1

    hits: list[Hit] = []
    for offset, value, region in raw:
        vram = region.vram + (offset - (region.rom or 0))
        target = ldmap.symbol_containing(value)
        target_symbol = target[0].name if target else None
        target_offset = target[1] if target else None
        starts = target is not None and target[1] == 0
        resident_symbol: str | None = None
        resident_offset: int | None = None
        if region.kind in ("data", "text"):
            resident = ldmap.symbol_containing(vram)
            if resident is not None:
                resident_symbol, resident_offset = resident[0].name, resident[1]
        name, whitelisted, reason = model.classify_value(value)
        family = clusters.get(offset)
        cluster = family[0] if family is not None and family[1] else None
        repeated = repeats[value]

        score = 0
        if whitelisted:
            rule = "whitelisted"
        elif alignment(value):
            rule = "misaligned"
        elif cluster is not None:
            rule = "progression-cluster"
        elif repeated >= REPEAT_MINIMUM or family is not None:
            rule = "repeated-value"
        elif (value & 0xFFFF) in (0x0000, 0x8000) and not starts:
            rule = "round-constant"
        else:
            rule = SCORED
            score = RESIDENCE_SCORES.get(region.kind, 0) + (
                SYMBOL_START_BONUS if starts else 0
            )
        if rule != SCORED:
            tier = "low"
        elif score >= TIER_THRESHOLDS["high"]:
            tier = "high"
        elif score >= TIER_THRESHOLDS["medium"]:
            tier = "medium"
        else:
            tier = "low"

        hits.append(
            Hit(
                rom=offset,
                vram=vram,
                value=value,
                region=region.output_section,
                residence=region.kind,
                resident_symbol=resident_symbol,
                resident_offset=resident_offset,
                target_symbol=target_symbol,
                target_offset=target_offset,
                alignment=alignment(value),
                points_at_symbol_start=starts,
                repeats=repeated,
                cluster=cluster if rule == "progression-cluster" else None,
                window=name,
                whitelisted=bool(whitelisted),
                reason=reason,
                score=score,
                rule=rule,
                tier=tier,
            )
        )
    return tuple(hits)


# ---------------------------------------------------------------------------
# WB-144: is the pin inventory complete?
# ---------------------------------------------------------------------------

#: ELF-native absolute symbols with no `-T` file and no map assignment behind
#: them at all -- not a pin, not a cascade-script boundary symbol, an
#: object-file-native constant the assembler or objcopy inserted. See the
#: module docstring's WB-144 section for how each entry was measured, not
#: assumed. `(pattern, "exact" | "prefix")`, the same shape
#: `NON_ALLOC_SECTION_FAMILIES` uses.
ELF_BUILTIN_ABSOLUTES: tuple[tuple[str, str], ...] = (
    # The assembler's per-translation-unit C include-guard constant (always
    # value 1): pilotwings64 emits one per object, 24 across its link.
    ("_MACRO_INC_GUARD", "exact"),
    # objcopy's own `_binary_<path>_size` beside the `_start`/`_end` pair
    # `BLOB_OBJECT_RULES` already reads -- a blob's byte count, not a
    # reference. Both live conformance projects carry these, one per blob
    # object (pilotwings64: 6, Banjo-Kazooie: 11).
    ("_binary_", "prefix"),
)


def _is_elf_builtin_absolute(name: str) -> bool:
    """Whether `name` matches a family `ELF_BUILTIN_ABSOLUTES` names."""

    for pattern, kind in ELF_BUILTIN_ABSOLUTES:
        if kind == "exact":
            if name == pattern:
                return True
        elif name.startswith(pattern):
            return True
    return False


#: Per-segment boundary and size symbols a cascade linker script computes for
#: every segment it names -- an assignment in the map exactly like a real
#: pin (``NAME = expression``), but never written by any `-T` file. See the
#: module docstring's WB-144 section for why a name-shape family, not a
#: blanket "is this a map assignment" test, is the only exclusion that does
#: not also hide a genuinely missing pin. Suffix match, not prefix: the
#: segment name itself is the caller's own and carries no fixed shape.
LD_SCRIPT_BOUNDARY_SUFFIXES: tuple[str, ...] = (
    "_ROM_START",
    "_ROM_END",
    "_TEXT_SIZE",
    "_DATA_SIZE",
    "_RODATA_SIZE",
    "_BSS_SIZE",
)


def _is_ld_script_boundary(name: str) -> bool:
    """Whether `name` ends with one of `LD_SCRIPT_BOUNDARY_SUFFIXES`."""

    return any(name.endswith(suffix) for suffix in LD_SCRIPT_BOUNDARY_SUFFIXES)


@dataclass(frozen=True)
class MissingPin:
    """One ELF absolute symbol the supplied pin inventory does not name."""

    name: str
    value: int
    size: int
    """The ELF symbol's own `st_size` -- carried for the same reason
    `ElfSymbol.shadows_definition` reads it, though this check does not: a
    nonzero size here means some object once defined this name too, zero
    means it never did, and either way the inventory is still missing
    whatever `-T` file pinned it."""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "size": self.size}


def find_missing_pin_sources(
    *,
    elf: ElfSymbols,
    ldmap: LdMap,
    window: MovableWindow,
    rom_extent: int,
    pin_names: frozenset[str],
) -> tuple[MissingPin, ...]:
    """WB-144: which ELF absolute symbols does `pin_names` not account for?

    The domain is deliberately narrower than "every absolute symbol in the
    ELF": only ones whose value lands inside `window` or inside `rom_extent`
    (the map's own `ConsistencyCheck.max_placed_extent`) are asked about at
    all -- the same two address families a pin can land in
    (`~decomp_workbench.pins.ARTIFACT_SUSPECT`,
    `~decomp_workbench.pins.ROM_OFFSET`) plus the shadowing check's own VRAM
    range. A hardware register in kseg1 or the cart domain is neither, so an
    omitted ``hardware_regs.ld`` is outside what this specific check can see
    -- true, and worth stating rather than widening the domain to relabel a
    different guess as certainty.

    For each in-domain symbol not named by `pin_names`, `_is_elf_builtin_
    absolute` and `_is_ld_script_boundary` (gated on the map actually
    carrying it as an assignment) are the two measured escape hatches the
    module docstring's WB-144 section explains. Anything left is reported:
    this run's pin inventory does not name it, and the linked ELF proves some
    ``-T`` file the link consumed does.

    Returned in name order -- stable, and grep-able, which matters more here
    than a ranking would: every entry is equally "go find the file".
    """

    found: list[MissingPin] = []
    for name in sorted(elf.names()):
        symbol = elf.symbol(name)
        assert symbol is not None  # from elf.names()
        if not symbol.is_absolute or name in pin_names:
            continue
        if not (window.contains(symbol.value) or 0 <= symbol.value < rom_extent):
            continue
        if _is_elf_builtin_absolute(name):
            continue
        map_symbol = ldmap.symbol(name)
        if (
            map_symbol is not None
            and map_symbol.is_assignment
            and _is_ld_script_boundary(name)
        ):
            continue
        found.append(MissingPin(name=name, value=symbol.value, size=symbol.size))
    return tuple(found)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShiftAudit:
    """One project's static shiftability inventory."""

    map_path: str | None
    image_path: str | None
    image_bytes: int
    regions: tuple[Region, ...]
    window: MovableWindow
    pins: PinCatalogue
    hits: tuple[Hit, ...]
    consistency: ConsistencyCheck
    blobs: BlobPlan = BlobPlan(
        applied=(), source=BLOB_SOURCE_NONE, suggestions=(), excluded=()
    )
    elf_path: str | None = None
    """The linked ELF WB-143b's shadowing check read, or ``None`` when
    ``--elf`` was not passed. Reported either way, because
    ``pins_shadowing=0`` with no ELF means "not asked" and with one means
    "none found"."""
    missing_pins: tuple[MissingPin, ...] = ()
    """WB-144: ELF absolute symbols the supplied pin inventory does not name.
    Always empty when `elf_path` is ``None``, for the same reason
    `pins_shadowing` is: ``pins_missing_sources=0`` with no ELF means "not
    asked", not "complete"."""

    def whitelist_template(self) -> str:
        """The skeleton `--emit-whitelist` writes, from this run's evidence."""

        return whitelist_template_text(
            self.pins,
            window_lo=self.window.lo,
            window_lo_section=self.window.lo_section,
        )

    @property
    def scan_total(self) -> int:
        return len(self.hits)

    @property
    def scan_high(self) -> int:
        return sum(1 for item in self.hits if item.tier == "high")

    @property
    def scan_medium(self) -> int:
        return sum(1 for item in self.hits if item.tier == "medium")

    @property
    def scan_low(self) -> int:
        return sum(1 for item in self.hits if item.tier == "low")

    @property
    def scanned_words(self) -> int:
        return sum(item.words for item in self.regions if item.scanned)

    @property
    def text_words(self) -> int:
        return sum(item.words for item in self.regions if item.kind == "text")

    @property
    def text_regions(self) -> int:
        return sum(1 for item in self.regions if item.kind == "text")

    @property
    def scan_rules(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for item in self.hits:
            found[item.rule] = found.get(item.rule, 0) + 1
        return dict(sorted(found.items()))

    @property
    def scan_by_region(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for item in self.hits:
            found[item.region] = found.get(item.region, 0) + 1
        return dict(sorted(found.items()))

    @property
    def pins_missing_sources(self) -> int:
        """WB-144: ELF absolute symbols no supplied pin file names.

        Always 0 with no `--elf`, the same as `missing_pins` being empty --
        see that field's docstring for why 0 there means "not asked", not
        "complete".
        """

        return len(self.missing_pins)

    def ranked(self) -> tuple[Hit, ...]:
        """Every hit, most confident first, then by where it sits in the ROM."""

        return tuple(
            sorted(
                self.hits,
                key=lambda item: (
                    _TIER_ORDER.get(item.tier, 3),
                    -item.score,
                    item.rom,
                ),
            )
        )

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        shown = self.ranked()[: max(0, limit)]
        payload: dict[str, Any] = {
            "schema": SHIFT_AUDIT_SCHEMA,
            "map": self.map_path,
            "image": self.image_path,
            "elf": self.elf_path,
            "image_bytes": self.image_bytes,
            "region_count": len(self.regions),
            "regions": [item.as_dict() for item in self.regions],
            "scanned_words": self.scanned_words,
            "text_words": self.text_words,
            "text_regions": self.text_regions,
            "scan_total": self.scan_total,
            "scan_high": self.scan_high,
            "scan_medium": self.scan_medium,
            "scan_low": self.scan_low,
            "scan_rules": self.scan_rules,
            "scan_by_region": self.scan_by_region,
            "hits_shown": len(shown),
            "hits": [item.as_dict() for item in shown],
            "rules": [item.as_dict() for item in TIER_RULES],
            "residence_scores": dict(RESIDENCE_SCORES),
            "tier_thresholds": dict(TIER_THRESHOLDS),
            "symbol_start_bonus": SYMBOL_START_BONUS,
        }
        payload.update(self.window.as_dict())
        payload.update(self.consistency.as_dict())
        payload.update(self.blobs.as_dict())
        payload.update(self.pins.as_dict(limit=limit))
        shown_missing = self.missing_pins[: max(0, limit)]
        payload["pins_missing_sources"] = self.pins_missing_sources
        payload["pins_missing_sources_shown"] = len(shown_missing)
        payload["pins_missing_sources_list"] = [
            item.as_dict() for item in shown_missing
        ]
        return payload


def build_shift_audit(
    *,
    ldmap: LdMap,
    image: bytes,
    pins: PinCatalogue,
    model: RangeModel,
    blobs: Iterable[str] = (),
    auto_blobs: bool = False,
    excluded_blobs: Iterable[str] = (),
    header_sections: Iterable[str] = (".header",),
    elf: ElfSymbols | None = None,
    map_path: str | None = None,
    image_path: str | None = None,
    elf_path: str | None = None,
) -> ShiftAudit:
    """Read one project's map, image, and pins into a single inventory.

    WB-140 rule B runs here, always on, right after the region table and
    before the (expensive, whole-image) scan: a map and image that do not
    describe the same link are refused before the report pretends to
    answer a question about them.

    Two derivations bracket that check. `resolve_blobs` runs first, because
    the blob set decides the region table it is checking; and
    :func:`~decomp_workbench.pins.reclassify_rom_offsets` runs after, because
    the ROM bound it needs is the consistency check's own
    ``max_placed_extent``. Handing pins in already classified and answering
    the ROM-offset question here is deliberate: it keeps the caller's read of
    its pin files free of any dependency on the map (a misspelled ``--census``
    key still costs nothing) while making sure no caller can *forget* to ask.
    """

    plan = resolve_blobs(ldmap, blobs=blobs, auto=auto_blobs, excluded=excluded_blobs)
    regions = build_region_table(
        ldmap,
        image_size=len(image),
        blobs=plan.applied,
        header_sections=header_sections,
    )
    consistency = check_map_image_consistency(
        regions, image, map_path=map_path, image_path=image_path
    )
    window = movable_window(regions)
    hits = scan_regions(image, regions, window=window, ldmap=ldmap, model=model)
    classified = reclassify_rom_offsets(
        pins, model=model, rom_extent=consistency.max_placed_extent
    )
    missing_pins: tuple[MissingPin, ...] = ()
    if elf is not None:
        # WB-143b runs last, because its evidence outranks every window-based
        # answer the two passes above could give: "an object already defines
        # this" is a stronger statement about a pin than "it is a kseg0
        # constant", and it comes with a remediation that costs nothing.
        classified = reclassify_shadowing_pins(classified, elf=elf)
        # WB-144 reads the same ELF for a different question: not which
        # supplied pin an object already shadows, but which absolute symbol
        # the link carries that no supplied pin file named at all.
        missing_pins = find_missing_pin_sources(
            elf=elf,
            ldmap=ldmap,
            window=window,
            rom_extent=consistency.max_placed_extent,
            pin_names=frozenset(item.name for item in classified.entries),
        )
    return ShiftAudit(
        map_path=map_path,
        image_path=image_path,
        image_bytes=len(image),
        regions=regions,
        window=window,
        pins=classified,
        hits=hits,
        consistency=consistency,
        blobs=plan,
        elf_path=elf_path if elf_path is not None else (elf.path if elf else None),
        missing_pins=missing_pins,
    )


# ---------------------------------------------------------------------------
# Human rendering
# ---------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render one column-aligned table, numbers right and text left."""

    if not rows:
        return [" ".join(header)]
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


def shift_audit_lines(found: ShiftAudit, *, limit: int) -> list[str]:
    """Render the human report: the same numbers `as_dict` carries."""

    window = found.window
    consistency = found.consistency
    padding = (
        "-" if consistency.padding_bytes is None else f"{consistency.padding_bytes:,}"
    )
    lines = [
        f"shift audit  map={found.map_path or '-'}  image={found.image_path or '-'}  "
        f"elf={found.elf_path or '-'}",
        "",
        f"image_bytes={found.image_bytes:,}  region_count={len(found.regions)}  "
        f"scanned_words={found.scanned_words:,}  "
        f"text_words={found.text_words:,}  text_regions={found.text_regions}",
        f"window_lo=0x{window.lo:08x}  window_hi=0x{window.hi:08x}  "
        f"window_lo_section={window.lo_section}  "
        f"window_hi_section={window.hi_section}",
        # WB-140: the map/image consistency headline. padding_bytes is `-`
        # when the image does not run past the map's own placed extent;
        # regions_unplaced_past_eof is printed here, prominently, rather
        # than left for a reader to notice across a long region table.
        f"max_placed_extent=0x{consistency.max_placed_extent:08x}  "
        f"padding_bytes={padding}  "
        f"regions_unplaced_past_eof={consistency.regions_unplaced_past_eof:,}",
        "",
        "regions",
    ]
    lines.extend(
        _table(
            (
                "output_section",
                "kind",
                "vram",
                "size",
                "rom",
                "rom_source",
                "words",
                "scanned",
            ),
            [
                (
                    item.output_section,
                    item.kind,
                    f"0x{item.vram:08x}",
                    f"0x{item.size:x}",
                    "-" if item.rom is None else f"0x{item.rom:06x}",
                    item.rom_source,
                    f"{item.words:,}",
                    "yes" if item.scanned else "no",
                )
                for item in found.regions
            ],
        )
    )

    plan = found.blobs
    lines.extend(
        (
            "",
            f"blobs={', '.join(plan.applied) if plan.applied else '-'}  "
            f"blob_source={plan.source}"
            + (f"  blobs_excluded={', '.join(plan.excluded)}" if plan.excluded else ""),
        )
    )
    if plan.unadopted:
        # The cold-start line: a caller who has never read this map by hand
        # is told which sections its own inputs say are opaque, and the one
        # flag that adopts them.
        lines.append(
            "suggested_blobs (from .bin.o inputs): "
            f"{', '.join(plan.unadopted)}  -- adopt with `--blobs auto`"
        )

    counts = found.pins.counts
    lines.extend(
        (
            "",
            f"pins_total={len(found.pins.entries):,}  "
            f"pins_derived={counts[DERIVED]:,}  "
            f"pins_authentic={counts[AUTHENTIC_FIXED]:,}  "
            f"pins_artifact={counts[ARTIFACT_SUSPECT]:,}  "
            f"pins_rom_offset={counts[ROM_OFFSET]:,}  "
            f"pins_shadowing="
            + ("off" if found.elf_path is None else f"{counts[SHADOWING_PIN]:,}")
            + f"  pins_unclassified={counts[UNCLASSIFIED]:,}  "
            + "pins_missing_sources="
            + ("off" if found.elf_path is None else f"{found.pins_missing_sources:,}"),
        )
    )
    for source in found.pins.sources:
        lines.append(f"  pin_sources: {source}")
    if found.elf_path is None:
        lines.append(
            "  pins_shadowing is off: pass --elf <linked ELF> to find pins an "
            "object already defines. GNU ld lets a script assignment override "
            "an object's definition silently, and the surviving absolute "
            "symbol keeps the losing definition's size -- which is what makes "
            "the check exact, and free."
        )
        lines.append(
            "  pins_missing_sources is off: pass --elf <linked ELF> to check "
            "whether --pins/--symbol-addrs named every absolute symbol the "
            "link actually carries. An incomplete inventory exits "
            "clean and reports every other number honestly about the pins "
            "it *was* given -- this is the only check that catches a pin "
            "file nobody handed it."
        )
    for classification, heading in (
        (SHADOWING_PIN, "shadowing pins"),
        (ARTIFACT_SUSPECT, "artifact-suspect pins"),
        (ROM_OFFSET, "rom-offset pins"),
    ):
        selected = found.pins.by_classification(classification)
        if not selected:
            continue
        shown_pins = selected[: max(0, limit)]
        lines.extend(
            (
                "",
                f"{heading} ({len(shown_pins)} of {len(selected)}, --limit)",
            )
        )
        lines.extend(
            _table(
                ("name", "value", "window", "source", "line"),
                [
                    (
                        item.name,
                        "-" if item.value is None else f"0x{item.value:08x}",
                        item.window or "-",
                        item.source or "-",
                        str(item.line),
                    )
                    for item in shown_pins
                ],
            )
        )
    if found.pins.by_classification(ROM_OFFSET):
        lines.append(
            "  rom-offset pins address the cartridge image, not memory. "
            "Symbolize them against the linker's own "
            "<segment>_ROM_START/_ROM_END symbols and they follow the layout."
        )
    if found.pins.by_classification(SHADOWING_PIN):
        lines.append(
            "  shadowing pins are already defined by an object in this link: "
            "the script's assignment overrode that definition silently. "
            "Deleting the pin is byte-identical at this layout and the "
            "object's own definition then follows the layout for free."
        )

    if found.missing_pins:
        shown_missing = found.missing_pins[: max(0, limit)]
        lines.extend(
            (
                "",
                "missing pin sources "
                f"({len(shown_missing)} of {len(found.missing_pins)}, --limit)",
            )
        )
        lines.extend(
            _table(
                ("name", "value", "size"),
                [
                    (item.name, f"0x{item.value:08x}", f"{item.size:,}")
                    for item in shown_missing
                ],
            )
        )
        lines.append(
            "  pins the link knows but your inventory does not -- read your "
            "link's -T list; splat's auto files count."
        )

    lines.extend(
        (
            "",
            f"scan_total={found.scan_total:,}  scan_high={found.scan_high:,}  "
            f"scan_medium={found.scan_medium:,}  scan_low={found.scan_low:,}",
            "",
            "scan_rules",
        )
    )
    lines.extend(
        _table(
            ("rule", "count"),
            [(name, f"{count:,}") for name, count in found.scan_rules.items()],
        )
    )
    lines.extend(("", "scan_by_region"))
    lines.extend(
        _table(
            ("region", "count"),
            [(name, f"{count:,}") for name, count in found.scan_by_region.items()],
        )
    )

    shown = found.ranked()[: max(0, limit)]
    lines.extend(("", f"hits ({len(shown)} of {found.scan_total:,}, --limit)"))
    lines.extend(
        _table(
            (
                "rom",
                "value",
                "tier",
                "rule",
                "region",
                "resident_symbol",
                "target_symbol",
            ),
            [
                (
                    f"0x{item.rom:06x}",
                    f"0x{item.value:08x}",
                    item.tier,
                    item.rule,
                    item.region,
                    _named(item.resident_symbol, item.resident_offset),
                    _named(item.target_symbol, item.target_offset),
                )
                for item in shown
            ],
        )
    )

    lines.extend(
        (
            "",
            f"text: {found.text_words:,} words in {found.text_regions} text "
            "region(s) were not scanned. An instruction's address arithmetic "
            "is split across a lui/%lo pair and only a relink resolves it: "
            "`shift rehearse` is the empirical referee for "
            "those, and for which of the words above actually move.",
            "",
            "tiers rank how confidently a word is an address reference, not "
            "how dangerous it is. A linked ROM keeps no relocations, so a "
            "resolved pointer and a typed-in constant are the same four "
            "bytes; only a shifted relink tells them apart.",
        )
    )
    return lines


def _named(symbol: str | None, offset: int | None) -> str:
    if symbol is None:
        return "-"
    return symbol if not offset else f"{symbol}+0x{offset:x}"
