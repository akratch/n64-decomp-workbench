#!/usr/bin/env python3
"""DKWB_UGEN_EMIT_V1 -- per-instruction emit correlation for IDO 5.3 ugen.

Layers on top of an already pool-instrumented ugen source (DKWB_UGEN_POOL_V1),
so one binary carries both instruments and they compose.

The seam: ugen builds each procedure in a two-ended "ibuffer".
    0x10018e68  capacity (items)
    0x10018e6c  base pointer, 16 bytes per item
    0x10018e70  forward cursor `i` (1-based; f_clear_ibuffer resets to 1)
    0x10018e78  backward cursor `d` (grows down from capacity; demit/data side)
Every f_emit_* / f_define_label / f_append_i writes the item at
base + 16*(i-1) and then does i++.  So the *ordinal of the next item to be
emitted* is exactly MEM_U32(0x10018e70) - 1, and it is live at every point in
ugen -- including inside the register allocator.  Stamping every pool event
with it gives the pool-GET <-> instruction-index join.

usage: patch_emit.py IN.c OUT.c
"""
import re
import sys

MARKER = "DKWB_UGEN_EMIT_V1"

# --- inserted after the last #include (before the pool statics) -------------
TOP = r"""
/* DKWB_UGEN_EMIT_V1 -- ibuffer emit-cursor correlation. */
#define DKWB_IBUF_CAP  0x10018e68u
#define DKWB_IBUF_BASE 0x10018e6cu
#define DKWB_IBUF_I    0x10018e70u
#define DKWB_IBUF_D    0x10018e78u

static uint8_t *dkwb_mem_g = 0;
static int dkwb_emit_state = -1;

/* ordinal of the next item that will be appended to the ibuffer */
static long dkwb_iidx(void) {
    uint8_t *mem = dkwb_mem_g;
    if (mem == 0) return -1;
    return (long) MEM_U32(DKWB_IBUF_I) - 1;
}
"""

# --- inserted after the pool helper block (can use dkwb_pool_fp/dkwb_sel) ---
MID = r"""
static int dkwb_emit_on(void) {
    if (dkwb_emit_state < 0) {
        const char *v = getenv("DKWB_UGEN_EMIT");
        dkwb_emit_state = v != NULL && *v != '\0' && *v != '0';
    }
    return dkwb_emit_state;
}

/* true when emit logging is on AND the proc filter passes */
static int dkwb_esel(void) {
    if (!dkwb_emit_on()) return 0;
    return dkwb_sel();
}

/* raw 16 bytes of ibuffer item `ord` (0-based) */
static void dkwb_item(uint8_t *mem, long ord) {
    uint32_t base = MEM_U32(DKWB_IBUF_BASE);
    uint32_t p;
    if (ord < 0) return;
    p = base + (uint32_t)(16 * ord);
    fprintf(dkwb_pool_fp, " raw=%08x.%08x.%08x.%08x op=%02x",
            (unsigned) MEM_U32(p + 0), (unsigned) MEM_U32(p + 4),
            (unsigned) MEM_U32(p + 8), (unsigned) MEM_U32(p + 12),
            (unsigned) MEM_U8(p + 5));
}
"""

PFX_OLD = '''static void dkwb_pfx(const char *ev) {
    fprintf(dkwb_pool_fp, "POOL %06lu p%-3d d%-2d %-12s",
            dkwb_pool_seq++, dkwb_pool_proc, dkwb_pool_depth, ev);
}'''

PFX_NEW = '''static long dkwb_iidx(void);
static void dkwb_pfx(const char *ev) {
    fprintf(dkwb_pool_fp, "POOL %06lu p%-3d i%-5ld d%-2d %-12s",
            dkwb_pool_seq++, dkwb_pool_proc, dkwb_iidx(), dkwb_pool_depth, ev);
}'''

# ---------------------------------------------------------------- wrapping --
DEF_RE_TMPL = (
    r"^static (?P<ret>[A-Za-z_][A-Za-z0-9_ ]*?) (?P<name>@NAME@)"
    r"\((?P<args>uint8_t \*mem, uint32_t sp[^;\n)]*)\) \{$"
)
ARG_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*$")


