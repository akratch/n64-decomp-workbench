# Field notes — Dinosaur Planet core campaign (2026-07-29)

Live-fire observations from applying the workbench to the dp64 core hard-nuts
(first target: `rarezipUncompress`, IDO 5.3, -O2 -g3 -mips2). Project-neutral;
no ROMs, objects, or proprietary artifacts. Roll confirmed items into
`tooling-roadmap.md`.

## Gaps / friction

- **`--function` alias for `--symbol`** (`compare`, `campaign`, `rank`).
  First real invocation this session used `--function` reflexively and failed;
  decomp vocabulary says "function", GNU vocabulary says "symbol". Accept both.
- **Empty skill directories in the repo checkout.** `skills/n64-decomp-campaign/`
  contains empty `agents/` and `references/` dirs in git, while `install-skill`
  emits populated references from the packaged copy. Browsing the repo suggests
  the skill is hollow. Either check in the canonical content or remove the
  placeholder dirs.

## Validated (keep doing this)

- `compare --show-diff` classified the rarezipUncompress residual as
  `allocation-mismatch` with per-web register ranges and an action-oriented
  `next:` line in one command — it selected the experiment family (lifetimes /
  declaration order, not fakes) with zero manual triage. The verdict-first
  output design is earning its keep.

## decomp_permuter integration notes (dp64, via Sonnet agent run)

- dp64's permuter settings live at `tools/permuter_settings.toml`, not repo
  root; root `diff_settings.py` belongs to asm-differ. Document per-project
  discovery in the skill references.
- `import.py` auto-defines `-DNON_MATCHING`/`-DPERMUTER` during preprocessing,
  so `#ifndef NON_MATCHING` guards resolve to the real-C branch with no manual
  flattening. Worth a line in campaign-hygiene.md — saves a manual step.
- `import.py` writes `nonmatchings/` relative to CWD; running it from a scratch
  dir keeps generated dirs out of the project tree.
- Case study for the skill: permuter solved one of two allocator webs
  (35→15) with a C-level red-herring mutation (dead `!global` hoist) whose real
  effect was raising the global-address web cost until it colored $a3. The
  workbench's basin/verdict view is the right lens for spotting this; the
  permuter's own diff.txt is not.

## From the rarezipUncompress campaign (Opus agent; MATCHED — 700 variants, 52 ledger rows)

- **`campaign` throughput**: compile is ~0.07 s, per-variant `compare`
  subprocess dominates. Agent abandoned `campaign` for a direct-import harness
  during the search phase. Wanted: in-process compare under `--jobs`, or a
  `compare-many` (N candidates vs one target).
- **No register-assignment readout**: the key signal was "which register did
  web X get" — agent had to objdump+regex every variant. Add `--report-regs`
  (per-index candidate/target register pairs even for matching instructions).
- **`--json` keys diverge from human labels**: prints `words=`/`insns=`/
  `frame=` but JSON has `word_mismatches`/`candidate_instructions`/
  `candidate_frame_size`. Cost a debugging cycle. Align or document.
- **`campaign` lacks `--stop-on-exact`**: a 300-variant sweep pays full price
  after the winner compiles.
- ~~trace-globalcolor/instrument-uopt unusable; 5.3 has no uopt~~ **CORRECTION
  (objprint campaign): IDO 5.3 does ship uopt, and an instrumented 5.3
  toolchain already exists on this machine** at
  `/private/tmp/sf64-ido-research.LtCtle/build/5.3/` (`uopt.instrumented-v6`
  with CDX_LOG/CDX_PROC/CDX_FORCE/CDX_DETAIL_WEB, `ugen.instrumented` with
  DKWB_UGEN_TRACE). Wiring is manual (symlink dir + swap binaries + USR_LIB) —
  wants a `--toolchain-dir` flag that automates it. Real gaps found instead:
  `CDX_PROC` atoi()s its arg (symbol names silently become proc 0), and the
  ugen copy-elimination/register-preference path is uninstrumented — the
  objprint coalescing residual was invisible to all current traces. Feature
  ask: log "temp web T proposed for coalescing into V, accepted/rejected,
  reason" + free-list push discipline (front/back) on release.
- **New skill technique (validated)**: when tracing is unavailable, black-box
  pool probing with synthetic multi-carrier functions maps the allocator's
  color order (here: `v0,v1,a0..a3,t0..t5` pool + separate `t6/t7/t8` temp
  rotation). Dead-web positioning then *selects* target registers: dead global
  reads ahead of a carrier march it down the pool; a dead loop-spanning local
  promotes a reload from temp rotation into the pool. This matched the
  function. Write it into ido-late-stage-patterns.md.
- **Basin reporting validated**: proved two whole variant families were no-ops
  in one run each — exactly its purpose.

## texDPTextureSimple observations

- **New diff class wanted: commutative-operand-order.** Residual is two `or`
  instructions with swapped rs/rt carrying the same values. `compare` calls it
  `allocation-mismatch` and suggests allocator traces — wrong lever. Detect
  "same opcode, same operand set, swapped order on a commutative op" and emit
  a dedicated verdict + guidance (expression-tree/statement-shape levers, not
  register lifetimes).
