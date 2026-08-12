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
verdict=instruction-exact aligned_total=   0 words=   0 raw=  48 ...
raw difference classes: relocation_controlled=48
raw-vs-words: raw=48 exceeds words=0 by 48 relocation-controlled word(s):
              linker-filled bits no source change moves. A raw objdump text diff counts
              them permanently, so words=0 is the honest gate, not a byte-identical dump.
next: Instruction-exact: raw differences are linker-controlled relocation fields.
```

The `raw-vs-words` note appears whenever `raw` exceeds `words`, because that
difference is the number a separately written disassembly diff will report and
cannot remove. A pair whose target names each literal with its own symbol and
whose candidate merges them into one anonymous section sits on such a floor at
every literal load.

This prevents a common late-stage failure mode: continuing to mutate source
solely because a UI or raw comparison reports a nonzero number after the object
oracle has already proved the instructions exact.

## No verdict may suppress a diff site

The verdict chooses emphasis and the next action. It never filters evidence.
Every position where the instruction words or the relocation kinds differ is
reported as a *diff site*, classified but never dropped:

```text
verdict=allocation-mismatch aligned_total=   2 words=   2 raw=   2 ...
aligned residual classes: aligned_register=1, aligned_constant=1
diff_sites=2 (constant=1, register=1)

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

When registers differ and the stack adjustments also disagree, the report keeps the
`allocation-mismatch` family but prints the frame delta before the residual and
names frame recovery as a separate acceptance gate. A lower normalized
register score never hides a wrong frame; inspect callee-save use, spills, and
source-local stack homes before treating that candidate as progress.

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
  with `-g0` is a high-value ownership probe. If the region collapses, debug
  metadata constrains the `-g3` schedule and as1 can reach the target ordering.
  It does **not** prove source correctness: a freer scheduler can rescue a
  non-original expression or statement shape.

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
| `word_mismatches` | Positional differences after masking known linker-controlled fields | Final function-level matching oracle at zero; a tiebreaker above it |
| `aligned_total` | LCS-aligned differing rows a source change controls | Rank candidates against each other, but only where `aligned_gaps` is 0 on both |
| `aligned_insertions`, `aligned_deletions`, `aligned_gaps` | Aligned rows the aligner filled on one side only | Decide whether `aligned_total` may be compared with another candidate's at all |
| `alignment_comparable`, `alignment_caution` | Whether it may be, and the one-line caution when it may not | Gate an automated ranking |
| `aligned_structural`, `aligned_schedule`, `aligned_register`, `aligned_constant`, `aligned_commutative` | The aligned residual split by mechanism | See which lever family the residual belongs to before opening `view` |
| `opcode_mismatches` | Positional mnemonic differences | Distinguish structure from operands |
| `normalized_distance` | Sequence edit distance after masking addresses, immediates, and stack offsets | Search guidance only |
| `register_mismatches` | Positional register-operand differences | Locate allocation phases |
| `fp_register_mismatches` | Register differences involving `$fN` | FP allocation diagnostics |
| `instruction_delta` | Candidate instruction count minus target count | Structural basin |
| `target_true_instructions`, `candidate_true_instructions` | Real, unpadded instruction counts -- see "The true instruction count" below | The correctness screen to run before trusting anything position-based |
| `true_instruction_delta` | `candidate_true_instructions - target_true_instructions` | The padding-safe `instruction_delta`; can be nonzero when `instruction_delta` reads zero |
| `instruction_count_verified` | Whether both true counts were read from the objects' own ELF `.text` sections | Distinguish a byte-exact measurement from the disassembly-based fallback |
| `candidate_frame_size` | First `addiu sp,sp,N` adjustment | Stack topology |
| `candidate_stack_offsets` | Histogram of `N(sp)` operands | Spill and local-home comparison |
| `candidate_fp_register_uses` | Histogram of FP operands | Promotion/allocation comparison |
| `verdict` | Product-level classification of the evidence | Decide whether to edit source, trace allocation, or verify the link |
| `raw_difference_breakdown` | Why literal words differ | Separate instruction bits from relocation-controlled words |
| `relocation_target_mismatches` | Positional relocation symbol/addend differences | Explain why a linked-function match can still fail the local scratch-score proxy |
| `diff_sites` | Every differing site with its class | Read the residual without the verdict filtering it |
| `diff_site_classes` | Count of differing sites per class | See the mechanism mix at a glance |
| `structural_exact` | Opcode, normalized shape, registers, frame, and count agree | Cross-ROM/compiler-lineage evidence only |
| `accepted` | Whether this invocation satisfies `--fail-on-mismatch` | Automation for `compare` and `compare-dumps` |
| `acceptance_basis` | `function-exact`, `cross-rom-structural`, or `mismatch` | Explain why the command accepted or rejected the comparison |

`instruction-words-identical` means the selected function's raw instruction
words and known relocation-kind layout agree. It does not claim that the whole
object file, symbol table, or final ROM is byte-identical.

## The true instruction count, and why the padded one lies

