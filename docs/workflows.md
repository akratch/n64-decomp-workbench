# Choose a workflow

Start with object comparison. Move into compiler diagnostics only after the
instruction structure is close.

## Object mismatch

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

| Result | Interpretation |
|---|---|
| Count, opcode, or normalized shape differs | Source/control-flow problem |
| Shape matches; register ranges differ | Allocation or live-range problem |
| Only raw words differ | Likely relocation-controlled fields |
| `exact=true` | Function-level comparison passed |

Use `--json` to save the report and `--fail-on-mismatch` in automation. See
[Object comparison](object-comparison.md).

## Candidate search

Use `campaign` once you can compile one arbitrary source path to one output
path:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --cache-dir .workbench/cache \
  --ledger .workbench/results.jsonl \
  --jobs 8
```

Change one source dimension per campaign. Declare behavior-changing compiler
variables with `--env` so they enter the cache key. See
[Candidate campaigns](campaigns.md).

## Register-allocation mismatch

Summarize the captured compiler log:

```sh
decomp-workbench trace-summary compiler.stderr --json
```

Then choose the specific parser:

- `trace-globalcolor` for live-range costs and color/split decisions;
- `trace-alias` for base provenance and alias queries;
- `trace-fifo` for temp-register allocation and reuse.

Use a tracing-off object comparison and a trace-on positive control before
interpreting the result. See [Trace analysis](trace-analysis.md).

## Late scheduling mismatch

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

## Stop conditions

- A ranking score is search guidance, not a match.
- `exact=true` is a function-level object result, not semantic or project-wide
  proof.
- A forced compiler choice is a causal test, not an acceptable final compiler.
- Finish with the project’s normal collateral and full ROM or binary checks.
