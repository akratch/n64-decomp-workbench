# Alternate authentic frontends

The workbench's compiler tooling treats the toolchain as one unit. The
SSB64 ovl8 campaign (2026-07-29/30) proved that the **frontend is a
variable**: a translation unit can be compiled by a frontend from a
different toolchain generation than its backend, and the resulting object
is unreachable from the backend's own frontend no matter what source is
written. This page records the inventory, the invocation recipes, and the
discrimination method, so the next stock-impossible dispatch costs hours
instead of weeks.

## When to suspect a foreign frontend

- A dispatch shape the project compiler provably cannot emit (e.g. a
  4-entry jump table under IDO cfe, whose grouping threshold is a
  hardcoded five labels at two `sltiu at,a1,5` sites).
- Deviations that cluster by translation unit while the rest of the
  binary matches the project compiler byte-for-byte.
- Residues that no source spelling moves, in functions whose siblings
  match — especially operand-order or scheduling conventions.

## Inventory of ucode frontends (all feed uopt/ugen/as1)

| frontend | ships in | language | notes |
|---|---|---|---|
| `cfe` | IDO 5.x–7.x | C | the assumed default; 5.2/5.3/6.0/7.1 binaries are behavior-identical on switch lowering |
| `ccom` | IDO ≤4.x (ECOFF era) | K&R C | jump-table threshold **4** |
| `accom` | IDO ≤4.x (ECOFF era) | ANSI C | threshold **4**; the SSB64 ovl8 frontend match |
| `upas` | IDO through 7.1 | Pascal | tables every dense `case` from N=2; positional argv |
| `fcom` | Fortran Dev Option | F77 | untested — no archived media located yet |
| `ecfe` | IRIX 5.2/6.0 trees | — | **red herring**: broken 1988–91 EDG C→C translator, no code generator, referenced by nothing |

## Invocation recipes (validated)

ECOFF-era frontends run under the `qemu-irix-4.0` + `ecoff_tool.py` rig
that decomp.me's ido4.1 package bundles. Operational caveats that cost
real debugging time: the emulator's host needs glibc ≥ 2.38; `/usr/tmp`
must exist in the sandbox; `ecoff_tool.py --convert-elf` accepts
**little-endian ECOFF only** (irrelevant for the ucode path below, which
never assembles under 4.1).

C through accom (4.1), backend from a modern ido-recomp 7.1:

```sh
# frontend (in an amd64 container with the 4.1 tree at $D)
qemu-irix-4.0 -silent -L "$D" "$D/usr/lib/acpp" -nostdinc -undef -p \
  -DLANGUAGE_C -D_LANGUAGE_C -Dsgi -Dunix -Dmips -D_MIPSEB -DMIPSEB \
  in.c > in.i
qemu-irix-4.0 -silent -L "$D" "$D/usr/lib/accom" \
  -Xv -EB -Xg0 -O2 -Xprototypes -Xxansi -XSin.T < in.i > in.B
# backend (native ido-recomp 7.1; project flags shown)
uopt -G 0 -mips2 -EB -g0 -O2 in.B in.O -t in.T tmp1
ugen -G 0 -mips2 -EB -g0 -O2 in.O -o in.G -t in.T -temp tmp2
as1 -t5_ll_sc_bug -elf -G 0 -p0 -mips2 -EB -g0 -O2 in.G -o out.o -t in.T
```

Pascal through upas (7.1, fully native):

```sh
upas -EB -G 0 -O2 in.p in.B in.T   # positional; unknown flags ignored
# same uopt/ugen/as1 tail as above
```

Cross-generation ucode handoff (4.1 B-ucode + symtab into 7.1 uopt) works
directly. The 4.1 backend does not reproduce 7.1 schedules (its own full
pipeline lands ~373/392 on a 391-instruction reference function); the
hybrid is the point.

## The fingerprint atlas method

Before porting whole functions, discriminate frontends with a probe
matrix, one small function per cell, through the identical backend:

1. dense switches N=2..6 → threshold map (`sltiu` immediate or chain);
2. sparse switches in source order, standalone and in-loop with the
   selector re-read from a global → test order, layout, and whether
   hoisted-constant compares are const-first or value-first;
3. `if/else if` versions of the same → chains carry no sort, so they
   isolate layout conventions from sorting;
4. an s16 loop counter indexing a scaled array → strength-reduction
   signature (C frontends model sign-extension at the use, blocking
   uopt's SR; upas truncates at the assignment, enabling it).

Judge each target-binary pattern separately: splat translation units can
merge several original source files, so one "TU" may legitimately mix
frontends (and languages).

## Established fingerprints (SSB64 campaign)

| behavior | accom/ccom 4.1 | cfe 5.2–7.1 | upas 7.1 |
|---|---|---|---|
| dense jump-table threshold | 4 | 5 | 2 |
| sub-threshold dense switch | ascending chain | ascending chain | (always tables) |
| sparse switch order | ascending, bodies-first | ascending, dispatch-first | value-split tree |
| if-chain order | source order | source order | source order |
| in-loop if-chain compare | **const-first** | value-first (const-first only with a global expression on the LHS) | — |
| address-sum reassociation | never | tree-height reduction | — |
| s16-counter strength reduction | blocked | blocked | performed |
| source line numbers | **semantic** (newline placement changes scheduling) | not observed | not observed |

Anonymous unions, `//` comments, and statements-before-declarations are
hard errors under accom — rejections are evidence about original source
shape, not just obstacles.
