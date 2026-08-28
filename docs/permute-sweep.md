# Permuter sweeps

`decomp-workbench permute-sweep` drives [decomp-permuter][permuter] over a
queue of functions. It exists because every project ends up writing this batch
loop, and each rewrite re-introduces the same three faults — each of which
makes the search answer a question nobody asked.

| Fault | What the operator sees | What is actually wrong |
|---|---|---|
| The scratch searches the wrong ISA | "8 of 12 targets found nothing instantly" — read as *hard functions* | The importer defaults to `-mips1`; the project builds `-mips2` |
| The scratch object is not the real object | A score of 0 that does not survive the real build | The build applies a post-compile `objcopy` the scratch never ran |
| The score is normalized | A "match" whose rebuild differs | Without `--stack-diffs` a spill at the wrong slot scores 0 |
| The scratch compiles a different function | A score of 0 whose frame is wrong by 8 bytes | The importer replaced the file's macros with stubs of its own |

The command forces the parts that are not opinions: the codegen flags come
from the build itself, the post-compile chain is replicated into the scratch,
`--stack-diffs` is always passed, and the scratch object is measured against
the object the project's own build produces before a window is spent on it.

## What it does not do

It does not promote. A scratch score of 0 is a *candidate*: proving it means
splicing it into the project's source, rebuilding with the authoritative
toolchain and byte-comparing, and that path is specific to the project that
owns the build. The sweep reports; the project's own tooling promotes.

It also does not discover the queue. Which functions are unmatched is a
project convention — an `#ifdef NON_MATCHING` guard, an objdiff report, a
ranking — so the queue is an input.

## Configure the project once

Add a `[permuter]` table to `.decomp-workbench.toml`
(see [Project configuration](project-configuration.md)):

```toml
[permuter]
make = "gmake"
permuter_dir = "tools/permuter"
object_template = "build/{source}.o"
compiler_marker = "tools/ido/cc"
compiler_command = "tools/ido/cc -c -non_shared -G 0 -I include -DVERSION_us"
assembler_command = "tools/binutils/mips64-elf-as -march=vr4300 -32 -G0"
preserve_macros = ["g[DS]P.*=void", "OS_PHYSICAL_TO_K0=void *"]
preserve_macro_modes = ["configured", "none"]
fallback_flags = ["-O2", "-mips2", "-32"]
ranking = "config/ranking.json"
output_dir = ".decomp-workbench/permute"
minutes = 20
load_threshold = 9.0
```

`compiler_command` is the *invariant* half of the compile line: the base
arguments, the includes, the defines. The codegen flags are never written
here — they are recovered per object from the build, because a static flag
table is wrong exactly when it matters. One Mickey translation unit that
looked entirely default carried `-Wab,-r4300_mul`; only the build's own dry
run knew.


## The scratch has to be the object the build produces

The three faults above are about the *recipe*. There is a fourth about the
*source*, and it is the quietest of them.

decomp-permuter's `import.py` does not hand your translation unit to the
compiler. It preprocesses it first, and for every macro named in
`[preserve_macros]` it hides the real definition and injects a stub of its own
through `#pragma _permuter latedefine` — which is what lets the permuter
permute *inside* a macro call instead of treating it as opaque text. Where the
stub expands to what the real macro expands to, this costs nothing. Where it
does not — the N64 `gDP*`/`gSP*` display-list macros are the standard case,
along with `_SHIFTL` and its relatives — the scratch compiles a different
function. On Mickey's `particles.c` `func_80041CE4` the scratch takes a -136
frame where the build takes -128, and every score measured on it is a score
about code the build never emits.

So the sweep checks. After each import it compiles the scratch's unmodified
base through the scratch's *own* `compile.sh` — the one carrying the recovered
flags and the replicated `objcopy` chain — and compares that object with the
project's object for the same translation unit, through the same object oracle
`compare` uses (see [Object comparison](object-comparison.md)).

```text
scratch object  identical [configured]
scratch object  differs(4 words) [none]
scratch object  unknown
```

| Verdict | Meaning |
|---|---|
| `identical` | the scratch's object carries the same words for this function as the build's. A score of 0 here is a score of 0 in the build |
| `differs(N words)` | it does not. The search will answer a question about a different function, and a loud `WARNING:` says so |
| `unknown` | the comparison could not be made: the project's object is not built, no objdump was found, or the base did not compile. Not a verdict about the function |
| `unchecked` | `--no-fidelity` |

