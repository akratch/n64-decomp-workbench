# Candidate campaigns

`campaign` is the repeatable replacement for a directory of single-purpose
compile loops.

## Run a campaign

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --compile-command './compile.sh {source} -o {output}' \
  --compile-cwd /path/to/project \
  --objdump /path/to/mips64-elf-objdump \
  --jobs 8 \
  --cache-dir .workbench/cache \
  --ledger .workbench/campaign.jsonl \
  --keep-objects .workbench/top-objects
```

`{source}` and `{output}` are required. The template is split with `shlex` and
executed directly; shell expansion, pipes, redirection, and command
substitution are not evaluated.

## Throughput

A variant costs one compiler process and one objdump process. The comparison
itself runs in process — `campaign` calls the comparator directly and never
spawns a `compare` subprocess per candidate — and the reference object is
disassembled once for the whole campaign rather than once per variant.

On a fast compiler (an IDO wrapper is roughly 0.07 s per translation unit) the
per-variant overhead used to dominate the compile; removing the repeated target
disassembly and the comparison subprocess is why a large grid is now worth
running through `campaign` instead of a hand-rolled import harness.

## Stopping on the first exact match

`--stop-on-exact` is the default: once a candidate compares exact, no further
candidates are submitted. Candidates already in flight (up to `--jobs` of them)
finish and are recorded, so the ledger keeps one record for every candidate
that actually ran and none for candidates that never started. The terminal
report names how many prepared candidates were skipped, and `--json-summary`
carries `stopped_on_exact` and `prepared_candidates`.

Pass `--no-stop-on-exact` when the point of the run is the whole grid — basin
census, per-family comparison, or a corpus that later differential work will
reuse.

Compiler processes normally inherit the directory in which the workbench was
started. Use `--compile-cwd` when a project wrapper expects relative include,
tool, or configuration paths. The resolved directory is recorded in
provenance and participates in the cache key.

## What is recorded

Each JSONL record includes:

- source path;
- rendered compiler command;
- compiler working directory;
- explicit compiler environment;
- source, target, directly invoked compiler/wrapper, and objdump identities in
  the cache key;
- compiler stdout, stderr, exit status, and duration;
- cache status;
- comparison metrics and object hashes;
- paths that produced the same prepared key, when applicable.

The directly invoked wrapper is hashed when it is a file. A wrapper may invoke
additional binaries or read configuration that the workbench cannot discover.
For complete reproducibility, put those versions in the wrapper’s own output or
campaign metadata.

Source paths intentionally remain in prepared keys even when file content is
equal. Some wrappers change behavior by path and some object formats embed
source paths. Passing the same prepared source more than once is deduplicated;
different paths are treated as distinct candidates.

## Process ownership

Every compiler runs in its own process group (`start_new_session` on POSIX, a
new process group on Windows), and the campaign ends that group — the wrapper
and everything it started — when the run fails or is interrupted. A compiler
wrapper that starts an assembler, a parallel search, or any other helper
therefore cannot outlive its campaign. A leaked parallel job did exactly that
in the field and degraded two later runs before the next campaign started.

Interrupting a campaign (`Ctrl-C`) cancels queued candidates, terminates
running compilers with their children, and re-raises. Records already written
to the ledger stay valid.

## Environment-sensitive compilers

Pass instrumentation and behavioral controls frequently use environment
variables. Declare them explicitly so they become part of the cache key:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --compile-command './compile.sh {source} -o {output}' \
  --env CDX_LOG=1 \
  --env CDX_PROC=3
```

Inherited environment variables are passed to the compiler but not all are
hashed. Avoid relying on undeclared environment state for a scientific
campaign.

## Reading campaign results

Keep several axes visible:

1. instruction count and frame size;
2. exact or relocation-aware word mismatches;
3. insertion/deletion/reorder penalties from the project’s native diff tool;
4. opcode and normalized structure;
5. register and FP-register ranges;
6. trace signature when candidates enter the same structural basin.

A candidate with a numerically worse score can still remove structural
differences and leave only a register permutation. Inspect individual metrics,
not only rank.

Campaign output uses the same metric registry as `compare`: the printed label
and the JSON key are one string, and `decomp-workbench campaign --explain-keys`
prints the mapping (including the deprecated long-form keys still emitted for
one release).

Use `--json-summary` for automation that only needs ranking metrics, hashes,
cache status, and retained-object paths. Unlike the full `--json` report, it
omits compiler streams, stack/register histograms, and instruction-level
register diffs, which can be very large for structurally distant candidates.

Campaign output also reports **object basins**: distinct source variants that
compiled to the same compared function bytes. Use `--show-basins` to list the
member source files, or consume `object_basins` from `--json-summary`. This is
especially useful for declaration-order, folded-condition, and expression-form
grids, where hundreds of source spellings may collapse to a handful of real
allocator outcomes.

The first member and `best_metrics` in each basin are the best-ranked
comparison in that basin, not the alphabetically first source. Basin identity
is based on raw words for the selected function; relocation-layout metrics
remain visible in the representative comparison.

## Writing transformation generators

Keep generators separate from the campaign runner. A generator should:

- start from a pinned source template;
- make one named transformation or a documented Cartesian product;
- emit deterministic filenames;
- include transformation parameters in a sidecar manifest or source comment;
- avoid editing the active project translation unit in place.

Useful transformation families include declaration order, expression
tree/order, statement split/merge, control-flow spelling, local reuse, literal
type, and live-range boundary changes. Their effect is compiler- and
function-specific.

## Cache hygiene

Objects are content-addressed under `--cache-dir`. Removing the cache is safe
but forces recompilation. The ledger is append-only so interrupted runs retain
completed records. Use a new ledger for a materially different experimental
question, even when the cache can be reused.
