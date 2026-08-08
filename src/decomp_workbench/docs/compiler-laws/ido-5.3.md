# Compiler laws: IDO 5.3

What this compiler *does*, as opposed to what to do about it. The
[field guide](../field-guide.md) is levers — source edits and the residual each
one moves. This page is mechanism: the rules the passes actually follow, each
with the evidence that established it and the earlier claim it corrected.

Both halves matter, and the second half more. Almost every law below replaced
a plausible, widely-repeated, wrong belief. Reading only the conclusions would
hand you the answers without the thing that makes them trustworthy, which is
the record of how the previous answers failed.

## Scope

Everything here is **IDO 5.3** (`cc` → `cfe` → `uopt` → `ugen` → `as1`) at
`-O2 -mips2 -G 0 -non_shared -Olimit 2000`. No law on this page has been tested
on another IDO release. Where a law depends on a driver default (ring widths,
list sizes) that is called out, because those are startup constants for one
driver configuration and not properties of the compiler.

The measurements come predominantly from one large procedure — 4644
instructions, 922 basic blocks — so "always" below means "in every case
observed in that procedure", never "provably, in all programs".

## Evidence tiers

| Tier | Meaning |
|---|---|
| **T1** | Measured with a gated instrumented compiler: the pass source was read, live records were logged, and a force knob reproduced a named object hash. |
| **T2** | Inferred from build outcomes: probe ladders, score deltas, hash collapses. The mechanism was not read directly. |
| **T3** | Single observation, not swept. Treat as a lead. |

**The identity gate.** A T1 claim is only T1 if the instrumented compiler was
gated: built with the instrumentation *disabled*, its object must be
byte-identical to the stock compiler's. Every instrument cited here passed that
gate, several against a stock object *and* one or more oracle hashes. An
ungated instrument attributes decisions to the wrong pass, which is worse than
having no instrument.

**Oracle hashes go stale.** A force set that reproduced a target hash on one
base often does not on the next, because adoptions move everything downstream.
The law usually survives; the hash does not. Re-gate an oracle on the current
base before believing a negative result from it.

**No impossibility claims.** Every closed lever below is recorded as *scoped* —
with the space that was actually covered — never as impossible.

---

## cfe (the front end)

### L1. Free order is cfe's operand order

