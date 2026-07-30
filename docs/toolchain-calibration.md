# External toolchains and calibration

The repository never ships an IDO binary, ROM, generated proprietary compiler
source, or target object. `toolchain` records a user-supplied external compiler
tree as inspectable state and gives downstream commands one path-sensitive,
calibrated environment.

## Materialize a real copy

```sh
decomp-workbench toolchain init OUTPUT \
  --base STOCK_USR_LIB \
  --uopt INSTRUMENTED_UOPT \
  --ugen INSTRUMENTED_UGEN
```

`OUTPUT` must not exist and cannot be nested inside the source tree. Source
symlinks are dereferenced, replacements are copied as real files, and the
destination is rejected if any symlink remains. `--replace RELATIVE=SOURCE`
supports other pass binaries.

The manifest records source/destination hashes, relative inventory, profile
identity, and calibration evidence. It contains no binary contents.

## The readiness gates

| Gate | What it prevents |
|---|---|
| `real_copy` | path-sensitive `USR_LIB` behavior through symlink indirection |
| `fidelity` | trace-off changes in `.text`, `.rodata`, `.data`, relocations, or symbols |
| `positive_control` | a trace hook that never fires, or scheduler records with no real ready-set tie |
| `unedited_replay` | attributing a difference to an edit when replay itself differs |
| `collateral` | a target-only check hiding breakage in already-matched functions |
| `project_output` | a function-local check hiding a final ROM/binary difference |

Initialization may record fidelity and scheduler positive-control evidence.
Use `toolchain calibrate` for the remaining pairs. Object pairs use
section-scoped fidelity because stock `-g3` debug sections can vary between
identical invocations; project-output pairs require exact file hashes.

`claim=ready` appears only when all gates pass and the current file inventory
still matches the manifest. No single synthetic package test substitutes for
these project-owned cells.

## Consume the toolchain

`doctor --toolchain`, `compile-rank --toolchain`, `campaign --toolchain`, and
`oracle force/sweep --toolchain` verify the manifest before deriving `USR_LIB`.
The manifest identity participates in campaign/oracle state, so replacing an
instrumented binary cannot silently reuse earlier evidence.

Use:

```sh
decomp-workbench toolchain status OUTPUT --json
```

after copying, after calibration, and before a long campaign. A changed or
missing file revokes integrity. Rebuild a new directory rather than editing the
calibrated tree in place; immutable evidence is easier to audit than a
“repaired” manifest.

## Scheduler profiles

The workbench supports the stable `DKWB-SCHED-V1` record and a hash-pinned
external profile adapter. It does not pretend one generated-source patch is
portable across static-recompiler revisions. A profile supplies:

- exact input SHA-256;
- exact source anchors and replacements;
- declared profile identity;
- the calibration gates required before its output is evidence.

`instrument-scheduler INPUT OUTPUT --profile profile.json` refuses a hash or
anchor mismatch and refuses to overwrite. A ready-set positive control must
contain at least one event with `ready >= 2`; a trace of uncontested choices
does not prove the tie-break hook.

This boundary keeps the redistributable parser and safety model in the
workbench while generated compiler details remain with the project that can
legally and technically validate them.
