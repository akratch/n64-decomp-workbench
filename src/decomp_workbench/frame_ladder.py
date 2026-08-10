"""The frame ladder: every stack slot one procedure owns, from a CDX log.

Two campaign scripts answered this and neither was a tool. One decoded
`webdetail` records into homes and grouped them by itable slot; the other read
`CDX_SYMTAB` itable dumps and printed the ops with symbolic operands. They
disagreed about what a "slot" was, both hard-coded one function's frame size,
and one of them carried a hand-written offset-to-name table that was wrong for
every other translation unit.

What survives from them is the arithmetic and one law:

* **`home(sp) = offset - frame`.** The itable's `off` is measured from the top
  of the frame and printed as a two's-complement word; the sp-relative slot a
  disassembly shows is that offset minus the (signed, negative) frame size.
  Getting the sign wrong puts every local in the caller's frame, which reads
  as a plausible ladder.
* **The ladder is layered.** Declared locals sit at the top, `cfe`'s pooled
  expression temps sit immediately below them, and `uopt`'s own temps sit
  below those. An unnamed slot below the lowest named one is a compiler temp,
  and that is the only claim this module will make about it -- the input ucode
  carries no names at all (see `patches/README.md`), so a name here is one the
  reader supplied and nothing else.

Two sources feed one ladder. `symtab` records are the whole itable and are
preferred; `webdetail` records name only the slots that reached the allocator,
which is a subset, and the report says which source each row came from rather
than blending them into a table that looks complete.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from .cascade import CascadeError, CdxLog, format_frame_offset, parse_frame_offset
from .globalcolor import optional_integer

__all__ = [
    "ITABLE_KINDS",
    "SYMTAB_RECORD_GRAMMAR",
    "UOPT_OPCODES",
    "ItableEntry",
    "Ladder",
    "Slot",
    "frame_ladder",
    "ladder_report",
    "op_report",
    "parse_slot_names",
]

LADDER_SCHEMA = "decomp-workbench-frame-ladder-v1"
OPS_SCHEMA = "decomp-workbench-frame-ops-v1"

#: The two records `CDX_SYMTAB=1` adds, in the same shape as
#: :data:`~decomp_workbench.cascade.RECORD_GRAMMAR`. Both are CAMPAIGN-LOCAL:
#: the patch that emits them ships as a diff in `patches/`, not as a compiler.
SYMTAB_RECORD_GRAMMAR: dict[str, str] = {
    "symtabcount": (
        "CAMPAIGN-LOCAL (patches/uopt-5.3-cdx-symtab.patch). The itable's "
        "size, once per procedure. proc n base."
    ),
    "symtab": (
        "CAMPAIGN-LOCAL (patches/uopt-5.3-cdx-symtab.patch). One itable "
        "entry. proc idx kind name dtype selfidx bit ver off tag class b23 "
        "b24 vreg op l r raw08..raw36 rec. `off` is the frame offset of an "
        "`isvar` and `b24` its access size in bytes; `op`/`l`/`r` belong to "
        "an `isop` and nothing else. `name` is the itable KIND, not a symbol "
        "name: the input ucode has no names."
    ),
}

#: `rec+0`, straight out of `f_printitab`.
ITABLE_KINDS: dict[int, str] = {
    0: "empty",
    1: "islda",
    2: "isconst",
    3: "isvar",
    4: "isop",
    5: "isilda",
    6: "issvar",
    7: "dumped",
    8: "isrconst",
}

#: `rec+16` on an `isop`, recovered by joining a dump against a stock
#: `-Wo,-zdbug:2` listing. Unmapped opcodes print as their number.
UOPT_OPCODES: dict[int, str] = {
    1: "uadd",
    4: "uand",
    10: "ucg1",
    11: "ucg1b",
    24: "ucvt",
    25: "ucvtl",
    35: "uequ",
    40: "ugeq",
    54: "uilod",
    63: "uistr",
    65: "uixa",
    78: "ules",
    91: "umpy",
    95: "uneq",
    116: "ushr",
    123: "ustr",
    125: "usub",
}

#: `rec+22`: the storage class an itable entry carries.
STORAGE_CLASSES: dict[int, str] = {1: "M", 2: "P", 3: "R"}

_NAME_RE = re.compile(r"^\s*(?P<key>[^\s=#]+)\s*[=\s]\s*(?P<name>.+?)\s*$")


def _kind_name(kind: int | None) -> str:
    if kind is None:
        return "?"
    return ITABLE_KINDS.get(kind, str(kind))


def parse_slot_names(text: str, *, frame: int | None = None) -> dict[int, str]:
    """Parse a reader-supplied slot-name map into frame offsets.

    Both spellings a reader actually has are accepted, because both are how
    the two sides of the same fact get written down: `-140 colour` is the
    itable's offset, and `sp:76 colour` is what the disassembly shows. The
    second needs ``--frame`` to become the first, and says so instead of
    guessing a frame size.
    """

    names: dict[int, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = _NAME_RE.match(line)
        if match is None:
            raise CascadeError(
                f"names line {number}: {raw.strip()!r} is not `OFFSET NAME`; "
                "write `-140 colour` for a frame offset or `sp:76 colour` for "
                "an sp-relative slot"
            )
        key = match.group("key")
        if key.lower().startswith("sp:"):
            if frame is None:
                raise CascadeError(
                    f"names line {number}: an `sp:` slot needs --frame to "
                    "become a frame offset (--frame -216)"
                )
            try:
                slot = int(key[3:], 0)
            except ValueError:
                raise CascadeError(
                    f"names line {number}: {key!r} is not an sp-relative slot"
                ) from None
            offset = slot + frame
        else:
            offset = parse_frame_offset(key)
        names[offset] = match.group("name")
    return names


@dataclass(frozen=True)
class ItableEntry:
    """One `symtab` record: one entry of uopt's per-procedure itable."""

    index: int
    kind: int | None
    dtype: int | None
    symbol: int | None
    version: int | None
    offset: int | None
    tag: int | None
    storage_class: int | None
    size: int | None
    vreg: int | None
    opcode: int | None
    left: int | None
    right: int | None

    @property
    def kind_name(self) -> str:
        return _kind_name(self.kind)

    @property
    def is_variable(self) -> bool:
        return self.kind == 3

    @property
    def is_operation(self) -> bool:
        return self.kind == 4

    @property
    def opcode_name(self) -> str:
        if self.opcode is None:
            return "?"
        return UOPT_OPCODES.get(self.opcode, str(self.opcode))

    @property
    def storage_class_name(self) -> str | None:
        if self.storage_class is None:
            return None
        return STORAGE_CLASSES.get(self.storage_class, str(self.storage_class))

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "kind_name": self.kind_name,
            "dtype": self.dtype,
            "symbol": self.symbol,
            "version": self.version,
            "offset": self.offset,
            "tag": self.tag,
            "storage_class": self.storage_class,
            "storage_class_name": self.storage_class_name,
            "size": self.size,
            "vreg": self.vreg,
            "opcode": self.opcode,
            "opcode_name": self.opcode_name if self.is_operation else None,
            "left": self.left,
            "right": self.right,
        }


