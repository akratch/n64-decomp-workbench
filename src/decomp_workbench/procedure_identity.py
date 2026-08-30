"""Bind UGEN procedure ordinals to names carried by retained Ucode."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .evidence import artifact_record
from .ucode import UcodeRecord, parse_ucode

PROCEDURE_MAP_SCHEMA = "decomp-workbench-ugen-procedures-v1"
SYMBOL_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_.$]*\Z")


def procedure_names(records: Sequence[UcodeRecord]) -> tuple[str, ...]:
    """Read each Uent's following procedure-name Ucomm payload exactly."""

    names: list[str] = []
    for index, record in enumerate(records):
        if record.name != "ent":
            continue
        if index + 1 >= len(records) or records[index + 1].name != "comm":
            raise ValueError(f"Uent record {record.index} has no following name Ucomm")
        name_record = records[index + 1]
        if len(name_record.words) < 6:
            raise ValueError(f"procedure-name Ucomm {name_record.index} is truncated")
        length = name_record.words[4]
        payload = b"".join(word.to_bytes(4, "big") for word in name_record.words[6:])
        if length < 1 or length > len(payload):
            raise ValueError(
                f"procedure-name Ucomm {name_record.index} has invalid length {length}"
            )
        try:
            name = payload[:length].rstrip(b"\0").decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError(
                f"procedure-name Ucomm {name_record.index} is not ASCII"
            ) from error
        if SYMBOL_RE.fullmatch(name) is None:
            raise ValueError(
                f"procedure-name Ucomm {name_record.index} is malformed: {name!r}"
            )
        names.append(name)
    if not names:
        raise ValueError("retained Ucode contains no named procedures")
    return tuple(names)


def procedure_map(
    ucode: str | Path, *, candidate_object: str | Path | None = None
) -> dict[str, Any]:
    """Build a hash-bound ordinal/name map from one complete retained stream."""

    names = procedure_names(parse_ucode(ucode))
    return {
        "schema": PROCEDURE_MAP_SCHEMA,
        "procedures": [
            {"ordinal": ordinal, "name": name} for ordinal, name in enumerate(names)
        ],
        "artifacts": [
            artifact_record(ucode, role="candidate-ucode"),
            *(
                [artifact_record(candidate_object, role="candidate-object")]
                if candidate_object is not None
                else []
            ),
        ],
        "claim": (
            "Procedure names and ordinals come from the candidate's retained Ucode. "
            "They scope candidate UGEN events; they do not infer target allocator "
            "events from machine code."
        ),
    }


def select_procedure(report: dict[str, Any], symbol: str) -> int:
    matches = [
        int(item["ordinal"])
        for item in report.get("procedures", [])
        if isinstance(item, dict) and item.get("name") == symbol
    ]
    if len(matches) != 1:
        raise ValueError(
            f"retained Ucode contains {len(matches)} procedures named {symbol!r}"
        )
    return matches[0]


__all__ = [
    "PROCEDURE_MAP_SCHEMA",
    "procedure_map",
    "procedure_names",
    "select_procedure",
]
