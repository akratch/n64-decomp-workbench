/*
 * L99 qualification fixture: no value homed in the frame across a call
 *
 * Synthetic C written for the workbench (CC0); no game code. Each case is
 * compiled four times, with 0..3 wholly unreferenced `int` locals (padN)
 * declared after the live ones, and the frame is read from the
 * `addiu sp,sp,-N` of each function. Measured with IDO 5.3 `cc -c -O2
 * -mips2 -32 -non_shared -G 0 -Xcpluscomm` (and -mips1, identical frames),
 * 2026-09-23. Frames, in bytes, for 0/1/2/3 pads:
 *
 *   int_leaf               0  0  0  0   frameless leaf
 *   float_leaf             0  0  0  0   frameless leaf with FP locals
 *   volatile_leaf          8  8  8  8   volatile local's home, no call
 *   coloured_across_call  40 40 40 40   live across calls in a callee-saved reg
 *   nothing_across_call   24 24 24 24   a call, nothing live across it
 *   param_across_call     24 24 24 24   only a parameter across it (caller's
 *                                        argument area, not this frame)
 *   array_only            32 32 32 32   an array local, no scalar homed
 *
 * See docs/compiler-laws/ido-5.3.md, L99, "Refinement -- when an unreferenced
 * local takes a home".
 */

extern void sink_i(int);
extern int src_i(void);
extern int use_buf(int *);

int int_leaf_0(int a, int *p) {
    int x;
    x = a * 3;
    *p = x;
    return x + 1;
}

int int_leaf_1(int a, int *p) {
    int x;
    int pad0;
    x = a * 3;
    *p = x;
    return x + 1;
}

int int_leaf_2(int a, int *p) {
    int x;
    int pad0;
    int pad1;
    x = a * 3;
    *p = x;
    return x + 1;
}

int int_leaf_3(int a, int *p) {
    int x;
    int pad0;
    int pad1;
    int pad2;
    x = a * 3;
    *p = x;
    return x + 1;
}

float float_leaf_0(float a, float *p) {
    float x;
    x = a * 3.0f;
    *p = x;
    return x + 1.0f;
}

float float_leaf_1(float a, float *p) {
    float x;
    int pad0;
    x = a * 3.0f;
    *p = x;
    return x + 1.0f;
}

float float_leaf_2(float a, float *p) {
    float x;
    int pad0;
    int pad1;
    x = a * 3.0f;
    *p = x;
    return x + 1.0f;
}

float float_leaf_3(float a, float *p) {
    float x;
    int pad0;
    int pad1;
    int pad2;
    x = a * 3.0f;
    *p = x;
    return x + 1.0f;
}

int volatile_leaf_0(int a) {
    volatile int t;
    t = a * 3;
    return t + 1;
}

int volatile_leaf_1(int a) {
    volatile int t;
    int pad0;
    t = a * 3;
    return t + 1;
}

int volatile_leaf_2(int a) {
    volatile int t;
    int pad0;
    int pad1;
    t = a * 3;
    return t + 1;
}

int volatile_leaf_3(int a) {
    volatile int t;
    int pad0;
    int pad1;
    int pad2;
    t = a * 3;
    return t + 1;
}

int coloured_across_call_0(int a, int n) {
    int x;
    int i;
    x = a * 3;
    for (i = 0; i < n; i++) {
        sink_i(x);
        sink_i(x + i);
    }
    return x + 1;
}

int coloured_across_call_1(int a, int n) {
    int x;
    int i;
    int pad0;
    x = a * 3;
    for (i = 0; i < n; i++) {
        sink_i(x);
        sink_i(x + i);
    }
    return x + 1;
}

int coloured_across_call_2(int a, int n) {
    int x;
    int i;
    int pad0;
    int pad1;
    x = a * 3;
    for (i = 0; i < n; i++) {
        sink_i(x);
        sink_i(x + i);
    }
    return x + 1;
}

int coloured_across_call_3(int a, int n) {
    int x;
    int i;
    int pad0;
    int pad1;
    int pad2;
    x = a * 3;
    for (i = 0; i < n; i++) {
        sink_i(x);
        sink_i(x + i);
    }
    return x + 1;
}

int nothing_across_call_0(int a) {
    int x;
    x = src_i();
    return x + a;
}

int nothing_across_call_1(int a) {
    int x;
    int pad0;
    x = src_i();
    return x + a;
}

int nothing_across_call_2(int a) {
    int x;
    int pad0;
    int pad1;
    x = src_i();
    return x + a;
}

int nothing_across_call_3(int a) {
    int x;
    int pad0;
    int pad1;
    int pad2;
    x = src_i();
    return x + a;
}

int param_across_call_0(int a) {
    sink_i(7);
    return a + 1;
}

int param_across_call_1(int a) {
    int pad0;
    sink_i(7);
    return a + 1;
}

int param_across_call_2(int a) {
    int pad0;
    int pad1;
    sink_i(7);
    return a + 1;
}

int param_across_call_3(int a) {
    int pad0;
    int pad1;
    int pad2;
    sink_i(7);
    return a + 1;
}

int array_only_0(int a) {
    int buf[2];
    buf[0] = a;
    buf[1] = a * 3;
    return buf[0] + buf[1] + use_buf(0);
}

int array_only_1(int a) {
    int buf[2];
    int pad0;
    buf[0] = a;
    buf[1] = a * 3;
    return buf[0] + buf[1] + use_buf(0);
}

int array_only_2(int a) {
    int buf[2];
    int pad0;
    int pad1;
    buf[0] = a;
    buf[1] = a * 3;
    return buf[0] + buf[1] + use_buf(0);
}

int array_only_3(int a) {
    int buf[2];
    int pad0;
    int pad1;
    int pad2;
    buf[0] = a;
    buf[1] = a * 3;
    return buf[0] + buf[1] + use_buf(0);
}