- Confirmed IDO 5.3 canonicalizes source-level commutative swaps: `a | b` vs
  `b | a` produced byte-identical objects (same content hash). Document in
  ido-late-stage-patterns.md so campaigns skip that dead family.

## texDPTextureSimple resolution (MATCHED) — two more comparator gaps

- **BUG: `--show-diff` omits non-register raw diffs under an
  `allocation-mismatch` verdict.** A `li v0,33` vs `li v0,49` literal diff was
  counted in `raw=3` but never printed (only register-range groups are shown).
  Cost a mis-framed subagent brief ("2 sites" when there were 3). Fix: always
  print every raw-diff site, grouped by class; never let the verdict filter
  the display.
- **`import.py` (decomp_permuter) `find_root_dir` needs absolute paths** when
  run outside the repo (it abspaths the c_file's dirname). Workbench docs/skill
  should note: pass absolute c_file/asm paths, keep cwd in the scratch dir.
- **Mechanism (for ido-late-stage-patterns.md):** commutative operand order on
  `or` follows front-end AST shape: `x = y | x` and `x = x | y` canonicalize
  identically, but `x |= y` is a distinct AST and flips emitted operand order.
  Compound assignment is the lever for commutative-order residuals.
- **Search-tool boundary (for the skill):** permuter cannot mutate arbitrary
  integer literals toward unknown values; literal diffs are hand/compare work.

## modLoadAnimActual campaign (MATCHED — 529 ledger rows)

- **Top feature ask: per-block temp-allocation sequence view.** The decisive
  signal was the ordered register sequence assigned to expression temps within
  a basic block (target vs candidate side by side) — agent had to build it
  with objdump+regex (`seqrep.py` in the campaign workspace; harvest it).
  With it: solved in ~15 variants. Without: 300 variants of nothing. Diffing
  only mismatched instructions hides the signal — the *matching* temps
  identified the queue.
- **Mechanism (for ido-late-stage-patterns.md): IDO 5.3 block-local temp FIFO.**
  Temps pop from a free queue and push back at last use; the phase entering a
  block is set by the *preceding* block's expression shapes and value deaths.
  Two source levers proven: hoisting a call-argument expression into a local
  (reorders deaths), and `(x == -1) != 0`-style comparisons (materialize a
  phantom pop with no emitted instruction). Allocation-mismatch guidance should
  offer "perturb the preceding block" alongside lifetime advice — and stop
  recommending globalcolor traces where they're unavailable.
- **Verdict naming**: equal-length reordered outputs get `structure-mismatch`;
  split into `schedule-mismatch` (same count, reordered) vs true structure.
- **`--json` key divergence** bit a second campaign. Prioritize.
- **Permuter boundary confirmed again**: 5k iterations, never beat base on a
  temp-phase residual whose fix was nominally in its mutation space. State in
  the skill: temp-phase residuals → directed search, not permuter.

## texLoadTextureActual round 1 (unsolved; 13 words persist)

- Diagnostic value of "byte-identical prefix, divergent temp state": add this
  as a named pattern in the skill — it points at *upstream, byte-invisible*
  levers (phantom queue pops, value-death reordering), not at the visible
  divergent block. Round-1 agent burned 13 variants on the visible block; the
  playbook should redirect earlier.
- decomp_permuter `base.c` uses `#pragma _permuter define` sentinels resolved
  only by permuter's own preprocessing — `compile.sh` on raw `base.c` fails
  with misleading cfe errors on macro-heavy TUs. Document: hand-testing should
  use a full real-TU copy, never the permuter's base.c.
- Campaign harnesses (or agents) must kill their spawned permuter jobs on
  exit — a leftover `-j10` job degraded two subsequent runs (semaphore-leak
  crashes under contention). The workbench campaign runner could own process
  lifecycle to make this structural.

## texLoadTextureActual round 2 — sequence view validated as a product feature

- The per-class register-sequence extractor (temp rotation vs coloring pool,
  target vs candidate) falsified the FIFO-phase hypothesis in one command:
  temp sequence identical 39/39, pool sequence divergent at exactly 4 slots.
  It converted "phase bug or coloring-order bug?" from ~20 blind variants into
  a one-minute answer. This should be a first-class workbench command
  (`compare --seq` or `seq-view`), not a per-campaign regex script.
- Negative mechanism data (document in ido-late-stage-patterns.md): bare
  discarded expressions (`id == id;`, `(void)(x & mask);`) are dropped by IDO
  5.3 with zero codegen effect — phantom pops require the comparison to feed a
  real context (modLoadAnim's came from `(x == -1) != 0` inside an `if`).
  Boolean-normalizing an actual branch condition (`(a < b) != 0`) is NOT free
  here (broke bltz/bgez folding, +178 words) — context-dependent, not a
  universal lever.

## vsprintf lineage recon (informs cross-ROM workflow docs)

- Lineage recon before campaigning paid off enormously on a 1245-insn
  function: dp64 vsprintf = glibc 1.09 vfprintf → Rare shared "di" printf;
  integer core byte-verified in DKR, float paths match JFG's later f32
  revision (proven via lwc1/ldc1 census of the target asm — a cheap,
  decisive lineage signal worth documenting as a technique).
- `compare --cross-rom` needs two built objects — impractical when the
  reference project's toolchain isn't stood up. A lighter-weight
  "cross-source structural witness" mode (compare target asm against a
  *source-only* reference via shape features) would make lineage recon
  first-class.
- decomp.me is Cloudflare-gated (403 to non-browser fetchers, HTML and API
  both) — agents cannot read scratch state. Affects the escalation loop:
  bundle-scratch out is fine, but reading community progress back requires a
  human or authenticated browser. Note in scratch-bundles.md.

## objprint endgame — uopt layer formally exonerated (5 words remain)

- Exhaustive CDX_FORCE over all 26 globalcolor webs proved the residual web
  (`textureAnimationCount` reload → must be v1, gets v0) is NOT uopt-colored:
  it comes from ugen's local allocator. First recorded case of comparator +
  CDX oracle jointly *proving* a residual sits below globalcolor — write this
  up as the skill's escalation-proof pattern.
- Empty-if reads confirmed as a general lever (zero-insn dead webs that shift
  pool coloring) but they cannot occupy v0 here; they take v1 — the register
  we need freed. Dead-web positioning has a reachability boundary; document.
- `CDX_PROC` atoi() bug bit again — agent initially traced proc 0 and drew a
  wrong conclusion. Symbol-name support is now a correctness issue, not
  convenience.
- **Concrete instrumentation ask (serves objprint AND texLoadTextureActual):**
  extend `ugen.instrumented` to log local-allocator pool get/put per request
  (register, requesting web/temp id, front-vs-back release discipline), and
  what routes a value to the expression-temp path vs a colored variable.
  Current DKWB_UGEN_TRACE covers `^f_` functions only and was byte-identical
  across the divergent builds — the deciding path is dark.

## intersect func_80053B24 scoping (402w, mapped not moved)

- **Promote an LCS instruction aligner into the workbench.** Second campaign
  today that had to build one ad hoc: positional diffing turns one upstream
  register-role swap into ~76 phantom scattered diffs; LCS alignment reveals
  the true ~43 structural hunks. `compare --align` remains the ask, now with
  two concrete implementations to harvest (campaign_objprint/fast.py,
  campaign_intersect/lcs_diff_base.txt generator).
- Callee-saved coloring tie-breaks (which var gets $s1 vs $s2) are a distinct
  residual class: source reorders either canonicalize away or explode (+334w).
  Needs the CDX oracle, not source search — queue a CDX_FORCE probe on the B1
  web pair as the intersect finisher's first move.
- `tools/m2ctx.py` (dp64) writes ctx.c to repo root unconditionally — upstream
  nit worth a PR alongside the macOS fixes.

## blockSetupVertices (183→21w; two structural finds; plateaus on ugen again)

- Wrong-constant class: candidate checked RENDER_UNK10 (0x10) where the asm
  materializes `lui 0x10` = 0x00100000 = RENDER_DECAL. One wrong identifier
  produced 183 "structural" words. Skill addition: when a large structural
  diff starts at a constant materialization (lui/andi mismatch), audit the
  flag/enum choice FIRST — the asm encodes the truth.
- Stale-hack interaction: an old `if ((s32)x) {}` pad was compensating for
  the wrong constant's register pressure; fixing the constant required
  removing the hack (frame/regs snapped exact). Lesson: re-derive fakes after
  any structural fix; they may have been fitted to the wrong body.
- Boundary case for dead-reads: in this loop context the `if ((s32)X) {}` web
  always lands function-lifetime (callee-saved tier), never loop-scoped —
  cannot add a loop-body temp. Complements the objprint reachability limit.
- **Counter-example to "declaration order is usually inert"**: removing a
  fully-unreferenced local (`pad`) changed codegen for other variables 20+
  insns away (21→38w) — internal numbering/tie-break effect. Cite in the
  playbook next to the inertness claim.
- Third residual proven/likely in ugen's local free-list (with objprint 5w,
  texLoad 13w): temp count differs (7 vs 6 t-regs) forcing a reuse. The ugen
  pool instrumentation now unblocks three functions at once.

## ugen deep-dive — hypothesis refuted, real layer found (MAJOR)

- **ugen exonerated by instrumentation**: its pool seeds t0–t9 only (minus
  uopt-claimed regs), strict FIFO (`f_append_to_list` tail-only,
  `f_remove_head` head-only). v0/v1/a0–a3 NEVER come from ugen — `f_ureg`
  reads them verbatim from uopt's ucode. The "local allocator front/back"
  theory is dead; update earlier notes.
- **CDX p1/p2 namespace trap (root cause of the false exoneration)**:
  globalcolor emits disjoint `p1dec` (callee-saved phase) and `p2dec`
  (caller-saved phase) web spaces. objprint's earlier "exhaustive 26-web
  sweep" was p1-only. The residual is **p2 web 55**; `CDX_FORCE=w55=c2`
  yields verdict-exact (words=0). Tool fixes: tag records with phase,
  phase-qualify CDX_FORCE keys, decode colors to machine regs via the
  0x10001ae0 coloroffset table, emit explicit `decision=firstfree` records
  (p2 does first-free scan, no cost comparison — zero cost records reads as
  "no data").
- **instrument-ugen's FREE_LIST_FUNCTIONS map is wrong for 5.3** (names like
  f_alloc_reg don't exist; real seams: f_get_free_reg/f_get_one_free_reg/
  f_remove_head/f_append_to_list). Hooks silently no-op'd — why earlier
  traces looked byte-identical. Adopt the new wrapper technique (rename to
  __dkwbreal + same-signature wrapper: captures args AND returns, survives
  indirect dispatch). Patcher: scratchpad/ugen_deepdive/patch_pool.py →
  productize as DKWB_UGEN_POOL_V1 profile.
