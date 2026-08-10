"""The remediation queue: one ranked, gated list out of every shift report.

The dossier's third honest tension (``shiftability-research/DOSSIER.md`` §6)
is the one this command answers:

    "Findings must be classified by remediation, or the tool is noise. mk64
    proved the failure mode: an unbounded hand-labeling slog. The deliverable
    is not '10,000 address-shaped words' but a ranked queue where every
    finding carries: confidence (empirical > static), evidence, the symbol
    whose range the value lands in, remediation class -- and the verification
    gate to run after the fix."

``shift audit`` and ``shift rehearse`` each produce a report that is true and
neither produces a *plan*. The audit ranks how confidently a word is an
address; the rehearsal says which references a real relink moved; the symbol
census says which names it left behind. A maintainer holding all three still
has to decide what to do first, and the answer is not "read the highest tier"
-- it is "delete the eleven pins an object already defines, because that is
free and it is proven free".

Three properties shape everything here.

**Merged by subject, not concatenated by report.** pilotwings64's
``D_803571F0`` appears in four places: as an artifact-suspect pin in the
audit, as a `shadowing-pin` once the audit reads the ELF, as a
``stale-confirmed`` word in the rehearsal, and as a shadowing finding in the
symbol census. It is one job. `PlanItem` is keyed by ``(remediation,
subject)`` and carries every source that named it, so the queue's length is
the number of things to *do* rather than the number of times they were
mentioned.

**Ranked by what the evidence cost, then by what the fix costs.** Convictions
lead: a finding a real relink demonstrated outranks one a static scan
suspects, which is the DOSSIER's "empirical > static" in one sort key. Then
the free wins (`DELETE_REDUNDANT_PIN` -- S6 proved by ablation that deleting
a shadowing pin leaves the ROM byte-identical), then the mechanical
symbolizations, then the real work, then the parked structural classes. A
queue sorted by severity would put the overlay window at the top, where it
would sit unfixed for a year; sorted this way, a maintainer's first afternoon
closes a third of it.

**Grouped by owning section inside the working classes.** `MIGRATE_SYMBOL`
items sort by the section whose extent contains their value, because a
maintainer fixing eleven pins fixes them one *file* at a time -- pilotwings64's
split into four in ``.kernel`` and eight in ``.app``, which is two sittings,
not twelve.

Every item carries the exact command to run after the fix. That is the
difference between a queue and a list: a `MIGRATE_SYMBOL` item is
match-preserving, so its gate is ``shift config verify`` proving the rebuilt
link is byte- and symbol-identical; a conviction's gate is the same rehearsal
re-run with a ``--census`` predicate one lower than it is today. Nothing here
is a verdict about a project. It is a work order with receipts.

**Rules as data, and what the reports could not carry.** `REMEDIATION_CLASSES`
and `PLAN_RULES` travel inside every report. So does `plan_capped`: a report
whose detail lists were written at ``--limit 40`` cannot describe a fortieth
finding, and a plan built from it says so rather than quietly planning a
third of the work.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "DELETE_REDUNDANT_PIN",
    "DERIVE_PIN",
    "DUAL_SPELLING_RISK",
    "INVESTIGATE",
    "MIGRATE_SYMBOL",
    "PLAN_RULES",
    "REMEDIATION_CLASSES",
    "SHIFT_PLAN_SCHEMA",
    "STRUCTURAL",
    "WHITELIST_CANDIDATE",
    "PlanItem",
    "PlanRule",
    "Remediation",
    "ShiftPlan",
    "build_plan",
    "plan_lines",
    "plan_markdown",
    "read_report",
]

#: JSON identity for the report.
SHIFT_PLAN_SCHEMA = "decomp-workbench-shift-plan-v1"

#: The schemas this command reads. Checked rather than assumed: handing
#: ``shift plan`` a rehearse report as ``--audit`` would otherwise produce an
#: empty plan and no complaint.
AUDIT_SCHEMA = "decomp-workbench-shift-audit-v1"
REHEARSE_SCHEMA = "decomp-workbench-shift-rehearse-v1"

# ---------------------------------------------------------------------------
# The remediation classes
# ---------------------------------------------------------------------------

DELETE_REDUNDANT_PIN = "delete-redundant-pin"
DERIVE_PIN = "derive-pin"
MIGRATE_SYMBOL = "migrate-symbol"
INVESTIGATE = "investigate"
DUAL_SPELLING_RISK = "dual-spelling-risk"
WHITELIST_CANDIDATE = "whitelist-candidate"
STRUCTURAL = "structural"


@dataclass(frozen=True)
class Remediation:
    """One published remediation class: what the fix is, and how it is gated."""

    name: str
    rank: int
    """Queue order within the same conviction band. Lower goes first."""

    kind: str
    """``"match-preserving"`` (the ROM must be byte-identical afterwards),
    ``"conviction"`` (a relink demonstrated the problem and must demonstrate
    the fix), ``"declaration"`` (the fix is a written reason, not a code
    change), or ``"parked"`` (named and set aside)."""

    evidence: str
    gate: str
    """What to run after the fix, in prose. The per-item `PlanItem.gates`
    carry the same thing as concrete command lines built from the reports'
    own paths."""


#: The classes, in queue order, as data for the same reason
#: `shift_audit.TIER_RULES` is: a reader has to be able to see the whole
#: taxonomy, and adding one should be an entry rather than a code path.
#:
#: The order is the DOSSIER's remediation taxonomy (§6, "(a) match-preserving,
#: (b) dual-spelling, (c) structural, (d) authentic") refined by what S6 and
#: S7 actually measured -- the match-preserving band splits into three, and
#: they are not equally cheap. Deleting a pin an object already defines costs
#: nothing and S6 proved it byte-identical by ablation; symbolizing a ROM
#: offset against the linker's own ``<segment>_ROM_START`` is mechanical;
#: giving a kseg0 artifact pin a section home is real decompilation work.
REMEDIATION_CLASSES: tuple[Remediation, ...] = (
    Remediation(
        DELETE_REDUNDANT_PIN,
        0,
        "match-preserving",
        "an object in this link already defines the symbol and the linker "
        "script's assignment silently overrode it. Deleting the assignment "
        "restores a definition that follows the layout for free -- and "
        "changes no bytes at the current layout, proved on "
        "pilotwings64 by ablating all ten and rebuilding to the same sha1",
        "rebuild and prove byte- and symbol-identity (`shift config verify`), "
        "then re-audit and watch pins_shadowing fall by one",
    ),
    Remediation(
        DERIVE_PIN,
        1,
        "match-preserving",
        "the pinned value is one the linker already computes: it lands "
        "exactly on a section's own ROM or VRAM boundary, so the script can "
        "name that boundary instead of writing the number down. Measured "
        "on Banjo-Kazooie -- five of its asset-table pins are, "
        "byte for byte, the AT() load addresses of the five sections they "
        "point at",
        "rebuild and prove byte- and symbol-identity (`shift config verify`), "
        "then re-audit and watch pins_rom_offset fall by one",
    ),
    Remediation(
        MIGRATE_SYMBOL,
        2,
        "match-preserving",
        "a kseg0 address written down for content this link actually places. "
        "The symbol needs a home in the section that owns its address -- a "
        "data or bss migration, which is real decompilation work and is still "
        "match-preserving: the bytes do not move, only who names them",
        "rebuild and prove byte- and symbol-identity (`shift config verify`), "
        "then re-run the rehearsal and watch symbol_stale fall by one",
    ),
    Remediation(
        INVESTIGATE,
        3,
        "conviction",
        "the evidence names a word or a symbol but not a remediation: a "
        "high-confidence address-shaped word the scan ranked, or an unmoved "
        "symbol that lands on no boundary and inside no section. Read the "
        "coordinates before deciding what class it is",
        "re-run the rehearsal at two independent deltas; a finding that "
        "survives both is not a coincidence of one layout",
    ),
    Remediation(
        DUAL_SPELLING_RISK,
        4,
        "conviction",
        "references this instrumentation structurally cannot judge. A MIPS "
        "address is split across a lui/%lo (or lui/ori) pair and never exists "
        "as one word, so a data-side value test cannot see it and a linked "
        "ROM keeps no relocation to read instead. The cost, measured on "
        "pilotwings64: seven RSP-microcode pins and the boot stack pointer "
        "were invisible to stale_confirmed and were found by the symbol side. "
        "Whether the original source spelled one lui/addiu or lui/ori is "
        "itself evidence about what it meant, and is per-compiler behaviour "
        "to calibrate rather than assume",
        "run the symbol-side census (`shift rehearse analyze --base-elf "
        "--shifted-elf`), which does not depend on reading text at all",
    ),
    Remediation(
        WHITELIST_CANDIDATE,
        5,
        "declaration",
        "an address the console fixes rather than this layout: a "
        "memory-mapped register, or a boot global below the movable window's "
        "own floor. The fix is a whitelist line with a reason on it, not a "
        "code change -- and the reason is the whole point, because an address "
        "with no reason is one somebody re-derives later",
        "add the line to your whitelist file and re-audit with --whitelist; "
        "pins_authentic rises by one and the entry stops being a suspect",
    ),
    Remediation(
        STRUCTURAL,
        6,
        "parked",
        "a layout decision rather than a pin: an overlay window several "
        "sections share, or a DMA'd blob whose link-time VMA is a load target "
        "and not a place anything lives. Named and set aside on purpose -- "
        "these are not fixed by editing a symbol file, and a queue that mixed "
        "them in with the free wins would be a queue nobody finishes",
        "none. Parked with a named reason; revisit only with a segment-model "
        "change, and re-derive the queue afterwards",
    ),
)

_BY_NAME: dict[str, Remediation] = {item.name: item for item in REMEDIATION_CLASSES}


@dataclass(frozen=True)
class PlanRule:
    """One published reason a finding entered the queue in the class it did."""

    name: str
    source: str
    remediation: str
    conviction: bool
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "remediation": self.remediation,
            "conviction": self.conviction,
            "evidence": self.evidence,
        }


#: Every path a finding can take from a report into the queue. One entry per
#: (report shape, class) pair, so a reader can answer "why is this here, and
#: why is it *that* class" from the report itself.
PLAN_RULES: tuple[PlanRule, ...] = (
    PlanRule(
        "audit-shadowing-pin",
        "audit-pin",
        DELETE_REDUNDANT_PIN,
        False,
        "`shift audit --elf` classed the pin shadowing-pin: the linked ELF's "
        "symbol of that name is absolute and carries a non-zero size, which "
        "is the overridden object definition's own size",
    ),
    PlanRule(
        "rehearse-shadowing-pin",
        "shadowing",
        DELETE_REDUNDANT_PIN,
        False,
        "the symbol-side census found the same shape across two links: an "
        "absolute symbol with an inherited size that did not move",
    ),
    PlanRule(
        "rehearse-stale-shadowing",
        "rehearse-stale",
        DELETE_REDUNDANT_PIN,
        True,
        "a relink left this word unmoved and the symbol it points at is a "
        "shadowing pin: the strongest form of the finding, because the "
        "remediation is both free and demonstrated",
    ),
    PlanRule(
        "rehearse-stale-confirmed",
        "rehearse-stale",
        INVESTIGATE,
        True,
        "a relink left a high-tier address word exactly where it was: the "
        "strongest available evidence for a hardcoded pointer, with no "
        "remediation class the reports can derive on their own",
    ),
    PlanRule(
        "rehearse-symbol-boundary",
        "rehearse-symbol",
        DERIVE_PIN,
        True,
        "a symbol the relink left behind whose value lands exactly on a "
        "section boundary the linker already computes",
    ),
    PlanRule(
        "rehearse-symbol-resident",
        "rehearse-symbol",
        MIGRATE_SYMBOL,
        True,
        "a symbol the relink left behind whose value lands inside a section "
        "that moved: it names content this link places and needs a home there",
    ),
    PlanRule(
        "rehearse-symbol-residue",
        "rehearse-symbol",
        INVESTIGATE,
        True,
        "a symbol the relink left behind that lands on no boundary and inside "
        "no section: residue, or a window this model does not name",
    ),
    PlanRule(
        "audit-rom-offset-pin",
        "audit-pin",
        DERIVE_PIN,
        False,
        "a raw cartridge offset, which the linker's own "
        "<segment>_ROM_START/_ROM_END symbols already name",
    ),
    PlanRule(
        "audit-artifact-pin",
        "audit-pin",
        MIGRATE_SYMBOL,
        False,
        "a kseg0 constant in a window the project itself owns, pointing "
        "inside a section this link places",
    ),
    PlanRule(
        "audit-whitelist-pin",
        "audit-pin",
        WHITELIST_CANDIDATE,
        False,
        "a hardware-window address, or a kseg0 constant below the movable "
        "window's floor: fixed by the console, not by this layout",
    ),
    PlanRule(
        "audit-scan-hit",
        "audit-scan",
        INVESTIGATE,
        False,
        "a high-tier scan hit: compiled data landing exactly on a symbol's "
        "start. Static confidence only -- a linked ROM keeps no relocations, "
        "so only a relink convicts",
    ),
    PlanRule(
        "audit-text-coverage",
        "audit-scan",
        DUAL_SPELLING_RISK,
        False,
        "the audit counted text words it deliberately did not scan; every "
        "reference consumed only from a lui/%lo pair lives in them",
    ),
    PlanRule(
        "rehearse-unattributed",
        "rehearse-stale",
        DUAL_SPELLING_RISK,
        True,
        "the word census found stale candidates the static scan never saw, "
        "because they sit in a region it does not read",
    ),
    PlanRule(
        "audit-shared-vram",
        "audit-scan",
        STRUCTURAL,
        False,
        "two or more output sections share one VMA. Extents alone cannot tell "
        "a nested placement from an N64 overlay group, and either way the "
        "window is a layout decision",
    ),
    PlanRule(
        "audit-blob-segment",
        "audit-scan",
        STRUCTURAL,
        False,
        "sections treated as opaque bytes: DMA'd from cart, so their "
        "link-time VMA is a load target rather than a place code lives",
    ),
)

_RULES_BY_NAME: dict[str, PlanRule] = {item.name: item for item in PLAN_RULES}


# ---------------------------------------------------------------------------
# Reading the reports
# ---------------------------------------------------------------------------


def read_report(path: str | Path, *, expected: str) -> dict[str, Any]:
    """Read one JSON report and refuse anything that is not `expected`.

    A shift report is self-identifying, and checking that identity is what
    turns "``--audit`` was handed the rehearsal by mistake" from an empty
    plan with no complaint into one line naming both schemas.
    """

    text = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not JSON: {error}") from None
    if not isinstance(payload, dict):
        raise ValueError(
            f"{path} is a JSON {type(payload).__name__}, not a report object"
        )
    schema = payload.get("schema")
    if schema != expected:
        raise ValueError(
            f"{path} carries schema {schema!r}, not {expected!r}: pass the "
            "report the matching command wrote with --json"
        )
    return payload


def _analyses(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every analysis inside one rehearse report, whichever mode it is."""

    if report.get("mode") == "orchestrate":
        return [item for item in report.get("analyses", []) if isinstance(item, dict)]
    return [report]


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


