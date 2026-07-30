# Changelog

## Unreleased

- Main now identifies itself as `0.3.0.dev0` instead of reusing the published
  `0.2.0` identity for a substantially different development build.

- Completed the common diagnosis journey. `diagnose`/`diagnose-dumps` render
  exact comparison truth plus the decisive aligned mechanism evidence after
  loading each input once; `check-scratch --view` reuses the imported
  comparison. Terminal width/pager controls and self-contained accessible HTML
  reports preserve the same evidence, and every explicit output refuses to
  overwrite.

- Added a durable campaign cockpit. Runs create an identity-checked manifest
  and append-only ledger under `.decomp-workbench/` by default; `campaign
  status/note/resume/export` preserve the best trajectory, failures, active
  hypothesis, object basins, family collapse, and exact-stop state.
  `decomp-workbench-experiment-v1` sidecars validate deterministic parameter
  assignments and selected instruction regions. Cache status, dry-run prune,
  recoverable cross-filesystem trash, and collision-safe restore complete the
  state lifecycle.

- Added calibrated compiler-research adapters without redistributing compiler
  inputs: real-copy `toolchain init/calibrate/status`, section/relocation/symbol
  fidelity, scheduler `DKWB-SCHED-V1` records and hash-pinned external
  profiles, original/static pass differential, behavioral fingerprint
  microcases, cross-revision lineage, relocation-alias evidence, mandatory
  unedited replay calibration, project-visible work roots, and bounded process
  artifacts.

- Productized the allocator oracle. `oracle plan` always reports both p1/p2
  namespaces and plans only measured or explicit non-forbidden colors;
  `diff` aligns semantic web provenance rather than numeric IDs; `force/sweep`
  use the campaign engine and require an intact ready toolchain; `status/export`
  reopen persistent, ledger-idempotent evidence. Forced exactness remains
  explicitly causal evidence, never a source match.

- Added semantic allocator and source provenance views: stable web
  fingerprints, forbidden-color neighbor attribution, virtual/final stack-home
  ownership, and `trace-source` joins through retained preprocessor markers and
  `.file/.loc` directives while preserving ambiguous line matches. Runnable
  synthetic oracle, source/listing, scheduler, and complete experiment-grid
  examples are executed by documentation tests.

- Hardened the evidence boundary found during final review: selected-region
  scores now use LCS-aligned residual sites; allocator details and interference
  edges are phase-qualified; an exact forced build is causal only after a
  successful non-exact control; relocation aliases preserve kind and
  cardinality differences; short section tails and undecodable compiler bytes
  remain observable; and toolchain/cache operations preflight collisions
  without deleting or partially restoring another process's files.

- Standardized automation on one versioned JSON document for success and
  failure, including argparse errors; added a compact journey command map,
  non-breaking task-group aliases, and generated Bash/Zsh/Fish/PowerShell
  completions. CI now runs actionlint, the full suite on macOS, targeted
  Windows process/filesystem contracts, and wheel/sdist installation smoke
  tests in addition to Python 3.10–3.14 and strict static analysis.

- Compiler execution now has one lifecycle contract across `check-scratch`,
  `compile-rank`, and `campaign`: a 120-second per-candidate timeout by
  default, explicit environment and working-directory controls, and
  process-group cleanup so a wrapper's assembler or search child cannot
  outlive a timeout. Campaign ledgers and JSON summaries record the deadline;
  site-faithful scratch reports also record wrapper identity, cwd, explicit
  environment, duration, and timeout.

- Hardened scratch handoffs. ZIP members must come from one flat root instead
  of being silently combined by basename, expanded directories refuse nested
  or symbolic-link content instead of ignoring it, checksums must be real
  hexadecimal SHA-256 values, and impossible browser scores are rejected
  rather than rendered above 100% or below 0%.

- Standardized examples and campaign state on repository-root commands and
  `.decomp-workbench/`, taught `doctor --cache-dir` to inspect a project's
  actual cache, schema-versioned the doctor and scratch-check JSON reports,
  and expanded documentation tests to execute redistributable trace examples.

