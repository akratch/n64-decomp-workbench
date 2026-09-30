"""Join observed spill-slot emissions to retained Ucode and concrete UGEN operands.

This reports UGEN binASM ownership, not an AS1 instruction-offset map or a
source-expression identity. No equality search establishes ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .ucode import parse_ucode
from .ugen_owners import owner_report, parse_owner_trace

FIELDS = {
    "WRITE": {"write", "proc"} | {f"w{i}" for i in range(8)},
    "SPILL": {"write", "proc", "slot", "index", "offset", "size", "enabled"},
    "FRAME": {"owner_serial", "node", "virtual", "frame", "mode", "result"},
    "MEM": {
        "owner_serial",
        "node",
        "epoch",
        "emit",
        "op",
        "reg",
        "base",
        "displacement",
        "extra",
    },
}
SIGNED = {"proc", "offset", "virtual", "result", "displacement"}


def parse_home_trace(text: str) -> list[tuple[str, dict[str, int]]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("DKWB-HOME-"):
            if "DKWB-HOME-" in line:
                raise ValueError("interleaved home record")
            continue
        tag, *tokens = line.split()
        kind = tag.removeprefix("DKWB-HOME-")
        row = {}
        for token in tokens:
            key, sep, value = token.partition("=")
            if not sep or key in row or not value or not value.lstrip("-").isdecimal():
                raise ValueError("malformed home field")
            number = int(value)
            if not (
                -(1 << 31) <= number < (1 << 31)
                if key in SIGNED
                else 0 <= number <= 0xFFFFFFFF
            ):
                raise ValueError("home field exceeds producer width")
            row[key] = number
        if kind not in FIELDS or row.keys() != FIELDS[kind]:
            raise ValueError("unknown home record or fields")
        rows.append((kind, row))
    return rows


def _words(row: dict[str, int]) -> list[int]:
    return [row[f"w{i}"] for i in range(8)]


def stack_home_report(text: str, *, ucode: bytes, binasm: bytes) -> dict[str, Any]:
    # Reuse strict owner lifetime/output checks; own memory operands below
    # require complete four-word verification rather than prefix-only matching.
    owner_report(text, ucode=ucode, binasm=binasm)
    owner_rows = parse_owner_trace(text)
    home_rows = parse_home_trace(text)
    records = parse_ucode(ucode)
    writes = [r for k, r in home_rows if k == "WRITE"]
    if len(writes) != len(records):
        raise ValueError("writer/retained record count differs")
    record_procs = []
    current_proc = -1
    write_positions = {}
    read_positions: dict[int, int] = {}
    for position, line in enumerate(text.splitlines()):
        if line.startswith("DKWB-HOME-WRITE "):
            fields = dict(token.partition("=")[::2] for token in line.split()[1:])
            write_positions[int(fields["write"])] = position
        elif line.startswith("DKWB-OWNER-READ "):
            read_positions[len(read_positions)] = position
    for index, (row, rec) in enumerate(zip(writes, records, strict=True)):
        if rec.name == "ent":
            current_proc += 1
        record_procs.append(current_proc)
        if row["write"] != index or _words(row)[:2] != list(rec.words[:2]):
            raise ValueError("writer ordinal or retained prefix differs")
        if row["proc"] != current_proc:
            raise ValueError("writer procedure differs from retained Ucode boundary")
        if write_positions.get(index, len(text.splitlines())) >= read_positions.get(
            index, -1
        ):
            raise ValueError("Ucode reader precedes matching writer event")
    spills = {}
    for kind, row in home_rows:
        if kind != "SPILL" or not row["enabled"]:
            continue
        index = row["write"]
        if index >= len(records) or index in spills:
            raise ValueError("invalid or duplicate spill ordinal")
        rec = records[index]
        if row["proc"] != writes[index]["proc"] or row["proc"] != record_procs[index]:
            raise ValueError("spill and writer procedure identity differs")
        if rec.name not in {"lod", "str"} or len(rec.words) != 4:
            raise ValueError("spill is not supported direct memory record")
        if (
            list(rec.words) != _words(writes[index])[:4]
            or rec.mtype != 1
            or rec.words[2] != row["size"]
            or rec.words[3] != row["offset"] & 0xFFFFFFFF
        ):
            raise ValueError("spill slot and emitted operand differ")
        spills[index] = row
    reads = [r for k, r in owner_rows if k == "READ"]
    read_indices = {r["serial"]: i for i, r in enumerate(reads)}
    snapshots: dict[int, dict[int, dict[str, Any]]] = {}
    nodes: dict[int, dict[str, Any]] = {}
    latest_read: dict[int, dict[str, int]] = {}
    outputs = []
    for kind, row in owner_rows:
        if kind == "READ":
            latest_read[row["ptr"]] = row
        elif kind == "NEW":
            nodes[row["node"]] = {"generation": row["serial"], "read": None}
        elif kind == "INPUT":
            read = latest_read.get(row["ptr"])
            read_index = read_indices.get(read["serial"]) if read else None
            record = records[read_index] if read_index is not None else None
            exact = (
                read is not None
                and record is not None
                and _words(read)[: len(record.words)]
                == _words(row)[: len(record.words)]
            )
            nodes[row["node"]]["read"] = read if exact else None
        elif kind == "BUILD":
            nodes[row["node"]]["built"] = True
        elif kind == "OUTPUT":
            outputs.append(row)
        snapshots[row["serial"]] = {n: dict(v) for n, v in nodes.items()}
    if not outputs:
        raise ValueError("missing output batches")
    epochs = {}
    base = 0
    for output in [outputs[-1], *outputs[:-1]]:
        epochs[output["epoch"]] = (base + output["backward"], output["forward"])
        base += output["forward"] + output["backward"]
    if base * 16 != len(binasm):
        raise ValueError("output batch extent differs")
    frames = {}
    chains = []
    unresolved = []
    emitted = set()
    for kind, row in home_rows:
        if kind == "FRAME":
            frames[(row["owner_serial"], row["node"])] = row
        if kind != "MEM":
            continue
        epoch = epochs.get(row["epoch"])
        if not epoch or not 1 <= row["emit"] <= epoch[1]:
            raise ValueError("memory emitter outside output batch")
        emission_key = row["epoch"], row["emit"]
        if emission_key in emitted:
            raise ValueError("duplicate memory emitter claim")
        emitted.add(emission_key)
        output_index = epoch[0] + row["emit"] - 1
        actual = struct.unpack_from(">4I", binasm, output_index * 16)
        expected = (
            0,
            0x170000 | row["op"] << 1,
            row["reg"] << 25 | row["base"] << 18 | row["extra"] & 0x3FFF,
            row["displacement"] & 0xFFFFFFFF,
        )
        if actual != expected:
            raise ValueError("concrete memory emitter differs from retained binASM")
        key = row["owner_serial"], row["node"]
        state = snapshots.get(key[0], {}).get(key[1])
        frame = frames.get(key)
        if state and not state.get("built"):
            raise ValueError("memory node used before tree copy completed")
        if not state or not state.get("built") or not state["read"]:
            unresolved.append({"reason": "no exact retained node origin", **row})
            continue
        read = state["read"]
        index = read_indices[read["serial"]]
        record = records[index]
        if record.name not in {"lod", "str"} or len(record.words) != 4:
            unresolved.append({"reason": "non-direct memory origin", **row})
            continue
        if list(record.words) != _words(read)[:4]:
            raise ValueError("retained memory operands differ")
        if frame is None or frame["virtual"] & 0xFFFFFFFF != record.words[3]:
            raise ValueError("frame result lacks exact memory operand")
        if frame["result"] != row["displacement"]:
            # Nonzero explicit f_loadstore addend needs a separate producer hook.
            unresolved.append({"reason": "additional loadstore displacement", **row})
            continue
        chains.append(
            {
                "read_index": index,
                "ucode_word_offset": record.word_offset,
                "node_generation": state["generation"],
                "binASM_index": output_index,
                "slot": spills.get(index),
                "frame": frame,
                "emission": row,
            }
        )
    linked = {c["read_index"] for c in chains if c["slot"]}
    return {
        "schema": "decomp-workbench-stack-homes-v1",
        "ucode_sha256": hashlib.sha256(ucode).hexdigest(),
        "binasm_sha256": hashlib.sha256(binasm).hexdigest(),
        "writer_records": len(writes),
        "slot_emissions": len(spills),
        "chains": chains,
        "unresolved": unresolved,
        "unjoined_slot_emissions": [r for i, r in spills.items() if i not in linked],
        "limits": [
            "No source-expression identity",
            "No AS1 final instruction-offset ownership",
            "Allocated slots without actual memory emission have no home claim",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--ucode", type=Path, required=True)
    p.add_argument("--binasm", type=Path, required=True)
    args = p.parse_args(argv)
    print(
        json.dumps(
            stack_home_report(
                args.trace.read_text(),
                ucode=args.ucode.read_bytes(),
                binasm=args.binasm.read_bytes(),
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
