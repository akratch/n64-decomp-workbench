# Documentation

Read in this order. The first three pages are the whole workflow; everything
below them is reference you consult when you need it.

## Terms, if you are new to N64 decomp

- **IDO** — SGI's optimizing MIPS C compiler for IRIX, and the usual N64
  decompilation target. Its passes are what every verdict here is about.
- **asm-processor** — the community preprocessor that lets hand-written MIPS
  assembly live inside C while a function is still being matched.
- **ugen / uopt** — IDO's code generator and optimizer passes. `uopt` colors
  variable webs into the register pool; `ugen` rotates block-local expression
  temps. The trace commands read their internal state.
- **decomp.me** — the community's browser service for sharing a scratch and
  scoring how close a candidate is.

## Start

| Read this if... | Document |
|---|---|
| You have an almost-matched function and do not know what to do next | **[Start here](START_HERE.md)** |
| `view` named a mechanism and you need the C that moves it | **[Field guide](field-guide.md)** |
| You have a verdict on screen and want the source edit it implies | **[From verdict to edit](from-verdict-to-edit.md)** |
| You have a pile of near matches and need an order to work them in | **[Backlog walkthrough](walkthrough-30-near-matches.md)** |
| You want a full campaign, dead ends included, as a worked example | **[Case study: SSB64 drawbitmap](../case-studies/ssb64-drawbitmap.md)** |
| You are about to conclude that no source form can reach your target | **[Case study: SSB64 unref_800036B4](../case-studies/ssb64-unref-800036B4.md)** |
| A linked-function match still has a decomp.me score, or one visible register swap hides several allocator webs | **[Case study: SSSV func_802963D0](../case-studies/sssv-func-802963D0.md)** |
| An exact source still contains suspicious fake-match scaffolding | **[Bounded carrier-substitution example](../examples/experiments/carrier-substitution/README.md)** |
| You want implemented capabilities and intentional boundaries | **[Product status](product-status.md)** |
| You have a stubborn residual you're sure is "just allocation," and want the taxonomy of source errors that only look that way | **[Postmortem: GE007 object_interaction](postmortem-2026-08-09-ge007.md)** |

New here? [Start here](START_HERE.md) takes ten minutes, and every command in
it runs against shipped fixtures — no ROM, no compiler, no toolchain.

## The commands

| Read this if... | Document | You need |
|---|---|---|
| You want the exact verdict rules and every `compare` option | [Object comparison](object-comparison.md) | MIPS objects or GNU objdump text |
| You want every `view` option, the alignment rules, and the JSON schema | [Aligned mechanism view](view.md) | Two objects or two reduced dumps |
| A `next:` footer named a playbook and you want its levers now | [The `guide` command](guide-command.md) | Nothing; the guide ships with the package |
| You are sweeping a variant family and want durable state | [Candidate campaigns](campaigns.md) | A compile-one wrapper |
| You keep hand-rolling the same byte-scoring loop, or a flag sweep might be lying to you | [score and matrix](score-and-matrix.md) | A candidate object; a ROM or target object |
| A `schedule` verdict survives `-g0` and every compiler you own, or you know line assignment owns it and need to know which line a statement wants (`--tie`) | [Line-assignment probe](line-assignment-probe.md) | A preprocessed `.i` and your compile command |
| You need a calibrated allocator force probe | [Allocator oracle](oracle.md) | Ready external toolchain and focused trace |
| You are wiring an external compiler tree safely | [Toolchain calibration](toolchain-calibration.md) | User-supplied toolchain and fidelity cells |
| You need to know which source lines own the differing rows | [Region attribution](region-attribution.md) | The candidate's C source |
| Several people or agents append findings to one shared log | [Shared notes](shared-notes.md) | A findings file anyone may rewrite |
| You consume reports from scripts or CI | [JSON contracts](json-contracts.md) | `--json` |
| You downloaded a decomp.me ZIP or the browser/local results disagree | [decomp.me export checking](decompme-exports.md) | Export ZIP/directory; compiler optional |
| You need a complete local decomp.me handoff | [Scratch bundles](scratch-bundles.md) | Target assembly, context, source, settings |
| You are about to publish a proof or integration repository | [Public handoff audit](public-handoffs.md) | Exact handoff tree; optional project dependency root |
| You know the symptom but not which command to reach for | [Workflow selection](workflows.md) | A target and a current hypothesis |
| A command failed or returned nothing usable | [Troubleshooting](troubleshooting.md) | Command, stderr, and tool identities |