- **Byte-identity gates must be section-scoped**: stock IDO cc under -g3 is
  file-level non-reproducible (.mdebug varies run to run). Gate on
  .text/.rodata/.data/relocs/symbols. Fix compiler-instrumentation.md wording.
- New skill technique: differential CDX diff between a v0-candidate and any
  corpus variant that achieves the wanted register reveals the deciding
  property (here: caller-saved interference count on the save≈5.5 prologue
  web). The 222-variant corpus was load-bearing — keep campaign objects.

## texDPTextures authoring (209→161w; instrumented triage on first outing)

- The new pool instrumentation was used by a *different* agent within the
  hour and productively triaged a fresh function — validates productizing
  DKWB_UGEN_POOL_V1. Bugs found on first reuse: `DKWB_UGEN_POOL_PROC` filter
  ignored (all procs logged); `USR_LIB` override silently no-ops when `cc`
  is a symlink (needs a real copy — document or fix in the toolchain-dir
  automation); pool trace lacks source correlation (opaque IR node pointers —
  line-number annotation is the ask).
- Dual-role local idiom (one variable reused across disjoint lifetimes,
  e.g. `frameOptions>>16` then a boolean) is a Rare-era source pattern worth
  listing in ido-late-stage-patterns.md — splitting it into two locals costs
  a live register everywhere downstream (48-word swing here).
