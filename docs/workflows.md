# Choose a workflow

The workbench is most useful after a decompilation is broadly correct and the
remaining question can be stated precisely. Start with object comparison.
Compiler tracing and pass replay are later interventions, not prerequisites.

## 1. Evaluate the project without a toolchain

**You have:** Python 3.10 or newer.

**You want:** To see what the reports look like before supplying compiler or
game inputs.

Install the checkout and run the redistributable fixtures:

```sh
python3 -m pip install -e .

decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch

decomp-workbench trace-fifo examples/traces/ugen-fifo.log \
  --registers t6,t7,t8 \
  --show-events \
  --fail-on-violation
```

The comparison should report `words=0 raw=2`. The FIFO should finish without a
violation. These commands prove that the installation and parsers work; they
do not validate a project toolchain.

## 2. Diagnose a late-stage object mismatch

**You have:** A target object, a candidate object, the function symbol, and a
GNU-compatible MIPS objdump.

**You want:** To determine whether the residual is structural, relocation-only,
or primarily register allocation.

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --show-diff
```

Read the result as a decision point:

| Observation | Next step |
|---|---|
| Instruction count, opcodes, or normalized structure differ | Continue ordinary source/control-flow work |
| Structure aligns but register ranges differ | Capture the narrowest relevant uopt or ugen trace |
| Raw words differ but relocation-aware words do not | Inspect relocation metadata; the linker-controlled fields may explain the raw difference |
| `exact=true` | Run the project’s normal object, collateral, and complete-output verification |

Use `--json` to retain the report and `--fail-on-mismatch` in automation. See
[Object comparison](object-comparison.md) for exact verdict semantics.

## 3. Run a reproducible candidate campaign

**You have:** A set of generated C candidates and a project wrapper that can
compile one source path to one object path.

**You want:** Repeatable parallel compilation, caching, and a record of every
result.

Begin with two candidates and prove the wrapper contract:

```sh
decomp-workbench campaign target.o candidates/a.c candidates/b.c \
  --symbol function_name \
  --objdump /path/to/mips64-elf-objdump \
  --compile-command './compile-one.sh {source} -o {output}' \
  --cache-dir .workbench/cache \
  --ledger .workbench/campaign.jsonl \
  --jobs 2
```

The command template is tokenized without a shell. Pipes, redirection, globbing,
and command substitution are not interpreted. The wrapper itself is executed
with your user permissions; inspect it before running it.

Once the control run works, scale one named transformation family at a time.
Declare behavior-changing environment values with `--env` so they enter the
cache key. Inherited environment and transitive compiler inputs are not fully
discoverable; use a new cache when those change. See
[Candidate campaigns](campaigns.md).

## 4. Investigate a register-allocation plateau

**You have:** A structurally aligned candidate and a trace from the relevant
compiler pass.

**You want:** To replace a vague “register pressure” theory with an observed
web, alias decision, or allocator schedule.

First identify what the trace contains:

```sh
decomp-workbench trace-summary compiler.stderr --json
```

Then choose the narrow report:

- `trace-globalcolor` for `CSAVE`, `CUP`, and `[CDX]` live-range decisions;
- `trace-alias` for base provenance and may-alias/no-alias queries;
- `trace-fifo` for ugen free-list allocation and reuse.

Establish an instrumentation-off control and a trace-on positive control before
interpreting a large translation unit. If the trace starts mid-allocation,
supply the known FIFO entry state with `--initial`; do not infer it from a
convenient physical register sequence. See [Trace analysis](trace-analysis.md)
and the [worked examples](../case-studies/README.md).

## 5. Test a pass-boundary hypothesis

**You have:** A retained ugen listing plus the matching as0 and as1 binaries.

**You want:** To ask whether one intermediate directive or instruction is
sufficient to explain the final schedule.

Replay the listing without edits first:

```sh
decomp-workbench replay-as1 unit.s control.o \
  --as0-command '/ido/as0 ... {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 ... {binasm} -o {object} -t {symtab}'
```

The control object must reproduce the normal downstream output. Only then add
one uniquely matched `--insert-before` or `--insert-after` edit. An exact edited
result proves downstream sufficiency, not why the earlier pass emitted or
omitted the fact. See [Retained-pass replay](pass-replay.md).

## 6. Instrument the pinned IDO 5.3 static recompile

**You have:** Generated C from `decompals/ido-static-recomp`.

**You want:** Opt-in host-side observations of uopt or ugen.

The generic ugen locator can instrument compatible generated `f_*` functions.
The uopt alias/globalcolor profiles are intentionally narrower: they accept one
pinned generated IDO 5.3 `uopt.c` hash and exact source anchors.

Do not bypass a hash rejection merely to make the patch apply. A different
generated source needs a reviewed profile, new anchors, and the complete
fidelity matrix. Trace-only hooks still require stock-versus-instrumented
output checks. Behavior-changing force controls are causal experiments, not
matching compilers. Follow [Compiler instrumentation](compiler-instrumentation.md).

## 7. Adapt or maintain the workbench

**You have:** A new trace schema, relocation type, compiler profile, or
repeatable diagnostic that should become reusable.

**You want:** A contribution that can be trusted outside one project.

Add the smallest synthetic or reduced fixture that demonstrates the behavior.
Keep exact verdicts separate from search heuristics. A new generated-source
profile must include its upstream commit, pristine source hash, unique anchors,
disabled-instrumentation comparison, and positive control. Function-specific
generators and proprietary inputs belong in their source project, with a
provenance link here if the lesson is promoted. See [Contributing](../CONTRIBUTING.md).

## What the workbench does not supply

It does not provide ROMs, target objects, proprietary compiler binaries,
project build wrappers, or a sandbox for untrusted compilers. It does not prove
semantic equivalence or historical source identity. Those boundaries are
deliberate; see [Scope and claims](scope-and-claims.md).
