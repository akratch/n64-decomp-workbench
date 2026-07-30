# Product status

This is the current-state companion to the dated field notes, product review,
and north-star vision. Those documents preserve why features were requested;
this page says what users can rely on now.

## Complete user journeys

| Job | Supported path |
|---|---|
| Explain one mismatch | `doctor` → `diagnose` → field-guide lever → rebuild |
| Check a 99.xx% decomp.me result | `doctor ZIP` → `check-scratch --view` → optional site-faithful compile |
| Work a candidate family | `experiment validate` → `campaign` → `campaign status/note/resume/export` |
| Manage local state | default `.decomp-workbench/` manifests/ledgers/cache; recoverable `cache prune/restore` |
| Establish pass ownership | `fidelity`, `pass diff`, calibrated `replay-as1` |
| Identify compiler lineage | behavioral `fingerprint-toolchain`; hash-recorded `lineage` across caller-supplied objects |
| Explain allocator decisions | `trace-webs`, `trace-source`, `trace-stack-homes`, `oracle plan/diff/force/sweep/status/export` |
| Explain scheduler decisions | stable trace reader plus hash-pinned external profile adapter and calibration gates |
| Automate safely | versioned success/error JSON, census exit codes, bounded streams, generated completions |

Flat command names remain compatible. `decomp-workbench commands` presents the
same surface as task groups (`object`, `scratch`, `campaign`, `cache`, `trace`,
`instrument`, `pass`, `toolchain`, `oracle`, `experiment`).

## Intentional boundaries

- No source auto-solver or C parser. External generators own project-specific
  rewrites; experiment manifests make their parameter space and results
  durable.
- No bundled proprietary toolchain or one-size-fits-all generated compiler
  patch. The workbench supplies adapters, hashes, trace schemas, and gates.
- No decomp.me upload client. Imports and deterministic bundles keep a human at
  the network boundary.
- No ROM reader in lineage mode. The caller supplies object inputs and may
  attach precomputed ROM hashes.
- No forced compiler result presented as a match. Oracle output always routes
  back to source and stock-project verification.
- No silent cleanup or overwrite. Evidence is append-only or exclusive;
  cache pruning is recoverable.

## Remaining research, not missing basic UX

The highest-value open depth work needs new measured evidence before it can be
implemented honestly:

- join ugen pool events to emitted-instruction indices, not only logical FIFO
  identities;
- recover richer expression ancestry and final frame ownership from validated
  compiler fields;
- add project-neutral mutation *recipes* only when equivalence conditions can
  be stated safely across supported C dialects;
- add multi-force oracle search when one-force evidence demonstrates a real
  need and the combinatorial policy can remain explicit;
- ship additional scheduler profiles only for revisions with reproducible
  source anchors and full calibration cells.

These are depth extensions. A newcomer, project contributor, decomp.me user,
campaign author, automation caller, and instrumentation specialist all have a
complete supported path today.