- Added `doctor` and `check-scratch` for the human handoff around decomp.me.
  `doctor` reports local readiness, validates an export or workbench bundle,
  and prints the exact shell-quoted next command. `check-scratch` safely reads
  a downloaded ZIP/directory without extraction, shows the browser score only
  as context, and compares the exported target/current objects (or retained
  objdump text) with the workbench's aligned oracle. Its optional compile mode
  reproduces the site's `ctx.c` + `#line 1 "src.c"` + candidate composition,
  supports explicit environment/cwd/timeout controls, and can retain the exact
  composed source and object for audit.

- `--objdump PATH` is now authoritative. A misspelled explicit path fails
  immediately instead of silently selecting a different host executable.
  `doctor` also verifies the selected reader against an exported `target.o`
  when available and reports large local campaign caches without modifying
  them.

- Fixed adjacent instruction swaps being misclassified as allocation or
  structure when unrelated relocation addends differed elsewhere. The shared
  aligned view now uses relocation-masked schedule identities, so the
  redistributable final-two-`li` fixture reports `aligned_schedule=2` and sends
  the user to the scheduling evidence ladder.

- Corrected an unsafe claim in runtime guidance, tutorials, postmortem, field
  notes, and the packaged Agent Skill: a region collapsing under `-g0` proves
  debug metadata participates and as1 can reach the target order, but does not
  prove source correctness. The eventual `vsprintf` match was the
  counterexample—a freer scheduler had rescued the wrong source topology.

- `CDX_FORCE` no longer kills the compiler when it names a color the web's
  interference mask already forbids. The instrumented pass **declines** the
  force, records
  `[CDX] force_declined phase=p2 site=dec proc=11 web=300 color=2 reg=v1 forbidden=0x…`,
  and lets the natural coloring stand. Six oracle probes across three campaigns
  could not be run at all because that case raised `SIGABRT`, and a sweep that
  hit one lost every result after it.

  The record prints whether or not `CDX_LOG` is set, and that is the semantic
  change worth knowing: a declined force is now *visible* and distinguishable
  from a force the pass never saw, so "the object did not change" no longer has
  two meanings. `site=dec` and `site=color` name which of the two force points
  declined. Forcing the split path (`p1:w9=s`) is never declined — no color
  mask can forbid it.

  The mask decode is now one rule in two places: `color_is_forbidden` in
  `globalcolor.py` and the generated C, checked against one table in the tests,
  anchored on the recorded observation that `forbidden0=0x7f800000` means
  exactly c1–c8. `trace-globalcolor` reports `forbidden_colors` on every
  allocator web, so a force sweep can be planned from one logging run instead
  of discovered one abort at a time.

- New `--census KEY=VALUE[,KEY=VALUE...]` on `compare`, `compare-dumps`,
  `view`, and `view-dumps`: assert values the command already reports and read
  the answer as an exit code — `0` when every predicate held, `3` when one
  failed, `2` when the question itself was wrong. One `PASS`/`FAIL` line prints
  per predicate, `--json` carries them under `census`, and the option is
  repeatable.

  Campaign agents rebuilt this filter at least seven times in one day as an
  objdump-and-regular-expression layer outside the workbench, and at least one
  of those copies keyed on the wrong instruction. `3` is deliberately not `1`:
  `--fail-on-mismatch` already means "this candidate is not a match", and a
  variant can be exactly the shape you are filtering for and still not be the
  match.

  Any key the command reports can be named, including the deprecated JSON
  spellings while they are still emitted; keys whose value is a list or an
  object are refused rather than silently compared; values compare by the
  reported type, so `exact=true` reads a boolean and `frame=-0x80` reads an
  integer in any base. Predicates are validated against the registry before the
  inputs are read, so a misspelled key in a long sweep costs one process rather
  than one compile. `--explain-keys` gained a fourth section for the keys a
  command wraps around a report (`accepted`, `acceptance_basis`, and the census
  results), which had never been explained anywhere.

