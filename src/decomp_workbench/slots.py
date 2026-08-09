"""Which stack slot holds what, and how many rows touch it.

Two campaign questions reduce to one census nobody had:

* **"Can this web be killed by fusing a donor onto it, and what does it
  cost?"** The price of a donor is the number of rows in the reference object
  that touch the donor's own stack slot -- one query, and one campaign spent a
  whole sweep answering it by construction instead. The cheapest donor
  available cost 2 rows; the others cost 4, 6 and 7, and none of that was
  visible until the slots were listed.
* **"Is this slot even the one I think it is?"** The traffic at a slot, split
  into loads and stores and into the widths that reach it, is what separates a
  killed web from a relocated one -- and a slot reached by two different widths
  is a pun, not two variables.

The reading is deliberately narrow: what the object's rows do, counted. It
does not say which C local lives at a slot, because nothing in an object says
so. :func:`volatile_probe_sources` is the measurement that does answer that,
and it is a build, not a read.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .csource import CSourceError, declaration_line, scan_statements, strip_noncode
from .model import Instruction

__all__ = [
    "SlotTraffic",
    "slot_report",
    "volatile_probe_sources",
]

SLOTS_SCHEMA = "decomp-workbench-stack-slots-v1"

#: Any frame-relative memory access, whichever register file it names. The
#: width matters: two widths at one offset is a pun or an overlap, and both are
#: worth seeing before a donor is priced.
_ACCESS_RE = re.compile(
    r"^(?P<op>l[bhwd]u?|lwc1|ldc1|s[bhwd]|swc1|sdc1)\s+"
    r"(?P<reg>\$?[\w$]+)\s*,\s*(?P<offset>-?\d+)\((?:\$)?sp\)"
)

#: `addiu rX,sp,N` -- the address of a slot, taken. A slot whose address is
#: computed is reachable by a callee, which changes what any conclusion about
#: it can claim.
#: The destination must not itself be `sp`: the prologue's
#: `addiu sp,sp,-1704` is the frame, not a slot, and counting it put the
#: frame size at the top of a "cheapest slot" list.
_ADDRESS_RE = re.compile(r"^addiu\s+(?P<reg>\$?[\w$]+)\s*,\s*(?:\$)?sp\s*,\s*(-?\d+)")

_WIDTHS = {
    "lb": 1,
    "lbu": 1,
    "sb": 1,
    "lh": 2,
    "lhu": 2,
    "sh": 2,
    "lw": 4,
    "sw": 4,
    "lwc1": 4,
    "swc1": 4,
    "ld": 8,
    "sd": 8,
    "ldc1": 8,
    "sdc1": 8,
}


@dataclass(frozen=True)
class SlotTraffic:
    """One sp-relative stack slot, and everything the object's rows do to it.

    ``offset`` is the displacement as the rows spell it -- the ``1184`` in
    ``lwc1 $f10,1184(sp)``. It is *not* the frame offset the allocator trace
    keys a site by: that is this number plus the frame size, and the two must
    not be confused, because ``1184`` and ``-520`` name the same storage.
    """

    offset: int
    loads: int
    stores: int
    address_taken: int
    widths: tuple[int, ...]
    registers: tuple[str, ...]
    rows: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.loads + self.stores

    @property
    def punned(self) -> bool:
        """Whether more than one access width reaches this offset."""

        return len(self.widths) > 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "loads": self.loads,
            "stores": self.stores,
            "total": self.total,
            "address_taken": self.address_taken,
            "widths": list(self.widths),
            "punned": self.punned,
            "registers": list(self.registers),
            "rows": list(self.rows),
        }


def slot_report(
    instructions: Sequence[Instruction],
    *,
    label: str,
    rows: tuple[int, int] | None = None,
    minimum: int = 1,
) -> dict[str, Any]:
    """Return the frame's slot traffic, one entry per offset touched."""

    from .compare import frame_size

    # The allocator trace keys a site by frame offset (`0xfffffdf8`); the rows
    # spell the same storage sp-relative (`1184(sp)`). Both are printed so the
    # reader never has to do the arithmetic, or discover the hard way that the
    # two vocabularies meet at `slot + frame`. Taken over every row, so a
    # `--rows` window that excludes the prologue still resolves it.
    frame = frame_size("\n".join(item.assembly for item in instructions))
    low, high = rows if rows is not None else (1, len(instructions))
    loads: dict[int, int] = {}
    stores: dict[int, int] = {}
    addresses: dict[int, int] = {}
    widths: dict[int, set[int]] = {}
    registers: dict[int, set[str]] = {}
    touched: dict[int, list[int]] = {}
    for index, item in enumerate(instructions, start=1):
        if not low <= index <= high:
            continue
        text = item.assembly.strip()
        access = _ACCESS_RE.match(text)
        if access is not None:
            offset = int(access.group("offset"))
            operation = access.group("op")
            bucket = stores if operation.startswith("s") else loads
            bucket[offset] = bucket.get(offset, 0) + 1
            widths.setdefault(offset, set()).add(_WIDTHS.get(operation, 0))
            registers.setdefault(offset, set()).add(
                access.group("reg").removeprefix("$")
            )
            touched.setdefault(offset, []).append(index)
            continue
        address = _ADDRESS_RE.match(text)
        if address is not None and address.group("reg").removeprefix("$") != "sp":
            offset = int(address.group(2))
            addresses[offset] = addresses.get(offset, 0) + 1
            touched.setdefault(offset, []).append(index)

    entries = [
        SlotTraffic(
            offset=offset,
            loads=loads.get(offset, 0),
            stores=stores.get(offset, 0),
            address_taken=addresses.get(offset, 0),
            widths=tuple(sorted(widths.get(offset, set()))),
            registers=tuple(sorted(registers.get(offset, set()))),
            rows=tuple(touched.get(offset, ())),
        )
        for offset in sorted(set(loads) | set(stores) | set(addresses))
    ]
    kept = [item for item in entries if item.total + item.address_taken >= minimum]

    def entry(item: SlotTraffic) -> dict[str, Any]:
        payload = item.as_dict()
        payload["frame_offset"] = None if frame is None else item.offset + frame
        return payload

    return {
        "schema": SLOTS_SCHEMA,
        "object": label,
        "rows": [low, min(high, len(instructions))],
        "frame": frame,
        "slot_count": len(kept),
        "row_count": len(instructions),
        "touched_rows": sum(item.total for item in kept),
        "slots": [entry(item) for item in kept],
        # Ranked among slots the rows actually read or write: a slot whose
        # only mention is an address-take costs nothing to disturb because
        # nothing touches it, which is not the question a donor price asks.
        "cheapest": [
            entry(item)
            for item in sorted(
                (item for item in kept if item.total), key=lambda item: item.total
            )[:5]
        ],
        "reading": (
            "counts of what this object's rows do to each sp-relative stack "
            "slot -- the 1184 in `lwc1 $f10,1184(sp)`. It does not say which "
            "C local lives at a slot: nothing in an object says so, and the "
            "measurement that does is a build (see `--volatile-probe`)."
        ),
    }


