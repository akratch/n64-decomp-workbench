# Zero-emission levers against a forced state: `sweep levers`

A force (`CDX_FORCE=p1:wN=cK`, or `=s` for a split) *prices* a target: if the
forced object matches, the residual is that one allocator decision. What is
left is the source edit that puts the allocator in that state without the
force. In the Mickey's Speedway USA campaign that search was, nearly every
time, a hand-written sweep of 50 to 500 cells drawn from a short catalogue of
transforms that emit no instruction of their own and change only what the IR
looks like to uopt. `sweep levers` is that catalogue, with an oracle that
recognises a cell which reached the forced state from the cell's own records.

```sh
decomp-workbench sweep levers func.c --function func --target target.o \
  --compile-command "ido/cc -c -O2 -mips2 -G 0 {source} -o {output}" \
  --proc 0 --oracle p1:w12=c15
```

## The catalogue

| Lever | Edit | Mechanism | Semantics |
|---|---|---|---|
| `dead_read` | `x = READ;` into a local that is dead there | the read's address expression enters uopt's table; a bare dead read is inert, so none is generated | safe |
| `dead_masked` | `x = READ & 0xFFFF;` into a dead integer local | the load goes to a scratch temp, the copy is deleted, and the web can still deny a register in its block | safe |
| `keep_alive` | `x \|= 0;` or `x ^= 0;` after `x = <expression>;` | kills uopt's substitution of the symbol | safe |
| `noop_redef` | `x = (T) x;`, `T` the declared type | deleted, but kills forward substitution into a later use | safe |
| `narrow_type` | a narrower or wider integer type for one local | changes the web's type, which orders webs | check |
| `subscript` | `[E]` -> `[(E) & 0xFFFF]`; `&X[E]` -> a byte-scaled address | a second scratch draw that as1 folds | check / safe |
| `boundary` | `do { S } while (0);` around a statement; an empty `if (v) {}` at a position | a block boundary; an empty `if` keeps `v` live there at zero emission | safe |
| `global_reread` | after `G = x;`, the next read of `x` reads `G` | moves a load ahead of a store group | check |
| `zero_def` | `k = 0;` for a dead integer local right after a loop | a def between two loops keeps the first loop's `<` exit test | safe |
| `split_local` | one local becomes two names from a dominating redefinition | two IR names, two live ranges | safe |
| `merge_locals` | two same-typed locals with disjoint ranges become one, declaration kept or dropped | one name; can shrink an oversized frame | check |
| `reorder` | two adjacent independent statements swapped | statement order reaches ugen emission order and as1's line-keyed tie-break | safe / check |
| `loop_move` | the statement before a loop moved into its head, or the body's first statement hoisted out | moves a def across the loop boundary | check |
| `const_iv` | `K = C; for (v = K; ...)` for `for (v = C; ...)` | a constant symbol folded into the induction variable's init | safe |

`check` means the edit can change behaviour; read a winner against the whole
enclosing scope before adopting it. "Dead" is decided conservatively from the
statement tree: the next mention after the position must be a plain
`x = ...` that does not read `x`, at a level every later path passes, with no
label, `goto` or escaping `break`/`continue` in between, and every enclosing
loop must re-kill `x` before its back edge reads it. A dead read is generated
only when the read's declared type is known and assignment-compatible; struct
field types come from the translation unit and any `--header` files.

Where each lever came from, and how strong the evidence behind it is, is
recorded row by row in the [IDO 5.3 evidence index](compiler-laws/ido-5.3-evidence.md).
Two of the properties the catalogue relies on are reproduced there with
original C: a bare dead read is byte-inert while an empty `if (n) {}` is
zero-emission yet moves allocation, and a def between two loops keeps the
first loop's `<` test.

Inserted text goes on the physical line of the statement it follows, so every
other line keeps its number (as1 breaks scheduling ties on source lines).
`--own-line` puts it on a line of its own instead.

## How a cell is measured