- `compare` and `compare-dumps` now report the LCS-aligned residual beside the
  positional one, and **candidate ranking moved to it**. `aligned_total` leads
  the summary line; `aligned_structural`, `aligned_schedule`,
  `aligned_register`, `aligned_constant`, and `aligned_commutative` split it by
  mechanism in `--json`, in `campaign --json-summary`, and on a human line
  under the verdict. `rank`, `compile-rank`, `campaign`, and the object-basin
  order sort on `aligned_total` first, with the positional `words=` count as
  the tiebreaker.

  This was the most expensive tool gap of the dp64 campaign day: positional
  counting shifts on every insertion, so the candidate one edit away reads as
  a cascade while a candidate with a dozen unrelated allocation differences
  reads as close. It misranked candidates in six separate campaigns — a
  one-hunk 11-word variant sorted below a five-site 5-word variant, and two
  variants tied at 95 words that the aligned split (10 structural versus 8)
  separated immediately. The shipped insertion fixture reproduces it in
  miniature: `words=11`, `aligned_total=1`.

  The counts come from `view`'s alignment, not from a second aligner in
  `compare`: campaigns rebuilt an ad-hoc LCS ranker six times in one day, and
  two implementations of one idea would eventually print different numbers
  under the same name in two commands. `words=` is unchanged and still the
  matching oracle — a match is `exact=true` with `words=0`, and aligned rows
  that are relocation-controlled or displaced by an insertion are outside the
  residual by design, because neither is a difference a source change owns.

- Wrote the documentation for the person who arrives with one almost-matched
  function and no idea what the next command is. Three new narrative pages sit
  above the reference material and are the first thing the README points at:

  - `docs/START_HERE.md` — ten minutes, in order: run `compare`, read the
    verdict, run `view`, read the lanes and hunks, take the lever from the
    `next:` footer, change one thing, repeat. Every command in it runs against
    the shipped fixtures with no ROM, compiler, or toolchain, so a reader can
    follow the whole loop before touching their own project. It answers the
    three questions people actually arrive with, where they arise: you do not
    isolate the function (`compare` and `view` are symbol-scoped against your
    normal full-TU build, and isolation changes codegen); you do not need an
    agent or a permuter (the verdict names the mechanism and the footer names
    the lever — the permuter is a hypothesis generator, not a solver); and
    traces are the last resort for one verdict class, not the first step.
  - `docs/field-guide.md` — the IDO codegen levers as a playbook. Nineteen
    entries, each with the diff signature that points to it, the C before and
    after, why it works, the function it was proven on with the measured
    effect, and the verdict or playbook name that routes here. Plus the dead
    families, which are worth as much as the levers: `a|b` versus `b|a`,
    declaration-order permutation, bare discarded expressions, and the
    permuter on varargs.
  - `docs/walkthrough-30-near-matches.md` — batch triage for a backlog rather
    than a function: classify the whole pile with `compare --json` and
    `view --json`, rank by verdict class rather than word count, clear the
    one-variant classes first, then structure, then the register lanes, with
    portable POSIX shell for each step.

  The docs index is now a journey rather than an alphabet, every entry carries
  a "read this if...", and the compiler-internals pages are explicitly marked
  as the last resort they are. `tests/test_doc_commands.py` extracts every
  documented command line that reads a shipped fixture, runs it, and checks it
  against the output the page promises — so a command line that stops working,
  or a verdict that changes wording, fails the build instead of misleading a
  reader.

- Gave `view` and `view-dumps` the same option behavior as every other command
  that selects one function: `--symbol`/`--function` conflicts are rejected
  instead of resolved last-one-wins, and `--explain-keys` prints the registry.
  Both options now come from one shared module rather than a copy per command
  module. `view` and `view-dumps` also moved next to `compare` and
  `compare-dumps` in the help listing, where the inputs they read put them.