`target_instructions`/`candidate_instructions` (`insns=`/`target_insns=`) are
the number of instruction *words compared* -- however many words objdump
disassembled. That number can include trailing padding: MIPS `.text` sections
are padded to a 16-byte, 4-instruction boundary, so a function whose real body
is not itself a multiple of four instructions has alignment filler words after
it. A whole-section comparison (no `--symbol`) disassembles that padding along
with the code, so `target_instructions`/`candidate_instructions` count it too.

The trap: two functions of *different* real length can report the *same*
padded count. A target with a 4641-instruction body padded out to 4644 words,
compared against a candidate whose real body is exactly 4644 instructions
(needing no padding at all), reports `insns=4644` on both sides -- the padded
counts agree while the real lengths differ by three. A probe three
instructions too long once passed a campaign's gate exactly this way, and
every stage after it had to re-derive the true count by hand with:

```sh
mips-linux-gnu-objdump -d obj.o | grep -c '^ *[0-9a-f]*:'
```

That command works only because GNU objdump's *default* disassembly (no
`-z`) elides a long-enough run of trailing zero bytes as `...` instead of
printing it, so alignment padding never reaches the count -- but *this tool*
always passes `-z` (it needs every word, including zero ones, to keep
addresses and relocations aligned), so it cannot get the same answer by
accident.

`target_true_instructions`/`candidate_true_instructions` are the answer to
the hand command, without running objdump a second time or depending on which
flags happened to be passed. They are always populated:

- **Read from the object's own ELF `.text` section** (`instruction_count_verified: true`) whenever a real object file is available and the
  comparison is not narrowed with `--symbol` -- the same question the hand
  command answers, for the same reason (`compare`, `diagnose`, `rank`, `score`,
  `campaign`, and anything else that reads `.o` paths).
- **Derived from the parsed disassembly** with the identical rule otherwise
  (`compare-dumps`/`diagnose-dumps`, which have no object file to read, and
  any `--symbol`-narrowed comparison, where a whole-section ELF read would
  answer "how long is the section" rather than "how long is the symbol").

The rule, either way: find the *last* `jr $ra` in the measured range, keep its
one delay-slot instruction, and drop everything after it only if it is at
least two all-zero words. That "at least two" is measured, not assumed: GNU
objdump's default disassembly still prints a *single* trailing zero word as a
real `nop` rather than eliding it, so a section that happens to end in one
genuine trailing `nop` -- needing no alignment filler at all -- is not
touched. Trimming that word anyway silently drops one real instruction from
the count, which happened on a real campaign object before the threshold was
measured against a hand-assembled fixture and locked in a regression test.

`compare`/`diagnose` print a `warning:` line, ahead of everything else, only
when `target_true_instructions != candidate_true_instructions` -- the
condition that actually invalidates a positional or per-region reading.
Whenever either side's *true* count differs from its *reported* one (padding
was found at all, even if both sides agree), a `target padding:`/`candidate
padding:` line says so in the explanation, without raising it to a warning:
padding by itself is not a problem, a true-count *mismatch* is.

## Aligned counts, and why they rank

`words=` counts positions. An inserted or deleted instruction shifts every
later position, so a candidate one edit away from the target reports a long
cascade while a candidate with a dozen unrelated allocation differences reports
a short one. That inversion misranked candidates in six recorded campaigns; in
one, positional words ranked two variants identically at 95 words when the
aligned split (10 structural versus 8) picked the only one that composed with
the next edit.

## Check what an exact function changed around itself

A selected function can be raw-word and relocation-target exact while its
source adds static storage, changes GP linker metadata, or perturbs another
function in the same translation unit. Compare the full objects separately:

```sh
decomp-workbench object collateral reference-tu.o candidate-tu.o \
  --function function_name --fail-on-collateral
```

The report inventories section sizes—including zero-fill `.bss` that has no
bytes for `objdump -s` to dump—section contents, relocations, and symbols.
With `--function`, it reports selected-function exactness as an independent
fact. `classification=outside-selected-function` means the function passed but
the containing object did not. Debug, comment, and note sections are ignored by
default; repeat `--ignore-section GLOB` to declare additional project-specific
noise explicitly.

This is a translation-unit collateral gate, not a replacement for the normal
link/map/ROM verifier.

`compare` and `compare-dumps` therefore also report the LCS-aligned residual,
computed by the same analysis `view` renders — not a second aligner:

- `aligned_total` — the ranking number while every candidate is gap-free, and
  the sum of the five class counts;
- `aligned_structural`, `aligned_schedule`, `aligned_register`,
  `aligned_constant`, `aligned_commutative` — the residual split by mechanism.

Aligned rows classed `match`, `displacement` (an encoded branch offset that
moved because something was inserted between here and there), `relocation`
(a linker-supplied field), and `pool` (the same literal-pool slot reached
through a differently named anchor) are not in the total: none of them is a
difference a source change owns. `pool_layout` — a literal-pool access that
resolves to a different slot — is reported as its own class and verdict but is
also outside the total, because the difference lives in the data section rather
than in the compared function.

