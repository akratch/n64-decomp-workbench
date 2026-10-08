/*
 * Wave-A W25 synthetic reproduction: a def between two loops keeps the
 * first loop's `<` exit test
 *
 * Synthetic C written for the workbench (CC0); no game code. Measured with
 * IDO 5.3 (decompals ido-static-recomp build) `cc -c -O2 -mips2 -32
 * -non_shared -G 0 -Xcpluscomm`, read back with GNU objdump, 2026-10-08.
 * Verdicts, per function, for the FIRST loop's exit test:
 *
 *   plain         rewritten to an inequality against a hoisted bound
 *   def_between   kept as a less-than test (one extra compare instruction)
 *   def_after     rewritten, exactly as plain: a def after the SECOND loop
 *                 does not count
 *
 * The second loop's exit test is rewritten in all three. See
 * docs/compiler-laws/ido-5.3-evidence.md, W25, and the main page's L153.
 */

extern int a[8];
extern int b[8];

void plain(void) {
    int i;
    int k;
    for (i = 0; i < 8; i++) {
        a[i] = 0;
    }
    for (k = 0; k < 8; k++) {
        b[k] = 1;
    }
}

void def_between(void) {
    int i;
    int k;
    for (i = 0; i < 8; i++) {
        a[i] = 0;
    }
    i = 0;
    for (k = 0; k < 8; k++) {
        b[k] = 1;
    }
}

void def_after(void) {
    int i;
    int k;
    for (i = 0; i < 8; i++) {
        a[i] = 0;
    }
    for (k = 0; k < 8; k++) {
        b[k] = 1;
    }
    i = 0;
}
