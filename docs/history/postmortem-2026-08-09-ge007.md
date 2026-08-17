# Postmortem: GE007 `object_interaction` (2026-08-09)

> **Historical campaign record.** The source-error taxonomy remains useful,
> but command syntax and product coverage are current only in
> [Product status](../product-status.md) and the live command guides.

**Who this is for:** you have a function that is close — instruction count
exact, frame exact, most of the register file exact — with a small,
stubborn residual that has survived real effort. You suspect every
remaining row is "just allocation." This campaign's whole second half says:
check that assumption before you believe it. Eleven of its rows were not
allocation at all; they were places where the decompiled C was quietly
**wrong**, in eleven distinct, recognizable shapes. This page is written for
a reader who did not live the campaign — it is the taxonomy, not the diary.

**What this campaign was:** `object_interaction`, GoldenEye 007 (US),
`s32 object_interaction(struct PropRecord *)`, 4644 instructions (frame
`-1704`), compiled by IDO 5.3 at `-O2 -mips2 -Olimit 2000`. It started from a
97.93% community scratch and, across roughly 90 stages over two sessions,
closed to a byte-exact ROM rebuild — `.text` identical in all 4644
instructions, all relocations, and every register lane. The last session
alone went from 54 differing words to 0.

## The arc: 54 → 0 in one session

| Words remaining | Stage | What closed it |
|---:|---|---|
| 54 | *(session start)* | Tactical pause/resume state; every remaining row already attributed to a named, priced compiler decision |
| 54 → 52 | COMP-B | Declared a matrix-typed local the decompilation had never named at all (error 9) |
| 52 → 39 | KEY-B / KEY-C / KEY-D | A pure-function call with a frozen argument let one definition be handed to a dead donor at zero cost (the "keystone") |
| 39 → 34 | RED / RED-B | A redundant copy into a named symbol was deleted and the computing temp's live range extended over its uses instead |
| 34 → 19 | B4R / B4S / B4T | The temp-ring's true seven-coordinate phase state was found and supplied at the one line a four-coordinate model couldn't see |
| 19 → 15 | EYE | A local was given the ROM's true stack slot instead of sharing one with an unrelated value |
| 15 → 14 | C468D | A commutative float operand pair was reordered to match how IDO's front end actually canonicalizes `+=` versus plain addition (error 4) |
| 14 → 4 | B4U | Four previously-adopted "fixes" were re-tested from zero and found to be pure cost — deleting all four, not adding a fifth, was the fix |
| 4 → 2 | SEV | Two C locals that were secretly one ROM register were re-merged (error 10) |
| 2 → 2 | DON | Rebase; established the exact price floor of every donor-fusion route, closing the search space without closing the score |
| 2 → 0 | OMEGA | A single discarded-value statement, emitting zero instructions, supplied the one remaining allocator decision (error 11) — **byte-exact match** |

