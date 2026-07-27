# Worked example: finding the pass that moved one store

- Function: [`func_8008FF1C`](https://github.com/akratch/Diddy-Kong-Racing/blob/8131d0da107d741084107545554570f9c0392c96/src/menu.c)
- Matching commit: `8131d0da`
- Target size: 371 instructions

## The misleading symptom

The menu function appeared to have a tiny register mismatch. Retaining the
assembly between ugen and as1 showed a more precise problem: the desired
register was already present, but one store occupied the wrong schedule slot.

The relevant listing shape was:

```asm
sw       $2,0($16)
.noalias $17,$sp
lh       $10,0($17)
beq      $10,-1,$1128
```

Because the listing did not state that `$17` and `$16` were disjoint, as1
could not sink the store past the load into the branch delay slot.

## Tool used: retained-pass replay

The campaign retained `unit.s`, edited one directive, then reran only as0 and
as1. The curated command is:

```sh
decomp-workbench replay-as1 unit.s candidate.o \
  --insert-before '^\tlh\t\$10,0\(\$17\)$=\t.noalias\t$17,$16' \
  --as0-command '/ido/as0 -G 0 -EB -g0 -O2 {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 -elf -G 0 -p0 -EB -g0 -O2 {binasm} -o {object} -t {symtab}'
```

The unedited replay was the control. The inserted `.noalias $17,$16` replay
produced zero strict word differences for the function. This established that
the downstream scheduler and one missing alias fact were sufficient to explain
the final placement.

## Trace the fact to its source form

The next question belonged upstream: why did uopt/ugen not produce that alias
relationship?

Alias-state instrumentation and reduced microcases compared:

- a pointer variable walking the render-detail array;
- direct indexing of the global render-detail array.

For this site, direct indexing retained named-global provenance and produced
the required register-pair `.noalias`; the pointer walk did not.

The curated reproduction path instruments the pinned uopt source and
summarizes its structured descriptors:

```sh
decomp-workbench instrument-uopt-alias \
  build/5.3/uopt.c /tmp/uopt.alias.c

DKWB_UOPT_ALIAS_TRACE=1 ./compile-candidate.sh 2> /tmp/alias.log
decomp-workbench trace-alias /tmp/alias.log --show-queries
```

The report distinguishes fresh, direct, and retained base paths and shows both
sides of each observed may-alias/no-alias query. The original campaign used
several evolving trace schemas; this profile preserves the stable,
source-independent fields rather than every exploratory field.

Direct indexing initially generated extra address work. Further measurements
localized that cost:

- a variable inner-loop bound prevented the required flat-index
  strength-reduction;
- the literal `-1` inner bound exposed the trip count;
- deriving `trackY` as `trackSelectY + i + 1` made it affine in the outer
  induction variable and avoided a separate loop-invariant spill.

The final ordinary code-generation detail was evaluating the masked-high-bits
term first in six `copyViewPort` OR expressions.

## Result

The matching source uses direct indexing, a literal inner bound, and the affine
outer-loop expression. Commit `8131d0da` records the C match and whole-ROM
verification.

## Why the tool mattered

Without the retained listing, experiments targeted “two wrong registers” and
ugen free order. Pass replay identified:

```text
uopt       decided alias provenance
  ↓
ugen       translated that information into .alias/.noalias directives
  ↓
as1        selected the legal delay-slot schedule
```

Each subsequent experiment could be aimed at the pass that owned the fact.

## Limits

Injecting the directive proved sufficiency, not historical origin. The source
experiments and original-IRIX/static-recomp differential supplied the stronger
evidence about where the directive came from for this case. The result should
not be generalized to every pointer-versus-array expression without a
microcase under the relevant compiler.
