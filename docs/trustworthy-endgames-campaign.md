# The trustworthy endgames campaign

> **Implementation status (2026-08-11): shipped.** Phases 1–5 are implemented
> with synthetic integration coverage: independent scratch/project truth,
> experiment-v2 signals and serial controls, compiler/frontend envelopes,
> coverage-qualified conclusions and mechanism trajectories, immutable
> promotion, fresh finish receipts, documentation, packaged-skill guidance, and
> an asset-free end-to-end walkthrough. Live inputs remain local-only by the
> acceptance policy below; their hashes and metrics may be recorded without
> redistributing target material. The local SSB64 acceptance receipt is
> [recorded here](live-acceptance-2026-08-11.md).

The campaign originated in the measured failures of a 501-object, 0/133-word
SSB64 campaign and turns them into project-neutral workbench contracts.
Existing commands remain the foundation; the implementation extends them
instead of opening a parallel workflow.

Late-stage decompilation has two different failure modes that look the same to
the person doing the work:

1. the source has not reached the target; or
2. the experiment is measuring the wrong function, source, context, compiler
   control, or candidate.

The second is more expensive. A plausible zero-result sweep can close a useful
family for weeks. A reduced scratch can disagree with a byte-exact project
translation unit by three register words and send the user back into source
search. A mutable winner file can leave an object beside source that did not
produce it. None of those failures is visible in a scalar score.

This campaign makes the trustworthy path the easy path. Its product promise is:

> **Every result says what compilation envelope it measured, every custom
> signal proves its control before the sweep starts, every negative conclusion
> states its coverage, and every promoted winner is an immutable source/object
> receipt that can be freshly rebuilt.**

The workbench will continue to be a diagnostic and orchestration product. It
will not become an automatic source solver, a decomp.me upload client, or a
host for arbitrary user-written detector code.

## Why this campaign exists

The source campaign that motivated this plan reached a genuine full-TU match,
then exposed a final context-only decomp.me residue. The measured failures are
general:

| Failure | Consequence | General contract |
|---|---|---|
| a detector read words 4–6 from the whole `.text`, not the selected function | tens of thousands of candidates were falsely reported as having no condition fixpoint | a signal is always scoped to one selected function and target-aligned row set |
| a transfer detector searched for one word anywhere in the function | a different occurrence at row 72 impersonated the required row-30 event | row identity is part of the signal; presence alone is a different signal kind |
| a force environment was constructed but never passed to the compiler | an oracle sweep ran with every force disabled | a causal control must produce a receipt or an expected differential before any result is accepted |
| macOS workers re-imported a module-global default seed | a sweep labelled as champion-based actually ran from an older basin | the declared baseline is compiled first from its recorded hash; campaign work receives immutable candidate payloads |
| two narrow families were reported as impossibility results | randomized/wider composition later found witnesses | the UI says exhaustive, sampled, or unmeasured over a declared space; it never says universally impossible |
| an archive name was derived from a changing file count | old ledger names drifted to different objects | content identity, not ordinal filename, is the stable artifact reference |
| a mutable best-source file changed between object build and source copy | one archive held a source/object pair that never existed | promotion selects one ledger record and verifies both hashes atomically |
| the full project TU scored 0 while the reduced scratch scored 3 | the user saw a non-zero site result after the source campaign was complete | project truth, scratch truth, and site metadata are rendered as three separate layers |
| an added `void` declaration freed `$v0`; the original TU's implicit-`int` call occupied it | three tail rows used `$v0` instead of the target's `$v1` | call-contract hypotheses include invisible return-register occupancy, not only visible move/copy hunks |

These are not SSB64 features. They are failures of experimental identity,
control design, context fidelity, coverage language, and artifact promotion.

## What already ships and will be reused

The campaign must not duplicate capabilities already in the product:

- `diagnose` and `check-scratch --view` already align one function, distinguish
  pool from temp lanes, classify coherent register substitutions, and route to
  field-guide levers;
- scratch checking already leads with `ACCEPTED`/`NOT ACCEPTED`, keeps browser
  score separate from object evidence, and can perform a site-faithful local
  compile;
