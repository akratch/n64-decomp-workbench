# IDO 5.3 laws from the Mickey wave-A lanes: evidence index

Thirty statements about IDO 5.3 that the Mickey's Speedway USA decompilation
measured on 2026-10-07/08, while closing near-matched functions in parallel
lanes. They are **candidates**, not laws of the [main page](ido-5.3.md): each
is listed here with where it was measured, what kind of evidence stands behind
it, whether this repository can reproduce it without the game, and the
L-numbered law it extends or overlaps. A candidate is promoted to the main page
only with a receipt and a falsification record of the kind that page requires.

This page follows the repository's rule for compiler-behaviour claims: record
the origin and the limits. It is written for a reader deciding how far to trust
one line before spending builds on it.

## Scope and limits

- **One compiler, one configuration.** IDO 5.3 at `-O2 -mips2 -G 0
  -non_shared`, as the project builds it. Nothing here has been tested on
  another IDO release.
- **One project.** Every "Measured by" cell is the Mickey's Speedway USA
  decompilation; the lane names are that campaign's own (`a-char`, `f-o008`,
  ...). Function citations are symbol-level, the exemption
  [CONTRIBUTING](../../CONTRIBUTING.md) records: a name, an address-derived
  symbol, a size. No instruction text, disassembly or extracted data from the
  game appears here, and the objects behind the receipts are not in this
  repository.
- **Mostly single functions.** A law whose class is T3 was observed closing one
  function. "Always" is not claimed for any of them.

## Evidence classes

The tiers are the main page's:

| Class | Meaning |
|---|---|
| **T1** | Read from a gated instrumented compiler's records (instrumented `uopt` CDX records, or an as1 scheduling trace), the instrumented build byte-identical to stock. |
| **T2** | Inferred from build outcomes across a sweep, census or round trip: more than one measurement, mechanism not read directly. |
| **T3** | A single observation, usually the edit that closed one function. Treat as a lead. |

**Synthetic** says whether this repository holds a reproduction built from
original C (`tests/fixtures/wave_a/`), measured with IDO 5.3 itself. A
reproduction is evidence that the behaviour is a property of the compiler and
not of one game function; its absence says nothing either way.

## The index