The order in which `ugen` releases the two source registers of a binary
operation is the ucode **operand order**, and that operand order is the same
bit `cfe` emits as `rs`/`rt`. cfe owns the bit, uopt transports it, ugen
consumes it (see [L11](#l11-ugen-frees-a-binary-ops-sources-in-operand-order)).

**Receipt — T1.** Instrumented `ugen` traced both objects through one divergent
site: the allocation *request* sequence was identical on both sides, and the
divergence entered through the free list. One free transposition 100 rows
upstream accounted for a 117-row heal, reproduced three equivalent ways
(`FFSWAPS`, `FHEADS`, `FSETS`) to one object hash. ~14 builds.

**Falsifies.** The prior stage's claim that the divergence unit was the
**within-statement request order**. Request orders were measured identical; the
prize was a free-order bit, not a request-order bit. That in turn had already
replaced an earlier "the target holds one extra fp temp live across this
window" reading, which two independent probes (a hold-out and a rotation) both
refuted — both builds carried the same free list into the window.

**Scope.** Binary operations reaching ugen's binary-operand path. This bit is
**invisible in the emitted bytes**: the assembly at the deciding statement was
byte-identical on both sides, so no amount of disassembly reading will recover
it.

### L2. Claim order is source *condition* order; test order is canonicalized

Specific-register claims are ordered by the order the values appear as
**conditions in the source**. The emitted **test** order is canonicalized by
cfe and does not track it.

**Receipt — T2 over a T1 attribution.** A 29-build probe ladder. The decisive
observation: the target emits its two definitions in one order while *both*
gate conditions test in the other, and a pure condition swap moves claim rows
while healing exactly zero test rows. Reordering the normalization groups so
the second value claims first healed 5 rows and was adopted on both artifacts.

**Falsifies.** The immediately preceding claim that ROM claim order was
condition **use** order. The pure-condition-swap probe is precisely the
disproof: use order predicts test rows would move, and none did.

**Scope.** Floating-point specific claims. This does **not** close the residual
band it was found in; no order permutation reaches it, and a different lever
class was named as required.

### L3. Float `+` at an assignment root: one bit, two effects

For a float `+` at the root of an assignment's right-hand side, cfe emits `rs`
as the source's **right** operand, and allocates the fp ring in the order
`[pair₁, singleton, pair₂]` when the paired subtree is on the right, or
`[singleton, pair₁, pair₂]` when it is on the left. One source-association bit
drives both.

**Receipt — T1.** Hand stage capture, gated byte-identical against the driver's
own object. The cfe intermediate records change shape with the source
association. 47 scored builds; all 12 spellings enumerated.

**Falsifies.** No prior claim. **But a conclusion drawn from it was itself
falsified**: reading the unscheduled instruction stream showed the target's fp
allocation ordinals at the deciding statement *are* ours, so the "the target
needs two halves of one bit to disagree" conflict does not exist. The rule
stands; that corollary does not.

### L4. cfe owns the frame layout

The frame is one descending symbol-creation-order batch, plus LIFO-bucketed
temps.

**Receipt — T1**, double-gated instrument. Six forces reproduce a 15-row heal
to an exact hash; later sharpened when it turned out **no anonymous temps
exist** in the translation unit at all, and a single force on one frame-batch
ordinal reproduces the oracle hash exactly. A related law: the spill home is
**symbol-keyed**, so renaming a dead host moves it.

**Falsifies.** The claim that a 15-row constant family was a second *uopt* temp
population. The homes are already present in the cfe intermediate: the "second
temp population" was cfe frame layout.

### L5. There is no `acpp` stage for C in IDO 5.3

`cc` invokes `cfe` directly. Verified from `cc -show`.

**Receipt — T1**, with a measured consequence: multi-line statement splits,
comments, and same-type casts are **byte-proven inert**.

**Falsifies.** An inherited cross-campaign lever — the `acpp` line-assignment
trick from a different toolchain — which would otherwise have been searched
blind. Line-assignment levers still exist under 5.3, but not through `acpp`.

---

## uopt (the optimizer)

### L6. A save "occurrence" is a basic block, not a source reference

In uopt's save computation, one occurrence is one **basic block** in which the
web appears. Uses and defs are per-block counts.

**Receipt — T1.** Instrumented uopt with an extended occurrence record, gated
byte-identical; field offsets read from the pass itself; block pointers printed
and rank-ordered into a program-order index of 922 blocks, monotone in source
line, calibrated against four symbols identified by independent probes.

**Falsifies.** The undocumented but universally acted-on assumption that an
occurrence is a source reference. The consequence is operational: **a source
edit that moves a reference within a block changes the gross cost and leaves
the occurrence count untouched**, so any tooling that diffs occurrence counts
to identify a web is blind. Diff the gross. This is why occurrence probes
looked inert for two entire stages.

### L7. The save formula, exactly

```
gross = Σ_occ (uses + defs) × block_weight
      − LDSTCOST × block_weight per call-boundary reload
      − LDSTCOST × block_weight per second-pattern occurrence
n     = occurrences + bvectcard
div   = n < 3 ? n : ((n − 2) >> 2) + 2
save  = gross / div        (doubled for one dtype; that branch does not fire here)
class = (save > 0) ? 1 : 2        ← strict greater-than
```

Corollary, load-bearing: every gross term is non-negative, so **`save <= 0` is
reachable only through the two boundary charges**. Occurrence count and loop
depth can only push save *up*.

**Receipt — T1.** Instrumented at the verdict store, which is the only writer,
plus per-occurrence and per-decision records. ~840 oracle builds across six
sweeps, gated to a named hash. Measured distribution: 293 of 404 uncoloured
webs sit at exactly zero net — one unit of gross away from the strict `>`.

**Falsifies.** Two inherited claims: the divisor is the **compressed** count,
not the raw occurrence count; and the dtype doubling is a separate late step
that does not fire in this configuration. It also falsified **this workbench's
own field labels** — one trace command was printing an equation asserting an
arithmetic relation the records do not establish, and a `class=` field that was
a different classification entirely. Both fixed.

**Scope.** The doubling branch is read from source, not measured here.

### L8. An uncoloured web is a memory home, not a ring temp

An uncoloured uopt web is a **memory local with a stack home and a store**. It
is not a ugen ring temp. A third state exists and is what a target often uses:
neither coloured nor stack-homed, because it is not a web at all — it is an
anonymous ucode stack expression.

**Receipt — T1.** Forcing a named intermediate to the uncoloured class did
produce the target's operand order and the desired register — *and also emitted
a store to a stack slot*, taking raw differences from 1148 to 3940. The
upstream damage was not the colouring; it was the extra live web.

**Falsifies.** An entire residue question two stages had framed — "how does a
one-statement float local avoid uopt colouring?" — by showing the answer would
not reproduce the target even if obtained. Recorded as retired, not deferred.
This is the law that lets you *price* an answer before spending builds on it.

### L9. All du-chains of one variable merge into one web (the graft lever)

uopt merges every du-chain of one user variable into one web. So assigning an
expression to a **dead local** grafts the new chain onto that variable's web,
and the merged web usually keeps the donor's colour. Because decompiled names
encode the register the target used, this is a *directed* colour lever.

**Receipt — T1 mechanism, T2 adoptions.** The mechanism was proven by a probe
showing one web carrying two disjoint chains at two loop weights. Three
adoptions banked 21 rows total, each with zero collateral and an identical
frame. ~95 builds.

**Scope — heavily fenced.** Four rules, each earned:

1. The donor must be an **existing** local. A new declaration shifts the frame
   and costs roughly 500 constant rows (see [L14](#l14-a-new-declaration-costs-the-frame)).
2. The donor's other du-chains must be dead, disjoint, and non-loop. A
   loop-weighted donor drags the merged web up the decision order.
3. The name must encode the register you want kept.
4. One graft per web, verified by census.

Known failure classes: grafts onto a heavy global's CSE web are always
catastrophic; **no fp local carries a ring-register name, so this lever cannot
recolour ring temps at all**; and webs are keyed on ranges rather than symbols,
which bounds how much of "one variable" is really the key.

### L10. Dead-def grafts die before web founding

Dead-def grafts of **any** shape — split definition or full redefinition — are
eliminated before founding and collapse to the same object. Only occurrences
that survive to founding can flip claim order. Use-side reorderings inside
conditions are cfe-folded.

**Receipt — T2, hash-exact.** A full early redefinition killed by an identical
later definition compiles to **byte-identically the same object** as a
structurally different split-definition graft. Byte identity of two different
constructs is the proof of a common absorption point.

**Falsifies.** The narrower rule from the previous stage, which had qualified
this as holding only when a compound redefinition follows. The qualifier was
removed. It also scoped out an earlier hypothesis about what governs founding.

**Scope.** Dead-def constructs only, and explicitly **not** an impossibility
claim about founding order: a *live* occurrence did flip founding and banked 13
rows. Web founding itself is live-ucode first-occurrence order, computed
**after** dead-code deletion — which is the reason this law holds.

### L20. A copy-lever's temp NAME is inert; only site and count matter

Once a grafting site and a member count are fixed (see
[L9](#l9-all-du-chains-of-one-variable-merge-into-one-web-the-graft-lever)),
which *name* fills each slot does not change the object at all — not the
score, not the register file, not the frame.

**Receipt — T2, exhaustive.** 40 distinct ordered triples of dead `f32` locals
at one three-statement copy site, drawn from a 14-name pool, all compiled to
`ni = 4641`, all four positional coordinates identical, and the identical
positional word count. The rows the copy occupies were charged by the site,
not by any property of the 40 spellings tried there.

**Falsifies.** The implicit assumption behind every "try another temp name"
sweep at an already-identified site: that spelling is a free variable worth
searching. It is not, once the site and count are fixed — a tool or a reader
should stop respelling and start asking why the *site* charges what it does.

**Scope.** Copy-lever grafts specifically. A name still matters for the
*register* a graft inherits when donor identity changes (L9's directed-lever
mechanism) — this law is about respelling **within** one already-chosen
donor/site combination, not about choosing a different donor.

### L21. A mint requires an unwebbed memory load feeding an operation directly

Every construct observed to mint an interfering coloured web shares one shape:
an **unwebbed** memory load (a struct field, not an existing local) that feeds
an operation — a comparison, an arithmetic op — **directly**, with no
intervening assignment to a webbed local. A load that lands in an existing web
first, or a load whose result is only ever stored, does not mint.

**Receipt — T2, unifying.** Established by elimination: three independently
discovered minters (a struct-field copy pair, a struct-field comparison hoist,
and an address pun) all fit the shape, and a large window of otherwise-plausible
candidate sites (nine source lines, dozens of respellings) were all inert
*because* each already routes its load through an existing web before use. The
inert results are explained by the same rule that explains the three positive
ones.

**Scope.** Necessary in every case observed; not proven sufficient in
general — see [L22](#l22-a-mint-also-requires-an-address-exposed-frame-slot),
which found a load meeting this shape that still did not mint until a second
condition was met.

### L22. A mint also requires an address-exposed frame slot

An unwebbed load feeding an operation directly (L21) mints an interfering web
**only when uopt cannot register-promote it** — and register promotion is
refused specifically when the value's stack slot is **address-exposed**
elsewhere in the function (something in the source takes its address, even
indirectly through a pun). The carrier that round-trips through that slot —
whichever declaration happens to occupy it — is what mints, not the
expression or the variable name used to reach it.

**Receipt — T2, positional, exhaustive.** A 186-position sweep transposing
which `f32` declaration occupies each frame slot found that only two adjacent
positions mint, and *whichever* declaration sits at the minting position
reproduces the same object **byte-for-byte**; moved off that position, the
same declaration is byte-identical to the base with no mint at all. The mint
follows the slot, independent of which source name or expression fills it.

**Falsifies.** The previous stage's narrower reading — "extending a live range
across a boundary mints an interfering web" — which was true of its one
example but named the wrong necessary condition: the mechanism is address
exposure of the slot the value round-trips through, not liveness extension by
itself. It also falsifies a claim from the stage before that: that a repeated
carrier at the same site is CSE'd into a single instance and so cannot mint
independently. Two independently-declared carriers at the delta-saturated
class (see [L25](#l25-a-delta-saturated-site-scores-identically-under-further-generators))
compose exactly by the group law and produce **different objects with the
same delta and the same instruction count** — proof that the delta is a
property of the *site*, not of which carrier occupies it.

**Scope.** One procedure, one address-exposing pun (`&sp498 - 8`-style). Not
tested against a function with no address-exposed locals at all, where this
mechanism may not be reachable.

---

## ugen (the code generator)

### L11. ugen frees a binary op's sources in operand order

ugen's binary-operand handler frees the first operand's register, then the
second's. Release order equals operand order — never the temp ID at the site.

**Receipt — T1**, established twice independently: first from traces (874
identical events, with the first divergence in the free list's *tail* order),
then read directly from the pass source with both free calls located.

**Falsifies.** The working temp-ID-order hypothesis for release order, which
had been queued as the next front. Killing it at the site relocated the
question upstream to temp-ID renumbering, merging two problems that had been
worked separately.

This is the consumption half of [L1](#l1-free-order-is-cfes-operand-order).

### L12. The temp ring is least-recently-freed

Two singly-linked FIFO lists per register class. Allocation pops the **head**
of the free list, spilling the in-use head if the free list is empty; freeing
appends to the **tail**.

> Therefore allocation is a least-recently-freed round robin. The register
> chosen for the *n*-th temp is a pure function of the allocate/free event
> sequence that preceded it — nothing else. There is no liveness heuristic, no
> preference, no ucode-temp-index mapping.

**Receipt — T1**, source plus gated instrument plus an oracle sweep, including
a prediction-then-test: one instruction's register was explained from first
principles (two prologue folds burn ring slots without emitting anything), then
confirmed by rotating the initial free list and walking that instruction
through the ring exactly one step per rotation.

**Falsified in turn — by itself, immediately.** The rotation that matched the
predicted instruction made the overall score *worse*. **The residue is
therefore not a ring phase.** Phase was worth 84 of 845 rows, and no choice of
initial free-list state can close the band. That negative retargeted the whole
campaign onto **class-crossing sites** — where one side leaves as a ugen temp
what the other coloured — and took the residual from 1416 to 572.

**Scope.** Per procedure: the register state is re-initialized once per
procedure and does not carry across, which is why levers placed in preceding
procedures were inert. List sizes are driver startup constants.

### L13. The fp ring is four wide: `f4 f6 f8 f10`

The initializer lists six registers, but two are withdrawn before the first
allocation and never handed out: **1460 of 1460** allocations were from the
four. The withdrawn pair are uopt colours.

**Rule filed with it: assert the ring width, do not derive it from the
initializer.**

**Receipt — T1, exhaustive**, from an instrumented trace, cross-checked against
an independent uopt colour listing and re-confirmed twice in later stages.

**Falsifies.** The earlier stage's own write-up, which reported the initializer
and called it "the independent confirmation" of the ring. Reading it literally
cost ~15 builds and one wrong adoption path, because widening the set makes a
tool report **phantom closures** — a move onto a uopt colour looks like a fix
and is not. It also falsified this workbench's prose, which had called the
withdrawn pair "genuinely ambiguous" and said the float free list "extends onto
them under pressure". Corrected; regression tests now lock the four-wide ring.

**Scope.** The *effective* ring for this driver's defaults. The withdrawal is
uopt's and is per-procedure.

### L23. Two independent copies take the ring colour their SOURCE ORDER sets

When two field-copy statements are independent of each other (neither reads
what the other writes) and both land on ring-temp candidates, **transposing
their source order** transposes which one gets which ring colour — with no
other effect: the instruction count, the frame, and every other positional
coordinate stay identical. This is the first lever found in the campaign that
repairs a ring-colour mismatch without minting a new record at all.

**Receipt — T2, swept.** 44 adjacent simple-assignment pairs in the procedure
were tried as the transposition; exactly one location produced the swap
(closing four rows of a residual byte-for-byte); nine more were score-neutral
but changed the object (a different, untested swap), and the remainder did
nothing. `ni` and frame were unchanged in every one of the 44.

**Scope.** Two source-adjacent, mutually-independent copy statements whose
values are both ring-temp (not uopt-web) candidates. Does not apply once
either side is coloured by uopt (see
[L8](#l8-an-uncoloured-web-is-a-memory-home-not-a-ring-temp)) — this is a
purely ugen-side reordering.

### L14. A new declaration costs the frame

Introducing a new local shifts the frame and costs on the order of 500 constant
rows. Never introduce one; graft onto an existing dead local instead.

**Receipt — T2, repeatedly**, across at least three independent stages that
each rediscovered it. Operationally this is the single most load-bearing rule
on this page.

### L15. There is no strength reduction in IDO 5.3 uopt

**Receipt — T2**, ten scoped probes. Consequence: a target pattern requiring an
unnamed loop-carried web cannot be minted from source, because there is no pass
to mint it. Stated as measured-absent in this translation unit, not
proven-absent in the pass.

### L16. Register claims are advisory

Forcing a claim to a different register produces a **byte-identical object**
for non-ring registers: the force fires, the logs obey, and the emitted colour
binds upstream regardless.

**Receipt — T1**, confirmed in two separate stages with two instruments.

**Falsifies.** A named force point from an earlier stage, which is now closed
as a lever and kept only as a log. This is the law that makes
[L2](#l2-claim-order-is-source-condition-order-test-order-is-canonicalized)
— source condition order — the only route to those rows.

### L17. ugen runs two fp allocation passes

The early allocation ordinals are **not** emission-ordered; the later ones are.
A knob indexed by allocation ordinal therefore looks structureless until the
boundary between the two passes is found.

**Receipt — T1**, by binary search for the boundary. This is the arithmetic an
earlier entry had declared could not be written.

---

## Measurement laws

### L18. Positional words are the honest metric

Rank candidates on **positional word differences after masking
linker-controlled fields**. Row-based census metrics inflate in repetitive
regions: a change measured as +5 to +8 rows was +1 positional word, every time.

**Receipt — T1-adjacent**, from an instrumented diff of a swap family where
every swap was exactly +1 positional.

**Falsifies.** More than one "compiler finding" on this page's history that
turned out to be a metric artifact rather than compiler behaviour — most
notably a claimed global schedule reordering that was the aligner destabilizing
over eight near-identical statements. One stage built a 257-build lever table
ordered by the wrong metric.

`decomp-workbench score TARGET.o CANDIDATE.o` prints this number as its
headline and says when the others disagree.

### L19. Partial closure is not monotone

Closing part of a set of class-crossing sites can make the score *worse* on
the way to making it much better. Score on the site count, not on words, until
the set is fully closed; confirm on words only at full closure.

**Receipt — T2.** A recorded run went 1416 → 1413 → 1445 → 1477 → **572** as
sites closed one at a time. Each intermediate regression was a real object,
not a measurement artifact: closing one crossing re-phases everything
downstream of it, and the phase only settles when its partner closes too.

**Falsifies.** The tacit assumption behind every greedy sweep — that a lever
which raises the score is a lever to discard. Under this law a rising score is
evidence about the *set*, not about the lever.

### L24. Instruction count under composition is not additive

Composing two constructs whose individually-measured `ni` deltas are `+a` and
`-a` does not reliably produce `ni + 0`. Screening candidate compositions by
their summed instruction-count delta, instead of building each one, is invalid.

**Receipt — T2, exhaustive within one window.** Sixteen zero-sum ±`ni`
compositions were built (pairs and triples measured individually at `+1`/`-1`,
`+3`/`-3`, `+11`/`-8`/`-3`, and others) across one nine-site window. None
landed on the target instruction count; the results scattered across five
other values instead, including one three-way composition that summed to zero
individually-measured delta and still missed by eight.

**Scope.** One window, one procedure. Stated as a warning against a specific
screening shortcut, not a claim about why composition fails — the individual
mechanisms (frame shifts, whole-procedure renumbering, CSE across sites) are
each independently documented elsewhere on this page; this law is that their
*sum* is not the composition's effect.

### L25. A delta-saturated site scores identically under further generators

Once a source line's available *permutation deltas* have all been produced by
some generator at that site, additional generators at the same site — even
structurally different ones — reproduce a delta already seen, and several
reproduce the identical object byte-for-byte.

**Receipt — T2, hash-exact.** Of 38 companion solutions found for one target
delta, 30 land on two adjacent source lines and **all 30 score identically**;
six of the 30 are byte-identical objects, not merely equal-scoring ones. An
earlier stage's table of per-generator scores at those same two lines was
measured against a single plain generator and does not transfer to the
saturated set — every later generator there was always going to match it.

**Falsifies.** The implicit assumption that a table of per-site scores,
measured once, stays valid as new generators are tried at that site. Once a
site is known saturated, further search there answers "which spelling",
never "what score" — the score question is already closed.

**Scope.** Sites where multiple generators have already been found; a lever
found once. Whether a NEW site is saturated is not knowable in advance —
this law explains why several already-saturated sites stopped producing
information, not which untried site will turn out to be one.

---

## Claims a reader will find in older notes and should not believe

| Claim | Status | What killed it |
|---|---|---|
| The divergence unit is within-statement request order | superseded by [L1](#l1-free-order-is-cfes-operand-order) | request orders measured identical |
| ROM claim order is condition *use* order | corrected by [L2](#l2-claim-order-is-source-condition-order-test-order-is-canonicalized) | a pure condition swap moved claims and zero tests |
| An occurrence is a source reference | superseded by [L6](#l6-a-save-occurrence-is-a-basic-block-not-a-source-reference) | occurrence records read from the pass |
| The save divisor is the raw occurrence count | corrected by [L7](#l7-the-save-formula-exactly) | instrumented decision records |
| The fp ring is six wide | corrected by [L13](#l13-the-fp-ring-is-four-wide-f4-f6-f8-f10) | 1460/1460 allocations from four registers |
| A 15-row constant family is a second uopt temp population | corrected by [L4](#l4-cfe-owns-the-frame-layout) | the homes are already in the cfe intermediate |
| ugen has a second, uninstrumented fp allocation path | closed | the traffic is uopt-assigned colour, not allocation |
| ugen binds uopt temp ids to physical fp registers via whole-procedure state | retired | every promotion decision identical under the perturbation; the collateral was uopt's |
| A 13-row family is one named variable's webs | corrected twice | first to six CSE webs, then to **one** web |
| Split-def grafts cannot flip founding only when a compound redefinition follows | generalized by [L10](#l10-dead-def-grafts-die-before-web-founding) | two different graft shapes compile byte-identically |
| Three or more simultaneous swaps trip a global schedule reorder | never existed | the trip was the aligner; positional damage is exactly +1 word per swap |
| No single fp-ring perturbation improves on the base | was a **sampled** claim presented as an enumeration | one eighth of the space had been swept; the conclusion held on re-run, but the original statement was not entitled to be a proof |
| A named heavy float literal is the headline lever | refuted with an instruction count | the proposed spelling deletes three instructions the target contains |
| Row *N* is the gate for all float rows | retired | it is worth one commutative row |
| Extending a live range across a boundary is sufficient to explain a mint | refined by [L22](#l22-a-mint-also-requires-an-address-exposed-frame-slot) | a 186-position sweep showed the mint follows the frame slot, not the live range |
| A repeated dead-store carrier at one site is CSE'd, so a second one cannot mint independently | falsified by [L22](#l22-a-mint-also-requires-an-address-exposed-frame-slot) | two independent carriers composed to different objects with the same delta and the same instruction count |

---

## Using this page

```sh
decomp-workbench guide laws ido53
```

The field guide answers "what do I change". This page answers "what will the
compiler do about it". When they disagree, the guide is the one that gets
edited: a lever is a hypothesis about mechanism, and mechanism is measured
here.
