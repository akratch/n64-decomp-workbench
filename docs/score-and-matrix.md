# Score and matrix

Two commands for the last mile of a campaign: `score` answers "how far is
this candidate from the target," and `matrix` runs a batch of pipeline
variants and tells you which ones actually produced different bytes at all.

## Start here: one number

```sh
decomp-workbench score target.o candidate.o
```

```text
score: 516 words differ (0 = match)
target:    target.o
candidate: candidate.o

  words          516  <- the score
  aligned_total  516     one candidate only
  raw            561     never the score
```

The headline is **`words`**: positional word differences after masking
linker-controlled relocation fields. It is the function-level matching oracle
(`words=0` is the match) and the only one of the three counts that means the
same thing for two different candidates. Rank on it.

The other two are printed because they are useful, and labelled because they
are not the score:

| Count | What it is | Why it is not the score |
|---|---|---|
| `words` | positional word differences, relocation-masked | — it *is* the score |
| `aligned_total` | LCS-aligned rows a source change controls | once the aligner inserts gaps, a differently scheduled object realigns against a different subsequence, so its row count can fall *below* a strictly better candidate's |
| `raw` | every differing word, relocations included | includes linker-filled bits no source change moves, so on some pairs it can never reach zero |

When they disagree, `score` says so and says why, with the numbers:

```text
these numbers disagree, and here is why:
  - raw=561 exceeds words=516 by 45: 45 relocation-controlled word(s).
    The linker owns those bits, so raw cannot reach zero on this pair and
    words=0 is the honest gate.
```

Silence in that block is itself a claim: it means all three counts agree and
any of them would have ranked the candidate the same way.

`--verbose` explains what each metric measures inline. `--json` emits
`headline_metric`, `headline_value`, and `metric_disagreements` beside the
existing fields.

This mattered. Every stage of one campaign had to be told which number to
trust, and one of them spent 257 builds ordering a lever table by the wrong
one.

The rest of this page is the second form of `score`, which windows one
function's bytes against target bytes that live *outside* the pair -- a ROM
image, or an object whose symbols are named differently.

Both grew out of the same recurring failure during the SSB64 drawbitmap
campaign: the operator hand-wrote the same roughly-30-line scoring snippet
about ten times (objcopy the candidate's `.text`, window out one function,
compare word-for-word against bytes pulled from the retail ROM at a known
offset, mask relocation words from `objdump -r`, count differences, and check
a couple of "control" functions that were already known to match). Two real
bugs happened doing this by hand, and a third happened one level up, sweeping
many variants of it. All three are why these commands exist.

## Story 1: the hardcoded offset went stale

The hand-rolled snippet windowed the candidate function out of its object
with a literal byte offset (`0x38`, say) computed once and then reused across
several translation-unit edits. When the TU changed shape, the offset no
longer pointed at the function -- and the snippet kept running, silently
scoring garbage against the wrong bytes.

`score` never takes a numeric offset into the *candidate*. It always resolves
the function through the symbol table:

```sh
decomp-workbench score build/candidate.o \
  --function drawBitmap \
  --rom baserom.z64 \
  --rom-offset 0x8A3F20
```

```text
candidate: build/candidate.o
target: --rom baserom.z64 offset 0x8a3f20 size 128
drawBitmap (function): size 128/128, diff words 0 (+6 relocation-floor words)
verdict: MATCH
next: Diff words are zero outside the relocation floor and every control is
      clean. Run the project's normal link/ROM verification for the final
      proof.
```

The *target* side is still a numeric ROM offset -- there is no symbol table in
a raw ROM -- but the offset only has to be right once, and `--size` defaults
to the candidate function's own size, so a TU edit that changes instruction
count is visible as a size mismatch instead of a silent misread.

## Story 2: IDO strips local symbols

IDO does not emit symbol-table entries for `static` functions. A symbol
lookup for one of those returns nothing, and naive tooling built on top of
that lookup can report the whole file 100% different -- not because the
function does not match, but because the tool never found it in the first
place.

`--between` finds the same bytes without a symbol for the function itself, by
using the two functions IDO *did* keep around it:

