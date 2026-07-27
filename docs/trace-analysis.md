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

Supported formats:

- `CSAVE`: one live range/web and its adjusted-save inputs;
- `CUP`: cost of a candidate color/register;
- `[CDX]`: selection, split/color, and force-choice decisions from the
  profiled instrumentation.

The report computes `total_save` as `adjusted_save × weight`. Field names are
descriptive handles for the pinned generated source, not stable IDO API names.
Non-finite values become `"inf"`, `"-inf"`, or `"nan"` in JSON.

## Trace comparison discipline

- Compare the same procedure ordinal and compiler profile.
- Keep source-line tags stable or record source hashes.
- Establish an instrumentation-off byte-identical control.
- Use a small positive-control source to prove the event hook fires.
- Treat force-choice output as a causal experiment, not as historical
  provenance.
- Reduce a trace to the smallest register class and source window that answers
  the question.
