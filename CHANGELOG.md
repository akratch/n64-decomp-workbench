# Changelog

Narrative release notes with the design reasoning behind each change are kept
in [design notes](docs/history/design-notes.md).

## Unreleased

### Added

- `public-match-check` queries public decomp.me for an existing match by name,
  `--address`, and `--max-score`/`--instructions`; `--fail-on-match`, `--json`.
- `fetch-scratch SLUG [--outdir]` downloads one validated scratch export;
  an already-fetched scratch is reported without a request unless `--force`.
- A shared standard-library HTTP client: identifying `User-Agent` with
  `--contact`, one retry with backoff, and an explicit refusal on HTTP 403.

### Changed

- `commands --json` carries a top-level `network` inventory of which commands
  may open a connection, replacing the blanket `safety.network: false`.
- `view` reports `verdict: register-ring-only` for ring-temp-only residuals;
  `--emit-force-spec` refuses a wholly ring-only residual.
- `trace-globalcolor --lineage-table` explains an empty result and that
  lineage records need `CDX_LINEAGE_TABLES` at capture time.
- Documentation corrections: field-guide lever 28, source-probes,
  object-comparison, troubleshooting, and decompme-exports pages.

### Fixed

- A relocation whose sides name different symbols is counted as
  `relocation_symbol_mismatches` (`reloc_syms=`) instead of masked to zero.
- `--function` on a target with a stripped symbol falls back to the
  whole-section positional path with a warning, across all comparison commands.
- `trace-scheduler` capture guidance captures both output streams, and
  `besttime` enters the tie-break chain above `aftercycles`.
- An instruction that slides inside a block reports as a schedule decision
  instead of `structural`.
- Control characters from objdump are dropped at the parse boundary and no
  longer reach `--json` (tab is kept).

## 0.5.0 - 2026-08-12

### Added

- `trace-frame` prints the frame ladder from `CDX_SYMTAB` or `webdetail`
  records, with `--ops`; the `CDX_SYMTAB` patch ships in the package.
- `trace-scheduler --from-as1-r` reads `as1`'s native `-R` selection trace
  (`cc -Wa,-R`, byte-inert), computing `tie=` from the losing candidates.
- `shift audit --blobs auto`/`--emit-whitelist`/`--elf`, `shift rehearse`
  `--base-elf`/`--anchor auto`, new `shift config verify` and `shift plan`.
- `shift audit` (static pin/word ranking) and `shift rehearse` (delta-corrected
  relink requiring `unexplained=0`, two deltas); `docs/shiftability.md`.
- `--OPTION-from FILE` on every list-valued option, with a shell-lint test
  over documented and shipped shell.
- `note reserve` claims a note identifier with `O_EXCL`; `note add` refuses
  another owner's reservation without `--author`/`--force`.
- `campaign survey` reads a manifest-less campaign directory: stages, findings
  logs, sweep manifests, and instrument-gate stamps, with `--budget`.
- `instrument gate` records the identity gate as a stamp with hashes and
  scope; `--verify` re-runs the comparison and reports `STALE`.
- `sweep regress/hoist/commute/copies/fuse` (plus `donors` and `carriers`),
  keyed by (site, class, carrier); `sweep ingest`; `docs/sweeps.md`.
- `slots` prices fusion donors per frame offset, marking width-punned slots
  `PUN`, with `--source --volatile-probe DIR` variant emission.
- `probe-equiv` prints a non-escaping local's same-value ranges between
  definitions, with `--at LINE --at LINE` for the pairwise question.
- `probe-deadread` lists positions where a discarded read can move the
  allocator, with the spelling table, `--reach textual`, and `--write DIR`.
- `trace-cascade` prints every allocator round at a `--frame-offset` site;
  `trace-order` ranks the colouring order; `trace-blocks` intersects webs.
- `align`/`align-dumps` print the edit script between instruction streams with
  a distance headline, `--window LO..HI`, and shift-diff JSON.
- `phase` reads the scratch-ring phase per named row slot, printing coset,
  quotiented, and positional counts; `docs/shift-and-phase.md`.
- `--disassembly-cache DIR` on `align`/`phase`, trusted only when an entry
  proves it is a complete disassembly of the object on disk.
- `compare` and `diagnose` name each commutative operand pair in
  `commutative_findings`, including crossed operand loads.
