"""Normal-mode CFE source operations joined to emitted Ucode intervals.

This is frontend provenance, not optimizer lineage or final stack ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .ucode import parse_ucode

SOURCE_SHA256 = "06f1d133e72f667ceed7de3d07511154467e32d71ee9aa9aaa773328a1b730f5"
MARKER = "DKWB_CFE_SOURCE_V1"
HEADER = r"""
/* DKWB_CFE_SOURCE_V1: read-only side channel for one pinned generated CFE. */
#include <stdio.h>
#include <stdlib.h>
static unsigned long long dkwb_cfe_written, dkwb_cfe_sequence;
static int dkwb_cfe_profile_sent;
static int dkwb_cfe_on(void) {
 const char *v=getenv("DKWB_CFE_SOURCE_TRACE");
 int enabled=v && *v && *v!='0';
 if(enabled && !dkwb_cfe_profile_sent) {
  fprintf(stderr,"DKWB-CFE profile=1 source_sha256="
          "06f1d133e72f667ceed7de3d07511154467e32d71ee9aa9aaa773328a1b730f5\n");
  dkwb_cfe_profile_sent=1;
 }
 return enabled;
}
static unsigned long long dkwb_cfe_cursor(uint8_t *mem) {
 uint32_t p=MEM_U32(0x1002f790);
 if(p<0x1002e790 || p>0x1002f790) return ~0ULL;
 return dkwb_cfe_written+p-0x1002e790;
}
static unsigned long long dkwb_cfe_begin(uint8_t *mem,const char *op,uint32_t d) {
 unsigned long long seq=++dkwb_cfe_sequence;
 if(!dkwb_cfe_on()) return seq;
 fprintf(stderr,"DKWB-CFE begin=%llu op=%s offset=%llu decl=%u",
         seq,op,dkwb_cfe_cursor(mem),d);
 if(d && MEM_U32(d+4)==0x63 && MEM_U32(d+24)) {
  uint32_t p=MEM_U32(d+24); unsigned i;
  fprintf(stderr," raw36=%d raw44=%u raw60=%u namehex=",
          (int32_t)MEM_U32(d+36),MEM_U32(d+44),MEM_U32(d+60));
  for(i=0;i<256 && MEM_U8(p+24+i);i++)
   fprintf(stderr,"%02x",(unsigned)MEM_U8(p+24+i));
  fprintf(stderr," truncated=%u",i==256);
 }
 fprintf(stderr,"\n");
 return seq;
}
static void dkwb_cfe_end(uint8_t *mem,unsigned long long seq) {
 if(dkwb_cfe_on()) fprintf(stderr,"DKWB-CFE end=%llu offset=%llu\n",
                         seq,dkwb_cfe_cursor(mem));
}
static void dkwb_cfe_write(uint32_t count) {
 dkwb_cfe_written+=count;
 if(dkwb_cfe_on()) fprintf(stderr,"DKWB-CFE written=%llu\n",dkwb_cfe_written);
}
"""


def _body(source: str, name: str) -> tuple[int, int]:
    pattern = rf"static (?:void|uint32_t|uint64_t) f_{name}\([^\n]*\) \{{\n"
    matches = list(re.finditer(pattern, source))
    if len(matches) != 1:
        raise ValueError(f"expected one function anchor for {name}")
    start = matches[0].end()
    return start, source.index("\n}\n", start)


def _instrument(source: str) -> str:
    """Apply structural anchors; public entry additionally requires exact hash."""
    if MARKER in source:
        raise ValueError("already instrumented")
    anchor = '#include "header.h"\n'
    if source.count(anchor) != 1:
        raise ValueError("expected one header anchor")
    result = source.replace(anchor, anchor + HEADER, 1)
    for name in ("load_var", "store_var", "load_addr"):
        start, end = _body(result, name)
        body = result[start:end]
        if "return;" not in body:
            raise ValueError(f"missing return anchor for {name}")
        body = (
            'unsigned long long dkwb_cfe_id=dkwb_cfe_begin(mem,"'
            + name
            + '",a0);\n'
            + body.replace("return;", "dkwb_cfe_end(mem,dkwb_cfe_id);\nreturn;")
        )
        result = result[:start] + body + result[end:]
    start, end = _body(result, "UWRITE")
    body = result[start:end]
    anchor = "return ((uint64_t)v0 << 32) | v1;"
    if body.count(anchor) != 1:
        raise ValueError("expected one UWRITE return anchor")
    body = body.replace(anchor, "dkwb_cfe_write(v0);\n" + anchor, 1)
    return result[:start] + body + result[end:]


OCCURRENCE_HEADER = r"""
/* Read-only AST construction and code-generation invocation receipts. */
static unsigned long long dkwb_cfe_node_seq, dkwb_cfe_occ_seq;
static int dkwb_cfe_occ_cap;
static void dkwb_cfe_node(uint8_t *mem,uint32_t p) {
 if (!dkwb_cfe_on()) return;
 if (!dkwb_cfe_occ_cap) {
  fprintf(stderr,"DKWB-CFE-OCC capability=1\n"); dkwb_cfe_occ_cap=1;
 }
 fprintf(stderr,"DKWB-CFE-OCC node=%llu ptr=%u node_id=%u tag=%u\n",
  ++dkwb_cfe_node_seq,p,MEM_U32(p),MEM_U32(p+4));
}
static unsigned long long dkwb_cfe_occ_begin(uint8_t *mem,uint32_t p) {
 unsigned long long n=++dkwb_cfe_occ_seq;
 if(dkwb_cfe_on()) fprintf(stderr,
  "DKWB-CFE-OCC begin=%llu ptr=%u node_id=%u offset=%llu\n",
  n,p,p ? MEM_U32(p) : 0,dkwb_cfe_cursor(mem));
 return n;
}
static void dkwb_cfe_output(uint8_t *mem,uint32_t p,uint32_t n) {
 uint32_t i;
 if(!dkwb_cfe_on()) return;
 fprintf(stderr,"DKWB-CFE-OCC output=%llu datahex=",dkwb_cfe_written-n);
 for(i=0;i<n;i++) fprintf(stderr,"%02x",(unsigned)MEM_U8(p+i));
 fprintf(stderr,"\n");
}
static void dkwb_cfe_occ_end(uint8_t *mem,unsigned long long n) {
 if(dkwb_cfe_on()) fprintf(stderr,"DKWB-CFE-OCC end=%llu offset=%llu\n",
  n,dkwb_cfe_cursor(mem));
}
"""


def _instrument_occurrences(source: str) -> str:
    result = _instrument(source)
    result = result.replace(HEADER, HEADER + OCCURRENCE_HEADER, 1)
    start, end = _body(result, "UWRITE")
    body = result[start:end]
    anchor = "dkwb_cfe_write(v0);"
    if body.count(anchor) != 1:
        raise ValueError("expected unique output observer")
    body = body.replace(anchor, anchor + "\ndkwb_cfe_output(mem,MEM_U32(sp+32),v0);", 1)
    result = result[:start] + body + result[end:]
    start, end = _body(result, "make")
    body = result[start:end]
    if body.count("return v0;") != 1:
        raise ValueError("expected one make return anchor")
    body = body.replace("return v0;", "dkwb_cfe_node(mem,v0);\nreturn v0;", 1)
    result = result[:start] + body + result[end:]
    start, end = _body(result, "expr_cg")
    body = result[start:end]
    if body.count("\nreturn;") != 1:
        raise ValueError("expected one expr_cg return anchor")
    body = "unsigned long long dkwb_occ=dkwb_cfe_occ_begin(mem,a0);\n" + body
    body = body.replace("\nreturn;", "\ndkwb_cfe_occ_end(mem,dkwb_occ);\nreturn;", 1)
    return result[:start] + body + result[end:]


def instrument(source: str, *, occurrences: bool = False) -> str:
    """Refuse all but the authenticated generated-source profile."""
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("CFE generated-source SHA-256 does not match pinned profile")
    return _instrument_occurrences(source) if occurrences else _instrument(source)


def join_trace(trace: str, ucode: bytes) -> dict[str, Any]:
    """Validate complete event pairs and exact stream-record boundaries.

    Declaration tokens are invocation-local opaque addresses, not portable IDs.
    Raw fields remain raw. Neither a matching name nor offset proves a home.
    """
    records = parse_ucode(ucode)
    boundaries = {record.word_offset * 4 for record in records} | {len(ucode)}
    opened: dict[int, dict[str, Any]] = {}
    seen: set[int] = set()
    stack: list[int] = []
    events: list[dict[str, Any]] = []
    written = 0
    writes = 0
    profile = False
    for line in trace.splitlines():
        if not line.startswith("DKWB-CFE "):
            continue
        fields: dict[str, str] = {}
        for token in line.split()[1:]:
            key, separator, value = token.partition("=")
            if not separator or key in fields:
                raise ValueError("malformed CFE record")
            fields[key] = value
        if "profile" in fields:
            if profile or fields != {"profile": "1", "source_sha256": SOURCE_SHA256}:
                raise ValueError("invalid or repeated CFE producer profile")
            profile = True
            continue
        if not profile:
            raise ValueError("missing CFE producer profile")
        if "written" in fields:
            if set(fields) != {"written"}:
                raise ValueError("malformed write record")
            current = int(fields["written"])
            if not written <= current <= len(ucode):
                raise ValueError("invalid cumulative write count")
            written, writes = current, writes + 1
        elif "begin" in fields:
            required = {"begin", "op", "offset", "decl"}
            named = {"raw36", "raw44", "raw60", "namehex", "truncated"}
            if set(fields) not in (required, required | named):
                raise ValueError("malformed begin record")
            seq, offset = int(fields["begin"]), int(fields["offset"])
            if seq <= 0 or seq in seen or offset not in boundaries:
                raise ValueError("invalid source event identity or boundary")
            if fields["op"] not in {"load_var", "store_var", "load_addr"}:
                raise ValueError("unknown source operation")
            event: dict[str, Any] = {
                "id": seq,
                "operation": fields["op"],
                "begin": offset,
                "declaration_token": int(fields["decl"]),
                "parent": stack[-1] if stack else None,
            }
            if not 0 <= event["declaration_token"] <= 0xFFFFFFFF:
                raise ValueError("invalid declaration token")
            if named <= fields.keys():
                raw_name = bytes.fromhex(fields["namehex"])
                if len(raw_name) > 256 or fields["truncated"] not in {"0", "1"}:
                    raise ValueError("invalid bounded source name")
                event.update(
                    name_bytes_hex=raw_name.hex(),
                    name_truncated=fields["truncated"] == "1",
                    raw_fields={
                        key: int(fields[key]) for key in ("raw36", "raw44", "raw60")
                    },
                )
            opened[seq] = event
            seen.add(seq)
            stack.append(seq)
        elif "end" in fields:
            if set(fields) != {"end", "offset"}:
                raise ValueError("malformed end record")
            seq, end = int(fields["end"]), int(fields["offset"])
            if not stack or stack.pop() != seq:
                raise ValueError("unbalanced source event")
            event = opened.pop(seq)
            if end not in boundaries or end < event["begin"]:
                raise ValueError("invalid emitted interval")
            event["end"] = end
            event["record_indices"] = [
                record.index
                for record in records
                if event["begin"] <= record.word_offset * 4 < end
            ]
            events.append(event)
        else:
            raise ValueError("unknown CFE trace record")
    if not profile or opened or not writes or written != len(ucode):
        raise ValueError("incomplete trace or Ucode stream length mismatch")
    return {
        "schema": "dkwb-cfe-source-v1",
        "profile_source_sha256": SOURCE_SHA256,
        "trace_sha256": hashlib.sha256(trace.encode()).hexdigest(),
        "ucode_sha256": hashlib.sha256(ucode).hexdigest(),
        "events": sorted(events, key=lambda item: item["id"]),
        "final_home_proof": False,
        "fidelity_proof": False,
        "limits": (
            "Frontend emission only; validate stock fidelity and capture pairing "
            "separately."
        ),
    }


def join_occurrences(trace: str, ucode: bytes) -> dict[str, Any]:
    """Join actual AST creation/occurrence intervals; no expression semantics."""
    report = join_trace(trace, ucode)
    records = parse_ucode(ucode)
    boundaries = {r.word_offset * 4 for r in records} | {len(ucode)}
    nodes: dict[int, tuple[int, int, int]] = {}
    node_ids: set[int] = set()
    stack: list[dict[str, Any]] = []
    seen: set[int] = set()
    occurrences: list[dict[str, Any]] = []
    source_parents: dict[int, int | None] = {}
    capability = False
    node_sequence = 0
    output = bytearray()
    written_cursor = 0
    for line in trace.splitlines():
        if line.startswith("DKWB-CFE written="):
            written_cursor = int(line.split()[1].split("=")[1])
        if line.startswith("DKWB-CFE begin="):
            source_parents[int(line.split()[1].split("=")[1])] = (
                stack[-1]["id"] if stack else None
            )
        if not line.startswith("DKWB-CFE-OCC "):
            continue
        if line.startswith("DKWB-CFE-OCC output="):
            tokens = line.split()
            if (
                not capability
                or len(tokens) != 3
                or not tokens[2].startswith("datahex=")
            ):
                raise ValueError("malformed output receipt")
            offset = int(tokens[1].split("=")[1])
            data = bytes.fromhex(tokens[2].split("=")[1])
            if (
                offset != len(output)
                or not data
                or offset + len(data) != written_cursor
            ):
                raise ValueError("invalid actual output interval")
            output.extend(data)
            continue
        fields: dict[str, int] = {}
        for token in line.split()[1:]:
            k, sep, v = token.partition("=")
            if not sep or k in fields:
                raise ValueError("malformed occurrence record")
            fields[k] = int(v)
        if "capability" in fields:
            if capability or fields != {"capability": 1}:
                raise ValueError("invalid occurrence capability")
            capability = True
            continue
        if not capability:
            raise ValueError("producer lacks occurrence observation")
        if "node" in fields:
            if set(fields) != {"node", "ptr", "node_id", "tag"}:
                raise ValueError("malformed node creation")
            if (
                fields["node"] != node_sequence + 1
                or not 0 < fields["ptr"] <= 0xFFFFFFFF
            ):
                raise ValueError("invalid node generation")
            if not 0 < fields["node_id"] <= 0xFFFFFFFF or fields["node_id"] in node_ids:
                raise ValueError("reused compiler node identity")
            node_sequence = fields["node"]
            node_ids.add(fields["node_id"])
            nodes[fields["ptr"]] = (fields["node_id"], node_sequence, fields["tag"])
        elif "begin" in fields:
            if set(fields) != {"begin", "ptr", "node_id", "offset"}:
                raise ValueError("malformed occurrence begin")
            node = nodes.get(fields["ptr"])
            if fields["ptr"] == 0 and fields["node_id"] == 0:
                node = (0, 0, 0)
            elif node is None or node[0] != fields["node_id"]:
                raise ValueError("missing or stale node generation")
            if (
                fields["begin"] <= 0
                or fields["begin"] in seen
                or fields["offset"] not in boundaries
            ):
                raise ValueError("invalid occurrence identity or boundary")
            seen.add(fields["begin"])
            stack.append(
                {
                    "id": fields["begin"],
                    "node_token": fields["ptr"],
                    "node_id": node[0],
                    "generation": node[1],
                    "raw_tag": node[2],
                    "begin": fields["offset"],
                    "parent": stack[-1]["id"] if stack else None,
                }
            )
        elif "end" in fields:
            if (
                set(fields) != {"end", "offset"}
                or not stack
                or stack[-1]["id"] != fields["end"]
            ):
                raise ValueError("unbalanced occurrence interval")
            event = stack.pop()
            if fields["offset"] not in boundaries or fields["offset"] < event["begin"]:
                raise ValueError("invalid occurrence interval")
            event["end"] = fields["offset"]
            event["record_indices"] = [
                r.index
                for r in records
                if event["begin"] <= r.word_offset * 4 < event["end"]
            ]
            occurrences.append(event)
        else:
            raise ValueError("unknown occurrence event")
    if not capability or stack or bytes(output) != ucode:
        raise ValueError("incomplete occurrence observation or CFE output mismatch")
    occurrence_map = {e["id"]: e for e in occurrences}
    for occurrence in occurrences:
        parent = occurrence_map.get(occurrence["parent"])
        if (
            parent
            and not parent["begin"]
            <= occurrence["begin"]
            <= occurrence["end"]
            <= parent["end"]
        ):
            raise ValueError("occurrence interval escapes parent")
    for event in report["events"]:
        event["occurrence"] = source_parents[event["id"]]
        parent = occurrence_map.get(event["occurrence"])
        if (
            parent
            and not parent["begin"] <= event["begin"] <= event["end"] <= parent["end"]
        ):
            raise ValueError("source interval escapes occurrence")
    report.update(
        occurrences=sorted(occurrences, key=lambda e: e["id"]),
        source_expression_semantics=False,
        actual_output_identity_proof=True,
        optimized_ownership_proof=False,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    patch = sub.add_parser("instrument")
    patch.add_argument("source", type=Path)
    patch.add_argument("output", type=Path)
    patch.add_argument("--occurrences", action="store_true")
    join = sub.add_parser("join")
    join.add_argument("trace", type=Path)
    join.add_argument("ucode", type=Path)
    join.add_argument("--occurrences", action="store_true")
    args = parser.parse_args()
    if args.command == "instrument":
        if args.source.resolve() == args.output.resolve():
            parser.error("output must not replace the original compiler source")
        args.output.write_text(
            instrument(args.source.read_text(), occurrences=args.occurrences)
        )
    else:
        print(
            json.dumps(
                (join_occurrences if args.occurrences else join_trace)(
                    args.trace.read_text(), args.ucode.read_bytes()
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
