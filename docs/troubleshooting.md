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
site's context and language-aware `src.c`/`src.cxx` reset, which can change an
IDO `-g3` schedule. See [the export tutorial](decompme-exports.md).

## `extern "C"` is a syntax error on decomp.me

Check the exported/compiler metadata, not only the name at the top of the
Options panel. `ido7.1` runs the C frontend (`cc`/`cfe`) and cannot parse C++
linkage. For the stock IDO 7.1 C++ path, set **Preset** to **Custom**, select
compiler `ido7.1_c++`, and verify language C++; that path uses `NCC`/EDG.
`check-scratch` prints these identities separately so a preset cannot hide the
frontend change.

## A pasted scratch fails to compile with an error on the first code line

Check whether the context you pasted ends with a trailing newline. decomp.me
concatenates the context and the editable code **verbatim**, with nothing
inserted between them. If the context's last line has no trailing newline,
the first line of code fuses onto the context's last statement, and the
compiler reports an error on a line that looks correct in isolation. This is
a paste-assembly problem, not a source problem: it shows up when a context is
hand-assembled (e.g. copied out of a source tree) rather than pasted from the
actual export, which always ends its `ctx` member in a newline. Diff your
pasted context against the exported `ctx.c` byte for byte before suspecting
the code.

## A pasted scratch fails on redeclaration of a file-scope static

The exported context already declares the translation unit's file-scope
statics. A paste assembled by hand from the raw source — rather than from the
actual export — commonly declares them a second time in the "code" portion,
which fails to compile. Use the export's `ctx.c` as the source of truth for
what is already declared, and start the editable portion after it, not from
the top of the original file. `check-scratch` (or `doctor`) against the real
export catches this before you paste anything, and
`decomp-workbench context duplicates ctx.c code.c` flags a simple duplicate
top-level definition mechanically instead of leaving it as a compiler error to
interpret. (`context lint` is the separate preprocessor-conditional audit.)

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

## `--function` on a target whose symbol was stripped

A decomp.me export's `target.o`, and any object holding an IDO `static`
function, carries one function's worth of `.text` with nothing in the symbol
table naming it. GNU objdump labels the section itself:

```text
00000000 <.text>:
```

`--disassemble=NAME` matches nothing there, and no spelling of `--function`
can ever select in such an object. Rather than reporting "produced no
instructions" — which reads like an object with no code in it — every
comparison command falls back to the whole-section positional path and says
so ahead of the verdict:

```text
warning: export/target.o has no symbol for 'drawObject' - its .text is one function's worth of code with the symbol stripped, which is normal for a decomp.me export and for an IDO static function. Comparing the whole .text section positionally instead. Omit --function to select this path explicitly.
```

The fallback is deliberately narrow. It requires the dump to carry the
section's own label and no function label: an object that *does* name
functions still rejects a name that misses them, so a typo stays a typo. A
dump carrying instructions under no label at all is treated as truncated
output and also still fails.

`compare`, `view`, `diagnose`, their `*-dumps` forms, and `check-scratch` all
take this path, so no two of them disagree about the same pair of objects.

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

`compare` names the gap when `raw` exceeds `words`:

```text
raw difference classes: instruction_bits=563, relocation_controlled=45
raw-vs-words: raw=608 exceeds words=563 by 45 relocation-controlled word(s):
              linker-filled bits no source change moves. A raw objdump text diff counts
              them permanently, so words=0 is the honest gate, not a byte-identical dump.
```

A separately written `objdump -d` diff has no relocation table in hand and
counts those words as differences, which is why such a diff can sit on a floor
the workbench does not report. The usual cause is symbol granularity: a target
that names each float literal with its own `.rodata` symbol against a candidate
that merges them into one anonymous section puts the slot in the addend, so
every literal load differs in bits while reading the same slot. `pool_matches`
and `pool_resolution` report that reading; `words = 0` remains the gate, and a
byte-identical disassembly is not reachable on such a pair.

## An unknown relocation prevents `exact=true`

The comparator refuses to guess which instruction bits an unfamiliar
relocation controls. Retain a reduced objdump fixture, verify the relocation
semantics from an authoritative ABI/binutils source, then add a mask and
regression test. Do not work around the failure by broadly masking immediates.

## `audit-handoff` says the root is not a directory, and doubles a name

`handoff root is not a directory: /work/bundle/bundle` from
`decomp-workbench audit-handoff bundle/` is not the argument being appended to
itself. A relative argument is resolved against the process working directory,
so that message means the shell was already inside `bundle` — the usual cause
is a `cd` in an earlier step of the same script. The message names the argument
as typed and the directory it was resolved against for exactly this reason:

```text
handoff root is not a directory: /work/bundle/bundle (from 'bundle/' relative to /work/bundle)
```

Relative and absolute spellings of the same tree audit identically; `.`,
`bundle/`, and `../bundle` all resolve to one canonical root.

## A near-match suddenly reports thousands of differing words

The candidate almost certainly emits a different number of instructions, and
the comparison is position-indexed: candidate row N against target row N. One
inserted instruction shifts every later row against its neighbour, so an
object that is byte-exact apart from one `nop` reports a four-figure count and
reads as garbage.

