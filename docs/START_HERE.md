# Start here

**You have a function that is almost matched. Here is what to do.**

Ten minutes, in order. Every command on this page runs right now, against
fixtures shipped in this repository. You do not need a ROM, a compiler, a
toolchain, or an AI to follow it.

```sh
git clone https://github.com/akratch/n64-decomp-workbench.git
cd n64-decomp-workbench
python3 -m pip install -e .
```

---

## Minute 0 — the mental model

You are in a loop, and the workbench serves one step of it:

```text
   classify the residual  ->  pick a lever  ->  change one thing  ->  compare again
        ^                                                                  |
        +------------------------------------------------------------------+
```

The hard step is the first one. "13 words differ" is not a classification —
it is a volume. A classification is a *mechanism*: a wrong constant, a
commutative operand order, a scheduling barrier, a temp-register phase, a
coloring-pool position. Different mechanisms have different levers, and the
lever for one is a waste of a day on another.

Three views share one analysis:

- **`compare`** — how different are these two objects, and is the difference
  real or linker noise?
- **`view`** — where does the divergence begin, which mechanism owns it, and
  which lever family moves it?
- **`diagnose`** — the common one-command journey: comparison plus the decisive
  mechanism view, with each input loaded once.

This tutorial teaches the two primitives so their evidence is legible.
Day-to-day, start with `diagnose`; use `compare` for a compact gate and `view
--show-all` when you need every hunk.

---

## Minute 1 — "Do I need to isolate the function first?"

**No. Do not isolate.** Build your translation unit exactly the way your
project normally builds it, with asm-processor (the community preprocessor
that keeps hand-written MIPS assembly inside C while a function is still being
matched) and everything else in the chain, and point the workbench at the
resulting `.o`:

```sh
decomp-workbench compare expected/code/foo.o build/src/code/foo.o \
  --function func_802963D0_6A7A80 \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

`--function` (or `--symbol`, the same option) scopes the whole comparison to
one symbol. The rest of the translation unit is disassembled and ignored. You
get a single-function verdict out of a whole-file build, which is exactly what
you wanted isolation for.

This matters more than it looks. **Isolation changes codegen.** Pull a
function into a small harness — a hand-written `base.c`, a decomp.me scratch,
a permuter working file — and you have changed the register pressure, the
alias facts, the type definitions reaching the optimizer, and often the
assembler flags. It is routine for a function to compile to 96 instructions in
an isolated harness and 93 in its real translation unit. The three extra
instructions are an artifact of the harness. If you tune against them, you are
tuning against a function that does not exist.

So:

| | |
|---|---|
| Compare against | your normal full-TU build output |
| Isolate for | nothing in this workflow |
| asm-processor | leave it exactly as your project has it; it does not interfere |
| `campaign` variants | full-TU source files — `{source}` is a whole translation unit, compiled by your normal wrapper |

The one time an isolated harness is legitimate is a decomp.me scratch you are
handing to someone else, and even then, verify flag parity before believing
its numbers. A single missing assembler flag once produced 78 "structural"
words of difference on source that was already ROM-verified.

---

## Minute 2 — run `compare` and read the verdict

Run this now:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump
```

```text
verdict=instruction-exact aligned_total=   0 words=   0 raw=   2 opcodes=   0 gaps=   0 norm=   0
raw difference classes: relocation_controlled=2
next: Instruction-exact: raw differences are linker-controlled relocation fields
```

*(your terminal also prints the matching field-guide levers here — this page trims them for space)*

`compare-dumps` is `compare` reading saved GNU objdump text instead of object
files. Identical analysis, no objdump and no `.o` needed — which is why this
page is runnable and why you can hand a mismatch to someone else without
shipping objects.

Read the line left to right:

