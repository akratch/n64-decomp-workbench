# Sweeps: generate a family, build it, read it back

**Read this if:** the next move is a search rather than a single edit — you
have a base, a site, and a family of things to try at it.

A sweep is three steps, and the workbench owns the first and the third:

```text
sweep <generator> ... --write DIR      emit variant sources + sweep.json
<your compile-one wrapper>             DIR/*.c -> OBJDIR/*.o
sweep ingest DIR --objects OBJDIR ...  gate, score, rank, report coverage
```

The middle step is yours. That is the same boundary
[`campaign`](campaigns.md) draws — the workbench does not run a project's
build system — and it is why a sweep directory is a plain directory of `.c`
files with a manifest beside them.

| Command | What it emits |
|---|---|
| `sweep regress` | the base unedited, then each accumulated construct removed |
| `sweep hoist` | one variant per (operand, carrier) at one statement |
| `sweep commute` | one variant per exchanged commutative operand pair |
| `sweep copies` | one variant per removable `Y = X;` copy |
| `sweep fuse` | one variant per donor fused into the target |
| `sweep carriers` | *(read-only)* the locals that are dead at a site |
| `sweep donors` | *(read-only)* the locals whose live range avoids a target's |

## `sweep regress` — the experiment nobody runs

Every stage inherits its predecessor's construction as "the base" and attacks
only the residue. The single highest-value experiment available at any point is
the opposite one: rebuild the base with each accumulated lever **removed**. One
campaign ran it once — twelve builds, ninety seconds — and found that a whole
four-atom supplier set was phase-neutral dead weight costing ten rows on the
live base. It had been carried for several stages because nobody re-tested an
inherited construction.

```sh
decomp-workbench sweep regress work.c \
  --construct 920..921=hoist \
  --construct 977=deadread \
  --write regress/
```

The first variant emitted is always the **control**: the base, unedited. A
price is a difference, and a difference needs both terms measured in the same
run by the same wrapper. A remembered score from an earlier session is exactly
what made this experiment skippable.

`--order N` adds the joint removals up to order *N*; the all-removed point is
always included whatever the order.

Every repeatable option in this family also has a `--OPTION-from FILE` form —
`--construct-from`, `--carrier-from`, `--donor-from`, `--line-from`,
`--frozen-from` — reading one value per line, ignoring blank lines and `#`
comments. Use it rather than building a list in a shell variable: `zsh` does
not word-split a parameter expansion, so an unquoted `$LEVERS` arrives as a
single argument and the run dies somewhere that looks like a tool bug. That
shape cost one campaign a stage.

After building, `sweep ingest` prints the price table:

```text
what each construct costs on the base as it stands now:
  L920-L921            removed: hoist          COSTS 10 row(s): removing it improves the base
  L977                 removed: deadread       EARNS 3 row(s): it is load-bearing
```

## The carrier is part of the experiment

At one line of one campaign, the carrier's **declaration index** selected
between two entirely different cost deltas: the compiler lays the frame out in
declaration order, so which dead local a hoist recycles is not an
implementation detail. Every sweep here is keyed by `(site, class, carrier)`,
and two variants that collide on that triple are a generator defect that stops
the run rather than overwriting each other.

Which locals may be recycled is its own question, and it was reimplemented by
hand five times in one campaign:

```sh
decomp-workbench sweep carriers examples/fixtures/sweep-base.c --at 16
```

```text
carrier pool: examples/fixtures/sweep-base.c at line 16
5 declared local(s); 2 dead here and therefore free

 idx  line  verdict    name                 type
 0    5     dead       lead                 f32
 2    7     dead       reach                f32
 1    6     live       span                 f32
        line 18 reads it before anything writes it, so recycling it here would change that read
```

A carrier is **an existing local that is dead at the site**. A fresh
declaration mints a new frame slot — 8 bytes for an `f32` on the compiler this
was measured on — and the frame gate rejects it, so the pool never proposes
one. An unused pad is worse still: it has no web to merge into and materializes
a stack home, where an already-declared symbol may hold the target's register
and cost nothing. That is why declared symbols are enumerated first and a pad
is never offered.

## `sweep hoist` — four classes, one of them new

```sh
decomp-workbench sweep hoist work.c --line 920 --class O,P --write hoists/
```

| Class | Shape |
|---|---|
| `H` | one side of the **top-level** binary expression |
| `O` | a leaf of a **nested** subexpression |
| `P` | `x op= y;` becomes `C = y; x op= C;` |
| `A` | `f(expr)` becomes `C = expr; f(C);` |

`O` is the one that matters and the one no generator library had. Splitting the
top-level operator of `a * (b + c)` can only reach `a` and `(b + c)`; hoisting
`c` out of the nested sum is a different edit with a different price, because a
deep hoist can leave the local ring rotation undisturbed where a shallow one
does not. `P` and `A` mint deltas nothing else does.

