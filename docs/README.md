# Documentation

| Guide | Use it when | You need |
|---|---|---|
| [Workflows](workflows.md) | You know the symptom but not the command | A target and a current hypothesis |
| [Object comparison](object-comparison.md) | You need an exact verdict or mismatch classification | MIPS objects or GNU objdump text |
| [Candidate campaigns](campaigns.md) | You have a source generator or variant set | A compile-one wrapper |
| [Scratch bundles](scratch-bundles.md) | You need a complete local decomp.me handoff | Target assembly, context, source, settings |
| [IDO version support](ido-support.md) | You need to know which 5.3 and 7.1 workflows are validated | Project compiler/pass identities |
| [Trace analysis](trace-analysis.md) | Structure matches but allocation or aliasing does not | A supported trace |
| [Compiler instrumentation](compiler-instrumentation.md) | You need a trace producer for static-recompiled IDO | Generated compiler C and its build |
| [Pass replay](pass-replay.md) | A late scheduling decision is suspect | A retained listing plus as0/as1 |
| [Troubleshooting](troubleshooting.md) | A command fails or returns no usable result | Command, stderr, and tool identities |
| [Tooling roadmap](tooling-roadmap.md) | You want the reusable gaps found in live campaigns | Evidence from a completed or late-stage match |

[Principles](principles.md) explains the safety and evidence rules behind the
commands. [Provenance](provenance.md) records the small amount of source history
needed to audit the package.

Every command has `--help`. Reporting commands expose JSON where it is useful
for scripts and CI.
