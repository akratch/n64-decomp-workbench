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
| You have a verdict on screen and want the source edit it implies | **[From verdict to edit](from-verdict-to-edit.md)** — including the four classes `diagnose` names the edit for outright |
| You have a pile of near matches and need an order to work them in | **[Backlog walkthrough](walkthrough-30-near-matches.md)** |
| You want a full campaign, dead ends included, as a worked example | **[Case study: SSB64 drawbitmap](../case-studies/ssb64-drawbitmap.md)** |
| You are about to conclude that no source form can reach your target | **[Case study: SSB64 unref_800036B4](../case-studies/ssb64-unref-800036B4.md)** |
| A linked-function match still has a decomp.me score, or one visible register swap hides several allocator webs | **[Case study: SSSV func_802963D0](../case-studies/sssv-func-802963D0.md)** |
| Your 100% project is assumed un-shiftable and nobody has measured it | **[Case study: Pilotwings 64 shiftability](../case-studies/pilotwings64-shiftability.md)** |
| An exact source still contains suspicious fake-match scaffolding | **[Bounded carrier-substitution example](../examples/experiments/carrier-substitution/README.md)** |
| You want implemented capabilities and intentional boundaries | **[Product status](product-status.md)** |
| You want the release-facing acceptance checklist across every user journey | **[Workbench quality checklist](workbench-quality-checklist.md)** |
| You repeatedly diagnose one project/object pair and want portable defaults | **[Project configuration](project-configuration.md)** |
| You want controlled sweeps, immutable promotion, and auditable finish receipts | **[Candidate campaigns](campaigns.md)** |
| You want those endgame gates in one asset-free runnable journey | **[Worked endgame example](campaigns.md#worked-endgame-example)** |
| A stubborn residual looks like "just allocation" | **[Postmortem: GE007 object_interaction](history/postmortem-2026-08-09-ge007.md)** — the taxonomy of source errors that only look that way |

New here? [Start here](START_HERE.md) is a short guided tour, and every command
in it runs against shipped fixtures — no ROM, no compiler, no toolchain.

## The commands

| Read this if... | Document | You need |
|---|---|---|
| You want the exact verdict rules and every `compare` option | [Object comparison](object-comparison.md) | MIPS objects or GNU objdump text |
| You want every `view` option, the alignment rules, and the JSON schema | [Aligned mechanism view](view.md) | Two objects or two reduced dumps |
| A verdict named the shape and you need the *pass* that owns it, and whether a lever reaches it | [The ownership verdict](view.md#reading-the-screen) — the `ownership:` line, and `diagnose --trace` | Two objects; a compiler trace to raise the basis above a heuristic |
| A `next:` footer named a playbook and you want its levers now | [The `guide` command](guide-command.md) | Nothing; the guide ships with the package |
| You are sweeping a variant family and want durable state, or you inherited a campaign directory with no manifest and need to know where it is | [Candidate campaigns](campaigns.md) | A compile-one wrapper |
| Current source, measured best, and accepted source have become confused, or stale targets keep re-entering the queue | [Evidence lifecycle and readiness](evidence-lifecycle.md) | A campaign manifest or target queue |
| You need the family itself — price every lever you inherited, hoist an operand into every free carrier, exchange every commutative pair — and one honest read-back | [Sweeps](sweeps.md) | The C source; a compile-one wrapper |
| You keep re-writing the same decomp-permuter batch loop, or a search "found nothing" and you do not know whether it searched the right thing | [Permuter sweeps](permute-sweep.md) — `permute sweep`, `permute doctor`, `permute classify` | A queue of functions; a decomp-permuter checkout |
| A function's target spells its calls with placeholders no scratch can reproduce, because its module ships unrelocated | [The linked image as an oracle](linked-oracle.md) — `reloc-surface`, `linked-compare`, `reloc-proof` | The module's objects and section map; the target image |
| You are about to order a week of work by a closeness ranking measured some other day | [The ranking is a measurement, and it decays](permute-sweep.md#the-ranking-is-a-measurement-and-it-decays) — `ranking stamp`, `ranking check` | A ranking file; a git checkout |
| A `words=0` might be a comparison against a build older than the source it came from | [Is the thing you compared the thing you just built?](object-comparison.md#is-the-thing-you-compared-the-thing-you-just-built) — `check-staleness`, `--built-from` | The artifacts and the inputs they were built from |
| You keep hand-rolling the same byte-scoring loop, or a flag sweep might be lying to you | [score and matrix](score-and-matrix.md) | A candidate object; a ROM or target object |
| A `schedule` verdict survives `-g0` and every compiler you own, or you know line assignment owns it and need to know which line a statement wants (`--tie`) | [Line-assignment probe](line-assignment-probe.md) | A preprocessed `.i` and your compile command |
| You need a calibrated allocator force probe | [Allocator oracle](oracle.md) | Ready external toolchain and focused trace |
| You are wiring an external compiler tree safely | [Toolchain calibration](toolchain-calibration.md) | User-supplied toolchain and fidelity cells |
| You need to know which source lines own the differing rows | [Region attribution](region-attribution.md) | The candidate's C source |
| Several people or agents append findings to one shared log, or keep filing different findings under the same number | [Shared notes](shared-notes.md) | A findings file anyone may rewrite |
| You consume reports from scripts or CI | [JSON contracts](json-contracts.md) | `--json` |
| You are about to start on a function and do not know whether it is already matched in public | [Gate 0: public match check](public-match-check.md) | The function's name or address; network |
| You downloaded a decomp.me ZIP or the browser/local results disagree | [decomp.me export checking](decompme-exports.md) | Export ZIP/directory; compiler optional |
| You need a complete local decomp.me handoff | [Scratch bundles](scratch-bundles.md) | Target assembly, context, source, settings |
| You are about to publish a proof or integration repository | [Public handoff audit](public-handoffs.md) | Exact handoff tree; optional project dependency root |
| You are about to register a campaign against a scratch/hosted target and want to know its scope is trustworthy before spending days on it | [Target audit](target-audit.md) | A target object; optionally a ROM and a known VA/offset pair |
| Your project is 100% matched and someone wants to mod it, or you need to know which words in the ROM are not explained by a symbol reference | [Shiftability](shiftability.md) | A linker map and a linked image; a relink script for the empirical half |
| You want to actually make your matched project shiftable, start to finish | [The shiftability campaign](shiftability-campaign.md) | The same, plus the ability to edit your linker configuration and relink |
| You know the symptom but not which command to reach for | [Workflow selection](workflows.md) | A target and a current hypothesis |
| A command failed or returned nothing usable | [Troubleshooting](troubleshooting.md) | Command, stderr, and tool identities |

## Reasoning and reference

| Read this if... | Document |
|---|---|
| You want the longer reasoning behind a difficult finish | [Final-function campaign lessons](final-function-campaigns.md) |
| The project compiler provably cannot emit what the target does | [Alternate authentic frontends](alternate-frontends.md) |
| You need to know which IDO 5.3 and 7.1 workflows are validated | [IDO version support](ido-support.md) |
| You want Codex or Claude Code to run the loop for you | [Agent skill](agent-skill.md) |
| You want what the compiler *does*, with the evidence and the claims it corrected | [Compiler laws: IDO 5.3](compiler-laws/ido-5.3.md) — L72-L82 are the newest eleven, from an overlay lever cohort; six say what an edit does and five say what no edit does; `guide laws ido-5.3 L80` prints one |
| Two objects differ in length, or a "huge" mismatch might be one inserted instruction, and you need the row-pairing story behind `align` and `phase` | [Shift and phase](shift-and-phase.md) |
| A trace gives you `save`, `nocs`, `totalsave`, `chargeA`, or `chargeB` and you need the whole allocator formula in one place | [The p1 decision arithmetic](p1-decision-arithmetic.md) |
| A number improved and you are about to trust it | [Metric traps](metric-traps.md) — the catalogue of correct readings of the wrong quantity |
| You are about to blame the allocator | [Source probes](source-probes.md) — the source questions that cost seconds, asked first |
| You want to know why the commands refuse what they refuse | [Principles](principles.md) |
| You are auditing where this package came from | [Provenance](provenance.md) |
| You want what is left before 1.0, with the campaign evidence per item | [Roadmap to 1.0](roadmap.md) |

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
| A late scheduling or copy-propagation decision is suspect | [Pass replay and static Binasm boundary inspection](pass-replay.md) | A retained listing or Binasm stream; as0/as1 only for replay |
| The residual is one word and you need to know which pass owns it | [Phase capture, stream surgery, and replay](phase-capture.md) | An IDO root you can build one translation unit with |

## History

Dated records, preserved as written. Use [Product status](product-status.md)
for current syntax and support claims.

| Record | Date |
|---|---|
| [Field notes: dp64 core campaign](history/field-notes-2026-07-29-dp64.md) | 2026-07-29 |
| [Postmortem: the dp64 campaign day](history/postmortem-2026-07-29-dp64.md) | 2026-07-29 |
| [UX vision](history/ux-vision-2026-07-29.md) | 2026-07-29 |
| [Field notes: SSB64 frontend lineage](history/field-notes-2026-07-30-ssb64.md) | 2026-07-30 |
| [Field notes: SSB64 drawbitmap](history/field-notes-2026-07-31-ssb64-drawbitmap.md) | 2026-07-31 |
| [Tooling roadmap from live campaigns](history/tooling-roadmap.md) | 2026-07-30 → 08-08 |
| [Postmortem: GE007 object_interaction](history/postmortem-2026-08-09-ge007.md) | 2026-08-09 |
| [Trustworthy endgames campaign spec](history/trustworthy-endgames-campaign.md) | 2026-08-11 |
| [Trustworthy endgame acceptance receipt](history/live-acceptance-2026-08-11.md) | 2026-08-11 |
| [Design notes, by release](history/design-notes.md) | rolling |

Maintainers: the [release checklist](release-checklist.md) and
[quality checklist](workbench-quality-checklist.md) gate every release.

Every command has `--help`. `decomp-workbench --explain-keys` prints the one
registry of printed labels, JSON keys, and their meanings; reporting commands
that use those metrics accept the same option after the command name.
Reporting commands expose JSON wherever it is useful for scripts and CI.