`pool_resolution`, `pool_matches`, `pool_layout_mismatches`,
`target_pool_slots`, and `candidate_pool_slots` report that reading beside the
counts. See [view.md](view.md) for the two resolution tiers and what each one
does and does not claim.

Alongside them, `gaps=` (with its `aligned_insertions`/`aligned_deletions`
split) reports the alignment's own edit operations. `aligned_total ==
word_mismatches` holds exactly when a candidate is a pure register renaming;
once the aligner has inserted a gap, the candidate is aligned against a
different subsequence of the target and its aligned total is no longer on the
same scale as another candidate's. `compare` prints a one-line `caution:` in
that case, ahead of the numbers it retracts.

When instruction counts and every positional opcode agree, the stronger
evidence wins: `alignment_method=positional-opcode` locks row N to row N and
bypasses LCS. This prevents repeated sibling blocks from manufacturing gaps
and false structure/constant guidance in a pure register-allocation residual.
Other shapes retain `alignment_method=lcs`.

Late-stage JSON also carries `pool_exact`, `pool_prefix_exact`,
`temp_prefix_exact`, `first_temp_divergence`, and `first_divergent_row`.
Prefix values are aligned object rows; `null` means that lane never diverged.

**What it costs.** The alignment is quadratic in the worst case and runs once
per comparison. Measured on a synthetic function with one inserted instruction
and one recolored register: 500 instructions 0.02 s, 1500 0.10 s, 3000 0.29 s,
for the whole comparison. Those are per-candidate costs against a compile, and
in that same 1500-instruction case the positional count is 1106 and the aligned
residual is 2 — which is the number the ranking needed.

The sort order for `rank`, `campaign`, and `compile-rank` is the aligned
residual first, then exact word mismatches, unknown and mismatched relocation
metadata, normalized distance, register mismatches, instruction-count delta,
then path. `words=` still decides between two candidates of the same aligned
shape, where it is exactly the right question, and `words=0` with
`exact=true` remains the only matching claim. This is a convenient default, not
a claim that one scalar ordering captures every useful transition.

## Ask a question and read the exit code: `--census`

`compare`, `compare-dumps`, `view`, and `view-dumps` accept predicates over the
keys they already report:

```sh
decomp-workbench compare target.o candidate.o --symbol texDPTextures \
  --census aligned_register=0,frame=-128
```

```text
census: PASS aligned_register=0
census: FAIL frame=-128 (actual -96)
```

One `KEY=VALUE` per predicate, comma-separated, and `--census` may be repeated.
A comma only separates entries when what follows it starts another `KEY=`, so a
value that contains one — `verdict=mixed(constant:1, register:2)` — survives.

| Status | Meaning |
|---|---|
| `0` | the report was produced and every predicate held |
| `3` | the report was produced and at least one predicate failed |
| `2` | the census could not be evaluated: bad syntax, an unknown key, a key this run did not produce, a non-scalar key, or a value of the wrong type |

`3` is deliberately not `1`. `--fail-on-mismatch` already answers with `1` and
means "this candidate is not a match"; the two questions are independent,
because a variant can be exactly the shape you are looking for and still not be
the match. When both are passed and a predicate fails, the status is `3`.

Any key the command reports can be named, including the deprecated JSON
spellings for as long as they are emitted; `--explain-keys` prints the list.
Keys whose value is a list or an object (`diff_sites`, `hunks`, `lanes`) are
refused rather than silently compared. Values are compared by the reported
type: `exact=true` reads a boolean, `frame=-0x80` reads an integer in any base,
`target_frame=none` reads a missing value, and a verdict compares as text.

Predicates are checked against the registry **before** the inputs are read, so
a misspelled key in a 2500-variant sweep costs one process, not one compile.
That is the point of the feature: campaign agents rebuilt this filter as an
objdump-and-regular-expression layer at least seven times in one day, and the
regular expression version keyed on the wrong thing at least once.

```sh
# Keep only the variants whose register residual is gone.
for object in build/variants/*.o; do
    decomp-workbench compare target.o "$object" --symbol texDPTextures \
      --census aligned_register=0 >/dev/null && echo "$object"
done
```

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

`relocation_target_mismatches` separately compares kind plus symbol/addend
targets. It does not change generic linked-function exactness because two
spellings may resolve to the same linked address. `check-scratch` requires it
to be zero, together with raw instruction identity, for its local zero-score
proxy.
`relocation_target_differences` is the corresponding receipt: each record
includes the instruction and relocation indices plus both sides' instruction
offset, relocation offset, type, symbol, parsed addend, and original target
spelling. `check-scratch` prints these records directly, so a relocation-only
rejection no longer requires a second hand-written objdump parser.

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

## Before the metrics: length and phase

Two facts decide what the numbers above are numbers *about*, and both are
invisible to a position-indexed comparison. `align` reports the edit script
between the two streams, so an object that is one instruction longer reads as
"one instruction away" rather than as a four-figure cascade. `phase` reports
the scratch-ring coset per named row slot, so a residual that is a global
register renaming is never mistaken for a list of mistakes -- nor recorded as a
win on the quotiented number. See
[Shift-tolerant diffs and the ring phase](shift-and-phase.md).
