# Roadmap to 1.0

As of 0.6.0, 2026-08-17. Each item carries the campaign evidence that earned
its place; nothing here is speculative. The dated design discussions behind
the older items are preserved in
[the 2026-07/08 tooling roadmap](history/tooling-roadmap.md).

## What 1.0 means

- Every blocker below is shipped or explicitly withdrawn with a recorded
  reason.
- The command surface and JSON schemas carry a semantic-versioning
  compatibility statement.
- The two open release-infrastructure items from the
  [quality checklist](workbench-quality-checklist.md) are closed: the PyPI
  trusted publisher is registered, and the published artifact — not a locally
  built wheel — passes the smoke journey in a fresh environment.

## Blockers: instrumentation

1. **A `[CDX] pre`/`hoistcand` record for uopt's PRE and speculative-hoist
   choice.** Two independent scratches in the 2026-08 GE007 frontier campaign
   hit the identical wall: the residual was decided before p1 coloring, in a
   pass the current CDX stream does not record. The highest-value single
   instrument left.
2. **A ugen FP-temp/freelist tracer.** The ugen expression-temp rotation law
   was reverse-engineered black-box twice by different operators because the
   allocator's own decision stream is unobservable. A `CDX_LOG`-style record
   on the ugen temp allocator replaces that probing. The macOS half of the
   fix is already documented: an unsigned instrument binary is killed by
   codesign, and `codesign --force -s -` clears it
   ([troubleshooting](troubleshooting.md)).
3. **Per-section size deltas on the compare verdict line.** A `words=0`
   comparison across 17,588 instructions whose `.data` had grown 0x20 → 0x60
   still printed "no source change is indicated". The verdict line should
   carry section deltas whenever any section beyond the compared function
   changed, in the spirit of `object collateral` but visible on the everyday
   command.

## Blockers: verification

4. **Post-link relocation-resolved comparison as a command.** The frontier
   campaign's `relink.py`/`verify-tu.sh` resolve `symbol_value+addend` and
   compare final bytes — strictly stronger than `words=0` and than raw `cmp`,
   both of which false-positive on anonymous `.rodata` jump tables. Promote
   that logic into the workbench with the usual verdict/JSON contract.
5. **Context faithfulness checks on scratch intake.** A scratch's `ctx.c` is
   not repo-faithful, and nothing cross-checks it: an `s32`-vs-`u8*` field
   and an `s32`-vs-`f32` prototype each cost about ten builds before being
   noticed by hand. `fetch-scratch`/`check-scratch` should diff declarations
   in `ctx.c` against project headers when the project is configured.

## Next: campaign ergonomics

6. **`compare --summary` and a transposition diff class.** A pure 2×2
   instruction transposition reported `opcodes=2 gaps=12` and nearly got a
   best candidate reverted; the diff classes have no name for "same
   instructions, two swapped positions".
7. **Nonmatching census and stale-name lint.** Manifest queues covered 135 of
   198 nonmatching functions in the frontier campaign, and three
   `sub_GAME_<hex>` names carried stale addresses. A `list-nonmatching`
   census and a `check-stale-names` lint close both gaps.
8. **Permuter integration hardening.** Of eleven permuter "improvements" in
   one session, two were real: add a frame-mismatch hard reject, opcode-aware
   scoring, and a `permuter-export` shim so its candidates enter a campaign
   ledger instead of a terminal scroll.
9. **A falsified-hypothesis dossier schema.** Roughly 150 of the frontier
   campaign's 215 commits closed candidate routes, but only as prose in a
   5,000-line handoff; ~13,000 permuter iterations partly re-walked closed
   routes. A per-function dossier (hypothesis / lever / result /
   do-not-repeat) would make the negative space queryable, and a
   `manifest.accepted` pointer would make the positive terminal state
   discoverable instead of living in loose `accepted-code.c` files.
10. **`doctor` host checks for environment folklore.** zsh word-splitting,
    BSD vs GNU sed/head, codesign kills, stale build-artifact hashes — each
    cost a session before being written down
    ([troubleshooting](troubleshooting.md)); `doctor` can test all of them in
    milliseconds.

## Open design questions, carried forward

Filed with their full discussion in
[history/tooling-roadmap.md](history/tooling-roadmap.md):

- a `tie` result that reaches the `probe-lines` verdict vocabulary;
- tie sweeps as a first-class recorded experiment;
- a placement-ladder mechanism for lever 28's positional axis;
- lane evidence that lets `view` split the `pool-position` playbook into
  routable families;
- an IDO driver stage-capture harness, a ucode record decoder, and a
  stage-position map;
- a save-class force control and the terms of its verdict;
- a campaign-manifest object model, and instrument builds that cannot return
  an ungated binary;
- normalize host-specific pass-listing paths only after an unedited replay
  proves fidelity.

And from [final-function campaigns](final-function-campaigns.md): stable web
fingerprints, source/IR/listing provenance for temporary webs and stack
homes, interference-edge explanations, and linked-address alias
classification from final linked output.
