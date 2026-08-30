# Evidence, candidate lifecycle, and queue readiness

Three rules keep a long campaign honest:

1. artifact identity is content identity, not a filename or timestamp;
2. current work, best measured work, and accepted work are different states;
3. stale measurements and incomplete relocation identities are maintenance,
   not source-matching assignments.

The commands on this page enforce those distinctions. They do not infer that a
source produced an object, that a linked image came from a particular checkout,
or that a project's relocation namespace has one universal format. The host
supplies those relationships explicitly and the workbench binds the supplied
files by SHA-256.

## Keep current and best separately

After a campaign has at least one successful candidate, archive its
deterministically ranked best source/object pair. Name the active source as
well when it differs from the winner:

```sh
decomp-workbench campaign checkpoint .decomp-workbench/campaigns/demo/manifest.json \
  --current-source src/demo.c --current-object build/demo.o
```

The archive lives below the campaign directory under `artifacts/ID/`. IDs are
derived from source and object contents. Existing archive files are rehashed
and never overwritten. Re-running the command is therefore idempotent for the
same candidate and a refusal if an immutable archive was altered.
Checkpoint, restore, and accept share one manifest transaction lock; archive
creation has a per-content lock, so cooperating concurrent campaign workers
cannot publish a half-written pointer or race the same immutable ID.

Materializing best is an explicit, recoverable operation:

```sh
decomp-workbench campaign restore-best \
  .decomp-workbench/campaigns/demo/manifest.json \
  --destination src/demo.c
```

The command compares the destination with the recorded current checkpoint,
copies an existing destination into the campaign's `backups/` directory, then
atomically installs the archived best source. Drift is refused. Use
`--allow-drift` only after reviewing the changed destination; the backup is
still made.

Acceptance is a pointer to one immutable checkpoint, not a loose source file:

```sh
decomp-workbench campaign accept .decomp-workbench/campaigns/demo/manifest.json
```

The checkpoint must have an exact comparison by default. `--allow-mismatch`
exists for an intentional non-terminal acceptance and is recorded as
`exact=false`; it does not turn a mismatch into a match.

## Record negative space

Append one tested hypothesis to the campaign dossier:

```sh
decomp-workbench campaign dossier-add \
  .decomp-workbench/campaigns/demo/manifest.json \
  --function demo \
  --hypothesis 'operand commutation changes the scheduler basin' \
  --lever 'swap the two source operands' \
  --result falsified \
  --outcome 'the normalized object hash was unchanged' \
  --do-not-repeat \
  --evidence 'campaign row 4'
```

`result` is exactly `falsified`, `supported`, or `inconclusive`. Records are
single-line, bounded, append-only JSONL. Their ID is a digest of the substantive
fields, independent of recording time: duplicate experiments are refused and
edited records fail their ID check when read. Appenders serialize duplicate
checks and issue one synced append while holding the dossier's lock.

Query all records or select one function/result:

```sh
decomp-workbench campaign dossier-list \
  .decomp-workbench/campaigns/demo/manifest.json \
  --function demo --result falsified --json
```

A torn final line is ignored with a warning after an interrupted append. A
malformed earlier line is corruption and is refused.

## Classify a queue before assigning work

`campaign readiness` reads `decomp-workbench-target-queue-v1` JSON. Every
entry carries a measured comparison and at least one artifact receipt:

```json
{
  "schema": "decomp-workbench-target-queue-v1",
  "entries": [
    {
      "symbol": "demo",
      "artifacts": [
        {
          "role": "candidate-object",
          "path": "/work/build/demo.o",
          "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
          "size": 4096
        }
      ],
      "measurement": {"exact": false, "words": 4, "verdict": "schedule"},
      "plateau": true
    }
  ]
}
```

Run the census:

```sh
decomp-workbench campaign readiness queue.json --json
```

The four classes are deliberately operational:

| Class | Meaning |
|---|---|
| `promotion-ready` | current measured comparison is exact; run final linked/project gates |
| `codegen-ready` | current non-exact evidence can be assigned to source/codegen work |
| `identity-maintenance` | relocation sites lack complete canonical identities |
| `remeasure` | an artifact/report changed, disappeared, or has no measurement |

A plateau remains `codegen-ready` only for a new evidence-producing mechanism;
the report says so in `next`. It is not permission to repeat the same source
search.

When `relocation_required=true`, `relocation_report` is itself a full artifact
receipt, not a path string. The report must be a current JSON
`reloc-surface --identity-provider` result. Readiness rehashes that report and
every artifact nested in its evidence block before reading `identities.complete`.
Unknown identity and contradicted identity remain distinct in that report, but
both stay out of the source queue.

## What the receipts prove

Artifact records hold resolved path, role, size, and SHA-256. Modification time
is intentionally absent: touching unchanged evidence does not alter its
identity. A receipt detects changed contents and missing/moved paths, but a
source-to-object relationship remains host-declared unless the command itself
runs the build.

Use [`reloc-proof`](linked-oracle.md#compose-a-dual-surface-proof) when that
declared source/object pair also needs complete relocation identities and exact
final linked bytes. Use `campaign finish` for a fresh compiler run and the
project's wider acceptance gates. These receipts complement one another; none
silently upgrades the claim made by another.
