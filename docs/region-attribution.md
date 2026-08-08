# Region attribution

```sh
decomp-workbench compare target.o candidate.o --by-region src/champion.c
```

```text
by-region: 516 differing word(s) across 57 region(s) of src/champion.c
anchors: 304 of 318 object call(s) matched against 320 source call expression(s)

  src/champion.c:1253          70 word(s)  register=70
  src/champion.c:1033-1123     42 word(s)  opcode=3 register=39
  src/champion.c:816-885       36 word(s)  register=36
```

Which source lines own these rows? Every campaign asks it and every campaign
rebuilds the answer by hand. This is that answer, ranked, with its own error
bars attached.

## The mechanism

An object built without debug information still carries one ordered signal
that names source-level constructs: its **call relocations**. A direct call to
a symbol the assembler could not resolve leaves an `R_MIPS_26` record carrying
the callee's *name*.

1. Read every `R_MIPS_26` in ascending section offset. That is the object's
   call sequence.
2. Scan the C source for call expressions in file order. That is the source's
   call sequence.
3. Align the two **by name**. Each matched pair is an anchor: one object
   offset, one source line.
4. Bracket each differing word between the two anchors that surround it.

## Three decisions that make it honest

**The object is ground truth; the source is a hypothesis.** The source scan is
a regex, and a regex cannot tell a call from a macro, a declaration, or a cast.
It does not have to. Only the alignment is trusted — a spurious source-side
name has no matching relocation, falls out, and is discarded. That is what
lets a cheap scanner be safe, and why this needs no C parser.

**Ambiguity is dropped, not guessed.** Text order and emission order disagree
whenever a call is nested: `f(g(x))` reads outer-first and emits inner-first.
Those pairs are dropped and counted rather than force-matched onto a wrong
line. The header always reports the ratio — `304 of 318` in the run above,
with the 14 dropped pairs being exactly the nested calls.

**The answer is a bracket, never a point.** Instruction density per source line
varies by an order of magnitude: a `sqrtf` call is two instructions, a matrix
build is two hundred. Interpolating a line number between two anchors would be
fabrication. A row between calls sixty lines apart gets a sixty-line answer,
and the report states its median bracket width so you can judge how tight the
attribution is.

## What it cannot do, and says so

Every run ends with a `how to read this:` block. It is not boilerplate; each
line is derived from that run's measurements.

- **Coverage.** Calls to `static` functions in the same translation unit, and
  calls the compiler inlined, emit no relocation and therefore no anchor.
  Stretches built entirely from them are bracketed only by whatever calls
  surround them.
- **Shadow rows.** When the two objects differ in instruction count, every
  branch immediate after the divergence differs mechanically. One campaign
  found 14 of its 42 "constant" rows were exactly that shadow and vanished for
  free from one upstream fix. Whenever the counts differ, the report warns that
  some counts below are shadow rather than independent work — because a ranking
  that puts shadow rows at the top actively misdirects the next edit.
- **Relocation-class words** are excluded from the ranking and counted
  separately. They are symbol naming, not emitted code, and no source edit
  moves them.

## Options

| Option | Effect |
|---|---|
| `--by-region SRC` | attribute and rank; available on `compare` and `compare-dumps` |
| `--by-region-limit N` | show the top N regions (default 12; `0` for all) |
| `--json` | adds a `by_region` object beside the existing comparison keys |

`decomp-workbench next TARGET.o CANDIDATE.o --src SRC` prints the
`--by-region` command with your paths already filled in.

## Refusals

Attribution fails loudly rather than returning an empty ranking, because a
silently absent ranking reads as "no regions differ":

- the object carries no call relocations at all;
- no call expression was found in the source;
- none of the object's calls matched any source call by name, which almost
  always means the source is not the one that produced the object.
