# Synthetic decomp.me export

This directory is a redistributable workflow fixture, not the result of one
compiler invocation.

- `metadata.json`, `ctx.c`, and `code.c` exercise export validation and the
  site's `ctx.c` + `#line 1 "src.c"` + source composition.
- `target.objdump` and `current.objdump` exercise the aligned comparator. They
  contain real MIPS instruction words with two adjacent `li` instructions in
  opposite orders, reproducing a late scheduling residual.
- The browser score is invented context. It is deliberately independent of
  the four-instruction dumps and must never be treated as the workbench oracle.

The repository cannot redistribute an IDO toolchain, so these files do not
claim that compiling `code.c` produces `current.objdump`. Use a real downloaded
export with `check-scratch --compile-command` when testing site-faithful
compilation. The synthetic split is intentional: one fixture can teach the
handoff semantics and the comparison shape without shipping proprietary
compiler output or project code.