@dataclass
class PlanItem:
    """One thing to do, with every report that asked for it."""

    subject: str
    """What the item is about: a symbol name, a ROM coordinate, or a section.
    Half of the merge key -- one subject in one class is one job."""

    remediation: str
    title: str
    sources: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    _evidence: dict[str, str] = field(default_factory=dict)
    """One line per routing rule, first writer wins. Keyed rather than
    appended because two deltas of the same rehearsal say the same sentence
    about the same subject with one number changed, and a queue that printed
    both would grow with the number of deltas rather than with the work."""

    _gates: dict[str, str] = field(default_factory=dict)
    """One command per gate kind (identity, audit census, rehearse census),
    on the same terms and for the same reason."""

    deltas: list[int] = field(default_factory=list)
    """Every delta whose rehearsal contributed to this item. Two deltas
    agreeing is itself evidence -- a partially symbolized reference can
    encode correctly at one shift by coincidence and cannot at two."""

    conviction: bool = False
    exemplar: bool = False
    """Whether this item's value is *exactly* an address the linker already
    computes. The strongest form of a `DERIVE_PIN`, and it leads its class:
    S7 measured five of Banjo-Kazooie's asset-table pins as byte-for-byte
    equal to the ``AT()`` load addresses of the sections they point at, and
    those five are the ones to fix first because the identity is arithmetic
    rather than argued."""

    section: str | None = None
    """The section whose extent owns this item's address, when there is one.
    The locality key inside `MIGRATE_SYMBOL`: a maintainer fixes one file at
    a time, so the queue hands them one file at a time."""

    value: int | None = None

    @property
    def rank(self) -> Remediation:
        return _BY_NAME[self.remediation]

    def order(self) -> tuple[Any, ...]:
        """The queue's sort key, most-earned first.

        Convictions before suspicions (the DOSSIER's "empirical > static"),
        then the class order, then the exemplars inside a class, then section
        locality, then the address -- so a run over the same reports always
        produces the same queue.
        """

        return (
            0 if self.conviction else 1,
            self.rank.rank,
            0 if self.exemplar else 1,
            self.section or "~",
            self.value if self.value is not None else 1 << 32,
            self.subject,
        )

    @property
    def evidence(self) -> tuple[str, ...]:
        """One line per rule, plus the cross-delta line when there is one."""

        lines = list(self._evidence.values())
        if len(self.deltas) > 1:
            lines.append(
                "confirmed at deltas "
                + ", ".join(f"0x{item:x}" for item in self.deltas)
                + " -- a reference can encode correctly at one shift by "
                "coincidence and cannot at two"
            )
        return tuple(lines)

    @property
    def gates(self) -> tuple[str, ...]:
        return tuple(self._gates.values())

    def merge(
        self,
        *,
        source: str,
        rule: str,
        evidence: str,
        conviction: bool,
        gates: Mapping[str, str] = {},
        section: str | None = None,
        value: int | None = None,
        delta: int | None = None,
        exemplar: bool = False,
    ) -> None:
        """Fold one more report's mention of this subject into the item."""

        if source not in self.sources:
            self.sources.append(source)
        if rule not in self.rules:
            self.rules.append(rule)
        self._evidence.setdefault(rule, evidence)
        for kind, command in gates.items():
            self._gates.setdefault(kind, command)
        if delta is not None and delta not in self.deltas:
            self.deltas.append(delta)
        self.conviction = self.conviction or conviction
        self.exemplar = self.exemplar or exemplar
        if self.section is None:
            self.section = section
        if self.value is None:
            self.value = value

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "title": self.title,
            "remediation": self.remediation,
            "remediation_kind": self.rank.kind,
            "conviction": self.conviction,
            "exemplar": self.exemplar,
            "sources": list(self.sources),
            # `matched_rules`, not `rules`: the audit's report already uses
            # that key for its suppressor table, and one spelling cannot mean
            # two tables in one registry.
            "matched_rules": list(self.rules),
            "evidence": list(self.evidence),
            "gates": list(self.gates),
            "deltas": [f"0x{item:x}" for item in self.deltas],
            "section": self.section,
            "value": self.value,
        }