- campaigns already hash source, target, wrapper, environment, working
  directory, objdump, and compiled objects; ledgers are append-only and state
  is atomic;
- the campaign runner already owns compiler process groups, stops on exact,
  records in-flight work, and kills children on interrupt or timeout;
- experiment manifests already declare parameter spaces, baselines,
  homologous groups, and selected target regions;
- campaign status already preserves object basins, structural/temp prefix
  progress, failures, and the active hypothesis;
- `probe-deadread` exposes zero-instruction allocator levers;
- `campaign package` already promotes a validated ledger winner into a
  checksummed scratch bundle;
- `object collateral`, `handoff audit`, and the project build remain the gates
  outside the selected function.

The new work is the connective tissue between those capabilities.

## Users and complete stories

Each milestone must answer all applicable stories in terminal, JSON, and—when
the command already supports it—HTML. Expert evidence may be progressively
disclosed, but the underlying truth may not differ by presentation.

| User | Story | Done when |
|---|---|---|
| New contributor | “Tell me whether this is a source mismatch or a broken experiment without making me understand allocator internals.” | the first screen separates truth layers, names failed controls, and gives one safe next command |
| Project contributor | “My normal project TU is exact, but an isolated harness or scratch is not.” | one report compares target↔project, target↔scratch, and project↔scratch and labels the residual `context-only` when justified |
| decomp.me user | “The site says 99.xx%; should I use match override?” | `check-scratch --view` states acceptance, identifies the one causal residue when possible, and distinguishes a source edit from a context/prototype hypothesis |
| Campaign author | “I have score, frame, count, and two custom structural gates. Do not run 100,000 candidates if the gates are broken.” | declarative signals and controls preflight before parallel work and appear beside score in status |
| External generator author | “My generator owns source mutation; prove that the emitted baseline and grid are what my manifest claims.” | manifest validation hashes every emitted source, compiles the baseline first, and reports coverage over declared assignments without pretending to inspect generator internals |
| Compiler researcher | “I requested a force or trace. Prove that the control fired before interpreting it.” | instrument/oracle receipts and differential controls have one shared PASS/FAIL/UNKNOWN vocabulary and a failed receipt blocks the run |
| Alternate-frontend researcher | “An IRIX 4.x `accom` frontend may feed the same later backend; keep that cell distinct and test it without assuming ELF.” | compiler identity separates frontend, driver, language, backend, and wrapper; controls/signals consume the selected function produced by the wrapper, independent of its intermediate object format |
| Collaborator or reviewer | “Which exact source produced this object, and can I reproduce it?” | every promoted artifact names source hash, object hash, compile identity, ledger record/cache key, and fresh-verification receipt |
| Maintainer integrating a match | “A function is exact; what remains before I can merge it?” | one finish report gates fresh function verification, optional scratch truth, TU collateral, handoff integrity, and the caller's project/ROM command |
| Agent or CI consumer | “Give me the same result without scraping prose.” | additive versioned JSON exposes truth layers, controls, signals, coverage, artifacts, and next action with stable exit codes |
| Clean-room publisher | “Do not leak target code through a campaign ledger or HTML export.” | signals store target-relative predicates and booleans, not target instruction text or words; existing redaction rules still apply |
| Non-IDO or non-scratch project user | “Use the general trust features without giving me IDO-specific folklore.” | controls, signals, coverage, artifacts, and finish flow work compiler-neutrally; call-contract guidance is evidence- and frontend-gated |

## Product rules

These rules constrain every phase:

1. **Acceptance remains built-in.** Custom signals can rank, gate an experiment,
   and explain progress. They can never redefine `exact`, decomp.me acceptance,
   TU collateral, or project/ROM verification.
2. **No arbitrary detector plugins.** Signals use a small declarative grammar
   over comparison metrics and target-aligned rows. The workbench never imports
   or executes a Python callback from a manifest.
3. **Target-relative by default.** “Rows 4–6 equal the target” is durable and
   clean-room safe. Copying three target words into every ledger is not.
4. **Unknown is not failure and not success.** A missing symbol, unaligned row,
   absent object reader, or unavailable project build produces `UNKNOWN` with a
   next action. It never silently becomes false.
