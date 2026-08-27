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

### 2. FP register-web instrumentation
- **Symptom.** A function was opcode/frame/schedule EXACT with the fp-temp ring
  identical, differing only by an **FP-pool bijection** (e.g. `f14 ↔ f18`).
  `CDX_FORCE` could not steer it and no source lever reached it, because the
  instrumented `globalcolor` profile emits **integer webs only** — every
  `p1dec`/`p2dec` bestreg observed was an integer register; FP allocation is
  wholly unobserved. Such residuals are currently **unprovable and unreachable**.
- **Proposed change.** Extend `globalcolor.py` + `instrument_uopt.py` /
  `instrument_profiles.py` to also emit FP register webs (f0–f31 / fp-pool slot
  assignments) and to accept `CDX_FORCE` directives over FP colors. Surface the
  FP free-list/pool state in the trace the way the integer ring already is.
- **Payoff.** Opens the entire **FP-allocator residual class** to analysis and
  force-proof — today a hard dead-end (see the Mickey `func_80012574` case).

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
