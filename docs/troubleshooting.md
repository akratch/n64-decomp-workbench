# Troubleshooting

Start by rerunning the smallest failing command without parallelism and with
the exact paths printed in your report. Preserve stderr, the command line, the
workbench version, and any JSON output.

## Browser and local decomp.me results disagree

Download the scratch export and run:

```sh
decomp-workbench check-scratch "/path/to/scratch.zip" --show-diff
```

This compares `target.o` and `current.o` from the same site state, so the
browser score and local oracle no longer refer to different inputs. For a
local candidate, use `--compile-command`: compiling `code.c` alone omits the
site's context and `#line 1 "src.c"` reset, which can change an IDO `-g3`
schedule. See [the export tutorial](decompme-exports.md).

## Objdump cannot be found

Pass the executable explicitly:

```sh
decomp-workbench compare target.o candidate.o \
  --objdump /path/to/mips64-elf-objdump
```

The executable must produce GNU-style `-d -r -z` output. A host objdump that
does not understand the object’s MIPS format is not interchangeable.
An explicit `--objdump` path is authoritative: a typo is reported instead of
silently falling back to a different executable on `PATH`.

## Objdump produced no instructions

The error lists every symbol each input actually defines, so compare your
`--function` spelling against that list first. **Names are case-sensitive**:
`DrawObject` and `drawObject` are different symbols, and a case slip and a
typo produce the same "no instructions" result.

Check all three inputs:

1. The requested section exists; `.text` is only the default.
2. `--symbol` exactly matches an objdump label, including its case.
3. The selected objdump understands the object format. `file format not
   recognized` means the path is not a compiled MIPS ELF object at all -
   usually because the build did not produce one.

Run the equivalent objdump command directly and inspect its stderr:

```sh
mips64-elf-objdump -d -r -z -j .text \
  --disassemble=function_name candidate.o
```

## The verdict looks confident but the objects hold different functions

Without `--function` the comparison is positional over the whole section. That
is correct when both objects hold the same single function, and meaningless
when they do not. When each side defines exactly one *differently named*
function, every command prints this ahead of the verdict:

```text
warning: target defines 'drawObject' but candidate defines 'drawShadow' - comparing the whole .text section positionally, not one function. Pass --function to select a single symbol explicitly.
```

Pass `--function` (or `--symbol`; they are one option) and run it again. The
warning cannot fire when either side defines several symbols, because a
whole-section comparison is then the documented and intended mode.

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

If the campaign has a manifest, prefer `campaign resume` over manually
re-running its source glob. Resume verifies target/source hashes, wrapper,
objdump, cwd, explicit environment, and toolchain-manifest identity before it
uses the existing ledger. A mismatch is a refused resume, not a cache hit.

Inspect cache state with `cache status`. `cache prune` is a dry run by default;
`--apply` moves entries to recoverable trash and prints the restore command.

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

## A toolchain is intact but still uncalibrated

That is expected after a successful partial `toolchain init/calibrate`. Run
`toolchain status DIRECTORY --json` and read `next_missing_gates`.
“Uncalibrated” is a claim state, while failed `integrity` means a copied file
changed or disappeared. Oracle execution requires both intact hashes and
`claim=ready`.

Do not edit a calibrated directory or rewrite its manifest. Materialize a new
real-copy directory when a pass binary changes, then rerun the evidence cells.

## Oracle planning returns no forces

Check that the trace contains p1/p2 decision records for the selected
procedure. A phase with zero webs is printed explicitly. Colors are taken only
from measured cost records unless `--colors-p1/--colors-p2` supplies a reviewed
set; the planner will not guess a register universe.

A force absent from the plan may be forbidden by the web mask. Use
`trace-globalcolor --proc N --web W` to inspect `forbidden_colors`.
`trace-source` can then map the web's logical line through a retained
preprocessor input without guessing between includes.

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

Commands given `--census` return **three** when the report was produced and at
least one predicate failed. Three rather than one, because `--fail-on-mismatch`
already owns one and answers a different question: a variant can be the shape
the census is looking for and still not be a match. A malformed or unknown
census key is a usage error and returns two like every other one, before the
inputs are read.

With `--json`, success and failure both produce exactly one schema-named JSON
document on stdout and leave stderr empty. Without JSON, user-facing failures
remain on stderr. See [JSON contracts](json-contracts.md).

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
