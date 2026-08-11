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
  --keep-objects .decomp-workbench/top-objects
```

`{source}` and `{output}` are required. The template is split with `shlex` and
executed directly; shell expansion, pipes, redirection, and command
substitution are not evaluated.

The normal path creates durable state automatically:

```text
.decomp-workbench/
├── cache/
└── campaigns/
    └── function_name-<identity>/
        ├── manifest.json
        └── ledger.jsonl
```

`--ledger PATH` remains available for an established external layout.
`--no-ledger` is the explicit stateless escape hatch.

## Reopen the campaign cockpit

```sh
decomp-workbench campaign status
decomp-workbench campaign note "padding macro line markers are the active hypothesis"
decomp-workbench campaign resume
decomp-workbench campaign export --output campaign-report.html
```

With no selector, cockpit commands choose the most recently updated manifest.
They also accept a manifest path, campaign directory, unique directory prefix,
or identity prefix.

`status` reports:

- best candidate and an ASCII best-aligned trajectory;
- successful, failed, and remaining candidates;
- how many source variants collapsed into each function-byte basin;
- basin transitions rather than only the final rank;
- experiment-family tested assignments, declared parameter space, and whether
  a family is still moving or has collapsed;
- the active `note`/hypothesis and interrupted-ledger warnings.
- serial control status, declared/visited/excluded coverage, and one of five
  honest conclusion labels;
- required and optional signal transitions, including a mechanism improvement
  from a candidate whose total score is worse.

Large parameter grids stay compact in the terminal: `status` prints the tested
assignment count plus a three-row sample and summarizes oversized declared
spaces as per-parameter choice counts. `status --json` retains the bounded
machine-readable assignment evidence.

If a legacy or stale invocation wrote `experiment: null` into ledger rows but
the campaign manifest still contains the experiment and prepared sources,
`status` reconstructs the family and assignments from source provenance. It
adds a warning with the recovered row count; it never silently presents the
reconstructed join as native ledger metadata.

`resume` re-hashes the target and every remaining source, resolves the current
wrapper and objdump, checks cwd/environment/toolchain identity, and refuses a
changed envelope. It runs only cache keys absent from the ledger. A campaign
that stopped on exact remains stopped; pass `--continue-after-exact` when the
unrun grid is itself the experiment.

Exports are bounded, self-contained JSON or HTML. They contain reduced
comparison/campaign evidence rather than object or compiler contents and
refuse to overwrite an existing file.

## Survey a campaign directory that never had a manifest

`campaign status` reads a *manifest*: a set of source variants compiled,
cached, ranked and recorded through `campaign run`. Its unit is a compiled
candidate and its state is a ledger it wrote itself.

A late-stage campaign often does not look like that. Its artifacts are files a
human promoted, its floor came from a sweep in another directory, and its
residue is a `compare --by-region` run against a source path nothing records.
For that shape:

```sh
decomp-workbench campaign survey .workbench/my-campaign
```

It reports every stage directory by recency with its file, source and object
counts and the notes it carries; the findings logs with their pending sidecar
notes; the sweep manifests and their coverage; and the instrument-gate stamps —
or their absence, which is itself the finding when the directory holds traces.

It is a **reading, not a registry**. Nothing is stored, so nothing in it can be
a stale claim, and it interprets only documents the workbench already defines,
counting everything else. `--base FILE` hashes one file now and prints it as
the pinned base; without it, the survey names the newest source and object it
found and says plainly that they may or may not be the base. Guessing that is
what a registry would have institutionalised.

The walk stops at `--budget` files and says when it did, so a stage inventory is
never quietly smaller than the directory.

## Describe a transformation family

Keep source generation external, but make its hypothesis machine-readable:

```sh
decomp-workbench experiment validate \
  examples/experiments/statement-grouping/experiment.json
