# Postmortem — the dp64 core campaign day (2026-07-29)

One session, one day. Starting state: core 1738/1748 (99.43%), overall
68.13%, no local toolchain, workbench 0.2.0 with 77 tests. Ending state:
**47 functions matched and submitted** (PRs #275/#276, ready for review),
core 1744/1748 (99.77%), overall 68.56%, workbench at 208 tests with the
`view` command, verdict taxonomy v2, and a human docs suite — plus six
compiler-instrumentation profiles and a ~35-entry mechanism catalog that
did the actual winning.

## What worked (keep doing)

1. **The loop that won every match**: comparator verdict → pick the lever
   family → census/trace-filter variants BEFORE compiling compares → one
   hypothesis per variant → integrate only on `instruction-words-identical`
   → full-ROM checksum oracle. Matches came in 1–4 variants once the right
   readout existed; hundreds of variants when it didn't. The instrument is
   always cheaper than the search.
2. **Build the missing readout instead of searching harder.** Every
   plateau that later broke, broke because a new instrument named the real
   layer: the pool tracer (blockSetupVertices), CDX p2 discovery
   (objprint), web-formation + BB-liveness (texLoad), COPYDEC (exonerated
   coalescing twice), PRE tracer (exonerated code motion, found the
   delay-slot layer). Six profiles, all fidelity-gated section-scoped,
   patchers preserved in `research-archive/dp64-2026-07-29/`.
3. **Cross-function lever transfer.** objprint's web-merge closed
   texDPTextures' cluster (b); texDPTextures' initializer-sinking fed the
   bCVC domino; blockSetupVertices' redundant-mask pattern came from
   rarezip's dead-web work. The field guide is the compounding asset —
   every campaign must read it first and write back to it.
4. **Volume mode for DLLs**: type one bss block → match every function
   touching it (8–10 per edit). Bottom-up (callees first). ~20-variant cap
   then revert. 41 matches in ~2 agent-hours.
5. **Oracle probes before source search**: a CDX force sweep answering "is
   there a single-force endpoint?" converts open search into bounded
   search, and sometimes the force IS the lever (texDPTextures'
   renderMipmaps force became a one-line initializer sink).

## What cost us (avoid)

1. **Positional word counts misranked candidates in six separate
   campaigns** — the single most expensive tool gap. LCS-aligned counting
   (`view`) is now mandatory for ranking; `words=` is only a same-shape
   tiebreaker.
2. **Layer misattribution ran for multiple rounds twice**: "it's ugen's
   FIFO" (objprint, texLoad) survived because the p1-only CDX sweep looked
   exhaustive (p1/p2 are disjoint namespaces) and because CDX_PROC
   off-by-ones mislabeled traces. Every instrument now prints
   phase/ordinal context; keep demanding that.
3. **Config contamination**: `configure.py --all-code` leaves
   `-DNON_MATCHING` in build.ninja and stale objects keep the checksum
   green until a recompile. Voided a wave of negative diagnoses (DLL
   210/437/413 need clean re-runs). Doctrine: `grep -c NON_MATCHING
   build.ninja` == 0 before trusting any verdict; ninja success is never
   match evidence — only the checksum line is.
4. **"Proven wall" claims need a second look at the premises.** Three
   walls fell after the blocking claim was re-derived: "hasTex needs a
   split web" (it needed two dual-role locals), "the ~110-word cascade is
   FIFO phase" (it was one copy-prop), "the scale hoist is PRE" (it was
   delay-slot coloring). The walls that stand (below) each survived an
   instrumented re-derivation — that's what makes them credible.
5. **Scratch-context lineage mismatches** burned several user paste
   cycles: two naming lineages exist across dp64 scratches, and decomp.me
   preset 28 lacks `-Wab,-r4300_mul`. Every paste file must be
   compile-verified against the exact ctx export first (now standing
   practice in the tracker repos).

## Where things live

