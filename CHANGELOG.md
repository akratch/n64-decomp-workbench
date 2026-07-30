# Changelog

## 0.3.1 - 2026-07-30

- The bundled `n64-decomp-campaign` Agent Skill caught up with the tool it
  ships in: it now routes agents through the guided next-steps footer and the
  `guide` command instead of past them, mandates a known-match harness proof
  before any target comparison, adds the frontend-lineage escape hatch (a new
  `references/frontend-lineage.md`: impossibility-first discipline, the
  fingerprint-atlas method, dispatch-construct discrimination, and what
  alternate-frontend evidence does and does not establish), counterweights the
  spelling experiments with the field guide's dead-families table and the
  line-placement lever, extends the evidence ladder with the two
  frontend-provenance rungs, and names the lever-19 clean negative as a
  legitimate terminal result.

- The README shows the product: an ANSI-faithful SVG of a real fixture
  diagnosis under the tagline and a screenshot of the self-contained HTML
  report at the `--html` mention, both generated from shipped fixtures.

## 0.3.0 — 2026-07-30

Every verdict now ends in an address: the matching field-guide levers, the
command that prints them, and both answers to "do you have an instrumented
toolchain?". Around that, three more themes — input safety, so a comparison
never reports a confident verdict about two unrelated functions; visualization
parity, so an exported report and a bounded terminal carry the same evidence as
a full screen; and the documentation that joins a screen to a source edit.

- Added `decomp-workbench guide <topic>`. It prints the field guide's own
  sections for a playbook (`forced-color-oracle`), either verdict vocabulary
  (`register-permutation`, `allocation-mismatch`), or a lever number (`19`),
  from a copy that ships inside the package — no checkout and no network. Every
  `next:` footer now names the matching levers with a one-line action each and
  the command that expands them, and any playbook whose advice mentions a
  trace, a probe, or an oracle gives both answers to "do you have an
  instrumented toolchain?", so the reader without one is told which source
  levers to spend instead.

- Added [From verdict to edit](docs/from-verdict-to-edit.md), the walkthrough
  from a diagnosis on screen to the source change it implies, and a glossary of
  the field's vocabulary in the documentation index.

- Symbol selection now falls back to a unique case-insensitive match, at the
  parser and in `dump_object`'s objdump retry: Pascal-era frontends (`upas`)
  fold identifiers to lower case, and comparing those objects previously
  required an `objcopy --redefine-sym` round-trip. That retry and the
  missing-symbol evidence pass below are one objdump call, not two.

- New documentation from the SSB64 frontend-lineage campaign: alternate
  authentic frontends (`docs/alternate-frontends.md` — accom/ccom/upas
  inventory, invocation recipes, cross-generation ucode handoff, and the
  fingerprint-atlas method), field-guide levers 20-22 with two new dead
  families, and field notes (`docs/field-notes-2026-07-30-ssb64.md`)
  including an open comparator report: exact matches occasionally render a
  vestigial `aligned_schedule` residual.

- Fixed a missing-symbol error that blamed the build instead of the typo.
  `objdump --disassemble=NAME` that matches nothing succeeds and prints an
  empty stream, so the "defines:" list built from it announced `no symbols`
  about an object that plainly defines the function the reader misspelled — on
  real `.o` files, the primary path. A single unfiltered second pass now
  supplies that list.

- Stopped a coarse verdict from guessing a lever family. `allocation-mismatch`
  dumped `pool-position`'s seven levers even though the same two streams make
  `view` say `phase-shift` or `register-permutation`, whose levers are 14-16
  and 17-19 — a guess that contradicted the sentence above it telling the
  reader to run `view` because *it* names the family, and that leaked into
  `--json` and the HTML payload beside a `view.next` that disagreed. The
  verdict now names all three families with the `guide` command for each and
  picks none, led by the sentence saying why it cannot.

- `--width` no longer truncates the `next:` footer. Guidance wraps on word
  boundaries with an indented continuation, so a bounded terminal keeps the
  dead-family warnings instead of the setup sentence that preceded them.