- Another "systemic single-shift" residual misclassified as
  structure-mismatch by volume — strengthens the verdict-classes ask
  (phase-shift/allocation classes should win over word volume).

## Deep-dive round 2 — p2 color map decoded; texLoad's true mechanism

- Empirical p2 color→register map: c1=v0 c2=v1 c3=a0 c4=a1 c5=a2 (decoded by
  force-and-diff). Ship this decode in the CDX output.
- objprint: proven hard tension — the only mask-moving lever (a bare label)
  works by displacing sp6C onto v0. Handoff spec: a sub-55 p2 web (26 is the
  candidate; 21 has c1 forbidden) must become profitable and take v0 without
  touching sp6C. "Make a web profitable via zero-code dead references" is the
  next technique to validate.
- texLoad: 585-force sweep proves globalcolor empty (45 p1 webs, 0 p2). Pool
  trace shows full t0–t9 FIFO round-robin; **an expression temp's register is
  a pure function of the count of preceding pool gets** — phase, measurable
  live via DKWB_UGEN_POOL. New workflow: check pool-get count in the trace
  before bothering to compare. Also: uopt claiming registers (objprint: v0,v1,
  t0–t5) vs claiming nothing (texLoad) completely changes which layer owns a
  residual — a per-proc "who claimed what" summary line would route diagnosis
  instantly.

## Deep-dive round 3 — the dark path is uopt's non-globalcolor assignment

- objprint premise refuted by mask decode: webs 21/26 already have c1
  forbidden (they interfere with the v0 holder); coloring them can only steal
  v1 or a1. No sub-55 p2 web can become the needed v0 blocker in any reached
  shape (~140 variants, mask rigid at 0x08cbbf00). CDX_FORCE is a no-op on
  no-color webs (18 forces byte-identical) — document.
- webdetail raw10 = frame offset for type=3 webs (raw14=0x04ae0102 marker) —
  the web→source-variable decoder ring. Ship this decode.
- Unused-declaration drops are fully inert (dropped before uopt) —
  declaration levers act on USED locals only.
- texLoad: phantom pool gets via `(x)!=0` inside real conditionals CONFIRMED
  (+1/+2 gets) but every pre-block placement breaks bltz/beq folding and the
  prefix. 856-force p1 sweep = zero hits; proc has zero p2 records; v0/a1
  arrive via f_ureg from uopt with NO coloring record. Round-2 "it's the ugen
  pool" self-corrected: the pool rotation is downstream of ONE extra uopt
  allocation decision at insn 43.
- **Converged conclusion: objprint (5w) and texLoad (13w) share one missing
  instrument — uopt's non-globalcolor register assignment path (v0/v1/a0/a1
  handed out with no p1dec/p2dec record). Highest-value single build.**

