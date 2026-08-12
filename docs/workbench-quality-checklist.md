# Workbench quality checklist

This is the release-facing acceptance checklist for the whole product. It is
organized by user job, not module. A checked item is implemented and covered
locally; an unchecked item needs external infrastructure or new measured
evidence and must not be implied by the UI.

## 1. Arrive, install, and orient

- [x] Python 3.10–3.14 package builds as wheel and source distribution.
- [x] The package has no native runtime dependency; Python 3.10 uses `tomli`
  for the same TOML parser included in newer Python.
- [x] An empty invocation gives a short welcome, not a wall of argparse names.
- [x] `commands` presents one task-oriented map; every bare group succeeds and
  prints its own operations.
- [x] Grouped and compatible flat spellings are validated against the live
  parser and generated completions.
- [x] `doctor` separates retained-dump readiness, object-tool readiness,
  optional scratch validation, compiler preflight, cache health, and calibrated
  toolchain status.
- [x] Objdump auto-discovery executes an auditable synthetic MIPS ELF probe and
  verifies symbol filtering, GNU instruction syntax, and relocation parsing.
- [x] `project init` discovers objdiff/Splat/build metadata without selecting an
  ambiguous unit, previews TOML, writes only with `--write`, and never
  overwrites.
- [x] Project paths resolve relative to the config and parent-directory lookup
  supports work from nested source directories.
- [x] `project campaign` consumes, rather than merely displays, the configured
  compile argv/cwd, sealed environment, compiler/frontend/backend lineage,
  target scope, cache/state roots, and source-retention policy.

## 2. Diagnose one function without being misled

- [x] Target and candidate are disassembled once and warnings appear before any
  verdict a user might trust.
- [x] Exactness, raw words, relocation-controlled fields, structure, scheduling,
  allocation, constants, commutative order, frame, and instruction count remain
  separate facts.
- [x] A cross-function symbol mismatch is a visible input warning.
- [x] Alignment explains insertions and movement without turning shifted rows
  into cascaded noise.
- [x] `aligned_total` ranks only a fully gap-free candidate set; any gap makes
  ranking fall back to positional words with explicit human and JSON state.
- [x] `next` emits a concrete argv, safety posture, and expected evidence—no
  `SRC.c`, `TRACE.log`, or guessed-row placeholders.
- [x] Dump inputs lead only to dump-capable follow-up commands.
- [x] HTML and terminal views carry the same verdict, lanes, hunks, webs,
  warnings, and machine-readable evidence.
- [x] The field guide maps each verdict/playbook to measured source levers and
  records families that failed.

## 3. Reconcile decomp.me, scratch, and project truth

- [x] ZIP/directory imports validate checksums and compose context, language
  reset, and source without uploading anything.
- [x] Site metadata, downloaded scratch-object truth, optional site-faithful
  rebuild, and full-project object truth render as independent layers.
- [x] Linked-function exactness cannot masquerade as a 100% site score;
  raw instruction words and relocation targets have an explicit score proxy.
- [x] `context lint` audits undefined-preprocessor-identifier collapse.
- [x] `context duplicates` reports simple file-scope definitions repeated
  across context/code fragments, with honest parser limitations.
- [x] Match override guidance is conditional on preserved local evidence; an
  override is never represented as compiler proof.
- [x] Scratch bundles are deterministic, checksummed, exclusive-output
  handoffs.

## 4. Run a reproducible candidate campaign

- [x] Compiler commands are argv, never shell evaluation, with explicit cwd and
  process-tree timeout cleanup.
- [x] Compiler processes receive a sealed environment; `--env` and
  `--inherit-env` are recorded identity inputs.
- [x] Target, source, wrapper, executable, objdump, cwd, environment, toolchain,
  and compiler lineage participate in cache/resume identity.
- [x] IRIX 4 `accom`/`ccom`, later `cfe`, driver, language, and hybrid backend
  are distinct experiment cells.
- [x] Required absolute/differential controls run before candidates and fail
  closed when a wrapper ignores the tested input.
- [x] Signals are function/row scoped and do not redefine exactness.
- [x] Coverage says exhaustive, sampled, interrupted, control-invalid, or
  unknown over the declared space.
- [x] The append-only ledger records failures, trajectories, signals, hashes,
  and object basins; status and resume do not require re-derivation.
- [x] Candidate source is staged content-addressably and retained by an explicit
  `leaders`, `exact`, `all`, or `none` policy.
- [x] Mutating commands refuse to guess when several campaign manifests exist.
- [x] Cache status uses human and exact byte sizes; prune combines age, size,
  and keep-recent policies, is a dry-run by default, and moves entries to
  recoverable trash preserving nested paths.

## 5. Finish, clean up, and publish a result

- [x] Promotion selects an immutable ledger record and rechecks source/object
  hashes.
- [x] `campaign finish` freshly rebuilds the winner and records function,
  signal, scratch, collateral, handoff, and project gates independently as
  PASS/FAIL/UNKNOWN/NOT RUN.
- [x] Packaging can require a passing finish receipt and can use a retained
  source after the original candidate directory is gone.
- [x] Source inspection marks every suspicious construct as unsafe for
  automatic removal and asks the semantic question a reviewer must answer.