class _Queue:
    """Accumulates merged items, keyed by ``(remediation, subject)``."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], PlanItem] = {}

    def add(
        self,
        *,
        subject: str,
        remediation: str,
        title: str,
        rule: str,
        evidence: str,
        gates: Mapping[str, str] = {},
        section: str | None = None,
        value: int | None = None,
        delta: int | None = None,
        exemplar: bool = False,
    ) -> PlanItem:
        published = _RULES_BY_NAME[rule]
        key = (remediation, subject)
        item = self._items.get(key)
        if item is None:
            item = PlanItem(subject=subject, remediation=remediation, title=title)
            self._items[key] = item
        item.merge(
            source=published.source,
            rule=rule,
            evidence=evidence,
            conviction=published.conviction,
            gates=gates,
            section=section,
            value=value,
            delta=delta,
            exemplar=exemplar,
        )
        return item

    def ranked(self) -> tuple[PlanItem, ...]:
        return tuple(sorted(self._items.values(), key=lambda item: item.order()))


# ---------------------------------------------------------------------------
# Gate commands
# ---------------------------------------------------------------------------


def _quote(path: str | None) -> str:
    return path if path else "<path>"


def _identity_gate(audit: Mapping[str, Any] | None) -> str:
    """The match-preserving gate: rebuild, then prove nothing moved."""

    if audit is None:
        return (
            "decomp-workbench shift config verify --pinned-map <before>.map "
            "--candidate-map <after>.map --pinned-image <before>.z64 "
            "--candidate-image <after>.z64"
        )
    return (
        "decomp-workbench shift config verify "
        f"--pinned-map {_quote(audit.get('map'))} "
        "--candidate-map <rebuilt>.map "
        f"--pinned-image {_quote(audit.get('image'))} "
        "--candidate-image <rebuilt>.z64"
    )


def _audit_gate(audit: Mapping[str, Any] | None, *, census: str) -> str:
    """Re-run the same audit and watch one census key fall."""

    if audit is None:
        return f"decomp-workbench shift audit ... --census {census}"
    parts = [
        "decomp-workbench shift audit",
        f"--map {_quote(audit.get('map'))}",
        f"--image {_quote(audit.get('image'))}",
    ]
    if audit.get("elf"):
        parts.append(f"--elf {audit['elf']}")
    for source in audit.get("pin_sources", []):
        parts.append(f"--pins {source}")
    for blob in audit.get("blobs", []):
        parts.append(f"--blob {blob}")
    parts.append(f"--census {census}")
    return " ".join(parts)


def _rehearse_gate(analysis: Mapping[str, Any] | None, *, census: str) -> str:
    """Re-run the same rehearsal and watch one census key fall."""

    if analysis is None:
        return f"decomp-workbench shift rehearse analyze ... --census {census}"
    parts = [
        "decomp-workbench shift rehearse analyze",
        f"--base-map {_quote(analysis.get('base_map'))}",
        f"--base-image {_quote(analysis.get('base_image'))}",
        f"--shifted-map {_quote(analysis.get('shifted_map'))}",
        f"--shifted-image {_quote(analysis.get('shifted_image'))}",
        f"--delta 0x{int(analysis.get('delta', 0)):x}",
    ]
    if analysis.get("base_elf"):
        parts.append(f"--base-elf {analysis['base_elf']}")
        parts.append(f"--shifted-elf {analysis.get('shifted_elf')}")
    parts.append(f"--census {census}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Boundary matching: the S7 rom-offset <-> AT() identity, generalized
# ---------------------------------------------------------------------------


#: Boundary kinds, in the order one address's description prefers them. A
#: *start* outranks an *end* because a pin holding a segment's first address
#: is naming that segment: ``D_5E90 = 0x5E90`` is Banjo-Kazooie's asset-table
#: entry for ``.assets``, and calling it "the ROM end of ``.crc``" -- equally
#: true, since the two abut -- would send a maintainer to the wrong file.
#: ROM outranks VRAM only as a tie-break; the two populations do not overlap
#: in practice, since a ROM offset is below every run-time RAM window.
_EDGE_ORDER: tuple[str, ...] = ("ROM start", "VRAM start", "ROM end", "VRAM end")

_EDGE_SUFFIX: dict[str, str] = {
    "ROM start": "_ROM_START",
    "ROM end": "_ROM_END",
    "VRAM start": "_VRAM",
    "VRAM end": "_VRAM_END",
}


@dataclass(frozen=True)
class _Boundary:
    """One address the linker itself computes, and every edge that meets there.

    An address is rarely one boundary. pilotwings64's ``0x803805e0`` is the
    VRAM start of ``.filetable`` *and* the VRAM end of ``.app_bss`` -- two
    symbols the linker already places, either of which would carry the pin
    that currently writes the number down. All of them are reported, in
    preference order, because a maintainer choosing which symbol to write
    needs the choice rather than this command's guess at it.
    """

    edges: tuple[tuple[str, tuple[str, ...]], ...]
    """``(edge, sections)`` pairs in `_EDGE_ORDER`, strongest first."""

    @property
    def edge(self) -> str:
        return self.edges[0][0]

    @property
    def sections(self) -> tuple[str, ...]:
        return self.edges[0][1]

    @property
    def section(self) -> str:
        """The first section at the strongest edge, for grouping by locality."""

        return self.sections[0]

    def _phrase(self, edge: str, sections: tuple[str, ...]) -> str:
        # Every section at an edge is named, not just the first. An N64
        # overlay group puts fourteen of them on one VRAM (Banjo-Kazooie's
        # 0x803863f0), and a description that picked one would be an
        # arbitrary answer dressed as a specific one.
        shared = f" ({len(sections)} sections share it)" if len(sections) > 1 else ""
        return f"the {edge} of {', '.join(sections)}{shared}"

    def describe(self, value: int) -> str:
        primary = self._phrase(*self.edges[0])
        alternates = "".join(
            f"; and {self._phrase(edge, sections)}"
            for edge, sections in self.edges[1:]
        )
        return (
            f"0x{value:08x} is exactly {primary}{alternates} -- an address this "
            "link already computes, so the linker script can name that boundary "
            f"(splat spells it {_boundary_symbol(self)}) instead of writing the "
            "number down"
        )


def _boundary_symbol(boundary: _Boundary) -> str:
    """The shape of the symbol a splat script places at one boundary.

    A *shape*, deliberately, not a claim: this reads a report, not a linker
    script, and cannot know how a given project spells its own segment
    symbols. Naming the section and the edge is evidence; naming the exact
    symbol would be a guess dressed as one.
    """

    stem = boundary.section.lstrip(".")
    return f"<{stem}>{_EDGE_SUFFIX[boundary.edge]}"


def _boundaries(regions: Iterable[Mapping[str, Any]]) -> dict[int, _Boundary]:
    """Index every ROM and VRAM boundary the map's regions establish.

    One entry per address, carrying every edge kind that meets there in
    `_EDGE_ORDER`, and every section that has that edge at it in report order
    -- so the answer never depends on which section the map printed first,
    and an address that is two boundaries at once reads as two.
    """

    edges: dict[tuple[int, str], list[str]] = {}

    def note(address: int, edge: str, section: str) -> None:
        names = edges.setdefault((address, edge), [])
        if section not in names:
            names.append(section)

    for region in regions:
        section = str(region.get("output_section", "?"))
        size = int(region.get("size", 0) or 0)
        rom = region.get("rom")
        if isinstance(rom, int):
            note(rom, "ROM start", section)
            note(rom + size, "ROM end", section)
        vram = region.get("vram")
        if isinstance(vram, int):
            note(vram, "VRAM start", section)
            note(vram + size, "VRAM end", section)

    collected: dict[int, list[tuple[str, tuple[str, ...]]]] = {}
    for address, edge in sorted(
        edges, key=lambda key: (key[0], _EDGE_ORDER.index(key[1]))
    ):
        collected.setdefault(address, []).append(
            (edge, tuple(edges[(address, edge)]))
        )
    return {
        address: _Boundary(tuple(rows)) for address, rows in collected.items()
    }


def _owning_section(
    regions: Sequence[Mapping[str, Any]], value: int
) -> str | None:
    """The smallest region whose VRAM extent contains ``value``."""

    candidates = [
        region
        for region in regions
        if isinstance(region.get("vram"), int)
        and int(region["vram"])
        <= value
        < int(region["vram"]) + int(region.get("size", 0) or 0)
    ]
    if not candidates:
        return None
    return str(
        min(candidates, key=lambda item: int(item.get("size", 0) or 0)).get(
            "output_section"
        )
    )


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShiftPlan:
    """One ranked, gated remediation queue and where every item came from."""

    audit_path: str | None
    rehearse_paths: tuple[str, ...]
    deltas: tuple[int, ...]
    items: tuple[PlanItem, ...]
    capped: tuple[str, ...]
    """Report lists whose ``--limit`` cut them short, named. A plan built from
    a capped report describes part of the work and has to say so."""

    def by_class(self) -> dict[str, int]:
        found = {item.name: 0 for item in REMEDIATION_CLASSES}
        for item in self.items:
            found[item.remediation] = found.get(item.remediation, 0) + 1
        return found

    def by_source(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for item in self.items:
            for source in item.sources:
                found[source] = found.get(source, 0) + 1
        return dict(sorted(found.items()))

    def sections(self) -> dict[str, int]:
        """How many match-preserving items each owning section carries.

        Restricted to the match-preserving band on purpose: this key exists
        to answer "which file do I open next", and the classes whose fix is a
        written reason (`WHITELIST_CANDIDATE`), a triage (`INVESTIGATE`) or
        nothing at all (`STRUCTURAL`) are not fixed by opening a file.
        """

        found: dict[str, int] = {}
        for item in self.items:
            if item.section is None or item.rank.kind != "match-preserving":
                continue
            found[item.section] = found.get(item.section, 0) + 1
        return dict(sorted(found.items()))

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def convictions(self) -> int:
        return sum(1 for item in self.items if item.conviction)

    @property
    def free_wins(self) -> int:
        return sum(
            1 for item in self.items if item.remediation == DELETE_REDUNDANT_PIN
        )

    @property
    def structural(self) -> int:
        return sum(1 for item in self.items if item.remediation == STRUCTURAL)

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        cap = max(0, limit)
        shown = self.items[:cap]
        counts = self.by_class()
        return {
            "schema": SHIFT_PLAN_SCHEMA,
            "audit_report": self.audit_path,
            "rehearse_reports": list(self.rehearse_paths),
            "deltas": [f"0x{item:x}" for item in self.deltas],
            "plan_total": self.total,
            "plan_convictions": self.convictions,
            "plan_free_wins": self.free_wins,
            "plan_derive_pin": counts[DERIVE_PIN],
            "plan_migrate_symbol": counts[MIGRATE_SYMBOL],
            "plan_investigate": counts[INVESTIGATE],
            "plan_dual_spelling": counts[DUAL_SPELLING_RISK],
            "plan_whitelist": counts[WHITELIST_CANDIDATE],
            "plan_structural": self.structural,
            "plan_by_class": counts,
            "plan_by_source": self.by_source(),
            "plan_sections": self.sections(),
            "plan_capped": list(self.capped),
            "plan_shown": len(shown),
            "plan_items": [item.as_dict() for item in shown],
            "remediation_classes": [
                {
                    "name": item.name,
                    "rank": item.rank,
                    "kind": item.kind,
                    "evidence": item.evidence,
                    "gate": item.gate,
                }
                for item in REMEDIATION_CLASSES
            ],
            "plan_rules": [item.as_dict() for item in PLAN_RULES],
            "limit": cap,
        }


def _plan_audit(queue: _Queue, audit: Mapping[str, Any], capped: list[str]) -> None:
    """Fold one `shift audit` report into the queue."""

    regions = [item for item in audit.get("regions", []) if isinstance(item, dict)]
    boundaries = _boundaries(regions)
    window_lo = int(audit.get("window_lo", 0) or 0)

    for pin in audit.get("pins", []):
        if not isinstance(pin, dict):
            continue
        name = str(pin.get("name", "?"))
        value = pin.get("value")
        classification = pin.get("classification")
        section = _owning_section(regions, value) if isinstance(value, int) else None
        if classification == "shadowing-pin":
            queue.add(
                subject=name,
                remediation=DELETE_REDUNDANT_PIN,
                title=f"delete the pin {name}",
                rule="audit-shadowing-pin",
                evidence=(
                    f"{name} = 0x{value:08x} in {pin.get('source')}:"
                    f"{pin.get('line')} -- an object in this link already "
                    "defines it (the surviving absolute symbol carries that "
                    "definition's own size)"
                    if isinstance(value, int)
                    else f"{name}: an object in this link already defines it"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "audit": _audit_gate(
                        audit, census="pins_shadowing=<one less>"
                    ),
                },
                section=section,
                value=value if isinstance(value, int) else None,
            )
            continue
        if classification == "rom-offset":
            boundary = boundaries.get(value) if isinstance(value, int) else None
            queue.add(
                subject=name,
                remediation=DERIVE_PIN,
                title=f"symbolize the ROM offset {name}",
                rule="audit-rom-offset-pin",
                evidence=(
                    boundary.describe(value)
                    if boundary is not None and isinstance(value, int)
                    else f"{name} = 0x{value:08x} is a raw cartridge offset, "
                    "below every run-time RAM window and inside the extent "
                    "this map places"
                    if isinstance(value, int)
                    else f"{name} is a raw cartridge offset"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "audit": _audit_gate(
                        audit, census="pins_rom_offset=<one less>"
                    ),
                },
                section=boundary.section if boundary is not None else section,
                value=value if isinstance(value, int) else None,
                exemplar=boundary is not None,
            )
            continue
        if classification == "artifact-suspect":
            if pin.get("window") in ("kseg1", "cart") or (
                isinstance(value, int) and value < window_lo
            ):
                queue.add(
                    subject=name,
                    remediation=WHITELIST_CANDIDATE,
                    title=f"declare {name} authentic, with a reason",
                    rule="audit-whitelist-pin",
                    evidence=(
                        f"{name} = 0x{value:08x} sits in the "
                        f"{pin.get('window')} window"
                        if isinstance(value, int)
                        else f"{name} sits in the {pin.get('window')} window"
                    ),
                    gates={
                        "audit": _audit_gate(
                            audit, census="pins_authentic=<one more>"
                        )
                    },
                    value=value if isinstance(value, int) else None,
                )
                continue
            boundary = boundaries.get(value) if isinstance(value, int) else None
            if boundary is not None and isinstance(value, int):
                queue.add(
                    subject=name,
                    remediation=DERIVE_PIN,
                    title=f"name the boundary {name} points at",
                    rule="audit-rom-offset-pin",
                    evidence=boundary.describe(value),
                    gates={
                        "identity": _identity_gate(audit),
                        "audit": _audit_gate(
                            audit, census="pins_artifact=<one less>"
                        ),
                    },
                    section=boundary.section,
                    value=value,
                    exemplar=True,
                )
                continue
            queue.add(
                subject=name,
                remediation=MIGRATE_SYMBOL,
                title=f"give {name} a home in {section or 'its own section'}",
                rule="audit-artifact-pin",
                evidence=(
                    f"{name} = 0x{value:08x} is a kseg0 constant"
                    + (f" inside {section}" if section else ", inside no section")
                    if isinstance(value, int)
                    else f"{name} is a kseg0 constant"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "audit": _audit_gate(
                        audit, census="pins_artifact=<one less>"
                    ),
                },
                section=section,
                value=value if isinstance(value, int) else None,
            )
            continue
        if classification == "authentic-fixed":
            continue

    if int(audit.get("pins_shown", 0) or 0) < int(audit.get("pins_total", 0) or 0):
        capped.append(
            f"pins ({audit.get('pins_shown')} of {audit.get('pins_total')} "
            "carried by the audit report)"
        )

    for hit in audit.get("hits", []):
        if not isinstance(hit, dict) or hit.get("tier") != "high":
            continue
        rom = int(hit.get("rom", 0) or 0)
        target = hit.get("target_symbol")
        queue.add(
            subject=f"rom:0x{rom:06x}",
            remediation=INVESTIGATE,
            title=(
                f"triage the word at ROM 0x{rom:06x}"
                + (f" -> {target}" if target else "")
            ),
            rule="audit-scan-hit",
            evidence=(
                f"0x{int(hit.get('value', 0)):08x} in {hit.get('region')} at "
                f"{hit.get('resident_symbol') or 'no named symbol'}, landing on "
                f"{target or 'no symbol start'} -- ranked high by the static "
                "scan, which cannot say whether a relink moves it"
            ),
            gates={
                "rehearse": (
                    "decomp-workbench shift rehearse analyze ... "
                    "--census stale_confirmed=0"
                )
            },
            section=str(hit.get("region")) if hit.get("region") else None,
            value=rom,
        )

    if int(audit.get("hits_shown", 0) or 0) < int(audit.get("scan_high", 0) or 0):
        capped.append(
            f"scan hits ({audit.get('hits_shown')} rows carried, "
            f"scan_high={audit.get('scan_high')})"
        )

    text_words = int(audit.get("text_words", 0) or 0)
    if text_words:
        queue.add(
            subject="text-regions",
            remediation=DUAL_SPELLING_RISK,
            title="the text side is not covered by any value test",
            rule="audit-text-coverage",
            evidence=(
                f"{text_words:,} instruction words in "
                f"{audit.get('text_regions')} text region(s) were counted and "
                "not scanned: a MIPS address is split across a lui/%lo pair "
                "and never exists as one word"
            ),
            gates={
                "rehearse": (
                    "decomp-workbench shift rehearse analyze "
                    "--base-elf <base>.elf --shifted-elf <shifted>.elf ... "
                    "--census symbol_stale=0"
                )
            },
        )

    # Two sections sharing a start address is only interesting when both
    # really occupy it. A zero-size region (an empty `.bss` output section)
    # shares a start with whatever follows it by arithmetic rather than by
    # design -- pilotwings64's `.entry_bss` and `.kernel` both begin at
    # 0x802000a0 for exactly that reason -- and a `non-alloc` region
    # (`.mdebug`, printed at VMA 0) is never in the running image at all.
    # Neither is a window anything is loaded into.
    shared: dict[int, list[str]] = {}
    for region in regions:
        vram = region.get("vram")
        name = str(region.get("output_section", "?"))
        if region.get("kind") == "non-alloc" or not int(region.get("size", 0) or 0):
            continue
        if isinstance(vram, int):
            names = shared.setdefault(vram, [])
            if name not in names:
                names.append(name)
    for vram, names in sorted(shared.items()):
        if len(names) < 2:
            continue
        queue.add(
            subject=f"vram:0x{vram:08x}",
            remediation=STRUCTURAL,
            title=f"{len(names)} output sections share VRAM 0x{vram:08x}",
            rule="audit-shared-vram",
            evidence=(
                f"{', '.join(names)} all start at 0x{vram:08x}. Extents alone "
                "cannot tell a nested placement from an N64 overlay group of "
                "mutually exclusive alternatives, and either shape is a "
                "layout decision rather than a pin"
            ),
            value=vram,
        )

    blobs = [str(item) for item in audit.get("blobs", [])]
    if blobs:
        queue.add(
            subject="blob-segments",
            remediation=STRUCTURAL,
            title=f"{len(blobs)} section(s) are opaque blobs",
            rule="audit-blob-segment",
            evidence=(
                f"{', '.join(blobs)} are treated as opaque bytes: DMA'd from "
                "cart, so their link-time VMA is a load target and not a place "
                "anything lives. Their contents are not attributable to "
                "symbols by any static means this command has"
            ),
        )


def _plan_rehearse(
    queue: _Queue,
    analysis: Mapping[str, Any],
    audit: Mapping[str, Any] | None,
    capped: list[str],
) -> None:
    """Fold one rehearsal analysis into the queue."""

    regions = [item for item in analysis.get("regions", []) if isinstance(item, dict)]
    if not regions and audit is not None:
        regions = [
            item for item in audit.get("regions", []) if isinstance(item, dict)
        ]
    boundaries = _boundaries(regions)
    shadowing = {
        str(item.get("name"))
        for item in analysis.get("symbol_findings", [])
        if isinstance(item, dict) and item.get("classification") == "shadowing-pin"
    }
    delta = int(analysis.get("delta", 0) or 0)

    for row in analysis.get("stale", []):
        if not isinstance(row, dict) or row.get("outcome") != "stale-confirmed":
            continue
        rom = int(row.get("rom", 0) or 0)
        target = row.get("target_symbol")
        evidence = (
            f"ROM 0x{rom:06x} holds 0x{int(row.get('value', 0)):08x} in "
            f"{row.get('region')} and a 0x{delta:x} relink did not move it; it "
            f"points at {target or 'no named symbol'}"
        )
        if target and target in shadowing:
            queue.add(
                subject=str(target),
                remediation=DELETE_REDUNDANT_PIN,
                title=f"delete the pin {target}",
                rule="rehearse-stale-shadowing",
                evidence=evidence,
                gates={
                    "identity": _identity_gate(audit),
                    "rehearse": _rehearse_gate(
                        analysis, census="stale_confirmed=<one less>"
                    ),
                },
                section=str(row.get("region")) if row.get("region") else None,
                value=int(row.get("value", 0) or 0),
                delta=delta,
            )
            continue
        queue.add(
            subject=f"rom:0x{rom:06x}",
            remediation=INVESTIGATE,
            title=f"convicted word at ROM 0x{rom:06x}",
            rule="rehearse-stale-confirmed",
            evidence=evidence,
            gates={
                "rehearse": _rehearse_gate(
                    analysis, census="stale_confirmed=<one less>"
                )
            },
            section=str(row.get("region")) if row.get("region") else None,
            value=rom,
            delta=delta,
        )

    if int(analysis.get("stale_shown", 0) or 0) < int(
        analysis.get("stale_confirmed", 0) or 0
    ):
        capped.append(
            f"stale rows ({analysis.get('stale_shown')} carried, "
            f"stale_confirmed={analysis.get('stale_confirmed')})"
        )

    for row in analysis.get("symbol_findings", []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "?"))
        value = int(row.get("value", 0) or 0)
        owner = row.get("owning_section")
        if row.get("classification") == "shadowing-pin":
            queue.add(
                subject=name,
                remediation=DELETE_REDUNDANT_PIN,
                title=f"delete the pin {name}",
                rule="rehearse-shadowing-pin",
                evidence=(
                    f"{name} = 0x{value:08x} is absolute and carries a "
                    f"{row.get('size')}-byte size inherited from the object "
                    f"definition it overrode; a 0x{delta:x} relink left it "
                    f"behind while {owner or 'its content'} moved"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "rehearse": _rehearse_gate(
                        analysis, census="shadowing_pins=<one less>"
                    ),
                },
                section=str(owner) if owner else None,
                value=value,
                delta=delta,
            )
            continue
        boundary = boundaries.get(value)
        if boundary is not None:
            queue.add(
                subject=name,
                remediation=DERIVE_PIN,
                title=f"name the boundary {name} points at",
                rule="rehearse-symbol-boundary",
                evidence=(
                    boundary.describe(value)
                    + f"; a 0x{delta:x} relink moved that boundary and left "
                    f"{name} behind"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "rehearse": _rehearse_gate(
                        analysis, census="symbol_stale=<one less>"
                    ),
                },
                section=boundary.section,
                value=value,
                delta=delta,
                exemplar=True,
            )
            continue
        if owner:
            queue.add(
                subject=name,
                remediation=MIGRATE_SYMBOL,
                title=f"give {name} a home in {owner}",
                rule="rehearse-symbol-resident",
                evidence=(
                    f"{name} = 0x{value:08x} lands inside {owner}, which a "
                    f"0x{delta:x} relink moved by 0x{delta:x} while {name} "
                    "stayed put"
                ),
                gates={
                    "identity": _identity_gate(audit),
                    "rehearse": _rehearse_gate(
                        analysis, census="symbol_stale=<one less>"
                    ),
                },
                section=str(owner),
                value=value,
                delta=delta,
            )
            continue
        queue.add(
            subject=name,
            remediation=INVESTIGATE,
            title=f"triage the unmoved symbol {name}",
            rule="rehearse-symbol-residue",
            evidence=(
                f"{name} = 0x{value:08x} did not move under a 0x{delta:x} "
                "relink and lands on no section boundary and inside no section"
            ),
            gates={
                "rehearse": _rehearse_gate(
                    analysis, census="symbol_stale=<one less>"
                )
            },
            value=value,
            delta=delta,
        )

    if int(analysis.get("symbol_findings_shown", 0) or 0) < (
        int(analysis.get("symbol_stale", 0) or 0)
        + int(analysis.get("shadowing_pins", 0) or 0)
    ):
        capped.append(
            f"symbol findings ({analysis.get('symbol_findings_shown')} carried, "
            f"symbol_stale={analysis.get('symbol_stale')} "
            f"shadowing_pins={analysis.get('shadowing_pins')})"
        )

    unattributed = int(analysis.get("stale_unattributed", 0) or 0)
    if unattributed:
        queue.add(
            subject="stale-unattributed",
            remediation=DUAL_SPELLING_RISK,
            title=f"{unattributed:,} stale candidates the scan never saw",
            rule="rehearse-unattributed",
            evidence=(
                f"the word census counted {unattributed:,} unmoved "
                "address-shaped words the static scan never read, because "
                "they sit in a region it does not scan"
            ),
            gates={"rehearse": _rehearse_gate(analysis, census="symbol_stale=0")},
            delta=delta,
        )

    if not analysis.get("symbol_census", False):
        capped.append(
            "symbol census (off in this rehearse report -- re-run with "
            "--base-elf/--shifted-elf)"
        )


def build_plan(
    *,
    audit: Mapping[str, Any] | None = None,
    rehearsals: Sequence[Mapping[str, Any]] = (),
    audit_path: str | None = None,
    rehearse_paths: Sequence[str] = (),
) -> ShiftPlan:
    """Merge every report into one ranked queue.

    The audit is folded first so that a pin the static half already named
    owns its subject before a rehearsal adds the empirical evidence to it --
    which is what lets ``D_803571F0`` arrive as one item carrying four
    sources instead of four items carrying one each.
    """

    queue = _Queue()
    capped: list[str] = []
    if audit is not None:
        _plan_audit(queue, audit, capped)
    analyses: list[Mapping[str, Any]] = []
    for report in rehearsals:
        analyses.extend(_analyses(report))
    for analysis in analyses:
        _plan_rehearse(queue, analysis, audit, capped)
    return ShiftPlan(
        audit_path=audit_path,
        rehearse_paths=tuple(rehearse_paths),
        deltas=tuple(int(item.get("delta", 0) or 0) for item in analyses),
        items=queue.ranked(),
        capped=tuple(dict.fromkeys(capped)),
    )


# ---------------------------------------------------------------------------
# Human rendering
# ---------------------------------------------------------------------------

#: The loop every work order states at the top, because a checklist with no
#: loop around it is a list of chores. Same three beats S6 ran on
#: pilotwings64: change the configuration, prove the ROM did not move, then
#: re-run the referee and watch the number fall.
CAMPAIGN_LOOP = (
    "fix one item -> rebuild -> prove the ROM is byte- and symbol-identical "
    "(`shift config verify`) -> re-run the instrument that found it and watch "
    "its census key fall by one. A fix that cannot pass its own gate is not a "
    "fix; a fix with no gate is a hope."
)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render one column-aligned table, the shape the shift family prints."""

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


