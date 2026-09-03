# From verdict to edit

**You ran `diagnose`. It printed a verdict, some webs, and a lever. Now what
do you actually type into the `.c` file?**

[Start here](START_HERE.md) teaches you to read the screen. [The field
guide](field-guide.md) catalogues the levers. This page is the twenty minutes
between them: one function, one screen, one source edit, re-diagnosed. Every
command runs right now against fixtures in this repository — no ROM, no
compiler, no toolchain.

- [1. Run it](#1-run-it)
- [2. Six differences, one cause](#2-six-differences-one-cause)
- [3. Why a "fake" edit is not superstition](#3-why-a-fake-edit-is-not-superstition)
- [4. The edit](#4-the-edit)
- [5. When the screen names the edit for you](#5-when-the-screen-names-the-edit-for-you)
- [6. Re-diagnose, and know when to stop](#6-re-diagnose-and-know-when-to-stop)

---

## 1. Run it

```sh
decomp-workbench diagnose-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep --terse
```

```text
verdict: phase-shift  structural=0 schedule=0 register=6 constant=0 hunks=1 playbook=temp-fifo-phase
ownership: owning_pass=ugen-temp-ring reachability=source-reachable ownership_basis=heuristic
signature: prefix-exact@12 state-divergence@temp:5 register-first-divergence
webs: w1 t7->t8 x2, w2 t8->t9 x2, w3 t9->t6 x2, w4 t6->t7 x2
```

Six differing instructions. The temptation is to open the C, find the six
places, and start changing them. That is the mistake this page exists to
prevent.

## 2. Six differences, one cause

Read the three header lines in the order they print, because that is the order
the facts happened in.

**`prefix-exact@12`** — the first twelve instructions are byte-identical. The
function is not wrong; something drifted at row 12.

**`state-divergence@temp:5`** — the temp lane, the register queue `ugen` hands
out for block-local expression values, first differs at slot 5. That is
*before* row 12 in causal terms: the queue had already drifted when row 12
merely became the first instruction to show it.

**`webs:`** — four consistent substitutions, `t7->t8`, `t8->t9`, `t9->t6`,
`t6->t7`. Follow them round: that is one rotation, not four decisions.

**`ownership:`** — the pass that took the decision, and how close a source edit
gets to it. `owning_pass=ugen-temp-ring` says this is the block-local
allocator's queue rather than the colouring pass, and
`reachability=source-reachable` says a lever reaches it — so the twenty minutes
below are worth spending. Had it read `pass-owned`, the footer would have sent
you to a search instead of to a source edit, and `ownership_basis=heuristic`
would still have told you that answer was read off the residual's shape rather
than measured. The footer for this verdict ends at
[law L64](compiler-laws/ido-5.3.md#l64-the-integer-temp-ring-is-seeded-t6-t7-t8-t9-t0--t5)
and [L65](compiler-laws/ido-5.3.md#l65-a-redundant-mask-still-costs-one-ring-pop--the-phantom-pop),
which are the mechanism these levers rest on: the ring's seed order, and the
fact that a folded mask emits nothing and still pops it.

```sh
decomp-workbench guide laws ido53 L65
```

The lane view says it in one picture:

```text
  temp  target     t6 t7 t8 t9 t6 t7 t8 t9 t6   slots=0..8/9
        candidate  t6 t7 t8 t9 t6 t8 t9 t6 t7
                   ---------------^ slot=5 aligned_row=12 rotation=+1
```

The candidate's queue is running **one slot ahead** from slot 5 onward. Every
register in the tail is the target's next one. Six "wrong registers" are one
event: somewhere before slot 5, your candidate popped one more temp than the
target did, or released one earlier.

> A web, in compiler terms, is one live range of a variable — every place it is
> defined and used until it dies — and the allocator gives one web exactly one
> register for its whole life. That is the unit these substitutions are grouped
> by, and it is why fixing them individually is impossible: you would be
> arguing with a queue.

So the question is not "which six registers are wrong". It is **"what happened
in the block before slot 5"**.

## 3. Why a "fake" edit is not superstition

The next section asks you to add a line of C that emits no instruction. That
feels like voodoo the first time, so here is the model that makes it ordinary.

IDO's register assignment is not arbitrary. It is a function of a small number
of inputs, and each classic decomp idiom pokes exactly **one** of them:

| Idiom | The input it moves |
|---|---|
| `if (gSomeGlobal) {}` | web *count* — creates a code-free web that takes the next free pool slot, shifting everything after it |
| `void f(...)` versus K&R `f(...)` | *coalescing* — return type decides whether ugen folds a copy away |
| `t = p->q;` then use `t` twice | CSE *ownership* — which value the coalesced copy lands on |
| joining or splitting statement lines | *scheduling* — `-g3` `.loc` records are a tie-break input to `as1` |
| a redundant, assembler-folded mask | one temp-queue *pop* — the FIFO advances, no instruction appears |

None of these are tricks against the compiler. They are the compiler's own
inputs, addressed directly. And half of them are plausible original code: a
1999 source tree is full of compiled-out debug macros, defensive reads, and
K&R declarations. `if (gDebugFlag) {}` is not a hack you invented — it is very
often what the author actually wrote, with the body inside an `#ifdef` that was
off for the shipping build.

The full catalogue, with the measured effect of each, is [the field
guide](field-guide.md). `decomp-workbench guide <playbook>` prints the relevant
part of it without leaving the terminal.

## 4. The edit

The footer already named the family and the levers:

```text
next: one upstream event, not 6 sites (temp lane, slot 5, aligned row 12, rotation +1).
      perturb the PRECEDING block: hoist a call-argument expression into a named local, which reorders value deaths.
```

```sh
decomp-workbench guide temp-fifo-phase
```

That prints levers 14, 15 and 16 in full. Lever 14 is the cheapest, so take it
first. The rule is: **the lever goes in the block before the divergence**, not
at the sites that look wrong.

Find the last call before the divergence. In the candidate it looks like this:

```c
/* before — the argument expression is computed inline at the call */
animApply(base + (index * 20), flags);
```

The expression `base + (index * 20)` is evaluated into a temp that dies
*immediately* at the call. Give it a name and it dies later:

```c
/* after — one named local, one changed death point */
s32 slot = base + (index * 20);
animApply(slot, flags);
```

That is the whole edit. It emits the same instructions; what it changes is
*when the value dies*, and value deaths are what push temps back onto the free
list. One reordered death shifts the entire downstream rotation by one slot —
which is exactly the `+1` the lane view measured.

One dimension per attempt. Rebuild the translation unit the way your project
normally builds it — full TU, asm-processor and all — and compare again.

## 5. When the screen names the edit for you

The twenty minutes above are what you spend when the verdict names a mechanism
and you have to pick the lever. For four residual classes the screen does that
step itself, in a `lever:` block under the mechanism view:

```text
lever: stack-home -- the frames agree and one home is displaced at an unchanged
  instruction count, which is one declaration too many
  edit (reuse-an-existing-local-as-carrier): carry the value in a local that is
  already dead at that point instead of declaring a second one; the declared
  count falls by one and every home below it moves one slot, at an unchanged
  instruction count
  proved on: func_overlay_026_F0000B18_187AF10, Mickey's Speedway USA,
  2026-09-03: 129/131 words to exact, 131 words on both sides
  evidence: frame: target 48 bytes, candidate 48 bytes, delta +0
  evidence: 2 aligned row(s) differ only in a stack displacement, over 1
  distinct home(s): a frame fact, not an immediate
  evidence: every declared local reserves a home whether or not it is
  register-coloured, and the declared block rounds up to 8 bytes: measured over
  five builds on func_overlay_022_F0000000, 7 locals -> 0x58, 6 -> 0x58, 5 ->
  0x50
  capture: declared-local count: rebuild with CDX_SYMTAB=1 on the instrumented
  uopt and pass the log as --ladder
  or (drop-a-declared-local) when the candidate frame is larger than the
  target's, or one homed value sits one word above the target's home with the
  frame equal
  or (declare-the-pair-later) when the frames are equal and two or more
  adjacent homes are displaced by the same amount
```

The block prints under the mechanism view in the full report. `--terse`, which
section 1 used, trims it along with the lanes.

Four classes, and each one is a different question about where the evidence
comes from:

| `lever_class` | Read from | The edit family | Lever |
|---|---|---|---|
| `stack-home` | the two prologues, and `--ladder` for the declared count | drop a declaration, reuse a dead local as the carrier, or declare a pair later | [40](field-guide.md#40-de-declare-a-value-so-it-takes-a-compiler-temp-home) |
| `temp-ring` | `--ring-trace` for the charged line, `--source` for the construct on it | read a field directly, scale an index twice, or split a fused accumulate | [41](field-guide.md#41-buy-or-sell-a-ring-pop-with-the-construct-that-costs-one) |
| `line-order` | `--emit-trace`: the line-order conflicts | join the initialiser to the loop header's physical line, or change a hoist's birth order | [42](field-guide.md#42-join-an-initialiser-to-the-loop-headers-physical-line) |
| `unreachable` | `--as1-trace`'s deciding key, or a catalogue proof whose precondition the residual already meets | none — read the proof and spend the builds elsewhere | [43](field-guide.md#43-read-the-proof-before-re-deriving-it) |

**The rule that makes the block worth reading: there is no `edit (…)` line
whenever the input that would name one is missing, and `capture:` names the
command that produces it.** A `lever: temp-ring` with no edit and a `capture:`
line is not the tool hedging — it is the tool declining to guess which of three
constructs moved the pop, because that is a fact about the free list and not
about the disassembly. Capture the trace and run it again.

The block above is the one class that reads the other way. Its three
directions are picked apart by the frame pair, which every disassembly carries,
so it names an edit straight away and its `capture:` line asks for the ladder
that would corroborate the declared count rather than for the evidence that
chose the family.

That refusal has a receipt. `overlay40UpdateEntries` was recorded "not
reachable by statement placement" by an analyst with four regressed variants
and a correct reading of everything they could see. The line the scheduler
actually reads was not one of those things: a loop-invariant hoisted into the
preheader carries the *loop header's* line, so the initialiser they had already
pushed as late as C allows was still winning the tie. With the emit trace, one
join — `remaining = 7; do {` — took it to exact the same day. A guessed lever
family would have re-manufactured that verdict rather than corrected it.

```sh
decomp-workbench diagnose target.o build/candidate.o --function animStep \
  --ring-trace ugen.log --lever-proc 3
```

`--ladder`, `--emit-trace` and `--as1-trace` supply the other three classes'
inputs the same way.

## 6. Re-diagnose, and know when to stop

```sh
decomp-workbench diagnose target.o build/candidate.o --function animStep
```

If the rotation was the whole story, `verdict=instruction-exact` and
`aligned_total=0`, and you go run your project's link and ROM verification.
Function exactness is not whole-project proof.

If it moved but did not close, read the new verdict — it is a new question, and
it gets its own lever. If it did **not** move, you have spent one variant to
learn that this block is not where the queue drifted; try the block before it.

**And there is a legitimate place to stop typing.** If you reach `verdict:
register-permutation` — every difference forming one clean bijection over
callee-saved registers — the footer will tell you so, and lever 19 explains
why *hand* source search is over there:

```sh
decomp-workbench guide 19
```

Read the `routing=` token beside the playbook before you record anything. On an
allocation, colour, or schedule tie it says `permuter-first`, and the footer
ends with the sentence that goes with it:

```text
next: no HAND lever found -- this is a permuter target; run the sweep before concluding a wall.
```

That is not a formality. Two functions whose verdicts read "interference-forbidden
colour" and "list-scheduler slot-fill — no source lever" were matched by a
twenty-minute permuter run, after a bespoke instrumentation build had been
funded to explain why they could not be. Nothing measured from two
disassemblies can prove an allocation tie unmatchable; it can only say that
*this* lever set does not reach it.

So the stopping point has one more step in it: run
`decomp-workbench permute-doctor <function>` and then a sweep, and let
`permute classify` say whether the search was still descending or flat. If it
is flat, record it, bundle the scratch with `bundle-scratch`, and take the next
function — now with a measurement behind the claim. A campaign that stops honestly on three functions and matches thirty
is a good campaign.

## See also

- [Start here](START_HERE.md) — the ten-minute tour of the screen this page
  acts on.
- [Field guide](field-guide.md) — every lever, with the measured effect of
  each; levers 40-43 are the four the `lever:` block names.
- [Compiler laws: IDO 5.3](compiler-laws/ido-5.3.md) — what the compiler does
  about each of them, and what it does about the ones no edit reaches.
- [The `guide` command](guide-command.md) — those levers, in the terminal.
- [Aligned mechanism view](view.md) — every option on the screen above.
- [Working a backlog of near matches](walkthrough-30-near-matches.md) — the
  same loop across thirty functions, in triage order.
