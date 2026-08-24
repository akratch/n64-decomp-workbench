# Known defects

## compare --symbol misaligns multi-function objects (2026-08-24)

Repro (SSB64 cef4c campaign, TU-state probe): a multi-function candidate
object built from `ctx.c` + sibling functions + the target function, compared
with

```sh
decomp-workbench compare ref5/target.o tu-pre.o --symbol func_ovl0_800CEF4C
```

returns `words=1799 opcodes=1798 gaps=1798 insns=1866` — nonsense values —
and the SAME command against a single-function object whose whole-.text
compare reports `words=1` returns the same nonsense. The symbol-scoped
extraction is therefore broken (likely applying section-relative relocation
or row offsets from the whole object to the carved function range).

Control evidence: whole-object compare of the same pairs gives sane results;
byte-searching the carved instruction encodings confirms the function bodies
are byte-identical apart from the expected single word.

Workaround used in the campaign: whole-.text compare with trailing siblings
only, plus direct byte-pattern search for the discriminating encodings.
