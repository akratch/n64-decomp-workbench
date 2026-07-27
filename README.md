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
| Check whether two MIPS objects match | [Object comparison](docs/object-comparison.md) |
| Explore the included fixtures without a toolchain | [Five-minute tour](#five-minute-tour) |
| Compile and rank many source candidates | [Campaigns](docs/campaigns.md) |
| Understand a register-only mismatch | [Trace analysis](docs/trace-analysis.md) |
| See why tracing uopt helped in practice | [Track renderer example](case-studies/trackbg-globalcolor.md) |
| Reconstruct a temp-register FIFO | [Plane physics example](case-studies/racer-fifo.md) |
| Inspect or perturb the ugen→as1 boundary | [Menu example](case-studies/menu-pass-replay.md) |
| Instrument a static recompile of IDO | [Compiler instrumentation](docs/compiler-instrumentation.md) |
| Browse everything evaluated for extraction | [Historical tooling inventory](docs/historical-tooling-inventory.md) |
| Understand what “exact” does and does not mean | [Scope and claims](docs/scope-and-claims.md) |
| Find the origin of an included technique | [Provenance](docs/provenance.md) |
| See release-level changes | [Changelog](CHANGELOG.md) |

## Install

Python 3.10 or newer is required. The core package uses only the standard
library.

```sh
cd tools/decomp-workbench
python3 -m pip install -e .
decomp-workbench --help
```

Run the test suite:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
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

1. [Globalcolor tracing exposed an expression-order tie](case-studies/trackbg-globalcolor.md).
2. [Penalty buckets prevented a useful candidate from being discarded](case-studies/objects-structural-score.md).
3. [A physical register trace became a logical event schedule](case-studies/racer-fifo.md).
4. [Pass replay identified one missing `.noalias` directive](case-studies/menu-pass-replay.md).

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
`archive/decomp-research-2026-07-26`. It is intentionally not mixed into the
public API.

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
and refuses other source by default. See
[compiler instrumentation](docs/compiler-instrumentation.md) for the exact
upstream revision and validation checklist.

## Project status

This branch is the curated successor to `decomp-workbench-v0.1.0`. The
relocation comparator, campaign preparation, trace parsers, FIFO model,
listing mutation, and instrumentation anchor checks have synthetic tests.
Actual IDO and whole-ROM fidelity checks require user-supplied toolchain and
game inputs and are therefore documented integration gates, not claims made by
the redistributable unit suite.

## License

Original workbench code, fixtures, and documentation are dedicated to the
public domain under [CC0 1.0 Universal](LICENSE.md). Third-party tools and
user-supplied compiler or game inputs retain their own terms.
