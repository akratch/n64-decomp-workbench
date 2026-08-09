# The allocator decision cascade

**Read this if:** you have a CDX log from an instrumented `uopt` and you want
to know what happened to one variable — every round, the colour it really got,
and which occurrence paid which charge.

Three commands read one input, a CDX log:

| Command | Question |
|---|---|
| `trace-cascade` | what happened at **one site**, in every round |
| `trace-order` | in what **order** p1 decided the webs, and which tie |
| `trace-blocks` | which webs occur in which **blocks**, and where the sets meet |

The arithmetic in the output is specified in
[the p1 decision arithmetic](p1-decision-arithmetic.md). This page is about
reading a log; that page is about what the numbers mean.

## What the commands need from your instrument

`trace-cascade --grammar` prints the record grammar, and marks each record
SHIPPED or CAMPAIGN-LOCAL:

- **SHIPPED** — `p1dec`, `p1color`, `p1cost`, `p1cand`, `webdetail`. These come
  from `decomp-workbench instrument-uopt`, which is
  [documented and hash-pinned](compiler-instrumentation.md).
- **CAMPAIGN-LOCAL** — `savedetail`, `saveocc`. These come from a `uopt.c`
  patch this project does **not** ship. The workbench owns the parsing,
  reporting, and planning layer over that output; the instrumented compiler
  stays with the campaign that patched it.

A log with the shipped records alone still gives you every round, the resolved
colour, and the kill signal. The save arithmetic — `gross`, `chargeA`,
`chargeB`, the occurrence table — needs the campaign-local records, and a
command that cannot find them says so by name instead of printing an empty
table.

