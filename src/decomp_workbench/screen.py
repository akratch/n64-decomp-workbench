"""The one line a sweep prints per object, with the four facts it needs.

Every stage of one campaign wrote its own version of this line and each got a
different subset of it right. Two of the omissions cost real work:

* no line carried the **ring coset**, so three stages built objects whose
  scratch ring had rotated, scored them against a coset-quotienting band tool,
  and recorded them as wins. The object was further from the target than the
  base it replaced.
* no line separated **stores from loads** at a stack slot. The store count was
  exactly what distinguished the winning kill from a rejected alternative that
  was one instruction longer, and screens printed only ``ld1184``.

The other two facts -- the real instruction count and the frame size -- were on
most stage lines but re-derived by hand each time, from ``objdump | grep -c``
and a ``grep`` for the prologue's ``addiu sp``.

So: one line, built once, carrying the object's identity, its true length, its
frame, its load and store traffic (optionally at one named slot), and the ring
coset it sits at relative to the target. The coset is the same reading
:mod:`decomp_workbench.phase` produces -- there is one implementation of it,
and this is a projection of it, not a second opinion.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Instruction

__all__ = ["ScreenLine", "build_screen_line", "file_sha1"]

#: Coprocessor-1 memory traffic against the frame. Separated because the two
#: directions answer different questions: loads say a value was needed here,
#: stores say it was spilled or homed here, and only the second distinguishes
#: a killed web from a relocated one.
_LOAD_RE = re.compile(r"^(?:lwc1|ldc1)\s+\$?f\d+\s*,\s*(-?\d+)\(\$?sp\)")
_STORE_RE = re.compile(r"^(?:swc1|sdc1)\s+\$?f\d+\s*,\s*(-?\d+)\(\$?sp\)")


def file_sha1(path: str | Path) -> str:
    """Return an object's short SHA-1: the identity a sweep line carries.

    Twelve hexadecimal characters, matching what every campaign screen used
    (``shasum -a1 obj.o | cut -c1-12``), so a line printed here and a line
    printed by a project's own script name the same object the same way.
    """

    digest = hashlib.sha1(usedforsecurity=False)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _traffic(
    instructions: Sequence[Instruction], *, slot: int | None
) -> tuple[int, int]:
    """Count float loads and stores against the frame, optionally at one slot."""

    loads = stores = 0
    for item in instructions:
        text = item.assembly.strip()
        load = _LOAD_RE.match(text)
        if load is not None:
            if slot is None or int(load.group(1)) == slot:
                loads += 1
            continue
        store = _STORE_RE.match(text)
        if store is not None and (slot is None or int(store.group(1)) == slot):
            stores += 1
    return loads, stores


@dataclass(frozen=True)
class ScreenLine:
    """One object's identity, length, frame, slot traffic, and ring coset."""

    label: str
    sha1: str | None
    instructions: int
    frame: int | None
    loads: int
    stores: int
    slot: int | None = None
    coset: str | None = None
    quotiented: int | None = None
    positional: int | None = None
    coset_unavailable: str | None = None

    @property
    def rotated(self) -> bool:
        """Whether this object's ring sits away from the target's.

        `?` is not a rotation. It is the reading for an object holding no
        ring-carrying row at all -- an integer function, a fixture, a
        candidate whose float work is entirely in another slot -- and treating
        it as a rotation printed the coset caution over whole sweeps of
        objects that had no ring to rotate.
        """

        return self.coset is not None and self.coset not in {"id", "?"}

    def render(self) -> str:
        suffix = "" if self.slot is None else str(self.slot)
        parts = [
            f"sha={self.sha1}" if self.sha1 else "sha=-",
            f"ni={self.instructions}",
            f"frame={self.frame if self.frame is not None else '-'}",
            f"ld{suffix}={self.loads}",
            f"st{suffix}={self.stores}",
        ]
        if self.coset is not None:
            parts.append(f"coset={self.coset}")
        return "screen: " + " ".join(parts)

    def caution(self) -> str | None:
        """Return the coset warning, or ``None`` when there is nothing to say."""

        if not self.rotated:
            return None
        return (
            f"COSET: this object's scratch ring sits at {self.coset}, not the "
            f"target's. A ring-quotienting scorer reads it as "
            f"{self.quotiented} row(s); as written it is {self.positional}. "
            "Do not record it as a win on the quotiented number."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "sha1": self.sha1,
            "instructions": self.instructions,
            "frame": self.frame,
            "loads": self.loads,
            "stores": self.stores,
            "slot": self.slot,
            "coset": self.coset,
            "coset_quotiented": self.quotiented,
            "coset_positional": self.positional,
            "coset_unavailable": self.coset_unavailable,
            "coset_caution": self.caution(),
            "rendered": self.render(),
        }


def build_screen_line(
    instructions: Sequence[Instruction],
    *,
    label: str,
    path: str | Path | None = None,
    target: Sequence[Instruction] | None = None,
    slot: int | None = None,
    ring: tuple[str, ...] | None = None,
) -> ScreenLine:
    """Build one screen line, reading the coset only when a target allows it.

    Without a target's instructions there is no coset to report -- scoring
    against raw ROM bytes is exactly that case -- and the line says so rather
    than leaving the reader to assume identity.
    """

    # Deferred: `phase` reads `compare`, which is a heavier import than a
    # summary line should force on every caller of this module.
    from .compare import frame_size
    from .objdump import true_instruction_count
    from .phase import DEFAULT_RING, build_phase_report
    from .shift_align import build_shift_diff

    loads, stores = _traffic(instructions, slot=slot)
    coset: str | None = None
    quotiented: int | None = None
    positional: int | None = None
    unavailable: str | None = None
    if target:
        report = build_phase_report(
            target,
            instructions,
            shift=build_shift_diff(target, instructions),
            ring=ring or DEFAULT_RING,
        )
        entry = report.slots[0]
        coset = "?" if entry.coset_evidence == "no-evidence" else entry.coset.label
        quotiented = entry.quotiented
        positional = entry.positional
    else:
        unavailable = (
            "no target instructions were supplied, so the ring coset is not "
            "measured here; score against a target object to read it"
        )
    return ScreenLine(
        label=label,
        sha1=file_sha1(path) if path is not None else None,
        instructions=true_instruction_count(instructions),
        frame=frame_size("\n".join(item.assembly for item in instructions)),
        loads=loads,
        stores=stores,
        slot=slot,
        coset=coset,
        quotiented=quotiented,
        positional=positional,
        coset_unavailable=unavailable,
    )
