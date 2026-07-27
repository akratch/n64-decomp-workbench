# Worked example: when a worse score was progress

- Function: [`func_80017A18`](https://github.com/akratch/Diddy-Kong-Racing/blob/17f4bddd9f7f94ba12d1501bf8f85fe8e7e05020/src/objects.c)
- Matching commit: `17f4bddd`
- Target shape: 279 instructions, `0x120`-byte frame

## The plateau

The object collision routine had the correct broad control flow and many
correct stack homes. A normalized scorer rewrote every `N(sp)` operand to the
same placeholder. That was intended to make structural comparison easier, but
it also hid a whole-frame shift and ranked candidates incorrectly.

The investigation also interpreted stores and reloads around a high-pressure
facet loop as explicit source copies. That assumption required extra variables
and source-level save/restore scaffolding.

## Tools used

Three views were kept side by side:

1. Exact instruction words and literal stack offsets.
2. The repository’s actual asm-differ score.
3. asm-differ penalty buckets for stack, register allocation, reorder,
   insertion, and deletion.

The reusable workbench supplies view 1 plus structural/register summaries:

```sh
decomp-workbench compare target.o candidate.o \
  --symbol func_80017A18 \
  --show-diff
```

For this campaign, asm-differ itself was imported and run with GNU objdump
`-d -r -z -j .text`. A handwritten approximation had been shown to misrank
candidates, so the approximation was retired.

## The decisive transition

The candidate at score 296 represented the stores/reloads as source-level
copies. Reading origin values directly into the working `x2/y2/z2` locals and
deleting that scaffolding changed the score from 296 to 441—apparently a
regression.

The penalty decomposition showed the opposite:

```text
instructions: 279 / 279
insertions:   0
deletions:    0
reorders:     0
remaining:    low FP temporary-register rotation
```

The stores were compiler spills: the original values occupied registers that
the inner loop needed to reuse. Once the source modeled that correctly, the
entire instruction order aligned.

Computing the interpolation deltas in `x, y, z` order rather than `z, y, x`
then fixed the remaining `{f4,f6,f8}` phase and produced score zero.

## How the workbench helps

Use a campaign ledger to retain candidates across a scalar-score regression:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol func_80017A18 \
  --compile-command './compile-object.sh {source} -o {output}' \
  --ledger .workbench/object-collision.jsonl \
  --jobs 8
```

Filter the ledger by:

- exact instruction count;
- exact frame;
- zero opcode or normalized structural distance;
- contiguous register mismatch ranges;
- literal stack-offset histogram.

Then inspect native asm-differ buckets before discarding a candidate.

## Result

Commit `17f4bddd` records ordinary C with the `GLOBAL_ASM` fallback removed and
successful ROM verification.

## Limits

The metric progression demonstrates that this scalar score was not a geometric
distance to the matching source. It does not imply that a worse score is
usually better; the evidence was the simultaneous elimination of structural
penalties and exact recovery of the frame/stack topology.
