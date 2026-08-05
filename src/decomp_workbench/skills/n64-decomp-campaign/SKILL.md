---
name: n64-decomp-campaign
description: Diagnose and finish late-stage N64 MIPS decompilation mismatches with reproducible evidence, object comparison, guided field-guide levers, IDO allocator traces, frontend-lineage checks, and source-variant campaigns. Use for near-matching functions, decomp.me score plateaus, cross-ROM comparisons, register-allocation residuals, dispatch shapes the project compiler cannot emit, or planning a decompilation campaign.
---

# N64 Decomp Campaign

Use this skill to turn a stubborn N64 decompilation residual into a sequence of
small, falsifiable experiments. Use the project's normal object or ROM build as
the final oracle. Treat a browser percentage as a lead, never as proof.

## Start from an evidence inventory

Before editing source, identify and preserve:

- target function object or a redistributable objdump dump;
- current source and its translation-unit context;
- compiler family/version, canonical compiler ID, language/frontend, preset,
  driver, flags, wrapper, and working directory as separate fields;
- current comparison report, candidate hash, and project build result;
- relevant trace/log only when the residual is allocation- or schedule-related.

Then prove the harness before trusting it: compare a known-matching sibling
function (or a shipped fixture) through the same compiler wrapper, flags, and
comparator invocation, and require `instruction-words-identical` before
touching the real target. Every recorded campaign that skipped this step
either chased a stale context file or credited the wrong compiler; every one
that ran it caught the problem in minutes.

Run `decomp-workbench diagnose` or `diagnose-dumps` before choosing an
experiment. It loads each input once and returns both exact comparison truth
and the decisive aligned mechanism view. Use `compare` for a compact gate and
`view --show-all` for every hunk. Record the verdict, not only a scalar score.

When the input is a downloaded decomp.me ZIP, start with
`decomp-workbench check-scratch SCRATCH.zip --view`. It reads the site's own
target/current objects, keeps the display score separate from object truth,
and can reproduce `ctx.c` plus the language-aware `src.c`/`src.cxx` line reset
and candidate composition with `--compile-command`. Its frontend line names
the canonical compiler ID, language, expected driver, and frontend family;
verify those before interpreting a compiler error. It never logs in or uploads.

The `next:` footer under every verdict names the matching field-guide
levers and the exact `decomp-workbench guide <playbook|lever|verdict>` command
that prints them; heed it before inventing an experiment, and consult the
field guide's dead-families table before re-testing a family it already
buried. Heed input warnings the same way: a cross-function warning means the
comparison itself is invalid, not that the source is far. In batch loops,
`--terse` drops only the orientation lines. When `compare` reports a coarse
allocation verdict it deliberately names three candidate families without
choosing; run `view` or `diagnose` to get the committed family before
spending a variant.

Rank candidates by `aligned_total`, never by `words`. Positional word counts
shift on every inserted or deleted instruction, so the variant one edit away
can report a longer residual than one with a dozen unrelated allocation
differences. `words=0` with `exact=true` is still the only matching claim.

## Choose the next experiment from the residual

| Evidence | Work on | Do not start with |
|---|---|---|
| Instruction count, opcode sequence, or frame differs | Control flow, loop form, calls, expression tree, declaration form | Register forcing or fake locals |
| Opcode shape is stable but registers differ | Lifetimes, variable reuse, declaration order, and one allocator web | Broad source rewrites |
| Only relocation-controlled raw words differ | Translation-unit context and final linked/ROM output | Chasing a display percentage |
| Same instruction multiset, different order | Expression/statement topology, then frontend-specific statement line assignment — moves change which numbers a statement can carry and logical-line ties change the relations — then as1 scheduling | Assuming cfe and EDG attribute a backslash splice identically; calling `-g0` collapse source proof |
| Cross-ROM structure matches | Shared lineage as a structural witness | Calling it target-object exact |
| A local forced/unrolled loop looks good but the function does not | Whole-function roles and liveness | More local fakes or manual unrolling |
| A dispatch shape the project frontend provably cannot emit, clustering by translation unit | Frontend lineage: alternate authentic frontends, dispatch-construct discrimination | More source spellings against the impossible shape |

Read [references/evidence-ladder.md](references/evidence-ladder.md) when
interpreting comparison evidence or external scores. Read
[references/ido-late-stage-patterns.md](references/ido-late-stage-patterns.md)
when the mismatch is caused by IDO code generation or register allocation.

## Run a controlled campaign

1. State one causal hypothesis with `campaign note` and in the experiment
   manifest when a generator produced the family.
