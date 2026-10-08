/*
 * Wave-A W11/W27 synthetic reproduction: zero-emission statements
 *
 * Synthetic C written for the workbench (CC0); no game code. Measured with
 * IDO 5.3 (decompals ido-static-recomp build) `cc -c -O2 -mips2 -32
 * -non_shared -G 0 -Xcpluscomm`, read back with GNU objdump, 2026-10-08.
 * Every function below is 11 instructions. Against base_fn:
 *
 *   bare_read    byte-identical: a bare dead read is inert (W11)
 *   keep_alive   byte-identical: `x |= 0` after `x = <expression>` is deleted;
 *                in this shape there is no substitution for it to kill (W18
 *                needs one), so this is a zero-emission control, not W18
 *   empty_if     same 11 instructions, two words differ: the value reloaded
 *                after the call lands in a2 instead of a0. The empty
 *                `if (n) {}` emits nothing and still moves allocation (W27)
 *
 * See docs/compiler-laws/ido-5.3-evidence.md.
 */

struct rec {
    int value;
    int next;
};
extern int use(int, int);

int base_fn(struct rec *p, int n) {
    int x;
    int y;
    x = p->value + n;
    y = use(x, n);
    return x + y;
}

int bare_read(struct rec *p, int n) {
    int x;
    int y;
    x = p->value + n;
    p->next;
    y = use(x, n);
    return x + y;
}

int empty_if(struct rec *p, int n) {
    int x;
    int y;
    x = p->value + n;
    if (n) {}
    y = use(x, n);
    return x + y;
}

int keep_alive(struct rec *p, int n) {
    int x;
    int y;
    x = p->value + n;
    x |= 0;
    y = use(x, n);
    return x + y;
}
