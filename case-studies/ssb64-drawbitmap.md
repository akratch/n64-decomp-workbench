# Case study: SSB64 `drawbitmap` — a trap under a trap under a trap

**Who this is for:** you have a function that is size-exact and register-exact
— every allocator lane matches, every web is where it should be — and a small
residue is left that is purely instructions in the wrong order. You have
already tried rebuilding at `-g0`. You are starting to suspect the ROM was
built with a compiler revision you don't have. Read this before you go
compiler-hunting.

**What this campaign was:** `drawbitmap`, libultra's sprite blitter
(`sprite.c`, part of the ultralib sprite library), in Super Smash Bros. 64
(US). 1479 instructions. The function had resisted matching long enough that
it was a known sore point on the public decomp.me scratch for it (`EqDZe`) —
reference source existed the entire time (SGI's original `sprite.c`, preserved
in the `decompals/ultralib` tree), the project compiler was known (IDO 7.1,
`-O2 -mips2`), and every other function in the translation unit already
matched. `drawbitmap` alone compiled to 6352 bytes against the ROM's 5916.
This case study is the full path from that gap to a byte-exact ROM rebuild,
written for the next person who gets stuck at the point this one nearly
stalled for good.

---

## Recognize these two traps first

If your symptom matches one of the rows below, skip to that section — you do
not need the whole narrative to fix it.

