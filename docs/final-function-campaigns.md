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

## cef4c: the last function, from 99.91% hosted to words=0

`func_ovl0_800CEF4C` (`lbParticleUpdateStruct`, 1,868 instructions) was the
last unmatched function in a full-project campaign. It went from a 99.91%
hosted frontier to an exact source through five stages, each recorded in a
standalone dossier
(`docs/history/postmortem-2026-08-24-cef4c-exact.md` is the after-action
review; the dossiers below are its evidence).

1. **Allocator reverse-engineering.** With the residual pinned at one
   register-allocation word, the campaign fully characterized IDO 7.1's
   Chow-priority coloring for the function — the `save/units` priority
   formula, the pop-order tie break, and the exact pop chain the target
   requires — by instrumenting `uopt` and exhaustively enumerating feasible
   pop orders. This did not move the residual; it explained precisely why
   every tested source family couldn't ("ALLOCATOR_MODEL.md" in the campaign
   dossiers).
2. **The one-word `as1` wall.** Nearly 5,000 compiled-and-compared source
   variants converged on a single fixed point: UGEN already emitted the
   target's instruction stream, but `as1`'s `peep_reg` copy-propagation
   rewrote one register on one instruction by path-local analysis, and no
   tested C spelling could suppress it. Binasm-level barrier probes proved
   the mechanism and its zero-cost artificial fix, but not yet a legal
   source route to it (`FABLE_HANDOFF.md`).
3. **The conditional-fjp barrier, proven at the phase boundary.** Ucode
   patch-and-replay found that inserting three (never two, never four)
   chained conditional branch-to-next records at a specific byte offset
   healed the wall with zero instruction cost, because UGEN's
   branch-to-next eliminator removes at most two conditional branches while
   `as1`'s copy-fact carry rule dies at the surviving one's transient block
   boundary. This was proven `words=0` by stream surgery before any source
   spelling reached it (`FJP_BARRIER_PROOF.md`).
4. **Making the barrier source-reachable.** A source-level `if/else`
   partition on the dispatch switch's range test, containing the empty-bodied
   triple-conditional statement, reproduced the barrier from C for the first
   time and healed the historical one-word residual — while introducing a
   new, unrelated dispatch-layout residual (high-case bodies relocated
   relative to the target's placement) (`PARTITION_BARRIER.md`). A lateral
   rediscovery of the same `as1` wall, from the integer-rotation side, found
   a donor-free three-word basin using the identical triple-read statement
   and gave the priority-arithmetic tables behind it (`O3AND_COUNTERDIAL.md`).
5. **Composition to words=0.** The exact source composed four independently
   proven mechanisms — the triple-conditional branch-to-next barrier, a
   goto-pair fallthrough inversion, a Duff-nested dispatch layout, and a
   ternary selector-temp reshape — none of which moved the residual alone.
   Composed, the local comparison reached `words=0` / `exact=true`
   (postmortem, "What the campaign actually took").
6. **The target-scope fix.** With a genuine local `words=0`, the hosted
   score still reported a nonzero residual. An ELF autopsy against ROM bytes
   found the hosted target object's own `.rodata` extraction had cut the
   function's literal pool short by 20 bytes (four constants mis-attributed
   to a neighboring symbol); a corrected target scored exact
   (`hosted-fix/TARGET_RODATA_FIX.md`).

Takeaway: the last percent of a hard function is rarely one more source
variant. It was an allocator model, a phase-boundary proof, a source route to
that proof, and a target-scope audit — four different kinds of evidence, in
that order. See
[references/late-stage-doctrine.md](../src/decomp_workbench/skills/n64-decomp-campaign/references/late-stage-doctrine.md)
and
[references/evidence-ladder.md](../src/decomp_workbench/skills/n64-decomp-campaign/references/evidence-ladder.md)
for the doctrine this campaign earned.

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
