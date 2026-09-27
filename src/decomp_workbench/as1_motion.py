"""Read IDO 5.3's native accepted cross-block motion decisions.

``-Wa,-xbbdbg,8`` emits paired MOVETO/MOVEFROM records and post-move block
snapshots. No instrumentation or correlation by instruction word is needed to
identify the two blocks of an accepted move. Block/slot IDs are run-local and
can be reused in later optimization rounds; event order is retained instead.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .as1_reorganize import mips_mnemonic

MOVE = re.compile(
    r"^\s*MOVE(TO|FROM) bb (\d+),? inst (\d+)\s+"
    r"time: old (-?\d+), new (-?\d+)\s*$"
)
DUMP = re.compile(r"^----- basic block instruction moved (to|from) -----\s*$")
INST = re.compile(
    r"^\s*INST (\d+): (!?)Line (\d+):\s+(0x[0-9a-fA-F]{8}|0000000000)(?:\s+.*)?$"
)
PSEUDO = re.compile(r"^\s*INST (\d+): (!?)# (\d+)\s*$")


@dataclass
class Endpoint:
    block: int
    slot: int
    old_time: int
    new_time: int


@dataclass
class Instruction:
    slot: int
    line: int | None
    word: int | None
    pseudo: int | None = None
    marked: bool = False


@dataclass
class Move:
    ordinal: int
    destination: Endpoint
    source: Endpoint
    destination_dump: list[Instruction] = field(default_factory=list)
    source_dump: list[Instruction] = field(default_factory=list)
    destination_dump_present: bool = False
    source_dump_present: bool = False


def parse_motion_trace(text: str) -> tuple[list[Move], int]:
    """Pair actual producer decisions; refuse truncated pairs and malformed dumps."""
    events: list[Move] = []
    pending: Endpoint | None = None
    active: Move | None = None
    dump: list[Instruction] | None = None
    ignored = 0
    for row in text.splitlines():
        if not row.strip():
            continue
        match = MOVE.fullmatch(row)
        if match:
            endpoint = Endpoint(*(int(match[i]) for i in range(2, 6)))
            if endpoint.slot < 1:
                raise ValueError("native instruction slots must be positive")
            if match[1] == "TO":
                if pending is not None:
                    raise ValueError("MOVETO has no paired MOVEFROM")
                pending, active = endpoint, None
            else:
                if pending is None:
                    raise ValueError("MOVEFROM has no paired MOVETO")
                active = Move(len(events), pending, endpoint)
                events.append(active)
                pending = None
            dump = None
            continue
        match = DUMP.fullmatch(row)
        if match:
            if active is None or pending is not None:
                raise ValueError("post-move dump without paired decision")
            name = "destination" if match[1] == "to" else "source"
            if getattr(active, name + "_dump_present"):
                raise ValueError("duplicate post-move dump")
            setattr(active, name + "_dump_present", True)
            dump = getattr(active, name + "_dump")
            continue
        if dump is not None:
            match = INST.fullmatch(row)
            pseudo = PSEUDO.fullmatch(row)
            if match or pseudo:
                if match is not None:
                    item = Instruction(
                        int(match[1]),
                        int(match[3]),
                        int(match[4], 16),
                        marked=bool(match[2]),
                    )
                else:
                    assert pseudo is not None
                    item = Instruction(
                        int(pseudo[1]), None, None, int(pseudo[3]), bool(pseudo[2])
                    )
                if item.slot != len(dump) + 1:
                    raise ValueError("noncontiguous or duplicate post-move slot")
                dump.append(item)
                continue
            if row.lstrip().startswith("INST "):
                raise ValueError("unsupported post-move instruction record")
            dump = None
        if row.lstrip().startswith(
            ("MOVETO", "MOVEFROM", "----- basic block instruction moved")
        ):
            raise ValueError("malformed native motion record")
        ignored += 1
    if pending is not None:
        raise ValueError("truncated MOVETO/MOVEFROM pair")
    for event in events:
        for name in ("destination", "source"):
            endpoint = getattr(event, name)
            records = getattr(event, name + "_dump")
            if getattr(event, name + "_dump_present") and len(records) < endpoint.slot:
                raise ValueError("post-move dump does not reach moved slot")
    return events, ignored


def _instruction(item: Instruction) -> dict[str, Any]:
    return {
        "slot": item.slot,
        "line": item.line,
        "word": f"0x{item.word:08x}" if item.word is not None else None,
        "opcode": mips_mnemonic(item.word) if item.word is not None else None,
        "pseudo": item.pseudo,
        "native_marked": item.marked,
    }


def _event(event: Move) -> dict[str, Any]:
    target = next(
        (
            item
            for item in event.destination_dump
            if item.slot == event.destination.slot
        ),
        None,
    )
    old = event.destination.old_time + event.source.old_time
    new = event.destination.new_time + event.source.new_time
    return {
        "event": event.ordinal,
        "outcome": "accepted-native-move",
        "source": asdict(event.source),
        "destination": asdict(event.destination),
        "moved_instruction": _instruction(target) if target is not None else None,
        "source_after": [_instruction(item) for item in event.source_dump],
        "destination_after": [_instruction(item) for item in event.destination_dump],
        "source_dump_present": event.source_dump_present,
        "destination_dump_present": event.destination_dump_present,
        "cost": {
            "old_sum": old,
            "new_sum": new,
            "sum_reduction": old - new,
            "destination_increase": event.destination.new_time
            - event.destination.old_time,
        },
    }


LIMITS = {
    "procedure_and_round": "unavailable: native motion records do not name either",
    "block_identity": "run-local; reuse in later rounds is possible",
    "instruction_identity": "native block slot only; no ELF or relocation identity",
    "eligibility": "unavailable: no admission or rollback predicates",
    "absence": "no event does not prove rejection, immobility, or trace completeness",
    "source_value": "physical line only; no authenticated C expression identity",
}


def motion_report(
    text: str, *, event: int | None = None, line: int | None = None
) -> dict[str, Any]:
    moves, ignored = parse_motion_trace(text)
    if event is not None and not 0 <= event < len(moves):
        raise ValueError("event ordinal is outside capture")
    rows = [_event(item) for item in moves if event is None or event == item.ordinal]
    if line is not None:
        rows = [
            item
            for item in rows
            if item["moved_instruction"] is not None
            and item["moved_instruction"]["line"] == line
        ]
    return {
        "schema": "decomp-workbench-as1-motion-v1",
        "trace_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "event_count": len(moves),
        "events": rows,
        "ignored_lines": ignored,
        "status": "native-moves-present" if moves else "no-native-move-records",
        "capabilities": dict(LIMITS),
        "proof": "Diagnostic only; requires stock fidelity. No matching verdict.",
    }


def compare_motion_traces(
    left: str, right: str, left_event: int, right_event: int
) -> dict[str, Any]:
    """Compare caller-selected events, without inferring identity across captures."""
    reports = [
        motion_report(left, event=left_event),
        motion_report(right, event=right_event),
    ]
    pair = [report["events"][0] for report in reports]
    changed = [
        key
        for key in (
            "source",
            "destination",
            "moved_instruction",
            "cost",
            "source_after",
            "destination_after",
        )
        if pair[0][key] != pair[1][key]
    ]
    return {
        "schema": "decomp-workbench-as1-motion-diff-v1",
        "left": reports[0],
        "right": reports[1],
        "changed": changed,
        "comparison_basis": "Caller-selected events; cross-capture identity unproved.",
    }
