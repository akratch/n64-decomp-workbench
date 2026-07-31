# Field notes — SSB64 `drawbitmap` campaign (2026-07-31)

Live-fire observations from matching `drawbitmap` (libultra sprite library,
`sprite.c`, SSB64 US; IDO 7.1, `-O2 -mips2`; 1479 instructions). Full
narrative: [case study](../case-studies/ssb64-drawbitmap.md). Project-neutral;
no ROMs, objects, or proprietary artifacts.

## Headline

A version-gated SDK switch case (`#if BUILD_VERSION >= VERSION_J`, both
macros undefined, guard evaluates true) produced a +109-instruction
structure-mismatch that every prior attempt inherited without diagnosing.
Fixed by `#include <PR/os_version.h>` — size-exact, 5916/5916 bytes,
register allocation exact (661/661 pool webs and temp-FIFO slots). The
remaining 59-word/23-cluster `schedule-mismatch` survived hours of compiler-
version archaeology (five IDO/MIPSpro generations, every `as1` model flag,
independent cross-era stage mixing) before a decomp-permuter **zero-mutation**
round-trip changed the schedule anyway, exposing the real cause: `cfe`
attributes per-statement line numbers from the *preprocessed* input, and
`uopt`/`ugen` honor those as scheduling barriers even at `-g0`. Preprocessing
externally with IDO's `acpp` instead of `cfe`'s internal preprocessor gives
each statement of a multi-line macro expansion its own source line, matching
the ROM's barriers exactly. The full US ROM rebuilds sha1-equal from clean SDK
source with a one-rule Makefile change (route this TU through `acpp` first).

## Gaps / friction

- **The `-g0` diagnostic's guidance needs a caveat.** Field guide lever 3
  frames `-g0` as removing `.loc`-driven scheduling constraints; that's true
  of the *object's* debug records, but statement-line metadata reaching
  `uopt`/`ugen` from the preprocessor is a separate, earlier input that
  `-g0` does not touch. A `-g0` rebuild that fails to collapse a
  `schedule-mismatch` residue is not proof the scheduler is unreachable — it
  can mean the barrier is upstream of `-g0`. Worth a documented caveat
  alongside lever 3, ideally backed by something like the workbench's
  line-assignment probe so this is a one-command check instead of a manual
  `.loc`/line-reflow comparison.
- **Silent flag fallback produced a false exhaustion proof.** `as1`'s
  `-t0`..`-t9` scheduling-model flags were swept with stderr suppressed;
  several spellings were invalid for the `as1` build in use and silently
  fell back to the default model. Eleven visibly different invocations
  produced eleven identical outputs, read as "the model space is exhausted."
  It wasn't run. A sweep harness should treat an unrecognized flag as fatal,
  or at minimum surface stderr, before a flat result is trusted as negative
  evidence.
- **`alternate-frontends.md`'s fingerprint table may need revisiting.** Its
  established-fingerprints table lists source line numbers as "not observed"
  to be semantic under `cfe` (only under `accom`). This campaign found a
  cfe-side line-attribution effect too — gated on which *preprocessor* feeds
  `cfe`, not on the frontend itself. Not the same claim as lever 21's
  `accom` line placement, but adjacent enough that a future pass over that
  table should account for it explicitly rather than leave the two findings
  unreconciled.
- **decomp.me paste pitfalls, now in troubleshooting.md**: missing trailing
  newline on `ctx` (site concatenates verbatim; first code line fuses onto
  the last context statement) and re-declaring statics the exported `ctx`
  already declares. Both cost paste cycles before the actual export bundle
  was used as the template instead of a hand-assembled one. A context lint
  ahead of paste would catch both mechanically.

## Validated (keep doing this)

- **Control-function discipline paid for itself immediately.** Every
  compiler-configuration experiment during the era-archaeology stretch was
  checked against `spDraw` (a known-matching sibling in the same TU) before
  being trusted as evidence about `drawbitmap`. Configurations that broke
  `spDraw` were discarded in one comparison, not after a week of downstream
  reasoning built on a broken premise.
- **Output-hash clustering ("attractors") compressed the wrong turn.**
  Dozens of superficially distinct compiler/flag configurations reduced to
  exactly two facts: one byte-identical 59-word residue ("attractor A") or a
  broken control function. Naming and tracking the attractor made it visible
  that the sweep had stopped producing new information long before it
  stopped producing new-looking attempts.
- **A permuter round-trip with zero mutations is a legitimate diagnostic
  move, not just search-prep.** Running `decomp-permuter`'s
  parse/re-emit step with no mutations at all is meant to be a codegen
  no-op; here it wasn't, and that gap was the whole signal. Worth keeping as
  a standing check whenever a residue resists every source-shape lever:
  re-emit unchanged and diff, before concluding the compiler is the
  variable.
- **A byte-for-byte token match with a line-reflow-only change is a clean,
  falsifiable confirmation.** Once the permuter round-trip pointed at line
  layout, reflowing the token-identical `.i` file by hand reproduced the
  same 48-site shift with no permuter involved — isolating the causal
  variable to line breaks alone, independent of any other tool's behavior.

## Numbers

| stage | value |
|---|---|
| function size | 1479 instructions |
| local build, before fix | 6352 bytes |
| ROM | 5916 bytes |
| structure-mismatch gap (Trap 1) | +109 instructions / +436 bytes, one extra jump-table case |
| after `os_version.h` fix | size-exact 5916/5916 bytes |
| register allocation after fix | 661/661 pool webs and temp-FIFO slots identical |
| residual after Trap 1 fix | 59 words, 23 clusters, pure instruction-order swaps |
| compiler generations swept (era-archaeology trap) | IDO 5.2, 5.3, 6.0, 7.1, MIPSpro 7.4.4 (o32) |
| `as1` model-flag sweep, falsely read as exhausted | 11 invocations, stderr suppressed, all fell back to default |
| permuter zero-mutation round-trip | 48 of 59 sites flipped toward the ROM |
| final result | drawbitmap reaches the relocation floor; full US ROM sha1-equal |
| decomp.me paste form | expanded macros + 12 `#line` directives |
