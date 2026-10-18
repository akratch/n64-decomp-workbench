"""Pinned observations of unchanged input LDA construction, before optimization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .cfe_source import join_occurrences
from .ucode import parse_ucode

SOURCE_SHA256 = "b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f"
MARKER = "DKWB_LDA_INPUT_V1"
HEADER = r"""
/* DKWB_LDA_INPUT_V1: native side channel, never changes compiler memory. */
#include <stdio.h>
#include <stdlib.h>
static unsigned long long dkwb_lda_read, dkwb_lda_generation, dkwb_lda_origin;
static unsigned dkwb_lda_depth, dkwb_lda_peeking;
static unsigned long long dkwb_lda_pass,dkwb_lda_word_count;
static int dkwb_lda_cap;
static int dkwb_lda_on(void) {
 const char *v=getenv("DKWB_LDA_INPUT_TRACE");
 int on=v && *v && *v!='0';
 if(on && !dkwb_lda_cap) {
  fprintf(stderr,"DKWB-LDA capability=1 source_sha256="
   "b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f\n");
  dkwb_lda_cap=1;
 }
 return on;
}
static void dkwb_lda_words(uint8_t *mem,const char *kind,uint32_t p) {
 unsigned i;
 if(!dkwb_lda_on()) return;
 fprintf(stderr,"DKWB-LDA kind=%s read=%llu",kind,dkwb_lda_read);
 for(i=0;i<8;i++) fprintf(stderr," w%u=%u",i,MEM_U32(p+4*i));
 fprintf(stderr,"\n");
}
static void dkwb_lda_newpass(void) {
 ++dkwb_lda_pass;dkwb_lda_word_count=0;
 if(dkwb_lda_on()) fprintf(stderr,"DKWB-LDA pass=%llu\n",dkwb_lda_pass);
}
static void dkwb_lda_word(uint32_t value) {
 if(dkwb_lda_peeking) return;
 ++dkwb_lda_word_count;
 if(dkwb_lda_on()) fprintf(stderr,
 "DKWB-LDA word=%llu pass=%llu value=%u\n",
 dkwb_lda_word_count,dkwb_lda_pass,value);
}
static void dkwb_lda_peekresult(uint32_t result) {
 --dkwb_lda_peeking;
 if(dkwb_lda_on()) fprintf(stderr,
 "DKWB-LDA peek_result=%u pass=%llu offset=%llu\n",
 result,dkwb_lda_pass,dkwb_lda_word_count);
}
static void dkwb_lda_record(uint8_t *mem,unsigned long long start,uint32_t p) {
 ++dkwb_lda_read;
 if(dkwb_lda_on()) fprintf(stderr,
 "DKWB-LDA record=%llu pass=%llu start=%llu end=%llu\n",
 dkwb_lda_read,dkwb_lda_pass,start,dkwb_lda_word_count);
 dkwb_lda_words(mem,"READ",p);
}
static void dkwb_lda_alloc(uint32_t p) {
 ++dkwb_lda_generation;
 if(dkwb_lda_on()) fprintf(stderr,"DKWB-LDA alloc=%llu ptr=%u\n",dkwb_lda_generation,p);
}
static void dkwb_lda_dead(uint32_t p) {
 if(dkwb_lda_on()) fprintf(stderr,"DKWB-LDA dead=%u\n",p);
}
static void dkwb_lda_construct(uint8_t *mem) {
 unsigned i;uint32_t p=MEM_U32(MEM_U32(0x1001c4a8));
 if(!dkwb_lda_on()) return;
 fprintf(stderr,"DKWB-LDA construct=%llu current=%llu depth=%u ptr=%u kind=%u",
 dkwb_lda_origin,dkwb_lda_read,dkwb_lda_depth,p,MEM_U8(p));
 for(i=0;i<8;i++) fprintf(stderr," w%u=%u",i,MEM_U32(0x10011ff0+4*i));
 fprintf(stderr,"\n");
}
"""


def _body(source: str, name: str) -> tuple[int, int]:
    matches = list(
        re.finditer(r"^static [^\n]*\b" + name + r"\([^\n]+\) \{\n", source, re.M)
    )
    if len(matches) != 1:
        raise ValueError("expected unique function anchor: " + name)
    return matches[0].end(), source.index("\n}\n", matches[0].end())


def _edit(source: str, name: str, old: str, new: str) -> str:
    start, end = _body(source, name)
    body = source[start:end]
    if body.count(old) != 1:
        raise ValueError("expected unique mutation anchor: " + name)
    return source[:start] + body.replace(old, new, 1) + source[end:]


def _instrument(source: str) -> str:
    if MARKER in source or source.count('#include "header.h"\n') != 1:
        raise ValueError("missing header or already instrumented")
    result = source.replace(
        '#include "header.h"\n', '#include "header.h"\n' + HEADER, 1
    )
    result = _edit(
        result,
        "f_ugetinit",
        "\nreturn;",
        "\ndkwb_lda_newpass();\nreturn;",
    )
    result = _edit(
        result,
        "f_ugetint",
        "\nreturn v0;",
        "\ndkwb_lda_word(v0);\nreturn v0;",
    )
    start, _end = _body(result, "f_ugeteof")
    result = result[:start] + "++dkwb_lda_peeking;\n" + result[start:]
    result = _edit(
        result,
        "f_ugeteof",
        "\nreturn v0;",
        "\ndkwb_lda_peekresult(v0);\nreturn v0;",
    )
    start, _end = _body(result, "f_readuinstr")
    result = (
        result[:start]
        + "unsigned long long dkwb_record_start=dkwb_lda_word_count;\n"
        + result[start:]
    )
    result = _edit(
        result,
        "f_readuinstr",
        "\nreturn;",
        "\ndkwb_lda_record(mem,dkwb_record_start,s2);\nreturn;",
    )
    result = _edit(
        result,
        "f_getop",
        "\nreturn;",
        '\ndkwb_lda_words(mem,"GETOP",0x10011ff0);\nreturn;',
    )
    start, _end = _body(result, "f_readnxtinst")
    prefix = (
        "unsigned long long dkwb_saved_origin=dkwb_lda_origin;\n"
        "dkwb_lda_origin=dkwb_lda_read;\n++dkwb_lda_depth;\n"
    )
    result = result[:start] + prefix + result[start:]
    result = _edit(
        result,
        "f_readnxtinst",
        "\nreturn;",
        "\n--dkwb_lda_depth;\ndkwb_lda_origin=dkwb_saved_origin;\nreturn;",
    )
    result = _edit(
        result,
        "f_readnxtinst",
        "func_43e3a8(mem, sp, a0);\ngoto L441664;",
        "func_43e3a8(mem, sp, a0);\ndkwb_lda_construct(mem);\ngoto L441664;",
    )
    result = _edit(
        result,
        "f_appendchain",
        "MEM_U16(v1 + 8) = (uint16_t)t0;\nL4855f8:",
        "MEM_U16(v1 + 8) = (uint16_t)t0;\ndkwb_lda_alloc(v1);\nL4855f8:",
    )
    return _edit(
        result,
        "f_delentry",
        "MEM_U8(a0 + 0) = (uint8_t)t8;",
        "MEM_U8(a0 + 0) = (uint8_t)t8;\ndkwb_lda_dead(a0);",
    )


def instrument(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("UOPT generated-source SHA-256 does not match pinned profile")
    return _instrument(source)


def _fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line.split()[1:]:
        k, sep, v = token.partition("=")
        if not sep or k in fields:
            raise ValueError("malformed LDA event")
        fields[k] = v
    return fields


def join_trace(trace: str, ucode: bytes, *, cfe_trace: str) -> dict[str, Any]:
    """Prove only input-stage identity; never infer optimized ownership."""
    frontend = join_occurrences(cfe_trace, ucode)
    records = parse_ucode(ucode)
    stream_words = tuple(
        int.from_bytes(ucode[i : i + 4], "big") for i in range(0, len(ucode), 4)
    )
    by_offset = {r.word_offset: r for r in records}
    input_records: dict[int, int] = {}
    record_spans: dict[int, tuple[int, int, int]] = {}
    pass_words: dict[int, int] = {}
    current_pass = 0
    pass_record_end: dict[int, int] = {}
    pending_peek: tuple[int, int] | None = None
    procedure = -1
    record_procs: dict[int, int] = {}
    for record in records:
        if record.name == "ent":
            procedure += 1
        record_procs[record.index] = procedure
    reads: dict[int, tuple[int, ...]] = {}
    selected: dict[int, tuple[int, ...]] = {}
    live: dict[int, int] = {}
    used: set[int] = set()
    chains: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    capability = False
    generation = 0
    words_keys = {f"w{i}" for i in range(8)}
    for line in trace.splitlines():
        if not line.startswith("DKWB-LDA "):
            continue
        f = _fields(line)
        if "capability" in f:
            if capability or f != {"capability": "1", "source_sha256": SOURCE_SHA256}:
                raise ValueError("invalid LDA producer capability")
            capability = True
            continue
        if not capability:
            raise ValueError("producer lacks LDA observation")
        if "pass" in f and set(f) == {"pass"}:
            if current_pass and (
                pass_words[current_pass] != len(stream_words)
                or pass_record_end[current_pass] != len(stream_words)
                or pending_peek is not None
            ):
                raise ValueError("incomplete input pass")
            if int(f["pass"]) != current_pass + 1:
                raise ValueError("invalid input pass")
            current_pass += 1
            pass_words[current_pass] = 0
            pass_record_end[current_pass] = 0
        elif "peek_result" in f:
            if (
                set(f) != {"peek_result", "pass", "offset"}
                or int(f["pass"]) != current_pass
                or int(f["offset"]) != pass_words[current_pass]
            ):
                raise ValueError("invalid lookahead observation")
            if (
                pending_peek is not None
                or int(f["peek_result"]) not in {0, 1}
                or (int(f["peek_result"]) == 1)
                != (pass_words[current_pass] == len(stream_words))
            ):
                raise ValueError("invalid EOF observation")
            pending_peek = (int(f["offset"]), int(f["peek_result"]))
        elif "word" in f:
            if (
                set(f) != {"word", "pass", "value"}
                or int(f["pass"]) != current_pass
                or not current_pass
            ):
                raise ValueError("malformed consumed word")
            offset = pass_words[current_pass]
            if (
                int(f["word"]) != offset + 1
                or offset >= len(stream_words)
                or int(f["value"]) != stream_words[offset]
            ):
                raise ValueError("input stream mismatch")
            pass_words[current_pass] += 1
        elif "record" in f:
            if (
                set(f) != {"record", "pass", "start", "end"}
                or int(f["record"]) != len(record_spans) + 1
            ):
                raise ValueError("invalid read generation")
            start, end = int(f["start"]), int(f["end"])
            if (
                int(f["pass"]) != current_pass
                or end != pass_words[current_pass]
                or start != pass_record_end[current_pass]
                or pending_peek != (start, int(start == end))
            ):
                raise ValueError("invalid consumed record span")
            if start == end:
                if end != len(stream_words):
                    raise ValueError("ambiguous empty record span")
            else:
                span_record = by_offset.get(start)
                if span_record is None or end != start + len(span_record.words):
                    raise ValueError("record boundary mismatch")
                input_records[int(f["record"])] = span_record.index
            record_spans[int(f["record"])] = (current_pass, start, end)
            pass_record_end[current_pass] = end
            pending_peek = None
        elif "alloc" in f:
            if set(f) != {"alloc", "ptr"} or int(f["alloc"]) != generation + 1:
                raise ValueError("invalid allocation generation")
            p = int(f["ptr"])
            if not 0 < p <= 0xFFFFFFFF:
                raise ValueError("invalid expression pointer")
            generation += 1
            live[p] = generation
        elif "dead" in f:
            if set(f) != {"dead"}:
                raise ValueError("malformed invalidation")
            live.pop(int(f["dead"]), None)
        elif "kind" in f and "construct" not in f:
            if set(f) != {"kind", "read"} | words_keys:
                raise ValueError("malformed input record")
            ordinal = int(f["read"])
            words = tuple(int(f[f"w{i}"]) for i in range(8))
            if any(not 0 <= w <= 0xFFFFFFFF for w in words):
                raise ValueError("invalid input words")
            if f["kind"] == "READ":
                if ordinal != len(reads) + 1 or ordinal not in record_spans:
                    raise ValueError("invalid retained READ ordinal")
                if ordinal in input_records:
                    record = records[input_records[ordinal]]
                    if (
                        record.name == "lda"
                        and words[: len(record.words)] != record.words
                    ):
                        raise ValueError("input LDA payload mismatch")
                elif words[0] >> 24 != 34:
                    raise ValueError("invalid synthetic EOF")
                reads[ordinal] = words
            elif f["kind"] == "GETOP":
                if ordinal not in reads or ordinal != len(reads) or ordinal in selected:
                    raise ValueError("stale selected input ordinal")
                selected[ordinal] = words
            else:
                raise ValueError("unknown input observation")
        elif "construct" in f:
            if set(f) != {"construct", "current", "depth", "ptr", "kind"} | words_keys:
                raise ValueError("malformed construction")
            ordinal = int(f["construct"])
            if ordinal not in reads or ordinal not in selected:
                raise ValueError("missing selected input")
            if ordinal not in input_records:
                raise ValueError("construction from synthetic EOF")
            if int(f["current"]) != len(reads):
                raise ValueError("retimed construction input")
            record = records[input_records[ordinal]]
            words = tuple(int(f[f"w{i}"]) for i in range(8))
            if (
                record.name != "lda"
                or int(f["depth"]) != 1
                or int(f["current"]) != ordinal
            ):
                unresolved.append(
                    {
                        "record_index": record.index,
                        "reason": "unsupported opcode or recursive origin",
                    }
                )
                continue
            if (
                words[: len(record.words)] != record.words
                or selected[ordinal][: len(record.words)] != record.words
            ):
                raise ValueError("unsupported LDA normalization")
            ptr = int(f["ptr"])
            if ptr not in live or int(f["kind"]) not in {1, 5}:
                raise ValueError("missing live LDA generation")
            gen = live[ptr]
            if any(c["record_index"] == record.index for c in chains):
                raise ValueError("duplicate LDA construction")
            events = [
                e
                for e in frontend["events"]
                if e["operation"] == "load_addr" and record.index in e["record_indices"]
            ]
            occurrence_map = {e["id"]: e for e in frontend["occurrences"]}
            source_proof = bool(events) and all(
                e["occurrence"] in occurrence_map
                and occurrence_map[e["occurrence"]]["generation"] > 0
                for e in events
            )
            chains.append(
                {
                    "record_index": record.index,
                    "expression_token": ptr,
                    "generation": gen,
                    "procedure_index": record_procs[record.index],
                    "reused_observed_generation": gen in used,
                    "source_events": events,
                    "source_occurrence_proof": source_proof,
                }
            )
            used.add(gen)
        else:
            raise ValueError("unknown LDA event")
    if (
        not capability
        or not current_pass
        or pass_words[current_pass] != len(stream_words)
        or pass_record_end[current_pass] != len(stream_words)
        or pending_peek is not None
        or len(reads) != len(record_spans)
    ):
        raise ValueError("incomplete input observation")
    covered = {c["record_index"] for c in chains} | {
        c["record_index"] for c in unresolved
    }
    unresolved.extend(
        {
            "record_index": r.index,
            "reason": "unsupported ILDA input"
            if r.name == "ilda"
            else "missing construction receipt",
        }
        for r in records
        if r.name in {"lda", "ilda"} and r.index not in covered
    )
    return {
        "schema": "dkwb-lda-input-v1",
        "input_sha256": hashlib.sha256(ucode).hexdigest(),
        "chains": chains,
        "unresolved": unresolved,
        "frontend": frontend,
        "input_passes": current_pass,
        "procedure_count": procedure + 1,
        "optimized_ownership_proof": False,
        "pre_proof": False,
        "final_home_proof": False,
        "fidelity_proof": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    patch = sub.add_parser("instrument")
    patch.add_argument("source", type=Path)
    patch.add_argument("output", type=Path)
    join = sub.add_parser("join")
    join.add_argument("trace", type=Path)
    join.add_argument("ucode", type=Path)
    join.add_argument("cfe_trace", type=Path)
    a = p.parse_args()
    if a.command == "instrument":
        if a.source.resolve() == a.output.resolve():
            p.error("output must not replace original compiler source")
        a.output.write_text(instrument(a.source.read_text()))
    else:
        print(
            json.dumps(
                join_trace(
                    a.trace.read_text(),
                    a.ucode.read_bytes(),
                    cfe_trace=a.cfe_trace.read_text(),
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