## vsprintf campaign (866 variants; plateau with the C proven correct)

- **Positional counting hid a near-match**: comparator said 635 words; opcode-
  aligned truth is 27 structural + 8 register (3 "relocation_controlled" were
  false positives — named symbol+0 vs section+addend at the same final
  offset; the comparator has the symbol tables and should prove equivalence).
  The `--align` structural/schedule/register split is now the #1 comparator
  ask (matches the UX vision's `view` bet).
- **NEW top-value mechanism: `-g3` is a scheduling constraint.** IDO emits
  `.loc` per statement; as1 restricts cross-block motion at those barriers.
  Diagnostic: recompile the candidate `-g0`; if the divergent region
  collapses to ~exact (vsprintf %e/%f: 25→2), the C is correct and the
  residual is debug-info scheduling — STOP searching source space. One
  command replaces ~550 blind variants. Line joins/comma merges cannot remove
  the barriers (.loc is per statement). → skill + ido-late-stage-patterns.
- `replay-as1` is a differential probe, not byte-faithful for IDO 5.3
  (listing→as0→as1 loses binasm scheduling metadata; silently ignores -Wa
  flags) — document as such.
- decomp_permuter hard boundary: IDO `va_arg` is unparsable by pycparser
  either expanded or preserved — permuter unusable on all varargs functions.
  Opaque-expression mode is the fix.
- Seed quirks vindicated: the repo's odd inline `if (spacing) { done++;
  (*s++)=0x84; }` form and named string constants (D_8009AE44 vs local
  static) were load-bearing; the `outchar()` macro form is NOT correct for
  this TU. Named-vs-local-static strings changed 5 register words.
- `cc -S` writes to cwd ignoring -o (leaves .s in repo root — clean up).

## blockSetupVertices instrument round — classified, not moved (20w)

- Globalcolor exhaustively exonerated (31 p1 webs × colors 1-34, zero p2
  records, no force improves) — residual is pure ugen pool FIFO phase from
  ONE byte-invisible upstream GET/FREE divergence (prefix byte-identical to
  insn 151, then one-slot rotation cascade).
- **Missing instrument named: per-instruction emit correlation.** The EMIT
  seam tried (f_output_inst_bin) fires once per proc, not per instruction —
  without GET↔instruction-index joins, upstream divergence hunting is
  guess-and-compile. This is the pool-layer twin of the round-3 ask.
- **Proc-ID technique (productize as default)**: grep an unfiltered trace for
  a source-unique immediate (e.g. 0x3fff) instead of trusting symbol-ordinal
  == proc index (off-by-one landmine hit again — 0-indexed).
- patch_assign.py's COLOROFF register decoder is wrong above ~color 20
  (30/31 both decode t5) — trace hint, not ground truth; verify via
  force-and-diff.
- Phantom-pop context-dependence reconfirmed: every guard spelling emitted
  real code here (frame grew) — the modLoadAnim lever needs its
  preconditions documented (value already live in a register, guard folds).
- Real-copy toolchain dirs compose: two instrumented binaries (pool + assign)
  coexist in one USR_LIB dir, gating cleanly on their own env vars.

## intersect B1 force-probe — oracle landed, map corrected

- Single-web force `CDX_FORCE=w371=c16` (proc 6) collapses B1 exactly:
  402→382 words, the removed register-range set matches B1's 15 positions
  precisely, zero side effects. B2/B3/B5 proven causally INDEPENDENT of B1
  (not downstream) — 356 words of genuine structural residual remain.
- Correction: B1 is 20 words, not ~76 (positional-spread illusion again).
- Mechanism: priority-order effect, not conflict — arg0's web (save 833, 93
  intf) colors early and takes s1; arg6's web (save 0.67, deferred via
  decision=split) gets s2 by elimination. Forcing only the high-priority web
  lets the allocator cascade the swap naturally.
- **Operational patterns for the oracle docs**: (1) multi-web CDX_FORCE can
  crash uopt (signal 6) — single-force + natural cascade is the reliable
  method; (2) proc ordinal = count function defs in source order, 0-indexed
  (now confirmed twice; also the unique-literal grep technique); (3) the
  raw10=frame-offset webdetail decode is gated on raw14=0x04ae0102 and is
  NOT universal (this proc: raw14=0x08400202, decode inapplicable);
  (4) colors range past 22 in FP-heavy procs — the color table alone cannot
  identify webs; use split-sweep + single-force confirmation;
  (5) CDX_DETAIL_WEB's intf neighbor logging emitted zero records in this
  proc — path dead/unreachable in this build; rely on p1dec summary fields.

## Web-formation instrument (DKWB_UOPT_WEBFORM_V1) — texLoad fully characterized

- **Formation chain decoded** (uopt.instrumented-v6.c cites in webform report):
  f_newbit → f_formlivbb (THE promotion site, creation unconditional once
  called; predicate lives in 33 call sites ≈ "live at a basic-block
  boundary") → localcolor (no colors) → globalcolor (ALL colors).
  itab @0x1001cc30 decode ring: +0 node, +4 liverange; web set @0x1001cc00.
- **texLoad residual = web-SET difference, not coloring**: candidate forms an
  expression web for CSE'd `id & 0xFFFF` (bit 49, save 2.0, takes v0 first);
  target's set instead contains `tab << 2` (which takes a1). Same
  cardinality, different membership. CDX_FORCE cannot delete a web; split
  spills (frame −136, target doesn't spill). Next instrument specced:
  per-BB live-in/live-out bitvector dump (bb+0x104/0x10c/0x114) — small
  extension of patch_webform.py.
- **CORRECTIONS invalidating earlier notes**: (1) round-4's "dark
  non-globalcolor path" was wrong for texLoad too — v0/v1/a0-a2 come from
  p1color records that never reach p1dec; read p1color, not just p1dec.
  (2) patch_assign.py bugs: COLOROFF `reg=` field bogus (ret IS the register
  number, not >>2 — trust `off=`); proc counter increments at f_reemit so
  every pre-reemit record is attributed to proc N−1; UWRITE uop dump layout
  wrong, unusable. patch_webform.py fixes all three (increments at
  f_oneproc). (3) "USR_LIB no-ops through symlinks" is too strong —
  version/context-specific; both symlinked dirs work in this environment.
- Frame-offset decoder generalized: type=3 nodes w10 is frame-relative,
  sp_offset = w10 + framesize; b22==2 marks formals. Full local→register
  maps now recoverable per proc.
- compare UX: summary line prints only the candidate path with sha1 —
  label both paths (agent read the diff backwards for minutes).

## blockSetupVertices MATCHED — the emit instrument + FIFO replayer

- **The seam**: ugen's forward ibuffer cursor is a GLOBAL (0x10018e70), not a
  function — every f_emit_* increments it itself. Stamping `cursor-1` on pool
  events gives the GET↔instruction-ordinal join (~10 lines). f_emit_* args
  are self-decoding (a0=mnemonic id, a1=dest reg in raw MIPS numbering).
  Productize as DKWB_UGEN_EMIT_V1 (built, fidelity-gated section-scoped on a
  186KB TU).
- **Calibration matters**: emit ordinals ≠ objdump indices (labels/.loc/
  d-side prologue/as1 nops; (s16)(float) conversions emit 4 GETs of which
  as1 folds 3). The folding is exactly what makes upstream divergences
  byte-invisible.
- **The FIFO replayer converted search into prediction**: parse trace →
  virtualize registers → replay hypothetical edits (±GET+FREE at each
  position) → score against target-objdump anchors. Predicted "+2 GETs, at
  the inx-sra and in the inz chain"; first conforming variant was exact.
  Promote as `pool-replay`. Anchor extraction (which emits survive folding)
  is the manual step `view --report-regs`-style output should automate.
- **NEW NAMED PATTERN — redundant mask, free at the assembler, not at the
  allocator**: `(s16 & 0x3fff) << 18` folds to zero instructions but costs
  one pool GET. THE genuinely-free phantom-pop lever (unlike `(x)!=0`
  guards, which emitted real code every time here). Heuristic: one-slot FIFO
  rotation + asymmetric mask/cast decoration on neighbouring statements →
  symmetrize the decoration. One-variant hypothesis, not a search. Also
  aesthetically: the matched source is MORE symmetric — decoration
  asymmetry in a candidate is itself a smell.
- Friction: patch_pool.py helper insertion anchors at LAST include (docs say
  first — layering instruments required splitting helpers); harness compile
  cwd=repo makes relative -o land in the repo tree (harden); ugen.emit.c
  needs -I<research-root>.

## texLoad rounds 5-6 (final) — web formation mastered; residual relocated

- **CDX_LIVE built and fidelity-gated** (tracing on AND off, section-scoped,
  3 TUs): per-BB live-in/out/def/anticipated bitvector dump; `bb+0x154` is
  the single-value "will form a web from this block" witness. Productize
  DKWB_UOPT_WEBFORM_V1 alongside the pool/emit profiles.
- **Copy-propagation defeat lever (proven)**: masking into a formal
  parameter (`id &= 0xFFFF`) blocks folding (params with multiple reaching
  defs are not propagated) — the CSE expression web never forms and the
  value falls to a ugen temp. First variant family in 6 rounds to match the
  target's insns 43-45.
- **Zero-code first-reference lever (proven)**: `if (localvar) {}` dead read
  emits nothing and re-orders itab bit numbering (bit follows FIRST UCODE
  REFERENCE; declaration order inert across 48 permutations).
- **Residual relocated, not solved**: target's `tab→v0` is blocked by
  interference with a higher-priority address web (save 3.0) from the
  piRomLoadSection region downstream — the lever is outside the divergent
  block. Precise handoff in the round-6 report; best structural variant 14w
  with the mask block exact.
- **Friction (priority order)**: (1) `--align` now BLOCKS directed search —
  positional words misranked the best variant 14×; (2) print register
  ranges under every verdict; (3) CDX_FORCE must decline forbidden colors
  with a message, not SIGABRT (six probes unrunnable, including the
  endpoint confirmation); (4) emulated-memory dumpers need fixed offset
  lists + tight pointer windows (blind scans SIGBUS) + descriptor-capped
  bit loops.

## Scratch-parity gap: relocation SYMBOL identity (from the anim_load 99.89% case)

- `compare` reported `instruction-words-identical` + "relocation-kind layout
  identical" while decomp.me still scored 15: three `jal` sites bound
  `piRomLoadSection` where the scratch target binds `read_file_region`. Kinds
  matched; NAMES didn't. Our masking is correct for cross-project
  redistributability, but for scratch parity symbol identity matters. Ask: a
  `reloc-symbol-mismatch` signature (list the differing names per site) so
  "words=0 but the browser disagrees" is answered in one run — plus a docs
  note that decomp.me scores call-symbol identity.
- Session pattern worth documenting: two naming lineages exist for dp64
  scratches (repo names vs modern names, e.g. piRomLoadSection vs
  read_file_region); every paste-ready artifact should state its lineage.

## objprint community-merge analysis — layer attribution finalized (4w base)

- Cross-shape merge analysis is a first-class technique: transplant both
  directions, filter on the oracle mask, and the "complementary" wins either
  compose or are PROVEN the same lever pointed opposite ways (here: `newp`'s
  copy-preference vs temp_t5-parks-in-v0 — mutually exclusive; no source
  merge exists). Saves chasing a phantom combination.
- New best 4w (community body ported to dp64 TU, sha1-faithful across
  contexts). Residual = ugen COPY-PREFERENCE: which live value receives the
  prologue's single expression-temp move. CDX force space exhausted in both
  namespaces on their shape — the decision is below globalcolor and above
  the pool (uninstrumented seam). **The one blocking instrument: log
  "coalescing proposed temp T into V — accepted/rejected + reason" around
  ugen f_copy/f_copy_reg/f_check_vreg/f_assign_vreg (ugen.c:50794/79683/
  101445/102247).** This was the original morning feature ask; now it gates
  exactly one function's last 4 words.
- Harness hygiene (for campaign-hygiene.md): exec()-style harness loading
  dumped globals and fabricated a plausible all-fail table (nd=30902) that
  was nearly reported — harnesses must be real modules with explicit APIs.
  Return-type mutations must patch declaration AND definition (silent
  COMPILE_FAIL cells misreported round-1's void results).
- decomp.me scratch parity confirmed end-to-end today: anim_load hit 100%
  in-browser after the call-symbol fix — the local IDO + workbench compare
  pipeline predicts browser scores exactly (words + reloc symbol identity).

## objprint terminal answer + first `view` field use

- Agent correctly REFUSED to build a mis-aimed instrument: the pool trace
  showed the residual `move`'s source and dest are both uopt-assigned (34
  f_ureg hits; pool yields only t6-t9), so ugen's copy machinery never
  decides — the copy uop is already in the ucode. ~830 forces negative;
  culprit = web 12 (a load-temp that doesn't exist in the target's ucode).
  Final attribution: uopt copy-propagation/web-formation, pre-localcolor.
  Next hook: "load into dest web D — coalesce or materialize temp+copy?"
  objprint rests at 4 words (BEST4c). Evidence-based instrument refusal is
  itself a pattern for the skill.
- **First real-world `view` use** (block_setup_vertices scratch port):
  one screen showed lanes identical 53/53+40/40, prefix-exact@20, six
  classified hunks — immediately separated reloc-display artifacts from the
  two real deltas (schedule + branch-likely). The bet is paying off on day
  one. Noted: jal-to-address-0 renders as whatever symbol sits at 0
  (display artifact worth normalizing), and mixed-verdict playbook ordering
  (constants first) read correctly.
- New port-hazard class: SAME source + SAME flags under a different TU
  context (scratch ctx vs dp64 headers) shifts schedule/branch-likely
  selection (ctx type diffs: EncodedTri d0/d1 u32 vs s32, etc.). Scratch
  ports of matched functions need their own verification pass — "matched in
  dp64" does not transfer automatically.

## block_setup_vertices scratch port — flag-parity root cause

- ~78 "structural" word diffs on a ROM-verified source were caused by ONE
  missing assembler flag: `-Wab,-r4300_mul` (R4300 multiply-hazard + branch-
  likely scheduling in as1). The -g0 diagnostic correctly REFUSED to blame
  .loc barriers, and a real-header isolate cleared the ctx-type hypothesis —
  systematic elimination landed on flag parity. Skill addition: **verify flag
  parity against the project's build.ninja BEFORE any source search on a
  scratch port** — decomp.me preset flags can diverge from the project's
  real flags (dp64 preset 28 lacks -Wab,-r4300_mul; likely affects EVERY
  dp64 scratch with multiplies or FP branches).
- `compare` handled free-text extra flags fine; the gap is human workflow:
  scratch presets are curated, and a preset-vs-project flag diff is
  invisible until someone diffs build.ninja. Workbench ask: `bundle-scratch`
  should emit the project's full CC flag line into scratch.json/README so
  paste-time flag parity is a copy-paste, not an investigation.

## DKWB_UOPT_COPY_V1 — coalesce-vs-copy solved; objprint one reachability from done

- **COPYDEC is the missing profile, now built + fidelity-gated (21/21 on 3
  TUs)**: one line per assignment uop — `lhs rhs rhsformed bbwit colors →
  COALESCE|TEMPCOPY`. Self-validated on first run (labelled web 12 and the
  unk70 load correctly). Promote to a first-class workbench profile.
- **Decision rule (document in ido-late-stage-patterns.md)**: temp+copy iff
  the RHS expression owns a liverange (f_formlivbb, called only from
  f_makelivranges here); a formed web emits its move only if the temp has a
  second emitted use; redundant reads BEFORE the assignment form the web,
  AFTER it in the same BB they fold away (position asymmetry).
- **objprint final state**: BEST4c and BEST5 are two different levers through
  v0 (model-CSE web parks in v0 → count web right, copy wrong; newp copy
  right → v0 free → count web wrong). Oracle: BEST5 + w55=c2 = byte-exact.
  Handoff constraint set for the last construct: (a) live across inner loop,
  (b) colors before web 55, (c) zero code, (d) NOT the RHS of a local
  assignment (else it spends the one copy). All known zero-code blockers
  violate (d); candidate expression CSEs (temp_t5->faces etc.) were inert in
  24 placements. Now purely a p2 first-free reachability question.
- Friction repeats: CDX_FORCE SIGABRT on forbidden colors (3rd campaign);
  positional words misranking (--align blocking on a 2nd function);
  --report-regs rebuilt per-campaign. NEW: fidelity gates must assert inputs
  exist (zsh non-splitting produced 7 empty-string-sha1 "OK"s); recompiled
  uopt links need version_info.o (recipe in build_uopt.sh).

## texLoadTextureActual MATCHED (round 7) + objprint constraint-(d) found

- **texLoad matched**: parameter-in-place mask + ONE dead read
  `if ((tab*4) + tabEntry + tabEntry) {}`. Three new levers for the
  patterns doc: (1) zero-code dead reads generalize to arbitrary RVALUE
  EXPRESSIONS (`if (gFile_TEX_TAB[tab]) {}` — the only thing that beat the
  lui hoist); (2) `tab * 4` forms a web where `tab << 2` does NOT —
  mul/shift are not interchangeable formation triggers despite identical
  emitted code; (3) READ-COUNT IS A PRIORITY DIAL — stacking reads of the
  losing web until it outranks the winner is monotone (1 read = 5w, 2
  reads = 0w). Map corrections: uopt colors 22 registers (t6-t9 are the
  only ugen scratch); the "save-3.0 blocker web" was a shape-dependent
  hoist artifact, not a fixed obstacle.
- **objprint constraint-(d) construct**: split a local's own update chain
  with a dead read (`x += a; if (!x); x++;`) — zero code, zero frame, forms
  a short web from the intermediate that takes v0 without touching any
  coalesce decision. Count web colors v1 with NO force (first in ~2800
  variants). Counter-note: "empty-if reads take v1 never v0" applies to
  whole locals/globals only — intermediate-value reads DO take v0.
  Remaining 11w = ONE schedule hunk (the dead read is a ucode branch
  pinning the chain above the guard) — the residual left the allocator.
  p2 exception discovered: web 2 (arg0) took c3 with c2 free — an
  incoming-register preference path exists; docs' "pure first-free" is
  wrong. Decode ring confirmed: forbidden0 bit = 1<<(31-c), regsleft =
  22 - popcount(f0).
- Repeated top ask (4th campaign): --align ranking. Positional words ranked
  a 1-hunk 11w variant below a 5-scattered-sites 5w variant and nearly
  steered the search wrong. Filter predicates must key on which web holds
  the contested color, not opcode (filt.py's op==0x04 test missed an
  op==0x18 equivalent).

## Community feedback (Discord, real users on released 0.2.0)

- mkst (SSSV, 30+ near-matches): "I am too dumb. How do I use the
  workbench?" — ran compare correctly, got words=13, no idea what next
  (0.2.0 has no verdict/guidance lines — the unreleased work is the fix;
  RELEASE MATTERS). Asked: isolate functions vs asm-processor? (answer for
  docs: no — compare is symbol-scoped; his own paste shows isolation
  CHANGING codegen, insns 96 vs 93, the perfect teachable example). Asked:
  "am I expected to use codex as the permuter?" — the manual path must be
  documented as first-class.
- inspect: wants "access and understanding to the trace stuff over the
  permuter... I like to understand how to match more things" — the
  mechanism playbook needs a human-facing field guide, not just skill files.
- queueRAM pointed at workflows.md; mkst still lost ("I feel like I need to
  be an AI to understand it") — validates the vision doc's onboarding bet;
  human-first docs pass dispatched (START_HERE, field-guide, batch-triage
  walkthrough).

## Pending (from subagent campaign runs — append when reports land)
