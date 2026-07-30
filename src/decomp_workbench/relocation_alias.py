"""Resolve differing relocation spellings through a caller-supplied symbol map."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .model import Instruction

ALIAS_SCHEMA = "decomp-workbench-relocation-aliases-v1"
EXPRESSION_RE = re.compile(
    r"^(?P<symbol>[A-Za-z_.$][A-Za-z0-9_.$]*)(?P<addend>[+-](?:0x[0-9a-fA-F]+|\d+))?$"
)
NM_RE = re.compile(
    r"^\s*(?P<address>[0-9a-fA-F]+)\s+(?:[A-Za-z?]\s+)?(?P<symbol>\S+)\s*$"
)


def load_symbol_map(path: str | Path) -> dict[str, int]:
    """Read either a JSON ``symbol: address`` object or conventional nm text."""

    source = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(source)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        result = {}
        for name, address in value.items():
            if not isinstance(name, str):
                raise ValueError("symbol-map JSON keys must be strings")
            try:
                result[name] = int(str(address), 0)
            except ValueError:
                raise ValueError(
                    f"symbol-map address for {name!r} is not an integer"
                ) from None
        return result
    result = {}
    for line_number, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        match = NM_RE.match(line)
        if not match:
            raise ValueError(
                f"symbol-map line {line_number} is not ADDRESS [TYPE] SYMBOL"
            )
        result[match.group("symbol")] = int(match.group("address"), 16)
    return result


def resolve_relocation_expression(
    expression: str | None,
    symbols: dict[str, int],
) -> int | None:
    if expression is None:
        return None
    match = EXPRESSION_RE.match(expression.replace(" ", ""))
    if not match:
        return None
    base = symbols.get(match.group("symbol"))
    if base is None:
        return None
    addend_text = match.group("addend")
    addend = int(addend_text, 0) if addend_text else 0
    return base + addend


def relocation_alias_report(
    target: list[Instruction],
    candidate: list[Instruction],
    *,
    symbols: dict[str, int],
) -> dict[str, Any]:
    """Classify same-address relocation spelling pairs without claiming exactness."""

    aliases = []
    unresolved = []
    for index in range(max(len(target), len(candidate))):
        expected_relocations = target[index].relocations if index < len(target) else []
        actual_relocations = (
            candidate[index].relocations if index < len(candidate) else []
        )
        for relocation_index in range(
            max(len(expected_relocations), len(actual_relocations))
        ):
            left = (
                expected_relocations[relocation_index]
                if relocation_index < len(expected_relocations)
                else None
            )
            right = (
                actual_relocations[relocation_index]
                if relocation_index < len(actual_relocations)
                else None
            )
            if (
                left is not None
                and right is not None
                and left.kind == right.kind
                and left.symbol == right.symbol
            ):
                continue
            left_address = resolve_relocation_expression(
                left.symbol if left is not None else None,
                symbols,
            )
            right_address = resolve_relocation_expression(
                right.symbol if right is not None else None,
                symbols,
            )
            record = {
                "index": index,
                "relocation_index": relocation_index,
                "target": (
                    {
                        "kind": left.kind,
                        "expression": left.symbol,
                        "address": left_address,
                    }
                    if left is not None
                    else None
                ),
                "candidate": (
                    {
                        "kind": right.kind,
                        "expression": right.symbol,
                        "address": right_address,
                    }
                    if right is not None
                    else None
                ),
            }
            if (
                left is not None
                and right is not None
                and left.kind == right.kind
                and left_address is not None
                and right_address is not None
                and left_address == right_address
            ):
                record["resolved_address"] = left_address
                aliases.append(record)
            else:
                unresolved.append(record)
    return {
        "schema": ALIAS_SCHEMA,
        "resolved_address_aliases": aliases,
        "alias_count": len(aliases),
        "unresolved_spelling_differences": unresolved,
        "proof": (
            "Caller-supplied symbol-map evidence only. Address-equivalent "
            "relocation spellings still require the project's link or ROM check."
        ),
    }
