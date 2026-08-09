# Shift-tolerant diffs and the ring phase

Two questions come before every metric a comparison reports, and a
position-indexed comparison answers both of them wrongly:

1. **Are these two streams even the same length, and if not, what did the
   candidate add?** One inserted instruction shifts every later row against its
   neighbour, so an object that is byte-exact apart from one extra `nop` reports
   a four-figure mismatch count.
2. **Is the residual a mistake, or a renaming?** A float-heavy function is often
   not wrong but *rotated*: the same values in the same scratch ring, starting at
   a different register. Whole regions differ in every row while being one
   renaming away from exact.

`align` answers the first. `phase` answers the second. Neither replaces
`compare`; they say what `compare`'s numbers are numbers *about*.

## `align` — the edit script, not the shift

```sh
decomp-workbench align-dumps examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump --symbol blockSum
```

```text
rows: target 14 candidate 15 (+1)
edit script (aligned on opcode): replaced 0 inserted 1 deleted 0
=> 1 instruction(s) away (1 edit + 0 residual)
a position-indexed comparison charges 11 rows for the same object: ...
shift shape: insertion-only, so a banded scorer can compensate for it
cuts (target rows the candidate inserts at): [5]
```

The two readings of that object are "one instruction away" and "eleven rows
wrong". Only the first is true, and eleven separate stages of one campaign
abandoned candidates of exactly this shape on the second.

The headline number is `rows_away` — the edit script plus the rows the aligner
paired that still differ. Pass several candidates for a census, one line each,
ordered by it:

```sh
decomp-workbench align target.o cand-a.o cand-b.o cand-c.o
```

Options worth knowing:

| Option | What it is for |
| --- | --- |
| `--align-on {opcode,normalized,exact}` | how much of an instruction the aligner sees. `opcode` (the default) survives a register renaming, which is what makes the row pairing usable by a scorer |
| `--window LO..HI` | tally how many insertions land before and inside a named row range |
| `--blocks N` | how many edit-script blocks to quote (default 20) |
| `--disassembly-cache DIR` | reuse disassemblies across runs; see below |

### Three things `align` does that a hand-rolled version will not

**The two objects' relocation rows stay in separate spaces.** A row whose word
the linker fills cannot be compared, on either side — but a target row is masked
by the *target's* relocations and a candidate row by the *candidate's*. Merging
them into one set and testing both indices against it over-masks near a shift
boundary; it silently dropped two genuine mismatches from one campaign's
published number.

**Branch destinations are renormalized through the pairing.** A local branch
encodes an absolute row number, so an insertion above it changes the word
without changing the code. The candidate's destination is mapped back into
target row space before the rows are compared.

**The cut list is derived.** `cuts` is the list of target rows the candidate
inserts at, read off the edit script rather than off a screen by a human, and
`insertion-only` says whether the shift is of the compensable shape at all.

## `phase` — the ring phase is a vector, and it names its coset

```sh
decomp-workbench phase-dumps examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump --symbol animStep \
  --ring '$t6,$t7,$t8,$t9' --slots 'head=0..11,tail=12..23'
```

```text
slots: 2 named, partitioning target rows 0..23 with no holes
head 12 0 7 id 0 0
tail 12 1 6 t9/t6/t7/t8 0 6
total 24 1 13 MIXED 0 6
phase vector: head=id tail=t9/t6/t7/t8
free=0 [COSET tail=t9/t6/t7/t8; positional 6]
COSET: 1 slot(s) sit at a non-identity ring coset ...
```

Read that as: the first half of this function is byte-identical, and the second
half would be byte-identical *if the whole ring were renamed* — which it has not
been. `free=0` is what a ring-quotienting scorer prints; `positional 6` is what
the object scores as written. One campaign's headline "39 → 29" was 1045
positional rows, and three stages recorded ring-flipped objects as wins because
no screen carried the coset. The quotiented number is therefore never printed
alone.

### Slots must partition the object

A slot table is a claim about which rows the report accounts for. The scorer
family this command replaces named eight ranges of a 4641-row object that
between them left 105 rows unnamed, so a mismatch landing there was absent from
every total — one candidate scored `RAW=1` with two real mismatches. Here a hole
is an error that names the rows:

```
error: the slot table does not partition rows 0..4640:
  - these rows belong to no slot, so a mismatch there would be absent from
    every total: 3285..3387 (103 row(s)), 3403..3404 (2 row(s))
```

The default is one slot covering the whole object, which cannot have a hole.
`--slots-from FILE` reads the table one `NAME=LO..HI` per line, because a
newline-joined shell variable does not word-split under zsh and the whole list
arrives as a single argument.

### The phase is per slot

The state is one coset for each slot, not one permutation for the object: one
campaign's eight named sub-zones each rotated independently. `phase vector:`
prints them in order, and `--detail` collapses each slot's residual into runs,
which is the sub-window reading a localized win is invisible without.

### A slot with no evidence is not identity

A slot whose rows all match (or all fail) under every coset says nothing about
the phase, and gets `no-evidence` rather than the first permutation that happens
to win. Classifying a small slot in isolation is how one campaign dropped a
working construct from every catalogue it kept. `--min-evidence N` raises the
bar; `--context OBJECT` scores each slot at the coset a supplied context
measures, so a construct is priced in composition rather than alone.

### Guards

| Option | What it refuses |
| --- | --- |
| `--require-ni` | a candidate whose real instruction count is not the target's. Without it the count difference is flagged and the rows are paired through the alignment anyway |
| `--base SOURCE` / `--require-base SHA256` | a table of objects built from a base other than the one you pinned |
| `--baseline OBJECT` | nothing — it adds the healed and broken row counts, because "healed nine, broke four" and "the score moved by five" are different facts |

## The disassembly cache

Both commands accept `--disassembly-cache DIR`. There is no default directory:
a scorer that defaults to one scores whatever is in it, and one campaign's batch
scorer defaulted to a *later* stage's object directory.

An entry is trusted only when it proves it is a complete disassembly of the
object on disk — its SHA-256 must match, its declared row count must match what
the body parses to, and for a whole-section dump it must also match the words
the object's own ELF section holds. Anything else is discarded, rebuilt, and
reported.

That is not defensive programming for its own sake. The cache every campaign
writes guards on existence alone, so a run killed mid-write leaves a **zero-byte**
file that is kept, parses to no rows, and therefore reports no mismatches — a
silent perfect score. Five independent reports of that one file, and one of its
numbers reached a stage summary.

## Where these sit

`score` prints the one-line screen these two commands elaborate:

```
screen: sha=10e37dc2dc12 ni=4641 frame=-1704 ld1184=2 st1184=1 coset=id
```

— identity, real instruction count, frame, float load and store traffic at a
`--slot`, and the ring coset. `next` routes an instruction-count difference to
`align` and a run of float-register rows to `phase`.

See also: [Object comparison](object-comparison.md) for the metric definitions,
[Aligned mechanism view](view.md) for row-level evidence, and
[score and matrix](score-and-matrix.md) for the byte-scoring gate.
