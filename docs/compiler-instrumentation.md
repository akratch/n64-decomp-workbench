# Compiler instrumentation

The workbench targets C emitted by
[`ido-static-recomp`](https://github.com/decompals/ido-static-recomp). It does
not include compiler binaries or generated compiler source.

## Two levels of intervention

### Trace-only hooks

Trace-only instrumentation observes host-side execution of a statically
recompiled compiler pass. With its environment variables unset it is intended
to leave emulated compiler state unchanged.

That intention still requires an output-fidelity test.

### Behavioral controls

Controls such as a forced globalcolor choice intentionally alter compiler
behavior. They are useful for questions like:

> If this web were assigned the target register, would the remaining object
> become exact?

An affirmative result isolates cause. It does not show that the original
compiler contained that control or that a forced object is an acceptable
decompilation result.

## Basic ugen call/free-list hooks

```sh
decomp-workbench instrument-ugen \
  /path/to/generated/ugen.c \
  /tmp/ugen.traced.c
```

Compile the result as the upstream project normally would, then enable:

```sh
DKWB_UGEN_TRACE=1 /path/to/traced-cc ...
```

The generated source emits:

- `DKWB-CALL` entry/exit records for selected `f_*` functions;
- `DKWB-FREELIST` records at known allocator/free-list helper entries.

Restrict function tracing:

```sh
decomp-workbench instrument-ugen ugen.c ugen.traced.c \
  --functions '^(f_(alloc|free|add_to|remove_from|move_to).*)$'
```

This generic instrumenter is an entry-level locator. The DKR research used a
deeper, IDO-5.3-specific profile that also logged queue state, node identity,
source line, destination hints, and exact append/remove events. The trace
parser accepts that historical format; the generic instrumenter does not claim
to recreate every one of those hooks on arbitrary generated source. The call
frame helper uses the GCC/Clang `cleanup` attribute, so the host compiler must
support it.

## Pinned uopt profiles

Apply both compatible profiles in one guarded operation:

```sh
decomp-workbench instrument-uopt \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.traced.c \
  --profile alias \
  --profile globalcolor
```

The command validates the pristine input once, applies profiles in a stable
order, and validates every source anchor. Use the narrower commands below when
only one trace family is needed.

### Globalcolor profile

```sh
decomp-workbench instrument-uopt-globalcolor \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.globalcolor.c
```

#### Globalcolor environment variables

| Variable | Effect |
|---|---|
| `CDX_LOG=1` | Emit `[CDX]` decision records |
| `CDX_PROC=N` | Restrict logs and controls to globalcolor invocation `N` |
| `CDX_OUT=FILE` | Write diagnostics to a file instead of stderr |
| `CDX_FORCE=w9=c30` | Force web 9 to color 30 for the selected procedure |
| `CDX_FORCE=w9=s` | Force the split/no-color path for web 9 in the selected procedure |

Multiple force entries are comma-separated. `CDX_FORCE` is ignored unless
`CDX_PROC` selects one globalcolor invocation; this prevents an experimental
choice from being applied to the same web number in unrelated procedures.
Here `wN` is the allocator bit position printed as `web=N`; `sym` is reported
separately and is not the force key.

### Alias and base-provenance profile

```sh
decomp-workbench instrument-uopt-alias \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.alias.c
```

Set `DKWB_UOPT_ALIAS_TRACE=1` while compiling to emit:

- `DKWB-BASE` when the pass observes a base in a register, including the
  register, descriptor type, symbol, address, prior-state flag, and `fresh`,
  `direct`, or `retain` path;
- `DKWB-ALIAS-QUERY` at the profiled base-noalias return, including both
  descriptors and the `may-alias` or `no-alias` outcome.

Summarize a captured log with:

```sh
decomp-workbench trace-alias uopt.log --show-queries
```

The profile observes the pinned sites; it does not grant alias relationships
or change the return value. Its current-register association follows the
profiled pass's observed call path, so validate it with a positive-control
microcase before interpreting a new workload.

### Input identity

Both profiles support this generated source:

- upstream: `decompals/ido-static-recomp`;
- upstream commit used to generate the profile:
  `9c242adc890beef098020149d9554f48208f699d`;
- generated `build/5.3/uopt.c` SHA-256:
  `b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f`.

Every profile command validates the SHA and every source anchor. It refuses a
different file by default. `--allow-unverified-source` exists for profile
development, not routine use; review the resulting diff and run all fidelity
gates.

## Required fidelity gates

For each profile and host:

1. Hash the unmodified generated source.
2. Build stock and instrumented passes with identical host flags.
3. Compile a positive-control microcase with tracing off through both.
4. Compare pass outputs byte for byte.
5. Compile the target translation unit through both.
6. Compare the target and already-matching collateral functions.
7. Rebuild and verify the complete ROM or binary.
8. Turn tracing on and prove the expected diagnostic appears.
9. If using a behavioral control, prove the disabled control returns to the
   stock output.

The workbench’s synthetic unit tests prove anchor validation and trace parsing.
They cannot substitute for these user-input-dependent integration gates.

## Profile development

Generated C is coupled to an input binary and static-recompiler revision.
Prefer a small patch generator with exact anchors over committing an enormous
diff of generated source. Record:

- input executable/version;
- static-recompiler commit;
- generated-source hash;
- all emulated addresses and what established them;
- trace schema;
- control semantics;
- positive and negative controls.