## Reasoning and reference

| Read this if... | Document |
|---|---|
| You want the longer reasoning behind a difficult finish | [Final-function campaign lessons](final-function-campaigns.md) |
| The project compiler provably cannot emit what the target does | [Alternate authentic frontends](alternate-frontends.md) |
| You need to know which IDO 5.3 and 7.1 workflows are validated | [IDO version support](ido-support.md) |
| You want Codex or Claude Code to run the loop for you | [Agent skill](agent-skill.md) |
| You want what the compiler *does*, with the evidence and the claims it corrected | [Compiler laws: IDO 5.3](compiler-laws/ido-5.3.md) |
| Two objects differ in length, or a "huge" mismatch might be one inserted instruction, and you need the row-pairing story behind `align` and `phase` | [Shift and phase](shift-and-phase.md) |
| A trace gives you `save`, `nocs`, `totalsave`, `chargeA`, or `chargeB` and you need the whole allocator formula in one place | [The p1 decision arithmetic](p1-decision-arithmetic.md) |
| A score improved, or a lever's old price looked stable, and you want the catalogue of ways that can still be the wrong reading | [Metric traps](metric-traps.md) |
| You are about to blame the allocator, and want the two source questions to ask first: are these two reads the same value, and where can a statement that emits nothing change the allocation | [Source probes](source-probes.md) |
| You want to know why the commands refuse what they refuse | [Principles](principles.md) |
| You are auditing where this package came from | [Provenance](provenance.md) |
| You want the reusable gaps found in live campaigns | [Historical tooling roadmap](tooling-roadmap.md) |
| You want the dated audit that drove the current product | [Historical elite product review](elite-product-review-2026-07-29.md) |
| You want the longer design target and rationale | [North-star UX vision](ux-vision-2026-07-29.md) |

## Compiler internals and traces

Reach for these **last**, and only when the residual is register-only, the
[field guide](field-guide.md) lever families are exhausted, and your project
has an instrumented static-recompiled IDO. Stock IDO does not emit these
traces, and three functions have been matched without ever reading one.

| Read this if... | Document | You need |
|---|---|---|
| Structure matches but allocation or aliasing does not | [Trace analysis](trace-analysis.md) | A supported trace |
| One variable is stuck and you need every round of its allocator decision, the colour it really got, and which occurrence paid which charge | [The allocator decision cascade](cdx-cascade.md) | A CDX log |
| You need a trace producer for static-recompiled IDO | [Compiler instrumentation](compiler-instrumentation.md) | Generated compiler C and its build |
| A late scheduling decision is suspect | [Pass replay](pass-replay.md) | A retained listing plus as0/as1 |

The dated field notes, skill feed, postmortem, review, and UX vision preserve
the evidence as it looked on the day each was written — 2026-07-29 for the
dp64 set, [2026-07-30](field-notes-2026-07-30-ssb64.md) for the SSB64
frontend-lineage campaign, and
[2026-08-09](postmortem-2026-08-09-ge007.md) for the GE007
`object_interaction` campaign that produced this page's newest compiler laws.
Use [Product status](product-status.md) for current syntax and support
claims.

Every command has `--help`. `decomp-workbench --explain-keys` prints the one
registry of printed labels, JSON keys, and their meanings; reporting commands
that use those metrics accept the same option after the command name.
Reporting commands expose JSON wherever it is useful for scripts and CI.
