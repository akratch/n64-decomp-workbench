# Known defects

Nothing outstanding. Fixed defects stay on this page: a defect that is deleted
once it is fixed leaves the next reader with no way to tell "this was never a
problem" from "this was a problem and somebody dealt with it", and both of the
entries below cost a campaign real work before they were understood.

## FIXED: `compare --symbol` misaligned multi-function objects (2026-08-24)

**Symptom.** In the SSB64 `cef4c` campaign's TU-state probe, a multi-function
candidate object built from `ctx.c` plus sibling functions plus the target
function, compared with

```sh
decomp-workbench compare ref5/target.o tu-pre.o --symbol func_ovl0_800CEF4C
```

returned `words=1799 opcodes=1798 gaps=1798 insns=1866` — nonsense values —
and the same command against a *single*-function object whose whole-`.text`
compare reported `words=1` returned the same nonsense. Whole-object compares
of the same pairs were sane throughout, and byte-searching the carved
instruction encodings confirmed the function bodies were byte-identical apart
from the expected single word. The workaround was a whole-`.text` compare with
trailing siblings only, plus direct byte-pattern search.

**Root cause.** Not relocations and not section-relative offsets, both of
which were suspected. `parse_disassembly` ended the symbol selection at the
**first `<label>:` header** it met after the requested symbol — and a label is
not a function boundary. The ROM-extracted target object carries a symbol for
every jump-table destination *inside* `func_ovl0_800CEF4C`: forty-five of
them, all local, all `STT_NOTYPE`, all with size 0. The selection therefore
stopped 68 instructions into an 1,868-instruction function, and the
comparison was a prologue against a whole function. `gaps=1798` was the
aligner correctly reporting that one input was 1,800 rows short.

**Fix.** `decomp_workbench.elf_symbols.symbol_extent` reads the object's own
symbol table and returns the requested symbol's section-relative byte range:
`st_size` when the producer set one (IDO always does), otherwise up to the
next `STT_FUNC` symbol, otherwise to the end of the section. `dump_object`
passes that extent to the parser, which then selects by address and ignores
printed labels entirely. For the text-only `*-dumps` commands, which have no
object to read, `objdump.interior_labels` keeps the selection open across any
label a conditional branch reaches — a sound rule, and a deliberately
incomplete one: a label reached only through a jump table is invisible to it,
so pass an object rather than retained text when the distinction matters.

**Cover.** `tests/test_symbol_selection.py`, on hand-built synthetic ELF
objects that reproduce the interior-label shape.

## FIXED: `pass ucode --json` had no registered report schema (2026-08-24)

`inspect-ucode` emitted JSON but was absent from `reporting.SCHEMAS`, so the
suite's "every JSON-capable parser declares its schema" check was red. Now
registered as `decomp-workbench-ucode-xjp-v1`, the schema the report already
carried.
