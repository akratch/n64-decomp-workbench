# The shiftability campaign

[Shiftability](shiftability.md) explains what the four `shift` commands
measure and why the matching gate cannot. This page is the other half: the
campaign you run to take a matched project from *nobody has ever asked* to
*every address in this ROM is a reference, and here is the finite list of the
ones that are not.*

It is written from a real one, run end to end on the pilotwings64
decompilation — 100% matched, `sha1 ec771aedf54ee1b214c25404fb4ec51cfd43191a`,
a project that had never planned for a shift. Every number and every
transcript below came off that tree, off banjo-kazooie's, or off the reference
project's, on the day this page was written. Where a step cost an hour that a
different order would have saved, the page says so.

**The headline is the opposite of a scandal, and it is a stronger result.**
pilotwings64 was **one line** of linker configuration away from a
shift-capable build. Relinked against a padded script at two independent
deltas it produced **zero unexplained changed words**. Its single
high-confidence stale reference was not a pointer Nintendo baked into the
cartridge — it was a redundant pin in the *decompilation's own* generated
symbol file, and deleting it left the ROM byte-identical. A matched N64
decomp's shift surface is mostly configuration, it is enumerable, and it is
fixable without touching matched code. You will not know that about your
project until you measure it.

## The shape of the campaign

| Phase | You are asking | Command | Costs |
|---|---|---|---|
| 0 | do I have the right inputs | `grep`, your build | one minute |
| 1 | where are my addresses written down | `shift audit` | one second, no build |
| 2 | can this project link symbolically at all | splat/`ld`, `shift config verify` | an afternoon, once |
| 3 | which references does a real shift move | `shift rehearse` | seconds per delta |
| 4 | what is the finite list of work | `shift plan` | one second |
| 5 | is it done, and does it stay done | the loop, `--census` in CI | forever, cheaply |

Phases 0, 1 and 4 need nothing but a map and an image. Phase 2 is the only
one that costs real thinking, it is a one-time cost, and on pilotwings64 it
was a single YAML line.

---

## Phase 0 — know your inputs

Three input mistakes will waste your afternoon before you have measured
anything. All three are cheap to rule out.

### 0.1 The one-second diagnosis

Before you touch a linker script, count the absolute addresses in the script
your build actually feeds to `ld`:

```
$ grep -cE '0x[0-9A-Fa-f]{4,}' build/pilotwings64.us.ld
15
$ grep -nE '0x[0-9A-Fa-f]{4,}' build/pilotwings64.us.ld | grep -v FILL
34:    .entry 0x80200050 : AT(entry_ROM_START) SUBALIGN(16)
829:    .app 0x802CA900 : AT(app_ROM_START) SUBALIGN(16)
```

Thirteen of the fifteen hits are `FILL(0x00000000)`. **Two** output sections
in the whole 59 KB script are pinned to an absolute VRAM address, and one of
them is the entrypoint, which *has* to be pinned because the ROM header's
boot address refers to it. The entire shift blocker in pilotwings64's linker
script is line 829.

That matters because the worry going in was the opposite. pilotwings64's
splat config carries 140-plus per-file `- { type: .bss, vram: 0x… }`
subsegments, and they look like 140 pins. They are not: splat consumes those
during *disassembly*, to name and place symbols, and never emits them into
the linker script. Every per-file bss input lands inside one `.kernel_bss` /
`.app_bss` output section that starts wherever `.` happens to be, and they
shift for free.

> **Count the absolute addresses in your *generated script*, not the `vram:`
> keys in your YAML.** They are different populations and only the first one
> blocks a shift.

Banjo-Kazooie reads the same way and answers differently:

```
$ grep -cE '0x[0-9A-Fa-f]{4,}' banjo.ld
48
$ grep -nE '0x[0-9A-Fa-f]{4,}' banjo.ld | grep -v FILL
20:    .boot 0xA4000040 : AT(boot_ROM_START) SUBALIGN(16)
38:    .entry 0x80000400 : AT(entry_ROM_START) SUBALIGN(16)
75:    .boot_bk_boot 0x80000450 : AT(boot_bk_boot_ROM_START) SUBALIGN(16)
271:    .core1 0x8023DA20 : AT(core1_ROM_START) SUBALIGN(4)
```

Four pins across 3,802 lines, and everything downstream of `.core1` is
*already* symbolic — `.core2 core1_VRAM_END`, and all fourteen overlays at
`.CC core2_VRAM_END`. Two of the four are as immovable as pilotwings64's
entrypoint: `.entry`, and `.boot` at `0xA4000040`, which is SP DMEM and an
address the console fixes rather than the layout. Two projects, two `grep`s,
and before you have built anything you know one of them has a one-line problem
and the other has two candidate lines and a decision about `.core1`.

### 0.2 If your build does not emit a map

Every command on this page reads a GNU `ld -Map` file. If your build does not
write one, add it to your link line — `-Map $(BUILD_DIR)/$(BASENAME).map` —
and rebuild. It costs a relink and changes no output bytes: the map is a side
report, not an input.

While you are in there, read the `ld` line itself, because Phase 1 needs it.
On a make-driven project, `make -n` prints the commands without running them —
but a matched project is a *built* project, so plain `make -n` prints nothing
but the final `sha1sum -c` and you learn nothing. Force it to print the whole
recipe and pull the link line out:

```
$ make -Bn | grep -- -Map
mips-linux-gnu-ld -T <script> \
  -T config/us/sym/hardware_regs.ld -T config/us/sym/pif_syms.ld \
  -T config/us/sym/libultra_undefined_syms.txt \
  -T build/splat_out/us/undefined_funcs_auto.txt \
  -T build/splat_out/us/undefined_syms_auto.txt \
  -Map <map> --no-check-sections -o <elf>
```

(One line in the real output; wrapped here to read.)

**That `-T` list is the complete set of files that can pin an address in your
project.** Nothing else reaches the linker. Write it down; it is Phase 1's
argument list, and Phase 2 will need to know that `-n` route exists anyway.

### 0.3 Which image — the compressed-game rule

**Audit the uncompressed linked image, never the retail cartridge, whenever
your project compresses segments after linking.** The map's `AT()` load
addresses describe the layout `ld` produced. If your build then rzip- or
gzip-compresses whole segments into the shipped ROM, every ROM offset in that
map describes a file that no longer exists at those offsets, and every address
you read out of the shipped image is read from the wrong place.

The failure symptom is loud, because the command refuses rather than
reporting nonsense. Point the audit at banjo-kazooie's shipped 16 MB ROM
instead of its 17.5 MB uncompressed link and you get:

```
error: 30 of 44 placed regions land past the end of the image -- that is not an overlay quirk, that is the wrong image (regions_unplaced_past_eof=30, placed_regions=44, image_bytes=16,777,216, map_placed_extent=16,981,856, map=build/us.v10/banjo.us.v10.map, image=build/us.v10/banjo.us.v10.z64)
```

Exit status 2. The right image is
`build/us.v10/banjo.us.v10.uncompressed.z64`, which the build already
produces on the way to the cartridge. If your project's names differ, the
one you want is the direct output of the link step, before any packing pass.

