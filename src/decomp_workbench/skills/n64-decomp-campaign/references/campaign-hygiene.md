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

Use `decomp-workbench campaign` for the cache and JSONL ledger. Store candidate
source outside the active project translation unit unless the project itself
requires an integration test.

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

## Capture tooling gaps

When the investigation exposes a missing diagnostic, record: the input class,
the misleading current output, the desired classification, the safe fallback,
and a redistributable fixture. Build the tool so it reports confidence and
provenance instead of silently guessing.