- Unified the two schema registries the merge left behind. The aligned view's
  keys now live in the shared metric registry beside the comparison and
  campaign keys, so `--explain-keys` explains `view` and `view-dumps` too, and
  a test asserts the registry and the view's output are one set in both
  directions: a key can neither be printed without an explanation nor
  explained without being printed. The view keeps its own namespace, because a
  spelling it shares with the comparison registry (`target_instructions`) is an
  aligned count there and a positional count here.

- Deduplicated the commutative-operand rule: `compare` and `view` shared two
  independent tables and two independent predicates that disagreed about the
  two-operand multiply form, so one residual could be `commutative-order` in
  one command and `register` in the other. Both now classify through
  `compare.commutative_swap`, and a table-driven test asserts the two commands
  name the same mechanism for a three-operand `or`, a two-operand `mult`, and
  the non-commutative controls.

- Kept every candidate a campaign actually ran: stopping on an exact match now
  waits for and records the candidates already in flight instead of discarding
  their objects and their ledger records, and a candidate that raises an
  unexpected error is recorded as a failed candidate rather than ending the
  run.
- Required a matching instruction multiset for `schedule-mismatch`, so a
  reordering that also moves a register is no longer reported as "not
  allocation".
- Escalated compiler termination from `SIGTERM` to `SIGKILL`, kept compilers in
  the workbench's session on Python 3.11+ (own process group, still attached to
  the terminal), and scoped the group-termination guarantee to POSIX in the
  documentation; Windows remains best effort.
- Gave the instrumented pass the same force-key grammar the workbench
  validates, so a partially formed control such as `p1:w9` or `p1:w9=zzz` is
  refused instead of silently forcing nothing.

- Established the packaged bundle under `src/decomp_workbench/skills` as the
  only skill tree, with a test that fails if a root-level `skills/` directory
  exists without matching what `install-skill` ships.
- Made the globalcolor instrumentation phase-explicit and self-describing:
  records carry `phase=p1`/`phase=p2`, `CDX_FORCE` keys must be phase-qualified
  (`p2:w55=c2`) and are rejected with both namespaces named — by `campaign
  --env` before a compile and by the pass itself — colors are decoded to
  machine registers in every record and in `trace-globalcolor`, and a
  symbol-named `CDX_PROC` now prints a procedure index table instead of
  silently selecting procedure 0.
- Documented the instrumentation fidelity gates as section-scoped
  (`.text`/`.rodata`/`.data`/relocations/symbols), because stock IDO under
  `-g3` is not file-level reproducible.
- Gave the campaign runner ownership of the processes it starts: compilers run
  in their own process group and are terminated with their children when a run
  fails or is interrupted, so a spawned search or assembler cannot outlive its
  campaign.
- Stopped campaigns on the first exact match by default (`--no-stop-on-exact`
  sweeps the whole grid) and removed the repeated target disassembly, so a
  variant costs one compiler run and one objdump run with the comparison in
  process.
- Split three verdicts out of the volume-based classes, each with the field
  lever attached: `constant-mismatch` (audit the flag/enum against the
  assembly), `commutative-order` (compound assignment, not the allocator), and
  `schedule-mismatch` (statement grouping and the `-g0` diagnostic).
- Unified human labels and JSON keys behind one metric registry and added
  `--explain-keys`. `words=` is now `"words"` in JSON; the previous long-form
  keys (`word_mismatches`, `candidate_instructions`, `candidate_frame_size`,
  and the rest) are deprecated and still emitted beside the canonical keys for
  one release.
- Reported every differing site regardless of verdict. `--show-diff` no longer
  prints only register groups, so a literal difference counted in `raw` can no
  longer be missing from the displayed evidence.
- Accepted `--function` as a second spelling of `--symbol` on every command
  that selects one function, and rejected conflicting values instead of
  silently keeping the last one.