```

Use `--json-summary` for automation that needs validation counts and the proof
boundary without embedding every candidate path. Plain `--json` retains the
full resolved candidate list.

The `decomp-workbench-experiment-v1` manifest records:

- one family name and baseline source;
- each parameter and its declared choice list;
- every candidate path and unique parameter assignment;
- an optional half-open `selected_region` instruction range.
- optional `homologous_parameters`, explicit groups of sibling parameters
  with the same choices.

Version 1 remains supported unchanged. Use
`decomp-workbench-experiment-v2` only when the experiment needs executable
claims. It adds four small signal kinds, serial controls, and coverage:

```json
{
  "schema": "decomp-workbench-experiment-v2",
  "family": "dispatch-spelling",
  "baseline": "baseline.c",
  "parameters": {"shape": ["if", "switch"]},
  "candidates": [
    {"source": "if.c", "parameters": {"shape": "if"}},
    {"source": "switch.c", "parameters": {"shape": "switch"}}
  ],
  "signals": [
    {
      "id": "late-tail",
      "kind": "target-rows-exact",
      "rows": [120, 121, 122],
      "comparison": "relocation-aware",
      "required": true
    }
  ],
  "controls": [
    {
      "id": "known-baseline",
      "candidate": "baseline.c",
      "expect": {"words": 16, "signals": {"late-tail": "PASS"}}
    }
  ],
  "coverage": {"method": "exhaustive", "excluded": 0}
}
```

Signals are predicates over the comparator's already-selected function, never
a second object reader. `target-rows-exact` and `target-region-exact` use
target-relative aligned rows, so inserting a candidate instruction before the
range cannot move the question. `metrics` checks registered comparison keys;
`residual-classes` permits or forbids the five source-controlled classes.
Receipts contain indices, classes, and booleans—not target words or assembly.
A required signal ranks failures behind passing candidates but never changes
the built-in definition of `exact`.

Controls compile serially before the ordinary job pool. An absolute control
reproduces expected metrics, signal states, object hash, or return code. A
differential control requires two control candidates to differ at named paths
such as `object_sha256`, `metrics.words`, or `signals.late-tail`; this is the
canary for a wrapper that ignored a force or environment knob. Required
`FAIL` or `UNKNOWN` exits 2 and schedules zero ordinary candidates. Control
source hashes participate in the experiment identity, so changing one refuses
resume.

Coverage is derived from ledger assignments and the declared Cartesian grid.
The declaration may state a method, sampling note, and excluded count; every
nonzero exclusion requires a reason and cannot exceed the grid. Status uses
exactly these conclusion labels: `exhaustive-over-declared-space`,
`sampled-over-declared-space`, `partial-interrupted`, `control-invalid`, and
`coverage-unknown`. None means “historical source proven.”

Migrating v1 to v2 is additive: change the schema and add only the fields the
experiment can prove. Do not add a ceremonial control or guessed coverage.
Projects that need none of these features should keep v1.

## Keep compiler/frontends as distinct experiment cells

The same wrapper can select materially different compilation lineages. Add an
explicit cell to the normal campaign invocation, for example
`--compiler-id IDO-5.3 --frontend 'IRIX 4.x accom' --language c89 --driver
cc-irix4 --backend 'IDO 5.3 ugen'`.

These fields join the cache key, campaign identity, controls, resume, and
finish receipts. This keeps an IRIX 4 `accom` frontend distinct from later
`cfe` even when both feed the same backend or emit through a final-object
wrapper. Signals inspect the selected final function and make no ELF or
intermediate-format assumption.

Homologous groups are not inferred from names. Their baseline must have a
complete assignment. Once two measured candidates differ in exactly one group
member, every other parameter is held fixed, and the temp prefix improves,
`campaign status` proposes the equivalent untested sibling assignment. A worse
total word score does not erase that causal prefix evidence.

Validation checks paths, assignment membership, duplicate sources/assignments,
grid size, and region bounds without compiling. Attach it to the run:

```sh
decomp-workbench campaign target.o variants/*.c \
  --compile-command './compile.sh {source} -o {output}' \
  --experiment-manifest experiment.json \
  --symbol function_name
```

The baseline must be included in `variants/*.c` if it should be compiled and
ranked; naming it in the manifest alone does not add work. Selected-region
preservation uses LCS-aligned target instruction indices, so an insertion
before the range does not create positional phantom failures. It ranks first,
then the ordinary whole-function aligned key. Outside-region residual sites
are bounded in the ledger.

The workbench does not rewrite C. That boundary avoids pretending that a
“neutral” mutation is source-equivalent under every C dialect and project
context. A generator should emit deterministic new files, never edit the
active translation unit, then use the manifest to make its tested space
auditable.

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
are waited for, compared, and recorded — their objects exist and the campaign
already paid for them — so the ledger holds one record for every candidate that
actually ran and none for candidates that never started. The terminal report
names how many prepared candidates were skipped, and `--json-summary` carries
`stopped_on_exact` and `prepared_candidates`.

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

When declared, the record also carries the compiler envelope, signal receipts,
full object SHA-256, and control provenance. Existing campaigns without those
fields keep their old cache identity.

## Finish and promote one immutable winner

`campaign finish CAMPAIGN` selects a recorded source/cache key, verifies its
source and cached-object hashes, then performs a fresh no-cache rebuild. The
receipt keeps six gates independent: fresh function exactness, required
signals, optional scratch context, optional translation-unit collateral,
optional handoff audit, and an optional caller-supplied project command.
Omitted gates remain `NOT RUN`; function exactness never silently promotes
them to PASS. JSON and self-contained HTML reports are written exclusively and
are never overwritten.

After a passing JSON finish, `campaign package --finish-receipt finish.json ...`
can require that exact receipt. Packaging verifies campaign identity, cache
key, source hash, and recorded-object hash before placing the receipt path in
the scratch provenance. Without `--finish-receipt`, the existing immutable
winner checks still apply.
The promoted provenance records both the receipt path and its SHA-256.

A candidate that fails — a compiler error, a 120-second default `--timeout`,
an unreadable object, or an unexpected error inside the comparison — is
recorded as a failed candidate with its diagnostics and does not end the
campaign. The timeout is recorded under `execution.timeout_seconds`; change it
per run with `--timeout SECONDS`. The other candidates keep their results and
their ledger records. Only an interrupt (`Ctrl-C`) or a process exit ends the
run.

The directly invoked wrapper is hashed when it is a file. A wrapper may invoke
additional binaries or read configuration that the workbench cannot discover.
For complete reproducibility, put those versions in the wrapper’s own output or
campaign metadata.

Source paths intentionally remain in prepared keys even when file content is
equal. Some wrappers change behavior by path and some object formats embed
source paths. Passing the same prepared source more than once is deduplicated;
different paths are treated as distinct candidates.

## Process ownership

Every compiler runs in its own process group, and the campaign ends that group
when the run times out, fails, or is interrupted, escalating from `SIGTERM` to
`SIGKILL` after a short grace period so a wrapper that traps the polite signal
cannot outlive the campaign. A leaked parallel job did exactly that in the
field and degraded two later runs.

- **POSIX** — the compiler gets its own process group inside the workbench's
  session (`process_group=0`; Python 3.10 falls back to `start_new_session`,
  which detaches the session as well). Termination signals the whole group, so
  an assembler, a parallel search, or any other helper the wrapper started is
  ended too. Keeping the session means the children keep the controlling
  terminal.
- **Windows** — the child is created in a new process group and is sent a
  console break, then terminated. Windows has no process-group signal, so
  group-wide termination is **best effort**: a grandchild that ignores the
  console break, or a run without a console, can survive. Only the direct
  child is guaranteed to end. Do not rely on the workbench to reap a detached
  Windows tool.

Interrupting a campaign (`Ctrl-C`) cancels queued candidates, terminates
running compilers, and re-raises. Records already written to the ledger stay
valid.

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

1. the aligned residual and its class split;
2. instruction count and frame size;
3. exact or relocation-aware word mismatches;
4. insertion/deletion/reorder penalties from the project’s native diff tool;
5. opcode and normalized structure;
6. register and FP-register ranges;
7. trace signature when candidates enter the same structural basin.

A candidate with a numerically worse score can still remove structural
differences and leave only a register permutation. Inspect individual metrics,
not only rank.

For an opcode-stable allocation campaign, make that progression the ordering:

```sh
decomp-workbench campaign run target.o variants/*.c \
  --compile-command './compile.sh {source} -o {output}' \
  --rank-by temp-prefix --no-stop-on-exact
```

This gates on positional opcode alignment and an exact pool lane, then prefers
the candidate whose ugen temp lane stays exact to the latest object row.
`--rank-by words` remains available for a deliberately positional campaign;
`auto` is the general default. All prefix fields are retained in full JSON,
`--json-summary`, ledgers, status trajectories, and `best_temp_prefix`.

### Ranking is aligned-first

Results are ordered by `aligned_total` — the LCS-aligned differing rows a
source change controls — with the positional `words=` count as the tiebreaker,
then the relocation, normalized-distance, register, and instruction-delta keys,
then the source path. `rank`, `compile-rank`, `campaign`, and the object-basin
ordering all use that one key.

**Unless the set is mixed.** `gaps=` counts aligned rows the aligner filled on
one side only. A candidate with gaps was aligned against a different
subsequence of the target than a gap-free candidate was, so the two aligned
totals are not on one scale — a gapped candidate has been observed reporting
1435 aligned rows against a 1865-row base while holding 2918 mismatching words
and 1807 opcode mismatches. When a result set contains both kinds, `rank` and
`campaign` order it on `words` instead, `rank --json` records
`ranked_by: "words"` and `mixed_alignment: true`, and the terminal prints
`caution: candidates differ in alignment gap status`.

The reason is measured, not aesthetic: positional counting shifts on every
insertion, and it misranked candidates in six recorded campaigns. In one, a
one-hunk 11-word variant sorted below a five-site 5-word variant and nearly
steered the search into the wrong family; in another, two variants tied at 95
positional words while the aligned split (10 structural versus 8) picked the
only one that composed with the next edit.

Two consequences worth stating plainly:

- **`words=` is still the oracle.** A match is `exact=true` with `words=0`;
  `aligned_total=0` alone is not a match, because relocation-controlled and
  displacement rows are outside the residual by design. For a decomp.me score
  target, use `check-scratch` and require both
  `raw_instruction_words_exact=true` and `relocation_targets_exact=true`;
  linked-equivalent relocation spellings can still carry a non-zero site
  score.
- **Ranking moved, verdicts did not.** The `verdict=` taxonomy is unchanged, so
  a saved ledger from an earlier release compares to a new one on every field
  except result order.

Campaign output uses the same metric registry as `compare`: the printed label
and the JSON key are one string, and `decomp-workbench campaign --explain-keys`
prints the mapping (including the deprecated long-form keys still emitted for
one release).

To ask one yes/no question about a single candidate — inside a shell loop, a
generator, or a fidelity gate — use `compare --census` and read the exit code
instead of parsing the campaign's JSON. It answers `0` when every predicate
holds, `3` when one fails, and `2` when the question itself is wrong; see
[object comparison](object-comparison.md#ask-a-question-and-read-the-exit-code---census).

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

## Promote a winner into a scratch

```sh
decomp-workbench campaign package CAMPAIGN \
  --output scratch/demo \
  --target-assembly target.s --context ctx.c \
  --platform n64 --compiler 'IDO 5.3' --compiler-id ido5.3 \
  --language C --compiler-flags='-O2 -mips2' --diff-label demo
```

The command revalidates the campaign's target, compiler, objdump, and source
hashes, selects the score winner (or `--selection temp-prefix`), and refuses a
candidate that is not raw-word and relocation-target exact unless
`--allow-mismatch` is explicit. The resulting standard scratch bundle records
the campaign identity, selected cache key, source hash, comparison evidence,
and paste order.

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

## Compose mechanisms, then minimize an exact source

A successful mechanism on one source parent may look useless on another. Do
not multiply every raw variant by every other raw variant. Preserve one
representative source delta per object basin and compose those deltas in a
bounded interaction set:

```sh
decomp-workbench experiment inspect-source exact.c
decomp-workbench experiment compose composition.json generated --dry-run
decomp-workbench experiment compose composition.json generated
decomp-workbench experiment validate generated/experiment.json
```

The composition manifest uses exact `find`/`replace` edits, named families,
optional `requires`/`conflicts`, and explicit `max_order`/`max_candidates`
bounds. Generation refuses a non-empty output directory and rejects an edit
whose expected occurrence count changed. It writes deterministic candidates
and a normal `decomp-workbench-experiment-v1` sidecar; it does not compile or
claim that the edits commute.

See
[`examples/experiments/carrier-substitution`](../examples/experiments/carrier-substitution/README.md)
for a runnable, redistributable example. The important pair was previously
missed in a real campaign because an erased boundary-control family and a
cancelled hot-read family were searched on separate parents.

When the baseline is already exact, run the generated set with
`--no-stop-on-exact`: the objective is no longer “find the first zero,” but
“find every zero with less fake-match burden.” Keep raw instruction words,
relocation targets, frame, and project verification as hard gates. Use
`object collateral` on the full translation unit before preferring a cleaner
function source; function-local statics can change `.bss` or GP-linker metadata
without changing one instruction in the selected function.

## Reviewing a generated winner

A generator proposes edits by shape, not by meaning. Nothing downstream asks
whether a variant is still the same program: the comparator answers "are these
the same object", and a variant that reads an uninitialised local compiles and
scores like any other. One recorded sweep renamed a local's occurrences in
line-proximity groups and produced both failures — a group of pure reads
rehosted onto a never-written local, and a top-scoring row that deleted a live
first store.

So a sweep winner is reviewed before it is adopted, never after:

```sh
decomp-workbench experiment review-mutation baseline.c winner.c
```

It prints the diff and flags a use that no earlier line writes to
(`read-before-definition` or `definition-removed`, error, exit 1) and a removed
write to a value that is still read (`write-removed`, warning; make it fatal
with `--fail-on-warning`). Only identifiers the file declares are considered,
and only shapes the mutation *introduced* — a baseline that already reads a
local above its write is the existing code, not this variant's doing.

The command is a review surface, not a proof. It does not parse, type, or
execute C and builds no control-flow graph, so a clean report means the two
named shapes were absent, not that the variant is valid. Read the diff and
justify every changed line.

## Cache hygiene

Objects are content-addressed under `--cache-dir`. Inspect before cleaning:

```sh
decomp-workbench cache status
decomp-workbench cache prune --older-than 30d
decomp-workbench cache prune --older-than 30d --apply
```

Prune is a dry run unless `--apply` is present. Apply moves selected entries
into a timestamped recoverable trash directory, including across filesystems;
it does not unlink them. The output prints the exact `cache restore` command.
Restore refuses to overwrite an entry that already exists.

The ledger is append-only so interrupted runs retain completed records. Use a
new campaign identity for a materially different experimental question, even
when the cache can be reused. Cache hits reproduce execution efficiently;
manifest identity and ledger evidence remain the audit trail.
