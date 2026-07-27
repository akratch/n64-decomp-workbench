# Worked example: from register trace to source statement order

- Function: [`func_80049794`](https://github.com/akratch/Diddy-Kong-Racing/blob/6c626c9b797c1241b39b1164c3e1955459778330/src/racer.c)
- Matching commit: `6c626c9b`
- Target size: 2,625 instructions

## Two different allocation questions

The plane physics function had two late plateaus:

1. The expected long-lived FP value was not promoted into `f20/f21`, and the
   frame was wrong.
2. After recovering the entire FP allocation and frame, 19 words remained,
   differing only in temporary GPRs in one final conditional.

The first belonged to uopt’s web construction/globalcolor. The second belonged
to ugen’s expression-temporary free list. Treating them as one generic
“register pressure” problem produced a very large, unfocused source search.

## Part 1: expose the missing web

Globalcolor traces reported costs per web. Earlier reasoning concluded that the
desired promotion was not profitable for every web then present. The useful
question became: could the source create a different web?

This two-statement form did:

```c
var_f20 = x * x + z * z + y * y;
var_f20 = sqrtf(var_f20) - 2.0f;
```

Under the measured compiler, the pre-call input and post-call factor became one
long live range. That changed the allocator economics, recovered `f20/f21`,
the 248-byte frame, and the target FP-register histogram.

This did not contradict the measured costs of the old webs; it changed which
web existed.

## Part 2: trace physical allocation events

The last 19 differences were isolated to `t3`–`t9`. A deeper ugen trace logged:

- allocation serial and source line;
- physical register;
- append/remove events;
- free-list address and queue snapshots;
- node/destination-hint information in later revisions.

An early model treated the first observed registers as the entry queue. That
was wrong because allocations and releases already interleaved.

The workbench reconstructs logical values:

```sh
decomp-workbench trace-fifo ugen.log \
  --registers t3,t4,t5,t6,t7,t8,t9 \
  --list-address 10019da4 \
  --show-events \
  --json > fifo.json
```

The resulting schedule says “allocate value 17, then free value 12” rather
than only “saw `t6`, then `t4`.” This made it possible to compare event
structure even when physical queues differed.

## The force-choice oracle

A diagnostic ugen control forced the 22 target register picks. With those
choices, the existing source produced the exact object. This established that
the source was already structurally sufficient and that the residual could be
explained by allocation order.

The force mode was never proposed as the matching compiler. It was a causal
test that narrowed the source search.

## Source change guided by the schedule

The solved event order required the shift temporary to allocate and release
before the damping expression’s temporaries. Writing the shift as its own
statement at the top of both arms did exactly that:

```c
if (!(gCurrentRacerInput & R_TRIG)) {
    var_t0 >>= 1;
    obj->trans.rotation.x_rotation -=
        (obj->trans.rotation.x_rotation * updateRate) >> 4;
    obj->trans.rotation.x_rotation -=
        ((var_t0 * 19) * updateRate) >> 1;
} else {
    var_t0 >>= 1;
    /* analogous damping and factor-30 update */
}
```

No extra target instruction was needed; the source boundary changed the
temporary event order.

## Result

Commit `6c626c9b` records a byte-identical function and successful whole-ROM
verification.

## Limits

The trace established strict FIFO behavior for the selected temp class in this
compiler/function campaign, including that tested deferred-free timing policies
did not change the outcome. It is not a proof that every IDO register class,
pass version, or expression follows the same policy.
