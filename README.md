# N64 Decomp Workbench

[![CI](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/akratch/n64-decomp-workbench/actions/workflows/ci.yml)

Find the cause of late-stage MIPS decompilation mismatches.

![One diagnose run on a shipped fixture: the verdict, the register lanes with
the divergence caret, the aligned hunk with per-web colored substitutions, the
webs table, and the next-steps footer naming the field-guide levers to try.](docs/assets/diagnose-phase-shift.svg)

*Real output — `decomp-workbench diagnose-dumps` on the phase-shift fixture in
this repository. [From verdict to edit](docs/from-verdict-to-edit.md) walks
this exact screen from top to bottom.*

## You have an almost-matched function. Now what?

**→ Read [docs/START_HERE.md](docs/START_HERE.md).** A short guided tour,
with every command runnable right now against fixtures in this repository — no
ROM, no compiler, no toolchain, no AI.

It answers the three questions people actually arrive with:

- *Do I need to isolate the function so asm-processor (the community
  preprocessor that lets hand-written MIPS assembly live inside C) stays
  out of it?* **No.**
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
| [Start here](docs/START_HERE.md) | One function, guided tour: diagnose → lever → repeat |
| [Field guide](docs/field-guide.md) | "The diff looks like X" → the C that moves it, with the measured effect |
| [Backlog walkthrough](docs/walkthrough-30-near-matches.md) | Thirty near matches: batch triage, and which classes to knock out first |

**Already at 100%?** Then your question is a different one — whether the
addresses in that matched ROM are *references*, so code and data can be
inserted, removed or resized without a hardcoded pointer quietly surviving the
move. Start at [the shiftability campaign](docs/shiftability-campaign.md): five
phases, the first two of which need only a linker map and a linked image, no
build. [Shiftability](docs/shiftability.md) is the reference beside it.

Everything below is reference.

## Try it in 60 seconds

Install from a checkout (Python 3.10 or newer; Python 3.10 installs one small
TOML compatibility dependency). For a standalone command, `pipx` keeps the
workbench isolated from system Python as recommended by the
[Python Packaging User Guide](https://packaging.python.org/en/latest/guides/installing-stand-alone-command-line-tools/):

```sh
git clone https://github.com/akratch/n64-decomp-workbench.git
cd n64-decomp-workbench
pipx install .
```

Or, inside an activated virtual environment:

```sh
python3 -m pip install .
```

Compare two fixture dumps whose raw words differ only in relocated fields:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
```

```text
verdict=instruction-exact aligned_total=   0 words=   0 raw=   2 opcodes=   0 gaps=   0 reloc_syms=   0 norm=   0 ...
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
- a sweep needs row/function-scoped signals, baseline/differential controls,
  honest coverage, or a fresh auditable finish receipt;
- the instruction shape matches but register allocation does not;
- a function already matches and you want to remove fake-match machinery
  without losing exactness;
- you need to test whether uopt, ugen, or as1 (IDO's optimizer, code
  generator, and final assembler pass) owns a difference;
- your project is 100% matched and you need to know whether it is safe to
  shift, insert, or resize code and data without a hardcoded address quietly
  surviving the move.

You do not need a ROM or compiler to try the included fixtures. Real object
comparison needs a GNU-compatible MIPS objdump. Compiler tracing and pass replay
need binaries supplied by your project.

## Use it in a decomp project

Preview a portable project config, then write it only after the inferred and
explicit inputs look right:

```sh
decomp-workbench project init . \
  --target target.o --candidate candidate.o \
  --symbol function_name
# After reviewing the preview:
decomp-workbench project init . \
  --target target.o --candidate candidate.o \
  --symbol function_name --write
decomp-workbench project diagnose
```

Discovery recognizes objdiff, Splat, and common build metadata but refuses to
guess which of many objects is authoritative. See [project
configuration](docs/project-configuration.md).
The same file can hold an explicit compile-one argv, sealed environment, and
frontend/backend lineage for `project campaign candidates/*.c`; no generic
Makefile is guessed into an executable campaign.

Compare one function out of your normal full-translation-unit build, or get
exactness, mechanism, and the next lever in one invocation:

```sh
decomp-workbench compare target.o candidate.o --function function_name \
  --objdump /path/to/mips64-elf-objdump --show-diff
decomp-workbench diagnose target.o candidate.o --function function_name \
  --objdump /path/to/mips64-elf-objdump
```

![The same diagnosis as a self-contained HTML report: sticky verdict bar with
an aligned-identity chip, register lanes with the divergent slot outlined,
annotated hunks, and a webs table linking each substitution to the hunks it
explains.](docs/assets/html-report.png)

*`diagnose --html report.html` carries the same evidence — no scripts, no
network, one file you can attach to a PR or a Discord thread.*

As the work deepens, one command family per stage of a real campaign:

- `public-match-check` — before starting a function at all, ask whether
  decomp.me already has a verified match. Bind on the target's address and
  size, not its name. See [gate 0][public-match-check].
- `campaign target.o candidates/*.c --compile-command ...` — run hundreds of
  source variants through your own compile wrapper, with caching, an
  append-only ledger, controls, and a fresh auditable finish receipt. See
  [candidate campaigns][campaigns].
- `check-scratch`, `fetch-scratch`, `bundle-scratch` — validate, download,
  and package decomp.me exports without guessing at context. See
  [checking decomp.me exports][decompme-exports]. `public-match-check` and
  `fetch-scratch` are the only two commands that ever open a network
  connection; both are read-only and neither ever runs implicitly.
- `object collateral` — an exact function is only the first gate; compare the
  containing objects for `.bss`, GP-table, symbol, relocation, or
  neighboring-code collateral. See [object comparison][object-comparison].
- `shift audit`, `shift rehearse` — a matched build proves the bytes at one
  layout, not that its addresses survive a resize. In one live gate, a
  hardcoded pointer that passed the project's own retail verifier was
  convicted by `shift rehearse`, by name. See [shiftability][shiftability]
  and [the shiftability campaign][shiftability-campaign].
- `handoff audit` — before publishing a proof repository, check that every
  local dependency actually travels. See
  [public handoff audits][public-handoffs].
- `install-skill codex|claude` — an optional agent skill that runs the same
  commands you would.

## Pick the next diagnostic

| What the comparison says | Next move |
|---|---|
| `structure-mismatch` | Keep working at the C/control-flow level |
| `constant-mismatch` | Audit the flag/enum against the assembly, then re-derive fakes |
| `commutative-order` | Change the expression tree (`x \|= y`), not the allocator |
| `schedule-mismatch` | Regroup statements; use `-g0` to locate ownership, not to prove the C |
| `allocation-mismatch` | Run `view` to name the family, then `decomp-workbench guide <playbook>` |
| `relocation-layout-mismatch` | Check relocation metadata, then the project link/ROM check |
| `exact=true` | Run the project’s normal collateral and full-output verification |

Whatever the verdict, `--show-diff` prints every differing site: no verdict
suppresses evidence. [The field guide](docs/field-guide.md) turns each of these
rows into the C that moves it, `decomp-workbench guide <playbook|verdict|lever>`
prints the relevant part of it in the terminal, and [from verdict to
edit](docs/from-verdict-to-edit.md) walks one case end to end.

## Command reference

Run `decomp-workbench commands` for the annotated map of every command,
grouped by journey (`object`, `scratch`, `trace`, `probe`, `sweep`,
`campaign`, `shift`, ...), or `decomp-workbench --help` for the flat list.
Two conventions hold everywhere:

- On every command that selects one function, `--symbol` and `--function` are
  the same option, and passing both with different values is refused rather
  than silently resolved.
- Every printed label is also the JSON key for that value;
  `decomp-workbench --explain-keys` prints the one registry of comparison,
  campaign, and aligned-view keys.

The name shapes — a bare verb reads objects, `trace-*` reads a compiler log,
`probe-*` reads your C source, `sweep <verb>` writes a family of variants —
are explained in [Choose a workflow](docs/workflows.md#command-names).
`decomp-workbench completion bash|zsh|fish|powershell` prints a completion
script.

## Documentation

- [Start here][start-here] — an almost-matched function, end to end
- [Field guide][field-guide] — the IDO codegen levers, with the C
- [Backlog walkthrough][walkthrough] — thirty near matches, in triage order
- [Documentation index][documentation] — every guide, with inputs, outputs,
  and reading order

## Support boundary

Comparison, ranking, campaigns, scratch bundling, trace parsing, and pass
replay are adapters: bring your own object files, objdump, compiler wrapper,
scratch inputs, traces, or pass binaries. These workflows support explicit
IRIX 4.x frontend cells and IDO 5.3/7.1 pipelines when the project supplies the
corresponding toolchain; instrumentation remains profile-specific. See the
[IDO support matrix][ido-support].

The packaged uopt patch profiles are intentionally narrower. They accept
generated `uopt.c` from one pinned IDO 5.3 static-recomp revision, verify its
SHA-256 and source anchors, and reject unknown input by default. The generic
ugen instrumenter supports a broader but shallower call/free-list trace.

The repository contains no ROMs, target objects, proprietary compiler
binaries, generated third-party contexts, extracted target assembly, or game
assets. The [CV64 campaign record](examples/cv64/README.md) retains aggregate
measurements and a local regeneration recipe, while the uncleared scratch
payloads remain excluded as recorded by its
[notice](examples/cv64/NOTICE.md).

## Development

```sh
python3 -m pip install -e ".[dev]"
python3 -m unittest discover -s tests -v
bandit -r src -ll
codespell README.md CHANGELOG.md CONTRIBUTING.md docs examples src tests
ruff check src tests
ruff format --check src tests
mypy src tests
```

The test runner is `unittest`, not pytest. pytest is not part of the dev
extras; `uv run pytest` fails with collection errors unless you first run
`pip install -e ".[dev]" pytest`.

See [CONTRIBUTING.md][contributing] before adding a relocation type,
instrumentation profile, or trace format.

## License

CC0-1.0. Third-party tools and user-supplied inputs keep their own terms.

[start-here]: docs/START_HERE.md
[field-guide]: docs/field-guide.md
[walkthrough]: docs/walkthrough-30-near-matches.md
[documentation]: docs/README.md
[campaigns]: docs/campaigns.md
[public-match-check]: docs/public-match-check.md
[decompme-exports]: docs/decompme-exports.md
[object-comparison]: docs/object-comparison.md
[shiftability]: docs/shiftability.md
[shiftability-campaign]: docs/shiftability-campaign.md
[public-handoffs]: docs/public-handoffs.md
[ido-support]: docs/ido-support.md
[contributing]: CONTRIBUTING.md
