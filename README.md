# N64 Decomp Workbench

Small, composable tools for the point where a decompilation is structurally
close but compiler behavior is still deciding the last instructions.

The workbench grew out of the final matching work on four large or stubborn
Diddy Kong Racing (DKR) functions. This standalone repository keeps the
reusable parts: relocation-aware comparison, repeatable candidate campaigns,
compiler trace analysis, guarded static-recomp instrumentation, and
retained-pass replay. The DKR-specific material is presented as worked
examples rather than as general rules about IDO or proof of the historical
source.

The repository contains no ROMs, extracted target objects, proprietary
compiler binaries, or complete copied translation units.

## Where it fits

Most of the workbench is project- and compiler-independent:

- `compare`, `compare-dumps`, ranking, and campaigns work with MIPS objects
  and GNU-compatible objdump output.
- Trace parsers consume documented text formats and can be fed by any compiler
  instrumentation that emits them.
- FIFO reconstruction models observed allocation events without assuming IDO.
- Pass replay invokes caller-supplied assembler stages and produces an object
  for comparison.

The `instrument-uopt*` commands are deliberately narrower. They patch generated
`uopt.c` from one pinned IDO 5.3 static-recomp revision, check its SHA-256 and
anchors, and refuse unknown input by default. Generic `ugen.c` call/free-list
hooks are available separately. The workbench does not include a compiler,
binutils, a ROM, or a game build system.

## Choose your workflow

| I want to… | Start with |
|---|---|
| Evaluate the package without an N64 toolchain | [Five-minute tour](#five-minute-tour) |
| Prove whether two MIPS objects match | [Object-matcher workflow][workflows-object] |
| Search and rank many source candidates | [Campaign-author workflow][workflows-campaign] |
| Investigate a register-allocation plateau | [Allocator workflow][workflows-allocator] |
| Isolate a late compiler-pass decision | [Pass-boundary workflow][workflows-pass] |
| Add guarded traces to static-recompiled IDO | [IDO instrumentation workflow][workflows-ido] |
| Adapt the package to another project or compiler | [Maintainer workflow][workflows-maintainer] |
| Diagnose an error or empty result | [Troubleshooting][troubleshooting] |

The complete [developer workflows][workflows] state prerequisites, expected
outputs, and stopping points. The [four DKR case studies](#worked-examples)
show the evidence behind the techniques; the [scope guide][scope-and-claims]
separates those observations from broader claims.

Reference material:

- Operation: [object comparison][object-comparison],
  [campaigns][campaigns], [trace analysis][trace-analysis],
  [pass replay][pass-replay], and
  [compiler instrumentation][compiler-instrumentation].
- Evidence: [historical tooling inventory][historical-inventory],
  [lessons learned][lessons-learned], [provenance][provenance], and the
  [0.2.0 validation record][validation-record].
- Project: [changelog][changelog], [contributing](CONTRIBUTING.md), and
  [license][license].

## Install

Python 3.10 or newer is required. The installed package uses only the standard
library.

From a clone of this repository:

```sh
git clone https://github.com/akratch/n64-decomp-workbench.git
cd n64-decomp-workbench
python3 -m pip install -e .
decomp-workbench --help
```

After a PyPI release, the package can instead be installed with
`python3 -m pip install n64-decomp-workbench`.

To work on the package:

```sh
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
Exit-code meanings and common toolchain failures are collected in
[Troubleshooting][troubleshooting].

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
docs/workflows.md           end-to-end developer journeys
docs/troubleshooting.md     failure modes and issue-report checklist
docs/                       focused guides, evidence, and reference
research-archive/           index to preserved raw experiments
.github/workflows/ci.yml    release-equivalent continuous integration
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

Version 0.2.0 supersedes the initial `v0.1.0` snapshot. The
relocation comparator, campaign preparation, trace parsers, FIFO model,
listing mutation, and instrumentation anchor checks have synthetic tests.
Actual IDO and whole-ROM fidelity checks require user-supplied toolchain and
game inputs and are therefore documented integration gates, not claims made by
the redistributable unit suite.

## License

Original workbench code, fixtures, and documentation are dedicated to the
public domain under [CC0 1.0 Universal][license]. Third-party tools and
user-supplied compiler or game inputs retain their own terms.

[campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/campaigns.md
[changelog]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/CHANGELOG.md
[compiler-instrumentation]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/compiler-instrumentation.md
[historical-inventory]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/historical-tooling-inventory.md
[license]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/LICENSE.md
[lessons-learned]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/lessons-learned.md
[menu-case]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/case-studies/menu-pass-replay.md
[object-comparison]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/object-comparison.md
[objects-case]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/case-studies/objects-structural-score.md
[pass-replay]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/pass-replay.md
[provenance]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/provenance.md
[racer-case]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/case-studies/racer-fifo.md
[research-archive]: https://github.com/akratch/Diddy-Kong-Racing/tree/archive/decomp-research-2026-07-26
[scope-and-claims]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/scope-and-claims.md
[trace-analysis]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/trace-analysis.md
[trackbg-case]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/case-studies/trackbg-globalcolor.md
[troubleshooting]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/troubleshooting.md
[validation-record]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/validation-0.2.0.md
[workflows]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md
[workflows-allocator]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#4-investigate-a-register-allocation-plateau
[workflows-campaign]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#3-run-a-reproducible-candidate-campaign
[workflows-ido]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#6-instrument-the-pinned-ido-53-static-recompile
[workflows-maintainer]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#7-adapt-or-maintain-the-workbench
[workflows-object]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#2-diagnose-a-late-stage-object-mismatch
[workflows-pass]: https://github.com/akratch/n64-decomp-workbench/blob/v0.2.0/docs/workflows.md#5-test-a-pass-boundary-hypothesis