| Symptom | Verdict / signature | Section |
|---|---|---|
| A large, oddly regular structural gap (dozens to hundreds of instructions) next to a jump table or switch dispatch that looks one case too big, in code translated from SDK/library source with `#if` version guards | `structure-mismatch`, large word count, extra dispatch arm | [Trap 1](#trap-1-the-version-guard-that-silently-includes-itself) |
| Size-exact, register-exact (allocator lanes and pool webs identical), but a residual handful of words that are the *same instructions in a different order*, clustered around `lui`/`ori` constant pairs and adjacent stores | `schedule-mismatch`, small `aligned_total`, pure reorder | [Trap 2](#trap-2-the-residue-that-looks-like-a-scheduler-problem) |

---

## Trap 1: the version guard that silently includes itself

The SDK source for the sprite library guards a fifth `switch` case —
`G_IM_SIZ_DD` — with:

```c
#if BUILD_VERSION >= VERSION_J
    case G_IM_SIZ_DD:
        ...
#endif
```

Neither `BUILD_VERSION` nor `VERSION_J` is defined by default in a from-source
build. The preprocessor evaluates undefined macros as `0`, so the guard
becomes `0 >= 0`, which is **true**. The fifth case silently compiles in.
Every prior attempt at this function inherited this and compiled a 6-entry
jump table where the ROM has a 4-case `beq` chain — a +109-instruction,
436-byte structural gap (6352 vs 5916 bytes) that has no source-level
explanation, because from the compiler's point of view the guard is doing
exactly what the source says. A structural diff this size, with no visible
wrong constant or wrong expression, is what a genuinely wrong macro looks
like: the C is correct for the macro state you have, and the macro state is
wrong.

**The fix:** `#include <PR/os_version.h>`, which defines `VERSION_J` (7) for
real. With the guard honestly evaluating false, the fifth case drops out.

**Result:** size-exact, 5916/5916 bytes. Register allocation exact — `uopt`'s
colored variable webs and `ugen`'s temp-register FIFO both land 661/661
identical to the target. This is a genuinely clean match on everything except
instruction order, which is a much smaller and much better-understood problem
than what the campaign started with.

Every campaign against this function before this one stalled here, at a
"hopeless" structure mismatch, without ever finding the guard — because
nothing about the C source itself was wrong.

---

## Trap 2: the residue that looks like a scheduler problem

After Trap 1's fix, 59 words remained, in 23 clusters. Every one of them was a
pure instruction-order swap, not a wrong instruction: the ROM interleaves a
`Gfx`-word store between the `lui`/`ori` halves of the *next* statement's
constant, where the local build finishes materializing that constant before
starting the store. `compare`'s verdict for this shape is
`schedule-mismatch`: the instruction multiset is equal, only the order
differs.

This is exactly the shape the field guide's `-g0` diagnostic addresses — and
running it is the right first move. But it is not the end of the story, and
believing it is the end of the story is what turns into the next section.

---

## The wrong turn: the era-archaeology trap

**Name this pattern so you recognize it before you spend a week in it.** The
symptom is: a schedule-shaped residue survives every source-level lever you
try, so you start varying the *compiler* instead of the source — first
reasonably, then less so. The signature of having fallen into it is a long
list of "exhausted" compiler configurations that all converge on the exact
same wrong output.

That is what happened here, for hours:

- IDO 5.2, 5.3, 6.0, and 7.1 — all tried as the backend.
- MIPSpro 7.4.4 in `o32` mode, which still runs the legacy ucode pipeline and
  is a plausible SSB64-era candidate.
- Every documented `as1` pipeline-model flag.
- Every cross-era stage mix: `cfe`, `uopt`, `ugen`, and `as1` swapped
  independently against each other, generation by generation.
- An `accom`/IRIX-4 alternate-frontend rig retained from a previous campaign.

**Every single one of these either reproduced the exact same 59-word residue
("attractor A") or broke the control function, `spDraw`.** `spDraw` is a
sibling function in the same translation unit that was already known to
match; any compiler configuration that stops matching it is disqualified
immediately, cheaply, without touching `drawbitmap` at all. That discipline is
what kept this from being pure noise — but a stack of "attractor A" results
under superficially different compiler identities still reads exactly like
"this ROM needs a compiler we don't have."

**A tooling bug reinforced the wrong conclusion.** The `as1` scheduling-model
flags (`-t0` through `-t9`) were being swept with stderr suppressed. Several
of the flag spellings tried were not valid options for the `as1` build in use;
`as1` silently fell back to its default model on an unrecognized flag instead
of erroring. Eleven visibly different flag invocations therefore produced
eleven *identical* outputs, and the honest-looking conclusion was "the `-t`
model space is exhausted." It was never exhausted — it was never run.
Un-suppressing stderr later showed the real error text and revealed the
actual model family (`-rNNNN`), which had not been tried at all.

The campaign came within one wrong turn of concluding the ROM required an
unarchived compiler that does not survive anywhere. It did not. **Every
input to the scheduling stage had not actually been varied — only three of
the four had: the binary identity, the flags, and the instruction DAG. The
fourth, statement/line metadata reaching the scheduler from the preprocessor,
had not been touched at all**, because nobody had reason to believe the
preprocessor was a variable.

---

## The pivot: a permuter round trip that shouldn't have changed anything

The break came from an unrelated tool, used for an unrelated reason. A
decomp-permuter import round-trip — parsing the source with `pycparser` and
re-emitting it, with **zero mutations** — is supposed to be a no-op for
codegen purposes; it exists to normalize source shape before a permuter search
begins. Run against `drawbitmap`, it changed the schedule. **48 of the 59
residual sites flipped toward the ROM's order**, from a transformation that
was not supposed to touch semantics or even codegen-relevant shape at all.

That is a strong, specific piece of evidence: whatever `pycparser`'s
re-emission changed, that thing (and only that thing) matters to the
scheduler. The one thing text re-emission reliably changes and hand-editing
does not is **line layout** — where each statement physically sits in the
file the compiler reads.

That hypothesis was confirmed directly, not inferred: token-identical
line-reflowing of the preprocessed `.i` file (same tokens, different line
breaks) reproduced the same 48-site shift on its own, with no permuter
involved. The mechanism, read straight out of `ugen`'s listing:

```text
.loc 2 200
.loc 2 200      <- two statements sharing one source line (cc's internal cpp)

.loc 2 211
.loc 2 214      <- the same two statements, different source lines (acpp)
```

**`cfe` records a source line number per statement from the preprocessed
input it receives, and `uopt`/`ugen` treat statement line boundaries as
scheduling barriers — even at `-g0`.** The `-g0` diagnostic (field guide
lever 3) removes `.loc` debug records from the *object*; it does not remove
line-boundary information from the compiler's internal statement metadata,
because that metadata comes from the preprocessed source, not from the `-g`
flag. A schedule residue that survives `-g0` is not proof the scheduler is
untouchable — it can mean the barrier lives one stage earlier than `-g0`
reaches.

---

## The fix: preprocess with `acpp`, not `cfe`'s internal preprocessor

`cfe` ships with two ways to get preprocessed C: an internal preprocessor
(the default, invoked as part of a normal `cc` call) and IDO's separate
external `acpp` binary — a K&R-lineage preprocessor. The two attribute macro
expansions to source lines differently. When a macro invocation spans
multiple physical lines, `cfe`'s internal preprocessor puts every statement
that expansion produces on **one** line (the invocation's first line).
`acpp` attributes each successive statement of the expansion to the
**successive physical line** of the multi-line invocation — walking down the
macro call as it walks down the expansion.

`drawbitmap`'s constant-materialization statements come from exactly this
kind of multi-line macro. Under `cfe`'s internal preprocessor they all
collapse onto one `.loc` line and the scheduler treats them as one movable
group. Under `acpp`, each keeps the invocation's own line, and the same
per-statement barriers the ROM's build evidently had reappear.

The fix in practice:

```sh
acpp <the TU's normal defines> sprite.c > sprite.i
cc -c <the TU's normal -O2 -mips2 flags> sprite.i
```

Preprocess externally with `acpp`, then compile the resulting `.i` — instead
of letting `cc` invoke its internal preprocessor implicitly.

**Result:** `drawbitmap` reaches the relocation floor — no residue left that
isn't linker-controlled. Rebuilding the **full US ROM** with this one-rule
Makefile change (route this translation unit's preprocessing through `acpp`
before compiling) produces a **byte-identical, sha1-equal ROM** from clean,
unmodified SDK source.

There is a plausible historical reading here, not just a technical one: HAL's
build system for this game preprocessed with `acpp` rather than relying on
`cfe`'s internal preprocessor. That is consistent with an earlier, separate
campaign's finding that this project's game-code build pipeline (as opposed
to its SDK-library build) was `acpp`/`accom`-lineage throughout — see
[Alternate authentic frontends](../docs/alternate-frontends.md). Two
independent campaigns, on different functions, converged on the same
external-preprocessor fact about this project's toolchain.

---

## The decomp.me epilogue: encoding a line layout the scratch platform can't run

decomp.me compiles scratches with `cfe`'s internal preprocessor; it has no way
to invoke `acpp` as a separate pass. So a paste-ready scratch for a function
that depends on `acpp`'s line attribution can't just paste the original macro
form — the site would collapse it back onto one line and the residue would
return. The workaround: hand-expand the load-bearing macros and encode
`acpp`'s line layout explicitly with **12 `#line` directives** — one per
place `acpp`'s statement-to-line attribution needs to land somewhere physical
layout alone can't reach (`acpp`'s line counter can walk *backward* relative
to physical file position inside certain expansions, which a plain reflow of
the pasted text cannot reproduce).

Building that paste-ready bundle surfaced two more pitfalls, both worth
checking with the workbench's context lint (`decomp-workbench context lint`, and the hardened `check-scratch`) before
a paste, and both entered in [Troubleshooting](../docs/troubleshooting.md):

1. **The scratch context needs a trailing newline.** decomp.me concatenates
   `ctx` and the editable code verbatim, with no inserted separator. Without a
   trailing newline on `ctx`, the first line of code glues onto the last
   statement of `ctx` and `cfe` errors on the fused line — a paste failure
   that has nothing to do with the source being wrong.
2. **Don't redeclare what the context already declares.** The exported `ctx`
   for this function already declares the translation unit's file-scope
   statics; a paste that also declares them (e.g. because it was assembled
   from a raw source file rather than the actual export) fails on
   redeclaration.

---

## Meta-lessons

1. **"Invariant under everything I tried" is not the same claim as
   "impossible."** A compiler stage has more inputs than the ones that are
   easy to enumerate. This campaign varied the binary, the flags, and the
   instruction DAG exhaustively — three inputs — and never noticed that
   statement/line metadata from the preprocessor was a fourth, separate input
   until a tool that was not even trying to test that hypothesis exposed it
   by accident. Before declaring a stage's input space exhausted, write down
   every actual input to that stage, not just the ones with command-line
   flags.
2. **A tool that silently falls back to a default on an unrecognized flag
   manufactures false exhaustion proofs.** Eleven distinct `as1` model flags
   producing eleven identical outputs looked like "the model space is
   explored." It was "the flags were never accepted." Always confirm a sweep
   actually varied its parameter — check stderr, or better, make an invalid
   flag a hard error — before trusting a flat result as a negative.
3. **A control function is the cheapest wrong-turn detector you have.** Every
   compiler-configuration experiment in this campaign was checked against
   `spDraw` before it was allowed to count as evidence about `drawbitmap`.
   That single cheap check disqualified most of the era-archaeology sweep in
   the time it takes to run one comparison, instead of after a week of
   believing a wrong compiler was the answer.
4. **Cluster by output hash, not by how different the experiment felt.**
   Dozens of ostensibly different compiler configurations reduced to two
   facts: "attractor A" (the 59-word residue, byte-identical every time it
   appeared) or "broke `spDraw`." Naming and tracking that attractor turned a
   list of dozens of variants into a two-row table — and made it visible,
   eventually, that the search had stopped producing new information long
   before it stopped producing new-looking attempts.

## See also

- [Start here](../docs/START_HERE.md) — where this case study is linked from
  the `schedule-mismatch` guidance.
- [Field guide, lever 3: the `-g0` diagnostic](../docs/field-guide.md#3-the--g0-diagnostic)
  — the probe that narrowed this residue, and the ownership-scoping caveat
  that turned out to matter here.
- [Alternate authentic frontends](../docs/alternate-frontends.md) — the
  sibling campaign whose frontend-lineage finding this one corroborates.
- [Field notes, 2026-07-31](../docs/field-notes-2026-07-31-ssb64-drawbitmap.md)
  — the condensed, session-log form of this campaign.
- [Troubleshooting](../docs/troubleshooting.md) — the two decomp.me paste
  pitfalls from the epilogue, in the troubleshooting entry format.
