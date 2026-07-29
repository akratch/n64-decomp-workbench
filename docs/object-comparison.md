# Object comparison

Use comparison as a ladder: begin with broad structural signals, then require
exact instruction words once the candidate is close.

## Compare objects

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

For CI:

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --fail-on-mismatch \
  --json > comparison.json
```

Every command that selects one function accepts `--symbol` and `--function`
as two spellings of the same option, because decompilation projects say
"function" and GNU tooling says "symbol". Passing both with different values
is an error rather than a silent last-one-wins.

`--fail-on-mismatch` returns nonzero unless the relocation-aware words and
relocation-kind layout match and every encountered type is understood. With an
explicit `--cross-rom`, structural equality is accepted for the command but
continues to report `exact=false`.

Every human-readable report starts with a verdict and next action. This is
intentional: `raw_word_mismatches` is evidence about literal instruction-word
identity, not an instruction-matching score. For example:

```text
verdict=instruction-exact words=   0 raw=  48 ...
raw difference classes: relocation_controlled=48
next: Instruction-exact: raw differences are linker-controlled relocation fields.
```

This prevents a common late-stage failure mode: continuing to mutate source
solely because a UI or raw comparison reports a nonzero number after the object
oracle has already proved the instructions exact.

## No verdict may suppress a diff site

The verdict chooses emphasis and the next action. It never filters evidence.
Every position where the instruction words or the relocation kinds differ is
reported as a *diff site*, classified but never dropped:

```text
verdict=allocation-mismatch words=   2 raw=   2 ...
diff sites: 2 (constant=1, register=1)

[   0] constant
       target    24020021  li $v0,33
       candidate 24020031  li $v0,49

[   1] register
       target    012a4021  addu $t0,$t1,$t2
       candidate 012a5821  addu $t3,$t1,$t2