5. **Controls run before scale.** A campaign with declared controls schedules no
   ordinary candidates until every required control passes.
6. **The generator boundary stays honest.** The workbench proves the files and
   assignments it receives. It does not claim to know which seed lived inside
   an external generator worker.
7. **No mutable promotion.** A pathname is a convenience label. A campaign
   cache key plus source/object hashes is the artifact identity.
8. **Negative evidence has a denominator.** `0 hits` is rendered with visited,
   declared, excluded, sampling method, and control status.
9. **Context is a compiler input.** Project TU, scratch composition, frontend,
   driver, language, backend, prototypes, source-line reset, flags, cwd, and
   environment remain visible. IRIX 4.x `accom`, later `cfe`, and hybrid
   frontend/backend pipelines are different cells even when their final object
   reaches the same comparison engine.
10. **Advice is conditional.** A C89 implicit-`int` lever is never suggested for
    C++, a non-C frontend, or a residue that lacks the measured tail-call shape.
11. **One engine, one vocabulary.** New behavior extends `check-scratch`,
    `diagnose`, `experiment`, `campaign`, and `campaign package`; it does not
    create a second campaign runner or scoring implementation.
12. **Fresh verification is real work.** A finish command bypasses cached output
    for the selected winner and records that new object separately.

## The target UX

### A. One truth stack for project and scratch

Extend `check-scratch` with an optional project-side receipt rather than adding
a new scratch command:

```sh
decomp-workbench check-scratch scratch.zip --view \
  --project-object build/project-tu.o \
  --project-source src/module.c \
  --function func_name
```

The default screen remains concise:

```text
truth
  site metadata       score=15/13300                 context only
  scratch object      NOT ACCEPTED  raw words=3      selected function
  project object      EXACT         raw words=0      selected function
  context differential             3 pool-register rows, one web

context hypothesis
  call contract: code.c declares helper() void; project source has no visible
  declaration at this call. Under C89, implicit int occupies v0.
  confidence=measured-shape, not source proof

next: test one explicit `int helper();` variant in the scratch context.
```

If no project object is supplied, today’s scratch-only path remains unchanged.
If no project source is supplied, the report can classify the context
differential but must not claim a declaration mismatch.

The same structured block appears under optional JSON keys
`truth_layers`, `context_differential`, and `context_hypotheses`. Existing keys
retain their meaning.

### B. Better call-contract routing

The current field-guide routing limits the implicit-`int` lever to a visible
move/copy. That misses a second measured shape: a call return that is unused in
C but still occupies `$v0`, changing the pool choice for a later indirect call.

Broaden lever 17 only when all applicable evidence agrees:

- language/frontend supports C89 implicit declarations;
- the residual is opcode- and temp-lane-stable;
- the first divergence is one coherent pool substitution;
- it begins after a direct call and is confined to address/materialization rows
  for a later call or tail region; and
- scratch/source context contains an explicit `void` declaration, or project
  context proves a different visible return category.

The footer should say **test**, not **change**. A compiler-generated allocation
shape is evidence for a one-variant probe, not proof of the original prototype.
False-positive fixtures—ordinary register swaps after calls, C++, and visible
non-tail allocation ladders—must suppress the suggestion.

### C. Declarative experiment signals

Add optional signals to a new input manifest schema,
`decomp-workbench-experiment-v2`. Version 1 remains accepted unchanged and is
normalized into the same internal model.

```json
{
  "schema": "decomp-workbench-experiment-v2",
  "family": "lifetime-barriers",
  "baseline": "baseline.c",
  "parameters": {"site": ["after-f7", "after-w0", "after-w1"]},
  "signals": [
    {
      "id": "transfer-row",
      "kind": "target-rows-exact",
      "rows": [30],
      "required": true
    },
    {
      "id": "condition-window",
      "kind": "target-rows-exact",
      "ranges": [{"start": 4, "end": 7}],
      "required": true
    },
    {
      "id": "shape",
      "kind": "metrics",
      "equals": {"insns": 133, "frame": -56},
      "required": true
    }
  ],
  "controls": [
    {
      "id": "baseline-receipt",
      "candidate": "baseline.c",
      "expect": {
        "words": 8,
        "signals": {"transfer-row": "PASS", "condition-window": "PASS"}
      }
    }
  ],
  "candidates": [
    {
      "source": "baseline.c",
      "parameters": {"site": "after-f7"}
    }
  ]
}
```

