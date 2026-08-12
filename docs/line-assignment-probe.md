# The line-assignment probe

**You have a `schedule-mismatch`. Same instruction multiset, same register
allocation, just a different order. You already tried `-g0` (field-guide
lever 3) and it didn't collapse. You have tried every compiler era you can
get your hands on and every one of them produced the identical bytes. You are
out of compiler archaeology to do, and you are about to start guessing at
source respellings with no idea which one is worth trying.**

There is one more question to ask before that, and it costs one variant:
*does the position of your statements on physical lines participate in
scheduling at all?* If it does, the fix is a preprocessing change, not a
source change, and every hour spent respelling expressions was never going to
find it. If it doesn't, you have just ruled out an entire mechanism for free
and can stop suspecting it.

`decomp-workbench probe-lines` runs that experiment for you.

- [1. The experiment, and why it is honest evidence](#1-the-experiment-and-why-it-is-honest-evidence)
- [2. Running it](#2-running-it)
- [3. The three verdicts](#3-the-three-verdicts)
- [4. Scoring against a target](#4-scoring-against-a-target)
- [5. Why line assignment can matter at all](#5-why-line-assignment-can-matter-at-all)
- [6. The acpp recipe](#6-the-acpp-recipe)
- [7. The drawbitmap numbers](#7-the-drawbitmap-numbers)
- [8. Known approximations](#8-known-approximations)
- [9. The `--tie` variant: from verdict to fix](#9-the---tie-variant-from-verdict-to-fix)

---

## 1. The experiment, and why it is honest evidence

Take the preprocessed `.i` that fed the compile you are trying to match.
Find the long macro-expansion line where the compiler's suspect statements
live - the preprocessor already flattened whatever multi-line macro produced
them onto one physical line, often hundreds of characters wide. Insert a
newline after each `;` on that line. Do not touch a single token: the source
text, read as a stream of characters with whitespace removed, is byte-for-byte
what it was before.

Recompile. If the schedule moves, a **token-identical** change moved it, so
the mechanism cannot be anything about *which* tokens you wrote - it can only
be about which physical line each statement's tokens were assigned to when
the compiler read them. That is the whole argument, and it is the reason this
probe is worth running before any source respelling: a source edit that
changes tokens can never cleanly separate "this moved because of what I
wrote" from "this moved because of where I wrote it," and this one does.

The probe runs a second variant as a control, for the same reason
`docs/pass-replay.md` insists on an unedited calibration cell before trusting
an edited one: if a completely inert change - blank lines prepended at the
very top of the file, moving every line number down by a fixed amount but
regrouping nothing - *also* moves the object, the compile itself is not
reproducible under trivial padding, and neither result is trustworthy. That
result is itself useful: it says stop, before spending any more variants on
this compile command at all.

## 2. Running it

You need the preprocessed translation unit: `cc -E unit.c > unit.i`, or
whatever an IDO-style driver retains alongside its normal compile (commonly
`-K`). You need the same compile command that produced the object you are
diagnosing, with `{input}` and `{output}` standing in for the source and
object paths - the same placeholder convention as `pass-diff` and
`replay-as1`.

```sh
decomp-workbench probe-lines unit.i \
  --compile-command '/ido/cc -c -O2 -mips2 -Xcpluscomm {input} -o {output}' \
  --function drawBitmap
```

`--function` windows the comparison to one symbol's byte range, read from the
compiled object's own ELF symbol table - no objdump needed. Omit it to
compare the whole `.text` section positionally, which is the only option
when the function you care about is `static` and IDO stripped (or never
emitted) its symbol-table entry.

The command compiles three variants - `baseline`, `split-statements`, and
`global-shift` (a fourth, `tie`, appears when you pass
[`--tie`](#9-the---tie-variant-from-verdict-to-fix)) - and prints something
like:

```text
input: unit.i
function: drawBitmap
split-threshold: 400 char(s)   shift-lines: 20
  baseline          words=214    window=.text[drawBitmap] (856 byte(s) at +0x120)
  split-statements  words=214    window=.text[drawBitmap] (856 byte(s) at +0x120)
  global-shift      words=214    window=.text[drawBitmap] (856 byte(s) at +0x120)
split-statements vs baseline: 115 word(s) differ
global-shift vs baseline:     0 word(s) differ
verdict: line-sensitive
LINE-SENSITIVE: statement line assignment participates in scheduling. next: field-guide lever 23 (preprocessor line assignment) — follow the copyable acpp recipe in docs/line-assignment-probe.md with this translation unit's exact defines, include paths, and compiler flags
next: retarget one statement: re-run with --tie STATEMENT=LINE ...
next: add --target-object/--target-bytes so the tie is scored ...
run directory: .decomp-workbench/probe-lines/probe-lines-a1b2c3
```

The `next:` lines are the routing, and they change with the result: an
unscored probe is told to score itself, a scored tie is told whether that
assignment was the one, and a `NOT line-sensitive` verdict is sent back to
`decomp-workbench guide g0-schedule-probe` rather than left at a dead end.

Every variant's source, object, and full compiler streams are retained under
the printed run directory - on success and on failure, per
[principle 14](principles.md) (cleanup must be recoverable; it must not
silently delete evidence a reader might need). `--split-threshold` (default
400 characters) controls which physical lines are reflowed; `--shift-lines`
(default 20) controls how many blank lines the control inserts. Pass `--json`
for the same report as one schema-tagged document
(`decomp-workbench-line-probe-v1`): `split_word_diff`, `shift_word_diff`,
`verdict`, `message`, `next_steps`, `target`, and - when `--tie` was used -
the `ties` that defined the experiment and the `tie_word_diff` it produced.
The report records every knob it was run with, so a run is reproducible from
its own JSON.

## 3. The three verdicts

**`LINE-SENSITIVE`** - the reflow moved the object and the control did not.
Statement line assignment participates in scheduling for this function under
this compile command. The next step is field-guide lever 23 (preprocessor
line assignment): stop respelling source and go fix how source lines get
assigned to statements before the compiler ever sees them. Section 6 below is
the recipe.

**`NOT line-sensitive under this reflow`** - neither variant moved. This is
also a real result: the residue is owned somewhere else entirely - the
compiler binary, a flag, or instruction selection - and this probe has
correctly taken preprocessor line assignment off your list of suspects
without costing you a single source respelling. Do not read this as "line
assignment can never matter" for a *different* function or a different
compile command; it is scoped to the input you just ran, the same way the
`-g0` diagnostic's negative result is scoped in
[field-guide lever 3](field-guide.md#3-the--g0-diagnostic).

**`NONDETERMINISTIC COMPILE`** - the control moved. A change that adds
nothing but blank lines at the top of the file must never alter the compiled
object, so if it did, the compile command itself is not reproducible under
trivial padding, and *every* verdict this probe could report is unearned
until that is fixed. Common causes: an embedded timestamp, a random seed, an
absolute path or line number baked into debug metadata, or an uninitialized
padding byte the compiler happens to read. Fix the compile command first;
there is nothing to learn from `probe-lines` until the control passes.

## 4. Scoring against a target

If you already have the target object - the ROM-verified bytes you are
trying to reach - `probe-lines` can score every variant against it instead of
just against baseline:

```sh
decomp-workbench probe-lines unit.i \
  --compile-command '/ido/cc -c -O2 -mips2 {input} -o {output}' \
  --function drawBitmap \
  --target-object drawbitmap-target.o
```

(`--target-bytes FILE [--target-offset N]` does the same thing against a raw
binary window - a ROM extract, for instance - instead of an object's ELF
`.text`.)

The report adds one line per variant:

```text
target: baseline differs from target at 59 site(s)
target: split-statements moved toward target at 48 site(s), away at 3, unchanged at 8 (of 856 compared position(s); 14 still differ)
target: global-shift moved toward target at 0 site(s), away at 0, unchanged at 856 (of 856 compared position(s); 59 still differ)
```

`toward` is how many of baseline's mismatched words the variant now matches;
`away` is how many previously-matching words it broke; `unchanged` is
everything else, and the three always sum to the compared window's total word
count. This is the number that actually decided whether a probe result was
worth pursuing on the drawbitmap campaign: not "did *something* move," but
"did most of the wrongness move in the right direction."

## 5. Why line assignment can matter at all

IDO's front end (`cfe`) records a per-statement line number as it parses, and
that number survives into the retained ugen listing as a `.loc`-adjacent
attribute even when you are not asking for `-g3` debug output. `uopt` and
`ugen` use statement-line identity as a scheduling boundary: two expressions
IDO believes belong to the *same* line are eligible to interleave; two it
believes belong to *different* lines are not, independent of whether the
final object embeds any debug records at all. This is `-g0`'s sibling
mechanism, and the reason lever 3 is not the end of the story: `-g0` asks
whether *emitted* debug metadata constrains the assembler; this probe asks
whether the front end's own internal line bookkeeping constrains it, which
survives `-g0` intact.

A macro expansion is exactly where this goes wrong for a decompilation
project. The macro's *definition* spans several source lines; the
preprocessor's *expansion* of one invocation collapses every one of those
statements onto the single physical line where the macro was invoked - unless
the preprocessor deliberately re-attributes them. `cfe`'s statements are
then, quite correctly by its own bookkeeping, all "the same line," and the
scheduler treats them as one interleaving-eligible group instead of the
several distinct groups the macro's author saw when they wrote it.

**The dial is coarser than a macro expansion, and this cuts both ways.** Any
two statements sharing a *logical* line share a line number - and a logical
line is what survives backslash-newline splicing, so `\`-joined physical lines
and several statements on one physical line are the same lever. That is
[field guide lever 25](field-guide.md#25-line-number-ties-by-splicing), and it
means a natural layout's statement line numbers are non-decreasing but *not*
strictly increasing.

**Caution: scope every impossibility you conclude from a bisection.** When you
sweep a statement's line number and find a plateau, what you have measured is
that plateau *under the statement order you swept and the physical layout you
swept it in*. Neither is a property of the language. A published claim from
this project - "no natural layout can express what this function needs, only
`#line` can" - was falsified within a day by someone who moved one statement
and spliced a block onto the next one; both halves were already in the
campaign's own variant matrix, filed as "inert" and "dead end". Write the
qualifiers down next to the conclusion, or do not draw the conclusion. See
[Case study: SSB64 `unref_800036B4`](../case-studies/ssb64-unref-800036B4.md).

## 6. The acpp recipe

IDO ships its own external preprocessor, `acpp`, and it does something GNU
cpp and most modern preprocessors do not bother with: when a macro expansion
produces several statements, `acpp` attributes them to the *successive* lines
of the macro's multi-line invocation in the caller, rather than collapsing
them all onto the invocation's single starting line. Preprocess with it
instead of the default, and `cfe` sees the statement-line boundaries the
macro's author actually wrote:

```bash
# Replace these example arrays with the translation unit's exact arguments.
cpp_flags=(-DVERSION_US -Iinclude)
compiler_flags=(-O2 -mips2)

acpp "${cpp_flags[@]}" file.c > file.i
cc -c "${compiler_flags[@]}" file.i
```

This is field-guide lever 23 (preprocessor line assignment). It is the fix a
`LINE-SENSITIVE` verdict points at, and it is a preprocessing change, not a
source change - the C is exactly as it was; only which tool flattened it, and
how, is different.

## 7. The drawbitmap numbers

This probe exists because of one SSB64 `drawbitmap` residue: a
`schedule-mismatch` of 59 words, the same instruction multiset, the same
register allocation, invariant under *every* IDO era tried against the same
source and flags. `-g0` did not collapse it. The line-assignment probe did:
splitting the suspect macro-expansion statements onto separate physical lines
moved the schedule from 59 diff words to 115 - not fewer, *more* - but 48 of
the original 59 mismatched sites flipped to agree with the target. That
lopsided, mostly-correct movement from a token-identical edit is what proved
the residue was owned by statement line assignment rather than by which
compiler binary was invoked. Re-preprocessing with `acpp` instead of the
project's default preprocessor, so that the macro's statements landed on the
lines their author wrote them on, took the residue to zero: a byte-exact
match, reproduced identically across every IDO era tested against the same
`.i`. Hours of comparing compiler binaries would have been spent chasing a
mechanism one blank-macro-expansion probe ruled in on the first try.

## 8. Known approximations

The `split-statements` tokenizer is small and deliberately honest about its
scope, not a C parser:

- It tracks string and character literals, `//` and `/* */` comments, brace
  depth, and `for (...)` headers (so `for (;;)` and multi-clause `for`
  headers are never split). It does not evaluate preprocessor directives,
  because it runs on an already-preprocessed `.i` and none should remain
  other than `#line` markers, which it passes through unexamined.
- Trigraphs and backslash-newline continuations *outside* a string or
  character literal are not special-cased; a preprocessor normally resolves
  both before emitting a `.i`, so real inputs should not exercise this gap.
- A string prefix such as `L"..."` or `u8"..."` is handled correctly only
  because the prefix letters are ordinary identifier characters that do not
  themselves open the literal - the tokenizer never needs to recognize the
  prefix as such.
- Only physical lines longer than `--split-threshold` are reflowed, matching
  the shape of a macro-expansion line in practice: an ordinary hand-written
  statement line is short and is left untouched even if it holds more than
  one `;`.

## 9. The `--tie` variant: from verdict to fix

`--tie STATEMENT=LINE` (repeatable) compiles a fourth variant that wraps the
statement on 1-based input line `STATEMENT` in a `#line LINE` / restore pair,
reassigning only that one statement's recorded line number. Where
`split-statements` asks *"does line assignment own this residue?"*, `--tie`
asks the follow-up that closes campaigns: *"which line does this statement
need?"* — typically the line of the statement the scheduler must not separate
it from (the target order's neighbor).

A `LINE-SENSITIVE` verdict routes here on its own: the report's `next:` lines
name the flag, and once a tie is scored they say whether that assignment was
the one.

Worked example (ssb64 `func_ovl8_80379070`, accom-hybrid rig): three m4-arm
defs each scheduled one slot early; tying each def's line to its store-`if`
head's line moved 4 sites toward the target and 0 away in one probe run:

```sh
decomp-workbench probe-lines unit.tu.c \
  --compile-command 'accom-hybrid.sh {input} {output}' \
  --symbol func_ovl8_80379070 --target-object baseline.o \
  --tie 83=88 --tie 178=183 --tie 273=278
```

Both numbers address the **original** input, so several ties compose without
any arithmetic on your side: `--tie 178=183` means the same thing whether or
not `--tie 83=88` is also present. The statement number must name a real,
non-blank line that is not itself a preprocessing directive — those carry no
statement for `cfe` to number, and the probe refuses them rather than
compiling a variant that changed nothing. The assigned number is deliberately
unbounded: the line a statement *needs* may sit past the end of the file.

Score it. `--tie` on its own reports how many words moved, which is not the
same question as whether they moved the right way; with `--target-object` (or
`--target-bytes`) the report adds the tie's toward/away/unchanged counts
alongside the other variants, and that ratio is the result worth acting on.

Two caveats, both about what a physical line is:

- The `#line` pair is inserted *between* physical lines, so a tie whose
  statement spans several lines retargets the first line and leaves the rest
  where they were. Tie the line the statement starts on, and check the
  variant source the run directory retained.
- `--tie` composes with `--split-threshold` only indirectly: the tie variant
  is generated from the untouched baseline, not from the reflow. To tie a
  statement the reflow created, run the reflow first and probe its output.

The tie is a probe, not necessarily the published source: once it confirms
the mechanism, hunt the natural spelling that carries the same line
assignment (for-increment-clause placement and lever 25 splices are the two
recorded families). `decomp-workbench guide 25` is that page.

See also:

- [Field guide lever 3](field-guide.md#3-the--g0-diagnostic) - the `-g0`
  diagnostic, this probe's sibling ownership test.
- [Field guide lever 25](field-guide.md#25-line-number-ties-by-splicing) - the
  same variable turned from natural source, with no preprocessor swap and no
  `#line`.
- [Retained-pass replay](pass-replay.md) - the same "one targeted, reversible
  change plus a mandatory unedited control" method, one pass boundary later.
- [Principles](principles.md) - measuring the owning pass, and treating a
  forced/probed result as a causal test rather than a source match.
