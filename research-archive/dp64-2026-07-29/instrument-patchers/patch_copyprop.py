#!/usr/bin/env python3
"""DKWB_UOPT_COPY_V1 - copy-propagation / coalesce-vs-temp+copy instrumentation
for the statically recompiled IDO 5.3 uopt.

Builds on DKWB_UOPT_WEBFORM_V1 (patch_webform.py).  Everything that profile
emitted (NEWBIT / FORMLIVBB / CENSUS / CDX_LIVE) is kept verbatim; this profile
adds the records that answer

    "an assignment `var = <expr>` whose RHS is a load: does uopt coalesce the
     load straight into var's web, or materialize an expression web T plus a
     copy uop T -> var?  what are the deciding inputs?"

New seams / decode ring (all established by reading the recompiled bodies and
cross-checking against emitted code):

  itab  0x1001cc30   entry[bit] = {node, liverange}.  A liverange pointer is
                     THE witness that the item became a register web; the whole
                     coalesce-vs-copy decision reduces to "does the RHS
                     expression node own a liverange".
  node+0   u8  type      3 = variable/leaf item, 4 = expression node,
                         2 = live-range item added by f_makelivranges.
  node+4   u16 table     expression hash-table index == expression IDENTITY.
                         Two type=4 nodes with the same `table` are the same
                         expression; `chain` (node+6) is the occurrence
                         ordinal.  Occurrence count > 1 == a CSE candidate.
  node+16  u32 w10       byte 3 = uop opcode.  0x7b = assign/store,
                         0x36 = load, 0x5b/0x18/0x41 = arith.
  node+20  u32 w14       operand 0 (for 0x7b: the LHS item node)
  node+24  u32 w18       operand 1 (for 0x7b: the RHS value node)

Records (all prefixed CDXW, so the webform parsers keep working):

  PASS>/PASS<   top-level uopt pass boundaries, so every NEWBIT / FORMLIVBB
                record is attributable to the pass that created it.
  FORMLIVBB     unchanged from webform, but now carries pass=<name>.
  EXPR          one line per type=4 bit at a census point: table, chain,
                occurrences of that table in the proc, opcode, operand bits,
                and formed=0/1 (+ color).  This is the web-SET view.
  COPYDEC       *** the decision record ***  one line per 0x7b assign node:
                    lhs=<bit> rhs=<bit> rhsformed=0/1 -> COALESCE | TEMPCOPY
                plus the deciding inputs we can see: the RHS expression's
                table, its occurrence count in the proc, its chain ordinal,
                whether any occurrence is live across a basic-block boundary
                (the bb+0x154 witness), and the LHS item's frame offset.

Gated on DKWB_UOPT_COPY (or CDX_WEBS for the inherited records); fully inert
and byte-identical when unset.

usage: patch_copyprop.py IN.c OUT.c
"""
import re
import sys

MARKER = "DKWB_UOPT_COPY_V1"

