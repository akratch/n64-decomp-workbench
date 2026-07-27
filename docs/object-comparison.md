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

`--fail-on-mismatch` returns nonzero unless the relocation-aware words and
relocation-kind layout match and every encountered type is understood.

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

## Ranking is not proof

Normalized distance intentionally hides information. A candidate can improve
instruction shape while worsening the scalar score, or hide a frame shift when
stack offsets are normalized.

For projects using asm-differ, keep its native score and penalty buckets beside
the workbench report. The workbench does not reproduce asm-differ’s alignment
or weights.

The final project gate should remain the project’s normal object or whole-ROM
verification, not a heuristic score.
