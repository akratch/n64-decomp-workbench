# Shiftability

Two commands for the question that only starts once a project is matched:
**which words in this ROM are not explained by a symbol reference?**
`shift audit` is the static inventory — one map, one image, one pass, no
build. `shift rehearse` is the empirical referee — the same objects linked
twice against linker scripts that differ by an inserted pad, with every byte
of the difference explained.

They exist because the matching gate cannot answer that question, and cannot
be made to.

## Matching is a point property; shiftability is a neighborhood property

A decomp is **matching** when its build reproduces the ROM byte-for-byte at
the original layout. It is **shiftable** when you can insert, remove, or
resize code and data and the rebuilt ROM still works — because every address
the ROM contains was produced by a linker-resolved symbol reference, so when
things move, the values move with them.

A matched build proves the bytes at one layout. A shiftable build proves the
*references*: that the build is still correct in a neighborhood of layouts,
not only at the point you measured. A hardcoded pointer is the difference —
correct today, wrong the moment anything above it moves.

The matching gate is blind to that difference **by construction**. A literal
`0x80123456` and a linker-resolved symbol that lives at `0x80123456` produce
the same four bytes in the final image. A linked N64 ROM keeps no relocations,
so there is nothing left in the image that says which one you wrote. Byte
identity cannot distinguish provenance, and no amount of byte identity ever
will.

