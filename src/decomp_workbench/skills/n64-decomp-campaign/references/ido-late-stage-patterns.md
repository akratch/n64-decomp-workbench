# IDO late-stage patterns

These are experiment prompts, not rewrite recipes. Re-check the object after
each change.

## Treat source spelling as compiler input

For a close function, preserve and test:

- declaration order and scope;
- which local carries an index, pointer, counter, or temporary result;
- expression grouping and assignment placement;
- integer versus floating literal type;
- loop source form before manually reproducing an apparent unroll;
- call-site prototypes and translation-unit visibility.

Semantically equivalent source can change expression tables, web construction,
spill homes, and later allocation decisions. Each classic "fake match" idiom
pokes exactly one allocator input — a dead web (`if (g) {}`) takes the next
free pool slot, a K&R implicit-int return changes coalescing, a named
intermediate changes CSE ownership, statement line-grouping moves the
schedule — so pick the idiom whose input the verdict names, one variant each.

Check the field guide's dead-families table first
(`decomp-workbench guide` prints the index): declaration-order permutation,
commutative operand swaps, and bare discarded expressions were each searched
exhaustively across multiple campaigns and are inert. Testing a buried family
once is cheap; re-searching it is how a day disappears.

Under line-sensitive frontends the placement of newlines is itself compiler
input: two token-identical bodies grouped differently across source lines can
schedule differently. When token-level spellings are exhausted, bisect
whitespace before concluding the schedule is unreachable.

cfe numbers each statement by the logical line it starts on, so the numbers a
natural layout produces are non-decreasing along statement order but not
strictly increasing — ties are free, via several statements on one physical
line or trailing-backslash splices. Splicing a block's closing brace and the
statement after it back to the block's first line hands that statement a
number from inside the block, which one-statement-per-line layouts cannot
express (field-guide lever 25). What matters is the relation between
statements' numbers, not their absolute values: uniform shifts are inert.
Line-number reachability is therefore two dials, not one — a statement move
changes which numbers a statement can carry at all; a tie changes the
relation between two of them — and a sweep that varies only physical layout
under a fixed statement order has not searched the space.

## Diagnose allocation rather than decorating it

When opcode shape stabilizes but registers differ:

1. Localize the mismatch range.
2. Capture the narrowest relevant `globalcolor`/UGEN trace.
3. Inspect one procedure and web at a time.
4. Form a lifetime hypothesis: an earlier use, a surviving pointer, or an
   unnecessary temporary may keep a color unavailable.
5. Test the source-lifetime change, then remove diagnostic scaffolding.

The Hartley finish showed that removing a fake can repair a distant coherent
register swap. A fake local is never neutral merely because its generated
instructions appear harmless nearby.

## Step back from a false local optimum

The Aquas finish showed that a manually forced loop can match a local region
while producing the wrong whole-function allocator topology. If a small loop
needs an escalating stack of fakes, forced conditions, or explicit unrolling:

1. Restore the natural source form.
2. Re-evaluate variable roles and reuse across the whole function.
3. Check declaration order and earlier expression lifetimes.
4. Let the compiler perform an observed unroll when the source topology is
   correct.

Use manual unrolling only when the target evidence requires source-level
unrolling, not because it temporarily improves a local score.

## Use force probes safely

A forced register/color, retained listing edit, or compiler patch is valuable
when it answers one question: "would this late-pass decision explain the
residual?" Record the exact control and result. Then translate the result into
a maintainable source hypothesis. Never commit the forced artifact as the
decompilation answer.