```sh
decomp-workbench score build/candidate.o \
  --between visibleFuncBefore,visibleFuncAfter \
  --rom baserom.z64 \
  --rom-offset 0x8A4010
```

```text
candidate: build/candidate.o
target: --rom baserom.z64 offset 0x8a4010 size 64
visibleFuncBefore..visibleFuncAfter (between): size 64/64, diff words 3 (+0 relocation-floor words)
  note: IDO strips local (static) function symbols from the object's symbol
  table, so --function cannot find them; --between locates the bytes between
  two surrounding symbols IDO did keep.
verdict: MISMATCH
next: The target came from raw ROM bytes, so `diagnose` needs a comparable
      target object to run against; export one, or run `decomp-workbench
      guide <verdict>` for lever guidance on the remaining diff words.
```

The note is always printed alongside a `--between` result, not just in
`--help`: a reader who has never hit the stripped-symbol problem should not
have to go looking for why the flag exists. And if you pass a plain
`--function` for a symbol that turns out to be stripped, the error says so
directly:

```text
error: symbol 'staticHelper' produced no instructions in build/candidate.o
  If 'staticHelper' is a local/static function, IDO may have stripped its
  symbol from the table -- try --between with the two symbols that surround
  it.
```

## Story 3: your lever changed something it must not touch

A causal probe (a compiler flag, a force spec, a source rewrite) is supposed
to change one function. `--control` checks that it did not also change a
function that already matched, by scoring it the same way:

```sh
decomp-workbench score build/candidate.o \
  --function drawBitmap \
  --rom baserom.z64 --rom-offset 0x8A3F20 \
  --control siblingA@0x8A4200:64 \
  --control siblingB@0x8A4400
```

Any control with a nonzero non-relocation diff marks the whole run
`CONTROLS BROKEN`, prominently, in both the terminal and `--json`:

```text
controls: 2 checked
  siblingA (function): size 64/64, diff words 0 (+2 relocation-floor words) OK
  siblingB (function): size 96/96, diff words 4 (+0 relocation-floor words) BROKEN
verdict: MISMATCH (CONTROLS BROKEN)
next: CONTROLS BROKEN: a control function that used to match no longer does.
      Your lever changed something it must not touch -- revert it and narrow
      the change before trusting the function score below.
```

`score` exits `0` only when the function under test matches *and* every
control is clean, so it composes in a shell loop:

```sh
for candidate in build/variant-*.o; do
  decomp-workbench score "$candidate" --function drawBitmap \
    --rom baserom.z64 --rom-offset 0x8A3F20 \
    --control siblingA@0x8A4200:64 \
    || echo "REJECTED: $candidate"
done
```

## Story 4: eleven outputs, one byte pattern

A compiler-era sweep once ran eleven differently-flagged pipeline variants
and got eleven outputs that were byte-identical -- because several of the
flags were unknown to that toolchain build and silently fell back to
defaults, and the stderr that said so was being suppressed downstream. The
sweep concluded "this axis is exhausted." It was not; the axis had never
actually been tried past the first working flag.

`matrix` runs a batch of variants and clusters their results by output byte
identity into lettered **attractors**, ordered by score (`A` is the closest
match), and never discards a variant's stderr:

```sh
decomp-workbench matrix compiler-era-sweep.json --run-dir .decomp-workbench/matrix/run1
```

A spec file names each variant's command and the scoring target once, shared
across every variant:

```json
{
  "variants": [
    { "label": "ido-5.3-r4000", "command": "./compile.sh --era 5.3 --cpu r4000 $OUTPUT" },
    { "label": "ido-5.3-r4300", "command": "./compile.sh --era 5.3 --cpu r4300 $OUTPUT" },
    { "label": "ido-7.1-r4000", "command": "./compile.sh --era 7.1 --cpu r4000 $OUTPUT" }
  ],
  "score": {
    "function": "drawBitmap",
    "rom": "baserom.z64",
    "rom_offset": "0x8A3F20"
  }
}
```

