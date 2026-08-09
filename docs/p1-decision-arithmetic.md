# The p1 decision arithmetic

**Read this if:** a trace or a hand census gives you `save`, `nocs`,
`totalsave`, `chargeA`, or `chargeB` for a web and you are not sure which of
them is the actual decision, which are just rank, and which source edit moves
which one. This page is the whole formula, worked end to end on one real
kill, with the `uopt.c` line for every term. It is the specification for
`workbench cascade`/`occmap` (WB-110), and the detail behind
[compiler laws L28–L37](compiler-laws/ido-5.3.md#p1-the-global-colour-allocator).

Everything here is IDO 5.3's `f_compute_save` / `f_globalcolor` / `f_split`,
measured on the GE007 `object_interaction` campaign (54 → 0 differing words).
Every number below was cross-checked against a full sweep of that function's
decision records (`p1dec`/`savedetail`/`saveocc`), not sampled.

## The one inequality that decides everything

p1 visits webs in priority order and asks exactly one question per web:

```
net <= bestcost ?  YES -> split (memory-resident, no colour)
                    NO  -> colour it
```

`bestcost` is the cheapest colour still available to the web at the moment
it is decided — a property of which colours its already-decided neighbours
have taken, not of the web itself. `net` is a property of the web alone.
**There is no third outcome.** A brief that says "make p1 decline this web"
is asking for exactly one thing: push `net` at or below whatever `bestcost`
turns out to be when the web is reached. Nothing else in the pass has a say.

A trace typically prints `totalsave` and `net` as if they were two different
numbers to reconcile by hand. They are not — `totalsave = save x nocs`, and
that product cancels back to `net` exactly, in every record checked (1454 of
1454, zero discrepancies). Read `totalsave` and `net` as one field with two
names, and the inequality above as the whole decision:

```
net 4.000 <= bestcost 0.000 ?  NO  ->  colour it, c27
```

is a complete, self-contained account of a colouring decision. Five loose
fields recombined by hand is the same fact, harder to read.

See [L28](compiler-laws/ido-5.3.md#l28-p1s-decision-is-net--bestcost-and-totalsave-is-net).

## `net`: gross minus the two boundary charges

```
net = gross - chargeA - chargeB
```

`gross` is the sum, over every occurrence of the web, of `(uses + defs) x
block_weight` for that occurrence's block — this is L7's formula, unchanged.
`chargeA` and `chargeB` are the two boundary charges L7 already named without
naming their mechanisms. Both are documented below with their `uopt.c`
coordinates. Every term in `gross` is non-negative, so **the only way `net`
goes to zero or below is through chargeA or chargeB** — occurrence count and
loop depth can only push it up.

### chargeA — a predecessor-outside-the-web charge

```
chargeA = 1.0 x block_weight, summed over every occurrence whose block
          has a predecessor OUTSIDE the web's own block set (the "nl" flag),
          excluding occurrences canmoverlod exempts
```

The `nl` flag is written in the occurrence builder, `uopt.c` **150695–150745**
(`nl = occ+21`). A web with even one non-exempt `nl` occurrence has `chargeA
>= 1`, and because `bestcost` for a fresh web at a contested site is often
`0`, that alone is enough to make it undeclinable — no amount of reshaping
the web's live range removes an occurrence's `nl` status without removing
the occurrence itself.

The GE007 campaign's own target web illustrates the trap directly: one
occurrence, `2.0f * x`, is `x + x` under IDO's own re-association — a single
source expression that reads the same value **twice** and so contributes two
uses to `chargeA`'s block, not one. A stage that reasoned about this
occurrence as if it were a single ordinary read undercounted its own
`chargeA` contribution by half.

See [L30](compiler-laws/ido-5.3.md#l30-chargea-the-boundary-charge-exactly).

### chargeB — a store-placement charge, not a loop charge

```
chargeB = sum of weight(bb(q)) over occurrences q where
          w34  AND  NOT o23  AND  o22  AND  (defs != 0 OR nl = 0)

  w34 = the web has at least one occurrence that is a definition
  o22 = NOT f_allsucmember(successors-of-block, web+0x14)
        i.e. the definition does not provably reach every successor block
```

`uopt.c` **154761–154808** is the gate itself; `w34` is set at **149841–149851**
and recomputed per split at **153573–153615**; `o22` is computed at
**150947–151122**.

Read in plain language: `chargeB` fires when the web has a **definition
whose value does not reach every path out of its block** — a store the
optimizer cannot prove is safe to skip on some path. This is a fact about
*where a definition sits relative to control flow*, not about whether a loop
is anywhere nearby. `weight(bb)` is the same `block_weight` multiplier L7's
`gross` formula already uses, and a loop body's blocks carry ×10 against a
straight-line block's ×1 — so a loop-adjacent definition typically produces
a *large* `chargeB` contribution, but a straight-line one produces a small,
nonzero contribution just as legitimately.

**This distinction is the single most expensive one in the whole campaign to
get wrong.** A donor-fusion kill was first explained as working "because the
donor's definition precedes a loop and its use is inside it" — a plausible
story, built from the one example available, where every donor tried
happened to be loop-adjacent. Reading `chargeB` directly from the pass
disproved it: a second kill, built later with *zero* loop involvement and
every contributing weight equal to 1, fired `chargeB` exactly the same way.
The loop was never a precondition. It only ever supplied the ×10 multiplier
on a mechanism that fires regardless. See
[L36](compiler-laws/ido-5.3.md#l36-chargeb-exactly-a-store-placement-term),
which corrects
[L35](compiler-laws/ido-5.3.md#l35-fusing-a-donor-imports-its-chargeb)'s
original causal account without changing L35's pricing result.

**Two ways to make `chargeB` fire, priced very differently.** Both routes put
a `defs != 0` occurrence with `o22` true onto the web:

1. **Fusion.** Rename a *spilled* donor's references onto the target symbol
   (see [L32](compiler-laws/ido-5.3.md#l32-web-fusion-by-rename-breaks-block-containment)
   for the storage-keyed mechanism). This imports the donor's own `chargeB`
   contribution, but it costs whatever the donor's own ROM-spilled row count
   is — GE007's cheapest available donor cost 2 rows; others in the same
   family cost 4, 6, and 7. No zero-cost donor existed in 290 tried fusions.
2. **A discarded read.** A statement that reads the web's own symbol and
   drops the value — `if (v);`, or better, a value-guarded form like
   `if (v != 0.0f);` — costs **zero instructions** (it is eliminated before
   codegen) but still creates an occurrence, and where the web already has a
   qualifying definition elsewhere, that occurrence alone can satisfy `o22`
   for the whole region. This is strictly cheaper than fusion when it is
   available at all: it needs no donor and no second stack home. See
   [L37](compiler-laws/ido-5.3.md#l37-the-discarded-expression-lever).

The discarded-read route is easy to miss because it leaves **no trace in the
object** — there is nothing to see in a disassembly diff, because nothing
was emitted. See [the metric traps
chapter](metric-traps.md#trap-6-a-statement-can-cost-zero-instructions-and-still-be-load-bearing)
for the general lesson.

## `nocs` and `save`: L7's divisor, exactly

```
nocs = f(occ + bbcard)
f(X) = X                    for X < 3
f(X) = ((X - 2) >> 2) + 2   otherwise

bbcard = |web+0x0c|   (the live-block bitvector's cardinality —
                        blocks the web is LIVE INTO, not blocks
                        it is read or written in)

save = net / nocs   (doubled when dtype == 12, which never fired
                      in this function — dtype was always in {0,6,8,13})
```

`f_compute_save`, `uopt.c` **154631–154905**. This is
[L7](compiler-laws/ido-5.3.md#l7-the-save-formula-exactly)'s `div`, under
the pass's own field name, sourced and floored: `nocs` never drops below 2
for any web with two or more live-in blocks, which means **removing an
occurrence from such a web can only ever lower `save`**, never raise it by
shrinking the divisor. A same-campaign stage lost real time to the opposite
assumption — proposing to drop a web's rarest occurrence specifically to
step `nocs` down and double `save`, when the web in question was already at
the floor and the removal only lowered `gross`.

`save` sets **rank** among webs whose `net <= bestcost` already agrees; it
never changes the decision itself. Confusing the two — reading a `save`
change as if it could flip a colour/split outcome — is the same trap as
reading `nocs` as a lever on the decision rather than on the ranking.

See [L29](compiler-laws/ido-5.3.md#l29-nocs-exactly--l7s-divisor-sourced-and-floored).

## Colour order: ties go to the lower web number

p1 visits webs sorted by `(-save, +web)` — highest `save` first, ties broken
by **ascending web number**, i.e. by which web was founded earlier. A
threshold reasoned against a lower-numbered competing web is `>=`, not the
strict `>` a plain reading of "highest save wins" suggests. This one notch
is what makes web fusion by rename (below) a real lever rather than a dead
end: a "no interference construct can help, because any blocker of the
smaller web is by construction a blocker of the larger one" argument is only
as strong as the strict inequality it assumes.

See [L31](compiler-laws/ido-5.3.md#l31-p1s-colour-order-tie-break-ascending-web-number).

## Webs are keyed on storage, not on the C name

Two constructs that reach the same stack slot — a plain access, a `struct`
wrapper, a `union` member, a pointer pun — are the **same web** to p1, and
compile to the same object, whatever they are named in C. This is why a
"donor" kill and a fusion kill both work the way they do: renaming a local's
references onto another symbol only changes anything when it changes which
storage the occurrences resolve to.

**One consequence worth stating on its own: p1 never colours into the ugen
local ring.** The FP colour set is exactly `{$f0, $f2, $f12, $f14, $f16,
$f18, $f20}` (see
[L27](compiler-laws/ido-5.3.md#l27-the-fp-colour-map-corrected)); `$f4`,
`$f6`, `$f8`, `$f10` are ugen's scratch rotation and are never a p1 colour in
either direction. A minted web at a site where the ROM has no web there
therefore costs at least 2 rows (one definition, one use) — there is no
route to a zero-cost plant there, and a zero-cost result at such a site is
evidence the decompiled C is *missing* a temp the true source had, not a
free lever.

See
[L26](compiler-laws/ido-5.3.md#l26-webs-are-keyed-on-storage-not-on-the-c-name)
and
[L38](compiler-laws/ido-5.3.md#l38-p1-never-colours-into-the-local-fp-ring).

## Worked example: the GE007 kill, end to end

The target web (`sp4A0`, a `f32` gate value) had one occurrence,
`2.0f * sp4A0`, that alone contributed two uses to a block with a
predecessor outside the web — `chargeA >= 2` on that occurrence by itself,
with `bestcost = 0.0` at the site. By the inequality above, `net >= 1 >
bestcost = 0` for *every* live-range shape that kept the occurrence: the
web could never be declined by reshaping it. It had to be removed, or its
`chargeB` had to be driven negative-net before it was founded at all.

Two source constructs did that, at very different prices:

| Construct | Mechanism | Price |
|---|---|---|
| Fuse a spilled donor (`sp384`) onto the symbol | Imports the donor's own `chargeB` via storage-keyed web fusion | 2 rows — the donor's own ROM-spilled row count, the cheapest of four donors tried (2, 4, 6, 7) |
| `if (sp4A0 != 0.0f);` at the right source line | The discarded read alone supplies `o22`/`w34` for the region | **0 instructions** — no donor, no second stack home |

Both reach `net < 0` for every split piece of the web, both send it to
`f_split` as memory-resident, and both reproduce the ROM's five `1184(sp)`
touches exactly. The second is strictly better, and it is invisible to a
disassembly-only search: there is no instruction to notice missing, because
none was ever emitted by either side until the statement is added. Finding
it required an external oracle (a sibling game's independently matched
decompilation of the evolved version of this routine, which carries the
identical discarded-read idiom in the identical place) rather than more
disassembly reading.

## See also

- [Compiler laws: IDO 5.3, the p1 section](compiler-laws/ido-5.3.md#p1-the-global-colour-allocator) —
  the full law entries this page draws its numbers from.
- [Metric traps](metric-traps.md) — the scoring and pricing mistakes this
  campaign paid for, several of them made *while reasoning about* this exact
  arithmetic.
- [Postmortem: GE007 `object_interaction`](postmortem-2026-08-09-ge007.md) —
  the discarded-read construct above is the campaign's closing move (error
  eleven).
- [Trace analysis](trace-analysis.md) — reading `p1dec`/`savedetail`/`saveocc`
  records directly, for anyone reproducing these numbers rather than
  trusting this page's arithmetic.