- [x] Cleanup composition is bounded, exact-text, hash-aware, dry-runnable, and
  coverage-qualified.
- [x] Mutation review prints the diff and flags the two measured invalid-edit
  shapes without claiming a clean textual scan proves semantic equivalence.
- [x] Naturalness is a human source-quality preference among candidates that
  still pass raw-word, relocation, frame, full-object collateral, and project
  verification gates—not another inferred score.
- [x] Handoff audit finds missing, absolute/local-only, and untracked
  publication dependencies.

## 6. Work with agents and automation safely

- [x] Every JSON-capable invocation yields one versioned success document or
  one common structured error document.
- [x] Exit codes distinguish success, gate/no-result, usage/capability/process,
  and census failure.
- [x] `commands --json` describes argv, report schema, default mutation posture,
  external-process use, and network/destructive behavior.
- [x] `next --json` gives executable argv and the expected signal; an agent need
  not scrape prose or execute a shell-rendered string.
- [x] Compiler stdout/stderr previews are bounded and full streams require an
  explicit artifact directory.
- [x] The bundled Codex/Claude Agent Skill uses the same evidence hierarchy,
  frontend cells, controls, source retention, cleanup gates, and final oracle.
- [x] Shared notes use cross-process locking and collision-safe ID reservation.
- [x] The workbench performs no network upload and reports `network=false` in
  command discovery.

## 7. Make every report usable

- [x] Human output leads with acceptance/verdict and puts cautions before
  metrics.
- [x] JSON retains full evidence while compact summaries omit unbounded streams.
- [x] HTML exports are self-contained, script-free, and network-free.
- [x] All HTML report families share a skip link, landmark, visible keyboard
  focus, theme metadata, captions, scrollable tables, tabular numbers,
  decorative-element hiding, expanded evidence by default, and print-safe
  details.
- [x] Report creation is exclusive; a rerun cannot overwrite a handoff silently.
- [x] Terminal color has a non-color text equivalent and automation never
  depends on ANSI output.
- [x] Four shell completion formats are generated from the live command
  surface.

## 8. Keep documentation and product claims honest

- [x] README leads to a short guided path and keeps deep internals below the
  everyday workflow.
- [x] The docs index routes by user question and separates start, command
  reference, reasoning, compiler internals, and dated history.
- [x] Product status names implemented journeys and intentional boundaries.
- [x] Troubleshooting distinguishes object reader, scratch assembly, context,
  compiler, and instrumentation failures.
- [x] IRIX 4 frontend support and 5.3/7.1 backend/instrumentation limits have a
  visible matrix.
- [x] Ranking guidance is consistent about gap-free aligned ranking,
  positional fallback, and the explicit temp-prefix exception.
- [x] Release notes state behavior changes and migrations; development versions
  cannot be published by the release workflow.

## 9. Portability and release gates

- [x] Platform-specific file locking imports only on its host OS.
- [x] Paths use `pathlib`, compiler invocation avoids a shell, and project TOML
  arrays avoid platform-specific quoting.
- [x] The full test suite runs on Linux and macOS, with Python 3.10–3.14 on
  Linux. Windows runs native process/filesystem contracts, a complete
  scratch-to-package campaign, and fixture-backed CLI smoke tests; Unix-only
  synthetic shebang executables are not mislabeled as Windows tests.
- [x] Static gates cover Ruff, formatting, strict mypy, codespell, Bandit,
  actionlint, wheel contents, wheel/sdist smoke tests, documentation links,
  parseable shell snippets, and the complete asset-free endgame example.
- [x] A tag-only release workflow verifies tag/version agreement, refuses
  `.dev` versions, builds once, checks artifacts, and uses PyPI trusted
  publishing through a protected environment, with automatic PEP 740 publish
  attestations.
- [x] All intended files are included in the `0.5.0` release commit and
  `handoff audit . --fail-on-warning` passes against that publication set.
- [ ] Observe the updated Windows-native and full macOS jobs green in hosted
  CI for the release commit; local tests cannot certify those runners.
- [x] The repository's protected `pypi` environment requires owner review and
  accepts only `v*` tag deployments.
- [ ] Register the pending PyPI trusted publisher before creating `v0.5.0`;
  the project name is not yet present on PyPI, so this requires the owner's
  authenticated PyPI account rather than repository code.
- [x] Uncleared CV64 scratch payloads are absent from the repository and both
  distributions; only aggregate code-free measurements, attribution, and a
  local regeneration recipe remain.
- [ ] Install the actually published artifact in a new environment and rerun
  the smoke journey; a locally built wheel is not that final gate.

## Explicit non-goals until evidence earns them

- [ ] No automatic C “naturalizer” or source solver. The workbench may generate
  bounded declared transformations; it cannot infer historical source or
  semantic equivalence from syntax and object score.
- [ ] No bundled proprietary compiler, ROM, target object, or game asset.
- [ ] No generic instrumentation profile applied to unpinned generated source.
- [ ] No universal impossibility claim from a finite source, layout, flag, or
  frontend sweep.
- [ ] No claim that a matched linked layout is shiftable without a measured
  relink.

These unchecked non-goals are guardrails, not missing buttons. Implement them
only when a real campaign supplies a falsifiable model, redistributable tests,
and a failure-closed acceptance gate.