@dataclass(frozen=True)
class Slot:
    """One frame offset, with everything both record families say about it."""

    offset: int
    home: int | None
    name: str | None
    indices: tuple[int, ...]
    webs: tuple[int, ...]
    size: int | None
    vreg: int | None
    dtype: int | None
    storage_class: int | None
    sources: tuple[str, ...]
    tables: tuple[int, ...]

    @property
    def index(self) -> int | None:
        """The first itable index stamped at this offset.

        First, not lowest-numbered by accident: the itable is in
        first-occurrence order, so this index is where the expression owning
        this slot first appeared in the ucode stream.
        """

        return self.indices[0] if self.indices else None

    @property
    def storage_class_name(self) -> str | None:
        if self.storage_class is None:
            return None
        return STORAGE_CLASSES.get(self.storage_class, str(self.storage_class))

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "offset_text": format_frame_offset(self.offset),
            "home": self.home,
            "name": self.name,
            "index": self.index,
            "indices": list(self.indices),
            "webs": list(self.webs),
            "size": self.size,
            "vreg": self.vreg,
            "dtype": self.dtype,
            "storage_class": self.storage_class,
            "storage_class_name": self.storage_class_name,
            "sources": list(self.sources),
            "ichain_tables": list(self.tables),
        }


@dataclass(frozen=True)
class Ladder:
    """One procedure's stack slots, lowest offset first."""

    log: str
    proc: int | None
    frame: int | None
    slots: tuple[Slot, ...]
    entries: tuple[ItableEntry, ...]
    sources: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def named(self) -> tuple[Slot, ...]:
        return tuple(item for item in self.slots if item.name)

    @property
    def lowest_named_offset(self) -> int | None:
        named = self.named
        return min(item.offset for item in named) if named else None

    @property
    def below_named(self) -> tuple[Slot, ...]:
        """Unnamed slots beneath the lowest named one: compiler temps.

        The classification is structural and it is the whole claim. Which
        pass owns a given temp -- `cfe`'s pooled expression home versus one of
        `uopt`'s own -- is a further question the ladder cannot answer, and a
        campaign that guessed it from the index number guessed wrong.
        """

        floor = self.lowest_named_offset
        if floor is None:
            return ()
        return tuple(
            item for item in self.slots if item.name is None and item.offset < floor
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": LADDER_SCHEMA,
            "log": self.log,
            "proc": self.proc,
            "frame": self.frame,
            "sources": list(self.sources),
            "slot_count": len(self.slots),
            "named_count": len(self.named),
            "unnamed_count": len(self.slots) - len(self.named),
            "lowest_offset": self.slots[0].offset if self.slots else None,
            "lowest_named_offset": self.lowest_named_offset,
            "temp_candidates": [item.offset for item in self.below_named],
            "entry_count": len(self.entries),
            "operation_count": sum(item.is_operation for item in self.entries),
            "slots": [item.as_dict() for item in self.slots],
            "warnings": list(self.warnings),
        }


