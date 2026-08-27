# Workbench improvement backlog

A living, prioritized queue of concrete improvements to the decomp-workbench,
each derived from a real matching campaign where the tool's current coverage,
correctness, or guidance fell short. Every item states the **symptom** (what a
real operator hit), the **proposed change** (which module), and the **payoff**.
New items are appended as campaigns surface them; resolved items move to the
CHANGELOG.

Priorities: **P0** correctness (the tool gives a wrong answer), **P1** coverage
(a whole class of residual is invisible), **P2** guidance/clarity.

---

## P0 — Correctness

### 1. Stale-build false positive in ROM-level comparison
- **Symptom.** An operator confirming a match with a `--rom`-style comparison
  (compare the just-built ROM to the target) got a silent **0 differing words**
  because the comparison read a *stale* `build/<rom>.z64` — the full ROM had not
  been rebuilt after the source edit. This burned a false "match" that only
  `decomp-workbench diagnose` against a freshly-assembled `target.o` caught.
- **Proposed change.** In `compare.py` (and any `--rom` path / host wrapper
  contract), add a **freshness guard**: stat the ROM/object mtime against the
  source and object it is derived from and **warn or refuse** when the compared
  artifact is older than its inputs. At minimum emit a one-line "⚠ comparing
  against a build older than <source>; rebuild before trusting a 0-word result."
- **Payoff.** Eliminates the single most dangerous failure mode — a *false
  match* — which wastes downstream verify cycles and can pollute a branch.

---

## P1 — Coverage (invisible residual classes)

### 2. FP register-web instrumentation — mostly landed; residual reclassified
- **Original symptom.** A function (Mickey `func_80012574`) was
  opcode/frame/schedule EXACT, differing only by an **`f14 ↔ f18` bijection**
  (7 words). It was believed unreachable because "the instrumented
  `globalcolor` profile emits integer webs only".
- **What the trace actually shows (2026-08-27).** That premise was wrong. FP
  webs **are** emitted, as `class=2` `p1dec`/`p2dec` records with
  `bestreg=?` — the pass keeps the integer decode table and the reader names
  the color (`globalcolor.py` `FP_COLOR_REGISTERS`, `c24`–`c29`, WB-80). For
  `func_80012574` the trace shows eight fp webs colored `c24`–`c30`; the
  `f14/f18` pair is web 40 (`c27`=`$f14`) and web 25 (`c29`=`$f18`).
  `CDX_FORCE` **does** steer fp colors: forcing `p1:w40=c29` moved the square
  web to `$f18` (a fresh force-and-diff receipt confirming `c29=$f18`). So the
  FP emission, reader map, force path, and tests already exist and are green.
- **Why the case is still walled.** The swap is **interference-forbidden**, not
  colorable: web 40 is colored before web 25 and takes `c27`; when web 25 is
  colored, `c27` sits in its forbidden mask (`0xf8`), and *stays* forbidden
  (`0xf4`) even after web 40 is forced off it — a second interferer holds it —
  so `p1:w25=c27` is **declined**. The target's coloring (projection→`c27`,
  square→`c29`) requires the **projection web to win coloring priority over the
  square web**, which is a `save`-order decision (projection `save=1.333`,
  square `save=1.5`), not a force. Declaration/lifetime/volatile/ABI probes do
  not move it, matching the plateau note in the source.
- **Remaining work.** This is now an item **#5** problem (name the owning pass
  and reachability): `diagnose` should tag `func_80012574`'s residual
  *uopt-fp / interference-forbidden* and point at the priority lever
  (`docs/p1-decision-arithmetic.md`) instead of at `CDX_FORCE`. Confirm the
  register names for fp colors `c30`–`c32` (observed; `c30` appears as the
  first spill/`split` color, so it may not be a register) before adding them to
  `FP_COLOR_REGISTERS`.
- **Payoff.** The FP-allocator residual class is already analysable and
  force-provable; the outstanding gain is verdict clarity so an operator is not
  sent to probe a force that must decline.

### 3. ugen temp-ring and g0-scheduler decision exposure
- **Symptom.** A batch of `register-only` near-misses (≤10 words, frame-exact)
  proved **integer-reachable-but-unwinnable**: the differing decision was owned
  not by a *colorable tie* (which levers steer) but by the **ugen temp-ring
  dequeue order** or the **g0 scheduler** placing a load, neither of which the
  current instrumentation exposes as a steerable web. The operator could only
  infer ownership indirectly (no p1 web maps the site; `CDX_FORCE` *declined*).
