# Skill feed — content for n64-decomp-campaign (from dp64 campaigns, 2026-07-29)

> **Historical drafting record.** This file preserves the source material that
> fed the bundled skill. Use [Agent skill](agent-skill.md) and the installed
> `SKILL.md` for the current agent workflow.

Each entry names the skill file it should land in. Source evidence: five
campaigns (3 matched, 2 mapped) + one from-scratch authoring run + one
compiler-instrumentation deep-dive, all on IDO 5.3 `-O2 -g3 -mips2`.

## references/ido-late-stage-patterns.md — new mechanism sections

1. **The coloring pool and its order.** IDO 5.3 colors variable webs from the
   pool `v0, v1, a0, a1, a2, a3, t0..t5`, lowest free index wins; expression
   temps draw from a separate block-local rotation (`t6/t7/t8`, extending to
   `t4-t9,s8` under pressure). Probe order empirically with synthetic
   multi-carrier functions when traces are unavailable.
2. **Dead-web positioning selects registers.** A duplicated global read as an
   empty-if (`if (gGlobal) {}`) creates a code-free web that occupies the next
   pool slot, marching the following web down the order (rarezipUncompress:
   two dead webs put the carrier in $a3). Boundary: a dead web takes the
   *next free* slot — it cannot reach past a live web to free a specific
   register (objprint: fakes took v1, could never occupy v0).
3. **Empty-if reads survive DCE; `(void)expr` and bare statements do not.**
   `id == id;`, `(void)(x & mask);`, dead second stores — all eliminated with
   zero codegen effect. Reads inside an if-condition with empty body survive.
4. **Pool-vs-temp routing.** A named local spanning a loop promotes a value
   into the coloring pool (rarezip `end`); inlining a named local demotes it
   to the temp rotation. Which side of the divide a value sits on is often
   the entire residual.
5. **Temp-FIFO phase is set by the *preceding* block.** Temps pop from a free
   list and push back at last use. Two proven levers (modLoadAnimActual):
   hoisting a call argument into a named local (reorders value deaths), and
   `(x == C) != 0` inside a real `if` (materializes a phantom pop emitting no
   instruction). Context caveat: boolean-normalizing an actual branch
   condition is NOT free when it defeats bltz/bgez folding (+178w in
   texLoadTextureActual).
6. **Commutative operand order is front-end AST shape.** `a | b` vs `b | a`
   canonicalize to identical objects — dead family, never spend variants on
   it. `x |= y` is a distinct AST and flips emitted operand order
   (texDPTextureSimple).
7. **K&R implicit-int return types.** 1999-era sources may declare functions
   with no return type. `void` vs implicit `int` changes ugen coalescing
   (objprint: a whole `move` instruction appears only under a non-void
   return). When a candidate is exactly one coalescing copy short, try the
   return type before anything else.
8. **CSE multiplicity routes the coalesced copy.** Under equal shape, the
   copy lands on the multi-referenced CSE temp; make an expression
   single-occurrence (hoist through a named intermediate) to move the copy to
   the other value (objprint layer 2).
9. **Declaration order is usually inert** (three campaigns, ~1000 variants:
   full permutation no-ops) — EXCEPT absolute first-declared position can
   matter (texLoadTextureActual: moving the first-declared local anywhere
   regressed). Test cheaply once, then drop the family.
10. **Callee-saved tie-breaks ($s1 vs $s2) resist source search** — reorders
    canonicalize or explode. Go straight to the CDX_FORCE oracle.
11. **Don't fight the auto-hoist.** IDO can carry a loop-invariant memory
    read past an intervening call by re-reading memory each iteration; a
    candidate with identical source shape may instead register-cache and
    spill/reload around the call (+1 insn, +8 frame). Restructuring source to
    force the reread (loop splitting/duplication) defeats IDO's own
    loop-invariant motion and regresses hard (+147w in
    blockComputeVertexColors). The lever, if any, is register pressure near
    the call, not control flow.
12. **A consistent +N frame delta with a uniformly shifted stack-offset tail
    is one extra spill slot** — census the stack offsets (target vs
    candidate) to find the single spilled value; don't chase the shifted
    offsets individually.
