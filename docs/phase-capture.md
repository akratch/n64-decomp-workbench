# Phase capture, stream surgery, and replay

There is a point in a long campaign where the object diff stops being useful.
The residual is one word, every source family is exhausted, and the only honest
question left is *which pass owns this word*. That question is answerable, and
it is answered at the pass boundaries — not in C.

This page is the whole journey: retain the streams, read them, compare them,
edit one record, and replay the edit through the stock phases. Each step is a
product command, and each step's claim is bounded. The worked example is the
conditional-branch barrier from the cef4c endgame, recorded in
[the hotwash](history/postmortem-2026-08-24-cef4c-exact.md); the technique was
built ad hoc twice before it became these commands.

## The claim boundary, first

Everything below establishes **sufficiency downstream of the boundary you
patched**. An inserted Ucode record that produces the target object proves what
ugen and as1 do with that record. It does not prove that any C spelling
survives cfe and uopt and emits it. That is a second, separate hunt — but it is
a hunt with a known destination, which is the entire point of doing this work
first. In the cef4c campaign the barrier was proven `words=0` by stream surgery
a full session before a source spelling for it landed.

## 1. Retain the streams

IDO's driver hands each phase temporary files and deletes them on exit, so by
the time a build finishes there is nothing to read. `capture make` wraps the
phases so a normal build leaves every boundary on disk:

```sh
decomp-workbench capture make /path/to/ido/7.1 .decomp-workbench/capture
```

That writes `.decomp-workbench/capture/toolchain/` — one POSIX shell wrapper,
a phase-named symlink to it for `ugen`, `as0` and `as1`, the untouched binary
beside each as `<phase>.real`, and every other file from the IDO root carried
across (`--link` symlinks them instead of copying). A self-alias named after
the source directory (`7.1`) is added, so a build that spells its compiler root
`$(TOOLROOT)/7.1/ugen` keeps working against the capture copy.

Point the project's compiler root at that directory and build **one**
translation unit. Each wrapped phase execs the untouched binary, so the build's
bytes do not change; what changes is that each invocation leaves a run
directory behind:

```
.decomp-workbench/capture/captures/20260824-083209-19786-ugen/
    argv.txt            one `%03d <argument>` line per argument
    status.txt          the phase's exit status
    before-7-ctmoA0r9Qp the positional Ucode input, as ugen received it
    before-11-ctmstGP.. the symbol table, before ugen mutated it
    after-9-ctmc2PdRlS  the Binasm output ugen wrote
    after-13-ctmgtUjPyVL the -temp file
```

Set `WORKBENCH_CAPTURE_OFF=1` to pass straight through, and
`WORKBENCH_CAPTURE_ROOT` to send run directories elsewhere.

```sh
decomp-workbench capture runs .decomp-workbench/capture
```

```text
captures: .../capture/captures (2 run(s), 2 listed; {'as1': 1, 'ugen': 1})
20260824-083209-19786-ugen  ugen  rc=0   132.1K in  6 file(s)  ctmoA0r9Qp \
    output=ctmc2PdRlS symtab=ctmstGPhHvK temp=ctmgtUjPyVL
20260824-083209-19807-as1   as1   rc=0    88.4K in  5 file(s)  ctmc2PdRlS \
    output=unit.o symtab=ctmstGPhHvK
```

The argv column is the point. It names which argument was the input, which was
`-o`, and — critically — which was `-t`, the symbol table ugen mutates in place
and as1 then reads. A replay that reconstructs a plausible command line instead
of reusing this one is a replay whose failures are its own.

## 2. Read the streams

Two formats meet here, and mistaking one for the other costs an afternoon:

* **Ucode** — variable-width, big-endian, framed by an opcode byte. This is
  ugen's *positional input*, the stream uopt produced.
* **Binasm** — fixed 16-byte records. This is ugen's `-o` output *and* its
  `-temp` output, despite that generic option name.

Both decoders read a path or bytes, and both windows detect the format from
record framing:

```sh
decomp-workbench ucode window before-7-ctmoA0r9Qp --at 0x8d0 --radius 4
decomp-workbench binasm window after-9-ctmc2PdRlS --at 0x980
```

