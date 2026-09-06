"""Explicit per-input reservations, not inferred allocator ownership.

A sidecar is an operator-supplied diagnostic assumption bound to an input and
symbol. Hash binding prevents accidental reuse; it does not prove the contents
of a compiler trace. Actual reserved registers need not survive in instructions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTER_STATE_SCHEMA = "decomp-workbench-register-reservations-v1"
IDO53_GP_SEED = ("t6", "t7", "t8", "t9", "t0", "t1", "t2", "t3", "t4", "t5")
IDO53_SHARED_GP = ("t0", "t1", "t2", "t3", "t4", "t5")


@dataclass(frozen=True)
class RegisterReservations:
    """Conditional integer scratch withdrawals for one procedure, supplied explicitly.

    Only the shared t0-t5 subset is represented. This is not a list of emitted
    colored uses, all UOPT colors, or a complete lifetime/alias model. Direct
    API callers own input binding; CLI callers use :func:`load_reservations`.
    """

    reserved: tuple[str, ...]
    evidence: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reserved, tuple)
            or any(not isinstance(item, str) for item in self.reserved)
            or len(set(self.reserved)) != len(self.reserved)
            or not set(self.reserved) <= set(IDO53_SHARED_GP)
            or not isinstance(self.evidence, str)
            or not self.evidence.strip()
        ):
            raise ValueError("invalid IDO 5.3 shared-register reservations")

    @property
    def temp_ring(self) -> tuple[str, ...]:
        return tuple(name for name in IDO53_GP_SEED if name not in self.reserved)

    def as_dict(self) -> dict[str, Any]:
        return {
            "basis": "supplied-reservations",
            "reserved": list(self.reserved),
            "temp_ring": list(self.temp_ring),
            "evidence": self.evidence,
        }


def load_reservations(
    sidecar: str | Path | None, input_path: str | Path, symbol: str | None
) -> RegisterReservations | None:
    """Load an explicitly scoped sidecar; never borrow the other side's state."""

    if sidecar is None:
        return None
    value = json.loads(Path(sidecar).read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema") != REGISTER_STATE_SCHEMA
        or symbol is None
        or value.get("symbol") != symbol
        or value.get("input_sha256")
        != hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
        or not isinstance(value.get("reserved"), list)
        or not isinstance(value.get("evidence"), str)
    ):
        raise ValueError("register reservations do not bind this input and symbol")
    return RegisterReservations(tuple(value["reserved"]), value["evidence"])
