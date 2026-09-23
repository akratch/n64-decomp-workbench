/*
 * L99 qualification fixture: a value homed in the frame across a call
 *
 * Synthetic C written for the workbench (CC0); no game code. Each case is
 * compiled four times, with 0..3 wholly unreferenced `int` locals (padN)
 * declared after the live ones, and the frame is read from the
 * `addiu sp,sp,-N` of each function. Measured with IDO 5.3 `cc -c -O2
 * -mips2 -32 -non_shared -G 0 -Xcpluscomm` (and -mips1, identical frames),
 * 2026-09-23. Frames, in bytes, for 0/1/2/3 pads:
 *
 *   local_across_call     32 40 40 48   declared int homed across the call
 *   float_across_call     32 40 40 48   declared float homed across the call
 *   temp_across_call      32 32 40 40   compiler temp (a * b) homed across it
 *
 * See docs/compiler-laws/ido-5.3.md, L99, "Refinement -- when an unreferenced
 * local takes a home".
 */

extern void sink_i(int);
extern void sink_f(float);

int local_across_call_0(int a) {
    int x;
    x = a * 3;
    sink_i(x);
    return x + 1;
}

int local_across_call_1(int a) {
    int x;
    int pad0;
    x = a * 3;
    sink_i(x);
    return x + 1;
}

int local_across_call_2(int a) {
    int x;
    int pad0;
    int pad1;
    x = a * 3;
    sink_i(x);
    return x + 1;
}

int local_across_call_3(int a) {
    int x;
    int pad0;
    int pad1;
    int pad2;
    x = a * 3;
    sink_i(x);
    return x + 1;
}

float float_across_call_0(float a) {
    float x;
    x = a * 3.0f;
    sink_f(x);
    return x + 1.0f;
}

float float_across_call_1(float a) {
    float x;
    int pad0;
    x = a * 3.0f;
    sink_f(x);
    return x + 1.0f;
}

float float_across_call_2(float a) {
    float x;
    int pad0;
    int pad1;
    x = a * 3.0f;
    sink_f(x);
    return x + 1.0f;
}

float float_across_call_3(float a) {
    float x;
    int pad0;
    int pad1;
    int pad2;
    x = a * 3.0f;
    sink_f(x);
    return x + 1.0f;
}

int temp_across_call_0(int a, int b) {
    sink_i(a * b);
    return a * b + 1;
}

int temp_across_call_1(int a, int b) {
    int pad0;
    sink_i(a * b);
    return a * b + 1;
}

int temp_across_call_2(int a, int b) {
    int pad0;
    int pad1;
    sink_i(a * b);
    return a * b + 1;
}

int temp_across_call_3(int a, int b) {
    int pad0;
    int pad1;
    int pad2;
    sink_i(a * b);
    return a * b + 1;
}