- Added `view` and `view-dumps`: the aligned mechanism view. Two-pass LCS
  alignment over the opcode streams, per-hunk classification
  (structural/schedule/register/constant/commutative/relocation), per-class
  register lanes that include the matching instructions, a
  `prefix-exact@N` / `state-divergence@class:slot` signature line, grouped
  register webs, and lever guidance chosen by the dominant class. Aligned
  counts replace positional counts, which multiply a single insertion into a
  phantom cascade. Two anchorings are scored against each other so neither a
  run of repeated opcodes nor repeated instruction text can mispair the
  streams, a shifted branch offset is reported as `displacement` rather than
  claimed as byte identity, and `phase-shift` requires a real rotation cycle
  instead of the constant offset that any small register swap satisfies. Both
  commands accept reduced objdump text, `--json` uses the same keys as the
  human labels, and `--report-regs` emits per-aligned-row register operands for
  matching rows too.
- Completed a release-quality UX pass: packaged the Agent Skill with the
  distribution, added a safe installer, clarified comparison proof scope and
  cross-ROM JSON acceptance, hardened focused web lookups, and selected the
  true best representative for every campaign basin.
- Added the portable `n64-decomp-campaign` Agent Skill for Codex and Claude
  Code, including installation guidance and reusable DKR/SF64 campaign
  evidence, IDO patterns, and reproducibility practice.
- Added action-oriented comparison verdicts, relocation-only raw-difference
  explanations, and a deliberately separate cross-ROM structural-evidence
  mode.
- Made register diagnostics portable across GNU objdump dialects that do or do
  not print MIPS register names with a `$` prefix.
- Added object-basin reporting to campaigns, so source variants that compile
  to the same function bytes are visible in both terminal and JSON summaries.
- Added focused `trace-globalcolor --proc ... --web ...` inspection with
  trustworthy callee-saved register names for the pinned compiler profile.
- Published a final-function campaign guide covering the Hartley, Titania, and
  Aquas evidence patterns and the safe next action for each residual class.
- Refocused the documentation on decompilation problems, command outputs, and
  support boundaries.
- Replaced project-specific research narratives with concise workflows,
  operating principles, and a documentation index.
- Excluded unreachable zero alignment padding after a selected MIPS function's
  return delay slot from object and retained-dump comparisons.
- Added deterministic, upload-neutral decomp.me scratch bundles with copied
  target/context/source inputs, settings, checksums, and manual-use guidance.
- Added a five-function Castlevania 64 walkthrough and complete scratch inputs,
  including exact matches and three small scheduling/code-generation puzzles.
- Documented the supported IDO 5.3 and 7.1 workflow matrix and the narrower
  version boundary of the pinned deep-uopt instrumentation profiles.

## 0.2.0 — 2026-07-27

- Made exact comparison relocation-aware and conservative about missing or
  unknown relocation kinds.
- Added redistributable objdump-text fixtures and symbol filtering.
- Added parallel, cached campaigns with explicit provenance and JSONL ledgers.
- Added structured ugen trace parsing, FIFO validation, and logical-value
  reconstruction.
- Added `CSAVE`/`CUP`/`[CDX]` globalcolor reporting.
- Added hash-pinned, anchor-validated uopt globalcolor and alias profiles,
  including safe profile composition and alias-state reports.
- Added retained ugen→as1 listing replay.
- Added task-oriented guides, CC0 licensing, and clean-wheel validation.
- Published the workbench as a standalone repository with end-to-end developer
  workflows, centralized troubleshooting, and root-level CI.
- Added Python 3.10–3.14 CI, strict type checks, formatter enforcement, and
  release-distribution smoke tests.
- Fixed list-address filtering in FIFO replay and accepted non-finite
  globalcolor costs emitted by compiler diagnostics.
- Corrected the phase-two globalcolor web identifier used by decision logs and
  force controls, and required force controls to select one procedure.
- Added a reproducible instrumentation fidelity microcase and release
  validation record.

## 0.1.0 — 2026-07-26

- Initial object comparison, ranking, sequential candidate compilation, and
  generic ugen instrumentation package.
