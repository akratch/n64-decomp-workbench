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

When `--symbol` selects an assembly-defined symbol without an ELF size, GNU
objdump can include zero alignment padding through the end of the section. The
workbench excludes unreachable zero words after the function's final `jr ra`
delay slot; the delay-slot instruction itself remains part of the comparison.

## What the metrics mean

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
