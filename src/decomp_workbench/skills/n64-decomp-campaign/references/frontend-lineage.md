# Frontend lineage

The compiler is a variable, not a constant. A translation unit can have been
built by a frontend from a different toolchain generation than its backend,
and the resulting object is then unreachable from the assumed frontend no
matter what source is written. This reference exists because one campaign
spent hundreds of variants — and a prior campaign spent weeks — against a
dispatch shape that an algorithm-level analysis later proved unreachable,
while an authentic 1992 frontend reproduced it word-for-word on the first try.

## When to suspect it

- A dispatch or convention the project compiler provably cannot emit: wrong
  jump-table arity for the case count, comparison chains in source order
  (IDO-family frontends sort case values), compare operands in the wrong
  order with hoisted constants.
- Deviations that cluster by translation unit while neighboring functions
  match the project compiler byte-for-byte — especially when the identical
  source idiom lowers differently in another TU.
- A residual that hundreds of spellings never move, in a function whose
  siblings match exactly.

Splat-style translation units can merge several original source files, so
judge each function's evidence separately; one "TU" may legitimately mix
frontends and even languages.

## What to do, in order

1. **Prove the impossibility before acting on it.** Instrument or statically
   read the assumed frontend's lowering algorithm (the workbench's
   compiler-instrumentation approach applies to frontends as well as
   backends) and reduce the target shape to a reachability question. "We
   tried everything" is a mood; "the only reachable state requires a
   duplicate case value the frontend rejects" is a result.
2. **Fingerprint the alternatives cheaply.** Same-generation and
   older-generation frontends (`accom`/`ccom` from the ECOFF era, `upas`
   for Pascal) emit ucode a newer backend accepts directly, so build a probe
   matrix through the identical backend: dense switch thresholds by case
   count, sparse-switch test order and layout, if-chain order, hoisted
   compare operand order, and the strength-reduction signature of a narrow
   loop counter. Minutes per probe; each cell either matches the target
   binary's pattern or excludes a candidate.
3. **Discriminate constructs before frontends.** Source-order chains are not
   switches in any IDO-family frontend — they are `if`/`else if` chains.
   Sorted tests with dispatch-first layout is one frontend's switch; sorted
   with bodies-first is another's; a value-split tree is Pascal's. Classify
   the dispatch before spending variants on the wrong construct.
4. **Only then port the function** through the winning pipeline, expecting
   the natural spelling to work: a correct frontend identification removes
   artifice rather than adding it. If your best candidate needs *more*
   hacks under the new frontend, the identification is probably wrong.

## Evidence discipline

A byte-exact reproduction through unmodified, community-archived binaries
identifies the historical *lowering* behaviorally; it does not name the exact
shipping point release. Say which claim you are making. Frontend strictness
is itself evidence: a construct the candidate frontend rejects (anonymous
unions, `//` comments, statements before declarations) tells you what the
original source could not have contained.