Initial signal kinds stay deliberately small:

| Kind | Meaning | Durable receipt |
|---|---|---|
| `target-rows-exact` | candidate rows paired to named target rows are raw- or relocation-aware exact, selected explicitly | row/range identity, comparison mode, PASS/FAIL/UNKNOWN; no target words |
| `target-region-exact` | one named half-open target region is exact | region and counts |
| `metrics` | built-in metric equality/range predicates | metric names, expected predicate, observed values |
| `residual-classes` | allowed/forbidden aligned residual classes | class counts and predicate |

Signals are evaluated through the same selected-function load and alignment
used by `compare`. A signal may not perform a second whole-section read.
Rows outside the selected function or absent after alignment return `UNKNOWN`.

Required signals are hard experiment gates, not new definitions of exactness.
Optional signals are trajectory evidence and can rank a dominated but
mechanistically useful basin.

### D. Controls and canaries

Controls are candidates with expected receipts. The runner compiles required
controls serially before opening the ordinary job pool.

A control receipt includes:

- manifest and source SHA-256;
- rendered compiler command, cwd, explicit environment, compiler identity,
  target identity, and objdump identity;
- output object SHA-256;
- built-in metrics and signal outcomes;
- `PASS`, `FAIL`, or `UNKNOWN`, with one reason and one next action.

Two control forms cover the observed failures:

1. **Absolute control:** one source must reproduce expected metrics/signals.
   This catches wrong function selection, wrong baseline, stale target, and a
   detector that never fires.
2. **Differential control:** two declared control candidates must differ in a
   named signal, metric, or object hash. This catches a force/environment knob
   that was requested but ignored.

A failed required control exits 2 and schedules zero ordinary candidates.
`UNKNOWN` blocks a required control because the question was not measured.
Optional controls may remain visible without blocking.

The workbench already sends immutable `Candidate` values to its compiler pool.
The new preflight verifies the emitted baseline and assignment. Documentation
must explicitly say it does not inspect an external generator's internal
workers; the generator should emit a baseline assignment and let the workbench
referee it.

### E. Coverage and conclusion language

Normalize the existing sweep coverage record and experiment parameter grid into
one status block:

```text
coverage: sampled 18,781 / 41,472 declared assignments
method: seeds=804801..804804, without replacement
excluded: 512 invalid combinations (rule: frame budget)
controls: 2/2 PASS
result: no sub-8 candidate observed in this sampled space
```

Only these conclusion labels are allowed:

- `exhaustive-over-declared-space`;
- `sampled-over-declared-space`;
- `partial-interrupted`;
- `control-invalid`;
- `coverage-unknown`.

The terminal and HTML should never synthesize “closed”, “impossible”, or
“cannot” from zero hits. A user may record stronger prose in a note, but the
structured report keeps the measured scope beside it.

Campaign status should show two trajectories:

- **acceptance trajectory:** exactness and ordinary comparison metrics;
- **mechanism trajectory:** required/optional signal transitions and selected
  prefix/region gains.

This preserves a dominated 54-word body that proves a previously unreachable
register color without promoting it over an 8-word score champion.

### F. Immutable artifact promotion

The underlying cache is already content-addressed. Make that identity visible
at every promotion boundary:

```text
winner
  record       4f2c…
  source       champion.c  sha256=…
  object       cache/9a1c…o sha256=…
  target       sha256=…
  comparison   raw exact; relocation targets exact
```

`campaign package` and the finish flow must select a ledger record/cache key,
then verify that the source and object hashes still match. They must never copy
“whatever is currently in best.c”. Friendly aliases remain useful, but reports
label them aliases.

If a source path changed after its ledger record, promotion refuses and points
to the immutable recorded hash. An explicit recompile creates a new record; it
does not rewrite the old one.

### G. One finish flow

Add `campaign finish` as a thin orchestrator over existing engines, not a new
comparator:

