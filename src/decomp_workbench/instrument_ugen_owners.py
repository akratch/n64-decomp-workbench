"""Source-pinned, read-only UGEN address operand ownership hooks."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

UGEN_SHA256 = "4079660f9ebb068a791c6f54abb67cf7c3bb792207c89a6eb9ac2d9e146341ec"
MARKER = "DKWB_UGEN_OWNERS_V1"
HEADER = r"""
/* DKWB_UGEN_OWNERS_V1: diagnostic reads, never simulated state writes. */
static unsigned long dkwb_owner_serial;
static unsigned dkwb_owner_epoch;
static int dkwb_owner_on(void) {
    const char *v = getenv("DKWB_UGEN_OWNERS");
    return v && *v && *v != '0';
}
static void dkwb_owner_record(uint8_t *mem, const char *kind, unsigned ptr,
                             unsigned node) {
    unsigned i;
    if (!dkwb_owner_on()) return;
    fprintf(stderr, "DKWB-OWNER-%s serial=%lu ptr=%u node=%u id=%u", kind,
            ++dkwb_owner_serial, ptr, node, node ? MEM_U32(node + 16) >> 8 : 0);
    for (i = 0; i < 8; ++i)
        fprintf(stderr, " w%u=%u", i, MEM_U32(ptr + i * 4));
    fprintf(stderr, "\n");
}
static void dkwb_owner_emit(uint8_t *mem, const char *site, unsigned node,
                           unsigned op, unsigned reg, unsigned sym,
                           unsigned addend, unsigned extra) {
    if (!dkwb_owner_on()) return;
    fprintf(stderr, "DKWB-OWNER-EMIT serial=%lu site=%s node=%u id=%u "
            "epoch=%u emit=%u op=%u reg=%u symbol=%u addend=%u extra=%u "
            "node_op=%u node_symbol=%u node_addend=%u node_reg=%u",
            ++dkwb_owner_serial, site, node, MEM_U32(node + 16) >> 8,
            dkwb_owner_epoch, MEM_U32(0x10018e70), op, reg, sym, addend, extra,
            MEM_U8(node + 32), MEM_U32(node + 36), MEM_U32(node + 44),
            MEM_U8(node + 25) >> 1);
    fprintf(stderr, "\n");
}
"""


def _function(source: str, name: str) -> tuple[int, int]:
    matches = list(
        re.finditer(
            r"^static [^\n]+ " + re.escape(name) + r"\([^\n]+\) \{\n", source, re.M
        )
    )
    if len(matches) != 1:
        raise ValueError("missing or duplicated function: " + name)
    return matches[0].start(), source.index("\n}\n", matches[0].end()) + 3


def _replace(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("missing or duplicated UGEN anchor")
    return source.replace(old, new, 1)


def instrument_ugen_owners(source: str) -> str:
    if MARKER in source or hashlib.sha256(source.encode()).hexdigest() != UGEN_SHA256:
        raise ValueError("UGEN source is not the supported pristine revision")
    result = _replace(source, '#include "header.h"\n', '#include "header.h"\n' + HEADER)
    for name, owner, expected in [
        ("f_loadstore", "s0", 3),
        ("f_eval_mov", "v1", 2),
        ("f_eval", "s6", 2),
    ]:
        start, end = _function(result, name)
        body = result[start:end]
        call = "f_emit_ra(mem, sp, a0, a1, a2, a3);"
        if body.count(call) != expected:
            raise ValueError("UGEN emitter site count changed")
        for index, match in reversed(
            list(enumerate(re.finditer(re.escape(call), body)))
        ):
            hook = (
                'dkwb_owner_emit(mem, "'
                + name
                + "-"
                + str(index)
                + '", '
                + owner
                + ", a0, a1, a2, a3, MEM_U32(sp + 16));\n"
            )
            body = body[: match.start()] + hook + body[match.start() :]
        result = result[:start] + body + result[end:]
    for name, hook in [
        ("f_readuinstr", 'dkwb_owner_record(mem, "READ", dkwb_input, 0);\n'),
        ("f_build_u", 'dkwb_owner_record(mem, "BUILD", v0 + 32, v0);\n'),
        (
            "f_new_tree",
            'if (dkwb_owner_on()) fprintf(stderr, "DKWB-OWNER-NEW '
            'serial=%lu node=%u id=%u\\n", ++dkwb_owner_serial, v0, '
            "MEM_U32(v0 + 16) >> 8);\n",
        ),
    ]:
        start, end = _function(result, name)
        body = result[start:end]
        if name == "f_readuinstr":
            first = body.index("\n") + 1
            body = body[:first] + "const unsigned dkwb_input = a0;\n" + body[first:]
        if name == "f_build_u":
            first = body.index("\n") + 1
            body = body[:first] + "const unsigned dkwb_input = a0;\n" + body[first:]
            hook = 'dkwb_owner_record(mem, "INPUT", dkwb_input, v0);\n' + hook
        returns = list(re.finditer(r"^return(?: v0)?;", body, re.M))
        if len(returns) != 1:
            raise ValueError("UGEN return count changed: " + name)
        pos = returns[0].start()
        body = body[:pos] + hook + body[pos:]
        result = result[:start] + body + result[end:]
    start, end = _function(result, "f_get_dest")
    body = result[start:end]
    first = body.index("\n") + 1
    body = (
        body[:first] + "const unsigned dkwb_node = a0, dkwb_hint = a1;\n" + body[first:]
    )
    body = _replace(
        body,
        "return v0;",
        'if (dkwb_owner_on()) fprintf(stderr, "DKWB-OWNER-DEST serial=%lu '
        'node=%u id=%u hint=%u reg=%u node_reg=%u\\n", '
        "++dkwb_owner_serial, dkwb_node, MEM_U32(dkwb_node + 16) >> 8, "
        "dkwb_hint, v0, MEM_U8(dkwb_node + 25) >> 1);\nreturn v0;",
    )
    result = result[:start] + body + result[end:]
    start, end = _function(result, "f_build_tree")
    body = result[start:end]
    first = body.index("\n") + 1
    body = (
        body[:first]
        + (
            "if (dkwb_owner_on() && dkwb_owner_serial == 0) "
            'fprintf(stderr, "DKWB-OWNER-PROFILE version=1 source_sha256='
            + UGEN_SHA256
            + '\\n");\n'
        )
        + body[first:]
    )
    result = result[:start] + body + result[end:]
    for name, hook in [
        ("f_clear_ibuffer", "++dkwb_owner_epoch;\n"),
        (
            "f_output_inst_bin",
            'if (dkwb_owner_on()) fprintf(stderr, "DKWB-OWNER-OUTPUT '
            'serial=%lu epoch=%u forward=%u backward=%u\\n", '
            "++dkwb_owner_serial, dkwb_owner_epoch, a1, a3);\n",
        ),
        (
            "f_cat_files",
            'if (dkwb_owner_on()) fprintf(stderr, "DKWB-OWNER-CONCAT '
            'serial=%lu\\n", ++dkwb_owner_serial);\n',
        ),
    ]:
        start, end = _function(result, name)
        body = result[start:end]
        first = body.index("\n") + 1
        body = body[:first] + hook + body[first:]
        result = result[:start] + body + result[end:]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.source.resolve() == args.output.resolve():
        parser.error("instrumented output must differ from pristine source")
    try:
        args.output.write_text(instrument_ugen_owners(args.source.read_text()))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