- **Best candidates + per-function mechanism writeups**: the ten
  `akratch/dp64-<func>-wip` tracker repos (durable).
- **Mechanism catalog**: `docs/field-guide.md` (human) +
  `docs/field-notes-2026-07-29-dp64.md` (raw, ~970 lines) +
  `docs/skill-feed-2026-07-29.md` (skill-file staging).
- **Instrument patchers + key harnesses**:
  `research-archive/dp64-2026-07-29/` (this repo — our authored code
  only). The instrumented toolchain *builds* live in `/private/tmp/...`
  (ephemeral!): rebuild by applying the patchers to a static-recomp
  `uopt`/`ugen` C source per their headers. The base research tree was at
  `/private/tmp/sf64-ido-research.LtCtle/` — if gone, regenerate via
  ido-static-recomp and re-apply patchers.
- **dp64 branches**: `match-core-functions` / `match-dlls-batch1` (the PR
  branches, clean history); `match-rzipUncompress` (original 15 commits,
  still carries Co-Authored-By trailers — clean before ever pushing).

---

# Re-attack plan: the last 4 core functions

Ordered by expected effort-to-win. General rules: LCS-ranked scoring only;
census-filter first; re-verify any inherited "negative" under a clean
build.ninja; read the tracker repo README + the relevant field-notes
sections before the first variant.

## 1. texDPTextures — 2 words (tracker: dp64-texDPTextures-wip)

State: `texDPTextures.FINAL2w.dp64.c` — every register matches, insns/frame
exact, one transposed pair: target has `lw a1,140(sp)` @105 then
`lui t1,0x8000` @106; candidate emits the lui first. uopt hoists both block
constants to the pre-`.loc` head; as1 pulls the first into the preceding
delay slot; the reload can't precede the remaining li without an in-block
consumer (which costs a store). De-CSE of the constant is value-changing
(dead family, evidence in notes).

Next moves:
- **Re-derive the premise** (the day's lesson): dump the target's uopt
  ordering assumption — is the target's `lw` actually *ahead* of the li in
  ucode, or does as1 produce that order from a different head grouping?
  The PRE tracer's STMT dump + `cc -S` listing comparison of the exact
  block answers this in one run. If as1-side: the answer may be an
  `-Wab`-class flag or listing-order nuance, not source.
- **Constant-web birth block**: the 0x80000000 web's first occurrence
  drives placement. Try shapes where the FIRST K0 use in *ucode order*
  moves (reorder the two gSPDisplayList emissions inside the changed
  block; swap the tex1!=NULL/else arms' emission order if semantics
  allow; the `hasTex = renderFlags` copy position interacts — sweep its
  slot against the first K0 use).
- Integration cautions in the tracker README are load-bearing (pad3,
  `renderFlags |= 0` position, hasTex dual-role).

## 2. vsprintf — 35 real words (tracker: dp64-vsprintf-wip)

State: C proven correct (-g0 collapses the %e/%f regions to ~2 words); the
residual is `.loc`-barrier scheduling under -g3. 866 variants; line
layout/statement merging cannot move the barriers.

Next moves:
- **Statement-boundary archaeology**: the barriers are per *statement* —
  the original's statement structure may differ (e.g. merged assignments,
  comma expressions inside macro bodies, different PAD/outchar macro
  shapes). The macro bodies are invisible in our reasoning so far: vary
  the MACRO DEFINITIONS (outchar/PAD as comma-expressions vs do-while vs
  statement sequences) — each changes .loc counts inside expansions
  without changing emitted code. This family was never swept.
- **Compare against DKR's build**: DKR's matched vsprintf compiles under
  its own repo — diff its .loc structure (objdump --dwarf=decodedline) vs
  ours for the same-shaped regions; where DKR's line table is denser or
  sparser reveals the statement-shape difference to copy.
- If the macro family fails, this is the strongest candidate for a
  community ask with the -g0 evidence attached (the tracker README has it).

## 3. func_80053B24 (intersect) — 402 banked (tracker: dp64-func_80053B24-wip)