- `SweepCoverage` records visited/excluded points and derives
  *swept-exhaustively* versus *sampled*; `experiment compose --step N`.
- `force-rows`/`force-rows-dumps` report which object rows an allocator
  control owns, with `--target`, `--gap N`, and `BYTE-INERT` results.
- `window`/`window-dumps` print named aligned rows side by side in the
  `aligned_row` numbering `compare --json` publishes.
- `experiment review-mutation` gates a sweep winner on its diff, flagging
  `read-before-definition`/`definition-removed` and `write-removed`.
- `probe-lines --tie STATEMENT=LINE` tests a line-owned schedule verdict via a
  `#line` reassignment, with `next:` routing on every verdict.
- Field-guide lever 28: alias a local (`if (&x);`) to remove it from the
  allocation contest, with `trace-globalcolor` symptom annotations.
- Field-guide lever 2 (accom operand reversal) and lever 26 (the pad slot for
  vacated stack slots).
- `experiment inspect-source` inventories suspicious statics; `experiment
  compose` applies bounded exact-text transformations with a sidecar.
- `object collateral` compares all in-scope section, relocation, and symbol
  contents, separating `outside-selected-function` changes.
- The SSSV endgame [case study](case-studies/sssv-func-802963D0.md), with
  field-guide lever 27 and the packaged Agent Skill workflow.
- `handoff audit` gates public proof repositories: relative paths, absolute
  user paths, untracked files, and cross-project dependencies.
- Redistributable dense-four and dense-five switch-lowering probes report
  comparison chain versus computed jump across frontends.
- Field-guide lever 25: line-number ties by splicing, with a
  [case study](case-studies/ssb64-unref-800036B4.md).
- `check-scratch` reports line-splice hazards in `code.c`, including a
  backslash followed by trailing whitespace.

### Changed

- Documentation and worked examples carry executable, tested contracts, with
  uncleared third-party CV64 payloads removed.
- The workbench fails closed at the seams: objdump ELF probes, sealed campaign
  environments, a `.decomp-workbench.toml` layer, and Windows contracts.
- Campaign endgames finish with receipts: experiment v2 controls and coverage,
  `campaign finish` gates, and `campaign package --finish-receipt`.
- `trace-webs --against` reports which identity field failed alignment and
  whether a rebuild would help, per field and producing record.
- Late-stage campaigns preserve evidence: `ACCEPTED` leads, `campaign
  --rank-by temp-prefix`, `trace fifo --emission-map`, `campaign package`.
- `next` routes an allocation-shaped verdict to `oracle plan` at family rank,
  ahead of region attribution; `docs/oracle.md` explains the ceiling rule.
- `compare` prints a `raw-vs-words:` note whenever `raw` exceeds `words`,
  naming the relocation-controlled floor.
- Literal-pool accesses are compared by resolved slot: new `pool` and
  `pool_layout` classes; same-symbol different-addend sites are `pool_layout`.
- Aligned row counts say when they are not comparable: `opcodes=`/`gaps=`, an
  alignment caution, and mixed-alignment ranking on `words`.
- `score` prints one screen line (`sha ni frame ld st coset`), with `--slot
  OFFSET` narrowing and a coset caution.
- `next` routes an instruction-count difference to `align` and a float run to
  `phase`.
- Instrument records name what they measure: `nocs` as three named fields,
  `class` as the IR register class, and the new `ALLOC_FP` hook.
- Every generated sweep edit states its base, refusing on SHA-256 mismatch,
  failed anchors, or `--frozen LO..HI` zones.
- Scratch acceptance separates linked exactness, raw word identity, and
  relocation identity, reported as `decomp_me_score_proxy_exact`.
- Allocator comparisons expose uncertainty: ambiguous webs block `aligned`,
  and empty captures report `no-evidence` with nonzero status.
- Allocator trace comparison separates identity from outcome, reporting
  carrier substitution instead of false identity.
- `oracle force` accepts a validated comma-separated force set and records the
  baseline-to-forced instruction delta.
- `trace copy-decisions` reports coalesce-versus-temporary outcomes with a
  conservative parser and is listed in group help and completion.
- Frame recovery and campaign handoff retain diagnostic state, with a
  wrong-frame playbook and visible metadata recovery.