def plan_lines(found: ShiftPlan, *, limit: int) -> list[str]:
    """Render the human report: the same numbers `as_dict` carries."""

    counts = found.by_class()
    lines = [
        f"shift plan  audit={found.audit_path or '-'}  "
        f"rehearse={', '.join(found.rehearse_paths) or '-'}",
        "",
        f"plan_total={found.total:,}  plan_convictions={found.convictions:,}  "
        f"plan_free_wins={found.free_wins:,}  "
        f"plan_structural={found.structural:,}",
        "",
        "plan_by_class",
    ]
    lines.extend(
        _table(
            ("remediation", "kind", "count"),
            [
                (item.name, item.kind, f"{counts[item.name]:,}")
                for item in REMEDIATION_CLASSES
            ],
        )
    )

    lines.extend(("", "plan_by_source"))
    lines.extend(
        _table(
            ("source", "items"),
            [(name, f"{count:,}") for name, count in found.by_source().items()],
        )
    )

    sections = found.sections()
    if sections:
        lines.extend(("", "plan_sections (working items per owning section)"))
        lines.extend(
            _table(
                ("section", "items"),
                [(name, f"{count:,}") for name, count in sections.items()],
            )
        )

    shown = found.items[: max(0, limit)]
    lines.extend(("", f"queue ({len(shown)} of {found.total:,}, --limit)"))
    lines.extend(
        _table(
            ("#", "remediation", "conviction", "section", "subject", "sources"),
            [
                (
                    str(index),
                    item.remediation,
                    "yes" if item.conviction else "-",
                    item.section or "-",
                    item.subject,
                    ",".join(item.sources),
                )
                for index, item in enumerate(shown, start=1)
            ],
        )
    )

    for index, item in enumerate(shown, start=1):
        lines.extend(("", f"{index}. {item.title}  [{item.remediation}]"))
        for evidence in item.evidence:
            lines.append(f"     evidence: {evidence}")
        for gate in item.gates:
            lines.append(f"     gate: {gate}")

    if found.capped:
        lines.extend(("", "plan_capped -- this plan is built from capped reports"))
        for entry in found.capped:
            lines.append(f"  {entry}")
        lines.append(
            "  Re-run the reports with a larger --limit to plan the rest. A "
            "detail list that stopped at --limit cannot describe what came "
            "after it, and neither can this queue."
        )

    lines.extend(("", "remediation classes"))
    for published in REMEDIATION_CLASSES:
        lines.append(f"  {published.name} ({published.kind}): {published.evidence}")
        lines.append(f"    gate: {published.gate}")

    lines.extend(("", f"the loop: {CAMPAIGN_LOOP}"))
    return lines