`--at` takes a byte offset or `#record-index`; an offset inside a record is
refused, with the nearest boundaries named. For the switch-shaped questions —
selector expression, XJP range, case table, trampoline chains — use
[`pass ucode`](pass-replay.md#inspect-a-retained-binary-ucode-switch); for
peephole-boundary questions use `pass binasm`.

Binasm records carry an `evidence` field. `calibrated` families were
established by assembling a probe listing through as0 and reading the record it
produced, by an as1 diagnostic naming the record's effect, or by a structural
pairing (the case table's section-switch/`.text` bracket). `inferred` families
were only ever observed with a payload that fits a familiar directive. `none`
means the record is left raw, which is always better evidence than a guess.

One framing trap is worth knowing: a float literal is an instruction record
whose fourth word is a **byte length**, followed by that many bytes of ASCII
digits spread over whole records. A decoder that walks 16 bytes at a time and
classifies on the opcode word reads `00e-05          ` as a record family. The
decoder frames those as `ascii-payload` instead.

## 3. Compare two boundaries

When a healing candidate and a stuck one differ, the difference is usually
visible one boundary earlier than the object:

```sh
decomp-workbench stream diff control.U candidate.U
```

```text
ucode: 2597 vs 2601 record(s); DIFFERENT; similarity=0.9992
records: delete=0, equal=2597, insert=4, replace=0
first divergence: insert at left #152 0x8d0 / right #152 0x8d0
```

The alignment is shift-tolerant, so one inserted record reads as one inserted
row rather than as every later record having moved. `--format` forces both
sides when detection would disagree, `--context` widens the equal rows shown,
and `--json` carries the same rows for automation.

## 4. Edit one record

`ucode patch` performs record-framed surgery and refuses to write a stream the
decoder cannot read back:

```sh
decomp-workbench ucode patch control.U \
  --insert-at 0x8d0 \
  --records '0x26680000,{fresh} | 0x42600000,{fresh},0,2' \
  --fresh-label \
  -o barrier.U
```

```text
ucode insert: at record #152 (0x8d0), removed 0 record(s), inserted 24 byte(s)
fresh labels: 143 (highest existing label 142)
  + Ufjp       26680000 0000008f  target=L143
  + Ulab       42600000 0000008f 00000000 00000002  label=L143
result: 41576 bytes, 2599 record(s) (+2), sha256=..., decodes=True
wrote: barrier.U
```

`--fresh-label` is what makes this safe without reading the whole stream: the
allocator scans every label operand the decoder establishes (`Ulab`, `Uldef`,
`Uujp`, `Ufjp`, `Utjp`, `Uclab`, and both `Uxjp` labels) and allocates above
the maximum. `{fresh+1}`, `{fresh+2}` … address further allocations.

The record spec is 32-bit words separated by whitespace or commas, records
separated by `|` or a blank line, `#` comments to end of line — or a path to a
file in the same syntax. When the spec groups its records, the groups must
match the framing the decoder recovers, so a four-word record cannot be split
into two by accident. `--replace N[:M]` and `--delete N[:M]` take record spans,
and patching a retained capture in place is refused.

## 5. Replay through the stock phases

```sh
decomp-workbench pass replay-ugen barrier.U \
  --toolchain .decomp-workbench/capture \
  --argv-from .decomp-workbench/capture/captures/20260824-083209-19786-ugen \
  -o barrier.o
```

The replay runs `ugen.real` and `as1.real` — the untouched binaries, never the
wrapper — with the captured argument shape: every optimization and target flag
in its original place, the positional input replaced by the stream being
replayed, and `-o`/`-t`/`-temp` pointed into a work directory. The symbol table
is seeded from the run's **entry** copy and handed to both phases in turn,
exactly as the driver did, because ugen mutates it and as1 reads what ugen
left. Missing temporaries are synthesized. Each phase runs at `nice 10` by
default.

The as1 argument shape is discovered by the only honest link between two run
directories: the as1 run whose positional input is this ugen run's `-o` file.
`--as1-argv-from` names it explicitly; `--skip-as1` stops at the Binasm
boundary.

### The fidelity gate

```sh
decomp-workbench pass replay-ugen before-7-ctmoA0r9Qp \
  --toolchain .decomp-workbench/capture \
  --argv-from .../20260824-083209-19786-ugen \
  --require-identical
```

```text
verify: replay reproduces the reference object byte for byte
```

Run this **before** trusting any patched variant. Replaying a capture's own
unmodified Ucode must reproduce that capture's object byte for byte; until it
does, a variant's object difference could belong to the harness rather than to
the patch. The verification defaults to the object the as1 run retained;
`--expect` names another. `--require-identical` turns the gate into an exit
status, and a mismatch is explained through `--objdump` rather than left as two
hashes.

## 6. Read the result like evidence

Score the replayed object the way any candidate is scored:

```sh
decomp-workbench compare target.o barrier.o --json
```

In the cef4c campaign that is where the endgame turned: a conditional
branch-to-next barrier inserted at one Ucode offset produced `words=0` while
the unconditional form produced nothing at all — which is itself a compiler
law. UGEN's branch-to-next eliminator removes at most two conditional branches
and unboundedly many unconditional ones, so three chained empty-body
conditional tests survive as exactly one removable branch, and as1 deletes it
only after its transient block boundary has already killed the copy fact.

Then, and only then, the source hunt: what C spelling makes cfe and uopt emit
that record naturally? The patch does not answer it. It makes the question
worth a session.

## What each rung claims

| Step | Claim | Not a claim |
|---|---|---|
| `capture make` / `capture runs` | these bytes crossed this boundary | nothing about why |
| `ucode`/`binasm window` | the stream contains these records | not which C emitted them |
| `stream diff` | these two boundaries differ here first | not which difference matters |
| `ucode patch` | the patched stream is well-framed | not that it is reachable |
| `pass replay-ugen` (unmodified) | the replay harness is faithful | nothing about the candidate |
| `pass replay-ugen` (patched) | this record is sufficient downstream | not that C can spell it |

## Related

* [Pass replay and static Binasm boundary inspection](pass-replay.md) — the
  as0/as1 listing replay, the generic pass adapter, and the two stream
  inspectors in detail.
* [Compiler instrumentation](compiler-instrumentation.md) — when the boundary
  streams are not enough and the pass itself has to be traced.
* [The cef4c hotwash](history/postmortem-2026-08-24-cef4c-exact.md) — the
  campaign these commands were extracted from.
