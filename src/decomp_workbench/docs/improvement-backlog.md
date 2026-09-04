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

**Status (landed).** Every comparison command states what it compared and when
each side was built, ahead of the verdict; `--built-from PATH` (repeatable)
names the inputs and makes the check enforceable; a compared artifact older
than one of its inputs is refused before anything is disassembled;
`--allow-stale` downgrades the refusal to a warning it never suppresses; and
`--json` carries the report as a namespaced `staleness` block.
`decomp-workbench check-staleness` and `staleness.staleness_report(...)` are
the host-facing halves, chain-aware (every earlier path is an input to every
later one) and able to record content hashes as well as times.
**Deliberately out:** the workbench does not discover the chain. Only the
project knows which sources produce which object and which objects produce the
ROM, and a guessed chain that silently checks the wrong thing would recreate
the false positive one layer down -- so the chain is declared, and an
undeclared one is reported `unknown` rather than `fresh`.

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

### 3. ugen temp-ring and g0-scheduler decision exposure — closed
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
- **Workbench status (2026-08-30).** The generic producer/reader contract is
  now complete. Ugen events carry producer procedure ordinals and can be bound
  to names from hash-pinned retained candidate Ucode. `DKWB-SCHED-V1` accepts
  optional emitted slot, source file/statement, reason, and full ready-set IDs;
  profiles declaring `provenance_required=true` must emit the complete set,
  and reports expose a completeness count. This closes the workbench-side
  schema and guard gap. A revision-specific emitter still requires a
  project-owned, source-hash-pinned profile and the documented fidelity gates;
  no universal generated-compiler patch is claimed.

**Status (landed, 2026-09-02). Part (b) is closed, and the premise it was
filed under was wrong.** The earlier finding — "g0 provenance is NOT hookable
via a helper fn (no discrete scheduler in ugen); it needs per-emit-record
ibuffer tagging, a materially larger build" — was half right and half a
category error. Right: there is no scheduler to hook. A full inventory of
ugen's **431 named generated functions** contains no ready list, no dependence
DAG, no delay-slot filler and no nop inserter. Wrong: that is not because the
scheduler is hidden inside ugen's emit path. **ugen has no instruction
scheduler at all.** The list scheduler is `as1`'s — `f_reorganize_bb`,
`f_schedule`, `f_fill_inst`, `f_emitnop` — already readable with no patch via
`cc -Wa,-R` and already decoded by `as1_reorganize`. "Which slot did g0 give
this instruction" has no answer, and asking for one is what stalled part (b).

What ugen *does* own is the scheduler's **input**: the order instruction
records enter the ibuffer, and the source line each one carries into as1. That
line is a key in as1's selection chain, minimised, and the only key in it with
a source lever attached. It is hookable by exactly the mechanism the earlier
note ruled out — a helper hook — because all 67 `f_emit_*` / `f_demit_*` /
`f_define_label` helpers are discrete single-entry functions that each write
one 16-byte ibuffer record at `MEM_U32(0x10018e70)` and then advance it.
`instrument-ugen --emit-provenance` hooks them; `DKWB_UGEN_SCHED=1` turns the
records on; `trace-emit` prints a block's emission order with lines and reports
its **line-order conflicts** — adjacent instruction records where the
later-emitted one carries a greater line, the pairs as1's line key can decide.

**The lever, and two closed acceptance cases.** The recurring shape is the
loop-invariant hoist: a base address lifted into a preheader is stamped with
the *loop header's* line, not its use site's, so every initialiser above the
loop carries a lower line and wins with no dependence edge behind it. Moving
the initialiser is not the lever — it is already as late as C allows. Putting
it on the **same physical line** as the loop header is, and both surveyed
residuals fell to it:

- `overlay40UpdateEntries` (44/46, first mismatch `+0xC`, handoff recorded as
  "no dependency edge authenticates a new source form"): loop count at line 45
  against the hoisted object-table address at line 46. `remaining = 7; do {`
  on one line → **46/46 exact**.
