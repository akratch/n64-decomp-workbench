# Choose a workflow

Start with object comparison. Move into compiler diagnostics only after the
instruction structure is close.

**If you have both objects in front of you, you do not have to choose from this
page.** `next` reads the current comparison and prints the steps in priority
order, each as a runnable command with your real paths already in it:

```sh
decomp-workbench next target.o candidate.o --src work.c
```

This page is the map behind that router: it says which symptom belongs to which
family, and what each family costs.

## Command names

Three shapes, and the shape tells you what kind of thing it is:

| Shape | Reads | Examples |
|---|---|---|
| a bare verb | two objects, or one | `compare`, `view`, `align`, `phase`, `score`, `slots`, `next` |
| `trace-*` | a log an instrumented compiler wrote | `trace-cascade`, `trace-order`, `trace-blocks` |
| `probe-*` | your C source, answering one question about it | `probe-equiv`, `probe-deadread`, `probe-lines` |
| `sweep <verb>` | your C source, and writes a family of variants | `sweep regress`, `sweep carriers`, `sweep fuse` |

`trace-*` needs an instrumented toolchain and `probe-*`/`sweep` needs nothing
but the source, which is the practical difference between them: a probe costs
seconds, a trace costs a compiler build.

Grouped spellings work everywhere and mean the same command: `trace cascade` is
`trace-cascade`, `sweep regress` is `sweep-regress`, `object slots` is `slots`.
Run `decomp-workbench commands` for the whole map, or `decomp-workbench trace`
(any group name, no arguments) for one family.

## Downloaded decomp.me scratch

```sh
decomp-workbench doctor "/path/to/scratch.zip"
decomp-workbench check-scratch "/path/to/scratch.zip" --show-diff
```

This validates the handoff, reports the browser score as context, and compares
the site's own target/current objects. Add `--compile-command` when you need to
test a local candidate with the site's context and source-line reset. See
[decomp.me export checking](decompme-exports.md).

## Object mismatch

```sh
decomp-workbench diagnose target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump
```

| Result | Interpretation |
|---|---|
| Count, opcode, or normalized shape differs | Source/control-flow problem |
| Shape matches; register ranges differ | Allocation or live-range problem |
| Only raw words differ | Likely relocation-controlled fields |
| `exact=true` | Function-level comparison passed |

`diagnose` disassembles each input once and renders the comparison plus
decisive aligned hunk. Use `compare` alone for a compact gate,
`--fail-on-mismatch` in automation, and `view --show-all` for full evidence.
See [Object comparison](object-comparison.md).

## The counts differ, or the mismatch looks impossibly large

A candidate that emits one extra instruction is compared row against row, so
every row after the insertion is charged too. Four figures of mismatch can be
one inserted `nop`. Before reading any hunk, read the shift:

```sh
decomp-workbench align target.o candidate.o
```

`align` prints the edit script — replaced, inserted, deleted, and the target
rows each block lands at — and one number, `away`, which is the instructions a
source change actually has to move. Pass several candidates for a census
ordered by that number.

If the residual is float-heavy and the rows differ in *every* register, the
candidate may not be wrong but rotated — the same values in the same scratch
ring, starting one register along:

```sh
decomp-workbench phase target.o candidate.o --slots head=1..2038,body=2039..4641
```

`phase` prints, per slot, the ring coset that would make it match **and** the
positional count it really scores. Rank on the second: a quotiented number is
not progress the object has made. See [Shift and phase](shift-and-phase.md).

For the one number that is the matching gate, plus the screen line
(`sha ni frame ld st coset`) that identifies a candidate in a sweep column:

```sh
decomp-workbench score target.o candidate.o
```

See [score and matrix](score-and-matrix.md).

## Mechanism diagnosis

When the residual is small but the layer that owns it is unclear, or when the
count looks large because the streams are shifted:

```sh
decomp-workbench view target.o candidate.o --function function_name
```

The output aligns the two streams, classifies every hunk, prints the per-class
register lanes (including the matching instructions), reports where the byte
prefix ends, and names the lever family. `view-dumps` runs the same analysis on
retained objdump text. See [Aligned mechanism view](view.md).

## Candidate search

