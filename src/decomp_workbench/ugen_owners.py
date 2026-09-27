"""Join UGEN address owners to retained Ucode and binASM records.

Only actual producer identities are joined. Equal draw counts and equal words
at different sites never establish ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from itertools import pairwise
from pathlib import Path
from typing import Any

from .instrument_ugen_owners import UGEN_SHA256
from .ucode import parse_ucode

WORDS = {f"w{i}" for i in range(8)}
FIELDS = {
    "NEW": {"serial", "node", "id"},
    "READ": {"serial", "ptr", "node", "id"} | WORDS,
    "INPUT": {"serial", "ptr", "node", "id"} | WORDS,
    "BUILD": {"serial", "ptr", "node", "id"} | WORDS,
    "DEST": {"serial", "node", "id", "hint", "reg", "node_reg"},
    "EMIT": {
        "serial",
        "site",
        "node",
        "id",
        "epoch",
        "emit",
        "op",
        "reg",
        "symbol",
        "addend",
        "extra",
        "node_op",
        "node_symbol",
        "node_addend",
        "node_reg",
    },
    "OUTPUT": {"serial", "epoch", "forward", "backward"},
    "CONCAT": {"serial"},
}
SITES = {
    f"{name}-{i}"
    for name, count in [("f_loadstore", 3), ("f_eval_mov", 2), ("f_eval", 2)]
    for i in range(count)
}


def _words(row: dict[str, Any]) -> list[int]:
    return [row[f"w{i}"] for i in range(8)]


def parse_owner_trace(text: str) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    profile = False
    for line in text.splitlines():
        if not line.startswith("DKWB-OWNER-"):
            if "DKWB-OWNER-" in line:
                raise ValueError("interleaved owner record; capture stderr separately")
            continue
        tokens = line.split()
        kind = tokens[0].removeprefix("DKWB-OWNER-")
        fields: dict[str, Any] = {}
        for token in tokens[1:]:
            key, sep, value = token.partition("=")
            if not sep or not value or key in fields:
                raise ValueError("malformed or duplicate owner field")
            if key in {"site", "source_sha256"}:
                fields[key] = value
            else:
                if not value.isascii() or not value.isdecimal():
                    raise ValueError("owner fields must be unsigned decimal")
                fields[key] = int(value)
                if fields[key] > 0xFFFFFFFF and key != "serial":
                    raise ValueError("owner field exceeds producer width")
        if kind == "PROFILE":
            if (
                profile
                or rows
                or fields != {"version": 1, "source_sha256": UGEN_SHA256}
            ):
                raise ValueError("unsupported or duplicate owner profile")
            profile = True
            continue
        if not profile or kind not in FIELDS or fields.keys() != FIELDS[kind]:
            raise ValueError("unknown owner record, fields or producer")
        if fields["serial"] != len(rows) + 1:
            raise ValueError("missing, duplicated or reordered owner record")
        if kind == "EMIT" and (
            fields["site"] not in SITES or fields["emit"] < 1 or fields["reg"] > 127
        ):
            raise ValueError("unsupported owner emission site or register")
        rows.append((kind, fields))
    return rows


def external_dense_symbols(data: bytes) -> dict[int, str]:
    """Read only external DNR names from a retained big-endian IDO .T file.

    Local dense entries remain unresolved. This is the on-disk equivalent of
    st_pdn_idn -> st_psym_ifd_isym -> st_str_extiss, not an ELF symbol order.
    """
    if len(data) < 96:
        raise ValueError("truncated IDO symbol header")
    header = struct.unpack_from(">HH23I", data)
    if header[0] != 0x7009:
        raise ValueError("unsupported IDO symbol-table magic/byte order")
    dense_count, dense_offset = header[5:7]
    string_count, string_offset = header[17:19]
    external_count, external_offset = header[23:25]
    ranges = []
    for offset, count, stride in [
        (dense_offset, dense_count, 8),
        (string_offset, string_count, 1),
        (external_offset, external_count, 16),
    ]:
        end = offset + count * stride
        if count and (offset < 96 or end > len(data)):
            raise ValueError("IDO symbol-table extent outside file")
        if count:
            ranges.append((offset, end))
    ranges.sort()
    if any(a[1] > b[0] for a, b in pairwise(ranges)):
        raise ValueError("overlapping IDO symbol-table extents")
    names = {}
    for dense in range(dense_count):
        file_index, index = struct.unpack_from(">II", data, dense_offset + dense * 8)
        if file_index != 0x7FFFFFFF:
            continue
        if index >= external_count:
            raise ValueError("external dense index out of range")
        string_index = struct.unpack_from(">I", data, external_offset + index * 16 + 4)[
            0
        ]
        if string_index >= string_count:
            raise ValueError("external string index out of range")
        start = string_offset + string_index
        end = data.find(b"\0", start, string_offset + string_count)
        if end < 0:
            raise ValueError("unterminated external symbol name")
        names[dense] = data[start:end].decode("utf-8", errors="strict")
    return names


def owner_report(
    text: str,
    *,
    ucode: bytes | None = None,
    binasm: bytes | None = None,
    symbols: bytes | None = None,
) -> dict[str, Any]:
    rows = parse_owner_trace(text)
    reads = [row for kind, row in rows if kind == "READ"]
    records = parse_ucode(ucode) if ucode is not None else None
    if records is not None:
        if len(records) != len(reads):
            raise ValueError("retained Ucode/read count differs")
        for retained_record, observed_read in zip(records, reads, strict=True):
            if list(retained_record.words[:2]) != _words(observed_read)[:2]:
                raise ValueError("retained Ucode/read prefix differs")
    names = external_dense_symbols(symbols) if symbols is not None else {}
    read_index = {row["serial"]: index for index, row in enumerate(reads)}
    latest_read: dict[int, dict[str, Any]] = {}
    owners: dict[int, dict[str, Any]] = {}
    emissions = []
    outputs = []
    concat = []
    for kind, row in rows:
        if kind == "READ":
            latest_read[row["ptr"]] = row
            continue
        if kind == "NEW":
            previous = owners.get(row["node"])
            if previous and previous["input"] is not None and previous["build"] is None:
                raise ValueError("node reused before pending tree copy completed")
            owners[row["node"]] = {
                "id": row["id"],
                "generation": row["serial"],
                "input": None,
                "build": None,
                "dest": None,
            }
            continue
        if kind == "OUTPUT":
            outputs.append(row)
            continue
        if kind == "CONCAT":
            concat.append(row)
            continue
        owner = owners.get(row["node"])
        if owner is None or owner["id"] != row["id"]:
            raise ValueError("owner node lacks current allocation identity")
        if (
            kind in {"DEST", "EMIT"}
            and owner["input"] is not None
            and owner["build"] is None
        ):
            raise ValueError("owner used before pending tree copy completed")
        if kind == "INPUT":
            if owner["input"] is not None:
                raise ValueError("duplicate node input")
            read = latest_read.get(row["ptr"])
            exact = read is not None and _words(read) == _words(row)
            owner["input"] = {
                "row": row,
                "read": read if exact else None,
                "status": "read-record-exact"
                if exact
                else "unresolved-mutated-or-unread-input",
            }
        elif kind == "BUILD":
            incoming = owner["input"]
            if (
                incoming is None
                or owner["build"] is not None
                or row["ptr"] != row["node"] + 32
                or _words(row) != _words(incoming["row"])
            ):
                raise ValueError("tree copy lacks matching input record")
            owner["build"] = row
        elif kind == "DEST":
            if row["reg"] != row["node_reg"]:
                raise ValueError("destination and stored node register conflict")
            owner["dest"] = row
        elif kind == "EMIT":
            incoming = owner["input"]
            read = incoming["read"] if incoming else None
            index = read_index[read["serial"]] if read else None
            record = (
                records[index] if records is not None and index is not None else None
            )
            if (
                record is not None
                and read is not None
                and record.name == "rlda"
                and list(record.words) != _words(read)[:4]
            ):
                raise ValueError("retained rlda operands differ from input record")
            binding = {
                "status": incoming["status"]
                if incoming
                else "unresolved-no-build-u-origin",
                "retained_operand_verification": (
                    "not-supplied"
                    if records is None
                    else "unresolved"
                    if record is None
                    else "full"
                    if record.name == "rlda"
                    else "prefix-only"
                ),
                "read_index": index,
                "read_serial": read["serial"] if read else None,
                "ucode_word_offset": record.word_offset if record else None,
                "opcode": record.name if record else None,
            }
            assigned = (
                record.words[2]
                if record is not None and record.name == "rlda"
                else None
            )
            dest = owner["dest"]
            if row["site"].startswith("f_eval-") and (
                dest is None or dest["reg"] != row["reg"]
            ):
                raise ValueError("eval address lacks matching get_dest result")
            emissions.append(
                {
                    **row,
                    "generation": owner["generation"],
                    "symbol_name": names.get(row["symbol"]),
                    "input": binding,
                    "input_assigned_register": assigned,
                    "get_dest": dest,
                    "binasm_record": None,
                }
            )
    if any(
        owner["input"] is not None and owner["build"] is None
        for owner in owners.values()
    ):
        raise ValueError("truncated tree input/copy pair")
    if binasm is not None:
        if (
            len(concat) != 1
            or not outputs
            or concat[0]["serial"] < outputs[-1]["serial"]
        ):
            raise ValueError("missing final UGEN concatenation boundary")
        # Authenticated main path emits procedure bodies first, then declarations,
        # and concatenates body file after declaration file. Each output writes
        # backward records before forward records.
        ordered = [outputs[-1], *outputs[:-1]]
        base = 0
        epochs = {}
        for output in ordered:
            if output["epoch"] in epochs:
                raise ValueError("duplicate output epoch")
            epochs[output["epoch"]] = (base + output["backward"], output["forward"])
            base += output["forward"] + output["backward"]
        if base * 16 != len(binasm):
            raise ValueError("retained binASM extent differs from output batches")
        for row in emissions:
            epoch = epochs.get(row["epoch"])
            if epoch is None or row["emit"] > epoch[1]:
                raise ValueError("emission outside authenticated output epoch")
            index = epoch[0] + row["emit"] - 1
            words = struct.unpack_from(">4I", binasm, index * 16)
            expected = (
                row["symbol"],
                0x170000 | (row["op"] << 1),
                (row["reg"] << 25) | 0x1204000 | (row["extra"] & 0x3FFF),
                row["addend"],
            )
            if words != expected:
                raise ValueError("retained binASM address record differs from emission")
            row["binasm_record"] = index
    return {
        "profile": "ugen-operand-owners-v1",
        "source_sha256": UGEN_SHA256,
        "retained_sha256": {
            name: hashlib.sha256(data).hexdigest() if data is not None else None
            for name, data in [
                ("ucode", ucode),
                ("binasm", binasm),
                ("symbols", symbols),
            ]
        },
        "read_count": len(reads),
        "emission_count": len(emissions),
        "emissions": emissions,
        "limits": [
            "Node identity uses allocation generation, not draw counts or "
            "raw pointer equality across runs.",
            "rlda register assignment precedes UGEN; no UOPT color reason "
            "or original C identity is inferred.",
            "Symbol names describe this retained table, not cross-overlay "
            "target identity.",
            "Only seven f_emit_ra sites are owned; other emitters, copied "
            "trees and final stack homes remain outside scope.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    for name in ("ucode", "binasm", "symbols"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args(argv)
    try:
        report = owner_report(
            args.trace.read_text(),
            **{
                name: getattr(args, name).read_bytes() if getattr(args, name) else None
                for name in ("ucode", "binasm", "symbols")
            },
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