def volatile_probe_sources(
    source: str | Path,
    *,
    directory: str | Path,
    variables: Sequence[str] = (),
) -> dict[str, Any]:
    """Write one source per local, that local made `volatile`.

    A `volatile` local must stay in memory, so the slot it lands at in the
    rebuilt object is the slot the compiler had already chosen for it. That is
    the only way to attribute a slot to a name without reading debug output,
    and one campaign built it by hand from a hand-maintained list of twenty-
    seven declaration line numbers. The declarations are found here instead.

    The workbench does not own the build: this writes the sources and stops.
    Build each one, run `slots` on the result, and the offset whose traffic
    appears or grows is that local's.
    """

    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CSourceError(f"cannot read {source}: {error}") from None
    code = strip_noncode(text)
    declarations = _local_declarations(code)
    if variables:
        missing = [name for name in variables if name not in declarations]
        if missing:
            raise CSourceError(
                "these names are not declared as locals in "
                f"{path.name}: {', '.join(missing)}"
            )
        declarations = {name: declarations[name] for name in variables}
    if not declarations:
        raise CSourceError(
            f"{path.name} declares no locals this probe can make volatile. It "
            "looks for a declaration line of the form `TYPE name;` inside a "
            "function body."
        )
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    lines = text.splitlines(keepends=True)
    written: list[dict[str, Any]] = []
    for name, number in sorted(declarations.items(), key=lambda item: item[1]):
        body = list(lines)
        original = body[number - 1]
        indent = original[: len(original) - len(original.lstrip())]
        body[number - 1] = f"{indent}volatile {original.lstrip()}"
        out = target / f"{path.stem}.vol.{name}.c"
        out.write_text("".join(body), encoding="utf-8")
        written.append({"variable": name, "line": number, "path": str(out)})
    return {
        "source": str(path),
        "directory": str(target),
        "count": len(written),
        "variants": written,
        "next": (
            "build each variant, run `slots` on it, and compare against the "
            "base object's slots: the offset that appears or grows is that "
            "local's stack home"
        ),
    }


_DECLARATION_RE = re.compile(
    r"^\s+(?:const\s+|volatile\s+|unsigned\s+|signed\s+|struct\s+|union\s+)*"
    r"(?P<type>[A-Za-z_]\w*)\s+(?P<stars>\**)\s*(?P<name>[A-Za-z_]\w*)\s*;\s*$"
)


def _local_declarations(code: list[str]) -> dict[str, int]:
    """Return each uninitialized local declaration's name and line.

    Indented, one name, no initializer, inside a body -- which is what a
    decompilation's local block looks like and is deliberately narrower than
    C's declaration grammar. A name this misses is a name the caller can pass
    explicitly.
    """

    statements = {item.line for item in scan_statements(code)}
    found: dict[str, int] = {}
    for number, line in enumerate(code, 1):
        if number not in statements:
            continue
        match = _DECLARATION_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if match.group("type") in {"return", "else", "case", "goto"}:
            continue
        if name in found:
            continue
        if declaration_line(code, name) != number:
            continue
        found[name] = number
    return found