```sh
decomp-workbench align target.o candidate.o
```

`align` prints the edit script and the number that survives a shift — `away`,
the instructions a source change must actually move. It also states what the
positional comparison charged, so the two numbers can be reconciled rather
than argued about. `next` routes here automatically and marks it a blocker:
allocator and scheduler experiments are not measurable across a count
difference. See [Shift and phase](shift-and-phase.md).

## The score improved a lot and nothing seems closer

Read whether the improvement is a rotation rather than a repair. A float-heavy
function often differs in every row of a region while being one register
renaming away from exact — the same values in the same scratch ring, starting
one register along.

```sh
decomp-workbench phase target.o candidate.o --slots head=1..2038,body=2039..4641
```

`phase` prints two numbers per slot: `free`, quotiented by the best-fit ring
coset, and `positional`, what the object scores as written. **Rank on
positional.** A slot whose row carries a `COSET` note is not progress the
object has made, and one campaign recorded exactly that as a win. See
[Metric traps](metric-traps.md).

## A cascade reports a kill that never happened

The site was named by a trace-local symbol or web number, and a rebase
renumbered it. `sym=1042` became `sym=1039`, the script that grepped the old
number found nothing, and "no decision for this site" was read as "the site
was killed" — for seven stages of one campaign.

Name the site by its frame offset, which is the one identity in the grammar
that a rebase does not move:

```sh
decomp-workbench trace-cascade build.ilog --frame-offset 0xfffffdf8
```

`--against OTHER.ilog` prints the same site in both logs round by round, and
says outright when the symbol number changed underneath it.

## `slots` says 1184 and `trace-cascade` wants 0xfffffdf8

They are the same storage. `slots` prints the displacement the rows spell
(sp-relative); the allocator trace keys a site by the frame offset, which is
that number plus the frame size. `slots` prints both columns and the frame
size in its header, so paste the `frameoff` value:

```sh
decomp-workbench slots candidate.o        # slot 1184  frameoff 0xfffffdf8
decomp-workbench trace-cascade build.ilog --frame-offset 0xfffffdf8
```

Passing `--frame-offset` and `--slot`+`--frame` together is refused unless
they derive the same site, so a driver that sets each from a different place
cannot silently read the wrong slot.

## `sweep ingest` says `sampled` and "never visited"

Some variants have no object. A point with no object is a point nobody
measured — it is not an exclusion, and it does not buy back the
`swept-exhaustively` claim, because a negative result over a space half of
which was never built is not a proof about that space. The `unbuilt` list
names each one and why: `no object at PATH` means the wrapper never wrote it,
`unreadable: ...` means it wrote something objdump could not read. Fix the
build for those, re-run `sweep ingest`, and the coverage sentence changes on
its own.

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

## A sweep driver dies with "file name too long" inside objdump

The list is arriving as one argument. `zsh` does not word-split a parameter
expansion, so a driver that builds a list in a variable and expands it
unquoted —

```sh
# shell-lint: allow-unquoted -- this is the mistake, not the fix
LABS=$(ls objects/*.o)
decomp-workbench rank target.o $LABS
```

— hands the whole newline-joined list to the command as a single filename. It
works under `bash` and silently does not under `zsh`, and the error surfaces
inside the tool rather than at the quoting, so it reads as a tool bug. One
campaign had this shape in every scorer invocation it wrote, and it cost a
stage.

Two fixes, both better than remembering to quote. Let the shell expand the
glob itself, which is field-splitting-free in every shell:

```sh
decomp-workbench rank target.o objects/*.o
```

or, where the values are not filenames, take them from a file. Every
list-valued option here also accepts `--OPTION-from FILE`, one value per line,
with blank lines and `#` comments ignored:

```sh
decomp-workbench sweep regress work.c --construct-from levers.txt --write regress/
```

Nothing this repository ships expands a variable unquoted, and a test enforces
that for every shell block in the documentation.

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

If one wrapper selects multiple historical frontends, pass the explicit
compiler envelope: `--compiler-id`, `--frontend`, `--language`, `--driver`,
and `--backend`. An IRIX 4 `accom` cell and a later `cfe` cell must not share a
cache identity merely because the final wrapper or backend path is identical.
Empty envelopes preserve old cache keys.

## A campaign stopped before compiling candidates

Read the control receipt. A required `FAIL` means the baseline or requested
differential contradicted its declaration. `UNKNOWN` means the metric, signal,
object hash, or successful compile needed to answer the control was absent; it
also blocks. This is exit 2 by design, and zero ordinary candidates were
scheduled. Fix the wrapper, selected symbol, control source, or expectation;
do not weaken a measured control just to open the pool.

## Campaign finish says NOT RUN

`NOT RUN` is not failure and not success. It means the optional gate was not
supplied: scratch context, collateral reference object, handoff directory, or
project command. Supply the corresponding option when that gate belongs to
your definition of done. A finish receipt is globally ready only when every
evaluated gate passes; omitted gates remain visible so a downstream reviewer
can decide whether they were required.

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