| Field | Meaning |
|---|---|
| `verdict` | the mechanism, not the volume — this is the field that decides your next move |
| `aligned_total` | LCS-aligned differences: **the number to rank candidates by**. (LCS = longest common subsequence — the same alignment idea behind `diff`, which is why an inserted instruction doesn't cascade into unrelated positional noise) |
| `words` | relocation-aware positional differences: the matching oracle at zero, a tiebreaker above it |
| `raw` | literal word differences, including linker-controlled fields |
| `regs`, `fp` | how many differences are register-only |
| `insns` | instruction count, target and candidate |
| `frame` | stack frame adjustment |

Here `words=0` and `raw=2`. A byte comparison would have rejected this
candidate over two relocation fields the linker owns. The workbench does not,
because it masks them. That gap between `raw` and `words` is the single most
common false alarm in decomp.

And a real one:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/register-mismatch.objdump \
  --show-diff
```

```text
verdict=allocation-mismatch aligned_total=   1 words=   1 raw=   3 opcodes=   0 gaps=   0 norm=   1
aligned residual classes: aligned_register=1
diff_sites=3 (register=1, relocation-controlled=2)
next: Opcode shape matches but register allocation differs.
```

*(your terminal also prints the matching field-guide levers here — this page trims them for space)*

`--show-diff` prints every differing site with both words and both
disassemblies. **No verdict ever suppresses evidence** — if a site differs, it
is printed, whatever the verdict decided to call the residual.

---

## Minute 3 — what the verdict is telling you to do

The verdict names the *cheapest mechanism that explains the whole residual*.
Cheap classes are cheap to fix; work them first.

| Verdict | What it means | First move |
|---|---|---|
| `exact` | nothing differs for this symbol | run your project's normal link/ROM check |
| `instruction-exact` | only linker-controlled fields differ | done at source level; do **not** mutate C |
| `constant-mismatch` | an immediate is wrong | audit the flag/enum against the assembly, then re-derive every fake |
| `commutative-order` | operands swapped on a commutative op | expression shape (`x \|= y`), never the allocator |
| `schedule-mismatch` | same instructions, different order | regroup statements; run the `-g0` probe |
| `structure-mismatch` | opcode shape / control flow differs | stay at the C level; do not touch registers yet |
| `allocation-mismatch` | shape matches, registers do not | go to `view` — the lever is upstream of what you can see |
| `relocation-layout-mismatch` | relocation metadata differs | a TU/linker question, not a source question |

Three of these are traps worth naming now:

- A **`structure-mismatch` with a huge word count can be one wrong constant.**
  One wrong enum identifier once produced 183 "structural" words. If the
  earliest difference is a `lui`/`li`/`andi` materialization, audit that
  constant before anything else.
- A **`structure-mismatch` can be one inserted instruction.** Positional word
  counting turns a single insertion into a cascade. That is what `view` fixes,
  next.
- A **`schedule-mismatch` that survives `-g0` is not automatically a
  "wrong compiler version" question.** If the instruction multiset is already
  equal and the allocator lanes are already identical, suspect *which source
  line each statement was attributed to by the preprocessor* before
  suspecting the compiler build: `cfe` records per-statement line numbers
  from its preprocessed input, and `uopt`/`ugen` can honor those as
  scheduling barriers even at `-g0`, which only strips `.loc` records from
  the object. The workbench's line-assignment probe (`decomp-workbench probe-lines`; and, where available, a
  re-preprocess with an external K&R-lineage preprocessor such as IDO's
  `acpp`) can confirm this in one comparison, and `probe-lines --tie
  STATEMENT=LINE` answers the follow-up — which line that statement needs.
  See the [SSB64 `drawbitmap`
  case study](../case-studies/ssb64-drawbitmap.md), where months' worth of
  compiler-version archaeology across five toolchain generations turned out
  to be exactly this.

Whatever the verdict, **you are looking for the mechanism, not the count.**

---

## Minutes 4-6 — run `view` and read the four sections

This is the command that answers "what do I do next", and it is the reason to
be on the current version rather than 0.2.0.

```sh
decomp-workbench diagnose-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep
```

(Against real object files it is `diagnose target.o candidate.o --function name
--objdump /path/to/mips64-elf-objdump`. Same screen.)

You first get the compact comparison truth, then the mechanism screen with four
sections. Read the mechanism in this order.

### 1. The verdict header and signature

```text
view animStep  target_instructions=24 candidate_instructions=24 aligned_rows=24 match=18
verdict: phase-shift  structural=0 schedule=0 register=6 constant=0 hunks=1 playbook=temp-fifo-phase
signature: prefix-exact@12 state-divergence@temp:5 register-first-divergence
webs: w1 t7->t8 x2, w2 t8->t9 x2, w3 t9->t6 x2, w4 t6->t7 x2
the FIRST divergence is a register-class divergence, not a structural one: the decision was made upstream of hunk 1 even though it surfaces there.
```

`verdict: phase-shift` and `playbook=temp-fifo-phase` are the answer to "which
mechanism". The counts tell you the residual is purely register: six register
rows, zero structural, zero schedule, zero constant.

The `signature:` line is the part people miss. `prefix-exact@12` says the first
twelve aligned instructions are byte-identical. `state-divergence@temp:5` says
the compiler's *temp-register state* diverged at slot 5 — **before** the bytes
did. And the sentence spells out the consequence: the decision was made
upstream of the block where you can see it.

That sentence is worth a day. One real campaign burned thirteen variants
editing the visibly-wrong block before working out that the block was innocent.

### 2. The register lanes

```text
REGISTER LANES (per-class assignment sequences, matching instructions included)
  pool  target     s0 s1 s2 a0 s0   slots=0..4/5
        candidate  s0 s1 s2 a0 s0
                   identical 5/5
  temp  target     t6 t7 t8 t9 t6 t7 t8 t9 t6   slots=0..8/9
        candidate  t6 t7 t8 t9 t6 t8 t9 t6 t7
                   ---------------^ slot=5 aligned_row=12 rotation=+1
```

A lane is the ordered sequence of registers a class gets assigned, in emission
order, **including the instructions that match**. That inclusion is the whole
point: the signal here lives in the temps that matched. Diff only the
mismatched instructions and the queue is invisible.

IDO (SGI's optimizing MIPS C compiler, the usual N64 decomp target) 5.3
has two register populations, and they behave differently:

- **pool** (`v0 v1 a0-a3 t0-t5`) — uopt's colored variable webs. Lowest free
  index wins.
- **temp** (`t6-t9 s8`) — ugen's block-local expression rotation, a strict FIFO.

Here the pool is identical and the temp lane runs *one slot ahead* from slot 5
onward — `rotation=+1`. That is one upstream event, not six independent
mistakes. The candidate popped one extra temp, or popped one fewer, somewhere
before this block.

### 3. The hunks and webs

```text
HUNK 1  class=register rows=12..17 target=12..17 candidate=12..17
     12 > addu $t7,$s2,$s0  | addu $t8,$s2,$s0   t7->t8 [w1]
     13 > lw $t8,20($t7)    | lw $t9,20($t8)     t8->t9 [w2] t7->t8 [w1]
     ...

WEBS (one consistent substitution may explain many sites)
  w1  t7->t8  count=2 rows=12,13
  w2  t8->t9  count=2 rows=13,14
```

Hunks are LCS-aligned, never positional — see the aside below for why that is
not a detail. Every non-matching row is printed inside its hunk, with both
disassemblies and the register substitution named.

A web, in compiler terms, is one live range of a variable — every place it's
defined and used until it dies — and the allocator gives one web exactly one
register for its whole life; that's the unit these substitutions are grouped
by.

The **WEBS** section groups those substitutions: if one swap explains six
sites, it prints as one web, not six problems. Four webs here, all of them
consequences of the same rotation.

### 4. The `next:` footer — this is your instruction

```text
next: one upstream event, not 6 sites (temp lane, slot 5, aligned row 12, rotation +1).
      perturb the PRECEDING block: hoist a call-argument expression into a named local, which reorders value deaths.
      or materialize a phantom pool get with `(x == C) != 0` inside a real `if`; a bare discarded expression is dropped with no codegen effect.
      do not fix the divergent sites individually; declaration-order permutation is a dead family here.
```

*(your terminal also prints the matching field-guide levers here — this page trims them for space)*

Four lines: what happened, two levers to try, and one family explicitly ruled
out. It also tells you what *not* to do — the dead families are as valuable as
the live ones, because each one is a day you do not spend.

### Aside: why the alignment matters

A single inserted instruction, counted positionally, looks like dozens of
scattered register differences. Try it on the other fixture pair:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump \
  --symbol blockSum
```

```text
caution: alignment inserted 1 gaps (10 opcode mismatches) -- compare candidates on positional words (words=), not aligned rows
verdict=structure-mismatch aligned_total=   1 words=  11 raw=  11 opcodes=  10 gaps=   1 norm=   1
aligned residual classes: aligned_structural=1
alignment gaps: insertions=1 deletions=0 (opcodes=10, words=11, raw=11)
```

Eleven positional words, one aligned difference — and `aligned_total` is the
number `rank` and `campaign` sort on, because `words` is the one that misranks.
Now the aligned truth in full:

```sh
decomp-workbench view-dumps \
  examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump \
  --symbol blockSum
```

```text
verdict: structure  structural=1 schedule=0 register=0 constant=0 displacement=1 hunks=1
HUNK 1  class=structural rows=5..5 target=none candidate=5..5
      5 > -                                | sll $t6,$t6,2                     structural
```

**One extra `sll`.** Ten of the eleven "register mismatches" were the same
instructions shifted by one slot, and the eleventh was a branch whose encoded
offset moved because of the insertion. On a real function this effect has been
measured at 635 positional words against an aligned truth of 27 structural plus
8 register. If you are triaging a batch by `words=`, you are sorting by noise —
which is why `aligned_total=` leads the line and owns the ranking.

**With one limit, and the run above printed it.** `gaps=` counts the rows the aligner filled on one side only. Once a candidate
has any, it is aligned against a *different subsequence* of the target than a
gap-free candidate is, so its `aligned_total` is the honest description of
**that** candidate and not a number to read against another one's. `rank` and
`campaign` detect a mixed set and order it on `words=` instead, and say so.

---

## Minute 7 — pick the lever

The footer names a lever family. [The field guide](field-guide.md) gives you
the actual C.

For this example, `playbook=temp-fifo-phase` points at the temp-FIFO entries:
hoisting a call argument into a named local, the phantom-pop guard, the
redundant-mask lever. Each field-guide entry gives you the shape of the diff,
the C before and after, why it works, and which verdict points there.

The mapping is direct:

| `playbook=` | Field guide section |
|---|---|
| `constant-audit` | [Wrong constant](field-guide.md#1-wrong-constant-masquerading-as-structure) |
| `ast-shape` | [Commutative operand order](field-guide.md#2-commutative-operand-order) |
| `g0-schedule-probe` | [The `-g0` diagnostic](field-guide.md#3-the--g0-diagnostic) |
| `temp-fifo-phase` | [Temp-FIFO phase](field-guide.md#the-temp-fifo-lane-ugen) |
| `pool-position` | [Coloring pool position](field-guide.md#the-coloring-pool-uopt) — one of three unresolved allocation families; read `view`'s footer for which. If the register is *taken* rather than underpriced, that is [lever 28](field-guide.md#28-alias-a-local-to-take-it-out-of-the-allocation-contest) |
| `forced-color-oracle` | [Callee-saved tie-breaks](field-guide.md#19-callee-saved-tie-breaks-and-the-forced-color-oracle) |
| `structure-buckets` | [Structure first](field-guide.md#working-a-structure-mismatch) |

---

## Minute 8 — change one thing, then compare again

One dimension per attempt. Rebuild the translation unit normally, re-run
`view`, and read the same four sections. You are looking for one of three
outcomes:

- **`words` fell** — right family, keep going in that direction.
- **`words` unchanged and the lanes are unchanged** — the change was inert.
  IDO drops a great deal: bare discarded expressions (`x == x;`,
  `(void)(x & mask);`) and unused declarations produce no codegen at all.
- **`words` rose sharply** — you defeated an optimization IDO was already doing
  correctly. Revert immediately; do not "push through". Restructuring a loop to
  force a re-read once cost +147 words against a candidate that was already
  close.

Record every attempt. The word count *and* the verdict, per variant. Half the
value of a campaign is knowing which families are dead.

---

## Minute 9 — sweep with `campaign` when one variant is not enough

When you have a family rather than a hypothesis — six placements of a dead
read, four spellings of a mask — stop editing by hand:

```sh
decomp-workbench campaign expected/code/foo.o variants/*.c \
  --function func_802963D0_6A7A80 \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --compile-cwd /path/to/project \
  --jobs 8
```

Two things to be clear about, because they are the ones people get wrong:

- **Each `{source}` is a full translation unit**, not an isolated function.
  `compile-one.sh` is your project's normal single-file build. The campaign is
  a sweep over whole-TU variants — same reasoning as Minute 1.
- **It stops at the first exact match by default.** Candidates already in
  flight finish and are recorded; nothing you paid for is thrown away. Pass
  `--no-stop-on-exact` when you want the whole grid for a basin census.

Once a function is exact, suspicious scaffolding deserves one bounded cleanup
pass. `experiment inspect-source` inventories candidates without calling them
dead; `experiment compose` combines measured mechanisms that may have been
tested on different parent sources. Keep the exact candidates, then use
`object collateral` before the project's normal link/ROM verification.

The workbench creates a manifest and JSONL ledger by default under
`.decomp-workbench/campaigns/`. Reopen it instead of reconstructing the run:

```sh
decomp-workbench campaign status
decomp-workbench campaign note "temp lane still diverges after the call"
decomp-workbench campaign resume
```

Status names the best trajectory, failures, object-basin collapse, experiment
families, and the active hypothesis. Resume verifies target, source, wrapper,
objdump, environment, and optional toolchain identities before running work
absent from the ledger. An exact campaign stays stopped unless
`--continue-after-exact` explicitly asks for the skipped grid.

For a generated family, validate and attach an
[`experiment` manifest](../examples/experiments/README.md); parameters then
survive filenames, and a protected instruction region can rank before the
whole-function residual.

To filter a pile of objects on one property, do not grep the report or parse
its JSON — ask, and read the exit code:

```sh
for object in build/variants/*.o; do
    decomp-workbench compare expected/code/foo.o "$object" \
      --function func_802963D0_6A7A80 \
      --census aligned_register=0,frame=-128 >/dev/null && echo "$object"
done
```

`--census KEY=VALUE` works on `compare`, `compare-dumps`, `view`, and
`view-dumps`, over any key those commands report. Exit `0` means every
predicate held, `3` means one failed, and `2` means the question itself was
wrong — a misspelled key is caught before the inputs are read, so it costs
nothing in a long sweep.

See [Candidate campaigns](campaigns.md) for the full option set, and
[object comparison](object-comparison.md#ask-a-question-and-read-the-exit-code---census)
for the census contract.

---

## Minute 10 — the three questions everybody asks

### "Do I need an AI, or a permuter, to use this?"

**No.** The manual path is complete: read the verdict, read the `view` screen,
pick the lever from the `next:` footer and [the field guide](field-guide.md),
try it. Everything on this page is something you do by reading a screen.

If the step from "the footer named a lever" to "I typed something into the
`.c`" is the one that feels unclear, [From verdict to
edit](from-verdict-to-edit.md) works exactly that step, once, on a fixture you
already have. `decomp-workbench guide <playbook>` prints the lever's own
section straight into your terminal.

The permuter is **optional, and it is a hypothesis generator, not a solver**.
Measured over roughly 140,000 iterations across four real campaigns, it solved
zero residuals directly. It earned its keep exactly once, by producing a
red-herring output that exposed a mechanism class nobody had thought of
(return-type coalescing). Budget it that way: run it in the background if you
like the lottery ticket, but never let it replace a directed variant.

There is also an [Agent Skill](agent-skill.md) (`install-skill codex` or
`install-skill claude`) if you *want* to hand the loop to an agent. It runs the
same commands you would. It is a convenience, not a requirement, and it does
not know anything the field guide does not tell you.

### "Am I supposed to parse `trace.lst` and understand it?"

Not yet, and probably not at all. Traces are the **last** resort, not the
first, and they are only meaningful for one verdict class.

The order is: `compare` → `view` → the field-guide levers → and only if all
three of the allocation lever families are genuinely exhausted, traces. Reach
for a trace when, and only when:

1. the verdict is `allocation-mismatch` or the view says `allocation` — a
   register-only residual with no consistent permutation and no lane rotation;
2. you have already tried the three allocation families (temp-queue phase,
   pool position, coalescing) from the field guide;
3. you actually *have* a trace producer — an instrumented static-recomp IDO.
   Stock IDO does not emit these. If your project has not built one, this step
   does not exist for you, and that is fine: three functions were matched
   without ever reading a trace.

When you do get there, `trace-summary` tells you what is in the file, then
`trace-globalcolor` (live-range costs and color decisions), `trace-fifo` (temp
reuse as a validated queue), or `trace-alias` (what the optimizer believed
about pointers). `trace-webs` aligns decisions by semantic provenance,
`trace-source` maps logical lines through retained markers without guessing,
and a calibrated [`oracle`](oracle.md) can test one bounded allocator cause.
Start at [Trace analysis](trace-analysis.md); building the producer is
[Compiler instrumentation](compiler-instrumentation.md).

A trace tells you *what the compiler decided*. It does not tell you what C to
write. The field guide does that.

### "I have 30 near-matched functions. Where do I start?"

Not with the hardest one. There is a batch triage workflow with concrete shell
for exactly this: [Working a backlog of near
matches](walkthrough-30-near-matches.md). The short version is that verdict
class, not word count, decides the order, and roughly half a typical backlog
falls to levers that cost one variant each.

---

## When you are genuinely stuck

Package the function and ask a human:

```sh
decomp-workbench bundle-scratch scratch/func_802963D0 \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-O2 -mips2'
```

That produces a complete, checksummed decomp.me handoff without uploading
anything. Include the `view` output with it — "verdict `phase-shift`, temp lane
rotation +1 from slot 5, prefix exact to 12" is a question someone can answer.
"13 words off" is not.

---

## Where to go next

| Read this if... | Document |
|---|---|
| you have a lever family and need the actual C | [Field guide](field-guide.md) |
| you have a pile of near-matches to work through | [Backlog walkthrough](walkthrough-30-near-matches.md) |
| you want every `view` option and the JSON schema | [Aligned mechanism view](view.md) |
| you want every `compare` option and verdict rule | [Object comparison](object-comparison.md) |
| you are running variant sweeps in bulk | [Candidate campaigns](campaigns.md) |
| you need to generate the variant family, and to price the levers you inherited | [Sweeps](sweeps.md) |
| a `schedule` residue survived `-g0` and every compiler you own | [Line-assignment probe](line-assignment-probe.md) |
| ordinary source levers are exhausted and you have a calibrated trace | [Allocator oracle](oracle.md) |
| you consume reports from automation | [JSON contracts](json-contracts.md) |
| a command failed or printed nothing usable | [Troubleshooting](troubleshooting.md) |
| you want the reasoning behind the levers | [Final-function campaign lessons](final-function-campaigns.md) |

Every command has `--help`. `decomp-workbench --explain-keys` prints the full
registry of printed labels and JSON keys with their meanings — the labels and
the keys are one set, deliberately.