- Scratch bundles record label, compiler ID, language, and preset separately;
  `check-scratch` reports the frontend and uses `src.cxx` for old C++.
- Line-layout guidance is frontend-specific: cfe splice behavior kept separate
  from NCC/EDG statement attribution.
- Frontend-lineage guidance no longer generalizes `cfe` to all of IDO and
  requires inspecting the actual phase command and intermediate.
- The campaign skill carries the campaign-strategy lessons: scoped negatives,
  residual-fixing variants as baselines, and credited falsifiers.

### Fixed

- No data-selecting option may default to a directory outside the workbench's
  own `.decomp-workbench` state, and a test enforces it.
- `coset=?` (no ring-carrying rows) is no longer reported as a rotation.
- `decomp-workbench probe` and `decomp-workbench sweep` list their operations
  instead of answering "not a command".
- One corrected float colour map (`c24=$f0` through `c29=$f18`), served by
  `register_for_color` to every trace report.
- The IDO 5.3 float temp ring is documented as four wide (`f4 f6 f8 f10`);
  `f16`/`f18` are withdrawn before the first allocation.
- `audit-handoff` failure on a relative root quotes the argument as typed and
  the working directory it was resolved against.
- The `--register-profile ido53` pool/temp split is corrected from probes,
  with the old table as `unverified` and `register_profile_evidence` in JSON.
- Symbol-table asymmetry no longer manufactures relocation rows: branch and
  jump destinations are normalized on both sides before classing.
- `cache` and `context` print their operation map and exit 0 without an
  operation, matching the other command groups.
- `view` and `view-dumps` accept the long-advertised `--show-all`.
- `check-scratch` accepts current C++ export members (`code.c++`/`ctx.c++`,
  plus `.cc`, `.cpp`, `.cxx`) instead of reporting `code.c` missing.
- `python -m decomp_workbench` works instead of failing with "No module named
  decomp_workbench.__main__".

## 0.4.0 - 2026-07-31

### Added

- `diagnose --candidate-listing LISTING.s` reports per-site `.loc` statement
  lines, promoting `playbook=line-assignment-probe` on a boundary majority.
- `probe-lines` proves or refutes line-assignment sensitivity via
  token-identical line reflow; `docs/line-assignment-probe.md`.
- `context lint` flags `#if`/`#elif` guards whose identifiers are all
  undefined; `check-scratch` runs it over ctx+code (lever 24).
- `score` windows a function via `--function` or `--between` with a relocation
  floor and `--control` checks; `matrix` clusters variants into attractors.

### Changed

- Campaign ledgers redact the target ROM's instruction text: salted 16-bit
  `target_digest`, masked opcodes, and salts in a `<ledger>.salt` sidecar.
- Ledger redaction filters site records through the `SITE_KEEP` allow-list;
  the salt is load-bearing, and `--html`/`force_spec` are documented leaks.

### Fixed

- The redaction sweep enters all container types, inspects keys and
  allow-listed values, and caps depth (six demonstrated bypasses closed).
- The unredacted-ledger resume warning streams every record instead of capping
  at 4096 lines, and says how far an explicit cap got.

## 0.3.1 - 2026-07-30

### Changed

- The bundled Agent Skill routes agents through the `next:` footer and
  `guide`, mandates a harness proof, and adds `references/frontend-lineage.md`.
- The README shows an ANSI-faithful SVG of a fixture diagnosis and a
  screenshot of the HTML report, both generated from shipped fixtures.

## 0.3.0 - 2026-07-30

### Added

- `decomp-workbench guide <topic>` prints the packaged field guide's sections
  for a playbook, verdict vocabulary, or lever number, offline.
- [From verdict to edit](docs/from-verdict-to-edit.md) walkthrough and a
  glossary in the documentation index.
- Alternate-frontend documentation: `docs/alternate-frontends.md`, field-guide
  levers 20-22, and SSB64 field notes.
- Four one-line vocabulary explanations at first use, removable with
  `--terse`; `--html` renders each lever as a runnable `guide N` snippet.
- A compact `webs:` header line, with substituted register tokens coloured by
  web.
- Every `next:` footer names the matching field-guide levers, the `guide`
  command, and both answers to "do you have an instrumented toolchain?".
- `diagnose`/`diagnose-dumps` render exact truth plus aligned mechanism
  evidence; `check-scratch --view` reuses the imported comparison.
