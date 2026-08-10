# Pilotwings 64: a shiftability assessment

This case study records a shiftability assessment of the Pilotwings 64
decompilation (`gcsmith/Pilotwings64Decomp`, 100% matched, US v1.0,
baserom SHA-1 `ec771aedf54ee1b214c25404fb4ec51cfd43191a`), run in August
2026 with this repository's `shift` commands. The question was the one
every matched project eventually gets asked: can code and data be added,
removed, or resized without breaking the ROM, and if not, what exactly is
in the way?

The short answer: the game is not the obstacle. The project's linker
script needs one changed line to become shift-capable, a padded relink
then produces zero unexplained changed words, and every blocker found
traces to the decompilation's own generated symbol files rather than to
anything Nintendo shipped. Ten of those blockers are deletable today with
a byte-identical ROM as the proof.

## Result and proof boundary

| Evidence | Recorded value |
|---|---|
| Matching build vs. retail image | byte-identical (`cmp`, plus the project's own `sha1sum -c`) |
| Symbolic relink vs. pinned link | byte-identical; 2,732 shared symbols at identical addresses; 14 sections identical (`shift config verify`: `faithful=yes, differences=0`) |
| Padded relink, deltas +0x10 and +0x40 | `unexplained_changed=0` at both; 23,236 changed words, all classified (11,720 jump targets, 9,672 `%lo` displacements, 1,842 data pointers, 2 header CRC words) |
| High-confidence stale references under shift | 1 (see below); 0 after a one-line deletion, with the unshifted ROM still byte-identical |
| Link-time symbol pins across the six `-T` files | 147 total: 102 fixed hardware/boot addresses, 27 artifact-suspect, 10 shadowing, 6 raw ROM offsets, 2 unclassified |

These are link-level measurements against the project's own build. They do
not include booting a shifted image; see Limitations.

## The linker script needs one line

The generated `ld` script for the US build contains exactly two absolute
VRAM addresses. One is `.entry` at `0x80200050`, which must stay: the ROM
header's boot address refers to it. The other is `.app` at `0x802CA900`,
and it is removable by giving the `app` segment a `follows_vram: kernel`
key in the splat config, after which the section starts wherever `.kernel`'s
bss ends, which is the same address, derived instead of written down.

The 140-plus per-file `vram:` keys in the project's YAML are not blockers.
splat consumes them during disassembly and never emits them into the
linker script; the per-file bss inputs land inside two output sections
that shift as units.

`shift config verify` confirms the edited config is faithful: relinked
without a shift, the symbolic script reproduces the pinned layout exactly,
down to the byte.

## What a real shift moves, and what it fails to move

With the symbolic script in place, relinking with a `. += 0x10` pad after
the entrypoint is a seconds-long operation on unchanged objects. Both
rehearsal deltas fully account for every changed word in the image, which
is the property that makes the rest of the findings trustworthy: nothing
moved that the tooling cannot explain.

The interesting output is what failed to move.

The data-side referee reported one high-confidence stale reference. The
word at ROM `0x0d5cbc` holds `&D_803571F0`, the third field of a struct
initializer at `src/app/code_51E30.c:22`. The variable itself is an
ordinary bss float, declared at line 6 of the same file, so the object
file both defines the symbol and carries a proper relocation for the
reference. It should shift cleanly. It does not, because line 33 of the
generated `undefined_syms_auto.txt` also pins it:

```
D_803571F0 = 0x803571F0;
```

A `-T` assignment silently overrides an object definition, so the linker
keeps the symbol at the pinned address while the storage it names moves
with `.app_bss`. Under a +0x10 shift the pointer lands in `.app`'s
trailing rodata instead of the float. That is a runtime fault waiting for
whichever code path dereferences it, in a build that links without a
single warning.

Deleting that one line flips the reference to tracking and leaves the
unshifted ROM byte-identical, which is the whole diagnosis and the whole
fix. The ELF symbol census (`shift rehearse --base-elf/--shifted-elf`)
generalizes it: ten pins in the auto-generated file shadow symbols the
objects already define, all ten are deletable the same way, and thirteen
object-backed symbols in total fail to move under a shift, the rest being
the RSP microcode blob symbols and a boot stack pointer that a shift
build would need to place deliberately rather than pin.

`shift audit --elf` finds the same ten statically, with no shift build
required. A project can run that check today against its ordinary
matching build.

## What this says about the game, and about the workflow

A source sweep for hardcoded kseg0 literals in the game code came back
clean apart from fixed RAM-map constants, and the rehearsal found no
stale reference attributable to original data. On present evidence,
Pilotwings 64 the game does not hardcode pointers that a shift would
break; the shift surface is decompilation configuration, it is small, and
it is enumerable.

That inverts the usual assumption about un-shiftable matched projects,
and it suggests a general lesson: the auto-generated pin files that make
early matching convenient become silent liabilities once the project is
done, because a pin that shadows a real definition is invisible to every
byte-comparison gate the community currently runs. The matching build
with the pin and without it are the same file.

## For the Pilotwings 64 project

Three changes, in increasing order of ambition, all verifiable with the
commands in this repository:

1. Delete the ten redundant entries from `undefined_syms_auto.txt`
   (regenerating with current splat should also drop them, since the
   objects define every one). The matching build stays byte-identical;
   `shift audit --elf` goes to `pins_shadowing=0`.
2. Add `follows_vram: kernel` to the `app` segment and keep a shift-mode
   config alongside the matching one. `shift config verify` is the gate
   that the two stay faithful.
3. Wire `shift rehearse` with
   `--census unexplained_changed=0,stale_confirmed=0` into CI so the
   properties above stay true as the project evolves.

The full procedure, with transcripts, is in
[the shiftability campaign guide](../docs/shiftability-campaign.md); the
command reference is [shiftability.md](../docs/shiftability.md).

## Limitations

Everything here is static and link-level. No shifted image was booted;
behavioral verification (an emulator or replay harness) is out of scope
for these tools and stated as such in their documentation. The audit's
confidence tiers rank how likely a word is to be an address reference and
never convict on their own; the convictions above come from differential
relinks, and the deletions were proven by rebuilding and comparing
images. Blob contents (the game's filesystem and audio banks) were
scanned for address-shaped words but not parsed; 62 words remain in the
audit's high tier for a human to review, and nothing currently suggests
they are live references.