| # | Law (one line) | Measured by | Class | Synthetic | Related |
|---|---|---|---|---|---|
| W1 | A three-float local declared as an array lets a dot product be computed straight into its destination; the same value in a struct goes through a temporary and a copy. | Mickey, `a-char` (charControl) | T3 | none | — |
| W2 | In a leaf function a GBI-style macro's cursor local emits nothing but is still numbered and coloured; taking the display-list copy after the first packet moves the parameter's register. | Mickey, `a-ovl1` (overlay 83 match) | T3 | none | L106 |
| W3 | Priority colouring considered only webs with at least 22 interferences in the measured function; a local adding one interference re-ranked hoisted constants. | Mickey, `a-front` (func_80049B14) | T3 | none | L84 |
| W4 | Grouping a macro's two constant terms in parentheses draws one register; ungrouped draws two that as1 folds, shifting every later temporary. | Mickey, `a-front` (frontend match) | T3 | none | L149 |
| W5 | A call later in a block forbids only its argument registers for webs in that block; a call earlier in the block forbids `v0`. | Mickey, `a-o008b`, instrumented records | T1 | none | L58, L101, L142 |
| W6 | One variable reused for several loops keeps them in one callee-saved register and frees another for a different value. | Mickey, `a-shad` (shadowGenerate match) | T3 | none | L115, L131 |
| W7 | A declared, never-used local can be load-bearing for the frame; removing it moved homes. | Mickey, `a-shad` (func_80016890 match) | T3 | none (L99 has one) | L99, L121 |
| W8 | A `for` loop that advances a pointer in its increment clause reproduces a pointer-walk loop exactly; the subscripted form converts to a byte bound. | Mickey, `a-res1` | T3 | none | L113 |
| W9 | An `int` return type against a `long`-typedef return changes how an `\|\|` chain is merged into one register. | Mickey, `d-near` (main 28FCC match) | T3 | none | — |
| W10 | A redundant `& 0xFFFF` on an index spends a scratch-register draw that as1 deletes, shifting the ring. | Mickey, `d-near`, `e-res2` | T2 | none | L65, L149 |
| W11 | An assigned dead read into an existing local breaks a save tie; a bare dead read is inert. | Mickey, `e-res1` (textures match) | T3 | **inert half**: `zero_emission.c` | L37, L109 |
| W12 | Reading a global pointer through a word-typed lvalue instead of as the pointer changes evaluation order in its block, which as1 then lifts across a test. | Mickey, `e-ovl2` (overlay 1 match) | T3 | none | — |
| W13 | `v0` is pinned only in the block directly after an int-returning call; float results and arguments never write the integer mask. | Mickey, `f-o008`, instrumented records | T1 | none | L101, L105 |
| W14 | The high-half load of a hoisted global address is moved into an earlier block by as1 when its register is free; uopt does not decide it. | Mickey, `e-res1` | T3 | none | L110 |
| W15 | A web splits only when `totalsave <= bestcost`; block-count wrappers do not change that rule. | Mickey, `f-o069` (overlay 17), records | T1 | none | L139 |
| W16 | A no-op redefinition of a local to its own type is deleted, but kills uopt's forward substitution into a later use, so the earlier assignment becomes a real variable with its own web. | Mickey, `g-near` (overlay 68 match) | T3 | none | L104 |
| W17 | A matrix element addressed through a float pointer scaled by a row stride emits a shift then a multiply into a second scratch register; as1 folds the arithmetic but the draw survives. | Mickey, `h-4` (models match) | T3 | none | L77, L149 |
| W18 | A symbol assigned an expression is defined through a ring temp plus a copy as1 deletes; uopt substitutes the local away unless `x \|= 0` after the definition kills the substitution. | Mickey, `i-near` (overlay 17 match) | T3 | **control only**: `zero_emission.c` | L102, L150 |
| W19 | A dead-after-loop local assigned through a masked right-hand side, inside a block, creates a `v0` web that denies `v0` to the block's other value. | Mickey, `j-7` (overlay 8, 3,592-byte function) | T3 | none | L101 |
| W20 | A constant web also splits only when `totalsave <= bestcost`; making the constant span two calls produces a second constant web that can split and hold an argument register across a region. | Mickey, `j-6` (wakeUpdate match) | T3 | none | L128, L139 |
| W21 | Spill homes are handed out in web-number order, each web reusing a free non-interfering slot or taking a fresh one below; a late-substituted loop-bound symbol gets a late web number. | Mickey, `k-6` (wakeAllocate) | T3 | none | L63, L99, L121 |
| W22 | as1's delay-slot tie-break follows the physical line: a loop and its call on one line orders the float saves ahead of a reload so the reload fills the call's delay slot. | Mickey, `m-f1` (overlay 8 match) | T3 | none | L59 |
| W23 | as1's scheduling tie-break, censused over 3,744 tie events: largest `aftercycles`; then lowest source line; equal lines to the list head (most recently readied, initial list in emission order); the branch is held while two others are ready; the last non-branch node fills the delay slot. `besttime` is never a key. | Mickey, `m-f2`, as1 trace census | T1 | none | L59, L152 |
| W24 | Dead statements are deleted before code generation but still renumber webs; a variable inside an expression is always numbered before the expression. | Mickey, `m-3`, records at identical bytes | T1 | none | L106, L154 |
| W25 | uopt rewrites a loop's `<` exit test to an inequality unless the index symbol has a def between that loop and the **next** loop; a def after an intervening loop does not count. | Mickey, `n-f1` (func_80009414) | T2 | **yes**: `loop_exit_test.c` | L90, L153 |
| W26 | A store emitted after a may-alias load cannot pass it in as1, so a global read placed before a store group keeps the stores after it; an empty `if (var)` on a split web seeds the piece in that block. | Mickey, `n-f2` (func_80056DD8, score 41 → 30) | T3 | none | L97, L125 |
| W27 | An empty `if (param) {}` after an early statement keeps a parameter live from entry as a zero-emission interferer, changing a split piece's growth test. | Mickey, `t-lever` (func_80009414 match, found by the lever sweep from a split oracle) | T1 | **zero-emission half**: `zero_emission.c` | L97, L136, L161 |
| W28 | The driver assembles a `.s` with `-pic0 -noglobal`; with the C flags the text round trip is byte-identical to the direct path, so editing a `cc -S` stream and reassembling is a valid oracle for as1/ugen-order questions. | Mickey, `q-f` (corrects an earlier `m-4` note) | T2 | none | L70 |
| W29 | A division's trap checks split as1's scheduling blocks; operations emitted before the division are not substituted into later stores. | Mickey, `q-f` (overlay 20 stream) | T3 | none | — |
| W30 | An oversized frame can be the target reusing locals across phases: a pairwise scan that merges every same-typed pair and keeps merges leaving the object unchanged outside frame offsets fixed one. | Mickey, `q-2` (track 1291C, score 293 → 234, frame exact) | T2 | none | L119, L143 |

## The synthetic reproductions

Both are original C, compiled with IDO 5.3 (the decompals static
recompilation) at `-O2 -mips2 -32 -non_shared -G 0 -Xcpluscomm`, read back
with GNU objdump on 2026-10-08. Each file's header records the verdicts; only
the verdicts are recorded, never the instructions.

- **`tests/fixtures/wave_a/loop_exit_test.c`** (W25). Three two-loop
  functions. With no def between the loops, and with a def only after the
  second loop, the first loop's exit test is rewritten to an inequality. With
  `i = 0;` between the loops it stays a less-than test and costs one extra
  compare. This reproduces the "next loop" half of W25 exactly.
- **`tests/fixtures/wave_a/zero_emission.c`** (W11, W18, W27). Four functions of
  11 instructions each. A bare dead read and a `|= 0` keep-alive are
  byte-identical to the base; an empty `if (n) {}` is the same length but moves
  the post-call reload from `a0` to `a2`. That is the property the lever sweep's
  `boundary` lever relies on -- zero emission, nonzero allocation effect -- shown
  on code that is not the game's. It does **not** reproduce W27's split-growth
  mechanism, and the keep-alive here is a control: the shape has no
  substitution for it to kill.

## How these were used

The levers in [`sweep levers`](../lever-sweep.md) come from these rows: W11
(`dead_read`), W19 (`dead_masked`), W18 (`keep_alive`), W16 (`noop_redef`), W9
(`narrow_type`), W10 and W17 (`subscript`), W26 and W27 (`boundary`), W26
(`global_reread`), W25 (`zero_def`), W6 and W30 (`split_local`,
`merge_locals`), and W22/W23 (`reorder`, which reaches as1's line-keyed tie
break). The sweep's oracle is how W27 was found; that row is T1 because the
cell that matched was checked against the forced state's own records.
