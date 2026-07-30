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
- [5. Re-diagnose, and know when to stop](#5-re-diagnose-and-know-when-to-stop)

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

## 5. Re-diagnose, and know when to stop

```sh
decomp-workbench diagnose target.o build/candidate.o --function animStep
```

If the rotation was the whole story, `verdict=instruction-exact` and
`aligned_total=0`, and you go run your project's link and ROM verification.
Function exactness is not whole-project proof.

If it moved but did not close, read the new verdict — it is a new question, and
it gets its own lever. If it did **not** move, you have spent one variant to
learn that this block is not where the queue drifted; try the block before it.

**And there is a legitimate place to stop.** If you reach `verdict:
register-permutation` — every difference forming one clean bijection over
callee-saved registers — the footer will tell you so, and lever 19 explains
why source search is genuinely over there:

```sh
decomp-workbench guide 19
```

Without an instrumented toolchain, that class is a stopping point, not a
failure. Record it, bundle the scratch with `bundle-scratch`, and take the next
function. A campaign that stops honestly on three functions and matches thirty
is a good campaign.

## See also

- [Start here](START_HERE.md) — the ten-minute tour of the screen this page
  acts on.
- [Field guide](field-guide.md) — all 22 levers, with the measured effect of
  each.
- [The `guide` command](guide-command.md) — those levers, in the terminal.
- [Aligned mechanism view](view.md) — every option on the screen above.
- [Working a backlog of near matches](walkthrough-30-near-matches.md) — the
  same loop across thirty functions, in triage order.
