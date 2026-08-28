# IDO version support

As of 0.7.0, 2026-08-28.

The workbench separates compiler-neutral adapters from generated-source
instrumentation profiles. “Supports IDO 7.1” therefore does not mean every
5.3-specific patch can be applied to 7.1.

## Compatibility matrix

| Workflow | IRIX 4.x frontend | IDO 5.3 | IDO 7.1 | Requirement |
|---|---:|---:|---:|---|
| `compare`, `compare-dumps`, `rank` | yes | yes | yes | MIPS object or GNU objdump text |
| `compile-rank`, `campaign` | yes | yes | yes | Project compile-one wrapper and explicit lineage |
| `bundle-scratch` | yes | yes | yes | Target assembly, context, source, settings |
| Trace parsers | format-dependent | yes | yes | A supported emitted trace format |
| `replay-as1` | backend-dependent | yes | yes | Matching retained listing and project as0/as1 commands |
| Generic `instrument-ugen` | backend-dependent | conditional | conditional | Recognized generated-C anchors plus fidelity controls |
| Pinned uopt alias/globalcolor profiles | no | yes, pinned revision only | no | Exact documented generated-source hash |

## IRIX 4.x frontends and hybrid pipelines

IRIX 4 `accom` and `ccom` are supported as explicit frontend experiment cells,
not as a claim that the workbench ships or instruments those proprietary
binaries. A project wrapper may run `accom` and then feed its B-ucode/symbol
table to a later `uopt`/`ugen`/`as1` backend. Record the split rather than
labelling the whole result with the backend version:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --compile-command './compile-irix4-hybrid {source} {output}' \
  --compiler-id ido-5.3 \
  --frontend 'IRIX 4.1 accom' \
  --language c89 \
  --driver cc-irix4 \
  --backend 'IDO 5.3 uopt/ugen/as1'
```

Those fields are part of cache keys, manifest identity, controls, resume, and
finish receipts. Never merge an `accom` cell with later `cfe` merely because
the backend and final object format agree. Use `fingerprint-toolchain` before a
large source sweep when switch lowering or another structural signature may be
frontend-owned. The measured recipes and dialect constraints are in
[Alternate authentic frontends](alternate-frontends.md).

## IDO 7.1 campaigns

Compiler identity must be explicit in the compile wrapper and in every
behavior-changing cache input. For example:

```sh
CV64_IDO_VERSION=7.1 decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --compile-command './compile-one.sh {source} {output}' \
  --env CV64_IDO_VERSION=7.1 \
  --cache-dir .decomp-workbench/cache \
  --ledger .decomp-workbench/campaign.jsonl
```

The workbench hashes the wrapper identity, source, target, objdump, and
declared environment. It does not infer a compiler version from generated
code.

## IDO 7.1 pass replay

`replay-as1` is version-neutral, but the supplied as0 and as1 commands are not.
Calibrate an unedited control before drawing conclusions:

1. Retain the 7.1 ugen listing.
2. Replay it through the same 7.1 as0/as1 binaries and flags.
3. Require the replayed object to match the normal candidate object.
4. Only then introduce one uniquely addressed edit.

An exact edited replay establishes that the downstream pass can account for a
difference. It does not establish why an earlier pass produced that listing.

## Instrumentation boundary

The packaged deep uopt profiles remain tied to one IDO 5.3 static-recomp
generated source and SHA-256. Do not bypass that rejection for routine 7.1
work and report the result as supported.

A real 7.1 deep profile needs:

1. the pristine generated `uopt.c` and its upstream revision;
2. a pinned source hash and uniqueness-checked anchors;
3. tracing-disabled byte identity against the stock 7.1 pass;
4. positive controls that reach every claimed trace site;
5. collateral tests showing the trace hooks do not alter unrelated output.

Until those gates are complete, use comparison, campaigns, retained listings,
pass replay, and the generic trace parsers for IDO 7.1 investigations.