This is a lesson the campaign paid for once, at the cost of a filed tool
defect that turned out to be a misreading: a large `unplaced` count on
banjo-kazooie was honest reporting about the wrong input, not a parser bug.

### 0.4 Where the pins live

A pin is any file that assigns an address to a symbol and reaches `ld`. Three
places to look:

- **Hand-maintained symbol files.** `undefined_syms.txt`, `manual_syms.*.txt`,
  `hardware_regs.ld`, `pif_syms.ld` — whatever your `-T` list names.
- **Generated symbol files, on splat projects.** splat writes
  `undefined_syms_auto.txt` and `undefined_funcs_auto.txt` under its output
  directory (`build/splat_out/<version>/` on pilotwings64) and the Makefile
  passes both with `-T`. These are the ones people forget, and on
  pilotwings64 they are *the entire shift surface*: 37 lines, against 147
  pins total.
- **Build-time generated tables.** banjo-kazooie's link consumes
  `build/us.v10/compressed_symbols.txt`, generated by the compression step,
  holding the ROM offsets of every compressed segment.

> **List every `-T` file your link consumes, and pass all of them. splat's
> auto files count.** An inventory that omits one is not wrong-looking — it is
> quietly smaller. Running pilotwings64's audit without the two `splat_out`
> files reports `pins_shadowing=7`; with them it reports 17, and the ten it
> was missing include the one word a relink later convicted.

That mistake is the one `shift audit` now catches on its own. Pass
`--elf` and the audit cross-checks its own pin classes against the linked
ELF's absolute symbol table: any address-shaped symbol the link carries in
the movable window or the placed ROM extent that no `--pins`/`--symbol-addrs`
file names is reported as `pins_missing_sources`, with the names themselves
capped and printed — the -T file nobody handed it, found without a second
run.

splat projects also keep a *third* population that is not a pin at all:
`symbol_addrs_*.txt`. Those are disassembly hints. They are read with the same
grammar, they never reach `ld`, and §1.4 explains what including them does to
your numbers.

---

## Phase 1 — inventory

`shift audit` reads one map and one image and builds nothing. Run it before
you form any opinion about your project.

```sh
decomp-workbench shift audit \
  --map build/pilotwings64.us.map \
  --image build/pilotwings64.us.z64 \
  --elf build/pilotwings64.us.elf \
  --pins config/us/sym/hardware_regs.ld \
  --pins config/us/sym/pif_syms.ld \
  --pins config/us/sym/libultra_undefined_syms.txt \
  --pins build/splat_out/us/undefined_funcs_auto.txt \
  --pins build/splat_out/us/undefined_syms_auto.txt \
  --blobs auto --limit 12 --pager never --width unlimited
```

Five `--pins` files, one per `-T` entry from §0.2. The linker script itself
is not passed: the audit reads its *result* out of the map.

### 1.1 `--blobs auto`

An asset segment DMA'd from cart has a link-time VMA that is a load target,
not a place code lives. Its bytes must be scanned — a hardcoded pointer can
sit inside one — but never attributed to a symbol, because attributing blob
offsets through a code section's VRAM mapping produces confident nonsense.
(The campaign's hand-rolled spike did exactly that and came back naming asset
bytes `gAudioHeapStack+0x1dcb0`, which they are not.)

You do not have to know your blob set. The audit derives it from the map's own
input records — every output section all of whose objects are raw binaries —
and prints the suggestion whether or not you take it:

```
blobs=-  blob_source=none
suggested_blobs (from .bin.o inputs): .ipl3, .filetable, .filesys, .audio_seq, .audio_ctl, .audio_tbl  -- adopt with `--blobs auto`
```

`--blobs auto` says yes to it. `--blob` still adds on top and `--no-blob`
subtracts; naming a section with both is refused rather than resolved by
precedence. On pilotwings64 the auto set is exactly right, and it is what keeps
703 coincidental address-shaped words in `.filesys` (compressed level
geometry) classified as low-tier noise instead of promoted into the finding
set.

### 1.2 Reading the pin classes

```
pins_total=147  pins_derived=0  pins_authentic=102  pins_artifact=27  pins_rom_offset=6  pins_shadowing=10  pins_unclassified=2  pins_missing_sources=0
  pin_sources: config/us/sym/hardware_regs.ld
  pin_sources: config/us/sym/pif_syms.ld
  pin_sources: config/us/sym/libultra_undefined_syms.txt
  pin_sources: build/splat_out/us/undefined_funcs_auto.txt
  pin_sources: build/splat_out/us/undefined_syms_auto.txt
```

The headline echoes the files it read, so the `-T` list you assembled in §0.2
is on screen beside the numbers it produced. `pins_missing_sources=0` is the
completeness check from §0.4: it needs `--elf`, and without it the audit says
`pins_shadowing=off  pins_missing_sources=off` and prints two lines telling you
what you are not being told.

| Class | What it means for you |
|---|---|
| `derived` | the right-hand side names a symbol (`gMainMemoryPool = main_BSS_END`). Nothing to do; whatever the linker decides, this follows |
| `authentic-fixed` | an address the console fixes — a hardware register, or one you whitelisted with a reason. Nothing to do, but the whitelist entry is how you say so |
| `artifact-suspect` | an absolute address inside a window your own project owns. This is the work |
| `rom-offset` | a raw cartridge offset (`boot_core1_rzip_ROM_START = 0x00F19250`). Remediable mechanically: the linker already computes that boundary as `<segment>_ROM_START` |
| `shadowing-pin` | an object in this link **already defines** this symbol and the script's assignment silently overrode it. Free to delete |
| `unclassified` | an absolute value in no window the model names and no ROM offset either. Reported as itself rather than guessed |

`shadowing-pin` is the class worth understanding first, because it is the one
that costs nothing to fix and it is invisible without `--elf`. GNU `ld` lets a
linker-script assignment override an object's definition of the same symbol,
with no warning — and it keeps the losing definition's *size* on the surviving
absolute symbol. That residue is the evidence. Pass `--elf` and the audit
reads it directly:

```
shadowing pins (10 of 10, --limit)
name                    value       window  source                                      line
rspbootTextStart        0x80245530  kseg0   build/splat_out/us/undefined_syms_auto.txt  12
gspF3DEX_fifoTextStart  0x80245600  kseg0   build/splat_out/us/undefined_syms_auto.txt  13
gspFast3DTextStart      0x80246a30  kseg0   build/splat_out/us/undefined_syms_auto.txt  14
aspMainTextStart        0x80247e60  kseg0   build/splat_out/us/undefined_syms_auto.txt  15
gspF3DEX_fifoDataStart  0x8024fbc0  kseg0   build/splat_out/us/undefined_syms_auto.txt  20
gspFast3DDataStart      0x802503c0  kseg0   build/splat_out/us/undefined_syms_auto.txt  21
aspMainDataStart        0x80250bc0  kseg0   build/splat_out/us/undefined_syms_auto.txt  22
D_80250E80              0x80250e80  kseg0   build/splat_out/us/undefined_syms_auto.txt  23
D_8034E710              0x8034e710  kseg0   build/splat_out/us/undefined_syms_auto.txt  25
D_803571F0              0x803571f0  kseg0   build/splat_out/us/undefined_syms_auto.txt  33
```

