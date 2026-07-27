# Worked example: tracing a globalcolor tie

- Function: [`trackbg_render_flashy`](https://github.com/akratch/Diddy-Kong-Racing/blob/faebc894b48cddc60fd2ae32acf7fdf3260cad79/src/tracks.c)
- Matching commit: `faebc894`
- Pass investigated: IDO 5.3 `uopt`

## The plateau

The track renderer was structurally close, but small source edits caused
nonlocal changes between FP registers such as `f16` and `f18`. Instruction
count and broad expression structure were no longer enough to explain why one
candidate entered the target allocation.

## Tool used

Historical environment-gated static recompiles of `uopt` logged live-range
save/cost inputs, forbidden colors, and selected registers. The curated
workbench includes:

- a hash-pinned decision/force-choice profile:
  `instrument-uopt-globalcolor`;
- a parser and ranking view for both the retained `CSAVE`/`CUP` logs and the
  profile's later `[CDX]` records:
  `trace-globalcolor`.

Typical use:

```sh
decomp-workbench instrument-uopt-globalcolor \
  build/5.3/uopt.c /tmp/uopt.traced.c

CDX_LOG=1 CDX_PROC=<procedure-ordinal> ./compile-candidate.sh \
  2> /tmp/globalcolor.log

decomp-workbench trace-globalcolor /tmp/globalcolor.log --top 30
```

The instrumentation-off compiler was checked against stock output during the
campaign. A community user reproducing the experiment should rerun the
[fidelity gates](../docs/compiler-instrumentation.md#required-fidelity-gates)
on their host and upstream revision.

## What the trace exposed

For the relevant ranges, allocation priority tied. In the measured generated
pass, the tie was resolved by the order in which expressions reached the
allocator’s table. That made otherwise dead or folded source expressions
observable through later register choice even though the expressions emitted
no instructions of their own.

This was a narrower and more actionable statement than “the compiler is
random” or “more register pressure is needed.” It suggested testing source
forms that preserve output structure while changing expression creation order.

## Source changes guided by the trace

The matching source includes two definitions that do not survive as standalone
instructions:

```c
pad_sp100 = 2.0f * scaledXSin;
/* ... */
pad_sp108 = var_f16;
```

In this function and compiler profile, they changed the table order and flipped
the relevant allocation tie. Other load-bearing expression forms recorded by
the matching commit were:

- an explicit unary minus in `zPositions[5]`, producing the target’s homed
  temporary;
- reassigning `scaledXCos = 1280.0f`, keeping the `320.0f` computation in the
  required register-resident form;
- using `pos.f[2]` in one UV expression, changing final operand order.

The trace also clarified an apparent uninitialized `sp78` reload: it was the
compiler’s join behavior for a local left unassigned on one path, not evidence
of a source-level copy.

## Result

Commit `faebc894` records a byte-identical function and successful full-ROM
verification from C.

## Reusable workflow

1. Establish that opcode order, frame, and count are already in the target
   basin.
2. Trace allocator candidates and decisions.
3. Identify ties or one isolated choice instead of guessing at generic
   pressure.
4. Use a force-choice control, if available, to test sufficiency.
5. Search source changes that affect the measured web/table order.
6. Turn instrumentation off and rerun the project’s exact verification.

## Limits

This experiment establishes how the measured IDO 5.3/static-recomp profile
selected these registers for this translation unit. It does not establish that
all IDO globalcolor ties are resolved identically, nor that the final C text is
the historical source text.
