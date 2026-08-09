# Source probes: same-value ranges and zero-footprint constructs

**Read this if:** the object is nearly right, the residue is allocation-shaped,
and you are about to go looking in the compiler. Two of the questions worth
asking first are about the C, and neither leaves a mark in the disassembly.

| Command | Question |
|---|---|
| `probe-equiv` | are these two reads of a local the **same value**? |
| `probe-deadread` | where can a statement that **emits nothing** change the allocation? |

Both are **probes**, not proofs. Each report ends with the list of things it
does not know, and the list is short enough to read.

## `probe-equiv` — the check that costs five stages when nothing names it

One campaign's closing lever was a source fact: a local whose address never
escapes cannot be written by any callee, so between two of its definitions its
value is fixed, and two expressions built from reads in that span are equal
however they are spelled. Five stages searched the register allocator for a
decline the pass's own arithmetic makes impossible. The answer was one `grep`
and one brace match, and no tool named the check, so nobody ran it.

```sh
decomp-workbench probe-equiv examples/fixtures/value-equality.c --variable sp4B8 --at 11 --at 13
```

```text
value equality: examples/fixtures/value-equality.c variable=sp4B8
declared at line 2; 2 definition(s); 4 read(s)
sp4B8's address is never taken in this file, so no callee can write it: a call between two reads cannot have changed the value
range defined lines reads note
1 7 7..9 1 same value at every read
2 10 10..19 3 spans a loop body: a back-edge can carry a definition
lines 11 and 13: SAME-VALUE
no definition between them, and no callee can write a local whose address never escapes
```

Without `--at`, the report is the range table alone: the maximal spans between
consecutive definitions, with the reads in each. Every read inside one range is
the same value as every other read in it.

The argument has exactly one load-bearing premise, and the report states it on
its own line: **the address is never taken**. One `&v` anywhere in the file and
the purity half is gone, the line says so, and every pairwise verdict becomes
`NOT-PROVEN`.

A range is flagged rather than trusted when a label, a `goto`, or a loop
back-edge is inside it, because textual order has stopped describing the
control flow there.

## `probe-deadread` — the construct no object diff can point at

A statement that reads a local and drops the value — `if (v != 0.0f);` — emits
**zero instructions** and still adds an occurrence to the variable's web. That
occurrence can be exactly what drives the web memory-resident, which is a real
allocator lever with no code cost. Because nothing is emitted on either side,
no disassembly diff will ever point at one; eleven stages of one campaign did
not find it, and a sibling game's independently matched decompilation of the
same routine carries the idiom in the same place.

```sh
decomp-workbench probe-deadread examples/fixtures/value-equality.c --variable sp4B8 --limit 3
```

```text
dead-read probe: examples/fixtures/value-equality.c variable=sp4B8
spelling footprint note
if (V != 0.0f); 0 value-guarded; preferred
if (V); 0 or +2 bare; merges with a neighbouring empty guard and can cost its bc1f+nop pair
V = 0.0f; 0 INERT: a dead store is eliminated before it can be an occurrence (986 of 999 positions, zero kills)
line depth loop reached-by statement
```

Three things the table encodes, each of them a measurement rather than a
guess:

- **The value-guarded spellings are the ones to build.** The bare `if (v);`
  merges with a neighbouring empty-body guard and costs that guard's
  `bc1f`+`nop` pair — which reads as "the lever cost two instructions" when it
  is the spelling that cost them.
- **A dead store is not a dead read.** `v = 0.0f;` at all 999 positions
  produced zero kills: a store that dead-code elimination removes never becomes
  an occurrence. It is the *read* that survives into the occurrence list.
- **Inside a loop is a different experiment.** The same construct that costs
  nothing outside a loop emitted real code inside one in every case measured,
  so loop positions are marked `LOOP` and ranked last.

### Which positions count

By default a position is a candidate only when a definition **structurally
reaches** it: the definition's enclosing blocks are all still open, so the read
is a read of a value every path assigned. `--reach textual` keeps every
position after the first definition line — the wider set the campaign's own
sweep used, and where several of its kills were found, because a read of a
variable a branch may not have written is still a zero-footprint allocator
probe. Rows in the wider set print their reaching definition in brackets.

### Building the sweep

The workbench does not own your build, so it stops at the source:

```sh
decomp-workbench probe-deadread work.c --variable sp4A0 --write variants/
```

writes one variant per candidate, named for the line it edits, ready for
whatever sweep driver the project already has. `--spelling` chooses which form
is inserted. Score the results with `decomp-workbench score --slot` (the load
and store counts at the slot are the screen that separates a kill from a
relocation) and read the allocator side with
[`trace-cascade`](cdx-cascade.md).

## `slots` — what a donor costs, without a build

Two of the questions that surround these probes are about the object, not the
source: how many rows touch a candidate donor's stack slot (that count *is* the
donor's price), and whether a slot is one variable or a pun.

```sh
decomp-workbench slots examples/fixtures/target.objdump --dumps
```

`slots` counts, per frame offset, the loads, the stores, the address-takes, the
access widths that reach it and the registers that carry it. A slot reached by
two widths is marked `PUN`: that is one storage location under two spellings,
and the allocator keys webs on storage rather than on the C name.

It reports what the rows do. It does not claim which C local lives at a slot,
because nothing in an object says so. The measurement that does answer that is
a build:

```sh
decomp-workbench slots target.o --source work.c --volatile-probe variants/
```

writes one variant of the source per local, that local made `volatile` so the
compiler must keep it in memory. Build each one, re-run `slots`, and the offset
whose traffic appears or grows is that local's stack home.

## See also

- [The p1 decision arithmetic](p1-decision-arithmetic.md) — why an occurrence
  with no instruction cost still moves the decision.
- [The allocator decision cascade](cdx-cascade.md) — reading what the change
  did to the allocator.
- [Metric traps](metric-traps.md) — the chapter on statements that cost zero
  instructions and are still load-bearing.