- **Proposed change.** Emit, per procedure, (a) the **ugen temp-ring pop
  sequence** with the source construct that consumed each pop (so a "phantom
  pop" from a redundant mask is visible as such), and (b) the **g0 schedule
  slot** each instruction landed in with its statement-line provenance. Let the
  analyzer answer "is this residual ring-owned / schedule-owned / color-owned?"
  directly.
- **Payoff.** Could re-open the ~20 currently-unwinnable `register-only`
  near-misses by revealing whether a *source foothold* exists (add/remove a
  mask to shift a ring pop; reorder a statement to move a schedule slot) instead
  of the operator guessing.
- **Progress (2026-08-27).** Part (a), the **temp-ring pop sequences** for
  both register classes, is landed. The entry `ALLOC_FP` hook logged the
  allocator's *request* descriptor, not the register it returned, and the
  integer allocator was not hooked at all (`f_alloc_reg`/`ALLOC` never fires;
  `f_get_free_reg` is the one that does). `instrument-ugen` now injects
  return-site hooks that emit `ALLOC_GP_RESULT` / `ALLOC_FP_RESULT` with the
  allocated register (`v0`), and `trace` decodes ugen's unified space (integer
  `0`–`31` by name, fp `32 + n` → `$fn`, request descriptors ≥ 64 numeric). On
  `func_80012574` the integer stream reads `t6 t7` and the fp stream is the
  `$f4 $f6 $f8 $f10` ring rotating in dequeue order — both rings observable
  from the pop side, and a phantom pop (a request resolving to an already-live
  register) is visible by comparing the paired `ALLOC_*` / `ALLOC_*_RESULT`
  records at one ordinal. Part (i) below is now landed too: each free-list
  record carries `line=`, ugen's current source line (`0x10018e00`, the value
  `f_warning` prints), tying a pop to its source construct. On Mickey
  `func_8001A154` this located the phantom pop directly — line 42
  (`flare.blue = entry->blue & 0xFFFFU`) is the one line consuming *two* ring
  pops; removing the redundant mask realigns the entire field-copy ring to the
  target (blue→`t4`, alpha→`t5`, size→`t7`, scale→`t9`, `multu $t8,$t9`). What
  then remains on that function is **g0-scheduler-owned** (the `li -1`
  materialization timing and the `div`-sequence `nop`/result register), which
  is sub-goal 3. **Still open:** part (b), the **g0 scheduler slot**
  provenance (sub-goal 3 below) — the last residual class walling the ring
  functions whose source construct is already correct.