With no `--carrier`, every dead local at the line is used, so the family is the
full (operand × carrier) grid. Two classes that spell the same file pay for one
build: the duplicate is dropped by exact byte identity and the dropped row names
the variant it duplicates.

## `sweep commute` — the lever the classifier never had

`compare` names a commutative row and the edit that would fix it. This is the
sweep: exchange every commutative operand pair and build them all — roughly two
hundred builds and half a minute on one campaign's function, and worth fifteen
rows there.

```sh
decomp-workbench sweep commute work.c --write commute/
```

Only **textually pure** exchanges are emitted. Exchanging the two operands of
one operator preserves the value; reassociating does not, and floating-point
addition and multiplication are commutative but not associative. So `a + b * c`
offers `b * c` and refuses `a + b`, and a swap that would need new parentheses
to stay associative-safe is named in the refusal list rather than emitted with
the parentheses added — those parentheses would be a second, untested edit.

## `sweep copies` and `sweep fuse` — two locals, one web

`Y = X;` where `X`'s allocated register already matches the target at that row
and `Y`'s does not is mechanically detectable, and was worth nine rows in one
case and fifteen in another. `sweep copies` drops the copy and rehosts `Y`'s
later reads onto `X` — but only when the text proves it: `X` not written again
while `Y` is still read, `Y` not written again at all, neither address taken.
Everything else is refused with the line that refused it.

Fusion is the same idea one level up: the donor's declaration goes and its
occurrences read the target instead, so two webs become one and a stack slot is
reclaimed. Whether that is even possible is a live-range question with no build
in it:

```sh
decomp-workbench sweep donors examples/fixtures/sweep-base.c --target carry
```

```text
fusion donors for carry: examples/fixtures/sweep-base.c
1 of 4 local(s) have a live range that avoids the target's

 idx  live      name                 verdict
 0    11..12    lead                 FUSABLE
        dies at line 12, before the target lives at 15
 1    12..18    span                 no
        live 12..18 overlaps the target's 15..20
```

That is one half of the donor table. The other half — how many rows touch the
donor's stack slot, which *is* its price — is [`slots`](source-probes.md#slots--what-a-donor-costs-without-a-build).

## Every edit states its base and respects a frozen zone

Composers that assert the content of a few lines and nothing else silently
mis-edit a file that has been rebased, and produce a plausible, wrong candidate
that has to be un-believed later. One campaign lost a stage to it.

So every generator here composes through one implementation that refuses, in
this order:

* **the base moved** — the file's SHA-256 is not the one the plan was written
  against, so no line number in the plan means what it meant;
* **an anchor moved** — the line is there but does not say what was expected;
* **the edit is inside a frozen zone** — `--frozen 900..940` marks another
  stage's protected lines, and a composer that quietly edits them is how two
  constructions get silently merged.

Anchors are re-read **at their own line** after composing, through the line map
the edits produced. The strongest campaign composer searched the whole emitted
file for its anchor text, which a coincidental duplicate elsewhere satisfies.

## `sweep ingest` — the gate, the score, the coverage

```sh
decomp-workbench sweep ingest examples/fixtures/sweep-ingest --objects examples/fixtures/sweep-ingest/objects --target examples/fixtures/shifted-insertion-target.objdump --dumps --target-dumps --object-suffix .objdump
```

```text
control (the base, unedited): rows_away=1  screen: sha=- ni=15 frame=-24 ld=0 st=0 coset=?

 rows  price  ni    frame  coset  class site                 carrier
    0     +1  14    -24    ?      N     L14                  -
```

Each row carries the gate line the campaign's stages kept re-deriving — object
sha, true instruction count, frame size, load and store counts (at one slot with
`--slot`), and the ring coset — beside the shift-tolerant distance from the
target. **A wrong instruction count is a column, never a rejection.** Position-
indexed scoring turns one inserted instruction into a four-figure mismatch, and
eleven stages of one campaign abandoned candidates that were one row away.

Nothing is dropped quietly. A variant whose object is missing is a row naming
the path that was looked for; a variant the generator refused is a row with its
reason; and the last line is the coverage sentence, which says whether a
negative result from this family is a proof about the space or evidence about a
sample.

## Reviewing a winner

A generator proposes edits by shape, not by meaning. Before adopting one:

```sh
decomp-workbench experiment review-mutation base.c winner.c
```

It flags a use that no earlier line writes to and a removed write to a value
still read. It is a review surface, not a proof — read the diff.

## See also

- [Candidate campaigns](campaigns.md) — the compile-and-rank half, and the
  compile-one wrapper contract this shares.
- [Source probes](source-probes.md) — the two source questions worth asking
  before a sweep: same-value ranges, and zero-footprint constructs.
- [The p1 decision arithmetic](p1-decision-arithmetic.md) — why an occurrence
  with no instruction cost still moves the decision.
- [Metric traps](metric-traps.md) — including the coset trap the ingest gate
  line exists to catch.
