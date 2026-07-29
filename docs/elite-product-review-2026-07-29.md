# Elite product review — user stories and scoped backlog

This review treats the workbench as a product, not a collection of commands.
The standard is simple: a new contributor should reach a trustworthy next
action quickly, an expert should not need to rebuild missing analysis in a
script, and an automated user should see the same facts and vocabulary as a
human.

The current product is unusually strong at the center of the loop:
relocation-aware comparison, LCS-aligned mechanism diagnosis, concrete
code-shape guidance, cached campaigns, and narrow compiler instrumentation.
The remaining opportunity is mostly around the loop: first-run readiness,
durable experiment state, consistent process and JSON contracts, and a clean
graduation from ordinary diagnosis to compiler internals.

## User-story review

| User | Job to be done | What works now | Remaining friction |
|---|---|---|---|
| Curious newcomer | Learn the mental model without a ROM or compiler | `START_HERE`, redistributable dumps, real output assertions | The root help is a long flat command list; installation is source-only until a package is published |
| Project contributor | Explain one stubborn mismatch | `compare` gives a verdict; `view` gives aligned hunks, lanes, and a lever | Two commands repeat input/options; `check-scratch` cannot render the full aligned view in the same run |
| decomp.me user | Turn a downloaded ZIP into local truth | Safe in-memory import, browser-score separation, site-faithful `#line` composition | Compiler failures are still text errors rather than a JSON error envelope; project wrapper readiness is not preflighted by `doctor` |
| Campaign author | Sweep variants without losing evidence | Parallel cache, early exact stop, basins, ledger, compiler ownership | Ledger is optional; no experiment-family manifest or status view; cache can be inspected but not safely managed |
| Mutation author | Learn which families move the compiler | Stable ranking and basin collapse expose no-op families | Source parameters live in filenames/comments; no first-class family/parameter schema or region constraints |
| Instrumentation specialist | Decide which compiler pass owns a residual | Pinned uopt profiles, fidelity gates, focused trace readers, pass replay | No supported scheduler profile, stable semantic web identity, or original-pass differential adapter |
| Maintainer | Release something users can trust | Broad Python CI, package inspection, executable docs, release checklist | Linux-only CI, a very large CLI module, no automated actionlint step, and no compatibility policy for every JSON report |
| Agent or script | Consume the same truth as the terminal | Canonical metric registry, JSON, census exit code, compact campaign summary | Several report types lack schemas; errors generally escape as stderr; command discovery is optimized for humans only partially |

## Complete journeys

### Journey A — “I have two objects and no idea what is wrong”

The intended path is:

```text
doctor → compare → view → field-guide lever → project rebuild → compare
```

The path is already teachable and evidence-led. The next product step is a
non-destructive `diagnose` command (or `compare --view`) that disassembles each
object once and renders the summary plus the decisive aligned hunk. It should
not remove `compare` or `view`; those stay composable primitives.

Acceptance criteria:

- one invocation answers exactness, mechanism, first divergence, and next lever;
- object inputs are disassembled once;
- human and JSON forms contain the same report object;
- `--show-all` expands evidence, while the default stays one screen;
- exit semantics remain compatible with `--fail-on-mismatch` and `--census`.

### Journey B — “decomp.me says 99.98%; is the source actually close?”

The intended path is:

```text
doctor export.zip → check-scratch export.zip → optional site-faithful compile
```

The importer now refuses mixed archive roots, nested expanded content,
impossible scores, and malformed checksums. Compiler execution owns the wrapper
and its children, has a deadline, and records the reproducibility envelope.

The next step is `check-scratch --view`, using the comparison already in
memory, plus a structured error report when compilation fails:

```json
{
  "schema": "decomp-workbench-error-v1",
  "command": "check-scratch",
  "stage": "compile",
  "error": {"kind": "timeout", "message": "...", "returncode": 124},
  "compile": {"command": [], "stdout": "", "stderr": ""}
}
```

Acceptance criteria:

- `--json` always emits valid JSON, on success and failure;
- the report states whether evidence came from exported objects, dumps, or a
  local site-faithful compile;
- the composed source identity and compiler/wrapper identity are retained;
- no archive member is extracted or silently ignored;
- exact function evidence never claims whole-project health.

### Journey C — “I have 30 near matches; what should I work on first?”

The existing walkthrough, aligned ranking, and basin grouping solve triage.
The missing bridge is durable state. A campaign should create a manifest and
ledger by default under `.decomp-workbench/`, then expose:

```text
campaign status   best candidate, trajectory, failures, family/basin map
campaign resume   only work not represented by the manifest and cache
campaign export   bounded shareable JSON/HTML evidence
```

Legacy `campaign` syntax must remain valid. A future namespace can add these
subcommands without forcing existing wrappers to migrate immediately.

Acceptance criteria:

- every run records target, symbol, wrapper, objdump, cwd, explicit
  environment, timeout, source hashes, and tool versions;
- resuming cannot silently combine a different target or compiler identity;
- interrupted, failed, and timed-out candidates remain visible;
- one candidate reaching exact stops new work while recording in-flight work;
- status explains whether 500 source variants produced 500 ideas or 4 object
  basins.

### Journey D — “I want to generate useful mutations, not random text”

Add a project-neutral experiment manifest:

```json
{
  "schema": "decomp-workbench-experiment-v1",
  "family": "statement-grouping",
  "baseline": "candidate.c",
  "parameters": {"shape": ["split", "comma", "do-while"], "site": ["pad-loop"]},
  "invariants": {"selected_region": "format-body"}
}
```

The runner need not become a C rewriter immediately. First, accept manifests
produced by external generators and join their family/parameters to ledger
records. Later, ship a conservative library of proven source-equivalent
templates.