```sh
decomp-workbench campaign finish CAMPAIGN \
  --selection score \
  --scratch-context scratch/ctx.c \
  --collateral-reference build/reference-tu.o \
  --handoff /path/to/proof-repo \
  --project-command './verify-project.sh'
```

The command is non-destructive. It does not edit the project, upload a scratch,
commit, push, or declare a ROM healthy without running the caller's command.
It performs and records:

1. resolve one immutable winner record;
2. bypass the campaign object cache and freshly rebuild the recorded source
   with the recorded wrapper/environment;
3. require selected-function raw/relocation exactness;
4. re-evaluate required signals as regression evidence;
5. optionally compile the scratch context and render the truth stack;
6. optionally run `object collateral` against the containing TU;
7. optionally run `handoff audit`;
8. optionally invoke the caller-supplied project verification command under the
   normal process/timeout/output contract;
9. write an exclusive `decomp-workbench-campaign-finish-v1` JSON/HTML receipt.

The receipt reports each gate independently. A missing optional gate reads
`NOT RUN`, never `PASS`. Function exactness can coexist with scratch mismatch,
collateral failure, or project verification not run without collapsing those
truths into one green badge.

## Delivery phases

Every phase is independently releasable, tested, documented, and useful. Do
not hold the call-contract fix behind the larger manifest work.

### Phase 0 — contracts and redistributable fixtures

**Goal:** freeze vocabulary and reproduce the failures without shipping game
code or proprietary compilers.

Deliverables:

- this campaign document and an ADR-sized schema note for signals/controls;
- retained synthetic objdump fixtures for:
  - one coherent pool substitution after a call;
  - an identical word at the wrong function and wrong row;
  - an insertion before a target-relative signal range;
  - an ordinary post-call register swap that must not trigger call-contract
    advice;
- source-only context fixtures for explicit `void`, explicit `int`, implicit
  declaration, C++, and conflicting declarations;
- a redaction fixture proving signal receipts do not retain target words or
  instruction text;
- a live, unshipped acceptance note recording the SSB64 scratch receipt by
  hashes and metrics only.

Gate: the fixtures fail against current behavior for the intended reason and
contain no target assembly, target words, ROM bytes, or proprietary binaries.

### Phase 1 — context differential and call-contract UX

**Goal:** make the three-word decomp.me case a one-screen diagnosis.

Likely touchpoints:

- `scratch_check.py`, `scratch_registration.py`, and `cli.py` for project-side
  inputs and source composition;
- `diagnosis.py`, `view.py`, and `comparison_render.py` for the context
  differential;
- `field_guide.py` and the packaged guide copy for evidence-gated lever 17;
- `html_report.py` and JSON reporting for the truth stack;
- scratch, diagnosis, field-guide, HTML, and CLI UX tests.

Acceptance:

- the measured SSB64 bundle reports scratch 3, project 0, and one context-only
  late register web while suppressing the call-contract probe because no
  qualifying direct call is nearby;
- a redistributable positive fixture with the measured call shape offers
  exactly one scratch-only `int` declaration probe;
- C++, non-C89, and unrelated post-call substitutions do not receive the hint;
- scratch-only invocations remain byte-for-byte compatible in their existing
  headline and exit behavior;
- JSON and HTML contain the same facts as the terminal.

### Phase 2 — experiment-v2 signals and control preflight

**Goal:** make a broken detector or baseline stop before scale.

Likely touchpoints:

- `experiments.py` for v1/v2 loading and normalized signal/control models;
- one new focused module for signal evaluation over an existing `Comparison`;
- `campaign.py` for serial control preflight and per-result signal receipts;
- `campaign_state.py` and `campaign_cli.py` for durable status/resume/export;
- `schema.py`, ledger redaction, and JSON docs;
- experiment, campaign, lifecycle, state, and redaction tests.

Acceptance:

- a target-row signal cannot pass on the same word in another function or row;
- an aligned target range survives a candidate insertion before the range;
- a wrong source hash, wrong baseline score, or ignored differential knob stops
  before any ordinary candidate starts;