13. **The `-g0` diagnostic (highest value per command).** When the residual
    is "same instruction multiset, target schedules/hoists further":
    recompile the candidate with `-g0`. If the region collapses to ~exact,
    debug metadata participates in the `-g3` ordering and as1 can reach the
    target schedule. This does **not** prove source correctness: a freer
    scheduler can rescue a non-original shape, as the eventual `vsprintf`
    match demonstrated. Compare expression/statement topology and line tags
    before ending source search.
14. **Web formation vs coloring.** A value can differ not in WHICH register
    a web gets but in WHETHER it becomes a colored web at all (target keeps
    it a ugen pool temp, candidate promotes it to a uopt web — texLoad).
    No color force can fix that class; the lever is liverange formation
    (f_makelivranges — hook specced, untested). Diagnose via the assign
    tracer: pool GET vs f_ureg provenance for the divergent register.
15. **Varargs functions are permuter-dead** (IDO va_arg unparsable by
    pycparser) — plan campaigns on printf-family functions accordingly.
16. **The redundant-mask lever (matched blockSetupVertices).** A source mask
    that is a no-op at the assembler (`(s16 & 0x3fff) << 18`) still consumes
    one ugen pool GET — a genuinely zero-instruction FIFO rotation, unlike
    `(x)!=0` guards which usually emit code. When the residual is a one-slot
    temp-FIFO rotation and neighbouring statements carry asymmetric
    mask/cast decoration, symmetrize the decoration first (one variant, not
    a search). Decoration asymmetry in a candidate is itself a smell — the
    original author's code is usually symmetric.

## references/evidence-ladder.md — additions

- **Byte-identical prefix + divergent register state** = the signature of a
  *byte-invisible upstream lever* (phantom pops, value-death order) OR of
  sub-uopt allocation (see next). Do not burn variants on the visibly
  divergent block first.
- **Layer exoneration by exhaustive force-coloring — WITH the phase caveat**:
  CDX globalcolor emits two disjoint web namespaces (`p1dec` callee-saved,
  `p2dec` caller-saved). A sweep is exhaustive only if it covers BOTH; a
  p1-only sweep produced a false "it's ugen" conclusion that survived a full
  campaign round (objprint — the residual was p2 web 55, one force from
  exact). Also now proven by instrumentation: ugen's own pool is t0–t9 strict
  FIFO; v0/v1/a0–a3 register choices are always uopt's, delivered in ucode.
- **Per-class register-sequence extraction** (pool sequence vs temp-rotation
  sequence, target vs candidate) converts "phase bug or coloring-order bug?"
  into a one-command answer. Use before choosing an experiment family.
- **Lineage recon before authoring**: for libc-shaped functions, census the
  asm (e.g. lwc1 vs ldc1 counts) against candidate ancestors' source
  conventions — cheap, decisive (vsprintf: glibc→Rare lineage, DKR integer
  core + JFG float fetch style, established in minutes).

## references/campaign-hygiene.md — additions

- Kill spawned permuter jobs on exit; a leftover -j10 job crashed two later
  runs (semaphore leaks under contention).
- decomp_permuter `base.c` contains `#pragma _permuter` sentinels — never
  hand-compile it; hand-test against a full real-TU copy.
- decomp_permuter `import.py`: pass absolute c_file/asm paths and run from the
  scratch dir (find_root_dir abspaths the c_file dirname; `nonmatchings/`
  lands in CWD).
- dp64 `tools/m2ctx.py` writes `<repo>/ctx.c` unconditionally — move it out
  immediately.
- Checkpoint best candidate + word count every ~20 variants on large
  functions; ledger everything (JSONL rows were load-bearing in every
  campaign).

## SKILL.md — guidance corrections

- Permuter's role: **hypothesis generator, not solver.** Across four runs
  (~140k iterations) it solved zero residuals but exposed one mechanism class
  (return-type coalescing) via its red-herring outputs. Budget it
  accordingly; never let it substitute for directed variants.
- The "capture a globalcolor/UGEN trace before adding local fakes" advice
  must be conditional on trace availability, and the allocation-mismatch
  guidance should offer: temp-queue phase (perturb the *preceding* block),
  pool-position (dead webs), coalescing (return type / CSE multiplicity) —
  three families the current text doesn't name.
- Add the divide-and-conquer pattern for >500-insn functions: align, bucket
  by region, fix structure biggest-bucket-first against lineage ground truth,
  then run the register playbook per remaining bucket.
