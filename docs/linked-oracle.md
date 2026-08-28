# The linked image as an oracle

Some games ship a code module **unrelocated**. The module's own relocation
table travels with it, and the game's runtime linker patches every site that
table names after the module is loaded. What the shipped image stores at such
a site is therefore not an address but the record's **stored addend** — the
value the runtime adds a base to.

That fact breaks every object-level oracle this workbench otherwise offers.
A translation unit compiled for such a module spells its cross-module calls
with placeholder externs that have no address in this build, so the linked
instruction word only carries the shipped addend if something supplies each
placeholder's value. Until that happens the candidate does not link at all;
once it does, `compare` and the permuter are still scoring the wrong thing,
because the target names symbols the candidate cannot.

Two commands answer the two halves:

| Command | Question |
|---|---|
| `reloc-surface` | what value must each placeholder carry for the link to reproduce the shipped words? |
| `linked-compare` | given the image that link produced, is this function's range the target's bytes? |

Neither builds anything. The [host-side loop](#the-host-side-loop) is the
project's, because only the project knows how it builds.

## Why the value is not a judgement call

For a candidate whose instruction schedule already agrees with the target
*at the site*, every placeholder's value is readable from the image at the
offset its relocation names:

| relocation | required symbol value |
|---|---|
| `R_MIPS_26` | `synthetic_vma \| (stored_imm26 << 2)` |
| `R_MIPS_HI16` + `R_MIPS_LO16` | `(stored_hi << 16) + sext16(stored_lo)` |
| `R_MIPS_32` | the stored word |

minus whatever addend the object's own instruction already carries.
Subtracting the object's addend is what lets one base symbol serve many
struct-field references: the compiler puts the field offset in the
instruction, so only the base belongs in the linker script.

The precondition is the italicized half, and the tool enforces it rather than
assuming it. Where two sites for one symbol demand different values the
schedule has diverged at the site, no consistent addend exists, and the
synthesis **refuses that symbol and names both values and every conflicting
site**. Inventing one instead would produce a link that succeeds and an image
that is quietly wrong, which is the most expensive failure this page can
prevent.

## The module map

One JSON document per module, written once by the host from whatever it
already knows — an extraction tool's configuration, a linker map, or the
module header itself. Everything is module-relative except `image_start` and
`image_end`, which locate the module inside the image.

```json
{
  "schema": "decomp-workbench-module-map-v1",
  "module": {
    "name": "overlay1",
    "image_start": "0x184C000",
    "image_end": "0x1856000",
    "synthetic_vma": "0xF0000000",
    "sections": {
      ".text": { "offset": "0x0", "size": "0x8000" },
      ".data": { "offset": "0x8000", "size": "0x1200" }
    },
    "text_placement": [
      { "object": "build/overlay1.c.o", "section": ".text",
        "offset": "0x1000", "size": "0x240" }
    ],
    "relocation_sites": [
      { "offset": "0x1000", "type": "R_MIPS_26" },
      { "offset": "0x1018", "type": "R_MIPS_HI16" },
      { "offset": "0x101C", "type": "R_MIPS_LO16" }
    ],
    "alias_template": "func_{module}_{module_offset:07X}"
  }
}
```

* **`text_placement`** is the only thing the addend formula strictly needs
  beyond the image: where in the module each object's section sits, so a
  site's module offset is `placement.offset + relocation.offset`. It is
  deliberately *not* read from a linked ELF — the link is exactly what is
  missing in the case this page exists for.
* **`relocation_sites`** is the module's own shipped relocation table, if the
  host can decode it. A site the table does not name is not a relocation site
  in the shipped image, and reading an addend there reads an ordinary
  instruction word. When any site for a symbol *is* corroborated, the
  synthesis ignores the ones that are not; that is the image's own statement,
  not a heuristic, and it is what makes the procedure tolerant of a candidate
  whose schedule diverges away from the sites in question. Omit it and every
  site is trusted — the run says so in a warning.
* **`alias_template`** is optional. It spells whatever identity the host's
  extraction tool gives a module offset, so the generated block can also
  point those identities at the friendly names the adopted C defines.
  `module`, `module_offset`, `image_offset` and `vma` are available as format
  fields.

A section that ends past the module, or a placement outside its section, is
refused when the map is parsed. Both silently produce plausible-looking wrong
addends, which is the one outcome worth failing loudly for.

## `reloc-surface`

```sh
decomp-workbench reloc-surface build/overlay1.c.o build/overlay1_tail.c.o --module-map module.json --image target.z64
```

Pass **every** object of the module the link consumes, not just the one you
are promoting: a symbol another object of the same module defines needs no
assignment at all, and passing them together is how that is recognized.

The output is a linker symbol block — value lines, then the alias block —
ready to `INCLUDE` from the project's linker script, or to write with
`--out FILE`:

```text
/* Stored relocation addends, per translation unit. */

/* build/overlay1.c.o */
overlay1Chain0Reloc = 0xF000048C;
gOverlay1ModeObject = 0x00018010;
```

`--sites` reports every mapped site behind those values. `--json` emits the
whole surface under `decomp-workbench-reloc-surface-v1`, with `sites` included
only when `--sites` is also given.

Exit status is 0 when every referenced symbol got a value and 1 when any was
refused. The three refusals:

| `reason` | What it means | What to do |
|---|---|---|
| `schedule-divergence-at-site` | two sites demand different values | the candidate's instructions differ *at* the placeholder's own sites; that is a real residual, and the conflict localizes it |
| `no-corroborated-site` | the shipped table names the symbol, but not at any site this object still spells the same way | same cause, seen through the corroboration filter |
| `unmapped-site` | no site could be read from the image | the map is wrong, or the object is not the one placed there |

### Auditing a block you already have

A project that has been hand-writing these values can replay them:

```sh
decomp-workbench reloc-surface build/overlay1.c.o --module-map module.json --image target.z64 --audit overlay_undefined_syms.txt
```

Four outcomes, and the last two are as informative as the first two:
`agree`, `disagree` (which names both values), `untracked` — a value the
synthesis produced that the block does not carry, because the link defines it
by other means — and `unreproduced`, where the synthesis stops rather than
where the block is wrong. Exit status is 0 only when nothing disagrees and
nothing was refused.

## `linked-compare`

```sh
decomp-workbench linked-compare build/game.z64 target.z64 --range overlay1DrawActive:0x1878b84:0x1878c40
```

`NAME:START+SIZE` works too, `--range` repeats, and `--ranges FILE` reads a
whole trial's worth:

```json
{
  "schema": "decomp-workbench-image-ranges-v1",
  "ranges": [
    { "name": "overlay1DrawActive", "start": "0x1878B84", "end": "0x1878C40" },
    { "name": "overlay1AdvanceGauge", "start": "0x1878C40", "size": "0x120" }
  ]
}
```

Every entry needs a `name` and a `start`, plus either an `end` or a `size`;
integers may be written as numbers or as `"0x..."` strings. Each range is
classified:

| class | meaning |
|---|---|
| `exact` | the whole image is byte-identical |
| `text-exact` | nothing differs inside the range; something differs outside it — collateral, an ownership question rather than code work |
| `text-differs N words` | N words differ inside the range: a real residual, with a number |
| `size-differs (+N)` | the images are different lengths, so the range does not name the same bytes on both sides and no verdict about it would mean anything |

The report names the first differing offset inside the range and the first
one outside it. The image-level verdict is the worst of its ranges. Exit
status is 0 when every range's own bytes agree — `exact` or `text-exact` —
and 1 otherwise.

## The host-side loop

The workbench measures; the project builds. A promotion trial is four steps
the host owns, with a workbench command in the middle of two of them:

1. **Splice** the candidate into its translation unit, exactly as a promotion
   would.
2. **Build**. If the candidate references placeholders, this build stops at
   the link — that is expected, and it is the window `reloc-surface` fills:
   run it against the objects that now exist, write the block, and relink.
   The surface has to be regenerated *after* the candidate compiles and
   *before* the link, which is a window a plain `make` does not offer, so the
   host builds, generates, and builds again.
3. **Compare** the image with `linked-compare` against the function's range.
4. **Restore** the source, whatever happened.

Two things are worth building into step 2 rather than discovering later. A
project whose build asserts each object's exact layout (a size-trimmed
section, a digest over the relocation set) will abort at *compile* time when a
candidate's codegen is a different size, so the trial learns only
"build-error" for a whole class of candidates; a report-and-skip mode behind
an environment variable turns that into a measured size delta and a linked
image to diff. And the image such a build produces is not a valid build and
must never be verified or shipped — it exists to be compared.