Use `campaign` once you can compile one arbitrary source path to one output
path:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --jobs 8
```

Change one source dimension per campaign. Declare behavior-changing compiler
variables with `--env` so they enter the cache key. See
[Candidate campaigns](campaigns.md).

The manifest and ledger are default state. Use `campaign status`, `note`,
`resume`, and `export` to continue the same experimental question. Validate an
external generator's parameter sidecar with `experiment validate` before
attaching it through `--experiment-manifest`.

## Before you blame the allocator

Two source questions cost seconds and have each closed a residual that five
stages spent on the register allocator. Ask them first.

*Are these two differently-spelled expressions the same value?* A local whose
address never escapes cannot be written by a callee, so between two of its
definitions every read of it is one value:

```sh
decomp-workbench probe-equiv work.c --variable sp4B8 --at 920 --at 991
```

*Where can a statement that emits no instructions still change the
allocation?* A discarded read has zero footprint and a real effect on web
structure:

```sh
decomp-workbench probe-deadread work.c --variable sp4B8
```

*What would a fusion donor cost?* The price of a donor is the number of rows
that touch its stack slot, which is a census over the object, not a build:

```sh
decomp-workbench slots target.o
```

`slots` prints each slot both sp-relative and as the frame offset the allocator
trace keys a site by, so its output is what the cascade commands below take.
See [Source probes](source-probes.md).

## Register-allocation mismatch

If you have a CDX log from an instrumented build, start at the site, not at the
summary. A site is named by its frame offset, which a rebase does not move:

```sh
decomp-workbench trace-cascade build.ilog --frame-offset 0xfffffdf8
```

- `trace-cascade` — every round of one site's decision cascade, the colour it
  actually received, and each decision as the one inequality it is. `--against
  OTHER.ilog` diffs the same site in two builds; `--kill` reduces it to one
  line for a sweep column.
- `trace-order` — the p1 colouring order, with the same-save ties named.
- `trace-blocks` — which webs occur in which basic blocks, and where the sets
  meet.

See [The allocator decision cascade](cdx-cascade.md) and
[The p1 decision arithmetic](p1-decision-arithmetic.md).

For a log from the older parsers, summarize it first:

```sh
decomp-workbench trace-summary compiler.stderr --json
```

Then choose the specific parser:

- `trace-globalcolor` for live-range costs and color/split decisions;
- `trace-alias` for base provenance and alias queries;
- `trace-fifo` for temp-register allocation and reuse.
- `trace-webs` for semantic alignment across source variants;
- `trace-source` for marker-aware source/listing correlation;
- `trace-stack-homes` for virtual-home ownership.

Use a tracing-off object comparison and a trace-on positive control before
interpreting the result — and record the identity gate so a later reader knows
the trace was trustworthy:

```sh
decomp-workbench instrument gate --stock stock.o --instrumented cdx.o \
  --profile uopt-cdx --stamp gates/uopt-cdx.json
```

See [Trace analysis](trace-analysis.md).

## Price the levers you already added, and sweep the next one

Every stage inherits its predecessor's construction and attacks only the
residue, so nobody ever prices what is already there. Run the removal lattice
first, not last:

```sh
decomp-workbench sweep regress work.c \
  --construct 920..921=hoist --construct 977=deadread --write regress/
```

The rest of the family generates one variant per lever of a kind:

- `sweep carriers` — which locals are dead at a site, and therefore free;
- `sweep hoist` — hoist an operand into every available carrier;
- `sweep commute` — exchange every commutative operand pair;
- `sweep copies` — drop a copy and rehost its reads on the original;
- `sweep donors` — the locals whose live range avoids a fusion target's;
- `sweep fuse` — fuse a donor's live range into the target's.

Each stops at the source. Build the variants with the project's own
compile-one wrapper, then read them back honestly — with the coverage claim
the run is actually entitled to:

```sh
decomp-workbench sweep ingest regress/ --objects build/ --target target.o
```

Every list-valued option has a `--OPTION-from FILE` sibling. Use it: zsh does
not word-split a shell variable, so `--construct $LIST` arrives as one
argument. See [Sweeps](sweeps.md).

## You inherited a campaign directory with no manifest

```sh
decomp-workbench campaign survey path/to/campaign/
```

A survey is a reading of the directory as it is now — stages, counts, the
newest artifacts, the findings log, and whether any instrument gate was ever
recorded. Nothing is stored, so nothing in it can be a stale claim. If several
people or agents append findings to one log, reserve identifiers before you
write them:

```sh
decomp-workbench note reserve --log WORKBENCH-IMPROVEMENTS.md --count 3
```

See [Candidate campaigns](campaigns.md) and [Shared notes](shared-notes.md).

## Adding code breaks the ROM even though everything matches

The match gate proves the bytes at one layout. It cannot prove that the
addresses in those bytes are *references*, because a linked ROM keeps no
relocations and a literal `0x80123456` and a resolved symbol at `0x80123456`
are the same four bytes. Start with the inventory, which costs one pass over
a map and an image and builds nothing:

```sh
decomp-workbench shift audit --map build/game.map --image build/game.z64 \
  --pins ver/symbols/undefined_syms.txt --blob .assets
