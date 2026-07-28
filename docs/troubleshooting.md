# Troubleshooting

Start by rerunning the smallest failing command without parallelism and with
the exact paths printed in your report. Preserve stderr, the command line, the
workbench version, and any JSON output.

## Objdump cannot be found

Pass the executable explicitly:

```sh
decomp-workbench compare target.o candidate.o \
  --objdump /path/to/mips64-elf-objdump
```

The executable must produce GNU-style `-d -r -z` output. A host objdump that
does not understand the object’s MIPS format is not interchangeable.

## Objdump produced no instructions

Check all three inputs:

1. The requested section exists; `.text` is only the default.
2. `--symbol` exactly matches an objdump label.
3. The selected objdump understands the object format.

Run the equivalent objdump command directly and inspect its stderr:

```sh
mips64-elf-objdump -d -r -z -j .text \
  --disassemble=function_name candidate.o
```

## Raw words differ but relocation-aware words match

This is expected when only linker-controlled fields differ. Confirm that
`relocation_metadata_mismatches` is zero and `unknown_relocations` is empty.
The exact verdict also requires equal instruction counts and relocation kinds
at aligned positions. Relocation symbols and addends are reported but are not
part of the verdict.

## An unknown relocation prevents `exact=true`

The comparator refuses to guess which instruction bits an unfamiliar
relocation controls. Retain a reduced objdump fixture, verify the relocation
semantics from an authoritative ABI/binutils source, then add a mask and
regression test. Do not work around the failure by broadly masking immediates.

## A trace command reports no events

Verify that:

- the instrumented pass, rather than the stock pass, was executed;
- the documented environment variable was set for the compiler process;
- stderr or `CDX_OUT` was captured from that process;
- a positive-control microcase reaches the instrumented site;
- procedure, register, and list filters are not excluding the event.

Keep the trace-off output comparison as a separate negative control.

## FIFO replay reports a violation

A violation can indicate a real model mismatch or an incomplete trace window.
Check the selected register class, free-list address, and first observed event.
If the trace begins after initialization, pass the known queue with
`--initial`. When `--list-address` is used, allocation records are retained
even if they carry no list address; only appends from the selected list are
accepted.

Do not “fix” a violation by reordering the inferred queue until every
allocation and append has a trace-based explanation.

## A campaign appears to reuse stale output

The cache key includes the source and target hashes, rendered command,
directly invoked wrapper identity, selected symbol/section, objdump identity,
and explicit `--env` values. It cannot discover every inherited variable,
configuration file, or compiler binary invoked by a wrapper.

Use a new cache directory after changing transitive toolchain inputs or
undeclared environment state. Record those identities in the wrapper output or
your experiment manifest.

## A campaign wrapper works manually but fails in the workbench

Check whether the wrapper assumes it starts in the project root. Candidate
paths are resolved, but relative compiler, include, and configuration paths are
still interpreted by the compiler process. Pass the expected directory
explicitly:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --compile-command './compile.sh {source} {output}' \
  --compile-cwd /path/to/project
```

## An instrumentation profile rejects generated source

The rejection is a safety property. Confirm the `ido-static-recomp` commit and
the pristine generated-source SHA-256 documented by the profile. If they differ,
develop a new profile and validate every anchor. `--allow-unverified-source`
exists for that development work, not routine compilation.

## Instrumented output differs with tracing disabled

Stop interpreting the trace. Confirm identical generated input, host compiler,
flags, environment, and downstream pass binaries. Compare a positive-control
microcase, the target function, collateral functions, and the project’s
complete output. A trace from an instrument that fails its disabled control is
not evidence.

## An unedited pass replay does not reproduce the object

Do not interpret an edited replay. Compare the original and replay commands,
pass binaries, flags, listing, symbol table, binasm, working directory, and
path-sensitive metadata. The unedited cell is the calibration for every edited
cell.

## Exit codes

Reporting commands return zero when they complete successfully. Commands with
`--fail-on-mismatch` or `--fail-on-violation` return one when the requested
quality gate fails. Commands return two for invalid input, missing files,
tool-discovery failures, or failed external stages. Ranking and trace-summary
commands can also return one when they produce no usable result.

Use `--json` for machine-readable details, but retain stderr as well: setup and
external-tool failures are written there.

## Reporting a reproducible issue

Include:

- `decomp-workbench --version` and Python version;
- operating system and objdump identity;
- the complete command with private paths redacted consistently;
- exit code, stdout, and stderr;
- the smallest redistributable objdump or synthetic trace fixture;
- expected versus observed verdict;
- for instrumentation, upstream commit, generated-source hash, host compiler,
  environment controls, and stock-versus-instrumented result.

Do not attach ROMs, proprietary compiler binaries, extracted target objects,
or third-party source you cannot redistribute.