2. Change one family at a time: declaration order, carrier reuse, expression
   tree, loop spelling, literal type, or live-range boundary.
3. Validate a `decomp-workbench-experiment-v1` sidecar with `experiment
   validate` when parameters or a protected instruction region matter.
4. Compile variants through `decomp-workbench campaign` with an explicit
   compiler wrapper, working directory, and environment. The identity-checked
   manifest and append-only ledger are created under `.decomp-workbench/` by
   default.
5. Compare every successful object; inspect `campaign status` so trajectory,
   failures, family space, and object basins survive interruption. Identical
   compiler outcomes do not masquerade as independent discoveries.
   Filter a large sweep with `compare --census KEY=VALUE` (exit 0 when every
   predicate holds, 3 when one fails) rather than writing another objdump and
   regular-expression layer.
6. Keep promising source/object pairs and the associated trace evidence.
   Treat a variant that fixes any subset of the residual as a new baseline
   and re-run the layout levers on top of it, even when its own score is
   dominated — the recorded `unref_800036B4` match was two edits from
   variants already on disk in a campaign that had scored them "partial,
   dominated" and moved on.
7. Use `campaign resume` for work absent from the validated ledger; do not
   reconstruct the source glob by hand.
8. Return to a readable, source-level explanation after a force probe or fake
   demonstrates causality.

Use `trace-globalcolor --proc PROC --web WEB` only after the comparator has
isolated an allocation residual. Use `trace-webs --against` to align variants
by semantic provenance and `trace-source` to map a logical line through
retained `#line`/`.loc` evidence without guessing. Plan a force grid with
`oracle plan`, which always reports p1 and p2 and excludes forbidden colors.
`oracle force/sweep` requires an intact, fully calibrated real-copy toolchain;
reopen results with `oracle status`. A forced exact build tests a cause; it is
not a source match.

For a schedule residual, rebuilding with `-g0` is a layer-ownership probe. A
collapse proves debug metadata constrains the `-g3` schedule and as1 can reach
the target order; it does not prove the source shape is original. A freer
scheduler can rescue a wrong topology. Compare topology and line tags before
capturing the smallest possible as1 ready-set trace.

Read [references/campaign-hygiene.md](references/campaign-hygiene.md) when
creating candidates, scratch artifacts, commits, or a public progress repo.
Read [references/frontend-lineage.md](references/frontend-lineage.md) when a
residual survives every source family and the shape looks impossible for the
project compiler — the frontend is a variable, not a constant, and hundreds of
variants against an unreachable shape are the most expensive way to learn
that.

Before calling a compiler path patched or impossible, run
`fingerprint-toolchain` through every plausible stock driver. Its dense-four
and dense-five switch cells report `chain` versus `table`; record the driver
and frontend with the result. A backend shared by two drivers does not imply
the drivers hand it the same control-flow IR, so source-level lowering remains
a frontend question until pass-boundary evidence proves otherwise.

## Validate in the right order

1. Accept `instruction-words-identical` or `instruction-exact` only as
   function-level object evidence. If the deliverable is a zero decomp.me
   score, additionally require `check-scratch` to report
   `decomp_me_score_proxy_exact=true`, with both
   `raw_instruction_words_exact=true` and `relocation_targets_exact=true`;
   `instruction-exact` alone can hide a scored relocation spelling.
2. If local and browser results disagree, run `check-scratch` and reproduce the
   site's context/line reset before editing C.
3. Run the project's normal build and whole-ROM or project-level verifier.
4. Preserve the exact command, inputs, output hash, and commit that produced
   the final result.
5. Before publishing a proof repository, run:
   `decomp-workbench handoff audit PATH --dependency-root PROJECT`. Resolve
   every missing or untracked dependency; a file on the author's machine is
   not a reproducible handoff.

Do not claim completion from normalized distance, a register-only report,
cross-ROM structural evidence, a forced compiler result, or a decomp.me score.

## Report the result

Report: final oracle and result; comparator verdict; the hypothesis confirmed
or rejected; the smallest source-level explanation; exact commands or manifest
location; and any tool gap discovered. A clean negative on a callee-saved
tie-break (field-guide lever 19) is a legitimate terminal result: record it,
bundle the scratch, and take the next function rather than grinding variants
past the point the evidence supports. Scope every negative or impossibility
claim to the space actually searched — statement order, physical layout,
frontend, flag set. "No layout reaches the target" published without the
fixed-statement-order caveat was falsified within a day by a natural-source
match built from ties the sweep never varied. Keep ROMs, proprietary compiler
binaries, and non-redistributable target objects out of public artifacts.