def plan_markdown(found: ShiftPlan) -> str:
    """Render the work order: a grouped checklist a maintainer works through.

    Grouped by remediation class rather than printed in queue order, because
    a work order is read by somebody deciding what to do this afternoon and
    the classes are the units of work: eleven deletions are one sitting, and
    eight migrations in one section are another. The queue's own order is
    preserved inside each group, and the rank is printed beside every item so
    the two views agree.
    """

    lines = [
        "# Shift remediation work order",
        "",
        f"**The loop.** {CAMPAIGN_LOOP}",
        "",
        "| | |",
        "|---|---|",
        f"| audit report | `{found.audit_path or '-'}` |",
        f"| rehearse reports | "
        f"{', '.join(f'`{item}`' for item in found.rehearse_paths) or '-'} |",
        f"| deltas rehearsed | "
        f"{', '.join(f'`0x{item:x}`' for item in found.deltas) or '-'} |",
        f"| items | {found.total} |",
        f"| convictions (a relink demonstrated these) | {found.convictions} |",
        f"| free wins (byte-identical to fix) | {found.free_wins} |",
        f"| parked as structural | {found.structural} |",
        "",
    ]
    if found.capped:
        lines.extend(
            (
                "> **This plan is built from capped reports.** A detail list "
                "that stopped at `--limit` cannot describe what came after "
                "it, and neither can this queue. Re-run with a larger "
                "`--limit` to plan the rest.",
                "",
            )
        )
        for entry in found.capped:
            lines.append(f"> - {entry}")
        lines.append("")

    position = {item.subject: index for index, item in enumerate(found.items, start=1)}
    for remediation in REMEDIATION_CLASSES:
        group = [
            item for item in found.items if item.remediation == remediation.name
        ]
        if not group:
            continue
        lines.extend(
            (
                f"## {remediation.name} ({len(group)})",
                "",
                f"*{remediation.kind}.* {remediation.evidence}",
                "",
                f"**Gate:** {remediation.gate}",
                "",
            )
        )
        heading: str | None = None
        for item in group:
            if remediation.name == MIGRATE_SYMBOL:
                owner = item.section or "no owning section"
                if owner != heading:
                    heading = owner
                    lines.extend((f"### {owner}", ""))
            rank = position.get(item.subject, 0)
            flag = " **(conviction)**" if item.conviction else ""
            lines.append(f"- [ ] **#{rank} {item.title}**{flag}")
            for evidence in item.evidence:
                lines.append(f"  - evidence: {evidence}")
            for gate in item.gates:
                lines.append(f"  - gate: `{gate}`")
            lines.append(f"  - sources: {', '.join(item.sources)}")
        lines.append("")

    lines.extend(
        (
            "---",
            "",
            "Every line above is evidence with coordinates attached, not a "
            "verdict about this project. The instrumentation reports what it "
            "measured and names what it structurally cannot see; the fixes, "
            "and the judgement about which of these addresses are authentic, "
            "remain the maintainer's.",
            "",
        )
    )
    return "\n".join(lines)
