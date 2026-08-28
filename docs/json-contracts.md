# JSON and automation contracts

Every command with `--json` returns exactly one JSON document on stdout.
Success documents carry a versioned top-level `schema`; failures carry
`decomp-workbench-error-v1`. Diagnostics are not mixed into stderr in JSON
mode, so a caller never has to guess whether stdout is parseable.

## Success

Schemas name the user-visible report, for example:

- `decomp-workbench-comparison-v1`
- `decomp-workbench-staleness-v1`
- `decomp-workbench-diagnosis-v3`
- `decomp-workbench-campaign-status-v1`
- `decomp-workbench-campaign-finish-v1`
- `decomp-workbench-oracle-sweep-v1`
- `decomp-workbench-trace-source-v1`

### One command, two shapes

Two commands take more than one candidate, and the schema says which shape you
got. Switch on `schema`, never on argument count:

| Command | One candidate | Several candidates |
|---|---|---|
| `align`, `align-dumps` | `decomp-workbench-shift-diff-v1` | `decomp-workbench-align-census-v1` |
| `phase`, `phase-dumps` | `decomp-workbench-phase-v1` | `decomp-workbench-phase-census-v1` |

A census document holds one single-candidate report per entry under
`candidates`, so a consumer that already reads the single shape can loop over
that list unchanged.

### Sub-documents never rename their host

Optional blocks merged into a report keep their keys namespaced and name
themselves under a prefixed key, never `schema`. `--watch-rows` adds
`watch_rows`, `watch_signature`, the tallies, and `watch_schema`
(`decomp-workbench-watch-rows-v1`) to a `compare`, `rank`, or `sweep build`
document; the document's own top-level `schema` is unchanged. `compare`,
`compare-dumps`, `diagnose` and `diagnose-dumps` add `staleness` and
`staleness_schema` (`decomp-workbench-staleness-v1`) the same way: what was
compared, when each artifact was built, and any input newer than the build
that was compared against it. `check-staleness` emits that document on its
own, with the schema at the top level. Switch on
`schema` to know what you are holding, and on the presence of the prefixed
keys to know which optional blocks came with it.

`decomp-workbench commands --json` is the versioned discovery surface. Existing
flat command names and journey spellings return the same report:
`object diagnose` is an alias of `diagnose`, and `campaign status` is an alias
of `campaign-status`. Each discovery entry includes executable `invocation`
argv, its `report_schema`, and conservative safety metadata (`default`,
`external_process`, `network`, and `destructive`). The metadata describes the
default path; command help remains authoritative for optional output flags.

The report also carries a top-level `network` object: the offline-first
`policy` sentences, the `commands` that may open a connection, and the `hosts`
they contact with the reason for each. It is an inventory, not a flag — an
empty `commands` list is the positive claim that this build cannot call out,
and every command outside the list reports `safety.network: false`. Use it as
the egress contract; do not infer network behavior from a command's name.

`next --json` is the action surface. Every proposed step carries
`command_argv`, a shell-rendered `command` for humans, `safety`, and an
`expected_signal` that says what evidence would make the step informative.
Agents should execute argv directly and evaluate the expected signal instead
of scraping prose or invoking a shell string.

Comparison metric labels, JSON keys, census keys, and ledger fields share one
registry. Run:

```sh
decomp-workbench --explain-keys
```

Canonical short keys such as `words`, `aligned_total`, and `frame` are the
stable vocabulary. Deprecated long spellings remain emitted only for the
documented compatibility window.

Rank reports name the selected scale as `ranked_by`. If any candidate required
alignment gaps, `alignment_ranking_unsafe=true` and the whole set is ordered on
positional `words`; two gapped candidates are not assumed to share an aligned
scale. `mixed_alignment` is retained as the narrower fact that both gap-free
and gapped candidates were present.

`diagnose`/`diagnose-dumps` emit `decomp-workbench-diagnosis-v3` and
`view`/`view-dumps` emit `decomp-workbench-view-v3`. Both bumps are additive.
v2 gained a `routing` field beside the verdict; v3 gained `owning_pass`,
`reachability` and `ownership_basis` beside that. Nothing was removed or
renamed at either step, so a consumer that ignores the new fields reads a v3
document exactly as it read a v1 one.

`routing` is one of `permuter-first`, `structural`, `import-fix`, or `none` --
which tool the residual belongs to, as opposed to which mechanism explains it.
An allocation, colour, or schedule tie is always `permuter-first`; it is never
reported as proven unmatchable.