The comparison is the *function's* words, not the sections. A scratch holds
one pruned function where the project object holds a whole translation unit,
so their `.data` and `.rodata` differ for reasons that have nothing to do with
codegen; comparing them would report a difference on every function. What does
carry across is the function's instruction words and the relocations they name,
and that is exactly where a macro expanding differently shows up — as a
different frame, a different schedule, or a different symbol being read.

### Repairing it: fewer preserved macros

When the scratch differs *and* the importer actually preserved macros (it says
so in `import.log`, and the sweep reads it), the import is retried with a
narrower preserved set, and the first mode whose object is identical wins:

```toml
[permuter]
preserve_macro_modes = ["configured", "none"]
```

| Mode | What it imports |
|---|---|
| `configured` | the project's own `[preserve_macros]` set |
| `none` | nothing preserved, so the translation unit's real header macros expand into the scratch exactly as they expand in the build |
| anything else | a narrowing regex, handed to `import.py --preserve-macros` with the project's type table still in place |

`none` is a real trade, not a free win: with nothing preserved the permuter
cannot permute inside those macro calls — a display-list write is opaque text
to it. That is the right price. A search that can reach inside a macro call in
an object the build never emits reaches nowhere.

Two modes that reach `import.py` identically are collapsed, so a project with
no `[preserve_macros]` imports once rather than importing twice to compare a
scratch with itself. A scratch that differs having preserved *nothing* is not
retried at all: whatever it differs by, a narrower preserve set is the same
import again. An import log that does not say either way is retried, because
"it did not say" rules nothing out; the recorded `preserved_macros` is `null`
there rather than an empty list. And when no mode is identical, the smallest measured difference
is kept — `configured` winning ties — and re-imported if it was not the one
left on disk.

`--require-fidelity` turns a non-`identical` verdict into a refusal, for the
runs where a score about the wrong object is worse than no score. It refuses
having spent the import and nothing else. `--no-fidelity` skips the check
entirely, for a project that cannot build the object to compare against.

## The queue

JSON, or one row per line:

```json
[
  {"function": "func_8001A154", "source": "src/game/track.c",
   "asm": "asm/nonmatchings/track/func_8001A154.s"}
]
```

```text
func_8001A154 src/game/track.c asm/nonmatchings/track/func_8001A154.s
```

| Key | Meaning |
|---|---|
| `function` | the C symbol the permuter searches |
| `source` | the C file holding it, relative to the project root |
| `asm` | the target assembly for that function |
| `object` | the Make object target, when `object_template` cannot derive it |
| `asm_symbol` | the name the target assembly uses, when it differs from `function` |

`asm_symbol` covers the overlay-naming case: a disassembler that names a
function from the address it was extracted at, where the C source uses the
name a human gave it. The label is renamed in the sweep's own copy of the
assembly; the project's extracted assembly is never modified, and no
instruction word is touched.

## Run it

```sh
decomp-workbench permute-sweep queue.json --ranking ranking.json --dry-run
decomp-workbench permute-sweep queue.json --ranking ranking.json --minutes 20
decomp-workbench permute-sweep queue.json --resume
```

Ordering is closest-first by the ranking's `differing_words`. A function the
ranking does not mention runs **last**: unranked means unmeasured, not close,
and a sweep that spends its first hours on unmeasured functions reports
"queue exhausted" having never reached the near-matches.

| Option | Effect |
|---|---|
| `--minutes N` | per-function wall-clock cap |
| `--jobs N` / `--threads N` | concurrent functions, and permuter threads each |
| `--load-threshold X` | wait for the one-minute load average to drop below `X` before each launch. POSIX only: a host with no load average cannot gate, and the sweep says so once instead of pretending it did |
| `--extend-minutes N` | re-seed once from the best candidate, but only when the run hit its cap with its best result in the final third of the window |
| `--resume` | skip the functions a previous run in this output directory actually searched; a row that errored is retried, because nothing was measured about it |
| `--limit N`, `--function NAME` | narrow the queue |
| `--list`, `--dry-run` | print the ordered queue and the resolved limits, and stop |
| `--permuter-arg ARG` | forward one argument to `permuter.py` (repeatable) |
| `--require-fresh` | refuse to run unless the ranking's stamp matches HEAD |
| `--require-fidelity` | refuse a function whose scratch object is not the object the build produces |
| `--no-fidelity` | skip the scratch-fidelity check |
| `--objdump EXE` | the disassembler the fidelity comparison uses (default: `object.objdump`) |

`--extend-minutes` is a trend test, not a time budget. A search whose best
result landed early and then sat has plateaued, and a second window buys
nothing; only a search still descending when the clock stopped it is
re-seeded.

## The ranking is a measurement, and it decays

