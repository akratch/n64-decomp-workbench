# N64 Decomp Workbench

[![CI](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml)

Find the cause of late-stage MIPS decompilation mismatches.

## You have an almost-matched function. Now what?

**→ Read [docs/START_HERE.md](docs/START_HERE.md).** Ten minutes, in order,
with every command runnable right now against fixtures in this repository — no
ROM, no compiler, no toolchain, no AI.

It answers the three questions people actually arrive with:

- *Do I need to isolate the function so asm-processor stays out of it?* **No.**
  Compare your normal full-TU build against the expected object; `--function`
  scopes it. Isolation changes codegen, so a harness is the wrong ground truth.
- *Do I need a permuter or an agent to use this?* **No.** The verdict names the
  mechanism, the `next:` footer names the lever, and the field guide gives you
  the C. The permuter is optional, and it is a hypothesis generator rather than
  a solver.
- *Am I supposed to read `trace.lst`?* **Not yet, and probably not at all.**
  Traces are the last resort for one verdict class, and only if your project
  built an instrumented compiler.

Three pages are the entire workflow:

| Page | What it is for |
|---|---|
| [Start here](docs/START_HERE.md) | One function, ten minutes: diagnose → lever → repeat |
| [Field guide](docs/field-guide.md) | "The diff looks like X" → the C that moves it, with the measured effect |
| [Backlog walkthrough](docs/walkthrough-30-near-matches.md) | Thirty near matches: batch triage, and which classes to knock out first |

Everything below is reference.

## Try it in 60 seconds

Install (Python 3.10 or newer, no runtime dependencies):

```sh
git clone https://github.com/akratch/n64-decomp-workbench.git
cd n64-decomp-workbench
python3 -m pip install -e .
```

Compare two fixture dumps whose raw words differ only in relocated fields:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

```text
verdict=instruction-exact aligned_total=   0 words=   0 raw=   2 norm=   0 ...
raw difference classes: relocation_controlled=2
next: Instruction-exact: raw differences are linker-controlled relocation fields ...
```

`words=0` is the relocation-aware result. `raw=2` shows why a literal word
comparison would have rejected the candidate.

Now diagnose a real residual—exactness and mechanism in one load, ending in a
lever:

```sh
decomp-workbench diagnose-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep
```

```text
verdict: phase-shift  structural=0 schedule=0 register=6 constant=0 hunks=1 playbook=temp-fifo-phase
signature: prefix-exact@12 state-divergence@temp:5 register-first-divergence
```

Six register differences, one upstream cause. [Start
here](docs/START_HERE.md#minutes-4-6--run-view-and-read-the-four-sections)
walks the rest of that screen.

## Is this for me?

Use it when:

- your candidate is close, but the remaining mismatch is hard to classify;
- you are compiling many source variants and need caching plus a durable ledger;
- the instruction shape matches but register allocation does not;
- you need to test whether uopt, ugen, or as1 owns a difference.

You do not need a ROM or compiler to try the included fixtures. Real object
comparison needs a GNU-compatible MIPS objdump. Compiler tracing and pass replay
need binaries supplied by your project.

## Use it in a decomp project

Compare one function, out of your normal full-translation-unit build:

```sh
decomp-workbench compare target.o candidate.o \
  --function function_name \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

Diagnose exactness and the mechanism behind the residual in one invocation:

```sh
decomp-workbench diagnose target.o candidate.o \
  --function function_name \
  --objdump /path/to/mips64-elf-objdump
```

`compare` and `view` remain composable primitives; `diagnose` loads each input
once and renders both truths together. Add `--show-all` for every hunk or
`--html report.html` for a self-contained handoff.

Run generated source variants through your existing compile wrapper. Each
`{source}` is a full translation unit, compiled the way your project compiles
one file:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --function function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --jobs 8
```

The command template is tokenized and executed without a shell. Every ledger
record includes source, target, wrapper, objdump, explicit environment, timing,
and comparison identity. The campaign stops at the first exact match unless
`--no-stop-on-exact` asks for the whole grid, compares in process, and
terminates the compilers it started (and their children) if it is interrupted
or one exceeds the 120-second default `--timeout`.

The manifest and append-only ledger are created by default under
`.decomp-workbench/campaigns/`. Reopen the cockpit without rebuilding:

```sh
decomp-workbench campaign status
decomp-workbench campaign note "the padding macro's line layout is the active hypothesis"
decomp-workbench campaign resume
decomp-workbench campaign export --output campaign-report.html
```

External generators can attach a validated family/parameter sidecar with
`--experiment-manifest`; selected instruction regions are ranked before the
whole-function residual. See [candidate campaigns][campaigns].

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

Downloaded a decomp.me ZIP? Validate it and compare the site's own target and
current objects before trying another source edit:

```sh
decomp-workbench doctor "/path/to/scratch.zip"
decomp-workbench check-scratch "/path/to/scratch.zip" \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

`check-scratch` prints the browser score as context, then reports the
relocation-aware, LCS-aligned truth. With `--compile-command`, it composes
`ctx.c`, decomp.me's `#line 1 "src.c"` reset, and the candidate source before
compiling, eliminating a subtle source-line mismatch that can change IDO's
`-g3` schedule. See [the export tutorial][decompme-exports].

Install the campaign skill for your preferred agent — optional, and it runs the
same commands you would:

```sh
decomp-workbench install-skill codex
# or
decomp-workbench install-skill claude
```

## Pick the next diagnostic

| What the comparison says | Next move |
|---|---|
| `structure-mismatch` | Keep working at the C/control-flow level |
| `constant-mismatch` | Audit the flag/enum against the assembly, then re-derive fakes |
| `commutative-order` | Change the expression tree (`x \|= y`), not the allocator |
| `schedule-mismatch` | Regroup statements; use `-g0` to locate ownership, not to prove the C |
| `allocation-mismatch` | Run `view`, then the pool/temp levers in the field guide |
| `relocation-layout-mismatch` | Check relocation metadata, then the project link/ROM check |
| `exact=true` | Run the project’s normal collateral and full-output verification |

Whatever the verdict, `--show-diff` prints every differing site: no verdict
suppresses evidence. [The field guide](docs/field-guide.md) turns each of these
rows into the C that moves it.

## Command reference

| Problem | Command | Output |
|---|---|---|
| Are these objects instruction-exact? | `compare` | Relocation-aware verdict, mismatch counts, register ranges, JSON |
| Can I share the comparison without sharing objects? | `compare-dumps` | The same report from reduced objdump text |
| Can one command tell me exactness, mechanism, and the next lever? | `diagnose`, `diagnose-dumps` | Comparison plus decisive aligned evidence, one input load |
| Where does the divergence begin, and which mechanism owns it? | `view`, `view-dumps` | LCS-aligned hunks, register lanes, prefix signature, lever guidance |
| Is this machine ready, and is this scratch valid? | `doctor` | Environment capabilities, handoff integrity, exact next command |
| Does this downloaded scratch really match? | `check-scratch` | Browser score context, aligned object truth, optional site-faithful recompile |
| Which candidate is closest? | `rank` | Stable structural and exact ranking |
| How do I run and reopen hundreds of variants safely? | `campaign`, `campaign status/resume/export` | Parallel builds, cache, durable state, trajectory and HTML |
| How do I describe a generated family? | `experiment validate` | Parameter/path/grid validation and selected-region contract |
| How do I manage the object cache? | `cache status/prune/restore` | Dry-run cleanup and recoverable trash |
| What events are present in this trace? | `trace-summary` | Event, register, and source-line counts |
| Is temp-register reuse following a FIFO? | `trace-fifo` | Validated queue and physical-to-logical value schedule |
| Why did uopt keep or split a live range? | `trace-globalcolor` | Per-web costs and color/split decisions, filterable by procedure |
| Which source/listing line owns a traced web? | `trace-source` | Marker-aware correlation with ambiguity preserved |
| Can a measured allocator choice close the residual? | `oracle plan/force/sweep` | Calibrated causal evidence, persistent status and export |
| Which alias facts reached uopt? | `trace-alias` | Base provenance and may-alias decisions |
| Would one late-pass edit explain the object? | `replay-as1` | A rebuilt object from an edited retained listing |
| Can I hand this function to decomp.me without uploading it? | `bundle-scratch` | Target, context, source, settings, and checksums |
| Can an agent follow the proven campaign method? | `install-skill` | Portable Codex or Claude Code Agent Skill |
| Can I observe static-recompiled IDO? | `instrument-ugen`, `instrument-uopt` | Instrumented generated C with opt-in traces |

On every command that selects one function — `compare`, `compare-dumps`,
`diagnose`, `diagnose-dumps`, `view`, `view-dumps`, `check-scratch`, `rank`,
`compile-rank`, `campaign` —
`--symbol` and `--function` are the same option, so either vocabulary works,
and passing both with different values is refused rather than silently
resolved. Every printed label is also the JSON key for that value;
`decomp-workbench --explain-keys` prints the one registry of comparison,
campaign, and aligned-view keys.

Run `decomp-workbench commands` for the compact journey map or
`decomp-workbench completion bash|zsh|fish|powershell` for a generated
completion script. Grouped spellings such as `object diagnose`,
`campaign status`, and `trace source` coexist with established flat commands.

## All documentation

The three narrative pages first, then the focused guides:

- [Start here][start-here] — an almost-matched function, end to end
- [Field guide][field-guide] — the IDO codegen levers, with the C
- [Backlog walkthrough][walkthrough] — thirty near matches, in triage order
- [Workflow selection][workflows]
- [Object comparison][object-comparison]
- [Aligned mechanism view][view]
- [Candidate campaigns][campaigns]
- [Calibrated allocator oracle][oracle]
- [External toolchains and calibration][toolchain-calibration]
- [JSON and automation contracts][json-contracts]
- [Current product status and intentional boundaries][product-status]
- [Checking decomp.me exports][decompme-exports]
- [Scratch bundles][scratch-bundles]
- [Lessons from final-function campaigns][final-function-campaigns]
- [Portable Codex and Claude Code skill][agent-skill]
- [IDO version support][ido-support]
- [Trace analysis][trace-analysis]
- [Compiler instrumentation][compiler-instrumentation]
- [Pass replay][pass-replay]
- [Tooling roadmap from live campaigns][tooling-roadmap]
- [Elite product review and scoped backlog][elite-product-review]
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

[start-here]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/START_HERE.md
[field-guide]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/field-guide.md
[walkthrough]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/walkthrough-30-near-matches.md
[view]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/view.md
[campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/campaigns.md
[decompme-exports]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/decompme-exports.md
[agent-skill]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/agent-skill.md
[compiler-instrumentation]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/compiler-instrumentation.md
[tooling-roadmap]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/tooling-roadmap.md
[elite-product-review]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/elite-product-review-2026-07-29.md
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
[oracle]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/oracle.md
[toolchain-calibration]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/toolchain-calibration.md
[json-contracts]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/json-contracts.md
[product-status]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/product-status.md