`owning_pass` is one of `cfe-spelling`, `rodata-load-form`,
`stack-home-assignment`, `uopt-globalcolor`, `ugen-temp-ring`, `g0-scheduler`,
`none` (an exact pair) or `unknown` (nothing here settles it). `reachability`
is one of `source-reachable`, `permuter-target`, `pass-owned` or `unknown`.
`ownership_basis` says what those two were read off and is never omitted:
`trace` when a compiler trace settled it, `heuristic` when they were read off
the residual's shape, `none` when there was nothing to read. A consumer that
treats a `heuristic` answer as a measurement is making the claim the field
exists to prevent.

`pass-owned` means the evidence exposes no handle a source edit reaches. It is
**not** a wall: a `pass-owned` residual routes `permuter-first` exactly like
any other tie, and the measurement that may record a wall is
`permute classify`, afterwards.

On a diagnosis the top-level `routing`, `owning_pass` and `reachability` may
differ from `view.*`: a relocation naming a different symbol makes the whole
residual `import-fix`/`unknown`/`unknown` while the view still reports the
mechanism it measured.

Experiment-v2 and endgame additions are additive to existing report schemas:

- comparisons expose `aligned_row_receipts`, a code-free row identity/class/
  equality table used by signals;
- campaign results expose `signals`, `object_sha256`, and `controls`;
- campaign status exposes `acceptance_trajectory`, `mechanism_trajectory`,
  `coverage`, `conclusion_label`, requested `rank_by`, effective `ranked_by`,
  and `alignment_ranking_unsafe`;
- scratch checks expose `truth_layers`, `context_differential`,
  `context_hypotheses`, and optional `project_comparison`;
- finish files use `decomp-workbench-campaign-finish-v1`, with independent
  gates whose status is `PASS`, `FAIL`, `UNKNOWN`, or `NOT RUN`.

Signal/control machine statuses are exactly `PASS`, `FAIL`, and `UNKNOWN`.
`UNKNOWN` blocks a required control; it never means false. Coverage conclusion
labels are exactly `exhaustive-over-declared-space`,
`sampled-over-declared-space`, `partial-interrupted`, `control-invalid`, and
`coverage-unknown`. Consumers should switch on those fields rather than parse
human reasons. Signal receipts deliberately contain no target instruction
text or target words; normal ledger redaction still applies to other
comparison detail.

The CV64 campaign record also uses
`decomp-workbench-recorded-example-v1`. That is aggregate historical metadata,
not a schema emitted by a CLI command and not a substitute for a fresh
comparison.

## Failure

A representative error is:

```json
{
  "schema": "decomp-workbench-error-v1",
  "command": "compare-dumps",
  "stage": "command",
  "status": 2,
  "error": {
    "kind": "not-found",
    "message": "..."
  }
}
```

Argument-parser failures follow the same envelope when `--json` was present.
`kind` is a small operational classification (`usage`, `not-found`,
`process-failed`, `timeout`, `no-result`, or `command-failed`); domain details
remain in the message or an optional `details` object.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | command completed; any explicitly requested gate passed |
| `1` | a requested match/validation gate failed, or no usable rows existed |
| `2` | invalid input, missing capability, or failed external stage |
| `3` | the report was produced, but at least one `--census` predicate was false |

A failed required campaign control returns 2 because the experiment is
invalid and ordinary candidates were not scheduled. `campaign finish` returns
1 when it wrote a valid receipt with one or more evaluated gates failing, and
2 when it could not produce a trustworthy receipt.

State and readiness are data, not automatically process failures. For example,
successful partial `toolchain calibrate` returns zero with
`claim="uncalibrated"` and lists the missing gates. `toolchain status` returns
nonzero only when recorded file integrity fails.

## Bounded process output

Compiler-facing reports retain at most 64 KiB per stdout/stderr stream by
default and report original byte counts plus truncation. Use `--stream-limit`
to change the preview and `--artifact-dir` to retain complete streams. Artifact
filenames are exclusive and collision-safe; existing evidence is never
overwritten.

Compact campaign automation should prefer `--json-summary`. Full `--json`
includes richer compiler and instruction evidence. JSONL ledgers are
append-only; a torn final line after interruption is ignored with a warning,
while malformed earlier records are rejected.

## Files written by reports

Explicit exports and force specifications refuse to overwrite. Derived status
inside an owned `.decomp-workbench` state directory is updated atomically.
Cache prune is a dry run until `--apply`, and apply moves entries to recoverable
trash rather than deleting them.

These contracts are exercised in the supported Python matrix, macOS full-suite
CI, targeted Windows process/filesystem CI, distribution smoke tests, and
runnable documentation tests.
