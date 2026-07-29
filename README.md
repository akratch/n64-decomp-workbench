# N64 Decomp Workbench

[![CI](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml)

Find the cause of late-stage MIPS decompilation mismatches.

The workbench compares objects without being fooled by relocations, runs
reproducible source-candidate campaigns, turns compiler traces into useful
reports, and replays late compiler passes. It complements asm-differ; it does
not replace your project’s build or matching checks.

## Is this for me?

Use it when:

- your candidate is close, but the remaining mismatch is hard to classify;
- you are compiling many source variants and need caching plus a durable ledger;
- the instruction shape matches but register allocation does not;
- you need to test whether uopt, ugen, or as1 owns a difference.

You do not need a ROM or compiler to try the included fixtures. Real object
comparison needs a GNU-compatible MIPS objdump. Compiler tracing and pass replay
need binaries supplied by your project.

## What it delivers

| Problem | Command | Output |
|---|---|---|
| Are these objects instruction-exact? | `compare` | Relocation-aware verdict, mismatch counts, register ranges, JSON |
| Can I share the comparison without sharing objects? | `compare-dumps` | The same report from reduced objdump text |
| Which candidate is closest? | `rank` | Stable structural and exact ranking |
| How do I run hundreds of variants safely? | `campaign` | Parallel builds, content cache, JSONL provenance ledger |
| What events are present in this trace? | `trace-summary` | Event, register, and source-line counts |
| Is temp-register reuse following a FIFO? | `trace-fifo` | Validated queue and physical-to-logical value schedule |
| Why did uopt keep or split a live range? | `trace-globalcolor` | Per-web costs and color/split decisions, filterable by procedure |
| Which alias facts reached uopt? | `trace-alias` | Base provenance and may-alias decisions |
| Would one late-pass edit explain the object? | `replay-as1` | A rebuilt object from an edited retained listing |
| Can I hand this function to decomp.me without uploading it? | `bundle-scratch` | Target, context, source, settings, and checksums |
| Can I observe static-recompiled IDO? | `instrument-ugen`, `instrument-uopt` | Instrumented generated C with opt-in traces |

## Install

Python 3.10 or newer:

```sh
git clone https://github.com/akratch/n64-decomp-workbench.git
cd n64-decomp-workbench
python3 -m pip install -e .
```

The installed package has no runtime dependencies outside the Python standard
library.

## Try it in 60 seconds

Compare two fixture dumps whose raw words differ only in relocated fields:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

Expected result:

```text
words=   0 raw=   2 norm=   0 regs=   0 fp=   0 insns=   6 ...
```

`words=0` is the relocation-aware result. `raw=2` shows why a literal word
comparison would have rejected the candidate.

Now inspect a real register mismatch:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/register-mismatch.objdump \
  --show-diff
```

## Use it in a decomp project

Compare one function:

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

Run generated source variants through your existing compile wrapper:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --cache-dir .workbench/cache \
  --ledger .workbench/results.jsonl \
  --jobs 8
```

The command template is tokenized and executed without a shell. Every ledger
record includes source, target, wrapper, objdump, explicit environment, timing,
and comparison identity.

## Pick the next diagnostic

| What the comparison says | Next move |
|---|---|
| Instruction count or opcode shape differs | Keep working at the C/control-flow level |
| Shape matches; registers differ | Capture the narrowest relevant uopt or ugen trace |
| Raw words differ; relocation-aware words match | Check relocation metadata, then use the project link/ROM check |
| A late schedule differs | Retain the ugen listing and calibrate `replay-as1` |
| `exact=true` | Run the project’s normal collateral and full-output verification |

Package a single-function target, full context, and current source for manual
decomp.me creation without uploading anything:

```sh
decomp-workbench bundle-scratch scratch/demo \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-O2 -mips2' \
  --diff-label demo
```

Start with [workflow selection][workflows], then use the focused guide:

- [Object comparison][object-comparison]
- [Lessons from final-function campaigns][final-function-campaigns]
- [Candidate campaigns][campaigns]
- [Scratch bundles][scratch-bundles]
- [IDO version support][ido-support]
- [Trace analysis][trace-analysis]
- [Compiler instrumentation][compiler-instrumentation]
- [Tooling roadmap from live campaigns][tooling-roadmap]
- [Pass replay][pass-replay]
- [Castlevania 64 worked examples][cv64-examples]
- [Troubleshooting][troubleshooting]
- [Command design principles][principles]

The [documentation index][documentation] lists inputs, outputs, and support
boundaries in one place.

## Support boundary

Comparison, ranking, campaigns, scratch bundling, trace parsing, and pass
replay are adapters: bring your own object files, objdump, compiler wrapper,
scratch inputs, traces, or pass binaries. These workflows support IDO 5.3 and
7.1 when the project supplies the corresponding toolchain.

The packaged uopt patch profiles are intentionally narrower. They accept
generated `uopt.c` from one pinned IDO 5.3 static-recomp revision, verify its
SHA-256 and source anchors, and reject unknown input by default. The generic
ugen instrumenter supports a broader but shallower call/free-list trace.

The repository contains no ROMs, target objects, proprietary compiler
binaries, or extracted non-code game assets. The attributed CV64 materials are
limited to complete single-function scratch handoffs.

## Development

```sh
python3 -m pip install -e ".[dev]"
python3 -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src tests
```

See [CONTRIBUTING.md][contributing] before adding a relocation type,
instrumentation profile, or trace format.

## License

CC0-1.0. Third-party tools and user-supplied inputs keep their own terms.

[campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/campaigns.md
[compiler-instrumentation]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/compiler-instrumentation.md
[tooling-roadmap]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/tooling-roadmap.md
[contributing]: https://github.com/akratch/n64-decomp-workbench/blob/main/CONTRIBUTING.md
[cv64-examples]: https://github.com/akratch/n64-decomp-workbench/blob/main/examples/cv64/README.md
[documentation]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/README.md
[ido-support]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/ido-support.md
[object-comparison]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/object-comparison.md
[final-function-campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/final-function-campaigns.md
[pass-replay]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/pass-replay.md
[principles]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/principles.md
[scratch-bundles]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/scratch-bundles.md
[trace-analysis]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/trace-analysis.md
[troubleshooting]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/troubleshooting.md
[workflows]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/workflows.md
