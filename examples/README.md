# Examples

Most files in this directory are synthetic or reduced text intended for
redistribution. [The CV64 walkthrough](cv64/README.md) is a separately
attributed set of complete, single-function scratch materials; it contains no
ROM or extracted non-code assets.

Run every command below from the repository root. CI executes these same
commands from that directory, so the examples cannot quietly drift.

## Object comparison fixtures

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

`target.objdump` and `relocated-match.objdump` differ only in bits covered by
`R_MIPS_HI16` and `R_MIPS_26`. `register-mismatch.objdump` adds one real FP
register change.

## Aligned mechanism view fixtures

```sh
decomp-workbench view-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep
```

`phase-shift-*.objdump` differ only by a temp-rotation phase: six register
substitutions, four webs, one upstream cause. `shifted-insertion-*.objdump`
carry one extra instruction, where positional counting reports eleven differing
words and the alignment reports one hunk. Both pairs are synthetic and encode
real MIPS words, so byte-level signatures are meaningful.

## Statement-line (`.loc`) boundary fixtures

```sh
decomp-workbench diagnose-dumps \
  examples/fixtures/loc-boundary-target.objdump \
  examples/fixtures/loc-boundary-candidate.objdump \
  --function blitRow \
  --candidate-listing examples/fixtures/loc-boundary-candidate.s
```

`loc-boundary-*.objdump` hold the same instruction multiset in two orders, so
the verdict is `schedule`. `loc-boundary-candidate.s` is a synthetic IDO ugen
listing for the candidate — the file `cc -K` keeps and `ugen -l` writes — with
`.loc`, `.livereg`, a label, and a `li` macro as1 has not expanded yet. Two of
the three divergent sites straddle a `.loc` change and one does not, so the
report routes to `playbook=line-assignment-probe`. The C statements named in
the listing's comments are invented; nothing here is derived from a game ROM,
and the causal claim the fixture demonstrates is the *shape* of the evidence,
not a measurement.

## decomp.me export fixture

```sh
decomp-workbench check-scratch examples/fixtures/decompme-export
```

`examples/fixtures/decompme-export/` is a synthetic expanded export: metadata,
context, source, and a redistributable target/current objdump pair. Its two
adjacent `li` instructions are reversed, reproducing the final shape of a real
`99.98%` scheduling residual without shipping compiler output or project code.
The full workflow is in
[From a decomp.me export to local truth](../docs/decompme-exports.md).

## Ugen FIFO trace

```sh
decomp-workbench trace-fifo examples/traces/ugen-fifo.log \
  --registers t6,t7,t8 \
  --show-events \
  --fail-on-violation
```

The first three appends seed the queue. Later events allocate and recycle four
logical values.

## Globalcolor trace

```sh
decomp-workbench trace-globalcolor examples/traces/globalcolor.log --dtype 13
```

The trace contains two live ranges, color costs, and one later `[CDX]`
decision. Values are illustrative; they are not copied from a target compiler
binary.

## Oracle planning and source correlation

```sh
decomp-workbench oracle plan examples/traces/oracle.log
```

The synthetic trace has one web in each allocator phase and measured color
costs, so planning can be phase-complete without inventing a register universe.
Map its logical lines back through retained preprocessor and listing evidence:

```sh
decomp-workbench trace-source \
  examples/traces/oracle.log \
  examples/traces/oracle-source.i \
  --listing examples/traces/oracle-listing.s \
  --source-file candidate.c
```

The report says whether each correlation was uniquely observed, selected,
ambiguous, or unresolved. It never treats a trace-local web number or a
line-only coincidence as stable source identity.

## Experiment manifest

```sh
decomp-workbench experiment validate \
  examples/experiments/statement-grouping/experiment.json
```

The example is a complete two-by-two parameter grid with a protected
instruction region. Validation checks every path and assignment without
compiling or modifying a source file; see
[its README](experiments/README.md).

## Alias trace

```sh
decomp-workbench trace-alias examples/traces/alias.log --show-queries
```

The fixture exercises fresh and direct base paths plus one `no-alias` and one
`may-alias` result. Addresses and symbol numbers are invented.

## Instrumentation fidelity microcase

`examples/instrumentation/fidelity-micro.c` is a small, header-free source used
to check the pinned uopt and generic ugen instrumentation against a real
static-recompiled IDO 5.3 build. It exercises integer and floating-point live
ranges, a loop, global memory, and alias queries. Use it for the positive and
negative controls in
[compiler instrumentation](../docs/compiler-instrumentation.md#required-fidelity-gates).