Acceptance criteria:

- source filenames are not the only parameter database;
- reports rank the best candidate per family and show basin transitions;
- selected-region constraints can preserve a solved block while ranking the
  rest;
- generated candidates are deterministic and never overwrite the active
  project source;
- negative family conclusions name the tested parameter space.

### Journey E — “Ordinary C levers are exhausted; which compiler decision?”

Instrumentation must be a staircase:

```text
view evidence → pass ownership probe → calibrated trace → focused causal probe
```

The next supported profile should be the scheduler, not a generic pointer dump.
Each record needs procedure, block, cycle, opcode/word, source line, ready-set
size, chosen node, and winning tie-break. It must pass tracing-off binary
identity, positive-control, unedited-replay, collateral-section, and project
output gates before documentation calls it supported.

After that, stable allocator web fingerprints should align webs by semantic
provenance rather than numeric ID. The useful answer is “this source lifetime
made color c2 unavailable to that carrier,” not two raw neighbor lists.

Acceptance criteria:

- stock and instrumentation-off outputs are identical in every scoped section;
- an included microcase proves each record can fire;
- trace schemas are versioned and documented;
- numeric compiler IDs are never presented as stable across source changes;
- forced decisions are labelled oracle evidence, never source matches.

## Prioritized product work

### P0 — trust and loss prevention

These belong in the base product:

- one compiler lifecycle helper for scratch checks and both campaign paths;
- per-candidate timeout with process-tree cleanup and recorded duration;
- strict scratch layout, size, checksum, and score validation;
- a distinct development version after every release;
- copy-paste-tested examples with explicit working directory;
- one default state namespace: `.decomp-workbench/`.

The current audit implements these items.

### P1 — make the common loop feel complete

1. Add `diagnose` or `compare --view`.
2. Add `check-scratch --view`.
3. Make the campaign ledger/manifest default, with an explicit `--no-ledger`
   escape hatch.
4. Add `campaign status` and `campaign resume`.
5. Add `cache status` and recoverable `cache prune --dry-run --older-than`;
   never delete by default.
6. Add `doctor --compile-command` as a no-candidate wrapper/toolchain preflight.
7. Put a schema version on every JSON report and emit a JSON error envelope
   whenever `--json` was requested.
8. Bound retained compiler stdout/stderr in terminal and summary modes while
   preserving complete streams only in an explicit artifact.
9. Consolidate `compile-rank` on the campaign engine, then document it as a
   compatibility convenience rather than a second campaign architecture.

### P2 — expert leverage and polish

1. Accept experiment manifests and report family trajectories.
2. Add selected-region constraints and register-permutation diagnostics.
3. Add a shareable, self-contained HTML export built from reduced evidence.
4. Add pager/width controls for large aligned views.
5. Add generated shell completions and a compact command map.
6. Introduce non-breaking command groups (`object`, `scratch`, `campaign`,
   `trace`, `instrument`) while retaining today’s flat names as aliases.
7. Test Windows process behavior in CI or change the platform classifier and
   support text to match the tested boundary.
8. Split the CLI dispatcher into journey modules; keep parsing and renderers
   separately testable.
9. Separate historical field notes from task-oriented docs in navigation,
   with explicit “historical” and “north-star” labels.

### P3 — calibrated compiler research

1. Productize the scheduler trace described above.
2. Add semantic allocator web fingerprints and interference-cause joins.
3. Add stack-home provenance and offset-centric reports.
4. Build the original-pass differential adapter with explicit user-supplied
   binaries and hashes.
5. Add compiler-variant fingerprint microcases and cross-ROM lineage reports.
6. Normalize host-specific pass-listing paths and formatting only after an
   unedited replay proves fidelity.

## Human factors

The workbench should preserve these rules as features are added:

- **Progressive disclosure.** Objects and retained dumps first, source levers
  second, traces last.
- **One vocabulary.** A terminal label, JSON key, census key, ledger field, and
  documentation term should not name the same fact five ways.
- **Proof labels.** Distinguish exact, structurally accepted, diagnostic,
  causal oracle, external score, and whole-project verification.
- **Refuse ambiguity early.** Conflicting selectors, unknown census keys,
  malformed force controls, mixed scratch roots, and changed resume identities
  fail before expensive work.
- **Show the next safe action.** Every non-exact verdict should end with one
  bounded lever or escalation path.
- **Never make cleanup a prerequisite for trust.** Cache pruning is explicit;
  evidence is append-only; an interrupt does not erase completed work.
- **Make synthetic examples honest.** Each fixture states which files are
  causally related and which merely exercise separate parts of the workflow.

## Product health measures

Track outcomes rather than command count:

- a new user reaches the first verdict from a clean checkout in under ten
  minutes without external assets;
- every redistributable documented command is executed in CI;
- no timed-out or interrupted compiler child survives a lifecycle test;
- all JSON reports and errors validate against a named schema;
- the same candidate ranks identically in compare, rank, and campaign views;
- a campaign can resume after interruption without recompiling a cached
  candidate or losing the reason it was generated;
- every supported instrumentation profile has negative, positive, replay, and
  collateral fidelity gates;
- the source-tree version cannot equal the latest release after unreleased
  behavior lands.

## Recommended build order

The highest-return sequence is:

1. finish the shared schema/error envelope;
2. combine compare and view in one diagnosis journey;
3. make campaign state default and add status/resume;
4. add cache lifecycle and compile preflight;
5. accept experiment manifests;
6. productize scheduler evidence;
7. add the deeper semantic allocator and pass-differential work.

That order keeps the common path wonderful before increasing the surface area
of the compiler-research layer.