HELPERS = r"""
/* DKWB_UOPT_COPY_V1 - inert unless CDX_WEBS / DKWB_UOPT_COPY is set. */
#include <stdio.h>
#include <stdlib.h>

#define DKWB_WF_ITAB    0x1001cc30u   /* -> array of {node, liverange} */
#define DKWB_WF_NBITS   0x1001cb38u   /* number of allocated bits       */
#define DKWB_WF_LRBASE  0x1001cb40u   /* first bit created by livranges */
#define DKWB_WF_WEBSET  0x1001cc00u   /* bvect of register candidates   */
#define DKWB_WF_SETINT  0x1001cc10u   /* regclass 1 candidate bvect     */
#define DKWB_WF_SETFP   0x1001cc18u   /* regclass 2 candidate bvect     */
#define DKWB_WF_BBHEAD  0x1001c8f8u

static int dkwb_wf_state = -1;
static int dkwb_wf_copy_state = -1;
static int dkwb_wf_procfilter = -1;
static int dkwb_wf_proc = -1;
static unsigned long dkwb_wf_seq = 0;
static int dkwb_wf_depth = 0;
static FILE *dkwb_wf_fp = NULL;
static const char *dkwb_wf_pass = "-";

static const char *dkwb_wf_regname(unsigned r) {
    static const char *n[32] = {
        "zero","at","v0","v1","a0","a1","a2","a3",
        "t0","t1","t2","t3","t4","t5","t6","t7",
        "s0","s1","s2","s3","s4","s5","s6","s7",
        "t8","t9","k0","k1","gp","sp","s8","ra"};
    return r < 32 ? n[r] : "?";
}

static int dkwb_wf_on(void) {
    if (dkwb_wf_state < 0) {
        const char *v = getenv("CDX_WEBS");
        const char *p = getenv("CDX_WEBS_PROC");
        const char *o = getenv("CDX_WEBS_OUT");
        dkwb_wf_state = v != NULL && *v != '\0' && *v != '0';
        if (p != NULL && *p != '\0') dkwb_wf_procfilter = atoi(p);
        dkwb_wf_fp = stderr;
        if (dkwb_wf_state && o != NULL && *o != '\0') {
            FILE *f = fopen(o, "w");
            if (f != NULL) dkwb_wf_fp = f;
        }
    }
    return dkwb_wf_state;
}

/* the copy/coalesce records are separately gated so the profile can be run
 * cheaply (DKWB_UOPT_COPY=1 alone) on big TUs. */
static int dkwb_wf_copy_on(void) {
    if (dkwb_wf_copy_state < 0) {
        const char *v = getenv("DKWB_UOPT_COPY");
        dkwb_wf_copy_state = v != NULL && *v != '\0' && *v != '0';
    }
    return dkwb_wf_copy_state;
}

static int dkwb_wf_sel(void) {
    if (!dkwb_wf_on()) return 0;
    if (dkwb_wf_procfilter < 0) return 1;
    return dkwb_wf_proc == dkwb_wf_procfilter;
}

static void dkwb_wf_pfx(const char *ev) {
    fprintf(dkwb_wf_fp, "CDXW %06lu p%-3d d%-2d %-12s",
            dkwb_wf_seq++, dkwb_wf_proc, dkwb_wf_depth, ev);
}

static int dkwb_wf_emul(uint32_t v) {
    return v >= 0x10000000U && v < 0x20000000U;
}

/* f_bvectin inlined: word = base + (bit>>7)*16 + ((bit&0x7f)>>5)*4,
 * tested from the MSB. */
static int dkwb_wf_bvin(uint8_t *mem, uint32_t bv, int bit) {
    uint32_t base = MEM_U32(bv + 4);
    uint32_t w;
    int lo = bit & 0x7f;
    if (!dkwb_wf_emul(base)) return -1;
    w = MEM_U32(base + (uint32_t)(bit >> 7) * 16u + (uint32_t)(lo >> 5) * 4u);
    return (int)((w >> (31 - (lo & 31))) & 1u);
}

static int dkwb_wf_regclass(uint8_t *mem, uint32_t node) {
    unsigned dt;
    if (!dkwb_wf_emul(node)) return -1;
    if (MEM_U8(node + 0) == 4) dt = MEM_U8(node + 18);
    else dt = MEM_U8(node + 1);
    if (dt < 32 && (((0xc0000u >> dt) & 1u) != 0)) return 2;
    return 1;
}

static void dkwb_wf_node(uint8_t *mem, uint32_t node) {
    if (!dkwb_wf_emul(node)) {
        fprintf(dkwb_wf_fp, " node=%08x <bad>", node);
        return;
    }
    fprintf(dkwb_wf_fp,
            " node=%08x type=%-3d dtype=%-3d sym=%-5d table=%-5d chain=%-5d"
            " b18=%-3d b19=%-3d b22=%-3d b24=%-3d class=%d"
            " w08=%08x w0c=%08x w10=%08x w14=%08x w18=%08x w20=%08x",
            node, (int)MEM_U8(node + 0), (int)MEM_U8(node + 1),
            (int)MEM_U16(node + 2), (int)MEM_U16(node + 4),
            (int)MEM_U16(node + 6), (int)MEM_U8(node + 18),
            (int)MEM_U8(node + 19), (int)MEM_U8(node + 22),
            (int)MEM_U8(node + 24), dkwb_wf_regclass(mem, node),
            (unsigned)MEM_U32(node + 8), (unsigned)MEM_U32(node + 12),
            (unsigned)MEM_U32(node + 16), (unsigned)MEM_U32(node + 20),
            (unsigned)MEM_U32(node + 24), (unsigned)MEM_U32(node + 32));
}

static void dkwb_wf_census(uint8_t *mem, const char *tag) {
    uint32_t itab, nbits, lrbase, i;
    if (!dkwb_wf_sel()) return;
    itab = MEM_U32(DKWB_WF_ITAB);
    nbits = MEM_U32(DKWB_WF_NBITS);
    lrbase = MEM_U32(DKWB_WF_LRBASE);
    dkwb_wf_pfx("CENSUS");
    fprintf(dkwb_wf_fp, " tag=%s nbits=%u lrbase=%u itab=%08x\n",
            tag, nbits, lrbase, itab);
    if (!dkwb_wf_emul(itab)) return;
    if (nbits > 20000u) nbits = 20000u;
    for (i = 0; i < nbits; i++) {
        uint32_t node = MEM_U32(itab + i * 8u + 0);
        uint32_t lr = MEM_U32(itab + i * 8u + 4);
        int inset = dkwb_wf_bvin(mem, DKWB_WF_WEBSET, (int)i);
        int inint = dkwb_wf_bvin(mem, DKWB_WF_SETINT, (int)i);
        int infp = dkwb_wf_bvin(mem, DKWB_WF_SETFP, (int)i);
        int color = -99;
        int numintf = -1;
        unsigned f0 = 0, f1 = 0;
        if (dkwb_wf_emul(lr)) {
            color = (int)(int8_t)MEM_U8(lr + 32);
            numintf = (int)MEM_U32(lr + 36);
            f0 = (unsigned)MEM_U32(lr + 40);
            f1 = (unsigned)MEM_U32(lr + 44);
        }
        dkwb_wf_pfx("WEB");
        fprintf(dkwb_wf_fp, " tag=%s bit=%-5u %s lr=%08x web=%d color=%d",
                tag, i, i >= lrbase ? "LR" : "  ", lr,
                dkwb_wf_emul(lr) ? (int)MEM_U32(lr + 4) : -1, color);
        if (color >= 1 && color <= 40)
            fprintf(dkwb_wf_fp, "(%s)",
                    dkwb_wf_regname(MEM_U8(0x10001ae0u - 1u + (uint32_t)color)));
        fprintf(dkwb_wf_fp, " intf=%d forb=%08x/%08x set=%d/%d/%d",
                numintf, f0, f1, inset, inint, infp);
        dkwb_wf_node(mem, node);
        fprintf(dkwb_wf_fp, "\n");
    }
}

/* ------------------------------------------------------------------ *
 * DKWB_UOPT_COPY_V1 additions                                        *
 * ------------------------------------------------------------------ */

/* node -> bit, by linear scan of the itab (procs here are <2k bits). */
static int dkwb_cp_bitof(uint8_t *mem, uint32_t node) {
    uint32_t itab = MEM_U32(DKWB_WF_ITAB);
    uint32_t nbits = MEM_U32(DKWB_WF_NBITS);
    uint32_t i;
    if (!dkwb_wf_emul(itab) || !dkwb_wf_emul(node)) return -1;
    if (nbits > 20000u) nbits = 20000u;
    for (i = 0; i < nbits; i++)
        if (MEM_U32(itab + i * 8u) == node) return (int)i;
    return -1;
}

static int dkwb_cp_formed(uint8_t *mem, int bit) {
    uint32_t itab = MEM_U32(DKWB_WF_ITAB);
    if (bit < 0 || !dkwb_wf_emul(itab)) return -1;
    return dkwb_wf_emul(MEM_U32(itab + (uint32_t)bit * 8u + 4)) ? 1 : 0;
}

static int dkwb_cp_color(uint8_t *mem, int bit) {
    uint32_t itab = MEM_U32(DKWB_WF_ITAB);
    uint32_t lr;
    if (bit < 0 || !dkwb_wf_emul(itab)) return -99;
    lr = MEM_U32(itab + (uint32_t)bit * 8u + 4);
    if (!dkwb_wf_emul(lr)) return -99;
    return (int)(int8_t)MEM_U8(lr + 32);
}

/* how many type=4 nodes in this proc share `table` (== the CSE occurrence
 * count of the expression), and how many of those own a liverange. */
static void dkwb_cp_occ(uint8_t *mem, unsigned table, int *n, int *nformed) {
    uint32_t itab = MEM_U32(DKWB_WF_ITAB);
    uint32_t nbits = MEM_U32(DKWB_WF_NBITS);
    uint32_t i;
    *n = 0; *nformed = 0;
    if (!dkwb_wf_emul(itab)) return;
    if (nbits > 20000u) nbits = 20000u;
    for (i = 0; i < nbits; i++) {
        uint32_t nd = MEM_U32(itab + i * 8u);
        if (!dkwb_wf_emul(nd)) continue;
        if (MEM_U8(nd + 0) != 4) continue;
        if ((unsigned)MEM_U16(nd + 4) != table) continue;
        (*n)++;
        if (dkwb_wf_emul(MEM_U32(itab + i * 8u + 4))) (*nformed)++;
    }
}

/* is `bit` a member of any basic block's +0x154 bvect?  That is the
 * "will form a web from this block" witness established by CDX_LIVE. */
static int dkwb_cp_bbwitness(uint8_t *mem, int bit) {
    uint32_t bb = MEM_U32(DKWB_WF_BBHEAD);
    int nbb = 0, hits = 0;
    if (bit < 0) return -1;
    while (dkwb_wf_emul(bb) && nbb++ < 300) {
        uint32_t n = MEM_U32(bb + 0x154u + 0);
        uint32_t q = MEM_U32(bb + 0x154u + 4);
        if (n >= 1u && n <= 64u && q >= 0x10000000u && q < 0x10400000u
            && (q & 3u) == 0 && (uint32_t)bit < n * 128u) {
            if (dkwb_wf_bvin(mem, bb + 0x154u, bit) == 1) hits++;
        }
        bb = MEM_U32(bb + 12);
    }
    return hits;
}

/* one line per type=4 (expression) item: the web-SET view. */
static void dkwb_cp_expr(uint8_t *mem, const char *tag) {
    uint32_t itab, nbits, i;
    if (!dkwb_wf_sel() || !dkwb_wf_copy_on()) return;
    itab = MEM_U32(DKWB_WF_ITAB);
    nbits = MEM_U32(DKWB_WF_NBITS);
    if (!dkwb_wf_emul(itab)) return;
    if (nbits > 20000u) nbits = 20000u;
    for (i = 0; i < nbits; i++) {
        uint32_t nd = MEM_U32(itab + i * 8u);
        unsigned tbl, op;
        int nocc, nf, o0, o1, c;
        if (!dkwb_wf_emul(nd) || MEM_U8(nd + 0) != 4) continue;
        tbl = (unsigned)MEM_U16(nd + 4);
        op = (unsigned)(MEM_U32(nd + 16) >> 24);
        dkwb_cp_occ(mem, tbl, &nocc, &nf);
        o0 = dkwb_cp_bitof(mem, MEM_U32(nd + 20));
        o1 = dkwb_cp_bitof(mem, MEM_U32(nd + 24));
        c = dkwb_cp_color(mem, (int)i);
        dkwb_wf_pfx("EXPR");
        fprintf(dkwb_wf_fp,
                " tag=%s bit=%-5u table=%-5u chain=%-3u op=%02x occ=%d/%d"
                " op0=%-5d op1=%-5d formed=%d color=%d",
                tag, i, tbl, (unsigned)MEM_U16(nd + 6), op, nf, nocc,
                o0, o1, dkwb_cp_formed(mem, (int)i), c);
        if (c >= 1 && c <= 40)
            fprintf(dkwb_wf_fp, "(%s)",
                    dkwb_wf_regname(MEM_U8(0x10001ae0u - 1u + (uint32_t)c)));
        fprintf(dkwb_wf_fp, " bbwit=%d w10=%08x\n",
                dkwb_cp_bbwitness(mem, (int)i), (unsigned)MEM_U32(nd + 16));
    }
}

/* *** the decision record ***
 * every assign uop (opcode 0x7b): does its RHS own a web (TEMPCOPY -> ugen
 * emits `op dst_of_rhs` + `move lhs, dst_of_rhs`) or not (COALESCE -> the
 * defining op writes lhs' register directly)? */
static void dkwb_cp_copydec(uint8_t *mem, const char *tag) {
    uint32_t itab, nbits, i;
    if (!dkwb_wf_sel() || !dkwb_wf_copy_on()) return;
    itab = MEM_U32(DKWB_WF_ITAB);
    nbits = MEM_U32(DKWB_WF_NBITS);
    if (!dkwb_wf_emul(itab)) return;
    if (nbits > 20000u) nbits = 20000u;
    for (i = 0; i < nbits; i++) {
        uint32_t nd = MEM_U32(itab + i * 8u);
        uint32_t lhsn, rhsn;
        int lb, rb, rformed, nocc, nf, rop = -1, lcol, rcol;
        unsigned rtbl = 0, rchain = 0;
        if (!dkwb_wf_emul(nd) || MEM_U8(nd + 0) != 4) continue;
        if ((MEM_U32(nd + 16) >> 24) != 0x7bu) continue;
        lhsn = MEM_U32(nd + 20);
        rhsn = MEM_U32(nd + 24);
        lb = dkwb_cp_bitof(mem, lhsn);
        rb = dkwb_cp_bitof(mem, rhsn);
        rformed = dkwb_cp_formed(mem, rb);
        nocc = nf = 0;
        if (dkwb_wf_emul(rhsn) && MEM_U8(rhsn + 0) == 4) {
            rtbl = (unsigned)MEM_U16(rhsn + 4);
            rchain = (unsigned)MEM_U16(rhsn + 6);
            rop = (int)(MEM_U32(rhsn + 16) >> 24);
            dkwb_cp_occ(mem, rtbl, &nocc, &nf);
        }
        lcol = dkwb_cp_color(mem, lb);
        rcol = dkwb_cp_color(mem, rb);
        dkwb_wf_pfx("COPYDEC");
        fprintf(dkwb_wf_fp,
                " tag=%s stmt=%-5u lhs=%-5d rhs=%-5d rhsop=%02x rhstable=%-5u"
                " rhschain=%-3u occ=%d/%d rhsformed=%d bbwit=%d"
                " lhscolor=%d rhscolor=%d lhsframe=%08x -> %s\n",
                tag, i, lb, rb, (unsigned)(rop < 0 ? 0 : rop), rtbl, rchain,
                nf, nocc, rformed, dkwb_cp_bbwitness(mem, rb), lcol, rcol,
                dkwb_wf_emul(lhsn) ? (unsigned)MEM_U32(lhsn + 16) : 0u,
                rformed == 1 ? "TEMPCOPY" : "COALESCE");
    }
}

/* ---- block-boundary liveness (CDX_LIVE), unchanged from WEBFORM_V1 ---- */
#define DKWB_WF_BBSCAN  0x180u

static int dkwb_wf_live_state = -1;
static int dkwb_wf_live_bit = -1;

static int dkwb_wf_live_on(void) {
    if (dkwb_wf_live_state < 0) {
        const char *v = getenv("CDX_LIVE");
        const char *b = getenv("CDX_LIVE_BIT");
        dkwb_wf_live_state = v != NULL && *v != '\0' && *v != '0';
        if (b != NULL && *b != '\0') dkwb_wf_live_bit = atoi(b);
    }
    return dkwb_wf_live_state;
}

static int dkwb_wf_isbv(uint8_t *mem, uint32_t p) {
    uint32_t n = MEM_U32(p + 0);
    uint32_t q = MEM_U32(p + 4);
    return n >= 1u && n <= 64u && q >= 0x10000000u && q < 0x10400000u
           && (q & 3u) == 0;
}

static void dkwb_wf_bvdump(uint8_t *mem, const char *what, uint32_t bv,
                           uint32_t nbits) {
    uint32_t i;
    uint32_t cap = MEM_U32(bv + 0) * 128u;
    int n = 0;
    if (cap < nbits) nbits = cap;
    fprintf(dkwb_wf_fp, "  %-14s n=%-3u [", what, (unsigned)MEM_U32(bv + 0));
    for (i = 0; i < nbits; i++) {
        if (dkwb_wf_bvin(mem, bv, (int)i) == 1) {
            fprintf(dkwb_wf_fp, "%s%u", n ? "," : "", i);
            n++;
        }
    }
    fprintf(dkwb_wf_fp, "]\n");
}

static void dkwb_wf_live(uint8_t *mem, const char *tag) {
    uint32_t bb, nbits;
    int nbb = 0;
    static const uint32_t globals[] = {
        0x1001cb88u, 0x1001cb90u, 0x1001cb78u, 0x10009568u,
        0x1001cc00u, 0x1001cc10u, 0x1001cc18u, 0x1001cb58u};
    static const char *gnames[] = {
        "g_cb88", "g_cb90", "g_cb78", "g_9568",
        "webset", "set_int", "set_fp", "g_cb58"};
    unsigned gi;
    if (!dkwb_wf_sel() || !dkwb_wf_live_on()) return;
    nbits = MEM_U32(DKWB_WF_NBITS);
    if (nbits > 4000u) nbits = 4000u;
    dkwb_wf_pfx("LIVE");
    fprintf(dkwb_wf_fp, " tag=%s nbits=%u focus=%d\n", tag, nbits,
            dkwb_wf_live_bit);
    for (gi = 0; gi < sizeof(globals) / sizeof(globals[0]); gi++)
        if (dkwb_wf_isbv(mem, globals[gi]))
            dkwb_wf_bvdump(mem, gnames[gi], globals[gi], nbits);
    bb = MEM_U32(DKWB_WF_BBHEAD);
    while (dkwb_wf_emul(bb) && nbb++ < 300) {
        uint32_t off;
        static const uint32_t bvoff[] = {0xf4u, 0x104u, 0x10cu, 0x114u,
                                         0x11cu, 0x124u, 0x154u};
        unsigned oi;
        dkwb_wf_pfx("BB");
        fprintf(dkwb_wf_fp, " tag=%s bb=%-4d line=%-6d addr=%08x succ=%08x\n",
                tag, (int)MEM_U16(bb + 8), (int)MEM_U32(bb + 308), bb,
                (unsigned)MEM_U32(bb + 12));
        for (oi = 0; oi < sizeof(bvoff) / sizeof(bvoff[0]); oi++) {
            char nm[16];
            off = bvoff[oi];
            if (!dkwb_wf_isbv(mem, bb + off)) continue;
            snprintf(nm, sizeof(nm), "+0x%x", (unsigned)off);
            dkwb_wf_bvdump(mem, nm, bb + off, nbits);
        }
        bb = MEM_U32(bb + 12);
    }
}
"""