Ten symbols that splat wrote down because, working only from the ROM, it saw
an address it could not attribute to a split file — and that the project's own
objects have since learned to define. The check is exact rather than
heuristic, and it needs no shift. Deleting all ten and relinking reproduced
pilotwings64's ROM byte for byte, `sha1 ec771aed…` unchanged.

`rom-offset` is the same shape of free win one level down. Banjo-Kazooie's
`-T` set — `manual_syms.us.v10.txt` and the generated
`build/us.v10/compressed_symbols.txt` — carries 32 of them, and they are not
arbitrary:

```
rom-offset pins (8 of 32, --limit)
name                       value       window     source                               line
boot_core1_rzip_ROM_START  0x00f19250  segmented  build/us.v10/compressed_symbols.txt  1
boot_core1_rzip_ROM_END    0x00f37f90  segmented  build/us.v10/compressed_symbols.txt  2
boot_core2_rzip_ROM_START  0x00f37f90  segmented  build/us.v10/compressed_symbols.txt  3
boot_core2_rzip_ROM_END    0x00fa3fd0  segmented  build/us.v10/compressed_symbols.txt  4
boot_CC_rzip_ROM_START     0x00fa3fd0  segmented  build/us.v10/compressed_symbols.txt  5
boot_CC_rzip_ROM_END       0x00fa5f50  segmented  build/us.v10/compressed_symbols.txt  6
boot_MMM_rzip_ROM_START    0x00fa5f50  segmented  build/us.v10/compressed_symbols.txt  7
boot_MMM_rzip_ROM_END      0x00fa9150  segmented  build/us.v10/compressed_symbols.txt  8
```

Each `_ROM_END` is the next `_ROM_START`. These are boundaries the link
already computes; the file writes them down as literals. Add banjo's splat
`symbol_addrs.us.v10.txt` with `--symbol-addrs` and the count reads 37 — five
more the disassembler wrote down and the linker never sees, which is §1.4's
distinction on a second project.

### 1.3 `--emit-whitelist`

Nothing is whitelisted by default, and every whitelist entry needs a reason,
because an address with no reason attached is one somebody has to re-derive
later. That policy makes the first whitelist tedious to write by hand, so the
audit will draft one from its own evidence:

```sh
decomp-workbench shift audit \
  --map build/pilotwings64.us.map \
  --image build/pilotwings64.us.z64 \
  --pins config/us/sym/hardware_regs.ld \
  --pins config/us/sym/pif_syms.ld \
  --pins config/us/sym/libultra_undefined_syms.txt \
  --pins build/splat_out/us/undefined_funcs_auto.txt \
  --pins build/splat_out/us/undefined_syms_auto.txt \
  --blobs auto --emit-whitelist boot-globals.txt \
  --pager never --width unlimited
```

What lands in the file is a skeleton, not a whitelist:

```
# shift audit --emit-whitelist: a skeleton, not a whitelist.
#
# Format: `0xADDR reason` or `0xLO-0xHI reason`, one per line, high
# bound inclusive, # comments ignored. A reason is required: an
# address with no reason is one somebody re-derives later.
#
# Every entry below is COMMENTED OUT. A whitelist entry is a claim
# your project makes about its own addresses, and reading a linker
# map does not entitle this command to make it for you. Delete the
# lines that are not authentic, rewrite the reasons on the ones
# that are, and remove the leading `# ` to turn one on.
#
# movable window floor: 0x80200050 (.entry)
# pin_sources: config/us/sym/hardware_regs.ld
# pin_sources: config/us/sym/pif_syms.ld
# pin_sources: config/us/sym/libultra_undefined_syms.txt
# pin_sources: build/splat_out/us/undefined_funcs_auto.txt
# pin_sources: build/splat_out/us/undefined_syms_auto.txt
# pins_total: 147
# candidates: 116
#   hardware-window (102): the value falls in a memory-mapped hardware window (kseg1, or the cart domain inside it): an address the console fixes, which no layout change can move
#   below-window-floor (14): a kseg0 constant below the movable window's own floor: it cannot be an address this layout owns, and it is the shape of the libultra boot globals the boot ROM writes before any of this project runs

# REVIEW: D_80000000 (build/splat_out/us/undefined_syms_auto.txt:7), rule below-window-floor
# 0x80000000 D_80000000: kseg0 constant below the movable window floor 0x80200050, so no insertion moves it -- boot-globals shaped
```

Two candidate rules, both conservative, both stated. It refuses to overwrite
an existing file, and the audit runs and reports normally either way. Review
it, delete what is not authentic, and pass the survivors back with
`--whitelist`.

### 1.4 The population that is not your shift surface

Run the same audit with pilotwings64's three splat `symbol_addrs_*.txt` files
added as `--symbol-addrs`, and the inventory becomes complete — and looks
twelve times worse:

```
pins_total=1,862  pins_derived=0  pins_authentic=102  pins_artifact=1,735  pins_rom_offset=6  pins_shadowing=17  pins_unclassified=2
```

Both numbers are true. `symbol_addrs` entries are read with the same grammar
as pins, so the audit inventories them; they are splat *disassembly* hints and
they never reach `ld`, so none of them can pin an address in a link. The
complete inventory is worth having once — it is where the extra seven
shadowing rows come from, which are the same seven RSP-microcode symbols
spelled a second time in `symbol_addrs_kernel.txt`, so 17 pin *lines* name 10
distinct symbols — but the file you point a remediation queue at is the `-T`
set.

> **Your shift surface is 147 pins, not 1,862.** Inventory everything; plan
> against what the linker consumes.

### 1.5 What the tiers mean

The scan half reads every data, blob and header region word by word and
reports each value landing inside the *movable window* — the VRAM range an
insertion would push. Text is placed and counted but never scanned: a MIPS
address is split across a `lui`/`%lo` pair and does not exist as one word.

```
scan_total=2,548  scan_high=62  scan_medium=681  scan_low=1,805
```

Five suppressors are terminal — `misaligned`, `progression-cluster`,
`repeated-value`, `round-constant`, `whitelisted` — and each was derived from
a false-positive family measured on a real ROM. What survives is scored:
compiled data landing exactly on a symbol's start is `high`, compiled data
alone or a blob resident pointing at a symbol start is `medium`, anything a
suppressor caught is `low`.

**The tiers rank how confidently a word is an address reference. They never
rank hazard, and they never convict.** Two of pilotwings64's 62 `high` hits
are the interesting ones and sixty are healthy pointers, and from one image
there is no way to tell which is which — a resolved pointer and a typed-in
constant are the same four bytes. Phase 3 is what separates them. Read the
audit as a ranked list of candidates worth relinking for, and go build the
relink.

---

## Phase 2 — the shift-capable config

This is the phase people expect to be a week. On pilotwings64 it was one line,
and the reason it took an afternoon anyway was that two of the three obvious
routes are traps.

### 2.1 Modern splat already emits symbolic addresses

papermario's widely-copied `ver/<v>/splat-shift.yaml` overlays two options:

```yaml
options:
  ld_use_symbolic_vram_addresses: True
  emit_subalign: False
