# JSON and automation contracts

Every command with `--json` returns exactly one JSON document on stdout.
Success documents carry a versioned top-level `schema`; failures carry
`decomp-workbench-error-v1`. Diagnostics are not mixed into stderr in JSON
mode, so a caller never has to guess whether stdout is parseable.

## Success

Schemas name the user-visible report, for example:

- `decomp-workbench-comparison-v1`
- `decomp-workbench-diagnosis-v1`
- `decomp-workbench-campaign-status-v1`
- `decomp-workbench-oracle-sweep-v1`
- `decomp-workbench-trace-source-v1`

`decomp-workbench commands --json` is the versioned discovery surface. Existing
flat command names and journey spellings return the same report:
`object diagnose` is an alias of `diagnose`, and `campaign status` is an alias
of `campaign-status`.

Comparison metric labels, JSON keys, census keys, and ledger fields share one
registry. Run:

```sh
decomp-workbench --explain-keys
```

Canonical short keys such as `words`, `aligned_total`, and `frame` are the
stable vocabulary. Deprecated long spellings remain emitted only for the
documented compatibility window.

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
