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

## p1 (the global-colour allocator)

Laws L26–L40 come from the GE007 `object_interaction` campaign (2026-08-08/09,
15 stages, 54 → 0 differing words), which spent most of its second half inside
`f_compute_save` and `f_split` — the same pass L6–L9 already described, read
here at the level of individual `uopt.c` line numbers rather than build
outcomes alone. Each entry below carries a **Provenance** line naming the
stage and that stage's own law label, because the campaign's parallel stages
independently reused numbers — two different stages each produced an "L84",
two each produced an "L60", and so on. The numbers below are this page's own,
assigned in the order the mechanism was nailed down; they do not match any
stage's internal numbering, and no stage's internal numbering is used
anywhere else on this page. [The p1 decision arithmetic](../p1-decision-arithmetic.md)
walks the whole formula end to end with a worked example; this section is the
per-fact reference it cites.

### L26. Webs are keyed on storage, not on the C name

uopt's web-formation keys on the **stack slot** (or register-equivalent
storage location) a value round-trips through, never on which C identifier
names it. A constant-offset address pun, a `struct` wrapper, and a `union`
member reaching the same storage all compile to the **same web** — and,
measured directly, the same object hash. **C cannot give one stack slot two
uopt symbols**, and the converse trap is just as real: a fresh declaration at
a *different* slot is a different web even when its value is provably
identical to an existing one (see [L14](#l14-a-new-declaration-costs-the-frame)).

**Receipt — T2, hash-exact.** Six differently-spelled reads of one slot
(plain access, struct wrapper, three union member spellings, a raw pointer
pun) all compiled to the identical object hash. A `f32 x[1]` respelling of
the same slot costs +4 rows and `volatile` costs +7 with 11 loads — neither
suppresses the web, because both still resolve to the same storage.

**Scope.** This is the fact [L39](#l39-copy-elimination-delete-the-redundant-copy-extend-the-temp)
and the fusion mechanism of
[L35](#l35-fusing-a-donor-imports-its-chargeb) both depend on: a "donor" or a
"copy elimination" is only free when the two spellings already share, or are
made to share, one piece of storage.

**Provenance:** stage `keyd`, originally L53.

### L27. The FP colour map, corrected

The IDO 5.3 floating-point colour-to-register map is `c24=$f0 c25=$f2
c26=$f12 c27=$f14 c28=$f16 c29=$f18`. `$f4`–`$f10` are never p1 colours at
all — see [L38](#l38-p1-never-colours-into-the-local-fp-ring) for what they
are instead.

**Receipt — T1, four independent object-level receipts** across four
separate forced-colour experiments, each reproducing a named hash.

**Falsifies.** An earlier reading in this same campaign (outside this page's
L40–93 source range) had asserted `c24=$f8 c25=$f10`, correct only from c26
upward, and had further concluded that landing a web naturally on c26
required first occupying c24/c25 — a plausible-sounding but wrong inference
that sent multiple stages hunting for an "occupancy" lever. What actually
keeps a web off c24/c25 is `f_cupcosts`' call-boundary charge (see
[L28](#l28-p1s-decision-is-net--bestcost-and-totalsave-is-net)), not colour
occupancy — a stage in this campaign's own line even read its own colour map
correctly for the *upper* two colours and still drew the wrong operational
conclusion from it, which is the reason this entry exists as a full law and
not a one-line erratum.

**Provenance:** stage `red`, originally L54.

### L28. p1's decision is `net <= bestcost`, and `totalsave` **is** `net`

The values a trace prints as `totalsave` and `net` are the identical number —
`totalsave = save × nocs`, and that product cancels back to `net` exactly,
in every record. p1's colouring/splitting decision is a single inequality,
`net <= bestcost`: true, the web is split (sent to `f_split`)
unconditionally; false, it stands and gets coloured. There is no third
outcome and no separate "decline" path reachable by any other route — a
brief that says "make p1 decline this web" means, arithmetically, "make
`bestcost >= totalsave` at the moment this web is decided," nothing else.

**Receipt — T1.** `f_globalcolor`, `uopt.c` **158777–158790**: `f6 = save *
nocs; cf = f6 <= f20 (bestcost); if (cf) f_split(...)`. Confirmed against
**1454/1454** `p1dec` records with zero discrepancies — every one satisfies
`totalsave == net` to the last decimal.

**Falsifies.** The folk reading that treated `nocs`/`bbcard` as levers on the
*decision* — "raise `bbcard` so the divisor steps and `save` halves" does
move `save`'s numeric value, but `nocs` cancels out of the product that
actually gates the decision, so that move changes the web's **rank** against
its neighbours and nothing about whether it splits. Also retires an earlier,
narrower reading in this campaign that treated "no decline" as an emergent
property of one specific web rather than the pass's actual control flow —
true in its conclusion, incomplete in its reason.

**Scope.** `f_needsplit`'s own spill path (a second route into memory
residency, gated on `regsleft == 0`) is reachable only from the
post-colouring neighbour loop, never from this decision. It is a different
mechanism and does not create a second way to "decline."

**Provenance:** stage `don`, originally L84 (disambiguated in this campaign's
own records as "L84-don" against `sev`'s unrelated L84,
[L32](#l32-web-fusion-by-rename-breaks-block-containment) below); the
weaker, single-web form of the same conclusion was first stated by stage
`keyb`, originally L40.

### L29. `nocs`, exactly — L7's divisor, sourced and floored

`nocs` is the same quantity [L7](#l7-the-save-formula-exactly) calls `div`:
`nocs = f(occ + bbcard)`, where `f(X) = X` for `X < 3` and `((X−2)>>2)+2`
otherwise, and `bbcard` is the cardinality of the web's live-block bitvector
(`web+0x0c`) — the count of basic blocks the web is **live into**, not the
count of blocks it is written or read in. `save = net / nocs`, doubled only
when `dtype == 12` (a branch this campaign never triggered: `dtype` was
always one of `{0, 6, 8, 13}` across 895 measured websurable). A direct
corollary: any web with two or more live-in blocks has `nocs >= 2`, so
**removing occurrences from such a web can only ever lower `save`**, never
raise it by shrinking the divisor.

**Receipt — T1.** `f_compute_save`, `uopt.c` **154631–154905**. Verified
against 893 `savedetail` records with zero discrepancies, and independently
against a second 895-record sweep for the `dtype` branch.

**Falsifies.** A same-campaign proposal to remove one web's rarest
occurrence on the theory that it would step `nocs` down and double `save` —
arithmetically, the occurrence in question belonged to a web already at
`nocs = 2`, the campaign-minimum for a multi-block web, and removing it left
`nocs` unchanged while lowering `gross`, making `save` worse, not better. The
step function has a floor, and reading it as freely reversible at any
occurrence is the trap.

**Provenance:** stage `redb`, originally L62 (`nocs` formula); stage `sev`,
originally L87 (the floor-of-2 corollary and its falsification of the
mis-applied reversal).

### L30. `chargeA`: the boundary charge, exactly

`chargeA` is `1.0 x block_weight`, summed over every occurrence whose basic
block has a predecessor **outside** the web's own block set (the `nl` — "not
local" — flag) and which is not exempted by `canmoverlod`. This is one of the
two boundary charges [L7](#l7-the-save-formula-exactly) already named without
decomposing. A web with **any** such occurrence has `net >= 1 > bestcost` for
every live-range shape that keeps the occurrence — it can never be declined
by shrinking or reshaping the web around it; the only way to change the
outcome is to remove the occurrence, or the web, before p1 sees it at all.

**Receipt — T1.** The `nl` flag is written in the occurrence builder, `uopt.c`
**150695–150745** (`nl = occ+21`). Cross-checked against KEY-D's earlier,
coarser statement of the same conclusion (chargeA = count of nl-flagged
occurrences), which this entry supersedes with the exact bit location and the
`block_weight` multiplier KEY-D's version omitted.

**Scope — the operational reading, quoted directly.** In this campaign's own
target web, one occurrence (`2.0f * x`, a doubled read in a single block)
contributed **two** uses in one boundary block by itself, which is why that
web's `net` floor was never reachable through source restructuring alone —
see [L35](#l35-fusing-a-donor-imports-its-chargeb) and
[L37](#l37-the-discarded-expression-lever) for the two constructs that
finally did remove it, neither of which is a "reshape."

**Provenance:** stage `keyd`, originally L55; refined with the exact
`uopt.c` location and multiplier by stage `redb`, originally L63; the
specific occurrence identified by stage `don`, originally L85 (disambiguated
as "L85-don" against `sev`'s unrelated L85,
[L32](#l32-web-fusion-by-rename-breaks-block-containment) below).

### L31. p1's colour-order tie-break: ascending web number

p1 visits webs sorted by `(−save, +web)` — highest save first, and **ties
broken by the lower web number**. A web can therefore out-rank a
higher-`save` neighbour it is exactly tied with, provided it was founded
earlier. Any threshold reasoned against a lower-numbered competing web is
`>=`, not the strict `>` a naive reading of the sort produces.

**Receipt — T1**, 486 decision records, 244 of them ties, zero violations of
the tie-break rule.

**Falsifies.** An earlier claim in this campaign that a specific pair of
webs was blocked by **strict** interference containment — "no interference
construct can free the contested colour, because any blocker of the smaller
web is by construction also a blocker of the larger one." The strict-`>`
premise behind that claim is one notch too strong; the actual tie-break gave
the lever this law's falsification history needed
(see [L32](#l32-web-fusion-by-rename-breaks-block-containment)).

**Provenance:** stage `sev`, originally L83.

### L32. Web fusion by rename breaks block containment

Renaming every reference of a local `V` to an existing local `W` merges `V`'s
occurrences into `W`'s web: `W`'s `occ`, `bbcard`, and `nocs` all rise, and
**`W` also imports every interference edge `V` had** — at zero instructions,
provided `V`'s and `W`'s live ranges were disjoint before the rename (uopt
[keys the merged web on the shared storage](#l26-webs-are-keyed-on-storage-not-on-the-c-name),
same mechanism as a graft, run in the opposite direction). This is the
construct that answers L31's "not strict" tie-break with an actual lever: a
block-containment relationship between two webs (one's forbidden-colour set a
subset of the other's) holds only while the smaller web's block set stays
what it is, and fusion changes that set.

**Receipt — T1.** One measured fusion took a web from `gross 12 -> 21`,
`nocs 2 -> 4`, and imported the donor's full interference mask, reproduced
byte-for-byte against a hand-derived prediction.

**Falsifies.** The "no interference construct can help" half of the claim
[L31](#l31-p1s-colour-order-tie-break-ascending-web-number) already
falsified the premise of. With the premise gone, the conclusion (block
containment as recorded is a fixed, unbreakable barrier) does not survive
either.

**Provenance:** stage `sev`, originally L84 (disambiguated as "L84-sev"
against `don`'s unrelated L84, [L28](#l28-p1s-decision-is-net--bestcost-and-totalsave-is-net)
above) and L85. The block-containment claim it falsifies was stage `zed`,
originally L79.

### L33. `numintf`/`f_isconstrained` was not the carve switch here

`f_isconstrained` (`numintf >= LIMIT[regclassof(sym)]`, `uopt.c`
**153891–153950**, `LIMIT` at `0x1001e5fc + 4*class`) gates one specific
allocator behaviour, but it was **not** the switch controlling this
campaign's contested carve: forcing `numintf` across its measured range
produced no flip, nor did forcing `forbidden0 = 0xff` / `bestcost = 60` /
`regsleft = 4` individually or in conjunction (ten forced-oracle builds).
The actual mechanism was the interference **structure** inside `f_split`'s
own region-growing loop, `uopt.c` **155990–156090**, which stops growing a
region at a block where `f_is_cup_affecting_regs` fires.

**Receipt — T1**, ten forced-oracle builds, all negative for the named
fields.

**Scope.** This is a scoped negative, not a claim that `f_isconstrained`
never matters — only that it was ruled out, by direct force, as the
mechanism for one named site. One switch inside `f_split`'s region-growing
loop remains formally undecoded: a byte read at `sp+127` gates whether the
loop consults `f_is_cup_affecting_regs` at all, is read six times in
`f_split`, and is written nowhere in it. The campaign that found this closed
its target through a different mechanism ([L37](#l37-the-discarded-expression-lever))
before needing to decode it.

**Provenance:** stage `don`, originally L86 (disambiguated as "L86-don"
against `sev`'s unrelated L86,
[L34](#l34-a-pure-call-with-a-frozen-argument-may-be-moved-across-an-equivalent-call)
below).

### L34. A pure call with a frozen argument may be moved across an equivalent call

If a function is pure and its argument value is already frozen (no
intervening write reaches it) between two call sites, the **value** the
first call computed is provably equal to what the second call would compute,
and either call's result may serve either use. Concretely: a call at source
line *A* and a second call to the same pure function with the same
now-frozen argument at line *B* mean the def normally attributed to *B* can
be handed to a **dead donor local** while the original symbol still carries
the correct value from *A* — because *A* dominates every read between the two
lines. This kills a web from source at zero added instructions whenever the
donor's forced store happens to land on the row the removed definition used
to occupy.

**Receipt — T2, one constructive instance, function-wide.** One campaign
target dropped 52 -> 39 positional words this way, `ni` unchanged, both
recompiles reproducing the object.

**Scope.** This is stated as a *general* decompilation lever, not specific to
its one discovered instance — the same campaign's own source has other
repeated calls to pure functions with arguments that become frozen between
call sites (`sqrtf`, `atan2f`), not swept here. A mechanical scan for
"repeated pure call, frozen argument between sites" is the natural next
instrument.

**Provenance:** stage `keyd`, originally L56.

### L35. Fusing a donor imports its chargeB

Renaming a **spilled** donor local's references onto a target symbol (the
same storage-keyed fusion as
[L32](#l32-web-fusion-by-rename-breaks-block-containment), applied to buy a
specific charge rather than to break containment) gives the target's web the
donor's `chargeB` contribution. Every split piece of the fused web then lands
at `net < 0`, i.e. class 2, and the whole symbol goes memory-resident with no
colour construct and no extra instructions under stock `cc`. The donor is not
optional: only a donor the ROM **itself** spills supplies a nonzero
`chargeB` (see [L36](#l36-chargeb-exactly-a-store-placement-term) for why),
so this family's price floor is fixed by the cheapest ROM-spilled donor
available — one measured campaign had donors at 2, 4, 6, and 7 rows, with no
zero-cost donor found across 290 tried fusions.

**Receipt — T1**, 290 fusion builds, oracle-verified against a forced-colour
target.

**Falsifies.** Nothing on this page; superseded in its *explanation* (not its
result) by [L36](#l36-chargeb-exactly-a-store-placement-term), which is the
direct read of the mechanism this entry originally attributed to "a
definition before a loop, with a use inside it." The floor this entry
establishes stands — it was simply not the cheapest route once L37 was
found.

**Provenance:** stage `don`, originally L89 (the kill mechanism, its causal
account since corrected) and L90 (the price floor, which stands).

### L36. `chargeB`, exactly: a store-placement term

`chargeB = Σ weight(bb(q))` over occurrences `q` satisfying `w34 ∧ ¬o23 ∧ o22
∧ (defs != 0 ∨ nl = 0)`, where `w34` = "the web has at least one occurrence
that is a definition," and `o22` = `¬f_allsucmember(successors, web+0x14)` —
the definition does **not** reach all of the block's successors. This is a
**store-placement** condition: it fires whenever a definition's value does
not provably reach every path out of its block, regardless of whether a loop
is anywhere nearby. A loop contributes only through `weight`, which is ×10
per loop-nesting level rather than the ×1 of straight-line code — the same
`block_weight` multiplier [L7](#l7-the-save-formula-exactly) already uses
throughout the save formula.

**Receipt — T1.** `uopt.c` **154761–154808** (the `chargeB` gate itself),
**149841–149851** and **153573–153615** (`w34`), **150947–151122** (`o22`).
Cross-checked against two independent kills: one where every contributing
weight was 10 (inside a loop), and a second, later one where every
contributing weight was 1 (no loop at all) — both fired `chargeB` correctly
by the formula above.

**Falsifies.** The immediately preceding reading in this same campaign,
which had attributed a successful kill to "a donor whose definition precedes
a loop and whose use is inside it" — a plausible story built from a single
positive example, where every contributing donor happened to be
loop-adjacent. Read from the pass source directly, the loop was never a
precondition: it was a coincidence of which donors happened to be available,
supplying only the weight multiplier, never the gate condition itself. The
donor-fusion **result**
([L35](#l35-fusing-a-donor-imports-its-chargeb)) is unaffected; only its
explanation was wrong.

**Provenance:** stage `omega`, originally L92, correcting stage `don`'s
originally L89.

### L37. The discarded-expression lever

A statement that reads a local and discards the value — `if (v);`, or a
value-guarded form like `if (v != 0.0f);` — compiles to **zero
instructions** and adds nothing to `gross`, but it still creates an
occurrence, and that occurrence is a **definition-adjacent read** that can
satisfy [L36](#l36-chargeb-exactly-a-store-placement-term)'s `o22`/`w34`
conditions on its own. Where the web already has a qualifying definition
elsewhere, adding this occurrence reshapes `f_split`'s region growth so every
resulting piece gains the exit edge `chargeB` needs, `net` drops below zero
for every piece, and the symbol goes memory-resident with **no donor, no
second stack home, and no instruction cost at all** — the cheapest possible
route to the outcome [L35](#l35-fusing-a-donor-imports-its-chargeb) reaches
by fusion.

Value-guarded spellings (`if (v != 0.0f);`, `if (v < 0.0f);`, `if ((s32) v);`)
are strictly better than the bare `if (v);`: the bare form can merge with a
neighbouring empty-body guard at the assembler and cost a real `bc1f`+`nop`
pair, which a value-guarded form does not.

**Receipt — T1.** This is the construct that closed a full campaign's last
residual words to zero. 3,930 candidate sources / 3,876 objects built to
find the one insertion point that scored 0 (305 of 999 tried insertion
positions scored 0 by themselves; the specific point chosen was the only one
provably assigned by every other constraint). The resulting object is
byte-identical to the ROM in all 4644 instructions.

**Falsifies.** Nothing directly, but it retires the assumption every
disassembly-only reconstruction makes implicitly: that every source
statement present in the original has a visible machine-code trace. See
[L48](#l48-zero-footprint-statements-can-be-load-bearing) for that lesson
stated on its own.

**Provenance:** stage `omega`, originally L91.

### L38. p1 never colours into the local FP ring

p1's colour set is exactly `{$f0, $f2, $f12, $f14, $f16, $f18, $f20}` — see
[L27](#l27-the-fp-colour-map-corrected). `$f4`, `$f6`, `$f8`, `$f10` are
[ugen's local scratch ring](../field-guide.md#the-allocation-law-ido-53-read-from-ugen-source-and-instrumented)
(see also [L13](#l13-the-fp-ring-is-four-wide-f4-f6-f8-f10)) and are **never**
a p1 colour, in either direction: p1 cannot claim them, and
nothing that lands in them was ever a coloured web. A direct consequence: a
minted web at a source site where the ROM has **no** web there costs at
least 2 rows (one for the definition, one for the use) — there is no route
to a zero-cost plant at such a site, because the register a plant would need
to reuse is never actually a colour. A zero-cost route at such a site is
therefore always evidence of a **missing temp in the decompiled C**, not a
free lever — see the campaign postmortem's
["split machine temp" and "missing local" error classes](../postmortem-2026-08-09-ge007.md).

**Receipt — T1**, consistent with L13's and L27's independent measurements
of the same ring.

**Provenance:** stage `b4u`, originally L75.

### L39. Copy-elimination: delete the redundant copy, extend the temp

When decompiled source computes a value into a compiler-visible temp `T` and
then copies it into a named symbol `S` (`T = expr; S = T;`), the register the
source is chasing is frequently **already on `T`** — deleting the copy and
extending `T`'s live range over `S`'s former uses reaches it directly,
because `S` never has to change colour: it simply stops existing over that
range. This heals a colour mismatch some campaigns spend many stages
searching for as if the fix had to move `S`'s own web.

**Receipt — T1**, one measured instance closing a full colour transposition
at zero instructions, byte-identical to the ROM at every coordinate.

**Falsifies.** Nothing named on this page, but it retroactively explains
several stages' worth of failed attempts, in the same campaign, to move `S`'s
colour directly against a block-level colour reservation — the reservation
was real ([L32](#l32-web-fusion-by-rename-breaks-block-containment)'s
containment relationship), and the lever was never on that side of the copy.

**Provenance:** stage `redb`, originally L60.

### L40. Routing through a third symbol is copy-propagated away

Introducing an intermediate named symbol purely to carry a value from one
expression to another (`T = <expr>; f(T, ...)`) does not create a new web or
a new occurrence when `T` is otherwise unused: uopt copy-propagates it away
before web-building, and the object is byte-identical to writing the
expression directly at the call site. **To change which web a value belongs
to, the edit must touch the symbol that already owns the value** — see
[L26](#l26-webs-are-keyed-on-storage-not-on-the-c-name).

**Receipt — T2**, 44 of 44 instances confirmed on one base, 4 of 4
re-confirmed on a second, independent base after an unrelated rebase.

**Provenance:** stage `eye`, originally L66.

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

### L41. The temp-ring phase is a seven-slot vector, not four coordinates

The ring's rotation state at any point in a function is fully described by a
vector of independent phase counters, one per structurally distinct region of
the function (seven were found in one campaign's target: four adjacent
"band" regions plus three finer sub-regions inside one of them), each valued
in `ℤ₄` (the ring is four wide — [L13](#l13-the-fp-ring-is-four-wide-f4-f6-f8-f10)).
Source edits move these coordinates **additively**: 87 of 87 tested
compositions of independently-measured edits predicted the resulting phase
vector exactly. A scorer that reduces this state to four whole-function
coordinates (or fewer) is not wrong about what it measures, but it is a
**lossy projection** — two regions can individually disagree with the target
while a coarse four-coordinate read reports them as identity, and a region
that is only one ring-step from correct can be hidden behind a region that
is already correct, because the coarse coordinate is an average, not a
per-region fact.

**Receipt — T2, exhaustive within one window.** 87/87 additive predictions
correct; the seven-slot model resolved a heal that the four-coordinate
model's owning campaign had failed to find for an entire prior stage.

**Falsifies.** A same-campaign claim, one stage earlier, that a specific
16-row window was "byte-exact if and only if" one whole-function phase
coordinate took a specific value — stated as a fixed, function-wide
relationship. It was not fixed: it was true only on the base it was measured
on, and broke on the very next base, because the real state has more degrees
of freedom than the coordinate the claim was stated against could see.

**Scope.** The slot count (seven) and their boundaries are specific to the
one function measured; the mechanism — additive per-region ring phase,
under-resolved by any coarser scorer — is the general claim.

**Provenance:** stage `b4s`, originally L64; falsifies stage `b4r`,
originally L60.

### L42. One copy temp is one ring step — unless the carrier repeats

Deleting or inserting one plain copy-through-a-temp statement (a
struct-to-local field copy with no other effect) steps every ring phase
coordinate downstream of it by exactly one ring position, and successive
steps at the same site compose multiplicatively (verified: two independently
measured deltas at the same site composed to exactly their product in the
ring's cyclic group). This holds **once per source line that supplies a
fresh occurrence** — but a single carrier symbol used as the copy target at
**two distinct source lines** steps the phase **twice**, because uopt treats
each line's occurrence as a separate web-formation event even though both
name the same symbol; only a genuine multi-statement chain collapsed onto
**one** line is coalesced into a single step.

**Receipt — T2.** Twenty scored objects, zero exceptions, for the
single-line case; a direct, deliberately-constructed counterexample (one
symbol, two lines) confirmed the double-step, `ni` and every positional
coordinate otherwise identical between the two readings.

**Falsifies.** An earlier, narrower statement in the same campaign that "a
multi-link chain at one source line steps the phase once, not once per
link" — true as stated, but read too broadly by the stage after it as "one
*symbol* steps once," which the two-line counterexample disproves. The
scoping variable is the source **line**, not the symbol.

**Provenance:** stage `b4r`, originally L59 and L62; corrected by stage
`b4t`, originally L73.

### L43. The phase vector is additive; the damage is not

While the ring-phase state itself composes additively across independent
source edits ([L41](#l41-the-temp-ring-phase-is-a-seven-slot-vector-not-four-coordinates)),
the **positional word cost** of reaching a given phase state is not: two
edits whose row-damage footprints overlap do not sum, and a search that
prunes candidate compositions by their summed damage (rather than building
each one) can miss the cheapest route. One measured pair of edits, individually
+33 and +31 rows, composed to +33 — not +64 — because their damaged rows
overlapped. A search capped at a fixed number of composed atoms on the
assumption that damage estimates transfer is a search capped on a false
premise.

**Receipt — T2**, direct build of the overlapping pair plus a wider sweep
that had been capped at three composed atoms on the additive-damage
assumption; the actual cheapest solution needed four.

**Scope.** This is the phase-mechanism analogue of
[L24](#l24-instruction-count-under-composition-is-not-additive): where L24
says instruction-count deltas do not sum under composition, this law says
the same about positional-word damage specifically inside one ring-phase
family, for the additive reason given above (row-set overlap), not for L24's
unrelated reasons (frame shifts, whole-procedure renumbering, CSE).

**Provenance:** stage `b4t`, originally L71.

### L44. A construct's delta class depends on the carrier, not only the site

At a fixed source site with a fixed construct shape, **which** local symbol
fills the carrier role can change the resulting phase delta's class, not
merely its cosmetic spelling. In one measured case, only the two
earliest-declared candidate locals at a site produced one delta class;
every other same-typed local available at that site produced a different,
more expensive one. A catalogue of "what this site's construct is worth"
that is keyed on the site alone, without recording which carrier was used
to measure it, silently under-resolves — later reuse of the cheap number
against a different carrier is not reproducible.

**Receipt — T2**, one site, one construct shape, full enumeration of the
available same-typed carrier pool.

**Falsifies.** A prior, differently-numbered law from an earlier stage of
the same campaign (outside this page's L26–48 source range, referenced here
only as "the delta belongs to the site") that had been carried forward
uncorrected through at least two later stages' work, including a census that
had thinned candidates on the strength of it.

**Provenance:** stage `b4s`, originally L65.

### L45. A fresh declaration's frame cost, reconfirmed

Independent reconfirmation of [L14](#l14-a-new-declaration-costs-the-frame)
on a second, unrelated campaign and a different function: introducing a
brand-new `f32` local (rather than recycling an existing dead one) shifted
the frame by 8 bytes and was unavailable as a carrier at an already
frame-saturated gate. The mechanism and the operational rule are identical
to L14; only the measured quantum differs (L14's host campaign measured
whole-function constant-row damage on the order of 500 rows for a different
function's frame; this campaign measured the frame-byte shift directly).
Both are the same fact — a new automatic variable is a new stack home — read
through different instruments.

**Receipt — T2**, direct frame-size comparison, one declaration added and
removed.

**Provenance:** stage `b4s`, originally L68.

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

### L46. Ring-quotiented scores are not positional scores

A band-vector score expressed relative to the ring's own rotation group (a
"free" count reported after quotienting out a global ring-coset shift) can
look like a large improvement while the actual positional-word score — the
one that matters, per [L18](#l18-positional-words-are-the-honest-metric) —
is far worse, because the whole object carries a hidden global coset shift
the ring-relative number cancels out. One recorded case reported as "worth
10" (an apparent close approach) was, measured positionally, **1045** words
off. A `free`/band number is only safely comparable to a baseline when the
object's ring-phase coordinates are independently confirmed identity; it is
never safe to read on its own.

**Receipt — T2, hash-exact.** The specific object behind the "worth 10"
claim, re-scored: bands **29**, `posdiff_nonreloc` **1045**.

**Falsifies.** The headline result of the stage that produced the "worth 10"
figure — not because the object was mis-built, but because the scorer used
to report it collapsed a ring-coset rotation into a number that reads like
positional progress and is not one.

**Provenance:** stage `redb`, originally L61; falsifies stage `red`,
originally L58/L59.

### L47. A lever's price is a property of the base — re-measure the whole set

An edit's cost is not an intrinsic property of the edit; it is a property of
the edit **against the object it is applied to**. The identical three-line
change was measured at +1015 positional rows against one base and, after an
unrelated fix changed that base's ring phase, was **free and −4** against
the next. More generally, a whole accumulated set of previously-adopted
levers can silently go from load-bearing to pure loss the moment the base
changes under it: one measured case found that four levers a prior stage had
each individually justified were, on the next base, jointly worth exactly
zero — their combined effect had already been supplied by an unrelated fix,
and all four were costing rows for no remaining benefit. The only way to see
this is a **removal experiment**: drop each inherited lever (and the full
power set of small combinations) and re-measure from zero, rather than
carrying a prior stage's pricing forward as fact.

**Receipt — T2.** The re-priced 3-line edit (comparison table across three
bases); the four-lever null-hypothesis sweep (128-point lattice, 128 builds,
the all-plain point uniquely minimal by 10 rows).

**Falsifies.** Every inherited "this costs N rows" figure a stage did not
personally re-derive on its own base. Neither instance was a measurement
error at the time it was taken — both were correct on the base they were
measured against — which is exactly what makes this trap easy to fall into
twice.

**Provenance:** stage `eye`, originally L67; independently rediscovered and
sharpened into the removal-experiment practice by stage `b4u`, originally
L74.

### L48. Zero-footprint statements can be load-bearing

Source can contain a statement that changes the compiler's allocation
decisions (see [L37](#l37-the-discarded-expression-lever)) while emitting no
instruction at all. A reconstruction built only from the disassembly —
however careful — cannot see such a statement, because there is nothing in
the object to reconstruct it from: eleven prior stages of one campaign,
working from disassembly and allocator mechanism alone, did not find it. It
was found by an oracle outside the disassembly entirely: a sibling game's
**independently matched** decompilation of the evolved version of the same
routine carried the identical discarded-expression idiom, in the identical
place, three times in fifteen lines. **When a function is byte-exact under a
forced allocator decision but not under the stock compiler, look for a
zero-footprint statement before looking for a mis-spelled one** — a forced
match that reproduces the target proves the allocation is reachable in
principle; the gap to a natural, unforced match is then a *missing*
construct, not a *wrong* one.

**Receipt — T1.** The closing match of a full campaign: a discarded-read
statement, zero instructions, that closed the campaign's residual to a
byte-exact ROM rebuild.

**Provenance:** stage `omega`, originally L93.

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
| The FP colour map is `c24=$f8 c25=$f10 …`, and a web lands on c26 by first occupying c24/c25 | corrected by [L27](#l27-the-fp-colour-map-corrected) | four independent forced-colour receipts; the actual barrier is `f_cupcosts`' call-boundary charge, not colour occupancy |
| A named web pair is blocked from recolouring because any blocker of the smaller is by construction a blocker of the larger (strict block containment) | corrected by [L31](#l31-p1s-colour-order-tie-break-ascending-web-number) and falsified by [L32](#l32-web-fusion-by-rename-breaks-block-containment) | the tie-break is `>=`, not `>`, and web fusion by rename changes the block set the containment claim was stated against |
| A source line's construct delta belongs to the site, independent of which local carries it | falsified by [L44](#l44-a-constructs-delta-class-depends-on-the-carrier-not-only-the-site) | only the two earliest-declared carriers at the site minted the cheap delta class; every other same-typed carrier minted a more expensive one |
| A ring-phase window is byte-exact iff one whole-function phase coordinate takes a fixed value | falsified by [L41](#l41-the-temp-ring-phase-is-a-seven-slot-vector-not-four-coordinates) | true only on the base it was measured on; the real state has more independent coordinates than the claim could see |
| A donor-fusion kill works because the donor's definition precedes a loop with a use inside it | corrected by [L36](#l36-chargeb-exactly-a-store-placement-term) | direct instrumentation of `chargeB` shows the gate is store-placement, not loop membership; the loop supplied only the weight multiplier |
| A re-deal is "worth 10 rows" (a band-relative improvement) | falsified by [L46](#l46-ring-quotiented-scores-are-not-positional-scores) | the same object scored positional 1045 once the ring-coset shift was accounted for |

---

## Using this page

```sh
decomp-workbench guide laws ido53
```

The field guide answers "what do I change". This page answers "what will the
compiler do about it". When they disagree, the guide is the one that gets
edited: a lever is a hypothesis about mechanism, and mechanism is measured
here.