- `overlay57HandleModeInput` (3 relocation-masked differences, `+0xE0`–`+0xE8`,
  handoff recorded as needing "source-authentic evidence for IDO's
  base-address scheduling"): index initialiser at line 90/91 against two base
  addresses hoisted to line 92. Joining the initialiser to the `do {` line →
  **exact under the project's relocation-masked comparison**.

Both TUs pass the fidelity gate: built through the instrumented `cc` with
traces off, `.text` is `cmp`-identical to stock, in both the shipped
(`GLOBAL_ASM`) and `-DNON_MATCHING` configurations.

**What this does not reach.** `func_8001A154`'s residual, recorded above as a
`li -1` dropped into a fixed `mtc1`→`cvt.s.w` latency bubble, is a
ready-list/slot-fill choice inside as1, not a line assignment; `trace-emit`
displays its input but hands over no lever, and the third-pass verdict on it
stands. The lever this item now supplies is specific: it applies where two
independent ready nodes are separated **only** by the lines ugen stamped them
with, and it works by removing that separation.

**Deliberately out:** `trace-emit` does not report slot, ready-list position,
priority or delay-slot occupancy. ugen does not decide them, so any value
printed there would be invented; the report's `proof` string says as much and
names `trace-scheduler --from-as1-r` as where they live. Procedure *names* are
also out — ugen gives ordinals, and binding them to names is the existing
retained-Ucode mechanism, not a new one.

Part (a), the ring pop sequence with line provenance, landed 2026-08-27; part
(b) landed 2026-09-02 as ugen **emit** provenance — not slot provenance, which
does not exist, but the order records enter the ibuffer and the line each
carries into as1.

What the two halves are worth, measured. Of the 22 overlay targets with
measured work on 2026-09-02/03, seven closed exact: two on the ring pops per line
(L76–L78), two on the line-order conflicts (L80), three on frame arithmetic that
needed no trace at all (L72–L74). An eighth improved from 10 words to 6 on the
line join. Four more closed in the other direction — proved unreachable, with
the proof recorded so the builds are not spent again (L79, L81, L82, and the
coalescing tie). The one residual class this item named and did not reach is
item 15. A sixth class, the pool rotation, was separated from the pool
*population* difference it had been confused with a lane later (L83-L86, and
lever 44); the force experiment that proves such a residual reachable is item
16.

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

**Status (landed).** `trace.read_trace_source` is the one reader every trace
command goes through -- `trace-summary`, `trace-fifo`, `trace-alias`,
`trace-a71`, `trace-scheduler`, `trace-source`, `allocator-*`, `copy-decisions`,
`oracle` and `diagnose --trace`. A pass-boundary stream is refused **by name**,
with its record count, the decoder that reads it (`ucode window` /
`binasm window`), and the Tier-2 instrumentation that produces a textual trace
instead. Classification is delegated to `streams.detect_format`, so a trace
command and `stream diff` cannot disagree about what a file is.

**The decode was never the test.** A Binasm record's words are small integers,
so such a stream decodes as UTF-8 without raising and reported *zero events* --
a quieter and more expensive failure than the `UnicodeDecodeError` this item
was filed against. One NUL, or a tenth of the file in control bytes, plus the
absence of any diagnostic line, is the evidence used instead.

**Deliberately out:** the trace commands do not decode stream records. A stream
carries records, not the decisions that produced them, and the decision text
only exists when the instrumented toolchain writes it -- printing a record
window under a trace command would blur exactly the Tier-1/Tier-2 boundary this
item asked to clarify. What *is* decoded is a file that merely contains binary:
its diagnostic lines are recovered, the replaced bytes counted, and a `warning:`
on stderr states both, because the other line formats sharing this reader
(globalcolor, a71, scheduler) carry no tag and must never be gated on one.

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

**Status (landed).** Every verdict carries `owning_pass` and `reachability`
beside `routing`, printed on an `ownership:` line under the verdict and carried
in JSON (`decomp-workbench-diagnosis-v3`, `decomp-workbench-view-v3`, both
additive). `owning_pass` is one of the passes this workbench already models --
`cfe-spelling`, `rodata-load-form`, `stack-home-assignment`,
`uopt-globalcolor`, `ugen-temp-ring`, `g0-scheduler` -- plus `none` for an
exact pair and `unknown` for inputs that settle nothing. `reachability` is
`source-reachable`, `permuter-target`, `pass-owned` or `unknown`, and a
`pass-owned` residual routes `permuter-first` exactly like any other tie: the
verdict says no handle *this evidence* exposes reaches the decision, which is
never a claim about the function (item #8). Each ownership footer ends at the
law for its pass, so `func_80012574`'s class of residual now points at the
mechanism instead of at a `CDX_FORCE` probe that must decline.

**A third field carries the honesty:** `ownership_basis` is `trace` when a
compiler trace settled it, `heuristic` when the answer was read off the
residual's shape, `none` when there was nothing to read -- never omitted, and
never inferred from the other two. `globalcolor.pass_evidence` is the
producer of the measured half, built from the two facts an instrumented uopt
already computes (a declined force, a `regsleft=0` contest), which are exactly
what separates a *taken* register from an *underpriced* one.

**Deliberately out:** the heuristic does not attempt to distinguish a
colourable tie from an interference-forbidden one without a trace. Two
disassemblies cannot see a forbidden mask, and a guess dressed as that
distinction would send a reader to give up on a residual a lever reaches --
the exact failure this item was filed against, in the other direction. Without
a trace those residuals are `permuter-target`, which is the honest answer and
the cheap one.

---

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

**Status (landed).** Nine laws, L62-L70 on
[the IDO 5.3 page](compiler-laws/ido-5.3.md), each with its receipt, evidence
tier and provenance, and eight new rows in that page's "claims a reader will
find in older notes and should not believe" table. The five levers this item
listed all landed, three of them differently from the sketch above:

- the **temp-ring seed** is L64 and the **phantom pop** is L65, split because
  they are a startup constant and a construct and the second is usable without
  the first;
- the **declaration-order stack ladder** is L63, filed as a *reconfirmation*
  of L53 rather than as a new law, because L53 already had it from a read of
  the cfe intermediate -- what this campaign added is the operational form and
  four whole-object matches. The two campaigns disagree on which pass writes
  the map; the law says so and leaves L53's instrument to settle it;
- the **float-invariant load form** is L62, sharpened: the gate is the
  constant's low halfword, not "int-representable";
- the **call-argument colour affinity** is L66, filed as the cost-side
  companion to L58;
- the **colourability gate** did *not* become a law. It is already L55 plus
  L57's `available0` argmin, and re-stating it under a new number would have
  put two numbers on one fact. It landed as machinery instead: `CDX_FORCE`
  declined and `regsleft=0` are what `globalcolor.pass_evidence` reads, and
  what makes an ownership verdict `pass-owned` on the `trace` basis (item #5).

Three laws the item did not ask for came out of the same campaign and are on
the page because leaving them off would have been arbitrary: L67 (a comparison
prints its copy-propagated variable first), L68 (the jump table's bytes are
the case mapping), and the two false-floor lessons as **measurement** laws --
L69 (a permuter that finds nothing instantly is a setup fault) and L70 (an
isolated `cc -c` does not schedule like the project path).

**And the laws are addressed, not just written.** `guide laws ERA LAW` prints
one law; `PASS_LAWS` keys them on the owning pass a verdict names, so a
residual's footer ends at its own law as a pasteable command; and
`PLAYBOOK_PASSES` gives `guide <family>` the same citation. The cross-link is
keyed on the pass rather than on the playbook because that is the finer
question -- a stack-home residual and a wrong immediate both arrive under
`playbook=constant-audit`, and only one of them is L63's.

**Deliberately out:** nothing measured on Mickey's pinned 5.3 was added to the
7.1 page, and no law was written from a campaign note alone. Two candidate
levers from the same notes are not here because their receipts are outcome
evidence about one function with no controlled comparison behind them.

---

## Workflow note (host-repo side, not the workbench itself)
- A per-function **closeness ranking** goes stale fast: functions matched since
  the snapshot still appear as "unresolved," sending workers at ghosts. Any host
  repo driving a fleet from a ranking should **regenerate it before each
  targeting pass** (in Mickey: `tools/nm_ranking.py`). Consider a workbench
  helper that stamps a ranking with the tree hash it was computed against and
  warns when that hash is stale.

---

## P1 — New (2026-08-27, from the permuter campaign false floors)

### 7. Permuter health-check / flag sanity
- **Symptom.** decomp-permuter's importer defaults to `-mips1`; the host build
  is `-mips2`. A naive flag-correction via `gmake -n <obj>` prints nothing for an
  already-built object, so the scratch silently stayed at `-mips1` and the search
  explored the wrong ISA — 8/12 targets "found nothing instantly," read as hard
  functions but actually a flag fault. (Fixed host-side: touch the source first
  plus a loud warning.)
- **Proposed change.** A workbench `permuter doctor <fn>` / import preflight:
  assert the scratch `compile.sh` ISA/flags match the project's real per-file
  flags, that `base.o` compiles, and that the base score is finite and > 0;
  refuse or loudly warn otherwise.
- **Payoff.** Kills the most expensive false-floor class: a permuter quietly
  searching the wrong target for hours.

### 8. `diagnose` verdicts must defer to the permuter, never read as walls
- **Symptom.** "interference-forbidden colour" and "list-scheduler slot-fill — no
  source lever" verdicts were taken as proof of un-matchability; the permuter then
  matched func_8002C94C and func_8001A154 anyway. An over-confident verdict sent
  ~1M tokens to bespoke instrumentation instead of a 20-minute permuter run.
- **Proposed change.** Whenever `diagnose` emits a "no hand-lever" verdict for a
  register/colour/schedule tie, append: "no *hand* lever found — permuter target;
  run permute.sh before concluding a wall." Never phrase an allocation tie as
  proven-unmatchable.
- **Payoff.** Routes ties to the tool that cracks them; stops analysis from
  manufacturing false floors.

**Status (landed).** `routing` is a field on the verdict -- `permuter-first`,
`structural`, `import-fix`, `none` -- printed in the `view`/`diagnose` header
and carried in JSON (`decomp-workbench-diagnosis-v2`,
`decomp-workbench-view-v2`, both additive). Every allocation, colour, or
schedule tie ends its footer with the routing sentence and the two commands
that act on it, and lever 19 plus the `forced-color-oracle` onramp were
reworded from "legitimate stopping point" to "legitimate stopping point for
HAND search", with the wall recorded only after `permute classify` measures a
flat search. **Deliberately out:** the tool does not *run* the sweep for the
operator, and `routing` is a claim about which tool to try next, never a
prediction that the search will succeed -- the prediction is what
`permute classify` measures afterwards.

### 9. Permuter scratch must replicate the TU's post-compile objcopy steps
- **Symptom.** Some TUs get a Makefile `objcopy --redefine-sym A=B` after compile
  (Mickey track.c, from the func_8000D018 TrapDanglingJump fix). The permuter's
  import builds its scratch object WITHOUT that objcopy, so a score-0 in the scratch
  does not transfer to the real build — every track.c permuter result was a
  non-transferring "false ceiling" (func_80012574: 2–4 words off, frame exact).
- **Proposed change.** The import/scratch build should detect and apply the same
  post-compile object transforms the Makefile applies to that TU's .o (parse the
  `objcopy`/`--redefine-sym` from `gmake -n <obj>`, already used for flag recovery),
  so the scratch object == the real object. Then track.c permuter matches transfer.
- **Payoff.** Unblocks the whole track.c permuter class and removes a subtle, expensive
  false-ceiling source.

  - **Also (same root):** the importer injects its own `gDP*`/`gSP*` macro definitions
    via `#pragma _permuter latedefine`. If a TU's real header macros differ, gfx-heavy
    functions (Mickey particles.c func_80041CE4: frame -136 vs -128) also fail to
    transfer. The scratch should use the TU's real macro context, not injected stubs.
    Net rule: a permuter scratch object must be bit-identical to the real per-TU object
    (flags + post-compile objcopy + real macros), or its score-0 is not a real match.

---

## Status update (2026-08-28, Mickey Epoch 14 setup)

- **#7 landed host-side** in Mickey `tools/permute_batch.py` (`build_recipe_for`):
  the real cc line is recovered from `gmake -n <obj>` after touching the source.
  Two further faults found while porting, both worth a workbench preflight:
  (a) gmake echoes the recipe with a backslash continuation, so the flags sit
  on a line that does not name the compiler -- join `\`+newline before parsing;
  (b) the static "flag group" tables every host tends to keep were wrong for a
  TU that *looked* default (`lights.c` carries `-Wab,-r4300_mul`); only the
  build's own dry-run is authoritative. Proof: `func_8001A154` is re-found from
  its pre-match source in 75 s and promotes through the real build.
- **#9 landed host-side** (objcopy chain appended to the scratch `compile.sh`,
  digest-guarded `.py` passes skipped and listed in `recipe.txt`). The injected
  gfx-macro context part landed in the workbench afterwards; see the status
  below.

**Status (#9 landed in full).** Both halves are in `permute-sweep` /
`permute-doctor`. The post-compile `objcopy` chain is recovered from the
build's own dry run and replicated into the scratch's `compile.sh`. The
injected-macro half is now measured rather than assumed: after each import the
scratch base is compiled through that same `compile.sh` and its object compared
with the project's object for the translation unit, reported as
`scratch_fidelity` (`identical` / `differs(N words)` / `unknown` /
`unchecked`). When it differs and `import.log` says macros were preserved, the
import is retried through `[permuter] preserve_macro_modes` -- default
`["configured", "none"]` -- and the first byte-identical mode wins;
`--require-fidelity` refuses a function whose scratch is not the real object.
Two limits worth stating. The comparison is the function's instruction words
and their relocations, not whole sections: a scratch holds one pruned function
where the project object holds a whole translation unit, so `.data` and
`.rodata` differ there for reasons that are not codegen. And repairing by
*narrowing* is all the workbench can do -- importing the real macro
definitions while still letting the permuter permute inside them would be a
change to decomp-permuter's importer, not to a driver around it. `none` is the
trade: the real expansions, and macro calls the permuter treats as opaque.

### 10. Permuter sweep driver as a first-class workbench command
- **Symptom.** Every host re-invents the same batch loop around decomp-permuter,
  and each re-invention re-introduces the fidelity faults (#7, #9, stack-diffs).
  Mickey's 2026-08-25 farm (0 hits / 38 searches) was such a re-invention and
  produced a false "queue exhausted" verdict for a 300 KB NON_MATCHING queue.
- **Proposed change.** `decomp-workbench permute-sweep <queue>`: closest-first
  ordering from the ranking, scratch built from the project's real recipe
  (flags + post-compile transforms), `--stack-diffs` forced, niced and
  load-gated launches, resume from a summary, score-trend extension (re-seed
  from the best candidate only when the best result landed in the final third
  of the window), and verify-once promotion on the authoritative build path.
  Reference implementation: Mickey `tools/permute_batch.py` + `permute_sweep.sh`.
- **Payoff.** The single highest-EV, zero-token lever in a late-stage campaign
  becomes a one-command, hard-to-misconfigure tool.

**Status (landed).** `decomp-workbench permute-sweep` is that command, and
`permute-doctor` is #7's preflight; both are documented in
[Permuter sweeps](permute-sweep.md) and recorded in the CHANGELOG. The
scratch is built from the project's real recipe (flags recovered from
`make -n` with continuations joined and the source touched first, plus the
post-compile `objcopy` chain replicated into `compile.sh`), `--stack-diffs`
is forced, launches are niced and load-gated, ordering is closest-first,
`--resume` continues a summary, and the extension only fires on a search
that was still descending. **Promotion stayed out**: proving a candidate on
the authoritative build is host-specific, so the sweep reports and the
project's own tooling promotes. Still open from #9: the importer's injected
gfx-macro context.

### 11. Ranking freshness stamp
- **Symptom.** (Promoted from the workflow note above.) A closeness ranking
  drifts within hours; Mickey's snapshot carried two already-matched functions
  and was used as an ownership ledger it never was.
- **Proposed change.** Stamp every ranking with the tree hash it was computed
  against; `diagnose`/sweep consumers warn when HEAD differs, and the sweep
  regenerates it per pass.

**Status (landed, except regeneration).** `decomp-workbench ranking stamp`
records `tree_hash` + `generated_at` into the ranking as one added key, and
`ranking check` compares it with `git rev-parse HEAD`, exiting 1 on anything
but a match. `permute-sweep` and `permute-doctor` run that check on the
ranking they were given: `stale` and `unknown` are loud warnings, `unstamped`
is a quiet note (it is where every project starts, and a warning everybody
sees is one nobody reads), and `--require-fresh` refuses. **Regenerating the
ranking per sweep pass stayed out**: producing a ranking needs the project's
own build and its own notion of what "unmatched" means, which is the same
reason the queue is an input. The stamp is what makes the staleness visible;
the project regenerates.

### 12. Permuter outcomes as the wall-class evidence
- **Symptom.** Wall classes (P / P! / F / S / W) are assigned by hand from
  verdict prose, and the "unwinnable" class has repeatedly been wrong.
- **Proposed change.** Aggregate the sweep's `summary.json` (base score, best
  score, extended?, promoted?) into the per-function record so a function is
  classed `P!` (permuter-stuck, score still descending) or `W-candidate` (flat
  from the first minutes) by measurement, and only *then* routed to trace
  levers or instrumentation. Mickey's Epoch 14 uses exactly this list to decide
  whether the g0-scheduler provenance build (#3) is worth funding.

**Status (landed).** `decomp-workbench permute classify <summary.json>`
assigns `MATCHED`, `P_STUCK_DESCENDING`, `P_STUCK_FLAT` or `IMPORT_FAULT`
from the sweep's own record, prints the numbers behind each call, and emits
either a pasteable markdown table or JSON
(`decomp-workbench-permute-classify-v1`). The sweep summary gained the fields
the call needs -- `best_output_mtime_fraction`, `window_seconds`, `hit_cap` --
because decomp-permuter overwrites its output directories and nothing else
records when a search last improved. The routing is documented with the
classes: only `P_STUCK_DESCENDING` goes to trace levers or a human,
`P_STUCK_FLAT` is the pool that argues for or against funding instrumentation,
and `IMPORT_FAULT` goes to the scratch. Two deliberate conservatisms: a run on
fallback flags is listed as describing the scratch rather than the function,
and an improvement whose timing was never recorded is classed descending, since
being wrong towards `P_STUCK_FLAT` is what funds a build for a function nobody
measured. The `P`/`P!`/`F`/`S`/`W` letters stay a host convention; this command
supplies the measurement they are supposed to encode.

### 13. Review follow-ups (2026-08-28, second review pass)
Small, each verified as a real gap and deliberately left out of the review commits:
- `compile_scratch_base` (and `import_scratch`, `make -n` recovery) have no timeout; the fidelity check adds up to two unbounded children per function. Give the scratch phase one bounded `run_owned` policy.
- `staleness_cli --tolerance` hardcodes `1.0` instead of `DEFAULT_TOLERANCE_SECONDS` and accepts negatives.
- `view.__all__` lacks `ROUTING_VALUES` / `ROUTING_*` while the other value lists are exported.
- `globalcolor.pass_evidence` is API-only: no `diagnose` flag feeds a trace, so `ownership_basis=trace` never appears on a terminal. Add `--trace PATH`.
- L66 has no `Scope` line and generalises one T1 trace; either scope it or mark it single-observation.
- Laws L62–L70 and `docs/permute-sweep.md` cite ROM function addresses, frame sizes and register groups (no instruction text); add the one-line redistribution basis CONTRIBUTING asks for, or state that symbol-level citations are exempt.

**Status (landed).** All six, in that order:

- **The scratch phase is bounded.** `[permuter] step_timeout_seconds`
  (default 600) is one policy over the three children that had none --
  `make -n` recovery, `import.py`, the fidelity compile -- applied through
  the `run_owned` runner each of them already took. `run_owned` could always
  end a process group on a deadline; it had never been handed one here. The
  `make -n` deadline is deliberately *not* fatal: its failure already has an
  answer (the fallback flags, plus the warning that says they are not the
  build's, plus the doctor refusing the function for it). Zero and negative
  are refused, because they are not "no deadline" -- they expire every child
  instantly.
- **`--tolerance` takes the shared constant** and refuses a negative window.
  A negative tolerance is not a stricter check but an inverted one: it calls
  a correctly-built artifact stale, and a reader who sees that learns to
  ignore the verdict. Zero stays legal; it is a policy somebody can mean.
- **`view.__all__` exports all four verdict vocabularies whole**, plus
  `routing_for` beside `ownership_for`. Exporting `ROUTING_VALUES` alone
  would have fixed the symptom and left the shape that caused it, so the
  test asserts the property -- every `BASIS_*`/`OWNING_PASS_*`/
  `REACHABILITY_*`/`ROUTING_*` value is exported -- rather than a list.
- **`diagnose --trace PATH` reaches `ownership_basis=trace`.**
  `--trace-proc`/`--trace-web` scope it, and the scoping is the substance:
  a trace covers a whole compilation and a residual is one function's, so an
  unscoped read would manufacture a measurement out of an unrelated declined
  force -- item #5's failure in the other direction. The footer states the
  scope when the trace settles ownership and says the trace settled nothing
  when it does not, because silence there reads as agreement.
  `examples/fixtures/globalcolor-declined.log` is the synthetic trace.
- **L66 is scoped to one observation**, naming the neighbouring cases nobody
  measured (a web feeding two calls at different argument positions, a web
  read after the call, the affinity against a competing pin) rather than
  demoting the tier: the instrument *was* read, so the receipt stands for
  what it saw; only the generality was never established.
- **The redistribution basis is recorded as an exemption**, which is the
  honest reading: a function's name, size, frame and register group is a
  measurement result from which no instruction can be reconstructed, not a
  copy of any part of a binary. CONTRIBUTING says so once, both pages state
  it at the point of use along with the fact that the objects behind their
  receipts are not redistributable and are not here, and the line stays
  exactly where it already was.

**Deliberately out:** no CLI override for `step_timeout_seconds`. A per-run
deadline is a property of the host's toolchain, not of one invocation, and a
second place to set it is a second place for it to disagree with the config.
`--trace` is not offered on `view`/`view-dumps`: the ownership verdict is
what a trace changes, and `diagnose` is where a reader acts on it.

### 14. Overlay relocation-surface synthesis (from Mickey, 2026-08-28)
- **Symptom.** In a game whose overlays ship unrelocated, promoting a candidate
  needs a bespoke post-compile ELF contract (add-symbol / rebind / filter /
  trim) hand-derived per function from the target's relocation table; that
  ritual, not the C, gated a 299 KB pool, and the permuter could never score
  zero on those functions (placeholder call symbols vs table resolution).
- **Finding.** Every placeholder's value is a pure function of the stored
  addends at its sites and the TU's placement (audit 1773/1773 on Mickey;
  `tools/reloc_surface.py` there). The linked ROM, not the scratch score, is
  the only sound oracle for such functions.
- **Proposed change.** A workbench `reloc-surface` helper: given an object, the
  module's section map and the target bytes, emit the symbol values / alias
  block / extent spec, and an `promotion-trial`-style linked comparison mode
  that classes candidates by linked bytes (exact / text-differs N / collateral).
  Also: `permute-doctor` should refuse (or warn) when the target's relocation
  symbols are placeholders that the scratch cannot reproduce.
- **Payoff.** Turns per-function integration ritual into generated data and
  gives overlay-style code a real oracle.

**Status (landed).** Three commands, generalized away from any one game.
`reloc-surface` reads a module's objects, a section map the host writes once
(`decomp-workbench-module-map-v1`: module image range, section ranges,
per-object text placement, synthetic VMA, an optional shipped relocation table
for corroboration, an optional alias template) and the target image, and emits
the linker symbol block and alias block. Two sites demanding different values
are refused as `schedule-divergence-at-site` with both values and every
conflicting site; `--audit` replays an existing hand-written block and scores
it `agree` / `disagree` / `untracked` / `unreproduced`. `linked-compare`
classifies a built image against the target per function range -- `exact`,
`text-exact`, `text-differs N words`, `size-differs (+N)` -- from `--range
NAME:START:END` or a `decomp-workbench-image-ranges-v1` file.
`permute-doctor --target-object` warns when every `R_MIPS_26` site in the
target names the function itself or a symbol the candidate lacks, and routes
to `linked-compare` instead of the score. Recorded as **L71** on the IDO 5.3
laws page; documented in [The linked image as an oracle](linked-oracle.md).

**Deliberately out:** no build orchestration. Splicing a candidate, running
the project's make, regenerating the surface between the compile and the link,
and restoring the tree are the host's, because only the project knows how it
builds -- a guessed loop would be wrong in the way that costs a day. The
host-side loop is written out in the documentation, with the originating
project's tools as the worked example, and the workbench measures the bytes it
is handed. Also out: the workbench does not decode a module's relocation
table. Its format is per-game, and a wrong decode would silently corroborate
the wrong sites; the table is an input, and a run without one says so.

---

### 15. Model as1's `besttime`, so readiness is predicted and not only observed
- **Symptom.** `cc -Wa,-R` says which key decided a selection, which is enough
  to rule the line lever *out* — and after that the analyst is blind. Five
  Mickey targets on 2026-09-02/03 (`overlay1FindNextAngle` and its twin
  `overlay1FindPreviousAngle`, `overlay11UpdateMenu`,
  `overlay33InitializeBuffers`, `overlay1ResolvePathPoint`) each ended in the
  same place: the trace shows the
  block's nodes, their readiness, and the leftover that took the delay slot,
  and nothing says what a *different* source form would make ready. On the
  overlay 1 pair alone that cost seven `-Wa,-R` traces and three full builds
  across seven levers, of which exactly one moved the schedule — and it moved
  the wrong instruction into the slot. The other three functions' lane iterated
  compile-only, so no build count attaches to them.
- **What is already known, which is most of the model.** The key chain is
  decoded and reproduced against 2688 recorded selections (`as1_reorganize`).
  `besttime` is release recency and follows ugen's emission order, which
  `trace-emit` now prints. The leftover-node law is measured: in a block of *N*
  pre-branch nodes whose branch becomes ready at cycle *N*−1, exactly one node
  is left over, and a leftover always wins the delay slot (**L79**). The
  missing piece is not the rule — it is running the rule forward.
- **Proposed change.** A `replay-as1` that takes one block's nodes from a
  `-Wa,-R` trace and answers the counterfactual: given this dependence graph
  and these latencies, which node is left over, and what would have to change
  about the node set for the branch to be picked last. Two outputs, not one:
  the predicted selection sequence, and the **node-count** delta the target's
  schedule requires — because L79's whole content is that the reachable edit is
  a change in what is in the block, not a change in where a statement sits.
- **Payoff.** Turns four recorded walls into a question with an answer, and the
  next one into a prediction rather than a build. It also closes the loop with
  the lever diagnosis, which today reports `unreachable/as1-readiness` from the
  deciding key and can say nothing about what would reopen it beyond naming
  this item.
- **What it must not do.** Predict a schedule for a source form nobody
  compiled. A counterfactual over the *node set the trace recorded* is a
  measurement; a counterfactual over a hypothetical node set is a simulation of
  ugen as well as as1, and there is no model of ugen's emission here. The
  output has to say which of the two it is.
- **One disagreement to settle on the way.** Two campaigns place `besttime` and
  `aftercycles` differently relative to each other in the chain, and neither's
  recorded selections separate the orderings. Nothing shipped depends on the
  answer today, and L79 says why; a forward model does.

### 16. Plan the force experiment, do not leave it to be typed

- **Symptom.** `words=0` under `CDX_FORCE` is the strongest verdict the
  workbench can produce for a register residual, and reaching it is still a
  hand exercise. On `overlay4UpdateObjectMotion` (Mickey's Speedway USA,
  2026-09-03) it took seven builds to find that three pinned colours closed
  the object: one force on the switch selector took 8 differing words to 5, and
  the selector plus the tied pair took it to 0. Every one of those forces was
  derivable before the first build — the residual names the registers, the
  colour table names their colours, and the CDX records name the webs holding
  them. `diagnose --force-result` reads such a run and says what it proved;
  nothing plans one.
- **Proposed change.** Given the residual's web substitutions and a CDX
  capture, emit the **minimal** force set and run it: for each substitution,
  the web that holds the candidate's register and the colour of the target's,
  skipping any colour already in that web's `forbidden0/1` mask (the pass
  declines those, and `oracle_plan` already refuses to guess a colour
  universe). Then the singletons first, the full set last, so a partial
  closure is attributed to a force rather than to the set. `oracle_plan` and
  `oracle_sweep` already compile a grid and compare it; what is missing is the
  step that turns *this residual* into *these cells*.
- **Payoff.** One command between a `pool-rotation` verdict and a reachability
  proof, and the proof is what separates "one spelling away" from "not
  available in this web graph" — the two states a lever block cannot tell
  apart on its own, and the ones that decide whether the next hour is spent on
  source or on the permuter.
- **What it must not do.** Report a force set as a match. A forced object is a
  statement about the allocator, never source-match evidence, and the
  distinction is already load-bearing in `oracle`: the plan must keep saying
  so. Nor may it widen a colour candidate list beyond what the capture and the
  residual name; an incomplete honest plan is the existing contract.
- **Blocked on nothing.** The inputs are the ones `diagnose --ladder
  --force-result` already takes.
