# Product status

This is the current-state companion to the dated field notes, product review,
and north-star vision. Those documents preserve why features were requested;
this page says what users can rely on now.

## Complete user journeys

| Job | Supported path |
|---|---|
| Explain one mismatch | `doctor` → `diagnose` → field-guide lever → rebuild |
| Check a 99.xx% decomp.me result | `doctor ZIP` → `check-scratch --view` → optional site-faithful compile |
| Publish a proof repository | `handoff audit` → resolve missing/untracked dependencies → fresh-clone review |
| Work a candidate family | `experiment validate` → `campaign` → `campaign status/note/resume/export` |
| Manage local state | default `.decomp-workbench/` manifests/ledgers/cache; recoverable `cache prune/restore` |
| Establish pass ownership | `fidelity`, `pass diff`, calibrated `replay-as1` |
| Identify compiler lineage | behavioral `fingerprint-toolchain`; hash-recorded `lineage` across caller-supplied objects |
| Explain allocator decisions | `trace-webs`, `trace-source`, `trace-stack-homes`, `oracle plan/diff/force/sweep/status/export` |
| Explain scheduler decisions | stable trace reader plus hash-pinned external profile adapter and calibration gates |
| Audit a matched project's shiftability | `shift audit` inventory → `shift rehearse orchestrate` two-delta relink → `--census unexplained_changed=0,stale_confirmed=0` as the CI gate |
| Make a matched project shiftable | `shift audit --blobs auto --elf` → linker-config edit gated by `shift config verify` → `shift rehearse` with `--base-elf/--shifted-elf` at two deltas → `shift plan --markdown` work order → per-fix loop, `--census` in CI |
| Automate safely | versioned success/error JSON, census exit codes, bounded streams, generated completions |

Flat command names remain compatible. `decomp-workbench commands` presents the
same surface as task groups (`object`, `scratch`, `handoff`, `campaign`,
`cache`, `trace`, `instrument`, `pass`, `toolchain`, `shift`, `oracle`,
`experiment`).

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

These are depth extensions. A newcomer, project contributor, decomp.me user,
campaign author, automation caller, and instrumentation specialist all have a
complete supported path today.

## Planned product campaign

The next cross-journey increment is scoped in
[The trustworthy endgames campaign](trustworthy-endgames-campaign.md). It does
not replace any complete journey above. It connects them with declarative
function/row-scoped signals, mandatory experiment controls, project-vs-scratch
context differentials, coverage-qualified conclusions, immutable winner
promotion, and one auditable finish receipt. Every item is planned and remains
outside the supported-capability table until its phase lands with tests.
