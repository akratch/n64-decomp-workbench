# Examples

Everything in this directory is synthetic or reduced text intended for
redistribution.

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