def build_wrapper(ret, name, args, entry, exit_):
    names = [ARG_RE.search(a.strip()).group(1) for a in args.split(",")]
    call = ", ".join(names)
    real = name + "__dkwbemit"
    voids = "".join("    (void) %s;\n" % n for n in names)
    out = []
    out.append("static %s %s(%s);" % (ret, real, args))
    out.append("static %s %s(%s) {" % (ret, name, args))
    out.append(voids.rstrip("\n"))
    if ret != "void":
        out.append("    %s __dkwb_r;" % ret)
    out.append("    unsigned long __dkwb_i0;")
    out.append("    dkwb_mem_g = mem;")
    if entry:
        out.append("    " + entry.replace("\n", "\n    "))
    out.append("    __dkwb_i0 = MEM_U32(DKWB_IBUF_I);")
    if ret != "void":
        out.append("    __dkwb_r = %s(%s);" % (real, call))
    else:
        out.append("    %s(%s);" % (real, call))
    if exit_:
        out.append("    " + exit_.replace("\n", "\n    "))
    if ret != "void":
        out.append("    return __dkwb_r;")
    out.append("}")
    out.append("static %s %s(%s) {" % (ret, real, args))
    return "\n".join(out)


def emit_hook(name, argnames):
    """entry/exit log pair for an ibuffer-appending function"""
    extra = [a for a in argnames if a not in ("mem", "sp")]
    fmt = " ".join("%s=%%08x" % a for a in extra)
    vals = ("".join(", " + a for a in extra)) if extra else ""
    exit_ = (
        'if (dkwb_esel()) {\n'
        '    unsigned long __dkwb_i1 = MEM_U32(DKWB_IBUF_I);\n'
        '    dkwb_pfx("EMIT");\n'
        '    fprintf(dkwb_pool_fp, " %-22s n=%lu ord=%ld", "{NAME}",\n'
        '            __dkwb_i1 - __dkwb_i0, (long) __dkwb_i0 - 1);\n'
        '    if (__dkwb_i1 > __dkwb_i0) dkwb_item(mem, (long) __dkwb_i0 - 1);\n'
        '    fprintf(dkwb_pool_fp, " {FMT}\\n"{VALS});\n'
        '}'
    ).replace("{NAME}", name).replace("{FMT}", fmt).replace("{VALS}", vals)
    return ("", exit_)


def main():
    src = open(sys.argv[1]).read()
    if MARKER in src:
        raise SystemExit("already instrumented")

    # 1. discover every ibuffer-appending function still in stock form
    targets = []
    for m in re.finditer(
        r"^static (?P<ret>[A-Za-z_][A-Za-z0-9_ ]*?) (?P<name>f_[A-Za-z0-9_]+)"
        r"\((?P<args>uint8_t \*mem, uint32_t sp[^;\n)]*)\) \{$",
        src, re.MULTILINE,
    ):
        n = m.group("name")
        if (n.startswith("f_emit_") or n.startswith("f_demit_")
                or n in ("f_define_label", "f_ddefine_label",
                         "f_define_exception_label", "f_append_i",
                         "f_append_d", "f_clear_ibuffer", "f_init_ibuffer",
                         "f_grow_ibuffer", "f_save_i_ptrs",
                         "f_restore_i_ptrs")):
            targets.append(n)
    targets = sorted(set(targets))

    applied = []
    for name in targets:
        rx = re.compile(DEF_RE_TMPL.replace("@NAME@", re.escape(name)),
                        re.MULTILINE)
        m = rx.search(src)
        if not m:
            continue
        argnames = [ARG_RE.search(a.strip()).group(1)
                    for a in m.group("args").split(",")]
        entry, exit_ = emit_hook(name, argnames)
        wrapper = build_wrapper(m.group("ret"), name, m.group("args"),
                                entry, exit_)
        src = src[:m.start()] + wrapper + src[m.end():]
        applied.append(name)

    # 2. every existing pool wrapper publishes `mem` for dkwb_iidx()
    n_pool = src.count("    dkwb_pool_depth++;")
    src = src.replace("    dkwb_pool_depth++;",
                      "    dkwb_mem_g = mem;\n    dkwb_pool_depth++;")

    # 3. pool prefix carries the emit ordinal
    if PFX_OLD not in src:
        raise SystemExit("pool prefix not found -- input not pool2?")
    src = src.replace(PFX_OLD, PFX_NEW)

    # 4. helper blocks
    inc = list(re.finditer(r"^\s*#include[^\n]*\n", src, re.MULTILINE))
    off = inc[-1].end()
    src = src[:off] + TOP + src[off:]

    anchor = '    return "other";\n}\n'
    k = src.index(anchor) + len(anchor)
    src = src[:k] + MID + src[k:]

    open(sys.argv[2], "w").write(src)
    print("emit-wrapped %d: %s" % (len(applied), " ".join(applied)))
    print("pool wrappers touched: %d" % n_pool)


if __name__ == "__main__":
    main()