### The worked example

Mickey's Speedway USA's decomp runs exactly this loop, and it is where the
procedure and its refusals were measured. Its `tools/reloc_surface.py` is the
project-side ancestor of `reloc-surface`: replayed over every overlay object
that project's link consumes, it reproduced **1773 of 1773** hand-written
symbol values with zero refusals, and a further 979 of 982 values the block
did not track agreed with the linked ELF's own symbols (the three exceptions
are lone `R_MIPS_LO16` sites, which observe only the low half of their
symbol's value — the emitted word is identical either way).

Its `tools/promotion_trial.py` is the project-side ancestor of
`linked-compare`, driving the four steps above per candidate. Generating the
whole surface rather than hand-writing it moved that project's measurable
overlay candidate pool from **110 of 279 to 150 of 279**, and turned a further
44 opaque build failures into an exact `.text` size delta. Every one of the
newly-linking candidates produced **zero out-of-range differing bytes**: the
synthesized surface disturbs nothing outside the promoted function.

Those objects, that image, and that project's tools are not redistributable
and are not here; what is cited is the measurement, and the fixtures behind
this page's tests are synthetic.

## `permute-doctor` routes to this page

The same fact that makes the linked image the oracle makes the permuter score
useless on these functions, and the symptom is indistinguishable from
[L69](compiler-laws/ido-5.3.md)'s badly-configured scratch: a search that
finds nothing. `permute-doctor` tells them apart when given the target
object:

```sh
decomp-workbench permute-doctor overlay1DrawActive --queue queue.json --target-object build/target.o --candidate-object build/overlay1.c.o
```

When every `R_MIPS_26` site in the target names the function itself or a
symbol the candidate object does not carry, the doctor reports the site count,
warns that the score cannot reach zero, and names `linked-compare`. It is a
warning rather than a refusal: the scratch may be healthy and the operator may
be searching it for another reason. Without `--target-object` the question is
not answered at all, and the report says nothing rather than "fine".

## Limits

* **The addend is only readable where the schedule agrees.** A candidate whose
  instructions differ at a placeholder's own sites gets a refusal, not a
  value. That is the model's stated precondition, and the refusal localizes
  the divergence.
* **A lone `R_MIPS_LO16` determines only the low half** of its symbol's value.
  The emitted instruction word is identical either way, so the link is right
  and the symbol value is non-canonical.
* **Without a shipped relocation table there is no corroboration.** Every site
  is trusted, so a literal the runtime does not patch cannot be told apart
  from an addend. The run warns.
* **`linked-compare` compares bytes, not meaning.** A `text-exact` verdict
  says the function's range agrees and something else moved; deciding whether
  that collateral is acceptable is [an ownership
  question](object-comparison.md#check-what-an-exact-function-changed-around-itself),
  not one this command answers.
* **Nothing here orchestrates a build.** A stale image compared against the
  target reports a match that will not rebuild; pair the loop with
  [`check-staleness`](object-comparison.md#is-the-thing-you-compared-the-thing-you-just-built).