`$OUTPUT` is substituted with a per-variant object path before the command
runs. The `"score"` object accepts the same options as `score`'s flags,
spelled as JSON keys: `function` or `between` (a two-item array), exactly one
of `target_object` or `rom` (with `rom_offset` and optional `size`), and
`controls` (an array of `"NAME@0xOFFSET[:SIZE]"` or bare `"NAME"` strings).

```text
run directory (logs never discarded): .decomp-workbench/matrix/run1
3 variant(s), 3 scored, 2 attractor(s)
ATTR  DIFF  MEMBERS
A        0  ido-5.3-r4000, ido-5.3-r4300
B       12  ido-7.1-r4000

NOTE: attractor A contains 2 differently-labeled variants that produced
identical bytes: ido-5.3-r4000, ido-5.3-r4300

next: decomp-workbench guide <verdict> for any remaining lever work
```

Two differently-labeled variants landing in the same attractor is called out
by name, not just implied by the table. If **every** variant collapses into
one attractor, the caution is explicit rather than a table you have to notice
is short:

```text
CAUTION: every variant produced identical bytes -- verify the flags are
actually accepted (this exact failure produced a wrong conclusion in the
SSB64 drawbitmap campaign).
```

`matrix` also scans every variant's stderr for the usual silent-fallback
wording (`unknown option`, `ignored`, `unrecognized`) and surfaces the first
matching line next to the variant's label, so a flag that quietly fell back
to a default looks different from a flag that was genuinely accepted and had
no effect:

```text
stderr warnings (possible silent flag fallback):
  ido-7.1-r4000: cc: warning: unknown option '-r4000', ignored
```

Every variant's full stdout and stderr are written under the run directory
(`<run-dir>/logs/<label>.stdout.log` / `.stderr.log`), and the produced
objects under `<run-dir>/objects/`, so nothing about a run has to be
reproduced from memory afterward. `matrix` prints that directory on every
run, human or `--json`.

## Reference

### `score`

```
decomp-workbench score CANDIDATE.o
  (--function NAME | --symbol NAME | --between SYMA,SYMB)
  (--target-object TARGET.o | --rom FILE --rom-offset 0xNNN [--size N])
  [--control NAME[@0xOFFSET[:SIZE]] ...]
  [--objdump PATH] [--section .text] [--json]
```

* Exactly one of `--function`/`--symbol` or `--between` selects the
  candidate function.
* Exactly one of `--target-object` or `--rom` supplies target bytes.
  `--target-object` reuses `--function`/`--between` against that object too;
  `--rom` reads raw big-endian bytes at `--rom-offset`, sized `--size`
  (default: the candidate function's own size).
* `--control` is repeatable. With `--rom`, write `NAME@0xOFFSET[:SIZE]`; with
  `--target-object`, write the bare symbol `NAME`.
* Exit code `0` when the function matches (zero non-relocation diff words)
  and every control is clean; `1` otherwise; `2` for a usage or input error
  (missing file, bad offset, unresolved symbol).

### `matrix`

```
decomp-workbench matrix SPEC.json [--run-dir DIR] [--timeout SECONDS] [--json]
```

* `SPEC.json` has a `"variants"` array (`label`, `command` with a literal
  `$OUTPUT` placeholder) and a `"score"` object using the same selection
  rules as `score`'s flags.
* `--run-dir` defaults to `.decomp-workbench/matrix/<timestamp>`; it holds
  every produced object and every variant's complete stdout/stderr.
* Exit code `1` only when no variant produced a scorable object at all
  (a usage-level "no usable rows," same convention as `rank`); `0`
  otherwise, so a mismatch or a broken control among the variants is still
  worth reading in the attractor table rather than treated as command
  failure. `2` for a spec file that does not exist or does not parse.

## The screen line

Both forms of `score` print one line carrying the four facts a sweep reads per
object -- the object's identity, its real instruction count, its frame, its
float load and store traffic (narrowed with `--slot OFFSET`), and the ring
coset it sits at relative to the target:

```
screen: sha=10e37dc2dc12 ni=4641 frame=-1704 ld1184=2 st1184=1 coset=id
```

A non-identity coset prints the caution beside it, because a ring-quotienting
scorer reads a rotated object as far closer than it is. See
[Shift-tolerant diffs and the ring phase](shift-and-phase.md).
