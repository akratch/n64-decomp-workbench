#!/usr/bin/env python3
"""DKWB_UOPT_ASSIGN_V1 - final-ucode / register-finalization instrumentation
for statically recompiled IDO 5.3 uopt.

Hooks the pass that actually decides what register ugen will see:

  f_uwrite(uop, ...)   serialises one final uop.  Layout established by reading
                       the recompiled body: u8 opcode at +0, then N u32 operand
                       words at +4.., with N = descriptor[17] of a 19-byte
                       table at 0x10022720 indexed by opcode.  This is byte-for
                       -byte what ugen's reader consumes, so every register
                       operand ugen ever sees passes through here.

  f_coloroffset(color) color -> register<<2 mapping; every register
                       finalisation in uopt funnels through it (24 call sites).

Plus entry/exit frames for the finalisation paths that call coloroffset outside
globalcolor, so the log shows WHICH path assigned a register:
  f_reemit, f_genrop, f_genrlodrstr, f_base_in_reg, f_prolog, f_epilog,
  f_in_reg_masks, and the pre-colouring / temp paths f_inreg, f_local_in_reg,
  f_constinreg, f_ldainreg, f_passedinreg, f_fitparmreg, f_gettemp,
  f_findbbtemps, f_str_to_temporary, f_spilltemps, f_localcolor,
  f_globalcolor, f_opt_saved_regs, f_makelivranges, f_regdataflow.

Gated on CDX_ASSIGN; inert (and therefore output-identical) when unset.

usage: patch_assign.py IN.c OUT.c
"""
import re
import sys

MARKER = "DKWB_UOPT_ASSIGN_V1"

HELPERS = r"""
/* DKWB_UOPT_ASSIGN_V1 - inert unless CDX_ASSIGN is set. */
#include <stdio.h>
#include <stdlib.h>

#define DKWB_UOPDESC 0x10022720u   /* 19-byte per-opcode descriptor table */

static int dkwb_as_state = -1;
static int dkwb_as_procfilter = -1;
static int dkwb_as_proc = -1;
static unsigned long dkwb_as_seq = 0;
static int dkwb_as_depth = 0;
static int dkwb_as_uop = 0;
static FILE *dkwb_as_fp = NULL;

static const char *dkwb_as_reg(unsigned r) {
    static const char *n[32] = {
        "zero","at","v0","v1","a0","a1","a2","a3",
        "t0","t1","t2","t3","t4","t5","t6","t7",
        "s0","s1","s2","s3","s4","s5","s6","s7",
        "t8","t9","k0","k1","gp","sp","s8","ra"};
    return r < 32 ? n[r] : "?";
}

static int dkwb_as_on(void) {
    if (dkwb_as_state < 0) {
        const char *v = getenv("CDX_ASSIGN");
        const char *p = getenv("CDX_ASSIGN_PROC");
        const char *o = getenv("CDX_ASSIGN_OUT");
        dkwb_as_state = v != NULL && *v != '\0' && *v != '0';
        if (p != NULL && *p != '\0') dkwb_as_procfilter = atoi(p);
        dkwb_as_fp = stderr;
        if (dkwb_as_state && o != NULL && *o != '\0') {
            FILE *f = fopen(o, "w");
            if (f != NULL) dkwb_as_fp = f;
        }
    }
    return dkwb_as_state;
}

static int dkwb_as_sel(void) {
    if (!dkwb_as_on()) return 0;
    if (dkwb_as_procfilter < 0) return 1;
    return dkwb_as_proc == dkwb_as_procfilter;
}

static void dkwb_as_pfx(const char *ev) {
    fprintf(dkwb_as_fp, "CDXA %06lu p%-3d d%-2d %-14s",
            dkwb_as_seq++, dkwb_as_proc, dkwb_as_depth, ev);
}

/* Dump one final uop exactly as ugen will read it.
 * f_uwrite writes d[17]+1 words starting at uop+0, then two more at
 * uop+d[17]*4 when d[16]!=0, then a variable tail. */
static void dkwb_as_uwrite(uint8_t *mem, uint32_t uop) {
    unsigned op = MEM_U8(uop + 0);
    unsigned d16 = MEM_U8(DKWB_UOPDESC + 19u * op + 16);
    unsigned d17 = MEM_U8(DKWB_UOPDESC + 19u * op + 17);
    unsigned n = d17 + 3u;
    unsigned i;
    if (n > 14) n = 14;
    dkwb_as_pfx("UWRITE");
    fprintf(dkwb_as_fp, " #%-4d op=%-3u d16=%-3u d17=%-2u", dkwb_as_uop++,
            op, d16, d17);
    for (i = 0; i < n; i++) {
        uint32_t w = MEM_U32(uop + 4 * i);
        fprintf(dkwb_as_fp, " w%u=%08x", i, w);
        if ((w & 3u) == 0 && (w >> 2) < 32u)
            fprintf(dkwb_as_fp, "(%s)", dkwb_as_reg(w >> 2));
    }
    fprintf(dkwb_as_fp, " tail=%08x/%08x/%08x/%08x\n",
            MEM_U32(uop + 16), MEM_U32(uop + 20),
            MEM_U32(uop + 24), MEM_U32(uop + 28));
}
"""

