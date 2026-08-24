# Target audit

`target audit` answers one question before a campaign spends any time on a
function: **is the target object even scoped correctly?** It is a static
check, plus one optional read-only ROM peek, and it runs in about a second —
which is the entire point. The alternative is finding out the target was
wrong after the campaign that trusted it is over.

```
decomp-workbench target audit TARGET.o [--rom ROM --rom-offset HEX --va HEX] [--json]
```

## Why this command exists

The [cef4c endgame postmortem](history/postmortem-2026-08-24-cef4c-exact.md)
(finding 7, "nobody audited the target") is the origin story. Ten days of
campaign work against `func_ovl0_800CEF4C` (`lbParticleUpdateStruct` in the
`ssb-decomp-re` project) assumed the hosted decomp.me `target.o`'s scope was
ground truth — right up until a fully reverse-engineered, ROM-faithful
`words=0` candidate still scored **5, not 0**, against it. Nothing about the
score said why. The campaign had to autopsy the ELF and the ROM by hand to
find the cause, a full session after the source itself was already exact.

### What was actually wrong

The function ends with two jump tables (dense `switch` dispatches, IDO's
usual shape) stored in `.rodata`, immediately followed by the function's own
literal pool: four identical copies of the constant `2048 / pi` — one per
`sincos`-family use site, because IDO does not deduplicate per-use-site FP
literals. As 32-bit bit patterns, each of those four words is
`0x4422F983`.

The splat extraction that produced the hosted `target.o` symbolized those
four words as **external** data symbols (`D_ovl0_800D6120` through
`..612C`) instead of leaving them as part of the function's own `.rodata`,
and truncated `.rodata` at exactly the jump tables' own end — 348 bytes,
instead of the 368 the function's real read-only data runs to. The 20 missing
bytes (16 bytes of literals plus a 4-byte alignment pad) are exactly what a
ROM-faithful candidate's `.rodata` carries that the target's does not, and
decomp.me charges every one of them as a mismatched data word.

Confirmed against the ROM directly: reading the bytes at ROM file offset
`0x51B00` (VA `0x800D6120`), immediately after the function's jump tables, in
`ssb-decomp-re`'s `baserom.us.z64` gives four repeats of `0x4422F983` in a
row, contiguous with the jump table and four-for-four with the four
"external" symbols `.text` loads through `$at`. The pool was never external —
it belonged to the function the entire time.