```

On splat 0.39.1 `ld_use_symbolic_vram_addresses` **defaults to True**. The
first line is a no-op for any modern splat; it exists because the option used
to default False. pilotwings64 was already emitting a symbolically-chained
script for every segment that had one to chain to. **The published recipe is
not necessary.**

It is also not sufficient, and §0.1 already told you why: the option only
decides whether a segment that *has* a `vram_symbol` uses it. `vram_symbol` is
populated from `follows_vram` / `vram_class`. No `follows_vram` means no
`vram_symbol` means an absolute address, whatever the option says.

Drop `emit_subalign: False` unless you have measured that you need it.
`emit_subalign` controls whether `SUBALIGN(16)` is emitted on each output
section; dropping it lets input sections fall back to their own object
alignment, which changes the layout and breaks the identity gate in §2.4 on
its own. Every delta you will use is a multiple of 16, so `SUBALIGN(16)`
never re-rounds anything and keeping it costs nothing and buys byte-identity.

### 2.2 `follows_vram` is segment-level, so you need a config copy

`splat split` accepts multiple configs and deep-merges them: dicts merge
recursively, **lists are appended**, scalars are replaced, and `base_path`
resolves relative to the *first* config's directory. An `options:`-only
overlay therefore works cleanly — which is exactly why papermario's shift file
only ever touches `options`.

A `segments:`-level change cannot be expressed as an overlay at all, because
`segments` is a list and an overlay would append duplicates rather than edit
one. pilotwings64's blocker is segment-level, so the shift config is a **full
copy** of the project config with the edit applied:

```diff
   - name: app
     type: code
     start: 0x51E30
     vram: 0x802CA900
+    follows_vram: kernel                      # the entire shift edit
     bss_size: 0x293F0
```

**Before you add `follows_vram` to any segment, check in the map that the
preceding segment ends exactly where this one is pinned.** For pilotwings64,
`.kernel_bss` runs `0x80250E80 + 0x79A80 == 0x802CA900`, which is `.app`'s pin
to the byte. If those had not matched, `follows_vram` would have *moved*
`.app` and the identity gate would have failed — for a real reason, and you
would have spent the afternoon debugging a layout change you introduced.

The resulting script differs from the shipped one by one line:

```diff
829c829
<     .app 0x802CA900 : AT(app_ROM_START) SUBALIGN(16)
---
>     .app kernel_VRAM_END : AT(app_ROM_START) SUBALIGN(16)
```

`.entry 0x80200050` stays. Something has to anchor the chain, and the
entrypoint is the correct anchor because the ROM header's boot address refers
to it.

### 2.3 Redirect all four output paths, or lose a build

**Never point a shift experiment at your in-tree paths.** The scratch config
redirects four things:

```yaml
options:
  ld_script_path:           <scratch>/pw64.shift.ld
  undefined_syms_auto_path: <scratch>/undefined_syms_auto.txt
  undefined_funcs_auto_path:<scratch>/undefined_funcs_auto.txt
  cache_path:               <scratch>/.splache
```

The first is obvious. The next two are the footgun, and it is a bad one.
`splat split … --modes ld` looks like the surgical way to regenerate only a
linker script. It is not: `write_undefined_syms_auto()` selects symbols that
are *referenced and not defined*, `referenced` is only set while **code**
segments are disassembled, and under `--modes ld` no code segment runs — but
the write happens outside the mode guard, so the file is **truncated anyway**.
Run it against your real config and you silently replace a 37-line
`undefined_syms_auto.txt` with a 0-byte one. The next link fails with dozens
of undefined symbols and nothing points at a linker-script experiment as the
cause.

`cache_path` matters for a smaller reason: it defaults to `.splache` at
`base_path`, which is not in every project's `.gitignore`, so an unredirected
run leaves an untracked file in your repo root.

Two more things `--modes ld` does that are worth expecting. It still rewrites
`textbin`/`databin` outputs — seven files under `bin/rsp/` on pilotwings64 —
with identical content but new mtimes, so your next `make` redoes those steps.
And `base_path` accepts an absolute path, which is what lets the scratch YAML
live outside the tree while still rooting at the repo. If you want a
full-fidelity regeneration, drop `--modes ld` entirely and pay the extraction
cost.

### 2.4 `shift config verify` — the trust gate

You now have two linker scripts that should produce the same build. Prove it
before you believe anything downstream, because every number in Phase 3 is
attributed to the *shift*, and an unnoticed layout change in Phase 2 would be
attributed to it too.

Relink with each script — on a make-driven project, command-line variable
overrides win over `:=` assignments, so `make no_verify LD_SCRIPT=… LD_MAP=…
ROM_ELF=… ROM_BIN=… ROM_Z64=…` gets you both without touching the tree; use
the target that skips `sha1sum -c`, since that check hard-codes the shipped
path. Then:

```sh
decomp-workbench shift config verify \
  --pinned-map base-pinned.map --candidate-map base-symbolic.map \
  --pinned-image base-pinned.z64 --candidate-image base-symbolic.z64 \
  --pager never --width unlimited
```

```
shift config verify  pinned=base-pinned.map  candidate=base-symbolic.map

faithful=yes  differences=0  allowed_deltas=[0]

shared_symbols=2,732  symbols_moved=0  symbols_only_in_pinned=0  symbols_only_in_candidate=0
shared_sections=14  sections_diverged=0  sections_only_in_pinned=0  sections_only_in_candidate=0
image=identical  pinned_image_bytes=8,388,608  candidate_image_bytes=8,388,608  image_first_difference=-
```

**Three checks, not one, and the image check is the weakest of them.** A
byte-identical image can coexist with a symbol that moved into a hole; only
the symbol check sees that. Two layouts can share a symbol table and still
place their sections differently; only the section check sees that. A faithful
pair exits 0. Anything else exits 3 and names the first divergent symbol and
the first divergent section, because the first one is the one you debug:

```
faithful=NO  differences=2,555  allowed_deltas=[0]

shared_symbols=2,732  symbols_moved=2,543  symbols_only_in_pinned=0  symbols_only_in_candidate=0
shared_sections=14  sections_diverged=11  sections_only_in_pinned=0  sections_only_in_candidate=0
image=differs  pinned_image_bytes=8,388,608  candidate_image_bytes=8,388,624  image_first_difference=0x000010

first divergent symbol: kernel_ROM_START 0x00001050 -> 0x00001060 (+0x10)
first divergent section: .entry.size 0x50 -> 0x60
```

That second transcript is a *shifted* pair, fed to `config verify` on purpose
to show the shape of a failure. A genuinely shifted pair fails all three
checks by construction — that is `shift rehearse`'s question, not this one's.

Run the control too. Relink with the **shipped** script into scratch output
paths first and verify that against the shipped build. If your override route
or your rebuilt intermediates changed anything, you want to know that before a
diff against the symbolic link means something. On pilotwings64 the control
was byte-identical, and then the symbolic link was byte-identical to the
shipped map as well as to the control — first try, zero iterations.

---

## Phase 3 — the rehearsal baseline

Now insert a pad and relink. The objects are the controlled constant of this
experiment: **relink only, never recompile.** A relink is seconds; a rebuild
is minutes and a different question.

### 3.1 `orchestrate` or `analyze`

`orchestrate` generates the padded scripts, calls your relink wrapper once per
delta, and analyzes each:

```sh
decomp-workbench shift rehearse orchestrate \
  --wrapper tools/relink.sh \
  --ld-script mods/game.custom.ld \
  --anchor-object build/src/hasm/entrypoint.s.o \
  --deltas 0x10,0x40 \
  --workdir .workbench/rehearsal \
  --image-name game.z64 --map-name game.map \
  --blob .assets --crc-words 0x10,0x14 \
  --census unexplained_changed=0,stale_confirmed=0
