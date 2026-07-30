# Documentation

Read in this order. The first three pages are the whole workflow; everything
below them is reference you consult when you need it.

## Start

| Read this if... | Document |
|---|---|
| You have an almost-matched function and do not know what to do next | **[Start here](START_HERE.md)** |
| `view` named a mechanism and you need the C that moves it | **[Field guide](field-guide.md)** |
| You have a pile of near matches and need an order to work them in | **[Backlog walkthrough](walkthrough-30-near-matches.md)** |
| You want implemented capabilities and intentional boundaries | **[Product status](product-status.md)** |

New here? [Start here](START_HERE.md) takes ten minutes, and every command in
it runs against shipped fixtures — no ROM, no compiler, no toolchain.

## The commands

| Read this if... | Document | You need |
|---|---|---|
| You want the exact verdict rules and every `compare` option | [Object comparison](object-comparison.md) | MIPS objects or GNU objdump text |
| You want every `view` option, the alignment rules, and the JSON schema | [Aligned mechanism view](view.md) | Two objects or two reduced dumps |
| A `next:` footer named a playbook and you want its levers now | [The `guide` command](guide-command.md) | Nothing; the guide ships with the package |
| You are sweeping a variant family and want durable state | [Candidate campaigns](campaigns.md) | A compile-one wrapper |
| You need a calibrated allocator force probe | [Allocator oracle](oracle.md) | Ready external toolchain and focused trace |
| You are wiring an external compiler tree safely | [Toolchain calibration](toolchain-calibration.md) | User-supplied toolchain and fidelity cells |
| You consume reports from scripts or CI | [JSON contracts](json-contracts.md) | `--json` |
| You downloaded a decomp.me ZIP or the browser/local results disagree | [decomp.me export checking](decompme-exports.md) | Export ZIP/directory; compiler optional |
| You need a complete local decomp.me handoff | [Scratch bundles](scratch-bundles.md) | Target assembly, context, source, settings |
| You know the symptom but not which command to reach for | [Workflow selection](workflows.md) | A target and a current hypothesis |
| A command failed or returned nothing usable | [Troubleshooting](troubleshooting.md) | Command, stderr, and tool identities |

## Reasoning and reference

| Read this if... | Document |
|---|---|
| You want the longer reasoning behind a difficult finish | [Final-function campaign lessons](final-function-campaigns.md) |
| You need to know which IDO 5.3 and 7.1 workflows are validated | [IDO version support](ido-support.md) |
| You want Codex or Claude Code to run the loop for you | [Agent skill](agent-skill.md) |
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
| You need a trace producer for static-recompiled IDO | [Compiler instrumentation](compiler-instrumentation.md) | Generated compiler C and its build |
| A late scheduling decision is suspect | [Pass replay](pass-replay.md) | A retained listing plus as0/as1 |

The dated field notes, skill feed, postmortem, review, and UX vision preserve
the evidence as it looked on 2026-07-29. Use
[Product status](product-status.md) for current syntax and support claims.

Every command has `--help`. `decomp-workbench --explain-keys` prints the one
registry of printed labels, JSON keys, and their meanings; reporting commands
that use those metrics accept the same option after the command name.
Reporting commands expose JSON wherever it is useful for scripts and CI.