- A durable campaign cockpit: manifest and append-only ledger under
  `.decomp-workbench/`, `campaign status/note/resume/export`, sidecars.
- Compiler-research adapters: `toolchain init/calibrate/status`,
  `DKWB-SCHED-V1` records, hash-pinned profiles, fingerprint microcases.
- Semantic allocator and source provenance views: web fingerprints, stack-home
  ownership, and `trace-source` joins through `.file`/`.loc`.
- `--census KEY=VALUE[,...]` on the comparison commands: assert reported
  values as exit codes (0 pass, 3 fail, 2 bad question).
- Three narrative pages: `docs/START_HERE.md`, `docs/field-guide.md`, and
  `docs/walkthrough-30-near-matches.md`, with executed doc-command tests.
- `doctor` (readiness and bundle validation) and `check-scratch`
  (extraction-free scratch reading with an optional compile mode).
- Three verdicts split out of the volume-based classes: `constant-mismatch`,
  `commutative-order`, and `schedule-mismatch`, each with its lever.
- `--function` as a second spelling of `--symbol` on every single-function
  command, with conflicting values rejected.
- `view` and `view-dumps`: the aligned mechanism view with two-pass LCS
  alignment, per-hunk classes, register lanes, webs, and lever guidance.
- The portable `n64-decomp-campaign` Agent Skill for Codex and Claude Code,
  with installation guidance and reusable campaign evidence.
- Action-oriented comparison verdicts, relocation-only raw-difference
  explanations, and a separate cross-ROM structural-evidence mode.
- Object-basin reporting in campaigns, visible in terminal and JSON summaries.
- Focused `trace-globalcolor --proc ... --web ...` inspection with trustworthy
  callee-saved register names.
- A final-function campaign guide covering the Hartley, Titania, and Aquas
  evidence patterns.
- Deterministic, upload-neutral decomp.me scratch bundles with copied inputs,
  settings, and checksums.
- A five-function Castlevania 64 walkthrough with complete scratch inputs.
- Documentation of the supported IDO 5.3 and 7.1 workflow matrix and the
  instrumentation profiles' version boundary.

### Changed

- Symbol selection falls back to a unique case-insensitive match, for
  identifier-folding frontends such as `upas`.
- `--width` wraps the `next:` footer on word boundaries with indented
  continuations instead of truncating it.
- The HTML report is rebuilt from the terminal's view model: verdict bar,
  lanes, linkable hunks, and a `Webs` table — still one self-contained file.
- An unknown command names itself and points at `decomp-workbench commands`
  instead of printing argparse's full catalogue.
- With no `--function` and one differently-named symbol per side, the
  comparison commands warn ahead of the verdict and name the fixing option.
- The novice path is legible: the bare program name welcomes and exits 0, and
  `docs/README.md` glosses IDO, asm-processor, ugen/uopt, and decomp.me.
- Missing-symbol and objdump `file format not recognized` errors name the
  likely cause before quoting the tool.
- `allocation-mismatch` footers lead with `view`/`diagnose` and the levers,
  gating traces on lever exhaustion plus an existing instrumented toolchain.
- Main identifies itself as `0.3.0.dev0` instead of reusing the published
  `0.2.0` identity.
- The allocator oracle is productized: `oracle plan/diff/force/sweep` use the
  campaign engine and `status/export` reopen persistent evidence.
- Evidence boundaries hardened: LCS-aligned region scores, phase-qualified
  allocator details, and forced exactness causal only after a control.
- Automation standardized on one versioned JSON document, with a command map,
  task-group aliases, shell completions, and expanded CI.
- Compiler execution shares one lifecycle contract: 120-second default
  timeout, explicit environment/cwd controls, and process-group cleanup.
- Scratch handoffs hardened: one flat ZIP root, refused nested or symlinked
  content, real SHA-256 checksums, and rejected impossible scores.
- Examples and campaign state standardized on repository-root commands and
  `.decomp-workbench/`, with schema-versioned JSON reports.
- `--objdump PATH` is authoritative: a misspelled explicit path fails
  immediately, and `doctor` verifies the reader against `target.o`.
- `schedule-mismatch` requires a matching instruction multiset, so a
  reordering that also moves a register is not "not allocation".