That is not a hypothetical. In this campaign's gate, a one-line hardcoded
pointer was injected into a 100%-matched project and the project's own
verifier reported `Verify: OK` against the retail cartridge — byte-identical,
independently `cmp`-confirmed. See the walkthrough below, and
[Trap 7](metric-traps.md#trap-7-byte-identity-does-not-prove-address-provenance).

It is also not a solved problem elsewhere. splat's own wiki names
shiftability and offers hand-written per-address override files; splat,
spimdisasm and mapfile_parser audit none of it; and no N64 decompilation
project runs a shiftability check in CI — papermario, zeldaret/oot and mk64
workflow files were fetched and grepped, with zero hits. Shiftability is
everywhere a manually-invoked opt-in build config maintained by convention
and periodic bug-hunting.

## Which command answers what

| Question | Command | What it needs |
|---|---|---|
| Where do my project's pinned addresses come from — the layout, or a number somebody typed? | `shift audit` | one `ld -Map`, one linked image, the project's own symbol files |
| Which words in the image are shaped like an address into the region an insertion would move? | `shift audit` | the same; no build, no ROM re-link |
| Which of those references does a real shift actually move? | `shift rehearse` | two links of the *same objects*, or a relink script |
| Did anything change that no class explains? | `shift rehearse` | the same |
| Did a checksum-protected function's body change without its checksum? | `shift rehearse --checksum-pair` | the pairs your build patches |

The division is the point. The audit ranks **how confidently a word is an
address reference**. It never ranks how dangerous a word is, because from one
image it cannot: a resolved pointer and a typed-in constant are the same
bytes. Only a relink separates them, and that is the rehearsal's whole job.

## `shift audit` — the static inventory

```sh
decomp-workbench shift audit \
  --map build/us/v77/dkr.us.v77.map \
  --image build/us/v77/dkr.us.v77.z64 \
  --pins ver/symbols/undefined_syms.txt \
  --blob .boot --blob .assets_lut --blob .assets \
  --whitelist boot-globals.txt
```

Two halves.

**The pin half** reads the project's own linker-input symbol files —
`undefined_syms.txt`, splat's `symbol_addrs` (`--symbol-addrs`) — and sorts
every assignment into four classes:

| Class | What it is |
|---|---|
| `derived` | the right-hand side names a symbol (`gMainMemoryPool = main_BSS_END`). Healthy by construction: whatever the linker decides, this follows |
| `authentic-fixed` | an absolute address the console fixes, not the project — a `kseg1` hardware register, or an address on your whitelist |
| `artifact-suspect` | an absolute address in a window the project itself owns: a bare `kseg0` RAM address, or the `0xB0000000` cart domain |
| `unclassified` | an absolute value in no window the model names, or an expression the reader could not fold. Reported as itself rather than guessed |

The whitelist is a file, it is yours, and every entry needs a reason:

```
# N64 boot globals and the fixed entrypoint: written by the boot ROM
# before any of this project runs.
0x80000300-0x80000400 boot globals (osTvType..osAppNMIBuffer) and the entrypoint
```

The high bound is inclusive, so that one range covers the entrypoint too.

Nothing is whitelisted by default. The libultra boot globals at `0x80000300`
are as fixed as a hardware register, and are distinguishable from an artifact
only by somebody saying so — an address with no reason attached is one
somebody has to re-derive later, so the parser refuses it.

**The scan half** reads the image's data, blob and header regions word by
word and reports every value that lands inside the *movable window* — the
VRAM range an insertion would push. Text is placed and counted but never
scanned: an instruction's address arithmetic is split across a `lui`/`%lo`
pair and does not exist as a single word, so only a relink resolves it.

`--blob` marks an output section opaque: scanned, but never split by its
input records and never attributed to a symbol. Use it for DMA'd asset
segments and boot code, whose VMA is a load target rather than a place code
lives. That refusal is a correction the campaign paid for — the hand-rolled
spike attributed every ROM offset through `.main`'s VRAM mapping and came
back naming asset bytes `gAudioHeapStack+0x...`, which they are not.

### Tiers rank address-likelihood, never hazard

Each surviving hit is scored by where it lives plus a bonus for landing
exactly on a symbol's start, and the score picks the tier. Before that, five
**suppressors** are terminal — each one is a reason the word is not an
address at all, and each was derived from a false-positive family measured on
a real ROM, not imagined:

| Suppressor | The family it came from |
|---|---|
| `misaligned` | the retail data image carries build-machine leftovers holding odd-valued "pointers" |
| `progression-cluster` | three or more hits at one constant stride whose values form an arithmetic progression: packed shorts in a menu struct |
| `repeated-value` | one struct constant counted many times, not that many references |
| `round-constant` | a fixed-point table value (`gSineTable+0x7fc = 0x80008000`) |
| `whitelisted` | you declared it authentic, with a reason |

So: **compiled data landing on a symbol start** is `high`; compiled data
alone, or a blob resident pointing at a symbol start, is `medium`; anything a
suppressor caught is `low`. The rules, the thresholds and the residence
scores all travel inside the JSON report, so a reader can see the rule rather
than infer it.

Calibrated rather than asserted: run against the reference project and then
checked against a real shift, all 38 `high` hits and 650 of the 657 `medium`
ones are words the shift actually moved — real references, every one. The
`low` tier is where the ambiguity lives, which is what a suppressor is for.

## `shift rehearse` — the empirical referee

Two modes. `analyze` explains two links you already have; `orchestrate`
produces them by calling your own relink script and then analyzes each.

```sh
decomp-workbench shift rehearse analyze \
  --base-map base/dkr.us.v77.map --base-image base/dkr.us.v77.z64 \
  --shifted-map shift-0x10/dkr.us.v77.map --shifted-image shift-0x10/dkr.us.v77.z64 \
  --delta 0x10 \
  --blob .boot --blob .assets_lut --blob .assets \
  --crc-words 0x10,0x14
```

**Pairing is corrected, not positional.** Words below the insertion compare
positionally; words at or above it compare against the shifted image offset
by delta. The spike measured what the naive alternative costs on an 11 MB
image: about 2.8 million differing words instead of 20,687.

**The insertion point is derived.** A ROM offset typed one word wrong
silently reclassifies the entire image, so the anchor is read out of the two
maps — the lowest in-window VRAM at which shared symbols begin differing by
delta — and the report prints `anchor_source=auto` beside the highest
in-window address a shared symbol kept, which is the other side of the
bracket. `--anchor SYMBOL` overrides it when you would rather name one.

Every changed word is classified — 26-bit jump targets, `%hi`/`%lo` halves,
absolute pointers, CRC and checksum storage — and every changed word that
fits no class is `unexplained`. **That count is the gate.** A word that
changed for a reason no class accounts for means either the census is wrong
or the build was not the controlled experiment it claims to be.

Every address-shaped word that did *not* change is judged against the audit's
own tiers. The merge is the whole reason to run both halves:

| Static tier | Moved | Did not move |
|---|---|---|
| `high` | `tracks` — a healthy reference | **`stale-confirmed`** — the finding |
| `medium` | `tracks` | `stale-review` — a queue |
| `low` | `tracks` | `noise` — the measured false-positive floor |

A word that changed by something other than the delta is `changed-other` at
any tier: an address-shaped word that moved by the wrong amount is a third
question, and no tier makes it benign.

### `orchestrate` and the wrapper contract

```sh
decomp-workbench shift rehearse orchestrate \
  --wrapper tools/relink.sh \
  --ld-script mods/dkr.custom.ld \
  --anchor-object build/us/v77/src/hasm/entrypoint.s.o \
  --deltas 0x10,0x40 \
  --workdir .workbench/rehearsal \
  --image-name dkr.us.v77.z64 --map-name dkr.us.v77.map \
  --blob .boot --blob .assets_lut --blob .assets \
  --crc-words 0x10,0x14 \
  --census unexplained_changed=0,stale_confirmed=0
```

The one part you implement is the wrapper. It is invoked as
`SCRIPT LDSCRIPT_PATH OUT_DIR` and must leave the linked image and its
`ld -Map` file in `OUT_DIR` under the names you gave `--image-name` and
`--map-name`. **It should relink only.** The objects are this experiment's
controlled constant; rebuilding them changes the question. On the reference
project a relink is seconds per delta — delete the link products, override
`LD_SCRIPT`, done — where a rebuild is minutes and a different comparison.

The pad is one line, `. += DELTA;`, inserted directly after the object you
name with `--anchor-object`. Exactly one line of the script may mention that
object: zero is a typo and two is ambiguous, and both refuse before anything
is built. Every padded script is generated before any build runs, and the
base build uses your script unmodified.

**Two deltas, not one.** A partially symbolized reference can encode
correctly at one shift by coincidence and cannot at two — the 2021 bug class
below is exactly that shape. Any class count that differs between deltas is
reported as a finding in its own right.

`--census` turns the report into an exit code (`3` when a predicate is
false), which is what puts `unexplained_changed=0,stale_confirmed=0` in a
project's CI.

### The checksum-consistency rule

Some N64 games checksum their own code at runtime. The reference project
embeds, for a handful of hand-picked functions, a byte-sum of that function's
own compiled bytes, and a post-link build step recomputes each one from the
map and patches it into the ROM. In 2021 one audio function was left off that
step's allowlist; under a shift its bytes changed, its frozen checksum did
not, the game's own runtime self-check failed, and the symptom was reported
as "cursed audio."

Neither a static scan nor a generic stale-word detector can see that. The
word holds a byte-sum, not an address — there is nothing for either mechanism
to key off. What it maps onto is one nameable rule:

> If any word inside a protected function's body changed, that function's
> checksum word must have changed too.

`--checksum-pair FUNCTION=VARIABLE` declares one pair, repeatably, and every
pair reports a status — passes included, with the basis it passed on:

| Status | Meaning |
|---|---|
| `pass` | body and checksum agree: the shift touched neither (`inert`) or changed both (`tracked`) |
| `checksum-stale` | the body changed and the checksum word did not — the cursed-audio class |
| `checksum-orphan` | the checksum changed and the body did not: either the extent read from the map is wrong, or the word is not what it is named |
| `unresolved` | a named symbol is missing from the map, has no ROM placement, or has no extent the map can bound — reported rather than skipped |

**Read a `checksum-stale` verdict alongside whether the project compiles its
runtime check in at all.** On the reference project, the shift-mode build
selects a `no_verify` target, so the post-link patcher never runs — and the
matching branch is the only one that defines `ANTI_TAMPER=1`, so the runtime
self-check is compiled out of mod builds entirely. The rule fires correctly
on those images and the finding is harmless by design. That combination is
exactly the 2021 precondition, and it is why the verdict is evidence about
your build chain rather than a verdict about your ROM: a rehearsal harness
should run the project's full post-link chain, or expect and explain this
class. With the patcher run post-link, the same four pairs come back
`pass`/`tracked` with bodies that changed 71, 90, 11 and 6 words.

## A worked walkthrough: catching a bug the retail verifier could not

The campaign's gate was a controlled experiment on a finished decomp — Diddy
Kong Racing, 100.00% across all five ROM versions as of 2026-07-25, and the
most shiftability-mature 100% N64 decomp the survey behind these commands
found: dual linker scripts, a cascade script for mod builds, derived
`undefined_syms`, symbol-relative asset addressing, and build-time asset
regeneration, all engineered in from June 2021.

The archaeology of that project's own 2021 shift-hardening found the dominant
historical bug class — a global pointer initialized from a raw RAM address
instead of `&symbol`, independently rediscovered three times in the campaign's
first pull request. None of the nine fixes reverts onto today's tree (every
file has been renamed, matched-and-deleted or reorganized in the intervening
five years), so the gate synthesized the class instead. One line, in one
matched source file:

```c
SoundPlayer *gSoundPlayerPtr = &gSoundPlayer;               /* before */
SoundPlayer *gSoundPlayerPtr = (SoundPlayer *) 0x80110470;  /* after  */
```

The address was read out of the project's own build map, so it is the correct
value — today.

**First, what every existing gate said about it.** The bugged shift-mode
build was byte-identical to the clean one (`cmp` clean). The bugged
**matching** build was byte-identical to the retail cartridge: CRCs good, the
project's own `Verify: OK`, plus an independent `cmp` against the baserom. A
100%-verified matched build carried a shift bug and nothing in the ecosystem
had a way to say so.

**What the audit said.** The pin half reconciles the project exactly — 66
pins, 7 derived, 57 authentic once the boot globals are whitelisted, and
exactly 2 artifact-suspect, which are the two cart-domain fakes the project's
own file labels as fakes in a comment. The scan half ranks 3,443 hits: 38
`high`, 657 `medium`, 2,748 `low`. The injected word is in the `high` list,
by name:

```text
hits (3 of 3,443, --limit)
rom       value       tier  rule    region  resident_symbol       target_symbol
0x0d18f8  0x800e0640  high  scored  .main   main_DATA_START+0x18  __BSS_SECTION_START
0x0d29dc  0x80110470  high  scored  .main   gSoundPlayerPtr       gSoundPlayer
0x0d4430  0x800d3780  high  scored  .main   gContPakStrings+0x14  gContPakDiffContStrings
```

