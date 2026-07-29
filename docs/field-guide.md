# Field guide: IDO codegen levers

**The diff looks like X. Here is the C that moves it.**

This is the manual path. No permuter, no agent, no trace — just the mechanisms
that were found by matching real functions, written down so you can apply them
by hand. [Start here](START_HERE.md) explains the loop these fit into; this page
is what you consult once `view` has named a mechanism.

Every lever below was proven on a real IDO 5.3 `-O2 -g3 -mips2` function, and
the measured effect is quoted so you can calibrate how much to believe it. The
C snippets are illustrative shapes, not copy-paste patches: the *form* is the
lever, the identifiers are yours.

**Read the order as priority.** Levers 1-4 cost one variant each and can erase
a hundred words. Do not touch the register sections until the instruction count
and opcode schedule have stopped moving.

- [Cheap first — one variant each](#cheap-first--one-variant-each)
- [Working a structure mismatch](#working-a-structure-mismatch)
- [The coloring pool (uopt)](#the-coloring-pool-uopt)
- [The temp-FIFO lane (ugen)](#the-temp-fifo-lane-ugen)
- [Coalescing copies](#coalescing-copies)
- [When source search is over](#when-source-search-is-over)
- [Dead families — do not spend variants here](#dead-families--do-not-spend-variants-here)

---

## Cheap first — one variant each

### 1. Wrong constant masquerading as structure

**Diff looks like:** a large `structure-mismatch` whose *earliest* hunk begins
at a constant materialization — `lui`, `li`, `andi`, `ori`, `slti`.

```c
/* before */  if (flags & RENDER_UNK10) { ... }   /* 0x10 */
/* after  */  if (flags & RENDER_DECAL) { ... }   /* 0x00100000 */
```

**Why:** the assembly encodes the truth about the constant, and everything
downstream of a wrong branch predicate is a consequence, not an independent
problem. One wrong enum identifier produced 183 "structural" words in
`blockSetupVertices`; correcting it left 21.

**Then re-derive every fake.** Padding and dead reads that were fitted to the
wrong body are now wrong too — in that same function a stale `if ((s32)x) {}`
pad had been compensating for the bad constant's register pressure, and the
frame and register counts only snapped exact once it was removed.

**Points here:** `verdict=constant-mismatch`, `playbook=constant-audit`, and any
structure verdict whose first hunk starts at an immediate.

### 2. Commutative operand order

**Diff looks like:** `verdict=commutative-order`, or a handful of `or`/`and`/
`xor`/`addu` sites with the same two operands in swapped positions.

```c
/* neither of these moves anything - they canonicalize identically */
x = a | b;
x = b | a;

/* this is a different AST, and it flips the emitted operand order */
x |= b;
```

**Why:** operand order on a commutative op is front-end expression shape, not
allocation. IDO 5.3 canonicalizes source-level swaps of a plain binary
expression to byte-identical objects, but compound assignment is a distinct
tree and emits the other order. Proven on `texDPTextureSimple`.

**Points here:** `verdict=commutative-order`, `playbook=ast-shape`. Do not
capture an allocator trace for this class — the allocator is not involved.

### 3. The `-g0` diagnostic

**Diff looks like:** the same instruction multiset in a different order, or
"the target hoists further than my candidate". `verdict=schedule-mismatch`, or a
`view` verdict of `schedule`.

```sh
# rebuild the same candidate with -g0 instead of -g3, then compare again
```

**Why:** IDO emits a `.loc` per statement under `-g3`, and as1 restricts
cross-block motion at those barriers. If the divergent region collapses to
near-exact under `-g0`, **your C is correct** and the residual is debug-info
scheduling — source search is over for that region. On `vsprintf`'s float paths
this took 25 words to 2, replacing roughly 550 blind variants with one command.

**The negative result is equally load-bearing.** If `-g0` does *not* collapse
the region, the residual is not `.loc` scheduling and you have exonerated a
whole hypothesis for one compile. Line joins and comma merges cannot remove the
barriers, because `.loc` is per statement — do not bother trying.

**Points here:** `verdict=schedule-mismatch`, `playbook=g0-schedule-probe`.

### 4. Flag parity and context parity

**Diff looks like:** a large structural residual on source you have reason to
believe is right — a ported scratch, a function that matched elsewhere.

**Why:** the same source under the same nominal flags produces different code
in a different translation unit context, and a single missing assembler flag
produces differences that read as structural. A decomp.me preset missing
`-Wab,-r4300_mul` produced roughly 78 "structural" words on already-ROM-verified
source. Type differences reaching the optimizer from a different `ctx.c` shift
schedule and branch-likely selection on their own.

**Do this before any source search on a ported function:** diff your flag line
against the project's real build rules, and compare against the full-TU build
rather than a harness. See [Minute 1 of Start here](START_HERE.md#minute-1--do-i-need-to-isolate-the-function-first).

---

## Working a structure mismatch

Bucket the hunks by size and fix the largest first, against whatever ground
truth you have about the function's lineage. Above roughly 500 instructions,
align, bucket by region, settle structure region by region, and only then run
the register playbook per remaining bucket. Hold every allocator experiment
until the instruction count and the opcode schedule are stable — a register
lever applied to a function with the wrong shape tells you nothing.

Two structure-class traps have their own levers.

### 5. Don't fight the auto-hoist

**Diff looks like:** `+1` instruction and `+8` frame around a loop that
contains a call; the target re-reads memory each iteration where your candidate
caches the value in a register and spills it around the call.

```c
/* do NOT do this to force the re-read */
for (i = 0; i < n; i++) { ... }        /* split into two loops, */
for (; i < m; i++) { ... }             /* or duplicate the body */
```

**Why:** IDO performs its own loop-invariant motion, and restructuring the
control flow to force a particular memory behavior defeats it rather than
steering it. Loop splitting cost +147 words on `blockComputeVertexColors`
against a candidate that was already close.

**The lever, if one exists, is register pressure near the call — not control
flow.** Revert any structural change that raises the word count sharply instead
of pushing through it.

### 6. The spill-slot census

**Diff looks like:** a consistent `+N` frame delta together with a *uniformly
shifted* tail of stack offsets.

**Why:** that signature is one extra (or one missing) spill slot, and every
shifted offset below it is the same fact restated. Census the stack offsets on
both sides, find the single value that gained a home, and work on that value's
liveness. Chasing the shifted offsets individually is chasing one problem N
times.

`compare --json` carries `candidate_stack_offsets` and both frame sizes for
exactly this census.

---

## The coloring pool (uopt)

The pool is `v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5`, and uopt colors variable
webs into it, lowest free index first. `view`'s **pool lane** is the sequence of
assignments in emission order. A pool-lane divergence means a web took a
different slot, which almost always means the *set* or the *priority* of webs
differs — not that one register was picked wrongly.

Three things move a pool assignment: adding a web, removing a web, and changing
a web's priority. That is the whole surface.

### 7. Dead-web positioning

**Diff looks like:** the pool lane diverges at slot *k*; your carrier is one
register too low.

```c
/* zero instructions emitted; creates a web that takes the next free pool slot */
if (gSomeGlobal) {}
```

**Why:** a duplicated read inside an if-condition with an empty body survives
dead-code elimination as a code-free web, and that web occupies the next free
pool slot, marching every later web one position down the order. Two such reads
put the carrier in `$a3` on `rarezipUncompress`, which matched the function.

**The boundary matters:** a dead web takes the *next free* slot. It cannot
reach past a live web to free a specific register. On `objprint`, dead reads of
whole locals and globals always landed in `v1` and could never occupy `v0` — see
lever 9 for the construct that can.

**Points here:** `playbook=pool-position`, a pool-lane divergence in `view`.

### 8. Expression dead reads

**Diff looks like:** as lever 7, but the plain `if (var) {}` form is inert,
lands in the wrong slot, or the value you need a web for is not a named local.

```c
if (gFile_TEX_TAB[tab]) {}            /* an array-index rvalue */
if ((tab * 4) + tabEntry + tabEntry) {}   /* an arithmetic rvalue */
```

**Why:** the zero-code dead read generalizes from locals and globals to
arbitrary rvalue expressions, and the expression form gives you control over
*which* value gets a web rather than only over how many webs exist. The second
form above, plus a parameter mask, is what matched `texLoadTextureActual`; the
first was the only thing that beat a stubborn `lui` hoist.

**And it lifts the `v0` boundary:** the "dead reads take `v1`, never `v0`" rule
applies to whole locals and globals. Reads of *intermediate values* do take
`v0`.

### 9. The read-count priority dial

**Diff looks like:** two webs compete for the same slot and the wrong one wins;
you can form the web you want, but it colors second.

```c
if (gFile_TEX_TAB[tab]) {}
if (gFile_TEX_TAB[tab]) {}    /* stack a second read of the losing web */
```

**Why:** uopt orders webs by accumulated benefit, so read count is a
continuous priority control rather than an on/off switch, and stacking reads of
the losing web until it outranks the winner is **monotone** — you can turn the
dial rather than search. On `texLoadTextureActual`, one read left 5 words and
two reads left zero.

**Practical note:** this is the cheapest possible campaign — a one-dimensional
sweep of *n* reads at one site, not a permutation search.

### 10. The chain-split dead read

**Diff looks like:** you need a short-lived web in `v0`, but the value is a
local whose update chain is one continuous assignment, and every dead read you
add takes `v1`.

```c
/* before */  x += a;
/* after  */  x += a; if (!x); x++;
```

**Why:** splitting a local's own update chain with a dead read forms a short
web *from the intermediate value*, and intermediate-value webs can take `v0`
where whole-local reads cannot. It costs zero instructions and zero frame, and
it does not consume a coalescing copy the way an assignment RHS would.

On `objprint` this was the first construct in roughly 2,800 variants to color
the count web correctly with no forced color at all. Note the trailing
semicolon: `if (!x);` — an empty *statement*, which is what keeps it free.

**Its cost:** the dead read is a branch in the ucode and pins the chain above
whatever guard follows, so it can convert an allocation residual into a
schedule residual. That is usually progress; check with `view` rather than
assuming.

### 11. Pool-vs-temp routing

**Diff looks like:** a value that appears in the *pool* lane on one side and
the *temp* lane on the other; often the entire residual.

```c
/* pool: a named local whose live range spans the loop */
s32 end = base + count;
for (...) { ... use(end); ... }

/* temp: the same expression inlined at the use site */
for (...) { ... use(base + count); ... }
```

**Why:** promoting a value to a named local that spans a loop makes uopt form a
colored web for it; inlining the expression leaves it in ugen's block-local temp
rotation. Which side of that divide a value sits on decides which lane it
appears in, and no color force can move it across. Proven both directions on
`rarezipUncompress` (the local `end`).

**When you see this**, stop working on colors: the question is web *formation*,
not web *coloring*.

### 12. Mul-vs-shift web formation

**Diff looks like:** identical emitted instructions, but one side forms a web
for a scaled index and the other does not.

```c
/* forms a web */          tab * 4
/* does not form one */    tab << 2
```

**Why:** the two spellings emit the same code but are not interchangeable as
liverange-formation triggers — the multiply survives into ucode as an
expression the optimizer can name, the shift is folded earlier. Recorded on
`texLoadTextureActual`.

**Confidence: low-to-moderate.** This is a single observation, and an earlier
round on the same function saw `tab << 2` as a web member on the target side.
Treat it as a cheap one-variant probe when a scaled index is near your
divergence, not as a rule.

### 13. Copy-propagation defeat

**Diff looks like:** a CSE'd expression forms a web on your side and takes the
register you wanted, and no placement of a dead read displaces it.

```c
/* before */  use(id & 0xFFFF); ... use(id & 0xFFFF);
/* after  */  id &= 0xFFFF; use(id); ... use(id);
```

**Why:** masking into a formal parameter in place gives that parameter multiple
reaching definitions, and IDO does not copy-propagate such a parameter — so the
CSE expression web never forms at all, and the value falls to a ugen temp
instead of consuming a pool slot. On `texLoadTextureActual` this was the first
variant family in six rounds to match the target's instructions 43-45.

**This is the delete-a-web lever**, the counterpart to levers 7-8. A forced
color cannot delete a web; source can.

---

## The temp-FIFO lane (ugen)

The temp rotation is `t6 t7 t8 t9`, extending to `s8` and further under
pressure. It is a strict FIFO: expression temps pop from a free list and are
pushed back at last use. `view`'s **temp lane** is that pop sequence.

A temp lane that reads `rotation=+1` from slot *k* is **one event**, not *N*
mistakes: somewhere before slot *k* your candidate popped one more or one fewer
temp than the target. Fixing the visibly-wrong instructions individually is
impossible — they are downstream of a queue.

**The lever is always in the block *preceding* the visible divergence.**

### 14. Temp-FIFO phase — perturb the preceding block

**Diff looks like:** `verdict: phase-shift`, `playbook=temp-fifo-phase`, and a
temp lane with a constant `rotation=+N` tail. Frequently paired with
`prefix-exact@N` — the bytes agree right up to the surfacing point.

```c
/* before */  animApply(base + (index * 20), flags);
/* after  */  s32 slot = base + (index * 20);
              animApply(slot, flags);
```

**Why:** hoisting a call-argument expression into a named local changes the
order in which values die, and value deaths are what push temps back onto the
free list. One reordered death shifts the whole downstream rotation by one slot.
Proven on `modLoadAnimActual`, which matched in roughly 15 directed variants
once the lane view existed — against 300 variants of nothing before it.

### 15. The phantom pop

**Diff looks like:** as lever 14, and you need `+1` pop rather than a
reordering.

```c
/* materializes a pool get, emits no instruction */
if ((state == -1) != 0) { ... }

/* these are dropped entirely - zero codegen effect */
id == id;
(void)(x & mask);
```

**Why:** a comparison that feeds a *real* context materializes a temp pop that
the assembler then folds away, so the queue advances without an instruction
appearing. A bare discarded expression is eliminated before it can do anything.
The distinction is the whole lever.

**Two preconditions, both learned the hard way.** The value must already be
live in a register, and the guard must fold. Boolean-normalizing an *actual*
branch condition is not free: `(a < b) != 0` defeated `bltz`/`bgez` folding and
cost **+178 words** on `texLoadTextureActual`. On `blockSetupVertices` every
guard spelling emitted real code and grew the frame. Verify with `view` after
one variant; do not build a family on it.

### 16. The redundant-mask lever

**Diff looks like:** a one-slot temp-FIFO rotation, *and* neighbouring
statements carry asymmetric mask or cast decoration.

```c
/* before */  v->x = (s16)fx << 18;
/* after  */  v->x = ((s16)fx & 0x3fff) << 18;
```

**Why:** a mask that is a no-op at the assembler still consumes one ugen pool
get before as1 folds it away — a genuinely zero-instruction FIFO rotation,
which the `(x) != 0` guards of lever 15 usually are not. This is the reliable
free phantom pop. It matched `blockSetupVertices`.

**Treat it as a one-variant hypothesis, not a search.** And read the smell:
decoration asymmetry between neighbouring statements in *your* candidate is
itself evidence, because the original author's code is usually symmetric.
Symmetrize the decoration first and see what happens.

---

## Coalescing copies

**Diff looks like:** the residual is exactly one `move rd,rs` (or
`or rd,rs,$zero`) present on one side and absent on the other, plus a
consistent register substitution downstream that unifies the two sides.

### 17. K&R implicit-int return type

```c
/* before */  void objprint(struct Obj *o) { ... }
/* after  */  objprint(struct Obj *o) { ... }      /* K&R implicit int */
```

**Why:** 1999-era sources routinely declare functions with no return type, and
`void` versus implicit `int` changes ugen's coalescing decision — on `objprint`
an entire `move` instruction appeared only under the non-void return.

**When a candidate is exactly one coalescing copy short, try this before
anything else.** It is one variant. Patch the declaration *and* the definition:
a mismatched pair compiles-fails silently in some harnesses and gets recorded as
a negative result that was never actually tested.

### 18. CSE multiplicity

```c
/* before */  a = f(p->q); b = g(p->q);        /* p->q referenced twice */
/* after  */  t = p->q; a = f(t); b = g(t);    /* single occurrence */
```

**Why:** under equal instruction shape the coalesced copy lands on the
multi-referenced CSE temp, so making an expression single-occurrence through a
named intermediate moves the copy onto the other value. This is the second lever
to try when lever 17 does not move it (`objprint`, layer 2).

Be aware that these two can be mutually exclusive — on `objprint` the two
levers each fixed one half of the residual and no source form did both. When you
hit that, you are at the boundary of source search.

---

## When source search is over

### 19. Callee-saved tie-breaks and the forced-color oracle

**Diff looks like:** `verdict: register-permutation` — every register
difference forms one consistent bijection — typically over callee-saved
registers (`$s1` versus `$s2`).

**Why source cannot reach it:** the choice is a priority-order tie-break
between two webs inside uopt's coloring, and source reorderings either
canonicalize away or explode into unrelated changes. On `func_80053B24` the
high-priority web (save 833) took `$s1` and the deferred one (save 0.67) got
`$s2` by elimination; forcing only the high-priority web let the swap cascade
naturally.

**What to do instead:** if your project has an instrumented static-recomp IDO,
go straight to a forced-color probe rather than more variants. If it does not,
this class is a legitimate stopping point — record it, bundle the scratch, and
move to the next function.

**One trap, because it cost a campaign a full round:** the instrumented pass
has *two disjoint web namespaces*, `p1` (callee-saved) and `p2` (caller-saved).
A sweep is exhaustive only if it covers both. A `p1`-only sweep once produced a
confident "this is ugen's fault" conclusion when the answer was a `p2` web, one
force from exact. The workbench now requires phase-qualified force keys
(`p2:w55=c2`) for exactly this reason. See
[Trace analysis](trace-analysis.md).

---

## Dead families — do not spend variants here

Each of these was searched exhaustively at real cost. Skipping them is as
valuable as any lever above.

| Family | Verdict |
|---|---|
| `a \| b` versus `b \| a` | Canonicalized to byte-identical objects. Use `x \|= y` (lever 2). |
| Declaration-order permutation | Inert across three campaigns and ~1000 variants. Test once, cheaply, then drop it. Two exceptions exist: absolute first-declared position mattered on `texLoadTextureActual`, and removing a fully-unreferenced local once changed codegen 20+ instructions away. |
| Bare discarded expressions | `id == id;`, `(void)(x & mask);`, dead second stores — all eliminated with zero codegen effect. Use an empty-if (lever 7). |
| Line joins and comma merges to beat `-g3` | `.loc` is per statement; the barriers do not move (lever 3). |
| Loop splitting to force a memory re-read | Defeats IDO's own loop-invariant motion; +147 words measured (lever 5). |
| The permuter on varargs functions | IDO's `va_arg` is unparsable by pycparser either expanded or preserved. Plan `printf`-family campaigns without it. |
| The permuter as a solver | Roughly 140,000 iterations across four campaigns solved zero residuals. It is a hypothesis generator; it earned its keep once, by exposing lever 17 through a red herring. |

---

## Verdict-to-lever index

| `view` verdict / `playbook` | Levers |
|---|---|
| `constant` / `constant-audit` | 1, then re-derive fakes |
| `commutative-order` / `ast-shape` | 2 |
| `schedule` / `g0-schedule-probe` | 3, 4 |
| `structure` / `structure-buckets` | 1, 4, 5, 6 |
| `phase-shift` / `temp-fifo-phase` | 14, 15, 16 |
| `allocation` / `pool-position` | 7, 8, 9, 10, 11, 12, 13 |
| `register-permutation` / `forced-color-oracle` | 17, 18, then 19 |

## See also

- [Start here](START_HERE.md) — the loop these levers fit into.
- [Working a backlog of near matches](walkthrough-30-near-matches.md) — how to
  apply this guide to thirty functions instead of one.
- [Aligned mechanism view](view.md) — the command that names the mechanism.
- [Final-function campaign lessons](final-function-campaigns.md) — the longer
  reasoning behind several of these entries.
