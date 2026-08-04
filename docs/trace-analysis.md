# Trace analysis

Trace analysis answers a narrower question than disassembly: which compiler
events produced an otherwise-correct register or scheduling pattern?

## Summarize an unfamiliar trace

```sh
decomp-workbench trace-summary compiler.stderr --json
```

The parser retains known `CODEX-*` and `DKWB-*` tags and counts actions,
registers, and source lines. Unknown diagnostic tags remain visible rather than
being silently discarded.

## Inspect alias-state decisions

```sh
decomp-workbench trace-alias uopt.log --show-queries
```

The pinned uopt profile emits two trace families:

- `DKWB-BASE` records the descriptor associated with a physical register and
  whether the base path was fresh, direct, or retained;
- `DKWB-ALIAS-QUERY` records the two descriptors and the pass's observed
  may-alias/no-alias result.

The report counts base paths, descriptor types, outcomes, and registers.
`--show-queries` prints each decision; `--json` retains the full normalized
event fields for downstream analysis. See
[compiler instrumentation](compiler-instrumentation.md) for profile creation
and the required controls.

## Reconstruct a FIFO free list

```sh
decomp-workbench trace-fifo ugen.log \
  --registers t3,t4,t5,t6,t7,t8,t9 \
  --list-address 10019da4 \
  --show-events \
  --fail-on-violation
```

The replay:

1. Uses unique append events before the first allocation as the initial queue,
   unless `--initial` is supplied.
2. Checks each allocation against the queue head.
3. Assigns a new logical value identity to each allocation.
4. Converts later appends into frees of those logical values.
5. Reports duplicate appends, frees without a live value, allocation of an
   already-live register, and empty-queue allocation.

Use `--initial t6,t7,t8,...` when the trace begins after queue initialization.
Addresses accept decimal, `0x`-prefixed hexadecimal, or bare hexadecimal when
the value contains `a`–`f`; prefix digit-only hexadecimal values with `0x`.
When `--list-address` is set, the replay keeps allocation records, which may
not carry a list address, and accepts append records only from the selected
list. Use `--json` when another solver will consume the logical schedule.

### Why logical identities matter

A physical sequence such as `t6,t4,t8,...` is not necessarily the allocator’s
entry queue. Allocation and free events interleave, and later registers may
already be recycled values. Logical values make the event schedule explicit
before any inference about source evaluation order.

## Read globalcolor traces

```sh
decomp-workbench trace-globalcolor uopt.log --dtype 13 --top 25
```

Once a comparison has isolated an allocation residual, inspect a single web
instead of scanning an entire procedure:

```sh
decomp-workbench trace-globalcolor uopt.log --proc 46 --web 240
```

`--proc` and `--web` hide unrelated legacy live-range rows. `--web` requires
`--proc`, and an explicit lookup exits nonzero when its allocator data is
absent. A missing lookup lists the procedure or web IDs that were actually
recorded.

The report names stable callee-saved profile colors when it can (`c17 (s3)`),
keeps profile-specific colors as `cNN`, and explains whether the web was
colored or split. A force probe is a causal experiment only: use it to learn
which lifetime must be reshaped, never as a source-match result.

Supported formats:

- `CSAVE`: one live range/web and its adjusted-save inputs;
- `CUP`: cost of a candidate color/register;
- `[CDX]`: selection, split/color, and force-choice decisions from the
  profiled instrumentation.

The report computes `total_save` as `adjusted_save × weight`. Field names are
descriptive handles for the pinned generated source, not stable IDO API names.
Non-finite values become `"inf"`, `"-inf"`, or `"nan"` in JSON.

## Align webs across source variants

Numeric allocator web IDs are stable only inside one compiler input. Compare
semantic provenance instead:

```sh
decomp-workbench trace-webs candidate.cdx --against variant.cdx --proc 7
```

Fingerprints use allocator phase, dtype/type, virtual-home fields,
table/expression formation chain, and block provenance. Numeric IDs are
trace-local handles. A fingerprint that is not unique on either side is
reported as ambiguous and withheld rather than paired by position.

When neighbor records are present, the diff joins a newly forbidden color to
the already-colored neighbor that occupies it, naming the neighbor's semantic
fingerprint and decoded register where known.

`trace-stack-homes TRACE --proc N [--offset VALUE]` classifies only homes for
which the producer recorded evidence: named source local, compiler temporary,
outgoing argument home, or allocator spill. Virtual offsets and final offsets
stay separate; a missing final layout is `null`, not inferred.

## Correlate logical lines to source and listings

Compiler line fields can be coarse, synthetic, and ambiguous after includes.
Retain the preprocessed/composed input and optional assembly listing:

```sh
decomp-workbench trace-source \
  examples/traces/oracle.log \
  examples/traces/oracle-source.i \
  --listing examples/traces/oracle-listing.s \
  --source-file candidate.c
```

The command replays standard preprocessor markers and `.file/.loc`
directives. It preserves all candidates when a logical line exists in several
files and narrows only on an explicit marker filename. Correlation is evidence
attached to a semantic web, never part of the fingerprint itself.

Neither correlation nor allocator metadata is a source semantic. Without a
direct trace `source_semantic`, `trace-webs` and `oracle plan` classify the web
as run-local/unattributed. Capture that field before turning a force result into
a source-experiment recommendation.

## Plan a causal allocator probe

```sh
decomp-workbench oracle plan examples/traces/oracle.log
```

The planner reports both p1 and p2, uses only measured cost colors (or explicit
overrides), and omits forbidden endpoints. A ready external toolchain can then
run one force or the full cached grid. See [Calibrated allocator
oracle](oracle.md) for the fidelity gates, state, and proof boundary.

## Trace comparison discipline

- Compare the same procedure ordinal and compiler profile.
- Keep source-line tags stable or record source hashes.
- Establish an instrumentation-off control that is byte-identical per section
  (`.text`, `.rodata`, `.data`, relocations, symbols); `.mdebug` varies between
  runs of stock IDO under `-g3`, so file-level hashes are not a usable gate.
- Compare the same allocator phase: `p1` and `p2` web numbers are disjoint.
- Use a small positive-control source to prove the event hook fires.
- Treat force-choice output as a causal experiment, not as historical
  provenance.
- Reduce a trace to the smallest register class and source window that answers
  the question.
- Reopen saved oracle evidence with `oracle status`; do not rerun merely to
  reconstruct a terminal screen.