```

The wrapper is the one part you implement: invoked as
`SCRIPT LDSCRIPT_PATH OUT_DIR`, it must leave the image and its `ld -Map` in
`OUT_DIR` under the names you gave. The pad is one line, `. += DELTA;`,
inserted after the object you name — exactly one line of the script may
mention that object, since zero is a typo and two is ambiguous, and both
refuse before anything is built.

Use `analyze` when you already have the pair, which is the case if you built
the padded scripts by hand during Phase 2. Everything below was measured with
`analyze` on prebuilt pilotwings64 links.

**Where to put the pad.** On pilotwings64 it went as the last statement inside
the `.entry` output section, after `entry_RODATA_SIZE`. Three reasons, and
they generalize: it is *after* the entrypoint object, so the IPL3 handoff
stays valid; it lands exactly on the first symbolic link in the chain, so a
clean pass proves the whole chain follows rather than one hop; and `0x10` is a
multiple of the `SUBALIGN(16)` granularity, so nothing re-rounds and the delta
stays exact end to end. **Pick multiples of your subalign** — a pad that is
not will be silently re-rounded by the next `ALIGN`, and the pair is then
refused rather than paired anyway, and the refusal always names the arithmetic
directly (`shifted image is +64 bytes longer than base, not the declared delta
+16`) — checked before the anchor is derived, with or without `--anchor`
given, so a wrong delta is never reported as the vaguer "no object-backed
symbol … moved by the declared delta" that its own failed derivation would
otherwise surface first. Either way, compare the two image sizes yourself
before you argue with the tool.

### 3.2 Two deltas

Always two. A partially symbolized reference — a `%hi(symbol)` paired with a
literal `%lo` — can encode correctly at one shift by coincidence and cannot at
two. Any class count that differs between the deltas is a finding in its own
right. On pilotwings64, `0x10` and `0x40` agreed exactly, which is itself
evidence: a delta-dependent result would have meant an alignment artifact
rather than a reference.

Confirm the arithmetic before you believe the report. The images grew by
exactly `0x10` and `0x40` (8,388,608 → 8,388,624 → 8,388,672), and `n64crc`
reported `CRC (Bad, fixed)` on both, which is the post-link CRC patcher doing
its job and is why `--crc-words 0x10,0x14` exists.

### 3.3 The anchor

The insertion point is derived by default, and it now derives correctly on
splat projects:

```
anchor_vram=0x802000a0  anchor_rom=0x001050  anchor_source=auto  anchor_symbol=func_802000A0  anchor_highest_unmoved=0x803571f0
```

That was not always true. `auto` looks for the lowest VRAM at which shared
symbols start differing by the delta, and splat emits `<segment>_ROM_START` /
`_ROM_END` assignments unconditionally — numerically low, VRAM-shaped, and
they move by the delta. The first run on pilotwings64 picked
`entry_ROM_END = 0x1050`, then correctly refused to translate it because no
`AT()` section covers VRAM `0x1050`. A good failure, and now a fixed one:
assignment symbols are excluded from the derivation.

**Confirm the reported pair anyway.** `anchor_vram=0x802000a0
anchor_rom=0x001050` is precisely the first shifted byte on pilotwings64 —
the entrypoint is 0x50 bytes at ROM 0x1000, so ROM 0x1050 is where the pad
went. An anchor wrong by one word reclassifies the entire image, silently and
plausibly. If it picks something you did not pad, override it by name with
`--anchor <symbol>`; the first `_TEXT_START` above the pad is the usual right
answer.

### 3.4 The two referees, and why you need both

```sh
decomp-workbench shift rehearse analyze \
  --base-map artifacts/base-symbolic.map --base-image artifacts/base-symbolic.z64 \
  --shifted-map artifacts/shifted-10.map --shifted-image artifacts/shifted-10.z64 \
  --base-elf scratch/base-symbolic.elf --shifted-elf scratch/shifted-10.elf \
  --delta 0x10 \
  --blobs auto \
  --crc-words 0x10,0x14 --limit 12 --pager never --width unlimited
```

`--blobs auto` rather than the five `--blob` names §1.1 first suggested: it reads
the same base map the audit derives from, through the same `resolve_blobs`, and
hand-listing them here is how an earlier draft of this page silently dropped
`.ipl3` — present in §1.1's `suggested_blobs` and absent from a copy-pasted
`--blob` chain nobody re-checked against it. `auto` cannot drop one.

```
shift rehearse  base=artifacts/base-symbolic.map  shifted=artifacts/shifted-10.map  delta=0x10

unexplained_changed=0  stale_confirmed=1  symbol_stale=13  shadowing_pins=10  findings=24
```

Every changed word, sorted into classes:

```
differing_total=23,236

classes
label         count
abs32-tracks  1,842
crc-header    2
j26-tracks    11,720
lo16-tracks   9,672
```

Every address-shaped word that did *not* change, judged against the audit's
own tiers:

```
reconciled_total=2,546  moved_total=1,842  unmoved_total=704  changed_other_total=0  stale_total=704  stale_unattributed=0

tier_verdicts
tier    verdict        count  outcome
high    moved          60     tracks
high    unmoved        1      stale-confirmed
high    changed-other  0      changed-other
medium  moved          681    tracks
medium  unmoved        0      stale-review
medium  changed-other  0      changed-other
low     moved          1,101  tracks
low     unmoved        703    noise
low     changed-other  0      changed-other
```

**`unexplained_changed=0` is the gate.** Every one of 23,236 changed words is
accounted for by a class. A word that changed for a reason no class explains
means either the census is wrong or the build was not the controlled
experiment it claims to be, and no other number on the page is worth reading
until it is zero.

The one `stale-confirmed` word is §4.2's worked example. But look at the
second headline: **`symbol_stale=13`**, from `--base-elf` / `--shifted-elf`.

The data-side referee judges "did not move" only against words the static scan
*read*, and the scan does not read text — 209,552 words on pilotwings64 —
because a MIPS address lives in a `lui`/`%lo` pair and never exists as one
word. A reference consumed only from code is therefore structurally invisible
to `stale_confirmed`. The symbol-side census answers exactly that half: every
symbol naming an address above the insertion must have moved by the delta.

```
symbol_census=on  symbol_checked=2,516  symbol_moved=2,493  symbol_stale=13  shadowing_pins=10
symbol_range=(0x802000a0, 0x803805e0]  symbol_boundary=12  symbol_only_in_base=0  symbol_only_in_shifted=0

