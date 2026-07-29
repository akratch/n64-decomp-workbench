# Examples

Most files in this directory are synthetic or reduced text intended for
redistribution. [The CV64 walkthrough](cv64/README.md) is a separately
attributed set of complete, single-function scratch materials; it contains no
ROM or extracted non-code assets.

## Object comparison fixtures

```sh
decomp-workbench compare-dumps \
  fixtures/target.objdump \
  fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

`target.objdump` and `relocated-match.objdump` differ only in bits covered by
`R_MIPS_HI16` and `R_MIPS_26`. `register-mismatch.objdump` adds one real FP
register change.

## Aligned mechanism view fixtures

```sh
decomp-workbench view-dumps \
  fixtures/phase-shift-target.objdump \
  fixtures/phase-shift-candidate.objdump \
  --function animStep
```

`phase-shift-*.objdump` differ only by a temp-rotation phase: six register
substitutions, four webs, one upstream cause. `shifted-insertion-*.objdump`
carry one extra instruction, where positional counting reports eleven differing
words and the alignment reports one hunk. Both pairs are synthetic and encode
real MIPS words, so byte-level signatures are meaningful.

## decomp.me export fixture

```sh
decomp-workbench check-scratch fixtures/decompme-export
```

`fixtures/decompme-export/` is a synthetic expanded export: metadata, context,
source, and a redistributable target/current objdump pair. Its two adjacent
`li` instructions are reversed, reproducing the final shape of a real
`99.98%` scheduling residual without shipping compiler output or project code.
The full workflow is in
[From a decomp.me export to local truth](../docs/decompme-exports.md).

## Ugen FIFO trace

```sh
decomp-workbench trace-fifo traces/ugen-fifo.log \
  --registers t6,t7,t8 \
  --show-events \
  --fail-on-violation
```

The first three appends seed the queue. Later events allocate and recycle four
logical values.

## Globalcolor trace

```sh
decomp-workbench trace-globalcolor traces/globalcolor.log --dtype 13
```

The trace contains two live ranges, color costs, and one later `[CDX]`
decision. Values are illustrative; they are not copied from a target compiler
binary.

## Alias trace

```sh
decomp-workbench trace-alias traces/alias.log --show-queries
```

The fixture exercises fresh and direct base paths plus one `no-alias` and one
`may-alias` result. Addresses and symbol numbers are invented.

## Instrumentation fidelity microcase

`instrumentation/fidelity-micro.c` is a small, header-free source used to
check the pinned uopt and generic ugen instrumentation against a real
static-recompiled IDO 5.3 build. It exercises integer and floating-point live
ranges, a loop, global memory, and alias queries. Use it for the positive and
negative controls in
[compiler instrumentation](../docs/compiler-instrumentation.md#required-fidelity-gates).