Read that honestly: the audit ranked it `high` because it is a word in
compiled data landing exactly on a symbol's start. So did the two rows around
it, and those two are *healthy references*. The audit has not caught
anything yet. It has produced a ranked list of candidates worth relinking
for.

**What the rehearsal said.** Relink base and shifted at delta `0x10` and
compare:

```text
unexplained_changed=0  stale_confirmed=1  findings=1

classes
label         count
abs32-tracks  1,941
crc-header    2
j26-tracks    8,101
lo16-tracks   10,642

tier_verdicts
tier    verdict        count  outcome
high    moved          37     tracks
high    unmoved        1      stale-confirmed
high    changed-other  0      changed-other
medium  moved          650    tracks
medium  unmoved        7      stale-review
medium  changed-other  0      changed-other
low     moved          1,254  tracks
low     unmoved        1,494  noise
low     changed-other  0      changed-other

stale (2 of 1,502, --limit)
rom       value       tier    rule    outcome          region  target_symbol
0x0d29dc  0x80110470  high    scored  stale-confirmed  .main   gSoundPlayer
0x0d18e8  0x80100400  medium  scored  stale-review     .main   gAudioHeapStack+0x1dcb0
```

One word. The right one. Named. `unexplained_changed=0`, so the rest of the
20,686-word difference is fully explained and nothing else fired. The whole
bug is visible in the arithmetic: 37 of the 38 `high` words moved, and the
one absolute-pointer class dropped from 1,942 to 1,941 — the missing tracker
is sitting in the unmoved column instead.

**Then the control.** Revert the one line, rebuild the pair, and the same
command says `stale_confirmed=0, findings=0`. Fire on the bug, silent on
health — both directions measured, on real builds, not asserted.

That is the demonstration you can run on your own tree.

## Reading the report

**The tier rules are data, and they ship inside the report.** `--json`
carries `tier_rules`, `tier_thresholds`, `residence_scores` and `merge_tiers`
beside the counts. When a hit is ranked somewhere you disagree with, read the
rule that ranked it rather than arguing with the label. Every reported metric
is in `--explain-keys` for both commands.

**`stale-review` is a queue, not a headline.** The seven medium-tier unmoved
words in the walkthrough are identical in the bugged run and the clean
positive control: they are the project's standing review queue, not
consequences of the injected bug. Calibration puts 650 of 657 `medium` hits
among the words a real shift moved, so the ones that stay put are worth a
look and not an alarm. Only `stale_confirmed` and `unexplained_changed` are
headline numbers, and both are printed as a pair for that reason.