symbol findings (12 of 23, --limit)
name                    value       shifted     class          kind    size   owning_section
rspbootTextStart        0x80245530  0x80245530  shadowing-pin  func    208    .kernel
gspF3DEX_fifoTextStart  0x80245600  0x80245600  shadowing-pin  func    5,168  .kernel
gspFast3DTextStart      0x80246a30  0x80246a30  shadowing-pin  func    5,168  .kernel
aspMainTextStart        0x80247e60  0x80247e60  shadowing-pin  func    3,616  .kernel
gspF3DEX_fifoDataStart  0x8024fbc0  0x8024fbc0  shadowing-pin  object  2,048  .kernel
gspFast3DDataStart      0x802503c0  0x802503c0  shadowing-pin  object  2,048  .kernel
aspMainDataStart        0x80250bc0  0x80250bc0  shadowing-pin  object  704    .kernel
D_80250E80              0x80250e80  0x80250e80  shadowing-pin  object  80     .kernel_bss
D_8034E710              0x8034e710  0x8034e710  shadowing-pin  object  24     .app
D_803571F0              0x803571f0  0x803571f0  shadowing-pin  object  4      .app_bss
D_8024B355              0x8024b355  0x8024b355  symbol-stale   notype  0      .kernel
D_8024B356              0x8024b356  0x8024b356  symbol-stale   notype  0      .kernel
```

**Thirteen against one.** Twenty-three symbol findings in all: ten
`shadowing-pin` and thirteen `symbol-stale`, against the data side's single
`stale_confirmed`. The seven RSP-microcode pins in that list carry two to five
relocations each and `D_80250E80` carries ten — every one of those references
would have been stale after a shift — and *none* of them appeared as
`stale-confirmed`, because they are consumed from `%hi`/`%lo` pairs in text.
The single word the data side did catch, `D_803571F0`, has the fewest
references of the ten.

> **Neither referee subsumes the other. Run both.** `stale_confirmed` is the
> data-side answer; the symbol census is the symbol-side answer. Pass
> `--base-elf` and `--shifted-elf` every time; the ELFs are already sitting
> next to the images your relink produced.

Two more things the referee cannot reach, so that you know to look elsewhere.
Segmented pointers inside game assets — display lists, geo layouts — are not
modeled by anything here. And source-level kseg0 literals compile to
text-resident immediates, so grep for them separately; on pilotwings64 that
sweep found only fixed RAM-map boundaries (`0x803DA800`, `0x80200000`,
`0x80400000`), which legitimately do not move with the image.

### 3.5 The checksum-consistency rule, read alongside your build

If your project byte-sums any of its own functions at run time, declare the
pairs:

```sh
decomp-workbench shift rehearse analyze \
  --base-map base/game.map --base-image base/game.z64 \
  --shifted-map shifted/game.map --shifted-image shifted/game.z64 \
  --delta 0x10 --crc-words 0x10,0x14 \
  --checksum-pair race_check_finish=gRaceCheckFinishChecksum
```

The rule is one sentence: *if any word inside a protected function's body
changed, that function's checksum word must have changed too.* Neither a
static scan nor a stale-word detector can see this class, because the word
holds a byte-sum rather than an address — there is nothing to key off. In 2021
one audio function was left off the reference project's post-link patcher
allowlist, its bytes changed under a shift, its frozen checksum did not, the
game's own runtime self-check failed, and the symptom was reported as "cursed
audio."

**Read a `checksum-stale` verdict alongside your project's post-link chain
before you treat it as a finding.** On the reference project the shift-mode
build selects a `no_verify` target, so the patcher never runs — and the
matching branch is the only one that defines `ANTI_TAMPER=1`, so the runtime
check is compiled out of mod builds entirely. The rule fires correctly on
those images and the finding is harmless by design. That combination is
exactly the 2021 precondition. With the patcher run post-link, the same four
pairs come back `pass`/`tracked` with bodies that changed 71, 90, 11 and 6
words. A rehearsal harness should run your full post-link chain, or expect and
explain this class.

---

## Phase 4 — the queue

`shift plan` reads reports, not maps. Re-run Phase 1's audit and Phase 3's two
rehearsals with `--json` — same arguments, plus a generous `--limit`, because
§4.4 is about what happens when you forget:

```sh
decomp-workbench shift audit \
  --map build/pilotwings64.us.map \
  --image build/pilotwings64.us.z64 \
  --elf build/pilotwings64.us.elf \
  --pins config/us/sym/hardware_regs.ld \
  --pins config/us/sym/pif_syms.ld \
  --pins config/us/sym/libultra_undefined_syms.txt \
  --pins build/splat_out/us/undefined_funcs_auto.txt \
  --pins build/splat_out/us/undefined_syms_auto.txt \
  --blobs auto --limit 5000 --json > pw64-audit.json

for delta in 10 40; do
  decomp-workbench shift rehearse analyze \
    --base-map artifacts/base-symbolic.map --base-image artifacts/base-symbolic.z64 \
    --shifted-map artifacts/shifted-$delta.map --shifted-image artifacts/shifted-$delta.z64 \
    --base-elf scratch/base-symbolic.elf --shifted-elf scratch/shifted-$delta.elf \
    --delta 0x$delta \
    --blob .filetable --blob .filesys --blob .audio_seq --blob .audio_ctl --blob .audio_tbl \
    --crc-words 0x10,0x14 --limit 5000 --json > pw64-rehearse-$delta.json
done
```

You now have one audit report and two rehearsal reports, holding somewhere
between hundreds and tens of thousands of rows between them. `shift plan`
merges them into one ranked, gated list of *jobs*.

```sh
decomp-workbench shift plan \
  --audit pw64-audit.json \
  --rehearse pw64-rehearse-10.json \
  --rehearse pw64-rehearse-40.json \
  --markdown PW64-WORK-ORDER.md \
  --pager never --width unlimited
```

```
plan_total=107  plan_convictions=14  plan_free_wins=10  plan_structural=1

plan_by_class
remediation           kind              count
delete-redundant-pin  match-preserving  10
derive-pin            match-preserving  7
migrate-symbol        match-preserving  12
investigate           conviction        62
dual-spelling-risk    conviction        1
whitelist-candidate   declaration       14
structural            parked            1

