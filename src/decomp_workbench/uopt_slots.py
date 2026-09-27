"""Trace IDO 5.3 temporary selection separately from emitted local-area demand.

Producer locations are compiler-profile coordinates, never C source lines.
Emulated pointers and descriptor fields are opaque identities, not final homes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .instrument_uopt import IDO_53_V12_SHA256

MARKER = "DKWB_UOPT_SLOTS_V1"
# Reviewed generated source with existing trace-only CDX/alias hooks.
REVIEWED_TRACE_PROFILE = (
    "769684842ada3f88032b89e0c90fb6096f6d9f575b997b1e3c8d2b1e520f0ea1"
)
PREFIX = "DKWB-SLOT "
HEADER = r"""
/* DKWB_UOPT_SLOTS_V1: observation only; never writes emulated state. */
#include <stdio.h>
#include <stdlib.h>
static int dkwb_slot_proc = -1;
static unsigned int dkwb_slot_request;
static const char *dkwb_slot_caller = "none";
static int dkwb_slot_on(void) {
    const char *p = getenv("DKWB_UOPT_SLOT_TRACE");
    return p && *p && *p != '0';
}
static void dkwb_slot_begin(uint8_t *mem, const char *path,
        uint32_t owner, uint32_t size, int index, int descriptor) {
    dkwb_slot_request++;
    if (!dkwb_slot_on()) return;
    fprintf(stderr, "DKWB-SLOT event=request proc=%d request=%u path=%s "
        "owner=0x%08x size=%u index=%d reserve=%u caller=%s "
        "raw_kind=%d raw_dtype=%d raw_sym=%d "
        "raw16=0x%08x raw20=0x%08x raw24=0x%08x raw28=0x%08x\n",
        dkwb_slot_proc, dkwb_slot_request, path, owner, size, index,
        MEM_U32(0x1001c4b4), dkwb_slot_caller,
        descriptor ? (int)MEM_U8(owner) : -1,
        descriptor ? (int)MEM_U8(owner + 1) : -1,
        descriptor ? (int)MEM_U16(owner + 2) : -1,
        descriptor ? MEM_U32(owner + 16) : 0,
        descriptor ? MEM_U32(owner + 20) : 0,
        descriptor ? MEM_U32(owner + 24) : 0,
        descriptor ? MEM_U32(owner + 28) : 0);
}
static void dkwb_slot_candidate(uint8_t *mem, const char *reason,
        uint32_t index, uint32_t slot, uint32_t available) {
    if (!dkwb_slot_on()) return;
    fprintf(stderr, "DKWB-SLOT event=candidate proc=%d request=%u "
        "reason=%s index=%u available=%u size=%d\n",
        dkwb_slot_proc, dkwb_slot_request, reason, index, available,
        slot ? (int)MEM_U32(slot + 8) : -1);
}
static void dkwb_slot_chosen(uint8_t *mem, uint32_t slot,
        uint32_t before, int reused) {
    if (!dkwb_slot_on()) return;
    fprintf(stderr, "DKWB-SLOT event=chosen proc=%d request=%u "
        "slot=0x%08x index=%u offset=%d size=%u reused=%d "
        "before=%u after=%u\n",
        dkwb_slot_proc, dkwb_slot_request, slot, MEM_U32(slot),
        (int32_t)MEM_U32(slot + 4), MEM_U32(slot + 8), reused,
        before, MEM_U32(0x1001c4b4));
}
static void dkwb_slot_home(uint8_t *mem, uint32_t record, uint32_t before,
        uint32_t descriptor, uint32_t color) {
    if (!dkwb_slot_on()) return;
    if (MEM_U8(record) == 0x6b) {
        fprintf(stderr, "DKWB-SLOT event=rlda proc=%d mtype=%u block=%u "
            "color_offset=%u address_offset=%d descriptor=0x%08x color=%u "
            "raw_kind=%u raw_dtype=%u raw_sym=%u\n",
            dkwb_slot_proc, MEM_U8(record + 1) >> 5, MEM_U32(record + 4),
            MEM_U32(record + 8), (int32_t)MEM_U32(record + 12), descriptor,
            color, MEM_U8(descriptor), MEM_U8(descriptor + 1),
            MEM_U16(descriptor + 2));
        return;
    }
    if (MEM_U8(record) != 0x6d && MEM_U8(record) != 0x70) return;
    fprintf(stderr, "DKWB-SLOT event=home proc=%d opcode=%u mtype=%u "
        "block=%u length=%u offset=%d before=%u after=%u\n",
        dkwb_slot_proc, MEM_U8(record), MEM_U8(record + 1) >> 5,
        MEM_U32(record + 4), MEM_U32(record + 8),
        (int32_t)MEM_U32(record + 12), before, MEM_U32(0x1001cc40));
}
"""

# Every anchor is unique and guarded, including on explicitly reviewed inputs.
PATCHES = (
    (
        "procedure",
        "//oneproc:\n",
        "//oneproc:\ndkwb_slot_proc++;\nif (dkwb_slot_on()) "
        'fprintf(stderr, "DKWB-SLOT event=procedure proc=%d\\n", '
        "dkwb_slot_proc);\n",
    ),
    (
        "spill locals",
        "//spilltemps:\n",
        "//spilltemps:\nuint32_t dkwb_spill_before = 0;\n",
    ),
    (
        "spill request",
        "L46da20:\n",
        "L46da20:\ndkwb_spill_before = MEM_U32(0x1001c4b4);\n"
        'dkwb_slot_caller = "spilltemps";\n'
        'dkwb_slot_begin(mem, "spill", MEM_U32(sp + 160), s0, '
        "(int)MEM_U32(sp + 188), 1);\n",
    ),
    (
        "spill conflict",
        "L46da48:\n",
        "L46da48:\ndkwb_slot_candidate(mem, "
        'v0 ? "conflict" : "size-check", s5, 0, v0 == 0);\n',
    ),
    (
        "spill size",
        "L46da70:\n",
        'L46da70:\ndkwb_slot_candidate(mem, "size", s5, v0, s0 == MEM_U32(v0 + 8));\n',
    ),
    (
        "spill chosen",
        "L46dbdc:\n",
        "L46dbdc:\ndkwb_slot_chosen(mem, MEM_U32(sp + 148), "
        "dkwb_spill_before, MEM_U8(sp + 155) != 0);\n",
    ),
    (
        "temporary request",
        "//gettemp:\n",
        "//gettemp:\nuint32_t dkwb_temp_before = MEM_U32(0x1001c4b4);\n"
        "int dkwb_temp_reused = 0;\n"
        'dkwb_slot_begin(mem, "temporary", a0, a1, -1, 0);\n',
    ),
    (
        "temporary candidate",
        "L47fd50:\n",
        'L47fd50:\ndkwb_slot_candidate(mem, "free-and-size", '
        "MEM_U32(v1), v1, MEM_U8(v1 + 12) != 0);\n",
    ),
    (
        "temporary reuse",
        "L47fd90:\n",
        "L47fd90:\ndkwb_temp_reused = v0 != 0;\n",
    ),
    (
        "temporary chosen",
        "L47feac:\n",
        "L47feac:\ndkwb_slot_chosen(mem, v1, dkwb_temp_before, dkwb_temp_reused);\n",
    ),
    (
        "home start",
        "//genrlodrstr:\n",
        "//genrlodrstr:\nuint32_t dkwb_home_before = MEM_U32(0x1001cc40);\n",
    ),
    (
        "home emission",
        "L4223e8:\n",
        "L4223e8:\ndkwb_slot_home(mem, s1, dkwb_home_before, s0, MEM_U32(sp + 52));\n",
    ),
    (
        "emitted Udef",
        "//uwrite:\n",
        "//uwrite:\nif (dkwb_slot_on() && MEM_U8(a0) == 0x1b && "
        "(MEM_U8(a0 + 1) >> 5) == 1) "
        'fprintf(stderr, "DKWB-SLOT event=udef proc=%d block=%u '
        'size=%u\\n", dkwb_slot_proc, MEM_U32(a0 + 4), '
        "MEM_U32(a0 + 8));\n",
    ),
)
CALLER_RETURNS = ("L4252e0", "L4255a4", "L4269cc", "L4269f8", "L426a14", "L430350")


@dataclass(frozen=True)
class SlotInstrumentation:
    source: str
    input_sha256: str
    profile: str = "ido-5.3-slots-v1"


def instrument_uopt_slots(
    source: str, *, allow_unverified_source: bool = False
) -> SlotInstrumentation:
    """Apply observation hooks only after profile and exact-anchor validation."""
    if MARKER in source:
        raise ValueError("source is already instrumented")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if not allow_unverified_source and digest not in {
        IDO_53_V12_SHA256,
        REVIEWED_TRACE_PROFILE,
    }:
        raise ValueError("source is not a pinned UOPT slot profile")
    patches = [("header", '#include "header.h"\n', '#include "header.h"\n' + HEADER)]
    patches.extend(PATCHES)
    for label in CALLER_RETURNS:
        old = f"f_gettemp(mem, sp, a0, a1);\ngoto {label};"
        patches.append((label, old, f'dkwb_slot_caller = "{label}";\n' + old))
    for label, old, new in patches:
        count = source.count(old)
        if count != 1:
            raise ValueError(f"slot anchor {label!r} occurred {count} times")
        source = source.replace(old, new, 1)
    return SlotInstrumentation(source, digest)


_FIELDS = {
    "procedure": {"proc"},
    "request": {
        "proc",
        "request",
        "path",
        "owner",
        "size",
        "index",
        "reserve",
        "caller",
        "raw_kind",
        "raw_dtype",
        "raw_sym",
        "raw16",
        "raw20",
        "raw24",
        "raw28",
    },
    "candidate": {"proc", "request", "reason", "index", "available", "size"},
    "chosen": {
        "proc",
        "request",
        "slot",
        "index",
        "offset",
        "size",
        "reused",
        "before",
        "after",
    },
    "home": {"proc", "opcode", "mtype", "block", "length", "offset", "before", "after"},
    "udef": {"proc", "block", "size"},
    "rlda": {
        "proc",
        "mtype",
        "block",
        "color_offset",
        "address_offset",
        "descriptor",
        "color",
        "raw_kind",
        "raw_dtype",
        "raw_sym",
    },
}
_TEXT_FIELDS = {"event", "path", "caller", "reason"}


def parse_slot_trace(text: str) -> dict[str, object]:
    """Reject partial/malformed producer records and unpaired requests.

    Ordinary compiler diagnostics can coexist with trace lines. Completeness is
    confined to the instrumented producers, never all allocator paths or homes.
    """
    events: list[dict[str, int | str]] = []
    procedures: set[int] = set()
    pending: dict[tuple[int, int], dict[str, int | str]] = {}
    completed: set[tuple[int, int]] = set()
    defined: set[int] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith(PREFIX):
            continue
        event: dict[str, int | str] = {}
        try:
            for field in line[len(PREFIX) :].split():
                key, value = field.split("=", 1)
                if key in event:
                    raise ValueError("duplicate field")
                event[key] = value if key in _TEXT_FIELDS else int(value, 0)
            kind = str(event.get("event", ""))
            if kind not in _FIELDS or set(event) != _FIELDS[kind] | {"event"}:
                raise ValueError("unknown event or incorrect fields")
            proc = int(event["proc"])
            if proc < 0:
                raise ValueError("missing procedure identity")
            if kind == "procedure":
                if proc in procedures or proc != len(procedures):
                    raise ValueError("duplicate or noncontiguous procedure")
                procedures.add(proc)
            elif proc not in procedures:
                raise ValueError("event precedes procedure")
            if kind in {"request", "candidate", "chosen"}:
                key_pair = (proc, int(event["request"]))
                if kind == "request":
                    if key_pair in pending or key_pair in completed:
                        raise ValueError("duplicate allocation request")
                    if (
                        event["path"] not in {"spill", "temporary"}
                        or int(event["size"]) <= 0
                    ):
                        raise ValueError("invalid allocation request")
                    pending[key_pair] = event
                elif key_pair not in pending:
                    raise ValueError("allocation event has no pending request")
                elif kind == "candidate":
                    if event["reason"] not in {
                        "conflict",
                        "size-check",
                        "size",
                        "free-and-size",
                    } or event["available"] not in {0, 1}:
                        raise ValueError("invalid candidate decision")
                elif kind == "chosen":
                    request = pending.pop(key_pair)
                    if (
                        event["size"] != request["size"]
                        or event["before"] != request["reserve"]
                    ):
                        raise ValueError("chosen slot disagrees with request")
                    if event["reused"] not in {0, 1} or int(event["after"]) < int(
                        event["before"]
                    ):
                        raise ValueError("invalid region growth/reuse")
                    if event["reused"] == 1 and event["before"] != event["after"]:
                        raise ValueError("reused slot grows region")
                    completed.add(key_pair)
            if kind == "udef":
                defined.add(proc)
            events.append(event)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"slot trace line {line_number}: {exc}") from exc
    if not events or pending or procedures != defined:
        raise ValueError(
            "incomplete slot trace: need procedures, chosen slots and local Udef"
        )
    return {
        "schema": "uopt-slot-trace-v1",
        "procedures": len(procedures),
        "allocation_requests": len(completed),
        "events": events,
        "claim_boundary": (
            "Producer-scoped allocation choices and emitted register-home/local-area "
            "demand. Neither slot offsets nor raw descriptor fields are final machine "
            "homes. Procedure ordinals require independent Uent mapping and full-TU "
            "OFF/ON fidelity; this report grants no matching credit."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    patch = commands.add_parser("instrument")
    patch.add_argument("source", type=Path)
    patch.add_argument("output", type=Path)
    patch.add_argument("--allow-unverified-source", action="store_true")
    report = commands.add_parser("report")
    report.add_argument("trace", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "instrument":
            if args.source.resolve() == args.output.resolve():
                raise ValueError("write to an isolated output, never overwrite input")
            result = instrument_uopt_slots(
                args.source.read_text(),
                allow_unverified_source=args.allow_unverified_source,
            )
            args.output.write_text(result.source)
            print(
                json.dumps(
                    {"profile": result.profile, "input_sha256": result.input_sha256}
                )
            )
        else:
            print(json.dumps(parse_slot_trace(args.trace.read_text()), indent=2))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