- **Ring-residual survey (2026-08-27), using the new line provenance.** Across
  the Mickey resident `register-only` residents (`size_delta=0`), the pop-line
  correlation sorts each residual into an owner cleanly, which is the payoff
  this item promised. Results:
  - `func_8003A2C8` (menu): **color**, not ring. The 5-word residual is a
    `v0`/`v1` inversion of the `mode`/`modeBits` webs; both are `REMOVE`d from
    the free list at entry and colored by globalcolor, never popped from the
    ring. Belongs to the uopt-color / verdict track (item #5).
  - `func_8002C94C` (saves): **color**, not ring. A `s5`/`s6` (callee-saved)
    inversion — a phase-one globalcolor web, never a ring temp.
  - `func_8001A154` (lights): **ring, then g0.** The redundant `& 0xFFFFU` on a
    `u8` field is the phantom pop; removing it aligns the whole field ring, and
    the remainder is g0-scheduler-owned (above).
  - `func_8002CF6C` (saves) and `func_80020D8C` (models): **ring, same-length
    permutation.** Every differing word is a `t`-register substitution (a
    uniform phase shift, e.g. `+2` on models), but the objects are the same
    length with no *removable* folded-mask phantom — the redundant masks that
    exist (`& 0x40` on a proven-`{0,1}` value; `& 0xFF` on a `u32` index) are
    emitted in the target too. Shifting the ring here without changing
    instruction count is a **g0 schedule-order** decision, so these are gated
    on part (b), not on a source mask.
  - **Conclusion.** The removable-phantom-pop lever (part (i)) resolves the
    *ring* portion wherever one exists, but every surveyed resident then bottoms
    out on either globalcolor (v0/v1, s-web inversions) or the g0 scheduler
    (same-length permutation, `li`-hoist timing, div `nop`). **Part (b), g0
    slot provenance, is the single highest-leverage remaining piece** for the
    resident register-only tail — it is what stands between "ring source is
    correct" and an exact match on `func_8001A154`, `func_8002CF6C`,
    `func_80020D8C`, and their kind.
- **g0 instrumentation feasibility + authoritative-path deepening
  (2026-08-27, second pass).** Two findings that must precede any further push
  on part (b):
  1. **No clean hook for the scheduler.** Unlike the free list (discrete
     helpers `f_get_free_reg` / `f_get_free_fp_reg` with a single return), a
     search of the recompiled ugen for a scheduler / nop-insertion / reorg
     pass (`sched|reorder|slot|cycle|delay|nop|peep|interlock|hazard|r4300`)
     finds **no discrete function** to instrument. The instruction ordering
     and the `-Wab,-r4300_mul` protective-nop insertion appear distributed
     through the low-level emit path, so g0 slot provenance needs the emit
     records themselves tagged (per-instruction slot + line at the point each
     word is written to the ibuffer), not a helper hook — a materially larger
     change than the ring/line work, and the reason part (b) is not yet built.
  2. **Isolated `cc` differs from the real build path — always diff on the
     authoritative path.** An isolated `cc -c` of a single function does *not*
     schedule identically to the project path (`asm-processor` +
     `mips64-elf-as`) that `gmake verify` uses: on `func_8001A154` the two
     disagreed on instruction count (56 vs 58) and nop placement. Redone on the
     authoritative path across ~9 `func_8001A154` source variants (blue mask
     on/off, signed vs unsigned mask, explicit product temp, statement
     reorders), **no source form reproduces the target schedule**: the target
     is `multu; mflo; nop; nop; div` with `li -1` hoisted late (`t2`, 58
     instrs), while every variant lands either fields-correct with `-1` early
     (55 instrs, no nops) or fields-shifted with `-1` late (56 instrs). Both the
     isolated (IDO `as1`) and the authoritative (`mips64-elf-as`) paths omit the
     two `multu`→`div` protective nops, so the nops are **ugen-scheduled and
     source-dependent** — not an assembler artifact — and the source form that
     makes ugen emit them (an extra dependency that denies the scheduler the
     slot it otherwise fills, which also holds `li -1` down to `t2`) was not
     found by hand. This is precisely what part (b) g0 slot provenance would
     show: per-instruction, which slot each landed in and why the scheduler had
     one free early (hoisting `-1`) that the target's schedule does not. Until
     it exists, `func_8001A154` is recorded g0-scheduler-owned with no manual
     source lever.
- **Reachability pre-check + single-decision isolation (2026-08-27, third
  pass).** Before building part (b), the authorized reachability question was
  settled: **the protective-nop schedule IS reachable through the project
  toolchain.** `func_80024D00` (camera.c, a fully C-matched resident — no
  `GLOBAL_ASM`, not in `asm/nonmatchings`) computes `((a - b) * m) / (c - d)`
  and its verified ROM object carries `multu; mflo; nop; nop; div`. So the IDO
  `cc` → ugen → `asm-processor` → `mips64-elf-as` path emits the `-Wab,-r4300_mul`
  mul→div nops from C; these residents are **not** a toolchain limit.
- **But reachable ≠ lever-able, and the residual is now a *single* scheduler
  decision.** Diffing `func_8001A154` (no-mask) against the target on the
  authoritative path, the two objects are **byte-identical for the first 24
  instructions** — prologue, the three `mtc1`/`cvt.s.w` float conversions, and
  the early-hoisted constants `at=0x64` (the `/100` divisor, at insn 9) and the
  `0x41`/`0x2B` field constants. They diverge at **exactly one slot**: the
  1-cycle `mtc1 $f16` → `cvt.s.w` latency bubble (target insn 25, a real `nop`).
  The scheduler in our build *fills* that bubble with `li -1` (reusing `t1`,
  just freed from the `z` load), which pins `flare.index` to `t1` and cascades
  the whole tail (the `-1` lands at `t2` insn 31 in the target, leaving the
  mul→div slots as the two nops). `li -1` is a zero-dependency constant, always
  ready, so **no source dependency can hold it out of that bubble** — the
  difference is a pure list-scheduler slot-fill/priority choice, invisible to
  the source. g0 slot provenance would *display* this decision but not hand over
  a lever for it, so for `func_8001A154` part (b) would **confirm-and-record,
  not unlock**. This is the sharpest statement of the resident register-only
  wall: where a residual reduces to which ready instruction the list scheduler
  drops into a fixed latency bubble, there is no C-level steering — it is a
  permuter/rescheduler target, not a source-edit target.

### 4. Binary Ucode/Binasm capture streams
- **Symptom.** `capture make` retains binary Ucode/Binasm pass-boundary streams;
  `trace-fifo` / `trace-summary` reject them with UTF-8 decode errors, forcing a
  jump straight to Tier-2 instrumentation for any textual analysis.
- **Proposed change.** In `trace.py`, detect binary streams and either decode
  them via the known record layout or emit a clear "binary stream — use the
  instrumented toolchain (Tier 2) for textual traces" message instead of a raw
  `UnicodeDecodeError`.
- **Payoff.** Removes a confusing hard failure and clarifies the Tier-1/Tier-2
  boundary at the point of use.

---

## P2 — Guidance & evidence clarity

### 5. Verdict should name the *owning pass* and *reachability*, not just the class
- **Symptom.** `diagnose` reports a class (register-only / schedule / size), but
  the operator still had to spend real effort distinguishing the three
  actionably-different sub-cases: (a) a **colorable tie** a lever can move, (b) an
  **interference-forbidden** color (`CDX_FORCE` *declined* — the color is taken,
  not underpriced, so no reweight wins), and (c) a decision the **instrument
  doesn't expose** (ring/scheduler/FP). These demand opposite responses (try a
  lever / give up / extend instrumentation).