The ordering above is only as good as the ranking behind it, and a ranking
describes one tree. Every function that matches and every edit that moves a
word changes what it says; one campaign's snapshot was still being read as an
ownership ledger hours after two of the functions in it had already matched.

So stamp it where it is produced, and check it where it is consumed:

```sh
decomp-workbench ranking stamp config/ranking.json
decomp-workbench ranking check config/ranking.json
```

`stamp` records the project's `git rev-parse HEAD` and the time, as one added
`stamp` key, and rewrites the file atomically. The rows are untouched, and both
ranking spellings are accepted -- but a ranking written as a bare list comes
back wrapped as `{"functions": [...], "stamp": {...}}`, because JSON has
nowhere to hang a key on a list. Every reader here takes both spellings; a
project script that re-reads its own ranking as `payload[0]` does not.
Re-stamping the same tree keeps the original `generated_at` -- that field says
when the measurement was taken, and a timestamp refreshed on every run cannot
say that. `check` exits 0 when the stamp matches HEAD and 1 otherwise.

The stamp compares commits, so a ranking measured against a *dirty* worktree
reads as `fresh` until the edits are committed. `fresh` means "the same commit",
not "nothing has changed since".

| Status | Meaning |
|---|---|
| `fresh` | the stamp is this tree; the ordering is a measurement of what you are looking at |
| `stale` | the stamp names a different tree; the ordering describes a tree that no longer exists |
| `unstamped` | no stamp, so the drift cannot be measured |
| `unknown` | stamped, but HEAD could not be read (not a checkout), so the two cannot be compared |
| `missing` | there is no ranking at that path |

`permute-sweep` and `permute-doctor` run that check on whichever ranking they
were given. A contradiction -- `stale`, or `unknown` -- prints a loud
`WARNING:`; an unstamped ranking gets a quiet `note:`, because unstamped is
where every project starts and a warning everybody sees is a warning nobody
reads. `--require-fresh` turns any non-`fresh` verdict into a refusal, for the
runs where searching in the wrong order is worse than not searching.


## What comes back

Per function, in `summary.json` (schema
`decomp-workbench-permute-sweep-v1`) and `summary.txt`:

```text
function                           base   best  zero  ext  flags     scratch         time
func_8001A154                       214      0  yes   no   real      identical        75s
func_80012574                        18      2  no    yes  real      DIFFERS/8      1215s
```

`flags` and `scratch` are the columns to read first: between them they say
whether the two score columns beside them mean anything at all. `FALLBACK` means the codegen flags were
*not* recovered from the build, so that row searched whatever the fallback
named — possibly the wrong ISA, and possibly for hours.

Each function also keeps its own directory: `recipe.txt` (the flags, their
origin, every replicated and every skipped post-compile step), the settings
file, the import and permuter logs, and the scratch itself.

Each result row carries what the classifier below reads, plus the timing it
reads it from. That timing is recorded because nothing else in the record
keeps it: decomp-permuter's output directories are overwritten, so once the
run is over there is no other way to know when its best candidate arrived.
When a run was extended, `best_output_mtime_fraction` and `hit_cap` describe
the *extension's* window -- the one that says whether the search was still
descending when it ended -- while `window_seconds` is both windows together.

| Field | Meaning |
|---|---|
| `base_score`, `best_score` | the unmodified base, and the lowest score any candidate reached (`null` when nothing beat the base) |
| `ok`, `error` | whether the scratch ran at all, and what stopped it |
| `flags_recovered` | the codegen flags came from the build, not the fallback |
| `seconds` | wall clock actually spent on this function |
| `window_seconds` | the cap it was given, extension included |
| `hit_cap` | the search was stopped by the clock rather than finishing. Reported for the reader; the classifier does not use it |
| `best_output_mtime_fraction` | where in the searched window the best candidate landed, 0.0 (first moment) to 1.0 (the last); `null` when nothing improved |
| `extended` | the run earned a re-seeded second window |
| `scratch_fidelity` | `identical`, `differs`, `unknown`, `unchecked` — see above |
| `scratch_fidelity_words` | how many words the scratch object differs by, when it differs |
| `scratch_fidelity_mode` | the preserved-macro import mode the searched scratch was built with |
| `scratch_fidelity_reason` | why the comparison could not be made, when it could not |

## Preflight one function

```sh
decomp-workbench permute-doctor func_80012574 --queue queue.json
```

```text
permute-doctor func_80012574
  source           src/game/track.c
  object           build/src/game/track.c.o
  codegen flags    -O2 -mips2 -Wab,-r4300_mul -32 [make -n]
  objcopy steps    1
    replicated     objcopy --redefine-sym A=B "$OUTPUT"
  scratch object  identical [none]
    mode          configured: differs (12 word(s))
    mode          none: identical
  base            compiles, score 18
  verdict         ready
```

