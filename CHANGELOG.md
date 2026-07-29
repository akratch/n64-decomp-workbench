# Changelog

## Unreleased

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
