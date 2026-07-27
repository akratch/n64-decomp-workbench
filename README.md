# N64 Decomp Workbench

Small, composable tools for the point where a decompilation is structurally
close but compiler behavior is still deciding the last instructions.

The workbench grew out of the final matching work on four large or stubborn
Diddy Kong Racing functions. The public package keeps the reusable parts:
relocation-aware comparison, repeatable candidate campaigns, compiler trace
analysis, guarded static-recomp instrumentation, and retained-pass replay.
The DKR-specific material is presented as worked examples rather than as
general rules about IDO or proof of the historical source.

The repository contains no ROMs, extracted target objects, proprietary
compiler binaries, or complete copied translation units.

## Start here

| I want to… | Start with |
|---|---|
| Check whether two MIPS objects match | [Object comparison][object-comparison] |
| Explore the included fixtures without a toolchain | [Five-minute tour](#five-minute-tour) |
| Compile and rank many source candidates | [Campaigns][campaigns] |
| Understand a register-only mismatch | [Trace analysis][trace-analysis] |
| See why tracing uopt helped in practice | [Track renderer example][trackbg-case] |
| Reconstruct a temp-register FIFO | [Plane physics example][racer-case] |
| Inspect or perturb the ugen→as1 boundary | [Menu example][menu-case] |
| Instrument a static recompile of IDO | [Compiler instrumentation][compiler-instrumentation] |
| Browse everything evaluated for extraction | [Historical tooling inventory][historical-inventory] |
| Review the practices supported by the four investigations | [Lessons learned][lessons-learned] |
| Inspect the checks run for this release | [Validation record][validation-record] |
| Understand what “exact” does and does not mean | [Scope and claims][scope-and-claims] |
| Find the origin of an included technique | [Provenance][provenance] |
| See release-level changes | [Changelog][changelog] |

## Install

Python 3.10 or newer is required. The installed package uses only the standard
library.

From a DKR source checkout:

```sh
python3 -m pip install -e tools/decomp-workbench
decomp-workbench --help
```

After a PyPI release, the package can instead be installed with
`python3 -m pip install n64-decomp-workbench`.

To work on the package:

```sh
cd tools/decomp-workbench
python3 -m pip install -e ".[dev]"
PYTHONPATH=src python3 -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
mypy src tests
```

## Five-minute tour

These examples use retained text fixtures and synthetic traces, so they do not
require a ROM, IDO, or MIPS binutils.

### 1. Compare two relocated instruction streams

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

The raw words differ in a `jal` target and a `lui` immediate, but both fields
have matching relocation records. The workbench masks only the
linker-controlled bits and reports `words=0 raw=2`.

Now expose a real register difference:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/register-mismatch.objdump \
  --show-diff
```

This reports one word, normalized, register, and FP-register mismatch.

### 2. Replay a traced temp-register FIFO

```sh
decomp-workbench trace-fifo examples/traces/ugen-fifo.log \
  --registers t6,t7,t8 \
  --show-events \
  --fail-on-violation
```

Leading append events seed the queue. The report checks every later allocation
against the FIFO head and assigns stable logical value identities (`v1`,
`v2`, …) to the physical register events.

### 3. Rank globalcolor live ranges

```sh
decomp-workbench trace-globalcolor \
  examples/traces/globalcolor.log \
  --dtype 13
```

This parses the retained `CSAVE`/`CUP` format and the later `[CDX]` records
emitted by the included profile. The historical field name `unk1C` is
presented as `weight`; the raw value is retained and the documentation does
not claim a broader semantic interpretation than the experiments established.

### 4. Inspect alias decisions

```sh
decomp-workbench trace-alias \
  examples/traces/alias.log \
  --show-queries
```

This separates retained, direct, and fresh base paths and summarizes the
descriptor types and outcomes of each observed alias query. The fixture is
synthetic; the field names mirror the pinned instrumentation profile.

## Command map

| Command | Purpose |
|---|---|
| `compare` | Disassemble and compare two objects |
| `compare-dumps` | Compare redistributable GNU objdump text |
| `rank` | Rank prebuilt candidate objects |
| `compile-rank` | Simple sequential compile-and-rank loop |
| `campaign` | Parallel compilation with caching and a JSONL ledger |
| `trace-summary` | Count events, registers, and source lines |
| `trace-alias` | Summarize uopt base provenance and alias decisions |
| `trace-fifo` | Validate and reconstruct a FIFO register class |
| `trace-globalcolor` | Summarize uopt allocation costs and decisions |
| `instrument-ugen` | Add opt-in call/free-list hooks to generated `ugen.c` |
| `instrument-uopt` | Compose compatible pinned uopt profiles |
| `instrument-uopt-globalcolor` | Apply the hash-pinned IDO 5.3 uopt profile |
| `instrument-uopt-alias` | Apply the hash-pinned alias trace profile |
| `replay-as1` | Edit a retained ugen listing and rerun as0/as1 |

Every reporting command supports JSON where machine-readable output is useful.
Compiler commands are tokenized with `shlex` and run without a shell.

## How the pieces fit

```text
source candidates
       │
       ▼
 campaign ──────► candidate objects ──────► compare / asm-differ
                                                │
                         structural plateau ────┘
                                                ▼
                                      uopt / ugen traces
                                      │       │       │
                                      ▼       ▼       ▼
                                  coloring  aliases  FIFO replay
                                      │       │       │
                                      └───────┼───────┘
                                              ▼
                                    focused source change

retained ugen listing ──► replay-as1 ──► causal pass-boundary experiment
```

The intended workflow is to use the least invasive oracle that answers the
current question. Compiler modification is a late diagnostic step, not the
default matching technique.

## Worked examples

The case studies emphasize the tool and the evidence it exposed:

1. [Globalcolor tracing exposed an expression-order tie][trackbg-case].
2. [Penalty buckets prevented a useful candidate from being discarded][objects-case].
3. [A physical register trace became a logical event schedule][racer-case].
4. [Pass replay identified one missing `.noalias` directive][menu-case].

Each example separates observed facts, the diagnostic intervention, the
source change that eventually matched, and the limits of the conclusion.

## Repository map

```text
src/decomp_workbench/       installable Python package
tests/                      standard-library unit tests
examples/fixtures/          redistributable objdump text
examples/traces/            small synthetic trace fixtures
case-studies/               four DKR worked examples
docs/                       task-oriented guides and reference
research-archive/           index to preserved raw experiments
```

The large historical campaign—hundreds of variants, reports, and
function-specific scripts—remains available on the DKR Git branch
[`archive/decomp-research-2026-07-26`][research-archive]. It is intentionally
not mixed into the public API.

## Instrumentation safety

Tracing a compiler can perturb the compiler. Treat this as a testable property,
not an assumption:

1. Build the unmodified pass and the instrumented pass.
2. Run both with every workbench environment variable unset.
3. Compare the target object, already-matching collateral objects, and the
   complete ROM or binary.
4. Enable one known trace as a positive control.
5. Use behavior-changing controls such as `CDX_FORCE` only as causal probes.

The uopt profile is pinned to the SHA-256 of one generated IDO 5.3 `uopt.c`
and refuses other source by default. See the
[compiler instrumentation][compiler-instrumentation] guide for the exact
upstream revision and validation checklist.

## Project status

Version 0.2.0 supersedes the initial `decomp-workbench-v0.1.0` snapshot. The
relocation comparator, campaign preparation, trace parsers, FIFO model,
listing mutation, and instrumentation anchor checks have synthetic tests.
Actual IDO and whole-ROM fidelity checks require user-supplied toolchain and
game inputs and are therefore documented integration gates, not claims made by
the redistributable unit suite.

## License

Original workbench code, fixtures, and documentation are dedicated to the
public domain under [CC0 1.0 Universal][license]. Third-party tools and
user-supplied compiler or game inputs retain their own terms.

[campaigns]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/campaigns.md
[changelog]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/CHANGELOG.md
[compiler-instrumentation]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/compiler-instrumentation.md
[historical-inventory]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/historical-tooling-inventory.md
[license]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/LICENSE.md
[lessons-learned]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/lessons-learned.md
[menu-case]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/case-studies/menu-pass-replay.md
[object-comparison]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/object-comparison.md
[objects-case]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/case-studies/objects-structural-score.md
[provenance]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/provenance.md
[racer-case]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/case-studies/racer-fifo.md
[research-archive]: https://github.com/akratch/Diddy-Kong-Racing/tree/archive/decomp-research-2026-07-26
[scope-and-claims]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/scope-and-claims.md
[trace-analysis]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/trace-analysis.md
[trackbg-case]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/case-studies/trackbg-globalcolor.md
[validation-record]: https://github.com/akratch/Diddy-Kong-Racing/blob/decomp-workbench-v0.2.0/tools/decomp-workbench/docs/validation-0.2.0.md