1. **The base, three times.** A stock compile; a traced compile with no force,
   whose function rows must equal the stock rows (the identity gate -- if they
   differ the sweep stops); and a traced compile with the oracle's force
   (and/or bias). Every force must be *accepted*: a colour force needs one
   decision and one colour record for its web, carrying the requested colour
   with `forced` equal to it or `-1`; a split force needs every decision row of
   its web to say `forced=-1` and no colour row. A force the compiler refused
   stops the sweep, because a sweep against an unpriced state finds nothing.
2. **Each cell, stock.** A cell whose function moves more than
   `--max-size-delta` bytes from the base is dropped before scoring. A cell
   whose function rows equal the base's is `inert`: it copies the base's
   numbers and costs no traced compile.
3. **Each other cell, scored and traced.** The cell is aligned against the
   target ([`align`](shift-and-phase.md)'s shift-tolerant residual: edit distance plus
   paired mismatches) and compiled once more with tracing on and *no* force.
   Its traced rows must equal its stock rows, or the oracle column reads
   `gate`.

Cells rank exact first, then by aligned residual, then by whether the oracle
reproduced, then by size delta. `=F` marks a cell whose function rows equal the
forced base's exactly.

## The oracle

Web numbers are not stable across source edits -- a dead statement still
renumbers webs -- so the forced web is never looked up by number in a cell. It
is re-found by its `webexpr` expression and kind, and the source lines of the
blocks it spans (Jaccard overlap at least 0.3; failing that, the same kind
over at least 0.6 of the lines). A colour target is reproduced when that row
carries the colour; a split target when no same-expression row over those
lines is coloured (a piece that is never formed counts). When the
best-overlapping rows tie and disagree, the cell reads `ambiguous` and the
candidates are printed, rather than a yes or a no.

`--bias 'N=DELTA,...'` prices a decision *order* instead of a colour, for an
instrument that implements `CDX_BIAS`: it adds `DELTA` to a phase-one web's
save for globalcolor's candidate selection only, so the records still print
the true save. The pairs of phase-one webs whose order the bias reversed
against the unbiased base are the state to reproduce, and a cell satisfies one
when its own unbiased records decide the two webs in the biased order. To
impose a whole order, give each named web its key minus its save.

The oracle reads the campaign-local `CDX_WEBREPORT` records (`webexpr`,
`bbline`; see [`trace web-report`](web-report.md)) as well as the shipped
profile's. A forced web with no `webexpr` record cannot be re-found after an
edit, and the sweep says so instead of guessing.

## The recipe

`--compile-command` is an argument vector with `{source}` and `{output}`,
split without a shell and run in a sealed environment: only `--env` values and
`--inherit-env` names reach the compiler. `--instrumented-command` is the
traced recipe; it defaults to `--compile-command`, which is right for an
instrumented compiler that is byte-identical to stock with tracing off. The
sweep sets `CDX_LOG`, `CDX_PROC`, `CDX_DETAIL_WEB`, `CDX_WEBREPORT`, `CDX_OUT`,
`CDX_FORCE` and `CDX_BIAS` itself, and refuses an `--env` that sets any of
them: a stray `CDX_FORCE` in the base environment would make every "unforced"
cell forced.

`--target` and every output may be an ELF object (read with `--objdump`) or
retained objdump text. Project-specific glue -- where a function's TU lives,
which per-file flags it builds with, which ordinal a symbol has -- stays in
the project: this command receives a recipe and a target and nothing else.

Exit status: 0 when a cell is exact or reproduces the oracle, 1 when none
does, 2 on an error. `--json` emits `decomp-workbench-lever-sweep-v1`. Cells
live under `--scratch` (default: a fresh temporary directory); only the best
`--keep` cells' sources survive, under `best/`.

## Stream surgery is a different instrument

For a question about as1 or ugen *order* rather than allocation, a faster
oracle exists: edit the `cc -S` output and reassemble it. It is valid only
when the text round trip is byte-identical to the direct path, which, for the
measured project, needed the driver's own assembler flags (see W28 in the
[evidence index](compiler-laws/ido-5.3-evidence.md)). Check the round trip on
the unedited stream first.