plan_by_source
source           items
audit-pin        43
audit-scan       64
rehearse-stale   1
rehearse-symbol  13
shadowing        10
```

Merged by *subject*, not concatenated by report: `D_803571F0` appears in the
audit's pin half, the audit's scan half, both rehearsals and the shadowing
census, and it is **one job**. That is the difference between 107 items and
several hundred rows.

### 4.1 The classes and their gates

| Class | Kind | What it is | Gate |
|---|---|---|---|
| `delete-redundant-pin` | match-preserving | an object already defines the symbol; the script's assignment silently overrode it | rebuild, `shift config verify`, re-audit and watch `pins_shadowing` fall by one |
| `derive-pin` | match-preserving | the pinned value is a boundary the linker already computes — a section's own ROM or VRAM edge | rebuild, `shift config verify`, re-audit and watch `pins_rom_offset` fall by one |
| `migrate-symbol` | match-preserving | a kseg0 address written down for content this link actually places; the symbol needs a home in the section that owns it | rebuild, `shift config verify`, re-rehearse and watch `symbol_stale` fall by one |
| `investigate` | conviction | the evidence names a word or a symbol but not a remediation. Read the coordinates before deciding what class it is | re-run the rehearsal at two independent deltas |
| `dual-spelling-risk` | conviction | references this instrumentation structurally cannot judge — the text side | run the symbol-side census, which does not read text at all |
| `whitelist-candidate` | declaration | an address the console fixes, not this layout. The fix is a line with a reason on it | add it to your whitelist and re-audit; `pins_authentic` rises by one |
| `structural` | parked | a layout decision rather than a pin: an overlay window several sections share, a DMA'd blob | none. Named and set aside on purpose |

Ordering is by **what the evidence cost, then what the fix costs**:
convictions a relink demonstrated, then the free wins an object already
defines, then the mechanical symbolizations, then the real migrations grouped
by owning section, with the structural classes named and parked at the bottom.

Park means park. banjo-kazooie's bottom item is:

```
313. 14 output sections share VRAM 0x803863f0  [structural]
     evidence: .CC, .GV, .MMM, .TTC, .MM, .BGS, .RBB, .FP, .SM, .cutscenes, .lair, .fight, .CCW, .emptyLvl all start at 0x803863f0. Extents alone cannot tell a nested placement from an N64 overlay group of mutually exclusive alternatives, and either shape is a layout decision rather than a pin
