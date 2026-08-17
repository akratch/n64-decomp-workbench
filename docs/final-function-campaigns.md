# Lessons from finishing the final functions

This guide turns the Hartley, Titania, and Aquas campaigns into reusable
decompilation practice. It contains no ROMs, proprietary compiler binaries, or
project-specific target objects.

## The campaign loop that worked

1. Establish the project build as the final oracle.
2. Use object comparison to classify the residual before changing C.
3. Hold instruction shape steady while investigating allocation-only residuals.
4. Use compiler traces and force probes to test a cause, then return to a
   source-level explanation.
5. Keep every promising source/object pair and its metrics; never trust a
   display percentage as the only record.

The critical UX rule is simple: the tool should say what kind of evidence it
has and what the next safe action is. A raw mismatch count by itself is not an
actionable diagnosis.

## Hartley: remove a fake before adding another one

The Hartley transform reached the final fraction of a percent with a fake near
the tail of the function. Removing that fake resolved an `a1`/`a2` swap and
produced the exact object.

Takeaway:

- A fake that appears locally harmless can alter a distant live range or a
  late register choice.
- When only a small, coherent register swap remains, first test removal of
  recent scaffolding and compare the affected range.
- Campaign ranking should retain structural signatures and object hashes, not
  only the highest scalar score. The best next move may be in a different
  score basin.

## Titania: distinguish source truth from presentation noise

Titania's standalone scratch could produce exact instructions, registers,
frame, and relocation layout while a browser score remained at 99.98%. The
residual was symbolization of compiler-generated rodata: a target named a
constant-pool address while the scratch emitted an equivalent `.rodata+offset`
reference.

Takeaway:

- `exact=true` is stronger evidence than a third-party percentage.
- A standalone scratch, its context, and the original translation unit do not
  necessarily have the same literal-pool symbol names.
- Put raw linked-word differences and relocation-layout differences in a
  separate bucket. They should recommend a linked-object or ROM check, not
  additional source mutations.

The comparison verdict and raw-difference breakdown exist specifically to make
this distinction visible.

## Aquas: a convincing local match can be the wrong topology

Aquas had a near-match that used a forced four-at-a-time timer loop plus fake
carriers. It matched the local loop unusually well but left a whole-function
allocator conflict. The exact source restored the natural scalar loop; once
variable roles, declaration order, expression trees, and lifetimes matched,
IDO unrolled it into the target code by itself.

Takeaway:

- If a small region requires increasingly artificial unrolling or fake values,
  step back and inspect whole-function variable reuse and live ranges.
- The source variable used for a table index can matter more than an equivalent
  local spelling. Reusing the right carrier may repair several distant register
  regions at once.
- A force-color build is excellent evidence that a web priority is causal. It
  is never proof that a forced compiler object is a source match.
- Cross-ROM structural comparison can rule out a regional source branch and
  turn another revision into a trustworthy structural witness.

## A practical decision table

| Comparator result | First response | Avoid |
|---|---|---|
| Instruction count or opcode mismatch | Fix control flow, loop form, expression tree, or call shape | Globalcolor forcing first |
| Same opcode shape; register mismatch | Trace one procedure/web and test a source-lifetime hypothesis | Adding opaque fakes everywhere |
| Exact except raw relocation words | Inspect verdict, context, and linked output | Chasing browser percentages |
| Structural match across ROMs | Use it as lineage evidence and keep one target as the source oracle | Calling it object-exact |
| Local loop nearly matches only with fakes | Revisit declarations, variable roles, and earlier expressions | Treating the local loop as isolated |

## Tooling changes shipped from these lessons

- Comparison verdicts and next-action guidance.
- A raw-difference breakdown that makes relocation-controlled words explicit.
- Cross-ROM structural acceptance mode that never masquerades as exactness.
- Portable register comparison across objdump dialects with and without `$`.
- Focused allocator-web inspection with stable saved-register names where the
  pinned profile permits it.
- Object-basin grouping, so campaigns expose genuinely different compiler
  outcomes instead of merely counting source spellings.

## Remaining high-value work

The [roadmap](roadmap.md) tracks the next layer. Of the items these campaigns
originally motivated, campaign manifests and object-hash basin grouping have
since shipped; still open are:

1. Stable web fingerprints across source variants, rather than volatile numeric
   web IDs.
2. Source/IR/listing provenance for temporary webs and stack homes.
3. Interference-edge explanations: which web made a color unavailable.
4. Linked-address alias classification using final linked output, not guesses
   from unlinked objects.

Build these as diagnostics with explicit confidence and provenance.