## Locate the site by frame offset, never by symbol number

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --frame-offset 0xfffffdf8
```

```text
cascade: cascade.log site=frame offset 0xfffffdf8 (-520) sym=1039 webs=1039,3059
kill: NO cascade.log sym=1039 rounds=4 colors=1 final=w3059:c27/$f14
round 1 w1039 class=2(float) decision=split (trace decision #2)
net 8.000 <= bestcost 8.000 ? YES -> split (memory-resident, no colour)
save 0.421053 nocs 19 regsleft 5 numintf 28
natural c29/$f18 taken -
forbidden c24/$f0 c25/$f2 c26/$f12 c27/$f14 c28/$f16 c30 c31
min-cost tie c29/$f18
entering: gross 8.000 - chargeA 0.000 - chargeB 0.000 = net 8.000 over 1 occurrence(s), nocs 19
piece left memory-resident: w1039 net -1.000 (gross 1.000 chargeA 2.000 chargeB 0.000, 1 occ)
```

`webdetail`'s `raw10` is the web's frame offset, and it is the only identity in
the whole grammar that a rebase does not move. Web numbers and symbol numbers
are trace-local: adding a live range renumbers them. One campaign's `sym=1042`
became `sym=1039`, and the script that grepped the old number printed
`WEB-ABSENT` — which reads exactly like the kill the stage was hoping for.
Seven stages re-reported that one bug.

If you know the slot rather than the offset, give the frame with it:

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --slot 1184 --frame -1704
```

```text
cascade: cascade.log site=frame offset 0xfffffdf8 (-520) sym=1039 webs=1039,3059
```

`--symbol-id` and `--web` are accepted, and each prints a caution saying what
it is not stable against. An offset that matches nothing is an error that says
what it means, rather than an empty result that reads like a kill:

```
no web in build.ilog sits at frame offset 0xfffffd00 (-768). This is NOT a
kill: a killed web still has a webdetail record. It means the offset is
wrong, or the frame moved under you. Nearest offsets present: ...
```

## Every round, not the last one

A stuck site is usually not one decision. `f_split` carves a web that declines
on cost and asks again, and the record a naive `grep` finds — the last `p1dec`
for the symbol — is the *end* of that chain. Five stages of one campaign
reasoned about the final child in isolation, and one stage's brief was written
on the false premise that the parent range did not exist.

Three things on a round block are worth naming:

- **The decision is one inequality.** `totalsave` and `net` are the same number
  under two names ([L28](compiler-laws/ido-5.3.md#l28-p1s-decision-is-net--bestcost-and-totalsave-is-net));
  printing five loose fields makes the reader recombine them by hand.
- **`natural` is not `taken`.** `bestcolor` on `p1dec` is the pre-resolution
  field: on a `CDX_FORCE` run it shows the *unforced* colour, and on a split
  web it shows the parent's. The colour the web received is `p1color`, joined
  here by web number. When they differ the line says so.
- **Float colours are named.** The instrumented pass prints `bestreg=?` for
  every float colour, because its own decode table is the integer one. The map
  is `c24=$f0 c25=$f2 c26=$f12 c27=$f14 c28=$f16 c29=$f18`
  ([L27](compiler-laws/ido-5.3.md#l27-the-fp-colour-map-corrected)); `$f4`–`$f10`
  are ugen's scratch ring and are never a p1 colour. An earlier map in the same
  campaign had `c24=$f8 c25=$f10` and stood for four stages. Colours the
  profile has not confirmed to a register stay numeric (`c30`, `c31`) rather
  than being guessed.

## Which occurrence pays which charge

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --frame-offset 0xfffffdf8 --occurrences --headroom
```

```text
entering: gross 5.000 - chargeA 0.000 - chargeB 2.000 = net 3.000 over 2 occurrence(s), nocs 19
chargeB is a store-placement term (L92), paid by 1 occurrence(s): occ2@bb202x2
occ bb uses defs weight term nl o22 o23 w34 chargeB
2 202 0 1 2 1 0 1 0 1 PAYS
headroom: net must fall by 4.000 to reach bestcost 0.000. Only chargeA and chargeB can do it -- every term in gross is non-negative.
at nocs 2, removing occurrences lowers gross and therefore save (rank), and cannot raise it: the divisor floor is 2 (L29).
```

`chargeB` fires on `w34 AND NOT o23 AND o22 AND (defs != 0 OR nl = 0)`: a
definition whose value does not provably reach every successor block. It is
**not** a loop term — three stages theorised it as one and planned sweeps
around loops. The gate is checked against the pass's own recorded `chargeB`
before it is reported: where the derived weights do not reproduce the recorded
number, the command says so and reports the pass's number rather than a
derived attribution.

`--headroom` adds, for each coloured web, how far `net` has to fall to reach
`bestcost` — and the reminder that occurrence removal lowers `save` (rank) and
cannot raise it once `nocs` is at its floor of 2.

## The kill signal, as one column

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --frame-offset 0xfffffdf8 --kill
```

```text
kill: NO cascade.log sym=1039 rounds=4 colors=1 final=w3059:c27/$f14
```

The decisive bit at a contested site is whether the target web got a colour at
all. One campaign turned a 946-variant sweep into a single column with this;
every stage before it re-invented the same `grep -c` by hand.

## Two builds, one site

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --against examples/traces/cascade-killed.log --frame-offset 0xfffffdf8
```

```text
cascade diff: cascade.log -> cascade-killed.log site=frame offset 0xfffffdf8 (-520)
symbol 1039 -> 1035 (renumbered -- which is why the site is keyed by frame offset)
rounds 4 -> 4
kill: NO cascade.log sym=1039 rounds=4 colors=1 final=w3059:c27/$f14
kill: YES cascade-killed.log sym=1035 rounds=4 colors=0
VERDICT: the kill signal changed -- coloured in cascade.log, killed in cascade-killed.log
4 w3059:color:c27/$f14 w3055:split:- decision,taken,net
```

The two logs are the same function before and after one source edit. The
symbol renumbered between them, and the site is still one lookup.

## Was the barrier ever there?

`--rom OBJECT` reads a reference object and reports which float colours it
never uses. `--rom-rows LO..HI` narrows the reading to the row range you care
about, and `--dumps` reads retained `objdump -d -r` text instead of objects:

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --frame-offset 0xfffffdf8 --dumps --rom examples/fixtures/target.objdump --object examples/fixtures/target.objdump --slot 1184
```

```text
float colours the reference uses: c24/$f0 c26/$f12
float colours the reference never uses: c25/$f2 c27/$f14 c28/$f16 c29/$f18
round 4: cheapest-tie colours the reference never uses: c27/$f14 c28/$f16 c29/$f18
reading: occupancy over the named rows, not a liveness analysis: absence is proof the colour was free, presence is not proof it was taken
screen: sha=- ni=6 frame=-32 ld1184=0 st1184=0
```

One campaign spent four stages driving `forbidden0` towards `0xff` at a gate
whose free colours the reference's own rows never mention — meaning the
reference declined that web on **cost**, not colour, and the barrier being
attacked was not there. The reading is **occupancy**, not liveness: a register
that appears nowhere in the range cannot be live in it, which is the direction
this conclusion needs. A register that does appear may still be dead at any
particular point, and the command does not claim otherwise.

`--object OBJECT --slot N` adds the candidate's screen line, with loads and
stores counted apart. The store count is what separates "the donor took over
the reference's store" from "the donor added one"; screens that print only
`ld1184` show those two as the same object. (Reading retained dump text rather
than the object leaves `sha=-`: the digest of a dump is not the identity of an
object.)

## Colour order and ties

```sh
decomp-workbench trace-order examples/traces/cascade.log --class 2
```

```text
colour order: cascade.log 6 of 6 decision(s) class=2(float)
pos web sym save nocs net bestcost colour numintf decision
1 255 255 8.000000 3 24.000 0.000 c25/$f2 16 color
5 3059 1039 2.000000 2 4.000 0.000 c27/$f14 10 color
ties (p1 breaks these by ASCENDING web number, so a threshold against a lower-numbered web is >=, not > -- L31):
save=8.000000: pos1/w255, pos6/w260
```

`--class 2` is the float-web census: every float web in the object, in decision
order, in one pass. Positions are the true colouring positions, not positions
within the filtered view.

## Which webs share a block

```sh
decomp-workbench trace-blocks examples/traces/cascade.log --web 255 --web 3059
```

```text
web blocks: cascade.log 2 web(s)
w255 1 block(s): 900
w3059 1 block(s): 300
intersection: EMPTY -- these webs share no occurrence block, so neither can be blocking the other through a shared block.
```

"Which web interferes with which" was argued from `numintf` deltas across five
stages of one campaign. It is a set intersection over `saveocc bb=` values.
`--block BB` goes the other way: every web with an occurrence in that block.

## What this cannot tell you

- **Which source line an occurrence came from.** `saveocc`'s `bb=` is a pointer
  into the pass's own block table and `webdetail`'s `bb=` is a block ordinal;
  no field joins them. `webdetail`'s `line=` is constant across every record in
  the traces measured (262 records, all `line=23`), so it is not a source line
  either. Mapping an occurrence back to a statement needs an instrument change,
  not a reader change.
- **What `p2` did.** The commands read `p2dec`/`p2color` where present, but the
  campaign evidence behind every number here is phase one.
- **Whether a colour was legal.** `forbidden0` says what the pass ruled out at
  that moment; `min-cost tie` (the raw `available0`) is the set of colours tied
  for the *cheapest* measured cost, **not** the set still free. Those coincide
  only at the caller-save 0.0 tier.

## See also

- [The p1 decision arithmetic](p1-decision-arithmetic.md) — what the fields mean.
- [Compiler instrumentation](compiler-instrumentation.md) — building the
  instrumented pass, and the shipped record set.
- [Trace analysis](trace-analysis.md) — the other trace-reading commands.