# --- pass-boundary wrappers: give every NEWBIT/FORMLIVBB a pass attribution --
PASSES = [
    "f_entervregveqv", "f_procinit_regs", "f_copypropagate", "f_findinduct",
    "f_codemotion", "f_getexpsources", "f_find_ix_loadstores",
    "f_makelivranges", "f_regdataflow", "f_localcolor", "f_spilltemps",
    "f_globalcolor", "f_reemit", "f_opt_saved_regs", "f_fix_par_vreg",
    "f_findallvregs", "f_checkforvreg", "f_copycoderep",
]

HOOKS = {
    "f_oneproc": (
        'dkwb_wf_proc++;\n'
        'if (dkwb_wf_on()) { dkwb_wf_pfx("PROC>"); '
        'fprintf(dkwb_wf_fp, " ordinal=%d\\n", dkwb_wf_proc); }',
        'if (dkwb_wf_sel()) { dkwb_wf_pfx("PROC<"); '
        'fprintf(dkwb_wf_fp, "\\n"); }',
    ),
    "f_newbit": (
        "",
        'if (dkwb_wf_sel()) { dkwb_wf_pfx("NEWBIT"); '
        'fprintf(dkwb_wf_fp, " pass=%s bit=%-5u lr=%08x", dkwb_wf_pass, '
        '__dkwb_r, a1); '
        'dkwb_wf_node(mem, a0); fprintf(dkwb_wf_fp, "\\n"); }',
    ),
    "f_formlivbb": (
        'if (dkwb_wf_sel()) { uint32_t __b = MEM_U16(a0 + 2); '
        'uint32_t __t = MEM_U32(DKWB_WF_ITAB); '
        '__dkwb_pre = dkwb_wf_emul(__t) ? MEM_U32(__t + __b * 8u + 4) : 0; }',
        'if (dkwb_wf_sel()) { uint32_t __b = MEM_U16(a0 + 2); '
        'uint32_t __t = MEM_U32(DKWB_WF_ITAB); '
        'uint32_t __po = dkwb_wf_emul(__t) ? MEM_U32(__t + __b * 8u + 4) : 0; '
        'dkwb_wf_pfx("FORMLIVBB"); '
        'fprintf(dkwb_wf_fp, " pass=%s bit=%-5u prelr=%08x postlr=%08x %s '
        'a1=%08x a2=%08x", dkwb_wf_pass, __b, __dkwb_pre, __po, '
        '__dkwb_pre == 0 ? "CREATE" : "update", a1, a2); '
        'dkwb_wf_node(mem, a0); fprintf(dkwb_wf_fp, "\\n"); }',
    ),
    "f_coloroffset": (
        "",
        'if (dkwb_wf_sel()) { dkwb_wf_pfx("COLOROFF"); '
        'fprintf(dkwb_wf_fp, " color=%u reg=%u(%s)\\n", a0, __dkwb_r, '
        'dkwb_wf_regname(__dkwb_r)); }',
    ),
}