The fix (`hosted-fix/target-fixed.o` in that session's own working notes) is
mechanical once found: extend `.rodata` to the true 368 bytes and repoint the
section header, touching nothing else. `compare target-fixed.o current.o`
then reports `exact=true, words=0` — the fix was purely in the target's own
scope, never in the source.

## What it checks

### 1. ELF sanity

Sections present (`.text`, `.symtab`), relocation section entry counts
consistent with their declared `sh_entsize` (a conforming `Elf32_Rel` entry
is 8 bytes; the whole point of a target audit is not to trust a header that
lies about its own layout), `sh_link`/`sh_info` pointing at what they claim
to (a symbol table, the section the relocations apply to), and every
relocation's and symbol's index inside the tables the object actually
carries. An object that fails here cannot support the findings below, so
these run first, in `src/decomp_workbench/elf.py` (a small generic ELF32
big-endian reader — sections, symbols, and relocations, all of them, not
just one section's raw bytes the way
`decomp_workbench.elf_instructions` reads for the padding-safe instruction
count).

### 2. The literal-pool truncation heuristic — the headline finding

The exact shape of the cef4c defect, read straight from the object with no
ROM needed. Two independent facts, checked together:

* **A jump table's own extent**, read from `.rel.rodata`: every relocation
  entry in that section whose symbol resolves *into `.text`* is a jump-table
  word (a code pointer stored in read-only data), and the highest such
  offset plus four is where the table ends.
* **A `$at`-loaded undefined symbol** in `.text`: a `%hi`/`%lo` relocation
  pair where the low half is an `lwc1`, `ldc1`, or address-materializing
  `lw`, based through register `$at` (the exact shape IDO's assembler emits
  for `lui $at, %hi(sym); OP %lo(sym)($at)`), naming a symbol this object
  does **not** itself define (`SHN_UNDEF`). A load through any other base
  register is addressing something else entirely — a struct field through a
  real pointer, not a pool slot — and is deliberately excluded; the real
  cef4c object has two such decoy sites (`D_ovl0_800D639C` through `$a1`,
  `D_ovl0_800D6358` through `$v0`) that must not be flagged, and the fixture
  suite in `tests/test_target_audit.py` pins that exclusion down directly.

When both are true **and** `.rodata`'s own declared size equals the jump
table's end exactly — zero bytes left over — that is
`literal-pool-truncated-at-jump-table`, a `defect`: a function-owned literal
pool that used to sit right after the jump table was externalized, and the
truncated section size hides the fact perfectly. There is no gap to notice
by eye; the coincidence between the table's end and the section's end *is*
the tell. When bytes remain after the table, that is `literal-pool-present`
(`info` — the pool survived). When `$at`-loaded undefined symbols exist but
no jump table was found at all, that is a `warning`
(`fp-literal-undef-no-jump-table-context`) — there is nothing to check the
truncation coincidence against, but the pattern is still worth a human
look.

The `defect` additionally requires the relocated words to *have the shape of
a jump table*: one dense ascending run of 4-byte slots, beginning at
`.rodata`'s own start, which is what a function's own extracted `.rodata`
looks like. Not every `.rodata` word that relocates into `.text` is a jump
table — a `const` array of function pointers is the common other one, and
when such an array ends `.rodata` it produces exactly the same zero-bytes-
left-over coincidence on a perfectly healthy object. That case is reported
as `rodata-ends-at-text-relocated-words`, a `warning` naming which half of
the shape did not hold, rather than condemning the object.

### 3. Data-scope report

Always emitted, independent of severity: `.text`/`.rodata`/`.data`/`.bss`
sizes, the jump table's own word count and end offset, the byte count that
survives past it, and every `SHN_UNDEF` symbol `.text` reaches through a
`%hi`/`%lo` pair at all (not only the `$at` subset) — each with the addends
every site that references it uses. On the real defective `target.o` this
reports nine undefined data symbols, of which four are the `$at`-loaded
literal-pool sites and the rest are ordinary externs the truncation
heuristic correctly leaves alone.

### 4. Optional ROM cross-check

`--rom FILE --rom-offset HEX --va HEX` reads the ROM bytes immediately past
the object's own **extracted** `.rodata` extent and reports what is there —
read-only, one bounded `open()`/`seek()`/`read()`, never parsed as a ROM
image, decompressed, loaded, or executed.

`--rom-offset` and `--va` name the *same byte*: the start of this object's
own extracted `.rodata` in the ROM, as a file offset and as a run-time
address respectively. That is what lets a caller supply one pair — found
once, from a splat symbol or a linker map — and have "just past the
extracted extent" derived from the object's own `.rodata` size rather than
typed in by hand for every function. On the real cef4c object, VA
`0x800D5FC4` / ROM offset `0x0519A4` is exactly that byte (the `.rodata`
start, jump-table start), and asking for the bytes 348 further on lands
exactly on the doc's own `0x51B00` / `0x800D6120`.

The interpretive verdict — does a value repeat as many times as there are
`$at`-loaded undefined symbols? — is only produced when the static heuristic
already found the section truncated at the table boundary. When it did not
(the healthy shape: the pool already lives inside `.rodata`), the bytes just
past the extent are simply the *next* datum in the ROM, not a repeated
literal, and scoring that as a mismatch would manufacture a false warning on
a perfectly good object — measured directly against `target-fixed.o` while
building this command, before the gate was added. The raw words are still
read and reported either way; only the pass/fail interpretation is
conditional on there being a truncation to corroborate.

### 5. Verdict and exit status

Severities compose into one verdict, gate-friendly for campaign
registration:

| Verdict    | Condition                          | Exit code |
|------------|-------------------------------------|-----------|
| `ok`       | no `defect`, no `warning` findings | 0         |
| `warnings` | no `defect`, at least one `warning` | 1         |
| `defects`  | at least one `defect`               | 2         |

`info` findings never affect the verdict — they are evidence (a jump table
was found, the ROM confirms the pool), not problems.

## Worked example

Against the real cef4c hosted objects (available only in the session that
produced this document; not checked into this repository — see the
implementation notes below):

```
$ decomp-workbench target audit target.o
verdict: DEFECTS (1 defect(s), 0 warning(s))
...
  .text-relocated words: 87, .rodata+0..348, 0 byte(s) follow them
...
findings:
  [DEFECT] literal-pool-truncated-at-jump-table: `.rodata` ends exactly at
  the jump table's own end (348 bytes), with zero bytes left over, while 4
  undefined symbol(s) are loaded through `$at` the way a per-use-site FP
  literal pool is -- this is the cef4c defect: ...

$ decomp-workbench target audit target-fixed.o
verdict: OK (0 defect(s), 0 warning(s))
...
  .text-relocated words: 87, .rodata+0..348, 20 byte(s) follow them
...
findings:
  [INFO] literal-pool-present: `.rodata` carries 20 byte(s) past the jump
  table's end (348); 4 undefined symbol(s) are still loaded through `$at`,
  but the section is not truncated at the table boundary
```

With `--rom baserom.us.z64 --rom-offset 0x0519A4 --va 0x800D5FC4` added, the
defective run additionally reports:

```
  [INFO] rom-confirms-literal-pool: ROM bytes immediately past the extracted
  `.rodata` extent repeat 0x4422f983 exactly 4 time(s) -- matching the 4
  undefined symbol(s) `.text` loads through `$at`. The pool belongs to this
  function
```

## Implementation notes

* `src/decomp_workbench/elf.py` — the generic ELF32 big-endian reader
  (sections, symbols, relocations) this command and any future static
  object check can build on.
* `src/decomp_workbench/target_audit.py` — the heuristic and the report.
* `src/decomp_workbench/target_audit_cli.py` — the `target audit` command.
* `tests/target_audit_fixtures.py` builds every test object from scratch (a
  small hand-rolled ELF32BE writer with real `Elf32_Sym`/`Elf32_Rel`
  tables); `tests/test_target_audit.py` never reads a game- or ROM-derived
  byte. The real cef4c `target.o`/`target-fixed.o` pair and
  `baserom.us.z64` were used only to develop and hand-verify this command
  against a known-true positive and negative, read-only, and are not part
  of this repository or its test suite. The one game fact quoted anywhere
  in this document is the four-byte constant value `0x4422F983` itself
  (`2048 / pi`, a public floating-point identity, not proprietary data).