- an IRIX 4.x `accom` wrapper and a later `cfe` wrapper retain distinct compile
  identities, while signals evaluate their selected final function without an
  ELF-only or intermediate-format assumption;
- interrupting a control kills its compiler process tree and records the
  interruption;
- resuming with changed controls/signals refuses the old campaign identity;
- v1 experiment manifests and campaigns behave exactly as before;
- no signal can make a non-exact candidate report exact or accepted.

### Phase 3 — coverage, mechanism trajectories, and artifact UX

**Goal:** make “what did we actually test?” and “which dominated basin taught us
something?” visible without reading a TSV.

Deliverables:

- normalized coverage in experiment/campaign status and export;
- the five conclusion labels and their exit/census predicates;
- signal transitions in trajectories and basin summaries;
- explicit immutable record/source/object identity in status and package;
- refusal tests for changed mutable source aliases;
- compact terminal defaults with `--show-all`/HTML for the complete grid.

Acceptance:

- an exhaustive 64/64 grid and a sampled 8/64 grid can never render the same
  conclusion label;
- an interrupted run says how much ran and does not turn zero hits into a
  negative conclusion;
- a worse word score with a newly passing signal is retained and visible as a
  mechanism transition;
- source/object race and ordinal-archive regression fixtures refuse promotion;
- output remains bounded on a 100,000-candidate synthetic ledger.

### Phase 4 — auditable finish and handoff

**Goal:** turn exactness into a complete, reproducible handoff without implying
that optional project gates ran.

Deliverables:

- `campaign finish` terminal/JSON/HTML;
- fresh no-cache rebuild receipt;
- optional scratch, collateral, handoff, and project-command gates;
- exclusive output and restart behavior after an interrupted finish;
- `campaign package` integration using the finish receipt when present.

Acceptance:

- a cached exact object whose source has changed cannot finish;
- fresh function exact + scratch mismatch renders both accurately;
- function exact + collateral failure exits 1 and never prints a global PASS;
- `NOT RUN` is preserved for every omitted gate;
- a timed-out project command loses all child processes and keeps bounded full
  diagnostics in the requested artifact directory;
- re-running against an existing explicit report refuses to overwrite it.

### Phase 5 — complete-journey integration and release

**Goal:** make the behavior discoverable for every supported user, not only the
campaign author who requested it.

Deliverables:

- updates to `START_HERE`, `campaigns`, `decompme-exports`, `field-guide`,
  `workflows`, `product-status`, `json-contracts`, troubleshooting, and the
  packaged Agent Skill;
- root command discovery and completions for new flags/operations;
- one end-to-end walkthrough from downloaded ZIP to context diagnosis, exact
  scratch, campaign control preflight, exact winner, and finish receipt;
- migration examples for experiment v1→v2 and no forced migration for users who
  need none of the new fields;
- release notes that distinguish new evidence from existing capabilities.

Release gate:

- supported Python/OS CI and distribution smoke pass;
- runnable documentation commands pass from the directory each page states;
- terminal/JSON/HTML parity tests pass;
- package contains updated docs, fixtures, schemas, and skill references;
- `python -m decomp_workbench` and installed console entry point both complete
  the walkthrough;
- a clean environment reproduces the synthetic journey without a ROM,
  proprietary compiler, or network;
- live acceptance is recorded on at least one project full-TU campaign, one
  decomp.me export, one non-scratch campaign, and one authentic alternate
  frontend cell (the existing IRIX 4.x `accom` route when available).

## Compatibility and schema policy

- `decomp-workbench-experiment-v1` remains accepted indefinitely within the
  existing compatibility policy. It receives no implicit required controls.
- `decomp-workbench-experiment-v2` adds controls, signals, and normalized
  coverage. A migration command is unnecessary; the docs show the additive
  fields and v1 remains the simplest valid manifest.
- Existing success reports may gain optional additive keys under their v1
  schemas. No existing key changes meaning. Any meaning or type change requires
  a new schema.
- New finish receipts use `decomp-workbench-campaign-finish-v1`.
- New control/signal status values are exactly `PASS`, `FAIL`, and `UNKNOWN` in
  JSON; terminal casing follows existing presentation conventions.