HOOKS = {
    # ---- the finalised ucode stream -----------------------------------
    "f_uwrite": (
        'if (dkwb_as_sel()) dkwb_as_uwrite(mem, a0);',
        "",
    ),
    # ---- colour -> register, every finalisation funnels through here ---
    "f_coloroffset": (
        "",
        'if (dkwb_as_sel()) { dkwb_as_pfx("COLOROFF"); '
        'fprintf(dkwb_as_fp, " color=%u -> off=%u reg=%s\\n", a0, __dkwb_r, '
        'dkwb_as_reg(__dkwb_r >> 2)); }',
    ),
    # ---- proc boundary -------------------------------------------------
    "f_reemit": (
        'dkwb_as_proc++; dkwb_as_uop = 0;\n'
        'if (dkwb_as_on()) { dkwb_as_pfx("REEMIT>"); '
        'fprintf(dkwb_as_fp, " begin\\n"); }',
        'if (dkwb_as_sel()) { dkwb_as_pfx("REEMIT<"); '
        'fprintf(dkwb_as_fp, " uops=%d\\n", dkwb_as_uop); }',
    ),
}

# Paths that finalise a register outside globalcolor: frame-only tracing so the
# call tree attributes each COLOROFF to a pass.
FRAME_ONLY = [
    "f_genrop", "f_genrlodrstr", "f_base_in_reg", "f_prolog", "f_epilog",
    "f_in_reg_masks", "f_inreg", "f_local_in_reg", "f_constinreg",
    "f_ldainreg", "f_passedinreg", "f_fitparmreg", "f_gettemp",
    "f_findbbtemps", "f_str_to_temporary", "f_spilltemps", "f_localcolor",
    "f_globalcolor", "f_opt_saved_regs", "f_makelivranges", "f_regdataflow",
    "f_assign_mtag", "f_checkforvreg", "f_entervregveqv", "f_findallvregs",
    "f_fix_par_vreg", "f_formal_parm_vreg", "f_gen_static_link",
    "f_genloadaddr", "f_genloadnum", "f_genloadrnum", "f_rewrite",
]
for _f in FRAME_ONLY:
    HOOKS.setdefault(_f, (
        'if (dkwb_as_sel()) { dkwb_as_pfx("%s>"); '
        'fprintf(dkwb_as_fp, "\\n"); }' % _f[2:],
        'if (dkwb_as_sel()) { dkwb_as_pfx("%s<"); '
        'fprintf(dkwb_as_fp, "\\n"); }' % _f[2:],
    ))

DEF_RE = (
    r"^static (?P<ret>[A-Za-z_][A-Za-z0-9_ ]*?) (?P<name>@NAME@)"
    r"\((?P<args>uint8_t \*mem, uint32_t sp[^;\n)]*)\) \{$"
)
ARG_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*$")


def wrapper(ret, name, args, entry, exit_):
    names = [ARG_RE.search(a.strip()).group(1) for a in args.split(",")]
    real = name + "__dkwbreal"
    out = ["static %s %s(%s);" % (ret, real, args),
           "static %s %s(%s) {" % (ret, name, args)]
    out += ["    (void) %s;" % n for n in names]
    if ret != "void":
        out.append("    %s __dkwb_r;" % ret)
    out.append("    dkwb_as_depth++;")
    if entry:
        out.append("    " + entry.replace("\n", "\n    "))
    call = "%s(%s)" % (real, ", ".join(names))
    out.append(("    __dkwb_r = %s;" % call) if ret != "void"
               else ("    %s;" % call))
    if exit_:
        out.append("    " + exit_.replace("\n", "\n    "))
    out.append("    dkwb_as_depth--;")
    if ret != "void":
        out.append("    return __dkwb_r;")
    out.append("}")
    out.append("static %s %s(%s) {" % (ret, real, args))
    return "\n".join(out)


def main():
    src = open(sys.argv[1]).read()
    if MARKER in src:
        raise SystemExit("already instrumented")
    ok, missing = [], []
    for name, (entry, exit_) in HOOKS.items():
        rx = re.compile(DEF_RE.replace("@NAME@", re.escape(name)), re.MULTILINE)
        m = rx.search(src)
        if not m:
            missing.append(name)
            continue
        src = (src[:m.start()]
               + wrapper(m.group("ret"), name, m.group("args"), entry, exit_)
               + src[m.end():])
        ok.append(name)
    inc = list(re.finditer(r"^\s*#include[^\n]*\n", src, re.MULTILINE))
    off = inc[0].end() if inc else 0
    src = src[:off] + HELPERS + src[off:]
    open(sys.argv[2], "w").write(src)
    print("wrapped %d: %s" % (len(ok), " ".join(sorted(ok))))
    if missing:
        print("MISSING %d: %s" % (len(missing), " ".join(sorted(missing))))


if __name__ == "__main__":
    main()