def _matches_proc(record_fields: dict[str, str], proc: int | None) -> bool:
    if proc is None:
        return True
    return optional_integer(record_fields.get("proc")) == proc


def itable_entries(log: CdxLog, *, proc: int | None = None) -> list[ItableEntry]:
    """Return the itable in log order, first record per index winning.

    A `symtab` dump repeats when a procedure is visited twice, and the first
    dump is the one the surrounding decisions were made against.
    """

    seen: dict[int, ItableEntry] = {}
    for record in log.of("symtab"):
        fields = record.fields
        if not _matches_proc(fields, proc):
            continue
        index = optional_integer(fields.get("idx"))
        if index is None or index in seen:
            continue
        if "kind" not in fields:  # the `nil` record: a pointer and nothing else
            continue
        seen[index] = ItableEntry(
            index=index,
            kind=optional_integer(fields.get("kind")),
            dtype=optional_integer(fields.get("dtype")),
            symbol=optional_integer(fields.get("selfidx")),
            version=optional_integer(fields.get("ver")),
            offset=optional_integer(fields.get("off")),
            tag=optional_integer(fields.get("tag")),
            storage_class=optional_integer(fields.get("class")),
            size=optional_integer(fields.get("b24")),
            vreg=optional_integer(fields.get("vreg")),
            opcode=optional_integer(fields.get("op")),
            left=optional_integer(fields.get("l")),
            right=optional_integer(fields.get("r")),
        )
    return [seen[index] for index in sorted(seen)]