It answers the four questions a sweep cannot recover from getting wrong: are
these the flags the real build uses, does the scratch replicate the
post-compile chain, is the scratch's object the object the build produces, and
does the base compile to a finite non-zero score. A base that already scores 0
is not scoring the function under test at all — it would report an instant
"match" that does not rebuild. Exit status is 0 when ready and 1 when not; a
differing scratch is a warning here rather than a refusal, unless
`--require-fidelity` is passed.

## Reading a sweep's results as evidence

A near-match the permuter cannot move in a full window, with the base score
flat from the first minutes, is a different animal from one whose score is
still descending at the cap. The first is a candidate for allocator or
scheduler analysis; the second just wants more time. Do not conclude that a
register or schedule tie is unmatchable before a sweep has actually run on
it with real flags — that conclusion has been wrong often enough to be worth
a rule.

`permute classify` makes that distinction from the record rather than from
prose:

```sh
decomp-workbench permute classify examples/fixtures/permute-summary.json
```

```text
Sweep: `examples/fixtures/permute-summary.json`

| function | class | base | best | delta | best at | elapsed | ext |
|---|---|---:|---:|---:|---:|---:|---|
| `synth_reached_zero` | MATCHED | 214 | 0 | 214 | 94% | 75s | no |
| `synth_still_descending` | P_STUCK_DESCENDING | 18 | 2 | 16 | 81% | 1215s | yes |
| `synth_plateaued` | P_STUCK_FLAT | 40 | 39 | 1 | 4% | 1200s | no |
| `synth_never_moved` | P_STUCK_FLAT | 96 | - | 0 | - | 1200s | no |
| `synth_bad_scratch` | IMPORT_FAULT | - | - | - | - | 4s | no |

| class | functions | routes to |
|---|---:|---|
| MATCHED | 1 | verify on the authoritative build, then promote |
| P_STUCK_DESCENDING | 1 | trace levers or manual work; the search is still moving |
| P_STUCK_FLAT | 2 | the pool that decides whether deeper instrumentation is worth funding |
| IMPORT_FAULT | 1 | fix the scratch (prototype conflicts, missing context, flags) |
```

`--json` emits the same classes as a document (schema
`decomp-workbench-permute-classify-v1`) with every number and the reason
behind each class; `--class NAME` narrows the report to one class.

### The four classes

| Class | Measured by | Routes to |
|---|---|---|
| `MATCHED` | `best_score == 0` | verify on the authoritative build, then promote. The sweep does not promote |
| `P_STUCK_DESCENDING` | improved on the base, **and** either the extension ran or the best candidate landed in the final third of the window | trace levers, or manual work. The search was still moving when the clock stopped it |
| `P_STUCK_FLAT` | never improved on the base, or improved only in the opening fraction of the window and then sat | the pool from which the case for deeper instrumentation is argued |
| `IMPORT_FAULT` | no base score: the scratch failed to import or compile | fix the scratch — prototype conflicts, missing context, an object target the build spells differently |

The decision rule those columns encode:

- **Only `P_STUCK_DESCENDING` routes to trace levers or a human.** The search
  is still finding improvements, so the expensive resources have something to
  work with.
- **`P_STUCK_FLAT` is a pool, not a verdict.** It is the evidence that decides
  whether a deeper instrumentation build is worth funding — a class that is
  large, on functions searched with *real* flags, is the argument for that
  spend. A single flat function is not a wall; it is one measurement.
- **`IMPORT_FAULT` is not a result about the function at all.** Nothing has
  been searched. It routes to the scratch, and `permute-doctor` is what reads
  it.

Two cautions the report prints for itself. A row whose flags were *not*
recovered describes the scratch, not the function, and is listed under the
table for that reason: a search on the wrong ISA is flat for reasons that
have nothing to do with the C. And a summary written before the sweep
recorded `best_output_mtime_fraction` cannot show that a search plateaued, so
an improvement with no timing is classed as descending — being wrong towards
`P_STUCK_FLAT` is what funds an instrumentation build for a function nobody
actually measured.

A third caution the classifier does not print, because it is not the
classifier's to make: `permute classify` reads the score columns and says
nothing about `scratch_fidelity`. A row whose scratch `differs` is a class
about a function the build does not contain, and `MATCHED` on such a row is a
candidate that will not rebuild. Read the `scratch` column before the class.

[permuter]: https://github.com/simonlindholm/decomp-permuter
