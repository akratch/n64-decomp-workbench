"""Pinned read-only hooks for actual spill records and local stack emitters."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from .instrument_ugen_owners import _function, _replace, instrument_ugen_owners
from .uopt_slots import instrument_uopt_slots

HEADER = r"""
/* DKWB_STACK_HOMES_V1: observation only. */
static unsigned long dkwb_home_write;
static int dkwb_home_on(void) {
    const char *v = getenv("DKWB_STACK_HOMES");
    return v && *v && *v != '0';
}
static void dkwb_home_words(uint8_t *mem, const char *kind, int proc, unsigned ptr) {
    unsigned i;
    if (!dkwb_home_on()) return;
    fprintf(stderr, "DKWB-HOME-%s write=%lu proc=%d", kind, dkwb_home_write, proc);
    for (i=0; i<8; ++i) fprintf(stderr, " w%u=%u", i, MEM_U32(ptr+i*4));
    fprintf(stderr, "\n");
}
"""


def _edit(source: str, name: str, edit: Callable[[str], str]) -> str:
    start, end = _function(source, name)
    return source[:start] + edit(source[start:end]) + source[end:]


def instrument_uopt(source: str) -> str:
    result = instrument_uopt_slots(source).source
    result = _replace(result, '#include "header.h"\n', '#include "header.h"\n' + HEADER)

    def writer(body: str) -> str:
        pos = body.index("\n") + 1
        hook = """if (MEM_U8(0x10022710)) {
dkwb_home_words(mem, "WRITE", dkwb_slot_proc, a0);
++dkwb_home_write;
}
"""
        return body[:pos] + hook + body[pos:]

    result = _edit(result, "f_uwrite", writer)
    hook = """if (dkwb_home_on()) fprintf(stderr,
"DKWB-HOME-SPILL write=%lu proc=%u slot=%u index=%u offset=%d size=%u enabled=%u\\n",
dkwb_home_write, dkwb_slot_proc, a2, MEM_U32(a2), (int)MEM_U32(a2+4),
MEM_U32(a2+8), MEM_U8(0x10022710));
"""
    return _edit(
        result,
        "f_spilltemplodstr",
        lambda b: _replace(
            b,
            "f_uwrite(mem, sp, a0, a1, a2, a3);\ngoto L42155c;",
            hook + "f_uwrite(mem, sp, a0, a1, a2, a3);\ngoto L42155c;",
        ),
    )


def instrument_ugen(source: str) -> str:
    result = instrument_ugen_owners(source)
    result = _replace(result, '#include "header.h"\n', '#include "header.h"\n' + HEADER)

    def build_u1(body: str) -> str:
        if body.count("return v0;") != 1:
            raise ValueError("f_build_u1 return anchor changed")
        first = body.index("\n") + 1
        body = body[:first] + "const unsigned dkwb_input = a0;\n" + body[first:]
        hook = """dkwb_owner_record(mem, "INPUT", dkwb_input, v0);
dkwb_owner_record(mem, "BUILD", v0 + 32, v0);
"""
        return _replace(body, "return v0;", hook + "return v0;")

    result = _edit(result, "f_build_u1", build_u1)

    def frame(body: str) -> str:
        if body.count("return v0;") != 3:
            raise ValueError("frame return count changed")
        hook = """if (dkwb_home_on()) fprintf(stderr,
"DKWB-HOME-FRAME owner_serial=%lu node=%u virtual=%d frame=%u mode=%u result=%d\\n",
dkwb_owner_serial, a0, (int)MEM_U32(a0+44), MEM_U32(0x10019388),
MEM_U8(0x10019398), (int)v0);
"""
        return body.replace("return v0;", hook + "return v0;")

    result = _edit(result, "f_frame_offset", frame)
    hook = """if (dkwb_home_on()) fprintf(stderr,
"DKWB-HOME-MEM owner_serial=%lu node=%u epoch=%u emit=%u op=%u reg=%u "
"base=%u displacement=%d extra=%u\\n",
dkwb_owner_serial, s0, dkwb_owner_epoch, MEM_U32(0x10018e70),
a0, a1, a3, (int)a2, MEM_U32(sp+16));
"""
    return _edit(
        result,
        "f_loadstore",
        lambda b: _replace(
            b,
            "f_emit_rob(mem, sp, a0, a1, a2, a3);\ngoto L427adc;",
            hook + "f_emit_rob(mem, sp, a0, a1, a2, a3);\ngoto L427adc;",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["uopt", "ugen"])
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.source.resolve() == args.output.resolve():
        parser.error("output must differ from original")
    instruments: dict[str, Callable[[str], str]] = {
        "uopt": instrument_uopt,
        "ugen": instrument_ugen,
    }
    args.output.write_text(instruments[args.phase](args.source.read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