def _webdetail_slots(log: CdxLog, *, proc: int | None) -> dict[int, dict[str, Any]]:
    """Group `webdetail` records by the frame offset in `raw10`."""

    found: dict[int, dict[str, Any]] = {}
    for record in log.of("webdetail"):
        fields = record.fields
        if not _matches_proc(fields, proc):
            continue
        raw = fields.get("raw10")
        if raw is None:
            continue
        try:
            offset = parse_frame_offset(raw)
        except CascadeError:
            continue
        if offset >= 0:  # a frame slot is below the frame top; 0 and up is not one
            continue
        entry = found.setdefault(
            offset,
            {"webs": [], "tables": [], "size": None, "dtype": None, "symbol": None},
        )
        web = optional_integer(fields.get("web"))
        if web is not None and web not in entry["webs"]:
            entry["webs"].append(web)
        table = optional_integer(fields.get("table"))
        if table is not None and table not in entry["tables"]:
            entry["tables"].append(table)
        if entry["dtype"] is None:
            entry["dtype"] = optional_integer(fields.get("dtype"))
        if entry["symbol"] is None:
            entry["symbol"] = optional_integer(fields.get("sym"))
        if entry["size"] is None:
            # `raw18` is the ICHAIN word whose top byte is the access size.
            raw18 = optional_integer(fields.get("raw18"))
            if raw18 is not None:
                entry["size"] = (raw18 >> 24) & 0xFF
    return found


def frame_ladder(
    log: CdxLog,
    *,
    frame: int | None = None,
    proc: int | None = None,
    names: dict[int, str] | None = None,
) -> Ladder:
    """Build one procedure's frame ladder from whichever records exist."""

    entries = itable_entries(log, proc=proc)
    web_slots = _webdetail_slots(log, proc=proc)
    if not entries and not web_slots:
        raise CascadeError(
            f"{log.name} carries no symtab and no stack-resident webdetail "
            "record, so it names no frame slot. Present: "
            f"{', '.join(sorted(log.kinds)) or 'nothing'}. The whole itable "
            "needs CDX_SYMTAB=1 from patches/uopt-5.3-cdx-symtab.patch; the "
            "allocator's subset of it needs CDX_LOG=1."
        )

    names = names or {}
    sources: list[str] = []
    if entries:
        sources.append("symtab")
    if web_slots:
        sources.append("webdetail")

    collected: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if not entry.is_variable or entry.offset is None:
            continue
        slot = collected.setdefault(
            entry.offset,
            {
                "indices": [],
                "size": None,
                "vreg": None,
                "dtype": None,
                "storage_class": None,
                "sources": ["symtab"],
            },
        )
        slot["indices"].append(entry.index)
        if slot["size"] is None:
            slot["size"] = entry.size
        if slot["vreg"] is None:
            slot["vreg"] = entry.vreg
        if slot["dtype"] is None:
            slot["dtype"] = entry.dtype
        if slot["storage_class"] is None:
            slot["storage_class"] = entry.storage_class

    for offset, found in web_slots.items():
        slot = collected.setdefault(
            offset,
            {
                "indices": [],
                "size": None,
                "vreg": None,
                "dtype": None,
                "storage_class": None,
                "sources": [],
            },
        )
        if "webdetail" not in slot["sources"]:
            slot["sources"].append("webdetail")
        if slot["size"] is None:
            slot["size"] = found["size"]
        if slot["dtype"] is None:
            slot["dtype"] = found["dtype"]
        if not slot["indices"] and found["symbol"] is not None:
            slot["indices"].append(found["symbol"])

    slots = tuple(
        Slot(
            offset=offset,
            home=None if frame is None else offset - frame,
            name=names.get(offset),
            indices=tuple(value["indices"]),
            webs=tuple(web_slots.get(offset, {}).get("webs", ())),
            size=value["size"],
            vreg=value["vreg"],
            dtype=value["dtype"],
            storage_class=value["storage_class"],
            sources=tuple(value["sources"]),
            tables=tuple(web_slots.get(offset, {}).get("tables", ())),
        )
        for offset, value in sorted(collected.items())
    )

    warnings: list[str] = []
    unplaced = sorted(set(names) - {item.offset for item in slots})
    if unplaced:
        warnings.append(
            "named offset(s) absent from this log: "
            + ", ".join(str(item) for item in unplaced)
            + " -- a name map from another build names slots this one does "
            "not have, and an edit that removes a local moves every offset "
            "below it"
        )
    if not entries and web_slots:
        warnings.append(
            "no symtab records: this ladder shows only the slots that reached "
            "the allocator, which is a subset of the frame. Rebuild with "
            "CDX_SYMTAB=1 for the whole itable."
        )
    return Ladder(
        log=log.name,
        proc=proc,
        frame=frame,
        slots=slots,
        entries=tuple(entries),
        sources=tuple(sources),
        warnings=tuple(warnings),
    )