# census / expr / copydec at the pass boundaries that matter
CENSUS_AT = {
    "f_makelivranges": ("pre-makelivranges", "post-makelivranges"),
    "f_localcolor": ("pre-localcolor", "post-localcolor"),
    "f_globalcolor": (None, "post-globalcolor"),
    "f_reemit": ("pre-reemit", None),
}


def _pass_entry(name):
    tag = name[2:]
    s = ('dkwb_wf_pass = "%s";\n' % tag)
    s += ('if (dkwb_wf_sel()) { dkwb_wf_pfx("PASS>"); '
          'fprintf(dkwb_wf_fp, " %s\\n"); }' % tag)
    pre = CENSUS_AT.get(name, (None, None))[0]
    if pre:
        s += ('\ndkwb_wf_census(mem, "%s");' % pre)
        s += ('\ndkwb_cp_expr(mem, "%s");' % pre)
        s += ('\ndkwb_cp_copydec(mem, "%s");' % pre)
    if name == "f_makelivranges":
        s += '\ndkwb_wf_live(mem, "pre-makelivranges");'
    return s


def _pass_exit(name):
    tag = name[2:]
    s = ""
    post = CENSUS_AT.get(name, (None, None))[1]
    if post:
        s += ('dkwb_wf_census(mem, "%s");\n' % post)
        s += ('dkwb_cp_expr(mem, "%s");\n' % post)
        s += ('dkwb_cp_copydec(mem, "%s");\n' % post)
    if name == "f_makelivranges":
        s += 'dkwb_wf_live(mem, "post-makelivranges");\n'
    s += ('if (dkwb_wf_sel()) { dkwb_wf_pfx("PASS<"); '
          'fprintf(dkwb_wf_fp, " %s\\n"); }\n' % tag)
    s += 'dkwb_wf_pass = "-";'
    return s


for _p in PASSES:
    HOOKS[_p] = (_pass_entry(_p), _pass_exit(_p))

NEEDS_PRE = {"f_formlivbb"}

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
    if name in NEEDS_PRE:
        out.append("    uint32_t __dkwb_pre = 0; (void) __dkwb_pre;")
    out.append("    dkwb_wf_depth++;")
    if entry:
        out.append("    " + entry.replace("\n", "\n    "))
    call = "%s(%s)" % (real, ", ".join(names))
    out.append(("    __dkwb_r = %s;" % call) if ret != "void"
               else ("    %s;" % call))
    if exit_:
        out.append("    " + exit_.replace("\n", "\n    "))
    out.append("    dkwb_wf_depth--;")
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
    off = inc[0].end() if inc else 0          # FIRST include, never the last
    src = src[:off] + "/* " + MARKER + " */\n" + HELPERS + src[off:]
    open(sys.argv[2], "w").write(src)
    print("wrapped %d: %s" % (len(ok), " ".join(sorted(ok))))
    if missing:
        print("MISSING %d: %s" % (len(missing), " ".join(sorted(missing))))


if __name__ == "__main__":
    main()