**The noise floor is real, and it was measured rather than assumed.** 1,494
low-tier words hold values that look like addresses into the moved region and
never move, on a build that is correct. They are packed shorts, fixed-point
table values, one struct constant counted many times, boot-blob bytes that
pattern-match, and Rare's own build-machine leftovers faithfully reproduced
in the retail data image. A tool that reported those as findings would be
reporting 1,501 findings on a healthy ROM, which is the failure mode that
made hand-labeling "just too much effort" on the one N64 project that tried
it. Cross-checking a second delta does **not** shrink this set — a
value-shaped coincidence is delta-invariant. Location and residence are the
discriminators; more deltas are for validating the *tracking* classes.

**`stale_unattributed`** counts stale candidates the static scan never saw
because they sit in a region it does not scan. They are reported rather than
absorbed into a nicer number.

## Where hardcoded addresses hide, and which half reaches each

| Hiding place | Reached by |
|---|---|
| Absolute symbol pins in linker inputs | `shift audit`, pin half — and the rehearsal converts them mechanically: an absolutely-defined symbol cannot track a shift, so every reference through one self-identifies |
| Raw address literals in C and in data | `shift audit` scan ranks them; `shift rehearse` convicts or clears them |
| Pointer values inside `incbin` blobs | scanned as blob residents (never symbol-named); the rehearsal is the only thing that can convict one |
| Unmigrated asm `.word`s and split `%hi`/literal-`%lo` pairs | `shift rehearse` only. A bare 16-bit offset is indistinguishable from a legitimate struct-member offset in a linked image, and the effective address never exists as one word |
| Hardcoded ROM offsets in DMA/asset tables | not a value class either command models — a ROM offset is not inside the movable VRAM window |
| Segmented pointers inside assets (display lists, geo layouts) | nothing here reaches them; see the boundaries below |

The fourth row is the one the archaeology argued hardest for. In 2021 the
project shipped four fixes whose whole content was turning a raw hex offset
into `%lo(symbol)` — code that assembled to **byte-identical output before
the shift**, because the literal happened to equal the symbol's low half in
that one layout. No single-build check, static or dynamic, can see that
class. Only a differential relink can, and only if it reconstructs `hi`/`lo`
pairs rather than scanning single words — which is why the rehearsal
classifies `lo16` and `j26` movement separately, and why it wants two deltas.

## What these commands refuse to claim

- **No behavioral verification.** Nothing here boots a shifted ROM. Full
  shiftability's referee is that the shifted image *runs*, and that needs an
  emulator oracle, which is outside this package's boundary. The strongest
  static referee — every changed word explained, every unmoved
  address-shaped word judged — is what these commands own, and the hand-off
  is documented rather than papered over.
- **No verdict about your project.** Both headline numbers are counts with
  coordinates attached. `stale_confirmed` is the strongest *available*
  evidence for a hardcoded pointer and is still evidence: read the ROM
  offset, the value and the named target, not the label.
- **No symbol names inside blobs.** A DMA'd segment's VMA is a load target,
  not a place code lives, so a blob finding reports its region and its
  value and stops there. Attributing blob offsets through a code section's
  mapping is a specific mistake this campaign made once and corrected.
- **No conviction from a linked image alone.** A linked ROM keeps no
  relocations, so the audit's tiers cannot convict anything, and the page
  they print says so on every run. The rehearsal convicts.
- **No verdicts from shape.** Detection has false positives in both
  directions — one non-N64 toolchain over-eagerly treated ordinary data
  words as pointers and emitted spurious relocations that themselves broke
  shifted builds. Findings carry evidence and a rule; empirical movement
  outranks every static signal.
- **No fixes.** The tools inventory and verify. Migrating data, placing
  symbols and removing pins is real decomp work. The promise is a complete,
  honest, finite queue — not automatic shiftability.
- **No object-level relocation scanning yet**, and no per-game asset format
  parsing. Both are named increments, not silent gaps.

## See also

- [Trap 7: byte-identity does not prove address provenance](metric-traps.md#trap-7-byte-identity-does-not-prove-address-provenance)
  — the same finding as a measurement trap, with the incident.
- [Shift-tolerant diffs and the ring phase](shift-and-phase.md) — the
  function-level relatives of the corrected pairing this page does at whole-image scale.
- [JSON contracts](json-contracts.md) — `--json`, `--census` and the exit
  codes a CI gate reads.
- [Shared notes](shared-notes.md) and [Candidate campaigns](campaigns.md) —
  a real shiftability pass is a multi-week, multi-agent grind, and the
  durable-state machinery already exists.
- [Product status](product-status.md) — the implemented surface and the
  intentional boundaries, in one place.