```

Fourteen level overlays sharing one window is not something you fix by editing
a symbol file, and a queue that mixed it in with the free wins would be a queue
nobody finishes.

### 4.2 Free wins first — the worked example

Item #1 on pilotwings64's queue, with the whole conviction attached:

```
1. delete the pin D_803571F0  [delete-redundant-pin]
     evidence: D_803571F0 = 0x803571f0 in build/splat_out/us/undefined_syms_auto.txt:33 -- an object in this link already defines it (the surviving absolute symbol carries that definition's own size)
     evidence: ROM 0x0d5cbc holds 0x803571f0 in .app and a 0x10 relink did not move it; it points at D_803571F0
     evidence: D_803571F0 = 0x803571f0 is absolute and carries a 4-byte size inherited from the object definition it overrode; a 0x10 relink left it behind while .app_bss moved
     evidence: confirmed at deltas 0x10, 0x40 -- a reference can encode correctly at one shift by coincidence and cannot at two
```

Four independent lines of evidence for one word, from four different
mechanisms. Here is what it is. `src/app/code_51E30.c` declares
`f32 D_803571F0;` and then `Unk802CAC48 D_8034E788 = { 0, 11, &D_803571F0, NULL };`.
The object carries a real `R_MIPS_32` relocation for that pointer and
*defines* the symbol in `.bss`. But splat's generated
`undefined_syms_auto.txt` also contains `D_803571F0 = 0x803571F0;`, that file
is passed to `ld` with `-T`, and a linker-script assignment beats an object's
definition — silently. `nm -n` on the base link shows the override: type `A`,
absolute, the script's value rather than the object's `.bss` slot.

```
803571f0 B app_BSS_START
803571f0 B app_bss_VRAM
803571f0 T app_RODATA_END
803571f0 A D_803571F0
```

The same two lines from the shifted link are the whole bug:

```
803571f0 A D_803571F0
80357200 B app_BSS_START
```

In the shifted ROM the `f32` physically lives at `0x80357200` while every
reference to it resolves to `0x803571F0` — sixteen bytes below `.app_bss`, in
the trailing padding of `.app`'s read-only data. Reads return stale ROM
contents; writes scribble on loaded data. Runtime-fatal, not cosmetic.

**And the fix is deleting one line.** Feed `ld` a copy of
`undefined_syms_auto.txt` with that line removed and the unshifted ROM is
still `sha1 ec771aedf54ee1b214c25404fb4ec51cfd43191a` — byte-identical to the
retail cartridge. The rehearsal's `high/unmoved` row moves to `high/moved`:
60 tracking and 1 stale becomes 61 tracking and 0 stale. Delete all ten
shadowing pins at once and the answer is the same. The pin was pure redundancy
that happened to be correct at one layout.

That is what "free win" means here, and it is why the ordering puts them
second, immediately behind the convictions: ten items, zero risk, and each one
removes a whole class of stale references from the shifted build.

### 4.3 `--markdown` is the thing you hand to a person

`--markdown FILE` writes the queue as a work order: the loop stated at the
top, a checkbox per item grouped by class, every item's evidence and gate
commands beside it, and **every** item exported regardless of the terminal
`--limit`.

```
# Shift remediation work order

**The loop.** fix one item -> rebuild -> prove the ROM is byte- and symbol-identical (`shift config verify`) -> re-run the instrument that found it and watch its census key fall by one. A fix that cannot pass its own gate is not a fix; a fix with no gate is a hope.

| | |
|---|---|
| audit report | `pw64-audit.json` |
| rehearse reports | `pw64-rehearse-10.json`, `pw64-rehearse-40.json` |
| deltas rehearsed | `0x10`, `0x40` |
| items | 107 |
| convictions (a relink demonstrated these) | 14 |
| free wins (byte-identical to fix) | 10 |
| parked as structural | 1 |
```

### 4.4 Read the capping notice

A plan built from capped reports says so, in the terminal and in the work
order. This is the same pilotwings64 plan, fed the default-limit reports and
the complete pin inventory from §1.4 instead:

```
plan_capped -- this plan is built from capped reports
  pins (40 of 1862 carried by the audit report)
  scan hits (40 rows carried, scan_high=62)
  Re-run the reports with a larger --limit to plan the rest. A detail list that stopped at --limit cannot describe what came after it, and neither can this queue.
```

The reports default to 40 rows per detail list. Pass `--limit` generously on
the `--json` runs that feed the plan — the plan is the artifact you are going
to work from for weeks, and a queue that silently stopped at row 40 is worse
than no queue.

### 4.5 What a plan without a rehearsal looks like

banjo-kazooie has no shift-capable linker configuration yet, so its plan comes
from the audit alone. `bk-audit.json` below is the *complete* inventory §1.4
argues for — the two `-T` files, plus the two splat hint files that never reach
`ld` — read at `--limit 200`:

```sh
decomp-workbench shift audit \
  --map build/us.v10/banjo.us.v10.map \
  --image build/us.v10/banjo.us.v10.uncompressed.z64 \
  --elf build/us.v10/banjo.us.v10.elf \
  --pins manual_syms.us.v10.txt \
  --pins build/us.v10/compressed_symbols.txt \
  --pins level_symbols.us.v10.txt \
  --symbol-addrs symbol_addrs.us.v10.txt \
  --blobs auto --limit 200 --json > bk-audit.json
```

```
shift plan  audit=bk-audit.json  rehearse=-

plan_total=314  plan_convictions=0  plan_free_wins=0  plan_structural=2

plan_by_class
remediation           kind              count
delete-redundant-pin  match-preserving  0
derive-pin            match-preserving  39
migrate-symbol        match-preserving  71
investigate           conviction        200
dual-spelling-risk    conviction        1
whitelist-candidate   declaration       1
structural            parked            2
```

**Zero convictions, and 200 items in `investigate`** — capped there from a
`scan_high` of 1,581. A plan from the audit alone is a plan of suspicions:
every one of those 1,581 words *might* be a hardcoded pointer and might
equally be a healthy reference, and nothing in a single linked image can tell
you which. Compare pilotwings64, where a working rehearsal collapsed the same
shape of evidence into 14 convictions and 93 other items.

The lesson is an ordering lesson. **Get Phase 2 done before you take Phase 4
seriously.** Every item a rehearsal contributes outranks all of the audit's,
and a rehearsal turns most of the audit's high tier from a queue into a
non-event.

---

## Phase 5 — the loop, and what done means

### 5.1 The loop

> fix one item → rebuild → prove the ROM is byte- and symbol-identical
> (`shift config verify`) → re-run the instrument that found it and watch its
> census key fall by one.

State it as a loop because it is one, and because each half of it fails in a
different way without the other. A fix that cannot pass `config verify` is not
a fix — it changed the build. A fix whose census key does not fall was not the
fix you thought it was. **A fix that cannot pass its own gate is not a fix; a
fix with no gate is a hope.**

Every item in the plan carries its own gate commands, filled in with your real
paths, precisely so this loop takes no thinking.

### 5.2 The CI gate

Two predicates, on the commands you already run:

```sh
decomp-workbench shift rehearse orchestrate \
  --wrapper tools/relink.sh --ld-script mods/game.custom.ld \
  --anchor-object build/src/hasm/entrypoint.s.o \
  --deltas 0x10,0x40 --workdir .workbench/rehearsal \
  --blob .assets --crc-words 0x10,0x14 \
  --census unexplained_changed=0,stale_confirmed=0
```

`--census` turns the report into an exit code — `3` when a predicate is false,
`2` for an unknown key — and prints one PASS/FAIL line per predicate. On a
healthy project it looks like this, from the reference project's own shifted
pair:

```
census: PASS unexplained_changed=0
census: PASS stale_confirmed=0
```

Add `symbol_stale=0` once the symbol side is clean, and `plan_convictions=0`
on the plan if you want the queue itself gated. Start with
`unexplained_changed=0` alone if your project is not there yet: it is the
integrity check on the measurement, it should be zero from day one, and it
catches the case where somebody's build change quietly stopped the rehearsal
from being a controlled experiment.

No N64 decompilation currently runs any shiftability check in CI —
papermario, zeldaret/oot and mk64 workflow files were fetched and grepped for
the survey behind these commands, with zero hits. Shiftability is everywhere a
manually-invoked opt-in build config maintained by convention and periodic
bug-hunting. Two census predicates is the cheapest thing that changes that.

### 5.3 Multi-version projects

Run the campaign once per version, and expect the *config* work to transfer
while the *findings* do not. The pin files are per-version
(`manual_syms.us.v10.txt`, `symbol_addrs.pal.txt`), the generated ones are
regenerated per version, and a symbol that an object defines in one revision
may be genuinely undefined in another — which turns a free `delete-redundant-pin`
into a real link failure. The `shift config verify` gate is per-version too,
and it is the cheap one: run it on every version before you believe a config
edit generalizes.

### 5.4 The boot-test hand-off

**Nothing here boots a shifted ROM, and nothing here can.** Full shiftability's
referee is that the shifted image *runs*. What these four commands own is the
strongest static referee available — every changed word explained, every
unmoved address-shaped word judged, every symbol above the insertion checked —
and the hand-off is stated rather than papered over.

The boundary is exact, so you can see what is on your side of it. After Phase
5 you know that no word in the image changed for an unexplained reason, that
no data-side reference stayed behind, and that no symbol above the insertion
failed to move. You do **not** know that segmented pointers inside your assets
survive, that a `%hi`/`%lo` pair spelled `lui`/`ori` rather than `lui`/`addiu`
was reconstructed the way the original meant it, or that any code path
actually executes.

So the hand-off needs an emulator oracle, and the shape it needs is a
*deterministic* one: a fixed input sequence replayed against the base and the
shifted build, compared on some observable that does not drift — a frame hash,
an audio buffer, a save-state field. Exercise, in this order, the things a
shift moves: boot to first frame at all; then the paths that consume the
sections that moved, which on a splat project means whatever `.app` or
`.core2` owns; then anything DMA'd, since blob VMAs are load targets and are
where the static referee is blindest; then audio, which is where the 2021
checksum bug surfaced and which fails in ways a frame hash will not catch.

There is no *automated* precedent to copy — the CI survey above found nobody
wiring a behavioral check to a shift at all. The closest thing to prior art
is manual: Mario Kart 64's shiftability tracking issue
(n64decomp/mk64 issue #6) records shift bugs found by replaying a TAS
against shifted builds at specific offsets — including audio corruption at
an extreme 0x9C40 shift traced to a single variable (`gDefaultPanVolume`) —
which is both an endorsement of replay-as-oracle and a demonstration of why
the exercise order above ends with audio. If your project already has a
deterministic replay harness for regression testing, that harness is your
oracle and pointing it at a shifted build is a small piece of work. If it does
not, building one is a larger project than this campaign, and it is honest to
ship the static result and say what it does not cover.

---

## What the pilotwings64 campaign actually found

Stated plainly, because the community-facing claim matters and it is the
opposite of what anyone expected:

> A 100%-matched N64 decompilation, given a shift-capable linker script and
> relinked against a padded layout, produced **zero unexplained changed words**
> at two independent deltas, and its only high-confidence stale reference was a
> redundant linker-script pin that can be deleted without changing a single
> byte of the matched ROM.

pilotwings64 shows no evidence of a genuine hardcoded pointer in the original
data. Its shift surface is entirely in configuration, entirely enumerable, and
entirely fixable without touching matched code. The complete remaining list is
37 lines long — 10 pins an object already defines, 2 that are live and need a
symbolic replacement (`D_803805E0` → `app_BSS_END`, and `D_802C3C90` →
`gSchedStack + 0xE8`, the boot stack pointer), 17 with zero relocations
anywhere that are pure configuration residue, and 8 legitimately outside the
movable window.

Three commits, none of which changes the ROM, and the project is shiftable.

That is a result you can only get by measuring, and the survey behind these
commands found nobody running the measurement: splat's own wiki names
shiftability and offers hand-written per-address override files, splat,
spimdisasm and mapfile_parser audit none of it, and no project's CI checks it.
Your project's number is probably also small. It is also probably not zero,
and you will not know which until you run Phase 3.

## See also

- [Shiftability](shiftability.md) — what each of the four commands measures,
  the tier rules, the pin classes and the boundaries they refuse to cross.
- [Trap 7: byte-identity does not prove address provenance](metric-traps.md#trap-7-byte-identity-does-not-prove-address-provenance)
  — the one-line hardcoded pointer that passed a retail verifier, as a
  measurement lesson.
- [JSON contracts](json-contracts.md) — `--json`, `--census` and the exit
  codes a CI gate reads.
- [Candidate campaigns](campaigns.md) and [Shared notes](shared-notes.md) — a
  real shiftability pass is a multi-week, multi-agent grind, and the
  durable-state machinery for running one already exists.
- [Product status](product-status.md) — the implemented surface and the
  intentional boundaries, in one place.