def ladder_report(ladder: Ladder) -> dict[str, Any]:
    """Return the ladder document, ready for `--json`."""

    return ladder.as_dict()


def _operand_name(
    index: int | None, entries: dict[int, ItableEntry], names: dict[int, str]
) -> str:
    if index is None or index in {-1, 0xFFFF}:
        return "."
    entry = entries.get(index)
    if entry is None:
        return f"#{index}"
    if entry.is_operation:
        return f"op{index}"
    if entry.is_variable:
        label = entry.storage_class_name or "?"
        if entry.offset is not None and entry.offset in names:
            return f"{names[entry.offset]}({index})"
        if entry.offset is not None:
            return f"{label}{entry.offset}({index})"
        return f"{label}{index}"
    return f"{entry.kind_name}{index}"


def op_report(
    ladder: Ladder,
    *,
    names: dict[int, str] | None = None,
    offsets: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Return the itable's operation stream, in creation order.

    Creation order is index order, and index order is first-occurrence order
    in the ucode stream. That is what makes this readable as a narrative of
    the source rather than a table: the entry beside which a temp is stamped
    is the construct that created it.
    """

    if not ladder.entries:
        raise CascadeError(
            f"{ladder.log} carries no symtab records, so it has no operation "
            "stream. The itable dump needs CDX_SYMTAB=1 from "
            "patches/uopt-5.3-cdx-symtab.patch."
        )
    names = names or {}
    by_index = {entry.index: entry for entry in ladder.entries}
    wanted: set[int] | None = None
    if offsets is not None:
        selected = set(offsets)
        wanted = {
            entry.index
            for entry in ladder.entries
            if entry.is_variable and entry.offset in selected
        }
    rows: list[dict[str, Any]] = []
    for entry in ladder.entries:
        if not entry.is_operation:
            continue
        if wanted is not None and not ({entry.left, entry.right} & wanted):
            continue
        rows.append(
            {
                "index": entry.index,
                "opcode": entry.opcode,
                "opcode_name": entry.opcode_name,
                "dtype": entry.dtype,
                "left": entry.left,
                "right": entry.right,
                "left_name": _operand_name(entry.left, by_index, names),
                "right_name": _operand_name(entry.right, by_index, names),
            }
        )
    return {
        "schema": OPS_SCHEMA,
        "log": ladder.log,
        "proc": ladder.proc,
        "entry_count": len(ladder.entries),
        "operation_count": sum(item.is_operation for item in ladder.entries),
        "selected_count": len(rows),
        "selected_offsets": None if offsets is None else sorted(set(offsets)),
        "operations": rows,
    }


def ladder_lines(ladder: Ladder) -> Iterator[str]:
    """Render the ladder the way a reader reads it: lowest slot first."""

    frame = "-" if ladder.frame is None else str(ladder.frame)
    temps = {item.offset for item in ladder.below_named}
    yield (
        f"frame ladder: {ladder.log}  {len(ladder.slots)} slot(s)  "
        f"frame={frame}  source={'+'.join(ladder.sources)}"
    )
    for slot in ladder.slots:
        home = "-" if slot.home is None else f"{slot.home}(sp)"
        index = "-" if slot.index is None else str(slot.index)
        size = "-" if slot.size is None else str(slot.size)
        vreg = "-" if slot.vreg is None else str(slot.vreg)
        webs = ",".join(str(item) for item in slot.webs) or "-"
        name = slot.name or ("temp?" if slot.offset in temps else "-")
        yield (
            f"  {slot.offset:6d} {home:>9s} idx={index:<5s} size={size:<3s} "
            f"vreg={vreg:<3s} class={slot.storage_class_name or '-':<2s} "
            f"webs={webs:<12s} {name}"
        )
    floor = ladder.lowest_named_offset
    if floor is not None:
        yield (
            f"  {len(ladder.below_named)} unnamed slot(s) below the lowest "
            f"named offset {floor}: compiler temps"
        )
    for warning in ladder.warnings:
        yield f"warning: {warning}"