Two things about this arc are worth carrying into the next campaign. First,
**every large step came from correcting a source-level fact, never from
searching harder inside a fixed understanding of the source.** Second, the
smallest-looking step (14 → 4, deleting rather than adding) was a direct
consequence of *not* trusting an inherited lever's old price — see
[metric trap 5](../metric-traps.md#trap-5-an-inherited-set-of-levers-is-never-re-tested-against-zero).

## The taxonomy: eleven decompiler errors, and how to catch each one

None of these are allocator behavior. Each is a place where the decompiled
C said something different from what the original programmer actually
wrote, in a way that happened to still compile and still run correctly —
which is exactly why each one survives casual review. The oracles that
found them were, in order of how often they paid off: reading the ROM's own
instruction stream directly, a sibling game's independently matched
decompilation of an evolved version of the same code, and the project's own
repository body reused character-for-character. None of the eleven were
found by search.

### 1. Invented locals

A local exists in the decompiled C with no counterpart in the true source —
usually a name given to a sub-expression that **other, nearby statements
already spell out in full**. IDO's own common-subexpression elimination
rebuilds the identical cache internally when the expression is repeated, but
colours it as a compiler temp (a caller-saved register), where a real,
named local takes an argument-register colour. The two are semantically
identical and register-different.

**Detection:** a local whose only definition is a re-derivable member-access
chain, with sibling reads of the *same* chain written as full expressions
elsewhere in the same region, is suspect — inline it and check whether the
register class changes.

### 2. Over-merged locals

One decompiled local is used to represent values from **two mutually
exclusive control-flow arms** (commonly two `else if` branches that can
never both execute). Its occurrence weight is the sum of both arms', and it
out-competes the arm-specific locals it should instead be split into for a
register.

**Detection:** a local referenced only inside two mutually-exclusive arms,
competing for a register against an arm-local value, is a merge candidate —
split it by donating one arm's occurrences to an *already-declared*
same-typed sibling used the same way in that arm (a new declaration is
never frame-neutral; a donation to an existing one usually is).

### 3. Wrong scope

A cluster of locals is declared at the wrong lexical scope — inside a block
when the true source declared them in the enclosing function scope, or vice
versa — which changes which values compete for which registers and in what
order they are claimed.

**Detection:** when a residual is a tight cluster of register/frame rows
around a group of related locals, try hoisting (or lowering) the whole
group into the enclosing scope, in their existing relative order, before
touching any individual one.

### 4. Wrong operand order

IDO canonicalizes a commutative operation's operand order from the
**expression tree's shape**, not from how the source spells it: `x += a * b`
and `x = c + (a * b)` are different trees and load their operands in
different orders even where the underlying arithmetic is the same.

**Detection:** if a residual is a same-instruction-count, swapped-operand
pattern on a commutative op (`add`, `mul`, `and`, `or`), try both the
compound-assignment and the fully-expanded spelling before spending a
variant on allocation — this is a zero-instruction-cost fix when it lands.

### 5. Wrong statement order

Two structurally parallel, mutually independent blocks of statements (for
example, two symmetric normalization sequences) are present but were
transcribed in the wrong relative order.

**Detection:** when a residual looks like a clean transposition of two
whole, self-contained statement groups rather than a scramble of individual
instructions, try swapping the *groups* — not individual statements inside
them — before assuming an allocator cause.

### 6. Unmasked increment

A counter is stored **unmasked** in the true source, with the mask applied
only where the value is later compared or read; the decompilation instead
masked the counter at its own increment/store site.

**Detection:** if a stored counter is masked at its point of increment
rather than at each of its read sites, try moving the mask to every read
site and storing the raw increment instead — verify semantics first, since
the two are equivalent only for values that never wrap past the masked
range.

### 7. Mistyped declaration

A kept-but-unused ("dead") declaration — needed only to hold a stack slot in
place, never itself read — has the **wrong declared type** for the value
the true source actually held there, which can shift frame layout or a
neighbour's register class without ever showing up as a used-variable diff.

**Detection:** when a stack-offset or register-class residual survives
every reordering of the *used* variables nearby, check the declared type of
every kept-but-dead declaration in the same region, not just whether it is
present.

### 8. Pointer-arithmetic artifacts

A raw pointer-arithmetic expression — address-of-member plus a byte offset,
or a pointer cast through an unrelated type — stands in for what the true
source wrote as an ordinary named-member access, or the reverse. The two
are value-identical and allocator-different, because a pointer computed
this way can change whether the underlying storage is treated as
address-exposed.

**Detection:** respell every pointer-arithmetic pun near the residual as its
structurally equivalent named-member form (and the reverse, where a named
form is already present), and diff the object — a change proves the
*spelling*, not just the value, was load-bearing.

### 9. Missing Mtxf local

A whole matrix-typed local was never declared in the decompiled C at all.
Its storage was reached only through a raw pointer pun anchored off a
neighbouring, unrelated local's address — and a placeholder the
decompilation had invented to explain one otherwise-unexplained word turned
out to be that matrix's own top word.

**Detection:** when a pointer pun's offset lands inside the byte range of a
plausible fixed-size engine type (a matrix, a vector) that nothing nearby
declares by name, declare it. Corroborating signals — the ROM's own
instruction shape at the site, the true source's declaration position
(when available), and any invented placeholder whose role the new
declaration subsumes — tend to confirm this one all at once rather than
gradually.

### 10. Split machine temp

Two different C locals were assigned to values that the ROM computed into
and read from the **same physical register**, at two different, disjoint
points in the function — literally one machine temporary, split into two
source names by the decompilation.

**Detection:** if two locals' names both encode the same physical register
(a common decompiler naming convention ties a generated name to the
register it was recovered from) and their live ranges never overlap, try
renaming the later one's references onto the earlier symbol. The rename is
legal exactly when the two live ranges are disjoint — check def-to-last-use
spans before adopting.

### 11. Zero-footprint discarded read

The true source contains a statement that reads a value and discards it —
`if (v != 0.0f);` or equivalent — which compiles to **zero instructions**
but still changes the register allocator's decision about a nearby web (see
[the p1 decision arithmetic](../p1-decision-arithmetic.md#chargeb--a-store-placement-charge-not-a-loop-charge)).
Because it leaves no bytes in the object, it is invisible to any method that
works from the disassembly alone.

**Detection:** when a function is byte-exact under a *forced* allocator
decision (an oracle proves the target machine code is reachable at all) but
not under an unforced, stock compile, look for a missing zero-footprint
statement before looking for a mis-spelled one — and check any
independently matched decompilation of a related or evolved version of the
same routine for the same idiom before assuming the construct has to be
invented from first principles.

## What made this campaign different

Every large win in this campaign's second half came from a source-truth
correction found by reading, never from search — and the three richest
sources of source-truth, in the order they actually paid off, were the
ROM's own instruction stream (never wrong, always available, hardest to
read), a sibling game's independently matched decompilation of an evolved
version of the same function, and the project's own repository body reused
character-for-character where a nearby function had already been solved.
None of those three is a compiler mechanism, and none of them is exhausted
by this campaign — they are exactly where to look for the twelfth error, on
this function or the next one.

The one discipline that made the taxonomy above trustworthy rather than
folklore: every claim on this page has a receipt — an object hash, a
before/after instruction count, or a forced-oracle build — behind it
somewhere in the campaign record. Where this campaign's own internal
numbering collided or a claim was later corrected, the record of the
correction was kept rather than quietly overwritten; see
[Compiler laws: IDO 5.3](../compiler-laws/ido-5.3.md) for the formal version of
that discipline, applied to the compiler-mechanism findings this same
campaign produced alongside the error taxonomy above.

## See also

- [Compiler laws: IDO 5.3](../compiler-laws/ido-5.3.md) — the p1/uopt mechanism
  findings from the same campaign, laws L26–L48.
- [The p1 decision arithmetic](../p1-decision-arithmetic.md) — the allocator
  formula behind errors 9–11 and the campaign's closing move.
- [Metric traps](../metric-traps.md) — the scoring and pricing mistakes that
  cost real stages, independent of the source-error taxonomy above.
- [Postmortem: dp64 core campaign day](postmortem-2026-07-29-dp64.md) — the
  same "what worked / what cost us" discipline applied to a different
  campaign and game.