```

The site count and class histogram always print; `--show-diff` adds the sites
themselves. Site classes are `constant`, `register`, `commutative-order`,
`opcode`, `operand`, `relocation-layout`, `relocation-controlled`, and
`instruction-count`. This is a policy, not a patch: a register-range summary
once hid a `li v0,33` versus `li v0,49` literal that the same report counted
in `raw`, and the omission scoped an experiment to two sites when there were
three. The invariant is covered by a test: every differing word is a site.

`diff_sites` and `diff_site_classes` carry the same evidence in `--json`.
`register_diff` remains for compatibility and is the register-classed subset.

When `--symbol` selects an assembly-defined symbol without an ELF size, GNU
objdump can include zero alignment padding through the end of the section. The
workbench excludes unreachable zero words after the function's final `jr ra`
delay slot; the delay-slot instruction itself remains part of the comparison.

## Verdicts and the next lever

A verdict names the cheapest mechanism that explains the residual, because a
verdict chosen by volume sends the next experiment to the wrong layer.

| Verdict | Recognized by | Next lever |
|---|---|---|
| `instruction-exact` | Masked words agree; raw differences are relocation-controlled | Verify the link or ROM; do not change source |
| `instruction-words-identical` | Raw words and relocation layout agree | Run the project's final verification |
| `unknown-relocation` | A relocation kind has no precise field mask | Add the mask before trusting the comparison |
| `relocation-layout-mismatch` | Instruction bits agree, relocation kinds/symbols differ | Translation-unit and linker context, not fake expressions |
| `constant-mismatch` | Every differing site is an immediate on `li`/`lui`/`ori`/`andi`/`addiu`/`slti` with equal opcodes and registers | Audit the flag/enum/constant against the assembly, then re-derive fakes |
| `commutative-order` | Every differing site swaps the two sources of a commutative operation | Compound assignment (`x \|= y`), not the allocator |
| `schedule-mismatch` | Equal instruction count and equal opcode multiset, reordered | Statement/expression grouping; `-g0` diagnostic; `replay-as1` |
| `structure-mismatch` | Opcode differences or an instruction-count delta | C and control-flow shape; check constant sites first when present |
| `allocation-mismatch` | Opcode shape agrees, registers differ | Live ranges, declaration order, allocator traces |
| `operand-mismatch` | Remaining immediate or offset differences | Inspect the localized sites |

Three of these classes exist because volume-based naming misdirected real
campaigns:

- **`constant-mismatch`** — one wrong flag identifier produced 183 words that
  read as `structure-mismatch`. When a large structural difference starts at a
  constant materialization, the assembly encodes the truth; audit the constant
  before anything else, then re-derive fakes that may have been fitted to the
  wrong body.
- **`commutative-order`** — two `or` instructions with swapped sources were
  reported as `allocation-mismatch`, which dispatched allocator work for an
  expression-tree problem. IDO 5.3 canonicalizes `a | b` and `b | a`, so that
  family is dead; `x |= y` is a distinct expression tree and is the lever.
- **`schedule-mismatch`** — equal-length reordered output was reported as
  `structure-mismatch`. Under `-g3` IDO emits a `.loc` per statement and the
  assembler restricts motion across those barriers, so rebuilding the candidate
  with `-g0` is the decisive one-command diagnostic: if the divergent region
  collapses, the C is correct and the residual is debug-info scheduling.

A verdict never suppresses evidence; see the diff-site policy above.

## One name per metric

The terminal label and the JSON key are the same string, rendered from one
registry entry. `words=` in the summary line is `"words"` in `--json`;
`insns=` is `"insns"`; `frame=` is `"frame"`. Print the whole registry with:

```sh
decomp-workbench --explain-keys
```

`--explain-keys` is also accepted by every command that reports comparison
metrics (`compare`, `compare-dumps`, `rank`, `compile-rank`, `campaign`), and
prints the table without running the command.

The previous JSON spellings — `word_mismatches`, `raw_word_mismatches`,
`normalized_distance`, `register_mismatches`, `fp_register_mismatches`,
`candidate_instructions`, `candidate_frame_size`, `candidate_sha1`, and the
other long forms listed by `--explain-keys` — **are deprecated but still
emitted beside the canonical keys for one release**. They carry identical
values. New consumers should read the canonical key; existing consumers keep
working until the next release removes the aliases.

This is a bug-class fix, not cosmetics: `words=` versus `word_mismatches` cost
debugging cycles in two recorded campaigns. A test asserts that every label
printed on the summary line resolves to a registry key and that both spellings
carry the same value, so the two surfaces cannot drift again.

## What the metrics mean

The table below uses the attribute names; the canonical short key for each is
in `--explain-keys`.

| Field | Meaning | Appropriate use |
|---|---|---|
| `raw_word_mismatches` | Positional 32-bit word differences before masking | Detect whether files are literally identical |
| `word_mismatches` | Positional differences after masking known linker-controlled fields | Final function-level matching oracle |
| `opcode_mismatches` | Positional mnemonic differences | Distinguish structure from operands |
| `normalized_distance` | Sequence edit distance after masking addresses, immediates, and stack offsets | Search guidance only |
| `register_mismatches` | Positional register-operand differences | Locate allocation phases |
| `fp_register_mismatches` | Register differences involving `$fN` | FP allocation diagnostics |
| `instruction_delta` | Candidate instruction count minus target count | Structural basin |
| `candidate_frame_size` | First `addiu sp,sp,N` adjustment | Stack topology |
| `candidate_stack_offsets` | Histogram of `N(sp)` operands | Spill and local-home comparison |
| `candidate_fp_register_uses` | Histogram of FP operands | Promotion/allocation comparison |
| `verdict` | Product-level classification of the evidence | Decide whether to edit source, trace allocation, or verify the link |
| `raw_difference_breakdown` | Why literal words differ | Separate instruction bits from relocation-controlled words |
| `diff_sites` | Every differing site with its class | Read the residual without the verdict filtering it |
| `diff_site_classes` | Count of differing sites per class | See the mechanism mix at a glance |
| `structural_exact` | Opcode, normalized shape, registers, frame, and count agree | Cross-ROM/compiler-lineage evidence only |
| `accepted` | Whether this invocation satisfies `--fail-on-mismatch` | Automation for `compare` and `compare-dumps` |
| `acceptance_basis` | `function-exact`, `cross-rom-structural`, or `mismatch` | Explain why the command accepted or rejected the comparison |

`instruction-words-identical` means the selected function's raw instruction
words and known relocation-kind layout agree. It does not claim that the whole
object file, symbol table, or final ROM is byte-identical.

The sort order for `rank` and `campaign` is exact word mismatches, unknown and
mismatched relocation metadata, normalized distance, register mismatches,
instruction-count delta, then path. It is a convenient default, not a claim
that one scalar ordering captures every useful transition.

## Relocations

The workbench invokes GNU-compatible objdump with `-d -r -z`. At each aligned
instruction, it masks the union of fields controlled by known relocations on
either side:

- lower 16 bits for common `HI16`, `LO16`, `GPREL16`, `GOT16`, `CALL16`,
  TLS, and related instruction relocations;
- lower 26 bits for `R_MIPS_26`;
- all 32 bits for relocations such as `R_MIPS_32` and `R_MIPS_REL32`.

`R_MIPS_NONE` and `R_MIPS_JALR` do not mask instruction bits. An unknown
relocation is reported and prevents `exact=true`; the comparator does not
guess.

Relocation symbols and addends are recorded by the parser but are not part of
the verdict. `relocation_metadata_mismatches` reports positional differences
in relocation kinds and prevents `exact=true`. The relocation-aware word
metric remains useful when comparing an extracted/link-resolved target and an
unlinked candidate, but the report does not silently call unequal relocation
layouts exact.

### Linked-address aliases

Two equivalent endpoints can have different spellings: `array + count` in an
unlinked candidate and the next adjacent BSS/data symbol in a linked target.
Their final linked address may be identical even though their relocation symbol
or addend presentation differs. Treat this as a translation-unit/linker-context
question, not proof that the function's C needs a fake expression. The
workbench calls such a case `relocation-layout-mismatch`; verify the linked
object or final ROM before changing source.

## Compare retained text

`compare-dumps` accepts GNU objdump text directly:

```sh
decomp-workbench compare-dumps target.objdump candidate.objdump \
  --symbol function_name
```

This is useful for bug reports and tests because the text can be reduced to a
small redistributable fixture. When a dump contains several functions,
`--symbol` selects the exact objdump label. It uses the same relocation parser
and metrics as object comparison.

## Cross-ROM structural evidence

Projects with regional or revision ROMs can compare retained dumps or objects
with `--cross-rom`:

```sh
decomp-workbench compare-dumps jp.objdump us.objdump \
  --symbol function_name --cross-rom --fail-on-mismatch
```

This accepts `structural_exact`: equal opcode sequence, normalized instruction
shape, register operands, frame, and instruction count. It is useful evidence
that the source/compiler lineage is shared across ROMs even when linked
addresses, data offsets, and absolute immediates differ. It never changes
`exact=true`, and it must not replace project-level object or ROM matching.
JSON output makes the distinction explicit with
`"acceptance_basis": "cross-rom-structural"`.

## Ranking is not proof

Normalized distance intentionally hides information. A candidate can improve
instruction shape while worsening the scalar score, or hide a frame shift when
stack offsets are normalized.

For projects using asm-differ, keep its native score and penalty buckets beside
the workbench report. The workbench does not reproduce asm-differ’s alignment
or weights.

The final project gate should remain the project’s normal object or whole-ROM
verification, not a heuristic score.
