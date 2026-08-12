# Field notes — Dinosaur Planet core campaign (2026-07-29)

> **Historical field record.** Measurements and failures are preserved as
> observed on the date above. Use [Product status](product-status.md) and the
> current command guides for supported syntax and capabilities.

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
  toolchain already exists on this machine** in the research tree's
  `build/5.3/` directory (`uopt.instrumented-v6`
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

## vsprintf campaign (866 variants; plateau initially misread as source proof)

- **Positional counting hid a near-match**: comparator said 635 words; opcode-
  aligned truth is 27 structural + 8 register (3 "relocation_controlled" were
  false positives — named symbol+0 vs section+addend at the same final
  offset; the comparator has the symbol tables and should prove equivalence).
  The `--align` structural/schedule/register split is now the #1 comparator
  ask (matches the UX vision's `view` bet).
- **NEW top-value mechanism: `-g3` is a scheduling constraint.** IDO emits
  `.loc` per statement; as1 restricts cross-block motion at those barriers.
  Diagnostic: recompile the candidate `-g0`; if the divergent region
  collapses to ~exact (vsprintf %e/%f: 25→2), debug metadata participates
  and as1 can reach the target schedule. It does not prove source correctness:
  the eventual match still required a different length/padding topology.
  One command can retire many blind scheduling variants, but source topology
  and line tags remain part of the evidence ladder.
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

## objprint_func_80036890 MATCHED (final assault) — p2 is index-ordered, and
## the dual-role local is a COLORING lever

- **words=0, insns=186, frame=-112; whole objprint TU .text byte-identical
  (2220 insns, 14/14 functions) under stock IDO 5.3 + project flags.**
- **The `-g0` diagnostic REFUSED the .loc hypothesis and was right.** The
  10-instruction hunk was byte-identical at `-g0` and `-g3` while the rest of
  the function fell apart at `-g0`. Recording the negative result matters:
  the diagnostic is genuinely two-sided, not just a "stop searching" signal.
- **CORRECTION to the p2 docs (important): p2 colors webs in ASCENDING WEB
  INDEX order, not save order.** The CDX log for objprint proc 8 emits
  p2dec/p2color for webs 0, 2, 21, 23, 26, 31, 55, 189… strictly ascending;
  saves along that sequence are 2.0, 4.0, −3.0, 3.0, −2.7, 7.0, 105.5, 400.
  Every earlier writeup that reasoned "the 105.5 web outranks the 15.0 web"
  was reasoning about the wrong ordering. Consequence for search: a dead-read
  web only helps if its FIRST UCODE REFERENCE precedes the victim web's, and
  "make the web profitable so it outranks" is not the mechanism — "make the
  web exist earlier" is. Also confirmed: `regsleft = 22 − popcount(f0)`, and
  bestcolor is first-free EXCEPT for the incoming-register preference (web 2
  = arg0 takes c3 with c2 free).
- **The winning lever: dual-role local as a WEB-MERGE tool.** The residual was
  "p2 web 55 (the `textureAnimationCount` reload) must have c1 forbidden".
  No new zero-code web could be created that both spans the inner-loop guard
  and leaves the schedule alone (proved over ~2500 filtered variants: every
  guard-spanning construct hoists part of the `sp34 + (sp6C<<1) + 1` chain
  above the `blez`, which the target keeps below it). The fix was not to add
  a web but to MERGE the victim into an existing one: reuse a single local
  for `arg0->def` (p2 web 23, already c1-forbidden via interference with
  `newp`/web 0, already colored c2=v1) and for the loop bound. The merged web
  inherits web 23's index AND its forbidden mask, so it takes c2 = v1.
  Both ingredients are individually inert (5w each); only the pair matches.
  Source shape:
    `var_dual = (s32)arg0->def; sp34 = ((ObjDef*)var_dual)->pTextures; …`
    `for (j = 0; j < (var_dual = t5->textureAnimationCount); j++)`
  s32+casts, `ObjDef*`+cast, and a `union {ObjDef* d; s32 n;}` spelling all
  produce the identical object. **Generalize this into
  ido-late-stage-patterns.md**: the dual-role local (previously listed as a
  register-pressure idiom) is also the only known way to transplant a
  forbidden-color mask onto a web you cannot otherwise constrain. Recipe:
  find a p2 web that already has the color you want, verify it dies before
  the victim's liverange, and merge them through one variable.
- **Negative results worth keeping**: whole-local `if (!(x));` dead reads after
  an assignment are dropped entirely (no web, zero effect); only rvalue
  EXPRESSIONS that CSE with a real computation form webs. Dead reads placed
  anywhere inside the inner loop cost 20–100 words (branch breaks the
  loop-body schedule). Prologue statement permutation is inert on its own for
  9 of the legal orders here — but combined with an early count read it moves
  the death points and reshuffles the whole p2 assignment (a usable but
  low-precision dial).
- **Repeat asks confirmed, in priority order**: (1) `--align` — positional
  words ranked a 12-word 4-hunk variant and a 12-word 20-hunk variant
  identically and misranked the 5-word register-only variant that turned out
  to be the correct base; an LCS-aligned word count found it immediately.
  Fifth campaign to need this. (2) `compare --report-regs` rebuilt again.
  (3) CDX should print the p2 processing ORDER explicitly (or at least a
  `rank=` field) — the index-order discovery above took a log re-read that a
  one-word field would have made free. (4) `census`-style prefilters
  (insns + which register holds web X) are what make 2500-variant sweeps
  practical at ~0.06 s each; a `compare --census KEY=VALUE` predicate would
  remove the per-campaign objdump+regex layer.

## DLL wave 2 additions (PIC catalog)

- **Unused-static dead-code elimination trap**: marking a helper `static`
  while its only caller is still a GLOBAL_ASM block guts the body to
  `jr ra; nop` (symbol kept, size≈0) and shifts every later function's
  address — cascading false structure-mismatches. Detect via readelf -sW
  size=0. Rule: flip to static only when the real C caller lands in the
  same pass (pairs with wave-1's bottom-up rule).
- Reconfirmed reloc-noise class: candidate `R_MIPS_GOT16 .data+off` vs
  target's named-symbol reloc = same runtime address; workbench buckets it
  correctly as relocation-controlled, but it still costs hunt time — the
  reloc-symbol-mismatch signature ask covers this case too.
- Manual-unroll-by-4 tell (dll_14 bss_0 family): first 3 unrolled checks
  use branch-likely, the 4th uses plain branch + nop (nothing to prefetch)
  — a strong "unrolled in source, not by compiler" signature.

## DLL 413 probe (parallel worker) + verification safety note

- **Safety rule (make it doctrine): ninja success is NOT match evidence.**
  A clean-compiling non-exact function still links; only the ROM checksum
  line (`build/dino.z64: OK` from md5sum -c) proves exactness. Our
  verify-commit discipline already gates on that exact line — keep it
  mandatory in every brief.
- DLL 413 (IMspacecraft): dll_413_setup has a PROVEN fix (callee
  dll_413_func_1AC as static real C → setup words=0) but the pair is
  COUPLED — static flips the caller's PIC codegen, so both must land
  together, and func_1AC is unsolved (one extra dead `move a0,zero` before
  its message loop; 7-case switch regalloc cascade). Handoff for a future
  round; the coupled-revert requirement is itself a reusable caution.

## Wave-2 final — config-contamination catch + corrected bottom-up rule

- **DOCTRINE: regenerate build.ninja before trusting any verdict.** A
  `configure.py --all-code` run leaves `-DNON_MATCHING` in build.ninja;
  every `#ifndef NON_MATCHING` gate then compiles the DRAFT branch, and
  stale objects keep the ROM checksum green until the next recompile.
  Negative results measured under a contaminated config are void (DLL
  210/437/413 diagnoses need clean re-runs). Add a config fingerprint line
  (grep -c NON_MATCHING build.ninja == 0) to every campaign brief.
- **Bottom-up rule CORRECTED**: never mark a callee static while its caller
  is still GLOBAL_ASM (IDO deletes the unreferenced-static body to jr ra;
  asm_processor splices post-compilation so the pragma is not a reference).
  Correct order: match the callee NON-static first, then flip to static in
  the same edit that makes the caller real C.
- New levers: statement order of independent stores drives t-register
  assignment (pre-scheduling order); $v0-reservation is the objdata-register
  tell in void vs value-returning accessors; free a-registers are ordinary
  colors ahead of t0; IDO won't CSE self->field across a store through a
  pointer param (aliasing) — a local is not optional there.
- dino.py extract-dll/configure must run under .venv python (the python3
  shebang dies on spimdisasm AFTER deleting the asm dir).

## vsprintf endgame science (kill + flags rounds)

- **Two false premises retired with evidence**: (1) no original DWARF
  exists anywhere (target vsprintf is a ROM-extracted GLOBAL_ASM blob; the
  .mdebug in build objects is OUR compile) — the "line-table archaeology"
  idea is dead for this project; (2) `cc -S` emits `.loc` per statement
  REGARDLESS of -g — every .loc-count measurement in earlier campaigns was
  a rendering artifact. Real -g difference in the body: 12 .bgnb/.endb
  scope pairs only.
- **cfe's -Xg is a binary switch** (g1≡g2≡g3; only g0 differs) — the whole
  statement/layout family measures identically by construction. Also:
  uopt WARNS and silently disables -O2 under -g1/-g2 ("use -g3").
- **Invocation space exonerated** (26 probes): O3/O1/g-levels, 7.1-cfe
  cross (byte-identical no-op!), full-7.1, and uopt's ENTIRE internal flag
  table (-docodehoist/-moremotion/-loopunroll N/-no_const_in_reg/-doassoc/
  -docopy/-createbb/-norlodrstropt/-do_opt_saved_regs/-noheurAB) — nothing
  approaches the target's float-region scheduling. `-loopunroll` REQUIRES
  a numeric arg or it eats the output filename (trap).
- **TOOL GEM: IDO binaries' rodata is 4-byte-word-swapped in the
  static-recomp builds** — plain `strings` shows garbage ("tpoup.mc");
  byte-swap every 4-byte word first and the full internal flag tables
  become greppable. Ship as `decomp-workbench ido-strings`. This recovered
  the entire uopt option table.
- Live hypothesis under test: the original used the two-step cc -S → as
  path (replay-as1 zeroed both float cases; prologue breakage attributed
  to as0-reconstruction infidelity, not the path).

## vsprintf closure (codex matched it) + final IDO facts

- vsprintf fell to a community/codex shape: single-expression length
  precompute (`a0 = (dash||sign||space) + prec + (prec>0||alt) +
  (exp>=100) + 5`) with LIVE width comparisons (`while (width-- > a0)`)
  instead of pre-subtracted PAD — the "early materialization" was the
  length calc's operands, not scheduling metadata. LESSON for the
  evidence-ladder: the -g0 diagnostic proves scheduling CAN reach the
  target from your shape, not that your shape is the original — a freer
  scheduler can rescue a wrong shape. Treat -g0 collapse as "necessary,
  not sufficient."
- An opt-in as1 selection trace reduced the final two-word residual to one
  ready-set tie: the wrong build chose encoded `li 45` at cycle 4 with
  source line `0x30f`, then `li 10` at cycle 5 with line `0x311`.
  Controlled line-identity variants confirmed the lower-line selection
  behavior. Instrumentation lesson: the temporary 20-word node dump was
  enough for one investigation but is not a product—any shipped profile
  needs named fields, scope controls, a pinned generated-source hash, and
  disabled-trace fidelity gates.
- **IDO 5.3 inlining facts (three-way verified)**: NO inlining at -O2
  (umerge never runs; #pragma inline is silently accepted and fully inert
  — cfe accepts arbitrary unknown pragmas without warning); at -O3 umerge
  inlines heuristically, pragma-independent; with no inlinable callee,
  -O3 output is BYTE-IDENTICAL to -O2 — so "was this built -O3?" is
  answerable per-callee. Inlined code is MORE -g3-sensitive, not less
  (129 vs 5 g0/g3-differing lines in A/B).
- `cc -S -O3` silently stops after cfe and drops a .u file in cwd.
- ido-strings (word-swap) remains unshipped but re-proved its worth: made
  the pipeline/pass-table archaeology a 30-minute kill.

## Pending (from subagent campaign runs — append when reports land)

## texDPTextures kill-mission (148 -> 74w; temp cascade solved, 2 structural sites left)

- **Result**: `cand_best` 148w/align=120 -> **74w/align=45 (struct 8 + reg 37)** in a
  two-line source diff, ~330 filtered variants. The ~110-word ugen temp cascade
  named in the prior handoff is **gone**; what remains is 4 clean pool-coloring
  clusters plus the original 8-word structural pair.
- **The winning pair is non-additive (both ingredients are losses alone)**:
  (1) `if (tex0->flags & RENDER_TEX_BLEND) {}` at the top of the `else` of
  `if (tex1 != NULL)` — a zero-code dead read that CSEs with the real
  `tex0->flags & BLEND` test 4 instructions later; alone 148->95.
  (2) `temp_a2 = temp_v1->valB | (renderFlags & temp_v1->valA)` instead of
  `(renderFlags & valA) | valB`; **alone this is 148->152 (worse)**, together
  95->74. Third confirmed instance of "two individually-inert/negative
  ingredients, only the pair matches" (after objprint's dual-role merge).
  Note this also **contradicts the field guide's dead-family entry** for
  commutative order: `a | b` vs `b | a` did NOT canonicalize here (`or a2,t8,t9`
  vs `or a2,t9,t8`), it flipped emitted operand order without compound
  assignment. The guide's claim needs an "operands of unequal depth" caveat —
  `X | (Y & Z)` is not the symmetric case that canonicalizes.
- **`--align` earned its keep again (6th campaign)**: positional words ranked
  `D_deadmask_elsetop` and `F_texfl_1` identically at 95w; LCS opcode-alignment
  separated them (struct 10 vs 8) and picked the one that actually composed with
  the `or` swap. An ad-hoc `align.py` (shape-normalised LCS -> struct/reg/hunks
  split) was rebuilt for the 6th time; it is ~40 lines and belongs in `compare`.
- **NEW NEGATIVE, important and general: IDO 5.3 copy-propagates EVERY plain
  local copy `X = <var>;`, unconditionally.** Falsified across ~90 variants:
  fresh locals, reused live locals, **formal parameters as the destination**
  (`force = renderFlags`), destinations with many other defs (`hasTex`),
  statement-separated copies, copies with real statements between copy and use.
  All produced byte-identical objects to the base. The field guide's lever-13
  rule ("params with multiple reaching defs are not propagated") is about the
  *source* of a read, not the destination of a copy — the two are not
  symmetric, and the dual-role/web-merge recipe from objprint therefore does
  **not** transfer to a value that arrives via a copy.
- **The one construct that DID defeat it (new lever)**: redefine the *source*
  after the copy. `var = renderFlags; renderFlags |= 0;` collapsed the
  double reload into a single register feeding both `andi`s (148->105 on the
  old base, exactly the target's shape) — but `|= 0` on a memory-resident
  formal materialises lw+sw and costs more than it wins on the good base.
  `renderFlags |= 0` **alone** is fully inert (303 insns, 148w) — it only
  materialises when it has a copy to kill. Wanted: a zero-code redefinition.
- **Exact remaining blocker (struct 8, unchanged since the prior campaign)**:
  target `lw a1,140(sp)` @105 in the dominator block (one renderFlags reload
  whose web spans both the `&0x40` and `&0x2000` tests) + `move a1,t3` @144
  (frameOptions copied into that same register before the `>>8`); candidate
  emits two loads @133/134 and hoists `sra t?,t3,0x8` to @145. Census
  (DKWB_UOPT_COPY_V1, proc 11) shows renderFlags = itab bit 63, `color=-1`,
  `intf=26`, split by globalcolor into three post-spill liveranges (bits
  299/300/301) all uncolored, `forb=7f800000` (c1-c8 forbidden). The target
  colors one of those fragments c4=a1. **CDX_FORCE cannot create the web**;
  this is a web-SET difference, same class as texLoad round 5.
- **Cluster attribution of the remaining 37 register words** (all pool, no temp
  cascade): (a) hasTex/var_a0 a0<->a1 swap, 14 sites — target keeps `hasTex`
  in a1 for its whole life (frame index @17 AND boolean @175/182/196) while the
  candidate splits it into two liveranges (a1 early, a0 late) and `var_a0` then
  takes a1 by elimination; (b) renderMipmaps a2 vs v1 + temp_v0_2 v0 vs v1 +
  tex0->flags v1 vs a1, ~18 sites, one chain displaced by the dead read's own
  web taking a1; (c) `addu v1,a3,t4` vs `addu v1,t4,a3`, 1 site; (d) two stray
  temps. Cluster (a) is almost certainly downstream of the missing a1 web —
  the same register is contested.
- **Proven-inert on this function (do not re-spend)**: declaration permutation
  (25 positions), statement order in the `tex0!=NULL` tail (all 24 perms),
  `hasTex` test spelling, `var_a0` expression form, `hasPalette` expression
  form, `dlSetEnvColorNoSync` argument spelling (5 forms), dead reads of
  `var_a0`/`hasTex` (all emit a branch, +1 insn), reads of renderFlags placed
  on the `tex1 != NULL` path to force PRE (dropped entirely), `&&` operand
  order, and parameter signedness (blocked by the header prototype).

## texDPTextures round 2 — 74 -> 43w; three new levers, sibling-transplant validated

- **43 words, insns 303, frame -128, align=36 (struct 4 + reg 32)**, down from
  148/align=120 at handoff. Instructions 106-172 (the whole divergent block that
  the prior campaign called a ~110-word cascade) are now **byte-identical**.
- **The sibling-source transplant is a first-class technique.** Reading the
  already-MATCHED `texDPTextureSimple` in the same TU produced the fix for the
  `move a1,t3` structural site in one variant: its argument spelling
  `dlSetEnvColorNoSync(&dl, (frameOptions & 0xFFFF) >> 8, ... x3)` instead of
  `frameOptions >>= 8;` + three bare args. **The `& 0xFFFF` is load-bearing and
  emits nothing** — `frameOptions >> 8` inline three times leaves struct=9,
  `(frameOptions & 0xFFFF) >> 8` gives struct=5 and materialises the copy.
  This is the redundant-mask lever (lever 16) acting on *web formation*, not
  just FIFO phase: the mask makes the shift's operand own a liverange, so the
  parameter's web must be copied into it rather than shifted in place.
  Recommendation for the skill: **before opening a campaign, diff the target
  against any matched sibling in the same file, statement by statement** — the
  three levers that moved this function (env-arg mask, `(renderFlags & valA) |
  valB` order, inline `var_a3_2[idx]` vs a pointer temp) were all readable
  directly off the sibling.
- **Copy-prop defeat, now cheap and general (this is the round's main lever)**:
  `var_dual = renderFlags; renderFlags |= 0;` — a redefinition of the *source*
  immediately after the copy. `renderFlags |= 0` alone is inert (byte-identical);
  it only materialises when it has a copy to kill, and then it costs one store
  that the target spends on a reload, so instruction count is unchanged (303).
  This collapsed the double `lw ?,140(sp)` into one register feeding both
  `andi`s — the exact target shape. `^= 0`, `+= 0`, `= x` and `&= ~0` are NOT
  equivalent: `+= 0` and `= x` are dropped before they can kill the copy,
  `|= 0` and `&= ~0` behave identically. Worth a patterns-doc entry with the
  full negative list.
- **Web-index steering by dead read, confirmed and quantified**: with the copy
  at the top of the block, `var_dual`'s web is first-referenced *before*
  `gCurrTex0`'s address web, so it takes c3=a0 and the address takes c4=a1 —
  the reverse of the target. Adding `if (gCurrTex0) {}` immediately **before**
  the copy moves the address web's first reference earlier, flipping the pair
  (renderFlags -> a1 as required): 50w -> 43w. Order within the slot is
  decisive — the same dead read placed *after* the copy is 158w, and at any
  earlier slot (function top, inside the `tex0 != NULL` branch) it is 254-299w.
  "First ucode reference order" is now directly steerable and this is the
  cleanest demonstration so far; it should be a worked example in
  ido-late-stage-patterns.md.
- **Counter-example to "unused-declaration drops are inert" (3rd sighting)**:
  after switching to inline `var_a3_2[var_a0]`, deleting the now-unreferenced
  `struct PointersInts* temp_v1;` declaration moved the function from 43w to
  67w (struct 4 -> 56). The declaration must be kept. This contradicts the
  round-3 note "unused-declaration drops are fully inert (dropped before uopt)"
  — that claim needs retracting or scoping.
- **Refuted this round**: the hasTex/var_a0 merge (F3). Making the surviving
  copy land in `hasTex` rather than a fresh local — i.e. one local carrying the
  frame index, the renderFlags reload, the frameOptions value and the boolean —
  is consistently 6 words *worse* (49 vs 43) and does not merge the two
  liveranges. Also refuted: splitting `var_v0`'s three roles the way the
  matched sibling does (separate `i`, `geomMode`, `s16` mask) — +150 words, so
  the sibling's local *count* does not transplant even though its expression
  spellings do. F1's expression-RHS copies (`| 0`, `+ 0`, `* 1`, `& ~0`,
  `(s32)`, `~~`) all fold to pure copies and are byte-identical to the base —
  **the fold boundary is: any expression whose value equals the operand is
  folded to a copy before copy-propagation runs**, so there is no F1 analogue
  of texLoad's mul-vs-shift asymmetry on the RHS of an assignment.
- **Terminal state / exact blocker**: struct 4 = the `renderFlags |= 0` store is
  emitted twice (once before `bne`, once in its delay slot) where the target
  emits one store plus one `lw a1,140(sp)` reload; instruction counts balance,
  so this is a store-duplication/schedule artifact of keeping the value live
  rather than reloading it. reg 32 = three clusters: (a) hasTex/var_a0 a0<->a1,
  14 sites — target keeps `hasTex` in ONE web from insn 17 to 196, candidate
  splits it (all merge attempts refuted above); (b) renderMipmaps a2->t0 and
  hasPalette t0->t1, 9 sites, blocked because the `if (gCurrTex0) {}` dead read
  consumes a2 with its own value web (the target's equivalent value lives in a
  ugen temp t6 — the dead read cannot avoid creating a pool web because the
  empty-if is a BB boundary); (c) one commutative `addu v1,a3,t4` and two
  strays. Cluster (b) is the tractable one: **the ask is a zero-code way to
  advance a global's ADDRESS web index without also forming a value web.**

## texDPTextures round 3 (campaign close) — the address-of dead read EXISTS and is free

- **New confirmed lever, and the answer to round 2's named ask:
  `if ((s32) &gGlobal) {}` is a zero-code dead read that forms the ADDRESS web
  without forming a VALUE web.** Verified in the object: with
  `if (gCurrTex0) {}` the global's value lands in a pool register
  (`lw a0,0(a2)`); with `if ((s32) &gCurrTex0) {}` it falls to a ugen temp
  (`lw t4,0(a1)`) exactly as the target does (`lw t6,0(a0)`), and instruction
  count is unchanged (303). This is the first construct found that separates
  the two webs a global reference normally creates. Add to the field guide
  next to levers 7/8: **the empty-if forms a web for whatever rvalue you name;
  naming the address instead of the value gets you the lui/addiu web alone.**
  Spellings `&g`, `(s32)&g`, `(u32)&g`, `&g != (T*)0`, `(s32)&g * 4`,
  `(s32)&g * 1`, `(s32)&g + var`, `(s32)&g | var` are all equivalent here — the
  arithmetic decorations neither help nor hurt, so the mul-vs-shift formation
  asymmetry does NOT extend to address expressions.
- **It does not fix this function, for a precise and reusable reason.** The
  address-only read costs +119 words (43 -> 162) on its own, and once the
  *value* read `if (gCurrTex0) {}` is present the address-of read is fully
  inert (byte-identical, 43w) in every position tried — the value read has
  already formed the address web, so the address-of read CSEs into it and
  creates nothing. **The index advance that cluster (b) needs is only produced
  by reading the value, and reading the value is exactly what consumes a2.**
  That is a genuine tension, not a search failure: on this shape the address
  web's first-reference cannot be advanced independently of the value web's.
- **Campaign closed at 43 words** (insns 303, frame -128, obj sha1 bf616e2d62ad,
  src sha1 7f058760f1303a058a4fc5844752c978c300d881), from 148 at handoff;
  911 ledger rows across 3 rounds. Instructions 106-172 byte-identical.
  Residual: struct 4 (the `renderFlags |= 0` store emitted twice vs the
  target's one store + one reload) and reg 32 in three clusters — (a)
  hasTex/var_a0 a0<->a1, 14 sites, needs hasTex to be ONE web from insn 17 to
  196 and every merge spelling was refuted; (b) renderMipmaps a2->t0 /
  hasPalette t0->t1, 9 sites, blocked by the tension above; (c) one commutative
  `addu` plus two strays. Next lever would have to come from below the source
  layer (a CDX force probe on the a0/a1 pair) rather than from more variants.

## blockComputeVertexColors — DKWB_UOPT_PRE_V1 and a NEW LAYER below coloring

**New instrument: `DKWB_UOPT_PRE_V1` (`patch_prehoist.py`, env `CDX_HOIST=1`),**
extends `DKWB_UOPT_COPY_V1`; all three profiles compose in one run
(`CDX_WEBS=1 DKWB_UOPT_COPY=1 CDX_HOIST=1`). Section-scoped byte fidelity
verified on 3 TUs (map, objprint, texture), tracing ON and OFF, 0 DIFF.

- **The unlock: uopt ships its own PRE dumpers.** `f_printprecm` /
  `f_printcm` / `f_printscm` survive with symbol names. Decoding their
  `write_string("<name> --")` -> `printbv(bb + off)` pairs out of the rodata
  blob gives the authoritative per-block field map, no guessing:
  `0xfc hoistedexp, 0x104 antlocs, 0x10c alters, 0x114 avlocs, 0x11c absalters,
  0x124 delete, 0x12c ppin, 0x134 iv, 0x13c cand, 0x144 subdelete,
  0x14c subinsert, 0x154 antin, 0x15c antout, 0x164 insert, 0x16c ppout`.
  The same words are reused: in the avail prepass `0x124 pavlocs, 0x144 avin,
  0x14c avout, 0x164 pavin, 0x16c pavout`; after `f_getexpsources`
  `0x134 sink, 0x154 source, 0x15c region`. **Corrects WEBFORM/COPY_V1:**
  `bb+0x154` is `antin`/`source`, not a bespoke "web witness".
  Also decoded: `bb+8` number, `bb+10` loopdepth, `bb+28` first statement,
  stmt `node+8` next, `node+16` owning block, `node+2` itab bit.
- **Liverange priority fields (from `f_printregs`): `lr+0x1c = nocs`,
  `lr+0x24 = numintf`, `lr+0x28/0x2c = forbidden`, `lr+0x30 = save`
  (an IEEE float = totalsave/nocs), `lr+4 = web id`, `lr+32 = color`.**
  This makes the initializer-sinking / read-count levers directly observable:
  dump `save` per web and watch the scan order move.
- **Two mandatory robustness fixes for any future uopt walker.** (1) The
  recompiled 512MB region is `mmap` PROT_NONE, paged in by `wrapper_sbrk`, so
  a speculative deref SIGBUSes -- `dkwb_ph_ok()` is a memoised per-4K-page
  `sigsetjmp` probe, armed only while tracing. (2) `f_bvectin` has no capacity
  check; nodes handed to `f_resetsubdelete` carry `sym` far past `nbits`.
  Bound-check against `n*128` first. Both were required; without them the
  instrument crashed on 2 of 3 gate TUs.

**Hypothesis refuted, and a new layer found.** The 4-vs-1 `sll` difference on
bCVC is NOT a uopt PRE decision. Across the hoisting and non-hoisting variants
`f_codemotion` makes byte-identical placement decisions (exactly one `insert`
in the whole proc, for an unrelated loop-invariant address; the scale's
`PLACE` sets are empty in both), and `f_getexpsources` only computes
source/sink/region. `f_codemotion`, `f_getexpsources`, `f_dompropagate` are
exonerated for this class of diff.

- **NEW LAYER: the ugen delay-slot filler, below coloring and above emission.**
  ugen fills a branch delay slot with the *first instruction of the target
  block* and advances the branch label past it. It may only do so with a
  **non-likely** branch -- which executes the slot on both paths -- when the
  slot instruction's **destination register is not live at the branch**.
  Otherwise it must emit `beql` (likely), and then every other predecessor
  needs its own copy plus the physical block-head copy survives.
- **The delay-slot collision rule (new, reusable).** On a compare-chain
  `switch`, if the scaled-index web and the switch-selector web get the SAME
  register, ugen is forced to `beql` and the arm's first instruction is
  emitted **3 times** (two delay slots + one dead block-head copy) instead of
  once. Cost: +2 instructions per switch region. Target: selector `v0`, scale
  `v1` -> `beq`, 2 per region. Every candidate: both `v0` -> `beql`, 4 per
  region. **Invariant to aim for is "different registers", not any particular
  register.**
- **The empty-if dead read is a binary CSE dial, not a graded one.** Any
  expression containing an exact `idx * 4` subterm placed in the switch's
  dominator makes cfe emit the scale once there and both arms consume it
  (0 per region); everything else leaves it per-arm. Confirmed hoisting:
  `idx*4`, `idx*4+1`, `(idx*4)&1`, `otherArray[idx]`. Confirmed NOT hoisting:
  `idx*8`, `idx*2`, `idx*3`, `idx<<2`, `idx+1`, `idx`, `-idx`,
  `&array[idx]`. No intermediate setting exists.
- **Inert on this shape (all byte-identical to base):** dead reads inside any
  case arm; `*(base+idx)` vs `base[idx]` in either or both arms; `(s32)` casts
  on the index; statement reordering inside arms; extra parens; `3 & x`;
  `switch (sel = ...)`. **The "per-arm syntactic variation defeats the CSE"
  family is refuted** -- cfe's ucode is identical for all of them.
- **A hard tension, same shape as texDPTextures round 3.** Two dominoes are
  needed and they are anti-correlated. `if (var_a0_2) {}` in the `case 0` arm
  moves `var_a0_2` into `a0` (target's register) at **zero instruction cost**
  and improves both metrics (678->676 words, 747->757 aligned). But every
  lever that separates the selector from the scale (any dead read of
  `(s16)flag & 3`, or dropping the `s16` cast) works *by extending the
  selector web*, and that extension immediately knocks `var_a0_2` back off
  `a0` and cascades a whole-function renaming (alignment 757 -> ~400).
  12 pairings tried; the anti-correlation held in every one.
- **Baseline correction for the campaign.** `BEST_FINAL_func.c` is not the
  best candidate: it carries three `if (var_a0_2 * 4) {}` dead reads that
  over-hoist (1035 insns, 15 of the target's 18 scale `sll`s). Removing all
  three scores **678 words / 1041 insns** vs 784/1035; adding
  `if (var_a0_2) {}` to `case 0` gives the current best, **676 words,
  757/1037 aligned**. Re-baseline on that, not on BEST_FINAL.
- Unsolved. ~50 new variants (73 ledger rows) in
  `scratchpad/prehoist_bCVC/ledger.jsonl`. Next lever must come from below the
  source layer -- a CDX force probe on the scale web's color, exactly the
  conclusion texDPTextures round 3 reached for its a0/a1 pair.

## 2026-07-29 -- DLL (PIC) match campaign: first pass on `-KPIC` codegen

37 DLL functions matched in one session (DLL total 5764 -> 5801, 62.23% ->
62.63%; overall 68.19% -> 68.52%). Commits: DLL 32 (2), DLL 14 (10), DLL 714
(14), DLL 7 (10), DLL 615 (1). Everything below is from `-O2 -g3 -KPIC`
(`CC_FLAGS_DLL`) rather than the core `-G 0 -non_shared` profile.

### Loop / oracle for DLLs
- Object pairs live at `build/src/dlls/<path>/<name>.o` vs
  `expected/build/src/dlls/<path>/<name>.o`. `decomp-workbench compare/view
  --symbol <fn>` works unchanged; `ninja build/src/dlls/.../x.o` is a ~2s
  iteration.
- **`tools/progress.py` counts `asm/nonmatchings/dlls/<dir>/*.s` files on
  disk, not pragmas in the C.** After a match you must run
  `./dino.py extract-dll <num>` (which re-runs splat and deletes the .s for
  functions now found in the C) before progress moves. Easy to miss; cost me
  one confused cycle. *Tool gap: the workbench could expose a "did the count
  actually move" check that knows about this re-extract step.*
- Relocation noise is much higher than in core: IDO emits **section-relative
  GOT entries** (`%got(.bss)` + literal offset) where splat's expected asm has
  **per-symbol** entries (`%got(sym)` + `%lo(sym)`). The workbench correctly
  buckets these as `relocation_controlled`, but raw immediates differ
  (e.g. `sb v0,38(at)` vs `sb v0,0(at)`); read `words=0` /
  `verdict=instruction-exact`, not `raw`.

### PIC idioms (new levers)
1. **Local (static) vs global symbol address is visible in the instruction
   stream.** Taking the address of, or calling, a function in the same TU:
   - `static` callee -> `lw t9,%got(f)(gp); addiu t9,t9,%lo(f); jalr t9`
     (3 insns; same 2-insn shape when storing a function pointer).
   - non-`static` callee -> `lw t9,%call16(f)(gp); jalr t9` (2 insns), or a
     single `lw` when only the address is stored.
   This is the single biggest structural blocker in object DLLs: every
   `ctor`, dispatch-table builder and thin wrapper calls same-TU helpers.
   **IDO hard-errors on `static f(); #pragma GLOBAL_ASM(f)`**
   ("static function declared and referenced, but not defined"), so a
   caller cannot match until its callee is fully decompiled. DLLs must be
   worked **bottom-up**. (`subtitles.c` already carries
   "Needs to be static for matching" comments -- same finding.)
   Blocked this session on: `dll_714_ctor`/`func_0`, `dll_714_func_38A0`,
   `dll_413_setup`, `dll_662_setup`, `dll_251_func_B64`,
   `dll_210_func_1CCC0`, `dll_437_func_15F8`.
2. **`%lo` folding vs address materialization discriminates single-use from
   multi-use.** A single scalar store folds (`sw x,%lo(sym)(at)`); two or
   more accesses to the same object materialize the base
   (`lw v0,%got(sym); addiu v0,v0,%lo(sym)` then `0(v0)`). Corollary lever,
   used to fix `dll_14_func_6CA0`: an extra materialized base with **no**
   matching load means a *read that copy-propagation killed*. Source is
   `a = X; b = a;` not `a = X; b = X;` -- the read forms the address web,
   then folds away. Worth one variant every time an unexplained
   `addiu vN,vN,%lo(sym)` appears.
3. **`-g3` argument home stores are an unused-parameter tell.** `sw a0,0(sp)`
   with no frame adjustment (or `sw aN,0x2N(sp)` with one) appears for
   parameters that are *not* consumed in a register. `void f(s32 a){}` is
   exactly `sw a0,0(sp); jr ra; nop`. Narrowing casts also force a home
   store plus the mask: `u8` param -> `sw a0,..(sp); andi t,a0,0xff`;
   `s16` -> `sw a0,..(sp); sll/sra 16`; `u16` -> `andi 0xffff`.
   Reading the mask tells you the declared parameter type for free.
4. **Parameter-in-place beats a shadow local** (same as core). `dll_7_func_5E5C`
   needed `if (arg0 >= 0x1C) arg0 = 0;` -- introducing `u8 var = arg0;` moved
   the mask into `a0` and reordered the whole prologue.
5. **Redundant `& 1` on a comparison is real, not noise.** `slt t,zero,x`
   followed by `andi t,t,1` means the source wrote the extra mask;
   `dll_714_func_18E0` needed
   `(4 * ((x > 0) & 1)) * 4` where the sibling `dll_714_func_1968` needed
   `4 * (x > 0) * 4`. One `andi` = one instruction of divergence.
6. **`b` to the next instruction = a real `else`.** `v=A; beqz c,L; nop;
   b L; v=B; L:` is `if (c) v=B; else v=A;` -- the *hoisted* value is the
   else arm. Writing the `if`-only form (`v=A; if (c) v=B;`) drops the `b`.
7. **`if (A || B)` vs `if (!A && !B)` decides branch polarity.**
   `dll_14_func_6E24` was 89/89 instructions with exactly 2 words wrong
   (`bnezl` vs `beqzl`); rewriting the condition inverted-with-swapped-arms
   fixed both. Cheap first variant on any 2-word branch residual.
8. **Pointer subtraction of a non-power-of-2 struct emits a real `div`.**
   `bss_AC4 - bss_AC0` with `sizeof == 0x18` -> `subu; li at,24; div; mflo`.
   Seeing `div` by a struct size is a pointer-difference tell, not an
   integer division in the source.

### bss/data layout under PIC
- IDO aligns each `.bss` object to at least 4, and to 8 once it is >= 8 bytes.
  A scalar `s16` followed by a 6-byte pad array will *not* land the next
  object at +8 -- declare the padded scalar as an array instead
  (`static s16 bss_AC8[4];`), which keeps the symbol, the offset and the
  codegen (`bss_AC8[0]` folds `%lo` identically to a scalar).
- Retyping bss/data is free as long as the **symbol names** survive: the
  remaining `GLOBAL_ASM` .s files only need the names, not the types. That
  makes "type the whole bss block, then convert every function that touches
  it" a very high-yield unit of work (DLL 14: 8 functions in one edit;
  DLL 7: 10). Check first with
  `grep -rl '<sym>' asm/nonmatchings/dlls/<dir>/` that the symbols you want
  to *delete* (by folding into a struct) are only referenced by functions you
  are converting in the same pass.
- Object-DLL data structs: `Object.data` is at `0xB8`, `Object.srt.transl` at
  `0xC` (SRT is yaw/pitch/roll/flags/scale *then* transl), `globalPosition`
  at `0x18`, `velocity` at `0x24`, `seqSlot` at `0xB4`, `shadow` at `0x64`
  (`ObjectShadow.tr` at `0x20`). Most tiny object-DLL functions are
  `self->data` field pokes and decode in one pass from these.
