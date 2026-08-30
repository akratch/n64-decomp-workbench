# Product status

As of 0.7.0, 2026-08-28.

This is the current-state companion to the dated records in
[docs/history](history/). Those documents preserve why features were
requested; this page says what users can rely on now.

The cross-cutting release gates and the few external checks that remain open
are tracked in the [Workbench quality checklist](workbench-quality-checklist.md).

## Complete user journeys

| Job | Supported path |
|---|---|
| Explain one mismatch | `doctor` → `diagnose` → field-guide lever → rebuild |
| Route one residual to the tool that owns it | `diagnose --trace` → the `routing` and `ownership` verdict lines → permuter sweep, field-guide lever, or import fix |
| Work a backlog of near-matches | `ranking check` → `permute doctor` → `permute sweep --require-fresh` → `permute classify` → project-truth verification |
| Trust that a comparison measured the current build | `--built-from` on `compare`/`compare-dumps`/`diagnose`/`diagnose-dumps`, or `check-staleness` over a whole build chain |
| Check a 99.xx% decomp.me result | `doctor ZIP` → `check-scratch --view` → optional site-faithful compile/project truth differential |
| Publish a proof repository | `handoff audit` → resolve missing/untracked dependencies → fresh-clone review |
| Work a candidate family | v1/v2 `experiment validate` → control preflight → `campaign` → status/note/resume/export |
| Preserve current vs measured best | `campaign checkpoint` → guarded `restore-best` with backup → exact-by-default `campaign accept` |
| Avoid repeating closed searches | append/query the campaign falsified-hypothesis dossier |
| Assign only current work | `campaign readiness` rehashes artifacts and splits codegen, identity, remeasurement, and promotion queues |
| Finish and promote a winner | immutable selection → `campaign finish` fresh/optional gates → optional receipt-gated `campaign package` |
| Manage local state | default `.decomp-workbench/` manifests/ledgers/cache; recoverable `cache prune/restore` |
| Reuse project inputs | conservative `project init` preview → strict `.decomp-workbench.toml` → configured `next`/`compare`/`diagnose`/`campaign` |
| Establish pass ownership | `fidelity`, `pass diff`, calibrated `replay-as1` |
| Identify compiler lineage | behavioral `fingerprint-toolchain`; hash-recorded `lineage` across caller-supplied objects |
| Explain allocator decisions | `trace-webs`, `trace-source`, `trace-stack-homes`, `oracle plan/diff/force/sweep/status/export` |
| Explain scheduler decisions | stable trace reader plus hash-pinned external profile adapter and calibration gates |
| Explain PRE/hoist decisions | stable procedure/block/expression records plus a hash-pinned external profile adapter |
| Prove an unrelocated-overlay promotion | project identity provider → `reloc-surface` → `linked-compare` → hash-bound `reloc-proof` |
| Audit a matched project's shiftability | `shift audit` inventory → `shift rehearse orchestrate` two-delta relink → `--census unexplained_changed=0,stale_confirmed=0` as the CI gate |
| Make a matched project shiftable | `shift audit --blobs auto --elf` → linker-config edit gated by `shift config verify` → `shift rehearse` with `--base-elf/--shifted-elf` at two deltas → `shift plan --markdown` work order → per-fix loop, `--census` in CI |
| Automate safely | versioned success/error JSON, census exit codes, bounded streams, generated completions |

Flat command names remain compatible. `decomp-workbench commands` presents the
same surface as task groups (`object`, `scratch`, `handoff`, `campaign`,
`cache`, `project`, `trace`, `instrument`, `pass`, `capture`, `ucode`,
`binasm`, `stream`, `probe`, `sweep`, `toolchain`, `shift`, `target`,
`permute`, `ranking`, `oracle`, `experiment`).

## Intentional boundaries

- No source auto-solver or C parser. External generators own project-specific
  rewrites; experiment manifests make their parameter space and results
  durable.
- No bundled proprietary toolchain or one-size-fits-all generated compiler
  patch. The workbench supplies adapters, hashes, trace schemas, and gates.
- No decomp.me upload client, login, or scrape. Network access is read-only,
  explicit, and inventoried: `scratch fetch` downloads one public export and
  `scratch public-match-check` queries the public search, both only when named
  on the command line. Publishing still goes through a deterministic bundle a
  human uploads, which keeps a person at the write boundary.
- No ROM reader in lineage mode. The caller supplies object inputs and may
  attach precomputed ROM hashes.
- No forced compiler result presented as a match. Oracle output always routes
  back to source and stock-project verification.
- No promotion from a permuter score. `permute sweep` runs a bounded search in
  a scratch it first proves is the object the project's own build produces; a
  score of 0 is a candidate until the authoritative build agrees. `permute
  classify` names the wall class the search *measured*, and never argues one
  from verdict prose.
- No exactness claim over an unstated build. A comparison answers "are these
  the same", not "is this what my last edit produced"; `--built-from` is what
  makes the second question answerable, and modification time is treated as
  evidence with an escape hatch rather than as proof.
- No silent cleanup or overwrite. Evidence is append-only or exclusive;
  cache pruning is recoverable.
- No emulator or behavioral oracle for shifted images. `shift rehearse`
  explains a relink word by word and names what stayed put; whether the
  resulting ROM *runs* is a hand-off, stated on the report rather than
  implied by it.
- No object-level relocation scanning, and no per-game asset-format parsing.
  The shift commands read a linker map and linked images; segmented pointers
  inside display lists and geo layouts are a named later increment, not a
  silent gap.
- No verdict from a linked image alone. A linked ROM keeps no relocations, so
  `shift audit`'s tiers rank address-likelihood and never hazard; only a
  shifted relink separates a resolved pointer from a typed-in constant.
- No fixes applied. `shift plan` merges the reports into a ranked queue with a
  remediation class, the evidence and a gate command per item; editing linker
  configuration, migrating data and placing symbols stays the maintainer's
  work. A plan built from capped reports says `plan_capped` rather than
  presenting part of a queue as the whole one.

## Remaining research, not missing basic UX

The highest-value open depth work needs new measured evidence before it can be
implemented honestly:

- decode the uopt intermediate stream deeply enough to add its record ranges
  to the shipped ugen emitted-index/object-row/source join;
- recover richer expression ancestry and final frame ownership from validated
  compiler fields;
- add project-neutral mutation *recipes* only when equivalence conditions can
  be stated safely across supported C dialects;
- add multi-force oracle search when one-force evidence demonstrates a real
  need and the combinatorial policy can remain explicit;
- ship additional scheduler profiles only for revisions with reproducible
  source anchors and full calibration cells.

These are depth extensions, not gaps in the supported journeys above.

## Trustworthy endgames campaign

[The trustworthy endgames campaign](history/trustworthy-endgames-campaign.md) is now
implemented: function/row-scoped signals, required serial controls,
project-vs-scratch truth layers, coverage-qualified conclusions, compiler-cell
identity (including IRIX 4 `accom`/later-backend hybrids), immutable promotion,
and a fresh auditable finish receipt are supported paths. The design document
remains the rationale and acceptance ledger; this page is the current claim.
