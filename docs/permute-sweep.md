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

The command forces the parts that are not opinions: the codegen flags come
from the build itself, the post-compile chain is replicated into the scratch,
and `--stack-diffs` is always passed.

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
| `--load-threshold X` | wait for the one-minute load average to drop below `X` before each launch |
| `--extend-minutes N` | re-seed once from the best candidate, but only when the run hit its cap with its best result in the final third of the window |
| `--resume` | skip functions already recorded in the output directory's summary |
| `--limit N`, `--function NAME` | narrow the queue |
| `--list`, `--dry-run` | print the ordered queue and the resolved limits, and stop |
| `--permuter-arg ARG` | forward one argument to `permuter.py` (repeatable) |
| `--require-fresh` | refuse to run unless the ranking's stamp matches HEAD |

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
`stamp` key; the rows are untouched, and both ranking spellings (a bare list
or an object with `functions`) survive it. Re-stamping the same tree keeps the
original `generated_at` -- that field says when the measurement was taken, and
a timestamp refreshed on every run cannot say that. `check` exits 0 when the
stamp matches HEAD and 1 otherwise.

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
function                           base   best  zero  ext  flags      time
func_8001A154                       214      0  yes   no   real          75s
func_80012574                        18      2  no    yes  real        1215s
```

`flags` is the column to read first. `FALLBACK` means the codegen flags were
*not* recovered from the build, so that row searched whatever the fallback
named — possibly the wrong ISA, and possibly for hours.

Each function also keeps its own directory: `recipe.txt` (the flags, their
origin, every replicated and every skipped post-compile step), the settings
file, the import and permuter logs, and the scratch itself.

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
  base            compiles, score 18
  verdict         ready
```

It answers the three questions a sweep cannot recover from getting wrong:
are these the flags the real build uses, does the scratch replicate the
post-compile chain, and does the base compile to a finite non-zero score. A
base that already scores 0 is not scoring the function under test at all —
it would report an instant "match" that does not rebuild. Exit status is 0
when ready and 1 when not.

## Reading a sweep's results as evidence

A near-match the permuter cannot move in a full window, with the base score
flat from the first minutes, is a different animal from one whose score is
still descending at the cap. The first is a candidate for allocator or
scheduler analysis; the second just wants more time. Do not conclude that a
register or schedule tie is unmatchable before a sweep has actually run on
it with real flags — that conclusion has been wrong often enough to be worth
a rule.

[permuter]: https://github.com/simonlindholm/decomp-permuter
