# Changelog

## Unreleased

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