- Added four one-line explanations where the vocabulary is first used: what a
  web is, what LCS buys, what the `pool` and `temp` lane classes are, and how
  to read the signature in causal order — plus a pointer to
  `--explain-keys`. The three in-tool notes are removable with `--terse`.
  `--html` now renders each lever as its own runnable
  `decomp-workbench guide N` snippet.

- Made the HTML report carry the evidence it claimed to. It is rebuilt from
  the same view model the terminal renderer consumes: a sticky verdict bar,
  register lanes with the divergent slot outlined, one linkable
  `<section id="hunk-N">` per hunk with context and divergence row classes, a
  per-row substitution cell whose colour swatch links to its web, and a `Webs`
  table linking each bijection to every hunk it explains. Lanes, hunk grouping,
  webs, and the `t7->t8 [w1]` annotations previously existed only inside the
  collapsed JSON blob, which is still there. Still one self-contained file with
  no script and no network.

- Fixed four comprehension defects in the terminal rendering. The verdict is
  bolded and coloured by family (green for exact, one hue per mismatch family)
  instead of being the only plain token beside a bold-red explanatory sentence,
  and `compare`/`compare-dumps`/`rank` gained the `--color` they never had, so
  batch triage can be colourized. `--width` now wraps a row's annotation to a
  continuation line instead of silently cutting a second web tag. Every
  non-matching row is annotated, in or out of the hunk being printed, so a
  context row in a known web no longer reads as an unexplained `register` site.
  The lane caret names its two units: `slot=5 aligned_row=12`, replacing
  `divergence=5 index=12` on screen **and in `--json`**, because one vocabulary
  across both audiences is the point of the metric registry.

- Added the highest-leverage fact to the header. A compact
  `webs: w1 t7->t8 x2, ...` line prints above the hunks, and the substituted
  register token inside the disassembly now takes its web's colour, so the
  annotation says *which* registers moved and the text says where.

- An unknown command now names itself and points at `decomp-workbench
  commands` instead of printing argparse's forty-odd-name `(choose from ...)`
  catalogue.

- Refused to report a confident verdict about two unrelated functions.
  With no `--function` and exactly one differently-named symbol on each side,
  `compare`, `view`, `diagnose`, and `rank` now print a warning ahead of the
  verdict, carry it in `--json`, and say which option fixes it. A multi-symbol
  input is still the documented whole-section mode and stays quiet.

- Made the novice path legible. The bare program name welcomes and exits `0`
  instead of printing a 44-command choice wall and exiting `2`; the usage line
  is one word plus a pointer to `commands`; the `commands` footer teaches the
  same flat spelling as README and START_HERE; `--symbol`/`--function` says
  what omitting it means; `docs/README.md` defines IDO, asm-processor,
  ugen/uopt, and decomp.me, which are also glossed at first use.

- Sharpened two error messages to the standard the census-key error sets.
  A missing symbol lists what each input actually defines, states that names
  are case-sensitive, and links the troubleshooting section; an objdump
  `file format not recognized` failure names the likely cause before quoting
  objdump's own words underneath.

- Put the trace back where the documentation always had it.
  `allocation-mismatch` now sends the reader to `view`/`diagnose` and the
  field-guide levers first, and gates the globalcolor/UGEN trace on those
  levers being exhausted *and* an instrumented toolchain already existing. The
  `pool-position` and `temp-fifo-phase` footers lead with their source-only
  branch for the same reason, and `pool-position` now says up front that it is
  one of three unresolved allocation families rather than implying a decision
  the verdict did not make.

- Gave every verdict an on-ramp. The `next:` footer of `compare`, `view`, and
  `diagnose` now keeps its expert content and adds the matching field-guide
  lever numbers with a one-line action each, the literal
  `decomp-workbench guide <playbook>` that prints them, and — for every
  playbook whose advice names a trace, a probe, or an oracle — both answers to
  "do you have an instrumented toolchain?", so the reader without one is told
  which source levers to spend instead. The new `guide` command accepts a
  playbook, either verdict vocabulary, or a lever number, and prints the field
  guide from inside the installed package with no checkout. A lever whose
  section is not in the shipped revision degrades to its one-line action rather
  than failing, and a missing document still answers with the one-liners and
  names where the full text lives.

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
