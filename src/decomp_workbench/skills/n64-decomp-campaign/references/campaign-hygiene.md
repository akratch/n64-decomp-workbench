# Campaign hygiene

## Keep experiments reproducible

For each campaign, retain a small manifest or ledger containing:

- target identity and selected symbol;
- compiler wrapper, compiler version, flags, working directory, and declared
  environment;
- candidate generator version and transformation parameters;
- object hash and comparison verdict for each successful candidate;
- trace command and focus when traces informed the decision;
- final project verifier command and result.

Use experiment v2 when claims need enforcement: target-relative signal
receipts, absolute/differential controls run before scale, and a coverage
declaration whose exclusions are bounded and explained. Keep the compiler
envelope explicit—frontend, driver, language, backend, and canonical build—so
an IRIX 4 frontend cell cannot collapse into a later frontend's cache basin.

Use `decomp-workbench campaign` for the cache and JSONL ledger. Store candidate
source outside the active project translation unit unless the project itself
requires an integration test.

Promote by immutable cache key, source hash, and full object hash. `campaign
finish` performs a fresh rebuild; optional scratch, collateral, handoff, and
project checks are separate gates and must not be summarized as run when their
receipt says `NOT RUN`.

## Keep public proof useful and safe

Publish only material your project may redistribute. Prefer a minimal scratch
bundle, reduced objdump text, synthetic trace, source sketch, manifest, or
tooling diff. Do not publish ROMs, proprietary compiler binaries, or target
objects with unclear redistribution terms.

When creating a public progress repository, make each commit independently
understandable:

- say what hypothesis changed;
- include the current source/context artifact where redistribution permits;
- record the evidence level, not just a percentage;
- distinguish a promising sketch from an exact verified function;
- use an unmistakable final commit message only after the final verifier passes;
- scope any published negative — name the statement order, layout family,
  frontend, and flags it was measured under. An unscoped "impossible" invites
  the community to disprove the claim you did not intend to make, and one
  such claim was disproved within a day. Credit the disprover prominently
  when that happens: a falsified claim that names its falsifier is still
  good science, and the campaign record gains a lever from it;
- keep dominated variants on disk and say where they live. A variant that
  fixed a subset of the residual is a baseline someone else can stack one
  more lever on, and deleting it deletes that path.

Before pushing, run `decomp-workbench handoff audit PATH`. If the README
refers into a separate project, add `--dependency-root PROJECT`; the audit
then distinguishes a published dependency from a file that merely exists in
the local worktree. Fix every `missing-path-reference`, `untracked-file`, and
`untracked-dependency`. The audit establishes publication completeness, not
function exactness or compiler provenance.

## Capture tooling gaps

When the investigation exposes a missing diagnostic, record: the input class,
the misleading current output, the desired classification, the safe fallback,
and a redistributable fixture. Build the tool so it reports confidence and
provenance instead of silently guessing.
