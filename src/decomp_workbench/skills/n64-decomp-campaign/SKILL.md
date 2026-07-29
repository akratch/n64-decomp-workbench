---
name: n64-decomp-campaign
description: Diagnose and finish late-stage N64 MIPS decompilation mismatches with reproducible evidence, object comparison, IDO allocator traces, and source-variant campaigns. Use for near-matching functions, decomp.me score plateaus, cross-ROM comparisons, register-allocation residuals, or planning a decompilation campaign.
---

# N64 Decomp Campaign

Use this skill to turn a stubborn N64 decompilation residual into a sequence of
small, falsifiable experiments. Use the project's normal object or ROM build as
the final oracle. Treat a browser percentage as a lead, never as proof.

## Start from an evidence inventory

Before editing source, identify and preserve:

- target function object or a redistributable objdump dump;
- current source and its translation-unit context;
- compiler version, flags, wrapper, and working directory;
- current comparison report, candidate hash, and project build result;
- relevant trace/log only when the residual is allocation- or schedule-related.

Run `decomp-workbench compare` or `compare-dumps` before choosing an
experiment. Record the verdict, not only a scalar score.

## Choose the next experiment from the residual

| Evidence | Work on | Do not start with |
|---|---|---|
| Instruction count, opcode sequence, or frame differs | Control flow, loop form, calls, expression tree, declaration form | Register forcing or fake locals |
| Opcode shape is stable but registers differ | Lifetimes, variable reuse, declaration order, and one allocator web | Broad source rewrites |
| Only relocation-controlled raw words differ | Translation-unit context and final linked/ROM output | Chasing a display percentage |
| Cross-ROM structure matches | Shared lineage as a structural witness | Calling it target-object exact |
| A local forced/unrolled loop looks good but the function does not | Whole-function roles and liveness | More local fakes or manual unrolling |

Read [references/evidence-ladder.md](references/evidence-ladder.md) when
interpreting comparison evidence or external scores. Read
[references/ido-late-stage-patterns.md](references/ido-late-stage-patterns.md)
when the mismatch is caused by IDO code generation or register allocation.

## Run a controlled campaign

1. State one causal hypothesis in the candidate name or manifest.
2. Change one family at a time: declaration order, carrier reuse, expression
   tree, loop spelling, literal type, or live-range boundary.
3. Compile variants through `decomp-workbench campaign` with an explicit
   compiler wrapper, working directory, environment, cache, and ledger.
4. Compare every successful object; inspect object basins so identical compiler
   outcomes do not masquerade as independent discoveries.
5. Keep promising source/object pairs and the associated trace evidence.
6. Return to a readable, source-level explanation after a force probe or fake
   demonstrates causality.

Use `trace-globalcolor --proc PROC --web WEB` only after the comparator has
isolated an allocation residual. A force-color build tests a cause; it is not a
source match.

Read [references/campaign-hygiene.md](references/campaign-hygiene.md) when
creating candidates, scratch artifacts, commits, or a public progress repo.

## Validate in the right order

1. Accept `instruction-words-identical` or `instruction-exact` only as
   function-level object evidence.
2. If a function is exact in a scratch but not in a browser, compare the
   scratch context, relocation layout, and linked output before editing C.
3. Run the project's normal build and whole-ROM or project-level verifier.
4. Preserve the exact command, inputs, output hash, and commit that produced
   the final result.

Do not claim completion from normalized distance, a register-only report,
cross-ROM structural evidence, a forced compiler result, or a decomp.me score.

## Report the result

Report: final oracle and result; comparator verdict; the hypothesis confirmed
or rejected; the smallest source-level explanation; exact commands or manifest
location; and any tool gap discovered. Keep ROMs, proprietary compiler
binaries, and non-redistributable target objects out of public artifacts.