State: fully decomposed. B2 (~281w): uopt PDSE sinks both tri-loop IV
stores; `sp11C` solved in principle by a function-end read (6 of 9 extra
pool webs), the ×2 strength-reduction temp has no direct source handle.
B1+s4/s5 (63w): oracle-closed by `CDX_FORCE=w371=c16,w484=c19` (comma
separator!); source dial quantified (arg0's save → (715.5,750) ≈ nocs 41).
B4: 3 words, slti-vs-li spelling, unsolved. ~6w harness-floor (vanishes on
repo integration).

Next moves (order matters — B2 first, it dominates):
- **B2 via loop restructure**: the ×2 temp exists because the loop indexes
  `bitmap[sp11C]` with a halfword scale. A walking-pointer loop
  (`u16 *p = &bitmap[...]; ... p++`) REPLACES the strength-reduction temp
  with a source-level IV — prior "pointer-form" attempts were inside the
  increment-spelling sweep under the OLD understanding; re-try with the
  function-end read pattern applied to BOTH `sp11C` and `p` (both must be
  live-out per the corrected rule: whole-function liveness forces
  memory-residency; short live-out promotes). Also try indexing from a
  SECOND variable (`j = sp11C * 2` maintained in-loop as its own IV) —
  gives the ×2 value a name and a store.
- **B1 source dial**: arg0 needs ~5 more call-crossings. A late
  `if (arg0) {}` AFTER several calls (post-loop region) — prologue reads
  cost insns but late ones may not (unverified: the campaign only swept
  prologue). w484 (arg7&8): store it to a local used across ≥4 calls.
- **B4 last**: try the GameCube scratch (pyduQ) reading of that loop for
  the exact spelling; also `for (t0 = 0; t0 != 3; t0++)` with the bound in
  a variable (blocks the range proof).

## 4. blockComputeVertexColors — 676 words (tracker: dp64-blockComputeVertexColors-wip)

State: frame + every declared stack offset exact; prefix 0-216
byte-identical; D_a0c0 base (case-arm dead read puts var_a0_2 in a0).
Blocker: the scale (`var_a0_2*4`) must color v1 (the dying flag web's
register) via per-case remat, but every construct separating it from the
selector evicts var_a0_2 from a0 — proven anti-correlation across 12
pairings. The delay-slot collision rule (field notes) explains the +2
insns/region cascade; 191 of 217 aligned diffs are downstream of this one
decision.

Next moves:
- **The web-merge play, one level up**: the target's scale coalesces into
  the FLAG's dying register. Merge them at source: derive the scale FROM
  the flag local's carrier — e.g. reuse the flag variable (or a dual-role
  local that carries flag-then-scale) so the scale inherits the flag web's
  color the way objprint/texDPT merges inherited masks. The campaign
  attacked selector/scale separation; it never tried scale-INTO-flag
  merging (the readout suggests IDO does exactly this internally).
- **Priority route**: with LR fields decoded (lr+0x30 save etc.), compute
  what save the scale web needs to color AFTER the flag web dies —
  read-count/initializer-sink dials to hit that window, filtered on the
  census in one grep.
- The four blend blocks repeat — verify any winning edit replicates 4×
  before full compare (per-block census).

## Shared infrastructure asks (build once, benefit all four)

1. `--align`/LCS ranking into `compare` proper (6 campaigns misranked).
2. `--census KEY=VALUE` predicate (rebuilt 7+ times).
3. CDX_FORCE: decline forbidden colors with a message (SIGABRT killed
   probes in 3 campaigns); phase-qualified keys everywhere (the workbench
   validators are fixed; the research-tree binaries predate that).
4. If the /private/tmp research tree is gone: rebuild ido-static-recomp
   5.3, apply `research-archive/dp64-2026-07-29/instrument-patchers/` in
   order (pool → emit → webform → copyprop → prehoist share lineage;
   headers document their base files).
