# Choose a workflow

Start with object comparison. Move into compiler diagnostics only after the
instruction structure is close.

## Downloaded decomp.me scratch

```sh
decomp-workbench doctor "/path/to/scratch.zip"
decomp-workbench check-scratch "/path/to/scratch.zip" --show-diff
```

This validates the handoff, reports the browser score as context, and compares
the site's own target/current objects. Add `--compile-command` when you need to
test a local candidate with the site's context and source-line reset. See
[decomp.me export checking](decompme-exports.md).

## Object mismatch

```sh
decomp-workbench diagnose target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump
```

| Result | Interpretation |
|---|---|
| Count, opcode, or normalized shape differs | Source/control-flow problem |
| Shape matches; register ranges differ | Allocation or live-range problem |
| Only raw words differ | Likely relocation-controlled fields |
| `exact=true` | Function-level comparison passed |

`diagnose` disassembles each input once and renders the comparison plus
decisive aligned hunk. Use `compare` alone for a compact gate,
`--fail-on-mismatch` in automation, and `view --show-all` for full evidence.
See [Object comparison](object-comparison.md).

## Mechanism diagnosis

When the residual is small but the layer that owns it is unclear, or when the
count looks large because the streams are shifted:

```sh
decomp-workbench view target.o candidate.o --function function_name
```

The output aligns the two streams, classifies every hunk, prints the per-class
register lanes (including the matching instructions), reports where the byte
prefix ends, and names the lever family. `view-dumps` runs the same analysis on
retained objdump text. See [Aligned mechanism view](view.md).

## Candidate search

Use `campaign` once you can compile one arbitrary source path to one output
path:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --jobs 8
```

Change one source dimension per campaign. Declare behavior-changing compiler
variables with `--env` so they enter the cache key. See
[Candidate campaigns](campaigns.md).

The manifest and ledger are default state. Use `campaign status`, `note`,
`resume`, and `export` to continue the same experimental question. Validate an
external generator's parameter sidecar with `experiment validate` before
attaching it through `--experiment-manifest`.

## Register-allocation mismatch

Summarize the captured compiler log:

```sh
decomp-workbench trace-summary compiler.stderr --json
```

Then choose the specific parser:

- `trace-globalcolor` for live-range costs and color/split decisions;
- `trace-alias` for base provenance and alias queries;
- `trace-fifo` for temp-register allocation and reuse.
- `trace-webs` for semantic alignment across source variants;
- `trace-source` for marker-aware source/listing correlation;
- `trace-stack-homes` for virtual-home ownership.

Use a tracing-off object comparison and a trace-on positive control before
interpreting the result. See [Trace analysis](trace-analysis.md).

## Late scheduling mismatch

First decide which layer owns the order. If the instruction multiset and the
allocator lanes already agree, ask whether statement *line assignment* owns it
before you ask which compiler build did — that question costs one
token-identical variant plus a control:

```sh
decomp-workbench probe-lines unit.i \
  --compile-command '/ido/cc -c -O2 -mips2 {input} -o {output}' \
  --function drawBitmap --target-object target.o
```

A `LINE-SENSITIVE` verdict routes onward to `--tie STATEMENT=LINE`, which
scores one statement's reassigned line number toward and away from the target.
See [Line-assignment probe](line-assignment-probe.md).

If the retained ugen listing is right but the final schedule is not, replay the
downstream passes:

```sh
decomp-workbench replay-as1 unit.s control.o \
  --as0-command '/ido/as0 ... {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 ... {binasm} -o {object} -t {symtab}'
```

The unedited replay must reproduce the normal object. After that, test one
uniquely matched `--insert-before` or `--insert-after` edit. See
[Pass replay](pass-replay.md).

## Static-recompiled IDO instrumentation

Use the generic `instrument-ugen` command for shallow function and free-list
tracing. Use `instrument-uopt` for the packaged IDO 5.3 alias/globalcolor
profiles.

Do not bypass a hash rejection for routine use. A different generated source
needs reviewed anchors and the full fidelity checks in
[Compiler instrumentation](compiler-instrumentation.md).

## Calibrated allocator cause

Only after ordinary source families and pass ownership are exhausted:

```sh
decomp-workbench oracle plan focused.cdx
decomp-workbench oracle force candidate.c \
  --trace focused.cdx \
  --target target.o \
  --toolchain .decomp-workbench/toolchains/ido53-cdx \
  --compile-command './compile-one.sh {source} -o {output}' \
  --symbol function_name \
  --force p2:w55=c2
```

If controlled single-force deltas identify an interaction, pass the distinct
web controls together (for example
`--force p1:w9=c4,p1:w14=c2,p2:w55=c14`). The persisted row includes the
baseline-to-forced changed instructions under `emitted_effect`; those are
object-level role clues, not source attribution.

Planning reports both allocator phases and measured endpoints. Force/sweep
requires a ready, intact real-copy toolchain and persists its evidence for
`oracle status/export`. An exact forced build is a source-level hypothesis,
never a final match. See [Allocator oracle](oracle.md).

## Stop conditions

- A ranking score is search guidance, not a match.
- `exact=true` is a function-level object result, not semantic or project-wide
  proof.
- A forced compiler choice is a causal test, not an acceptable final compiler.
- Finish with the project’s normal collateral and full ROM or binary checks.