- Compiler termination escalates from `SIGTERM` to `SIGKILL`, with own process
  groups on Python 3.11+ and the guarantee scoped to POSIX.
- The packaged bundle under `src/decomp_workbench/skills` is the only skill
  tree, enforced by a test.
- Globalcolor instrumentation is phase-explicit: `phase=p1`/`p2` records,
  phase-qualified `CDX_FORCE` keys, and decoded machine registers.
- Instrumentation fidelity gates are documented as section-scoped, because
  stock IDO under `-g3` is not file-level reproducible.
- The campaign runner owns its process groups, terminating compilers with
  their children on failure or interrupt.
- Campaigns stop on the first exact match by default (`--no-stop-on-exact`
  sweeps the whole grid), with the repeated target disassembly removed.
- Human labels and JSON keys unified behind one metric registry with
  `--explain-keys`; long-form JSON keys deprecated for one release.
- `view`/`view-dumps` reject `--symbol`/`--function` conflicts, gain
  `--explain-keys`, and move beside `compare` in the help listing.
- The aligned view's keys live in the shared metric registry, with a
  two-direction test between registry and output.
- A release-quality UX pass: packaged Agent Skill, safe installer, clarified
  proof scope, and true best basin representatives.
- `compare` and `compare-dumps` report the LCS-aligned residual beside the
  positional one, and ranking sorts on `aligned_total` first.
- Documentation refocused on decompilation problems, command outputs, and
  support boundaries.
- Project-specific research narratives replaced with concise workflows,
  operating principles, and a documentation index.

### Fixed

- A missing-symbol error no longer blames the build for a typo: an unfiltered
  second objdump pass supplies the real "defines:" list.
- `allocation-mismatch` no longer guesses a lever family: it names all three
  unresolved families with the `guide` command for each and picks none.
- Four terminal rendering defects: family-coloured verdicts, `--color` on
  `compare`/`rank`, wrapped annotations, and `slot=/aligned_row=` labels.
- Adjacent instruction swaps are no longer misclassified when unrelated
  relocation addends differ; the view uses relocation-masked identities.
- An unsafe claim corrected across guidance: a region collapsing under `-g0`
  does not prove source correctness (the `vsprintf` counterexample).
- `CDX_FORCE` no longer aborts on a forbidden color: the pass declines,
  records `force_declined`, and `trace-globalcolor` reports `forbidden_colors`.
- The commutative-operand rule is deduplicated: `compare` and `view` classify
  through one `compare.commutative_swap` predicate.
- Stopping on an exact match records candidates already in flight, and an
  unexpected candidate error is recorded rather than ending the run.
- The instrumented pass validates the workbench's force-key grammar, refusing
  a partially formed control instead of silently forcing nothing.
- `--show-diff` reports every differing site regardless of verdict, not only
  register groups.
- Register diagnostics are portable across GNU objdump dialects with or
  without the `$` register prefix.
- Unreachable zero alignment padding after a selected MIPS function's return
  delay slot is excluded from comparisons.

## 0.2.0 - 2026-07-27

### Added

- Redistributable objdump-text fixtures and symbol filtering.
- Parallel, cached campaigns with explicit provenance and JSONL ledgers.
- Structured ugen trace parsing, FIFO validation, and logical-value
  reconstruction.
- `CSAVE`/`CUP`/`[CDX]` globalcolor reporting.
- Hash-pinned, anchor-validated uopt globalcolor and alias profiles, with safe
  profile composition and alias-state reports.
- Retained ugen-to-as1 listing replay.
- Task-oriented guides, CC0 licensing, and clean-wheel validation.
- The workbench published as a standalone repository with end-to-end
  workflows, centralized troubleshooting, and root-level CI.
- Python 3.10-3.14 CI, strict type checks, formatter enforcement, and
  release-distribution smoke tests.
- A reproducible instrumentation fidelity microcase and release validation
  record.

### Changed

- Exact comparison is relocation-aware and conservative about missing or
  unknown relocation kinds.

### Fixed

- List-address filtering in FIFO replay, and acceptance of non-finite
  globalcolor costs emitted by compiler diagnostics.
- The phase-two globalcolor web identifier used by decision logs and force
  controls; force controls must select one procedure.

## 0.1.0 - 2026-07-26

### Added

- Initial object comparison, ranking, sequential candidate compilation, and
  generic ugen instrumentation package.
