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

After a function matches, inspect suspicious source constructs and compose a
bounded cleanup set instead of hand-editing the accepted source in place:

```sh
decomp-workbench experiment inspect-source candidate.c
decomp-workbench experiment compose cleanup.json cleanup-candidates --dry-run
decomp-workbench experiment compose cleanup.json cleanup-candidates
```

The generated `experiment.json` feeds the normal campaign runner. Exact
function output is still only the first gate; compare the containing objects
for `.bss`, GP-table, symbol, relocation, or neighboring-code collateral:

```sh
decomp-workbench object collateral reference-tu.o candidate-tu.o \
  --function function_name --fail-on-collateral
```

![The same diagnosis as a self-contained HTML report: sticky verdict bar with
an aligned-identity chip, register lanes with the divergent slot outlined,
annotated hunks, and a webs table linking each substitution to the hunks it
explains.](docs/assets/html-report.png)

*The `--html` report carries the same evidence — no scripts, no network, one
file you can attach to a PR or a Discord thread.*

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
decomp.me (the community's browser scratch and match-scoring service)
creation without uploading anything:

```sh
decomp-workbench bundle-scratch scratch/demo \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1 C++' \
  --compiler-id ido7.1_c++ \
  --language C++ \
  --compiler-flags='-O2 -mips2' \
  --diff-label demo
```

Before starting on a function at all, ask whether it is already matched in
public. Family walks miss those matches — they live in unrelated lineages —
and a name lookup misses scratches named after a data label, so bind on the
target's size and search its address too:

```sh
decomp-workbench public-match-check func_800C1A90 --address 0x800C1A90 --instructions 127
```

A `score=0` row with `match_override=false` is a match decomp.me itself
verified; `match_override=true` is one its owner merely declared. See
[gate 0][public-match-check].

Have a slug? Fetch the export once, validated, into the standard layout — a
scratch already on disk is reported rather than downloaded again:

```sh
decomp-workbench fetch-scratch aBcDe --outdir ~/scratches
```

These two are the only commands that open a network connection; both are
read-only and neither ever runs implicitly. `decomp-workbench commands --json`
carries the whole inventory.

Downloaded a decomp.me ZIP? Validate it and compare the site's own target and
current objects before trying another source edit:

```sh
decomp-workbench doctor "/path/to/scratch.zip"
decomp-workbench check-scratch "/path/to/scratch.zip" \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

`check-scratch` prints the browser score as context, then reports the
raw-object score proxy and relocation-aware, LCS-aligned function truth as
separate gates. `--fail-on-mismatch` requires raw instruction identity and
matching relocation symbol/addend targets for a decomp.me export, so a
linker-equivalent relocation spelling cannot masquerade as a 100% site result.
This is a local proxy, not a claim about decomp.me's service. With
`--compile-command`, it composes
`ctx.c`, decomp.me's language-aware `src.c`/`src.cxx` line reset, and the
candidate source before compiling, eliminating a subtle source-line mismatch
that can change IDO's `-g3` schedule. The report keeps preset, canonical
compiler ID, language, frontend, and expected driver distinct. See [the export
tutorial][decompme-exports].

Before publishing a proof or integration repository, check that every local
dependency will actually travel:

```sh
decomp-workbench handoff audit /path/to/public-proof-repo \
  --dependency-root /path/to/game-project
```

This catches missing references and dependencies that exist locally but were
never tracked. See [public handoff audits][public-handoffs].

A matched build proves the bytes at one layout; it says nothing about whether
the addresses in them are references that survive a resize. Inventory a
matched project's pinned and in-image addresses without building anything,
then let a real padded relink referee which ones actually move:

```sh
decomp-workbench shift audit --map build/game.map --image build/game.z64 \
  --elf build/game.elf --pins ver/symbols/undefined_syms.txt --blobs auto
decomp-workbench shift rehearse orchestrate --wrapper tools/relink.sh \
  --ld-script mods/game.custom.ld --anchor-object build/src/hasm/entrypoint.s.o \
  --deltas 0x10,0x40 --workdir .workbench/rehearsal \
  --census unexplained_changed=0,stale_confirmed=0
```

In this campaign's gate, a one-line hardcoded pointer in a 100%-matched
project passed the project's own retail-cartridge verifier and was still
convicted by `shift rehearse`, by name. `shift config verify` gates the linker
edit that gets you there and `shift plan` turns the reports into a finite,
gated queue. See [shiftability][shiftability] for the reference, and
[the shiftability campaign][shiftability-campaign] for the phases in order.

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
| `allocation-mismatch` | Run `view` to name the family, then `decomp-workbench guide <playbook>` |
| `relocation-layout-mismatch` | Check relocation metadata, then the project link/ROM check |
| `exact=true` | Run the project’s normal collateral and full-output verification |

Whatever the verdict, `--show-diff` prints every differing site: no verdict
suppresses evidence. [The field guide](docs/field-guide.md) turns each of these
rows into the C that moves it, `decomp-workbench guide <playbook|verdict|lever>`
prints the relevant part of it in the terminal, and [from verdict to
edit](docs/from-verdict-to-edit.md) walks one case end to end.

## Command reference

| Problem | Command | Output |
|---|---|---|
| How far is this candidate, in one number? | `score` | The positional word delta that is the matching gate, the two other counts labelled with what each is for, and the screen line that identifies a candidate in a sweep column |
| What do I do next? | `next` | The next steps in priority order, each a runnable command with your real paths in it and one sentence saying what it settles |
| Are these objects instruction-exact? | `compare` | Relocation-aware verdict, mismatch counts, register ranges, JSON |
| Can I share the comparison without sharing objects? | `compare-dumps` | The same report from reduced objdump text |
| Can one command tell me exactness, mechanism, and the next lever? | `diagnose`, `diagnose-dumps` | Comparison plus decisive aligned evidence, one input load |
| Where does the divergence begin, and which mechanism owns it? | `view`, `view-dumps` | LCS-aligned hunks, register lanes, prefix signature, lever guidance |
| Is this function already matched in public? | `public-match-check` | Name-, address- and size-anchored search, with site-verified matches and owner-declared claims told apart |
| Can I get that scratch's export without hand-rolling a download? | `fetch-scratch` | One polite, identified, validated fetch into the standard layout, cached on disk |
| Is this machine ready, and is this scratch valid? | `doctor` | Environment capabilities, handoff integrity, exact next command |
| Does this downloaded scratch really match, or only differ from the exact project because of context? | `check-scratch` | Browser score context, independent scratch/project truth, optional site-faithful recompile |
| The footer named a playbook — what is it? | `guide` | The field-guide levers for a playbook, verdict, or lever number |
| The counts differ, so every later row is charged — how far is it really? | `align`, `align-dumps` | The edit script (replaced, inserted, deleted) and the instructions a source change must actually move, instead of what one insertion cost positionally |
| Is this candidate wrong, or the same allocation rotated one register along? | `phase`, `phase-dumps` | Per row slot, the ring coset that would make it match **and** the positional count it really scores, so a rotation is never recorded as a win |
| Which candidate is closest? | `rank` | Stable structural and exact ranking |
| How do I run and reopen hundreds of variants safely? | `campaign`, `campaign status/resume/export/finish` | Controls before scale, parallel builds, cache, coverage/mechanism trajectories, fresh finish receipt |
| How do I describe a generated family? | `experiment validate` | v1 parameter/path/grid provenance or v2 signals, controls, and coverage |
| How do I manage the object cache? | `cache status/prune/restore` | Dry-run cleanup and recoverable trash |
| What events are present in this trace? | `trace-summary` | Event, register, and source-line counts |
| Is temp-register reuse following a FIFO? | `trace-fifo` | Validated queue and physical-to-logical value schedule |
| Why did uopt keep or split a live range? | `trace-globalcolor` | Per-web costs and color/split decisions, filterable by procedure |
| What happened to this one variable, in every round? | `trace-cascade`, `trace-order`, `trace-blocks` | The whole f_split cascade keyed by frame offset, the colour actually taken, the charge each occurrence pays |
| Which source/listing line owns a traced web? | `trace-source` | Marker-aware correlation with ambiguity preserved |
| Can a measured allocator choice close the residual? | `oracle plan/force/sweep` | Calibrated causal evidence, persistent status and export |
| Which alias facts reached uopt? | `trace-alias` | Base provenance and may-alias decisions |
| Does statement line assignment own this schedule, and which line does a statement need? | `probe-lines`, `probe-lines --tie` | Token-identical variants plus a control, scored toward and away from the target |
| Are these two reads of a local the same value? | `probe-equiv` | Same-value ranges from definition placement plus the address-of check, with its limits printed |
| Where can a statement that emits nothing change the allocation? | `probe-deadread` | Candidate positions, the measured spelling table, and one variant source per candidate |
| What would fusing this donor cost? | `slots`, `sweep donors` | Loads, stores and address-takes per stack slot — printed both sp-relative and as the frame offset `trace-cascade` keys a site by; and the locals whose live range avoids the target's |
| What is every lever I inherited actually costing me? | `sweep regress` | The removal lattice with its own control, and a measured price per construct |
| Which locals are free at this site? | `sweep carriers` | The declared locals that are dead here, each refusal saying why |
| Which carrier, which operand, which commutative pair? | `sweep hoist`, `sweep commute`, `sweep copies`, `sweep fuse` | One variant source per lever of that kind, keyed by (site, class, carrier), with the frozen zones another construction owns left untouched |
| I built the family — now read it back honestly | `sweep ingest` | Every variant gated, scored and ranked, with the coverage claim the run is entitled to and a row naming each variant that did not build |
| I inherited a campaign directory and there is no manifest | `campaign survey` | Stages, counts, the newest artifacts, the findings log, and whether any instrument gate was recorded — read at read time, so nothing in it can be stale |
| Several of us append findings to one log and keep colliding on numbers | `note reserve` | Identifiers reserved before they are written, across more than one document |
| Was that instrumented compiler ever gated against stock? | `instrument gate` | The section, relocation and symbol comparison, plus a stamp saying exactly what it does and does not claim |
| Would one late-pass edit explain the object? | `replay-as1` | A rebuilt object from an edited retained listing |
| Can I hand this function to decomp.me without uploading it? | `bundle-scratch` | Target, context, source, settings, and checksums |
| Will this proof repository work from a fresh clone? | `handoff audit` | Missing paths, absolute paths, and untracked local dependencies |
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
The name shapes — a bare verb reads objects, `trace-*` reads a compiler log,
`probe-*` reads your C source, `sweep <verb>` writes a family of variants —
are explained in [Choose a workflow](docs/workflows.md#command-names).

## All documentation

The three narrative pages first, then the focused guides:

- [Start here][start-here] — an almost-matched function, end to end
- [Field guide][field-guide] — the IDO codegen levers, with the C
- [The `guide` command][guide-command] — those levers, in the terminal
- [From verdict to edit][from-verdict-to-edit] — one screen to one source change, end to end
- [Backlog walkthrough][walkthrough] — thirty near matches, in triage order
- [Workflow selection][workflows]
- [Object comparison][object-comparison]
- [Aligned mechanism view][view]
- [Candidate campaigns][campaigns]
- [Calibrated allocator oracle][oracle]
- [External toolchains and calibration][toolchain-calibration]
- [JSON and automation contracts][json-contracts]
- [Current product status and intentional boundaries][product-status]
- [Gate 0: public match check][public-match-check]
- [Checking decomp.me exports][decompme-exports]
- [Scratch bundles][scratch-bundles]
- [Public handoff audits][public-handoffs]
- [Shiftability][shiftability] — is a matched project safe to insert, remove, or resize code and data in
- [The shiftability campaign][shiftability-campaign] — the five phases that make one safe, run live on a 100% decomp
- [Lessons from final-function campaigns][final-function-campaigns]
- [Alternate authentic frontends][alternate-frontends] — when the compiler itself is the variable
- [Portable Codex and Claude Code skill][agent-skill]
- [IDO version support][ido-support]
- [Trace analysis][trace-analysis]
- [The allocator decision cascade][cdx-cascade]
- [Source probes][source-probes]
- [Sweeps][sweeps] — generate a variant family, then read it back gated and scored
- [Compiler instrumentation][compiler-instrumentation]
- [Pass replay][pass-replay]
- [Line-assignment probe][line-assignment-probe] — does statement line assignment own the schedule
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
[guide-command]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/guide-command.md
[from-verdict-to-edit]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/from-verdict-to-edit.md
[alternate-frontends]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/alternate-frontends.md
[walkthrough]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/walkthrough-30-near-matches.md
[view]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/view.md
[campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/campaigns.md
[decompme-exports]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/decompme-exports.md
[agent-skill]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/agent-skill.md
[ido-support]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/ido-support.md
[compiler-instrumentation]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/compiler-instrumentation.md
[tooling-roadmap]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/tooling-roadmap.md
[elite-product-review]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/elite-product-review-2026-07-29.md
[contributing]: https://github.com/akratch/n64-decomp-workbench/blob/main/CONTRIBUTING.md
[cv64-examples]: https://github.com/akratch/n64-decomp-workbench/blob/main/examples/cv64/README.md
[documentation]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/README.md
[object-comparison]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/object-comparison.md
[final-function-campaigns]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/final-function-campaigns.md
[pass-replay]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/pass-replay.md
[line-assignment-probe]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/line-assignment-probe.md
[principles]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/principles.md
[public-match-check]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/public-match-check.md
[scratch-bundles]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/scratch-bundles.md
[trace-analysis]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/trace-analysis.md
[cdx-cascade]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/cdx-cascade.md
[source-probes]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/source-probes.md
[sweeps]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/sweeps.md
[troubleshooting]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/troubleshooting.md
[workflows]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/workflows.md
[oracle]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/oracle.md
[toolchain-calibration]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/toolchain-calibration.md
[json-contracts]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/json-contracts.md
[product-status]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/product-status.md
[public-handoffs]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/public-handoffs.md
[shiftability]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/shiftability.md
[shiftability-campaign]: https://github.com/akratch/n64-decomp-workbench/blob/main/docs/shiftability-campaign.md