- **Proposed change.** Have the oracle/diagnose output tag each residual with
  **owning pass** (uopt-color / uopt-fp / ugen-ring / g0-schedule / structural)
  and a **reachability verdict** (lever-reachable / interference-forbidden /
  not-instrumented), driven by the force/decline signal and web-presence the
  tool already computes internally.
- **Payoff.** Turns minutes of manual `CDX_FORCE` probing per function into one
  line of guidance — the single biggest operator-time saver observed.

### 6. Contribute campaign-verified IDO 5.3 laws to the field guide
- **Symptom.** Several load-bearing levers were re-derived from scratch during
  the campaign though they are general IDO-5.3 behavior.
- **Proposed change.** Add to `docs/field-guide.md` / `docs/compiler-laws/ido-5.3.md`
  (verify each against the existing numbered levers first, cite evidence):
  - **ugen temp-ring init order** `t6,t7,t8,t9,t0..t5`, and the **phantom pop**:
    a redundant mask (`x & 1` into a 1-bit field) still consumes one ring pop.
  - **Declaration-order stack ladder**: declared locals take *descending* stack
    homes in declaration order — reorder declarations to place a spill.
  - **Float-literal vs extern scheduling**: a scalar joins the invariant-load
    group iff its *value* forces the rodata `lwc1` form (low halfword ≠ 0, e.g.
    `0.01f = 0x3C23D70A`); an int-representable const stays a statement-load.
  - **Call-argument color affinity**: a p2 web feeding a call arg inherits that
    arg register at cost 0 — re-cache a base into it each loop iteration to ride
    the arg register.
  - **Colorability gate**: `CDX_FORCE` *declined* ⇒ interference-forbidden ⇒ no
    reweight lever wins (distinct from *underpriced*, which a read-count dial
    can move).
- **Payoff.** Directly serves "as clear evidence and guidance as possible" —
  future operators (and agents) get the lever without re-deriving it.

---

## Workflow note (host-repo side, not the workbench itself)
- A per-function **closeness ranking** goes stale fast: functions matched since
  the snapshot still appear as "unresolved," sending workers at ghosts. Any host
  repo driving a fleet from a ranking should **regenerate it before each
  targeting pass** (in Mickey: `tools/nm_ranking.py`). Consider a workbench
  helper that stamps a ranking with the tree hash it was computed against and
  warns when that hash is stale.