```

That says which of your pinned addresses follow the layout
(`gMainMemoryPool = main_BSS_END`) and which are written down
(`D_B0000574 = 0xB0000574`), and ranks every word in the image holding a
value inside the range an insertion would move. Its tiers rank how confidently
a word is an address reference, never how dangerous it is.

To find out which of those references a shift actually moves, relink the same
objects against a padded script and let the two images referee it:

```sh
decomp-workbench shift rehearse orchestrate --wrapper tools/relink.sh \
  --ld-script mods/game.custom.ld --anchor-object build/src/hasm/entrypoint.s.o \
  --deltas 0x10,0x40 --workdir .workbench/rehearsal \
  --census unexplained_changed=0,stale_confirmed=0
```

Two deltas, not one: a partially symbolized reference can encode correctly at
one shift by coincidence. `stale_confirmed` is a word the audit ranked high
that the relink did not move — the strongest available evidence for a
hardcoded pointer, with the symbol it should have been named beside it. See
[Shiftability](shiftability.md).

## A shifted or modded build boots wrong and the ROM verifies clean

Same family, read from the other end. A `Verify: OK` against the retail
cartridge says nothing about provenance — in this campaign's gate a one-line
hardcoded pointer passed exactly that check. If the project checksums any of
its own functions at run time, declare the pairs so the rehearsal can apply
the consistency rule to them:

```sh
decomp-workbench shift rehearse analyze \
  --base-map base/game.map --base-image base/game.z64 \
  --shifted-map shifted/game.map --shifted-image shifted/game.z64 \
  --delta 0x10 --crc-words 0x10,0x14 \
  --checksum-pair race_check_finish=gRaceCheckFinishChecksum
```

A `checksum-stale` verdict means a protected function's body changed and its
checksum word did not. Read it alongside whether your build runs its post-link
patcher and whether the runtime check is even compiled into this
configuration. See [Shiftability](shiftability.md) and
[Trap 7](metric-traps.md#trap-7-byte-identity-does-not-prove-address-provenance).

## Late scheduling mismatch

First decide which layer owns the order. If the instruction multiset and the
allocator lanes already agree, ask whether statement *line assignment* owns it
before you ask which compiler build did — that question costs one
token-identical variant plus a control:

```sh
decomp-workbench probe-lines unit.i \
  --compile-command '/ido/cc -c -O2 -mips2 {input} -o {output}' \
  --function drawBitmap --target-object target.o
```

A `LINE-SENSITIVE` verdict routes onward to `--tie STATEMENT=LINE`, which
scores one statement's reassigned line number toward and away from the target.
See [Line-assignment probe](line-assignment-probe.md).

If the retained ugen listing is right but the final schedule is not, replay the
downstream passes:

```sh
decomp-workbench replay-as1 unit.s control.o \
  --as0-command '/ido/as0 ... {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 ... {binasm} -o {object} -t {symtab}'
```

The unedited replay must reproduce the normal object. After that, test one
uniquely matched `--insert-before` or `--insert-after` edit. See
[Pass replay](pass-replay.md).

## Static-recompiled IDO instrumentation

Use the generic `instrument-ugen` command for shallow function and free-list
tracing. Use `instrument-uopt` for the packaged IDO 5.3 alias/globalcolor
profiles.

Do not bypass a hash rejection for routine use. A different generated source
needs reviewed anchors and the full fidelity checks in
[Compiler instrumentation](compiler-instrumentation.md).

## Calibrated allocator cause

Only after ordinary source families and pass ownership are exhausted:

```sh
decomp-workbench oracle plan focused.cdx
decomp-workbench oracle force candidate.c \
  --trace focused.cdx \
  --target target.o \
  --toolchain .decomp-workbench/toolchains/ido53-cdx \
  --compile-command './compile-one.sh {source} -o {output}' \
  --symbol function_name \
  --force p2:w55=c2
```

If controlled single-force deltas identify an interaction, pass the distinct
web controls together (for example
`--force p1:w9=c4,p1:w14=c2,p2:w55=c14`). The persisted row includes the
baseline-to-forced changed instructions under `emitted_effect`; those are
object-level role clues, not source attribution.

Planning reports both allocator phases and measured endpoints. Force/sweep
requires a ready, intact real-copy toolchain and persists its evidence for
`oracle status/export`. An exact forced build is a source-level hypothesis,
never a final match. See [Allocator oracle](oracle.md).

## Stop conditions

- A ranking score is search guidance, not a match.
- `exact=true` is a function-level object result, not semantic or project-wide
  proof.
- A forced compiler choice is a causal test, not an acceptable final compiler.
- Finish with the project’s normal collateral and full ROM or binary checks.
