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
  records at one ordinal. See the CHANGELOG. **Still open:** (i) each pop's
  **statement-line** is not emitted — `trace.py` already parses a `line=`
  field, so the emitter need only stamp ugen's current source-line global on
  the freelist record, which would tie a pop to the *source construct* that
  consumed it (the piece that turns "one phase off" ring residuals like Mickey
  `func_8001A154` into a specific source edit); (ii) part (b), the **g0
  scheduler slot** provenance, is untouched (sub-goal 3 below).

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