- Flat commands and task-group aliases remain equivalent.
- Default campaign behavior without a v2 manifest is unchanged.
- Existing cache entries and campaign manifests remain readable. New identity
  inputs participate only when controls/signals are declared.

## Test strategy

The campaign is finished only when the failure modes are tests, not anecdotes.

### Unit tests

- v1/v2 manifest parsing, unknown fields, duplicate IDs, invalid ranges, and
  clean error messages;
- target-relative signal evaluation under exact, inserted, deleted, relocated,
  missing-symbol, and ambiguous-alignment cases;
- call-contract evidence gates and suppression cases;
- coverage math and conclusion labels;
- source/object/record identity checks;
- redaction of target text and words.

### Integration tests

- controls execute before ordinary candidates at `--jobs > 1`;
- failed and unknown required controls schedule zero ordinary work;
- differential controls catch an ignored environment setting;
- interruption and timeout terminate the whole process group;
- resume identity changes when signal/control definitions change;
- scratch/project truth stack and finish orchestration share one comparison
  implementation;
- terminal, JSON, HTML, ledger, status, and export agree.

### Property and scale tests

- target-relative row signals do not change when arbitrary equal-length exact
  prefixes are prepended outside the selected function;
- content identity is independent of filename and candidate enumeration order;
- coverage never exceeds the declared space and exclusions are disjoint from
  visited assignments;
- bounded renderers stay bounded on large synthetic ledgers;
- no sampled run can acquire an exhaustive conclusion through sorting,
  resuming, or merging.

### Live acceptance without redistribution

The real SSB64 inputs remain outside the repository. Acceptance records only:

- input hashes and tool identities;
- project/scratch instruction counts, frames, sizes, and mismatch counts;
- signal/control outcomes;
- the one-line next action and final exact result.

No ROM bytes, target objects, target disassembly, or compiler binaries enter
the repository.

## Risks and how the design contains them

| Risk | Containment |
|---|---|
| custom signals become a second scoring language | four initial kinds only; built-in exactness remains authoritative |
| call-contract advice overfits one SSB64 function | strict frontend and residual-shape gates plus negative fixtures; language says “test” |
| v2 makes simple campaigns harder | v1 and manifest-free flows remain unchanged |
| control preflight slows small grids | only declared controls run; their cost prevents much larger invalid runs |
| project and scratch objects are built by incomparable wrappers | report identities and `UNKNOWN`; do not synthesize context-only without comparable selected functions |
| coverage metadata is dishonest | derive visited counts from ledger; accept declared total/exclusions only after manifest validation |
| finish becomes a build-system abstraction | caller supplies existing wrappers; finish orchestrates and records, never invents project commands |
| reports leak copyrighted target code | target-relative predicates and redacted receipts; HTML target rows retain the existing explicit warning and opt-in behavior |
| expert detail overwhelms newcomers | one truth stack and one next action by default; grids, receipts, and identities behind `--show-all` or HTML |

## Definition of done

The campaign is complete when all of these are true:

1. The downloaded-scratch story reaches the correct context-only diagnosis
   from one command, and call-contract advice appears only when its direct-call
   and declaration evidence is actually present.
2. A project contributor can see “project exact, scratch context differs”
   without either result overriding the other.
3. A campaign with a broken detector, ignored force, stale baseline, or wrong
   selected function stops before parallel candidate work.
4. Every zero-hit conclusion carries control status and a coverage denominator.
5. A dominated candidate that crosses a declared mechanism signal remains
   visible beside the score champion.
6. Promotion and finish operate on immutable ledger records and reject a
   mutable source/object mismatch.
7. Fresh function verification, scratch acceptance, TU collateral, handoff,
   and project verification are distinct gates in one receipt.
8. Existing users who do not opt into v2 signals/controls see no behavior or
   schema regression.
9. Humans, agents, and CI consume the same facts and next action.
10. The entire redistributable walkthrough runs without game assets,
    proprietary tools, or network access.

That is the general lesson of the source campaign: the final few words are not
only a compiler problem. They are a product test of whether the workbench can
distinguish a hard decompilation problem from an experiment that quietly asked
the wrong question.
