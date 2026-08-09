# Changelog

## Unreleased

- **`align` reports the edit script, not what the shift cost.** `compare` and
  `score` index by position, so an object that is byte-exact apart from one
  extra instruction reports a four-figure mismatch count and reads as garbage;
  one campaign paid that cost eleven separate times and two more stages
  rediscovered the same gap. `decomp-workbench align TARGET.o CANDIDATE.o` (and
  `align-dumps` on retained objdump text) aligns the two instruction streams and
  prints `replaced`/`inserted`/`deleted`, the target rows each block lands at,
  the derived cut list, and one headline: how many instructions away the
  candidate really is. Several candidates give a one-line-each census ordered by
  that number. The two objects' relocation rows stay in separate spaces — merging
  them over-masks near a shift boundary and silently dropped two genuine
  mismatches from a published count — and branch destinations are renormalized
  through the pairing so an insertion above a correct branch is not charged as a
  difference. `--window LO..HI` tallies insertions before and inside a named row
  range. `--json` emits `decomp-workbench-shift-diff-v1`.

- **`phase` reads the scratch-ring phase as a vector over named row slots.**
  Three campaign scorers reported a ring rotation and each lied differently.
  `decomp-workbench phase TARGET.o CANDIDATE.o --slots 'B1=0..1573,B4=1574..4640'`
  prints, per slot, the coset that would make it match, the quotiented count
  under that coset, and the positional count it really scores — never the first
  without the second, because one campaign's headline "39 → 29" was 1045
  positional rows and three stages recorded ring-flipped objects as wins. Slots
  are checked to partition the row space: a hole is an error naming the rows,
  after a band table left 105 rows of a 4641-row object unnamed and a candidate
  scored `RAW=1` with two real mismatches. Rows are paired through `align`, so a
  shifted candidate scores near its true residual. `--require-ni` refuses a
  candidate of the wrong length; `--base`/`--require-base` pin the source the
  table was built from; a slot with no coset-dependent rows reads `no-evidence`
  rather than being labelled from nothing, and `--context OBJECT` prices a
  construct in composition instead of alone; `--baseline OBJECT` reports healed
  and broken rows separately. Any register pool may be the ring. `--json` emits
  `decomp-workbench-phase-v1`. Documented in `docs/shift-and-phase.md`.

- **A disassembly cache that cannot answer "perfect" because it was truncated.**
  `align` and `phase` accept `--disassembly-cache DIR`, whose entries are trusted
  only when they prove they are a complete disassembly of the object on disk: the
  object's SHA-256, the entry's own row count against what the body parses to,
  and — for a whole-section dump — against the words the object's ELF section
  holds. The cache every campaign writes guards on existence alone, so a run
  killed mid-write leaves a zero-byte file that parses to no rows and therefore
  reports no mismatches: a silent perfect score, reported five times
  independently. There is no default cache directory, because a scorer with one
  scores whatever is in it.

- **A commutative row is a lever, and it is often one row up.** `compare` and
  `diagnose` now name each commutative operand pair — which expression, which two
  operands, and that the edit is expression shape rather than allocation. IDO
  canonicalizes `a + b` and `b + a`, so a wrong operand order frequently leaves
  the arithmetic row byte-identical and surfaces only in the two operand loads
  above it, whose destinations are crossed; a classifier reading the differing
  row alone calls those an ordinary register difference and sends the reader to
  the allocator for a front-end question. Both shapes appear in
  `commutative_findings`.

- **`score` prints one screen line.** `screen: sha=… ni=… frame=… ld1184=…
  st1184=… coset=…` — identity, real instruction count, frame, float load and
  store traffic (whole-frame or narrowed by `--slot OFFSET`), and the ring coset
  relative to the target, with a caution when it is not identity. Every stage of
  one campaign wrote its own version of this line; none carried the coset, and
  none separated stores from loads at a slot even though the store count was what
  distinguished the winning kill from a rejected alternative.

- **A sampled sweep says what it never visited.** `SweepCoverage` records the
  space, the points visited, the stride, and the points excluded by a stated
  rule, and derives the vocabulary from them: *swept-exhaustively* or *sampled*.
  A campaign closed a family on a `step 8` sweep whose record said nothing about
  the other seven eighths. `experiment compose` carries the block and gains
  `--step N`, so a combination space larger than the cap can be sampled instead
  of abandoned.

- **`next` routes a count difference to `align` and a float run to `phase`.**
  The instruction-count blocker previously named `view`, which shows the
  alignment but not what the difference costs.

- **`force-rows` measures which object rows an allocator control owns.** A web
  number is not a location: it indexes a run-local table that does not survive
  into the object, and one campaign measured that neither "ucode record index
  implies program position" nor "allocator event order implies emission order"
  holds — a change confined to sixteen intermediate records 18% into the stream
  first moved the object at instruction 94, with 143 differing rows before the
  edited site. So the map cannot be read; it has to be measured.
  `decomp-workbench force-rows BASELINE.o FORCED.o --force p1:w9=c30` (and
  `force-rows-dumps` on retained objdump text) reports the rows that moved,
  grouped into runs with their classes. It runs no compiler — the two builds
  are inputs — so the join works for any control a reader can set. `--target`
  adds `compare_row`, the number `compare --json` publishes as `aligned_row`
  and `window --rows` accepts; `--gap N` sets how many matched rows may sit
  inside a run (default 3); a control that moves nothing prints `BYTE-INERT`,
  which is a result and not an empty screen. Runs come from the shared aligner,
  so a force that changes the instruction count is one run rather than
  "everything after the insertion", and the report says the count changed.
  `--force` is validated by the same parser the instrumented pass uses.
  `--json` emits `decomp-workbench-force-rows-v1`. Documented in
  `docs/compiler-instrumentation.md`; tests `tests/test_force_rows.py`.

- **Instrument records now name what they measure.** Three labels were read as
  claims the instrumentation does not make, and a campaign acted on two of
  them. `nocs` in a `p1dec`/`p2dec` record is the pass's *compressed*
  occurrence divisor, `((n - 2) >> 2) + 2`, not an occurrence count — so
  `trace-webs` no longer renders the economics as `save:X*nocs:Y=total:Z`, an
  equation shape that invited ranking by a product that is not "saving times
  uses"; the three numbers are printed as three named fields. `class` in the
  same record is the IR register class (integer versus floating point) from
  `regclassof`, *not* the save class — the class-1/class-2 verdict that decides
  whether a web is a colouring candidate at all is taken earlier and no shipped
  record reports it. And `instrument-ugen`'s `ADD` hook on
  `f_add_to_free_list` was measured as firing only inside `f_init_regs` (ten
  calls for a 4644-instruction procedure), so it sees the pool being built and
  nothing about the allocations that follow; `f_get_free_fp_reg` joins the hook
  table as `ALLOC_FP`, the live per-allocation floating-point hook, beside
  `f_free_reg`. Documented in `docs/compiler-instrumentation.md` and the field
  guide.

- **`window` prints named aligned rows, in the row numbering the tool already
  publishes.** Reading a row by number is the most common action in a register
  residue campaign, and it had no command: three stages of one campaign each
  wrote their own objdump-scraping script for it, and each invented its own row
  numbering — none of them the `aligned_row` that `compare --json` reports and
  `view` prints. A write-up saying "the gate is the `add.s` at row 863" was
  therefore one private script away from being unreadable.
  `decomp-workbench window TARGET CANDIDATE --rows 860-868` (and `window-dumps`
  on retained objdump text) shares the aligner and prints exactly those rows
  side by side, marking each differing row with `*` and carrying `view`'s web
  colouring and substitution annotations. `--rows` takes `N` or `LOW-HIGH` and
  repeats; matching rows are printed too, a range past the end is clamped and
  says so, and a range entirely past the end is reported rather than rendered
  as an empty screen. `--json` emits `decomp-workbench-window-v1` with `view`'s
  per-row keys. Documented in `docs/view.md`; regression tests
  `tests/test_window.py`, including that the rows `compare --json` names are
  the rows `window` prints.

- **`experiment review-mutation` gates a sweep winner on its diff, not its
  score.** An automated source-mutation sweep proposes edits by shape, and
  nothing downstream asks whether a variant is still the same program — the
  comparator answers "are these the same object". One recorded sweep grouped a
  local's occurrences by line proximity and renamed a whole group, producing
  two winners that compiled, scored better than their baseline, and were not
  valid C transformations: a group of pure reads rehosted onto a never-written
  local, and a top row that deleted a live first store. The new command prints
  the baseline-to-variant diff and flags a use that no earlier line writes to
  (`read-before-definition`/`definition-removed`, error, exit 1) and a removed
  write to a value still read (`write-removed`, warning; `--fail-on-warning`
  makes it fatal). Only identifiers the file declares are considered, and only
  shapes the mutation *introduced* — a baseline that already reads a local
  above its write is existing code. The report never claims validity: it does
  not parse, type, or execute C and builds no control-flow graph, and `proof`
  says so. The adoption rule is now stated as a hard rule in the campaign
  Agent Skill and the field guide (*A sweep winner is a hypothesis, not an
  edit*), and in `docs/campaigns.md`. New schema
  `decomp-workbench-mutation-review-v1`; regression tests
  `tests/test_mutation_review.py`, including both recorded failures and the
  cases that must stay silent.

- **`compare` explains a `raw` that exceeds `words`.** The summary line has
  always printed both counts and never said why they differ, and the answer is
  a floor rather than outstanding work: `words` excludes a word whose only
  differing bits are relocation-controlled, and a separately written
  `objdump -d` diff, which has no relocation table in hand, does not. On the
  recorded `object_interaction` pair that is 563 against 608, and the 45-row
  gap was read as unfixed literal-pool work for about an hour, across three
  campaign stages. Whenever the gap exists, a `raw-vs-words:` note now names
  the count, the class, and the consequence — a raw disassembly diff counts
  those words permanently, so `words = 0` is the honest gate, not a
  byte-identical dump. Nothing is renamed or removed and no count changed.
  Documented in `docs/object-comparison.md` and `docs/troubleshooting.md`;
  regression test `tests/test_literal_pool.py::RawFloorTests`, including the
  silence when the two counts agree.

- **The IDO 5.3 float temp ring is documented as four wide, because that is
  what ugen hands out.** The register tables already placed `f16`/`f18` in
  `fp-pool`, but every sentence around them called the pair "ambiguous" and
  said ugen's float free list "extends onto them under pressure". It does not.
  ugen initializes `ffree` with six entries — `f4 f6 f8 f10 f16 f18`, from
  `nf1 = 4` plus `nf2 = 2` — then withdraws `f16`/`f18` before the first
  allocation and never hands them out; an instrumented procedure allocated
  `f4`–`f10` 1460 times out of 1460, and uopt colors the pair as c28/c29. A
  campaign that read the initializer as the ring widened its own float-site
  metric onto two uopt colors, so every `f12`→`f16` coloring change counted as
  a closed temp site: about fifteen builds and one adoption path spent on
  phantom closures. The claim is now stated as the measurement in the field
  guide, `view --register-profile` help (`register_profile_evidence`),
  `docs/view.md`, the `temp-fifo-phase` on-ramp, and the agent-facing
  late-stage patterns reference, with the advice to assert a float ring's width
  rather than derive it from the initializer. No classification changed.
  Regression tests: `tests/test_register_eras.py` locks the four-wide
  `fp-temp`, the evidence string, and an `f12`-versus-`f16` row landing in
  `fp-pool` on both sides.

- **`audit-handoff` says which directory a relative root was resolved
  against.** A campaign read `handoff root is not a directory:
  .../bundle/bundle` from `audit-handoff bundle/` as the command appending the
  argument's basename to itself, and worked around it with absolute paths. It
  never did that: relative and absolute spellings of one tree resolve to one
  canonical root, and the doubled path was a working directory that had already
  moved into `bundle`. Both root arguments now resolve through one helper, and
  a failure on a relative argument quotes the argument as typed and the working
  directory it was resolved against — the two cases the old sentence could not
  tell apart. Regression test: `tests/test_handoff_audit.py`
  (`HandoffRootResolutionTests`), which audits `.`, `bundle/`, `./bundle`, and
  `../bundle` against the absolute spelling from two working directories.

- **The pool-versus-temp register split is now per compiler era, and the IDO
  5.3 one is corrected.** `view` classed `t0`-`t5` as uopt coloring-pool
  registers and `t6`-`t9` plus `s8` as ugen temps under the single profile name
  `ido53`. That table was inherited from earlier campaigns and had never been
  measured against a named release; on IDO 5.3 at `-O2 -mips2` it is wrong in
  both directions. Nine forced-color experiments, confirmed against an
  instrumented ugen, show uopt handing out only `v0`/`v1`/`a0-a3`/`s0-s8` and
  `f0`/`f2`/`f12-f24`, with `t0-t9` and `f4/f6/f8/f10` **always** ugen
  block-local temps. Three campaign agents read a `t`-register difference as a
  coloring-priority question because of the old table and spent variants on the
  wrong lever family.

  `--register-profile ido53` (still the default) now carries the probed split,
  including separate `fp-pool`/`fp-temp` lanes, with the temp tables in ugen
  free-list *ring* order (`t6 t7 t8 t9 t0 .. t5`, `f4 f6 f8 f10`) so a phase
  rotation stays a contiguous run of the table. The pre-probe table ships
  unchanged under the honest name `--register-profile unverified`, which is
  what a release with no probe of its own still gets — outputs for an
  unmeasured era do not change silently. `view --json` gained
  `register_profile_evidence`, so a probed table is never quoted as an
  inherited one.

  The field guide's temp-FIFO section now carries the 5.3 allocation law read
  from ugen source and validated with an instrumented binary — a per-class
  least-recently-freed ring re-seeded once per procedure, so the register at a
  site is a pure function of the alloc/free event sequence — together with the
  consequence that the fix dimension is the count of **class-crossing sites**
  rather than rows, and the warning that partial closure is *not* monotone in
  raw words. Which claims are 5.3-verified and which are 7.1-derived is stated
  where each is made. The shipped `phase-shift` example fixture was rebuilt to
  use era-correct registers.

- **Literal-pool accesses are compared by the slot they resolve to, not by the
  symbol that names it.** A decomp target and its candidate rarely anchor
  read-only data the same way: on the recorded `object_interaction` campaign
  the target names one external symbol per literal (`D_80052AA8`, addend 0)
  where the candidate emits one dense anonymous `.rodata` symbol with the slot
  in the addend. Every shared slot therefore rendered as a different
  `(symbol, addend)` pair, and 88 rows — 59 `lui at,0x0` against `lui at,0x0`
  and 29 `lwc1 $fN,0(at)` against `lwc1 $fN,K(at)` — were reported as
  relocation evidence against a pair whose pool accesses agree at every site,
  costing that campaign a work item with nothing to fix. `view` now resolves
  each relocated data reference and classes the row on the resolution: `pool`
  when the two sides read the same slot at the same width (not reported, like
  `displacement`), and the new `pool_layout` class and verdict when they do
  not. `--json` gained `pool`, `pool_layout`, `pool_resolution` and
  `pool_slots` on the view, and `pool_resolution`, `pool_matches`,
  `pool_layout_mismatches`, `target_pool_slots` and `candidate_pool_slots` on
  a comparison. Nothing was renamed or removed, and `aligned_total` is
  unchanged: on that campaign pair the 88 rows leave `aligned_diff_sites`
  (1953 → 1865) while the residual stays at 1865. Two resolution tiers are
  reported by name, because they answer different questions: `absolute` (both
  sides anchor on a section symbol, so byte offsets are compared directly) and
  `anchor-correspondence` (one side names each literal, so what is checked is a
  one-to-one slot correspondence at a constant displacement per anchor pair).
  Neither claims the two pools hold the same bytes.

  *Behaviour change to know:* a site where both objects name the **same**
  symbol with **different** addends used to be `relocation` and is now
  `pool_layout` — the addend is the source's choice, not the linker's, so it
  was never linker-controlled. A `lui` with no load under it in the compared
  window is still `relocation`: nothing in view says which slot it reaches.

- **Aligned row counts now say when they are not comparable across
  candidates.** `aligned_total` is computed against a per-candidate LCS
  alignment, so a candidate that forced the aligner to insert gaps is measured
  against a *different* subsequence of the target than a gap-free candidate is
  — and its row count can fall below a strictly better candidate's. On the
  recorded `object_interaction` campaign one such candidate reported 1435
  aligned rows against an 1865-row base while holding 2918 mismatching words
  and 1807 opcode mismatches, and a 257-build lever table was ordered on that
  inversion. Every scoring surface now carries the evidence: the summary line
  gained `opcodes=` and `gaps=` beside the existing `words=` and `raw=`,
  `compare`/`diagnose` print
  `caution: alignment inserted N gaps (M opcode mismatches) — compare
  candidates on raw words, not aligned rows` ahead of the numbers it retracts,
  and the JSON gained `aligned_insertions`, `aligned_deletions`,
  `aligned_gaps`/`gaps`, `alignment_comparable`, and `alignment_caution`. No
  existing key was renamed or removed. `rank` and `campaign` detect a result
  set containing both kinds and order it on `words` instead, with
  `ranked_by`/`mixed_alignment` in `rank --json` and a one-line caution in the
  terminal; a uniform set still ranks aligned-first exactly as before.

- **Symbol-table asymmetry no longer manufactures relocation rows.** A decomp
  target is disassembled from a stripped, positional object and its candidate
  from a symbolized one, so objdump renders the same word as `jal 0x0` against
  `jal 0 <fn>` and `b 0x485c` against `b 485c <fn+0x485c>`. `view` classed the
  spelling difference as a `relocation` row: on the recorded
  `object_interaction` campaign, 692 of 780 such rows were phantoms, and the
  real relocation differences were buried under them. Branch and jump
  destinations are now normalized on both sides before classing -- a
  self-branch by aligned row whichever spelling it arrived in, a relocated
  destination by its own relocation record rather than by whichever enclosing
  symbol objdump reached for. On that campaign's pair the relocation class
  falls from 780 rows to the 88 real ones, and thirteen moved branch offsets
  are now correctly counted as `displacement` rather than `constant`.

- **A command group printed without an operation now exits 0.** `cache` and
  `context` answered the question "what can this do" with argparse's
  required-subcommand error on stderr and exit 2, while their sibling groups
  (`object`, `scratch`, `trace`, `instrument`) already printed a map and
  succeeded. Printing a listing is the success path of discovery: a non-zero
  status there breaks `set -e` scripts and reads as a failure. Naming an
  operation or a `guide` topic that does not exist is still an error and still
  exits non-zero, and the whole set is now locked by a test.

- **A line-owned schedule verdict now routes to the command that fixes it.**
  `probe-lines --tie STATEMENT=LINE` (repeatable) compiles a fourth
  token-identical variant that reassigns one statement's line number via a
  `#line` pair and scores it toward/away against the target. Found live on the
  ssb64 80379070 campaign, where three one-slot-early defs were each cured by
  tying their line to the store-head's line (4 sites toward, 0 away, in a
  single probe run). The probe no longer stops at proving ownership: every
  verdict now prints `next:` routing — an unscored probe is told to score
  itself, a scored tie is told whether that assignment was the one, and a
  negative result is sent to `guide g0-schedule-probe` instead of a dead end.
  The `line-assignment-probe` playbook's on-ramp names `probe-lines` and
  `--tie` for the first time, so a `schedule` verdict reaches the flag without
  a second command. The tie is refused when it names a blank line or a
  preprocessing directive (neither carries a statement to reassign) or the
  same statement twice, and the report records the `ties` it ran with plus its
  `next_steps`, so a run is reproducible from its own JSON.

- **Field guide lever 28: alias a local to take it out of the allocation
  contest.** Every other allocator lever adjusts what a web *costs*; `if (&x);`
  changes what the compiler is *allowed* to do — an aliased local's post-call
  reads can never join a register web, so the variable leaves the coloring
  contest and frees the register it was holding, at zero instructions. Found on
  an SSB64 blit function whose ROM packed ten callee-saved values into nine
  registers: no reweighting could seat the tenth, and aliasing the one that
  belonged in memory reproduced the ROM's callee-saved map exactly. Ships with
  its companion construct (two source variables over one home), the direction
  rule (alias the memory half), and its measured boundaries: the mark's
  *placement* is a tuning axis worth real words (140 head / 131 `j`-loop / 106
  innermost on `func_ovl8_803787C0`, all at zero instructions — sweep
  innermost-first and score it), it does not compose with identity-arithmetic
  anti-folding, and frame size counts homes rather than locals. The symptom is
  machine-detectable, so it is now surfaced rather than only documented:
  `trace-globalcolor` annotates a `split`/`no-color` decision whose `regsleft`
  is exhausted, and a `desired-forbidden` color barrier says the register is
  taken rather than underpriced.

- **Two more measurements from the same campaign.** Lever 2 records that accom
  lineage emits `a + b` with its operands reversed relative to source order, so
  a swapped-operand `addu` hunk under a non-cfe frontend is a free source fix
  rather than an allocation problem. Lever 26 records the pad slot: splitting an
  existing local to hold a vacated stack slot moves compiler-temp offsets while
  keeping the frame exact, where deleting a dead local moves the same offsets
  and drops the frame.

- **`view` and `view-dumps` accept `--show-all`.** The field guide and the
  `diagnose` footer have always advertised `view TARGET.o CANDIDATE.o
  --show-all`, but only `diagnose` and `check-scratch` defined the flag; on
  `view` it was an argparse error. The flag now lives with the other aligned-
  view presentation controls, so every command that renders hunks accepts the
  same spelling. One declaration serves three renderers that do slightly
  different things with it, so each command's help text states what its own
  `--show-all` does: `diagnose` also drops its differing-site filter, and
  `check-scratch` renders nothing without `--view`.

- **Exactness now has a disciplined cleanup phase.** `experiment
  inspect-source` inventories suspicious statics, empty controls, and cancelled
  arithmetic without calling them dead. `experiment compose` applies bounded,
  exact-text transformations across mechanism families, emits a validated
  campaign sidecar, caps combinatorial growth, and prints the next command.

- **Function matches no longer hide translation-unit collateral.** `object
  collateral` compares all in-scope section sizes and contents, including
  zero-fill `.bss`, plus relocation and symbol tables. An optional selected
  function separates `outside-selected-function` changes from a general TU
  mismatch; project link/ROM verification remains the final gate.

- **Allocator trace comparison separates identity from outcome.** Paired web
  reports now compare the ordered decision kind, natural color, and assigned
  color independently of semantic-web fingerprints. Identical decisions with
  partial semantic alignment are reported as carrier substitution, not false
  identity. The SSSV case study, field-guide lever 27, packaged Agent Skill,
  and redistributable composition example carry the complete workflow.

- **Scratch acceptance now measures the zero-score boundary it claims.**
  `check-scratch` separates linked-function exactness, raw instruction-word
  identity, and relocation symbol/addend identity. Its JSON calls the result a
  `decomp_me_score_proxy_exact`, not a site fact, and a direct-symbol versus
  struct-member relocation can no longer pass the proxy merely because both
  spellings link to the same address. The obsolete missing-final-newline
  warning was also removed: decomp.me's language-aware source boundary already
  supplies a safe separator.

- **Allocator comparisons now expose uncertainty instead of manufacturing
  alignment.** Coverage uses the union of unique fingerprints, ambiguous webs
  prevent an `aligned` claim, and empty captures report `no-evidence` with a
  nonzero command status. Natural and forced colors, interference producers,
  unavailable-cost sentinels, formation chronology, decision order, and
  source attribution remain separate facts.

- **The forced-color oracle can test a measured interaction in one controlled
  build.** `oracle force` accepts a validated comma-separated force set,
  rejects duplicate phase/web controls, and records the baseline-to-forced
  instruction delta as object-level role evidence. It does not promote that
  evidence to source attribution or source reachability.

- **Copy/coalescing traces have a conservative parser and a visible command.**
  `trace copy-decisions` reports coalesce-versus-temporary outcomes and
  directly bracketed pass transitions. Hash buckets, statement IDs, and bit
  numbers remain explicitly run-local and collision-prone; comparison aligns
  only by observed stack home and ordinal. The command is now present in group
  help and shell completion.

- **Frame recovery and campaign handoff retain the useful diagnostic state.**
  Object reports distinguish observed physical save-slot bytes from the
  remaining frame, route allocation-exact/wrong-frame results to a dedicated
  playbook, compact large experiment grids, and visibly recover stale
  experiment metadata from manifest/source provenance instead of silently
  dropping it.

- **The SSSV endgame is recorded with its corrections, not as folklore.** The
  [case study](case-studies/sssv-func-802963D0.md) documents why one visible
  register bijection required a multi-web lifetime composition, why allocator
  formation/economics/decision order are distinct, and why a locally
  linked-exact archive still scored 99.89% until its relocation target matched.
  Source distributions now include the linked case-study directory instead of
  shipping documentation with dead relative links.

- **Public proof repositories now have a pre-push gate.** `handoff audit`
  checks relative Markdown and inline-code paths, absolute user paths, files
  present locally but absent from Git, and dependencies in another declared
  project root. It reproduces the SSB64 `threshold4` failure directly: the
  referenced README existed locally but was untracked, so a public clone could
  never follow the integration instructions.

- **Scratch UX now treats the frontend as an identity, not a nickname.**
  Bundles can record display label, canonical compiler ID, language, and preset
  separately; generated instructions explicitly set Preset to Custom before
  choosing the compiler. `check-scratch` reports the frontend and expected
  driver and uses `src.cxx` for old-C++ line identity instead of hardcoding
  `src.c`. This catches the `IDO 7.1` preset/`ido7.1_c++` compiler confusion
  that made valid `extern "C"` source fail under `cfe`.

- **Current C++ scratch exports load directly.** decomp.me now names their
  members `code.c++` and `ctx.c++`; `check-scratch` accepts that pair (plus
  `.cc`, `.cpp`, and `.cxx`) and normalizes it internally instead of falsely
  reporting that `code.c` and `ctx.c` are missing.

- **Line-layout guidance is frontend-specific.** The campaign skill now keeps
  cfe splice behavior separate from NCC/EDG statement attribution and asks
  schedule investigations to test splices, physical-line ties, and repeated
  `#line` markers independently.

- **Toolchain fingerprints now measure switch lowering.** Redistributable
  dense-four and dense-five probes report comparison chain versus computed
  jump. Running the same backend through `cc`/cfe and `NCC`/EDG can now answer
  whether jump tables are disabled or merely cross a frontend threshold
  without relying on a function-specific compiler patch.

- **Frontend-lineage guidance no longer generalizes `cfe` to all of IDO.** A
  source-order sparse comparison chain can come from IDO 7.1 EDG C++ even
  though `cfe` sorts the same switch values. The skill now also requires
  inspection of the actual phase command and intermediate before treating a
  removed driver flag or a frontend's representative-C printer as a real
  Cfront-style compilation path.

Everything here descends from one falsification: a community member matched
SSB64 `unref_800036B4` with no `#line` directive after this project helped
publish the claim that no natural layout could reach it. The claim had been
scoped, silently, to one statement order and one statement per physical line.

- **Lever 25: line-number ties by splicing.** cfe numbers statements by
  *logical* line, so the numbers a natural layout produces are non-decreasing
  but not strictly increasing — ties are free, via same-line placement or
  trailing-backslash splices, and a block's closing brace plus the statement
  after it can both be tied back to the block's first line. Field guide,
  `guide lever 25`, playbook ordering, and the line-assignment-probe doc all
  route to it; the full arc (290 → 120 → 4 → 0 with `#line` → 0 natural) is
  [a case study](case-studies/ssb64-unref-800036B4.md).

- **`check-scratch` now reports line-splice hazards in `code.c`.** An intact
  statement-level splice is load-bearing for exactly these ties and does not
  survive whitespace-trimming editors, formatters, or some paste paths — the
  failure is a regressed score, not an error — so it is listed for re-checking
  after every paste. A backslash followed by trailing whitespace, which looks
  tied but compiles untied, is a warning. Macro continuations are excluded.

- **`python -m decomp_workbench` works.** It failed with "No module named
  decomp_workbench.__main__", which reads as a broken install rather than a
  missing convenience, in every environment where the console script is not
  on PATH.

- **The skill and its references now carry the campaign-strategy lessons.**
  Scope every published negative to the space actually searched; treat a
  variant that fixes a subset of the residual as a new baseline for layout
  levers even when its own score is dominated (this match was two edits from
  variants already on disk); keep dominated variants and say where they live;
  and credit the falsifier prominently when a claim falls.

## 0.4.0 - 2026-07-31

Everything in this release descends from one campaign: SSB64 `drawbitmap`
(decomp.me scratch EqDZe), taken from a years-old structure-mismatch to a
byte-exact ROM rebuild. Each entry names the failure it encodes.

- **A `schedule` verdict can now be tested against statement lines instead of
  against compiler versions.** The one documented next step for
  `verdict=schedule-mismatch` was a `-g0` rebuild (lever 3), which is vacuous
  for a project that already builds `-g0` -- and the reader who runs it, sees
  nothing move, and concludes the compiler must be exotic has been sent to a
  dead family by the tool. One campaign spent hours there: IDO 5.2, 5.3, 6.0,
  7.1 and MIPSpro 7.4.4, every `as1` flag and pipeline model, all producing
  identical output.

  The mechanism that actually owned that residue is now lever 23: cfe takes
  each statement's source line number from its *preprocessed* input, and
  uopt/ugen treat a statement line boundary as a scheduling barrier at `-g0`
  as well as `-g3`. On SSB64 `drawbitmap` (1479 instructions) preprocessing the
  TU with IDO's external `acpp` instead of cfe's internal cpp took 59
  schedule-swapped words to zero, with no other change.

  `decomp-workbench diagnose ... --candidate-listing LISTING.s` reads the
  assembly listing ugen wrote for the candidate (`cc -K` keeps it, `ugen -l`
  writes it) and reports, per schedule-divergent site, the `.loc` statement
  lines of the instructions involved -- so `N of M sites sit at statement-line
  boundaries` is a measurement rather than a guess. A boundary majority
  promotes `playbook=line-assignment-probe` in the footer. Sites the listing
  cannot attribute are printed as unmapped and excluded from the majority
  rather than counted either way, and a `schedule` verdict with no listing is
  told the option exists and where the file comes from.
- **`probe-lines` turns the campaign's decisive experiment into one command.**
  Token-identical line-reflow of a preprocessed TU (split long multi-statement
  lines; a blank-line global shift as the control) proves or refutes
  line-assignment sensitivity in minutes, and with a target supplied reports
  the emotionally important number: how many divergent sites moved toward the
  ROM. See `docs/line-assignment-probe.md`.

- **`context lint` catches the guard that kept drawbitmap unmatched for
  years.** An `#if`/`#elif` whose identifiers are all undefined evaluates to a
  constant nobody intended (`#if BUILD_VERSION >= VERSION_J` is TRUE when both
  are undefined: `0 >= 0`). The lint evaluates the cpp expression subset,
  classifies `always-true-by-absence` as HIGH, and `check-scratch` now runs it
  over ctx+code -- along with two new decomp.me concatenation checks (a ctx
  that ends without a trailing newline, and symbols defined in both ctx and
  code). Lever 24 routes structure verdicts here.

- **New `score` and `matrix` commands replace the hand-rolled scoring
  snippet from the SSB64 drawbitmap campaign.** The operator rewrote the same
  ~30-line objcopy/window/mask/compare routine roughly ten times by hand, and
  it broke twice doing so: a hardcoded function offset went stale when a
  translation unit changed, and IDO's stripping of local (`static`) function
  symbols made a symbol lookup return nothing, which a downstream tool then
  read as "100% different." `score` windows the candidate function through
  the symbol table (`--function`) or, for a stripped local, between the two
  visible symbols around it (`--between`), masks relocation words from
  `objdump -r` into a separate "relocation floor" rather than counting them
  as diffs, and checks repeatable `--control` functions so a lever that
  changes something it must not touch marks the whole run `CONTROLS BROKEN`.
  `matrix` runs a batch of pipeline variants from a JSON spec, hashes each
  one's scored function bytes, and clusters identical hashes into lettered
  attractors -- the analytical device that caught a compiler-era sweep
  silently collapsing eleven differently-flagged outputs into byte-identical
  results during the same campaign. See `docs/score-and-matrix.md`.

- **Campaign ledgers no longer carry the target ROM's instruction text.** The
  schema used to ask for it: every diff site recorded `"target"` (the
  disassembly) beside `"target_word"` (the 32-bit word), so writing a correct
  ledger and writing a redistributable copy of the game's code were the same
  act. Two such ledgers from a Mickey's Speedway USA campaign reached a public
  remote with 126 sites apiece -- enough to reconstruct 129 of one function's
  146 instructions -- and undoing it took a history rewrite.

  Redaction now happens at the serialisation boundary (`append_ledger`), which
  is the single place a comparison becomes a file. The in-memory `Comparison`
  is untouched, so the terminal diff, the HTML report and every diagnosis path
  show exactly what they showed before. What lands on disk keeps only what the
  ledger is for: a 16-bit salted `target_digest` (lossy by construction, ~2^16
  preimages per digest -- but see the retraction below, the property *does*
  depend on the salt staying secret), a `target_opcode_masked` word with every
  operand field zeroed for at most the first three sites of each list, and
  `target_register_count` in place of the target's register names. The candidate side -- the operator's own
  compiler output from their own C -- is untouched.

  Salts live in a `<ledger>.salt` sidecar, never in the ledger, so a leaked
  ledger carries no rainbow-table shortcut with it. `tests/test_ledger_redaction.py`
  is the regression test.

- **Redaction hardened after review, and two claims corrected.**

  Site records are now filtered through an **allow-list** (`SITE_KEEP`) rather
  than a list of banned keys. A deny-list made the wrong promise: the incident's
  leak lived in the per-site records `compare` emits, so a *new* target-side
  field added upstream would have been carried straight to disk, and no test
  could have caught it -- the fixtures are hand-written and would not contain
  the new field either. Unknown keys are now dropped by default, with their
  names (never their values) recorded under `dropped_fields`.

  The claim that "the security property does not depend on the salt staying
  secret" was **wrong** and is retracted. It assumed a uniform prior over
  instruction words; at a diff site the record deliberately keeps `candidate`
  and `candidate_word` in full, which narrows the target to a small set of
  plausible variants, and against a small set a known-salt 16-bit digest is an
  exact-match confirmation oracle. The salt is load-bearing; the 16-bit width
  is the second, independent defence for sites with no such constraint. Treat
  `<ledger>.salt` as sensitive.

  Resuming a campaign whose ledger predates this change now prints a warning:
  new records are redacted, the old ones in the same file are not, and the file
  as a whole remains ROM-derived.

  Also corrected: `append_ledger` is the only place a **ledger** record is
  written, not the only place a comparison becomes a file. `--html` on `view`
  and `diagnose` renders target assembly rows into an HTML report. That export
  is opt-in and lands where the operator names it -- a real mitigation, not a
  redaction -- and it is now documented as a known second instance of the class.
  **`force_spec` is a third**: each aligned web it records carries
  `target_register`, which names a register in the target. Same class, same
  handling -- operator-named, opt-in, not something to commit -- and it is now
  recorded here rather than only in a comment at the point of use.

- **The sweep is now actually recursive, and the claim now matches the code.**

  "Recursive default-deny" was, on execution, recursive over `dict` and `list`
  and default-deny over keys spelled `target` in lower case. Six bypasses were
  demonstrated by driving `redact_record` directly, each writing the target's
  instruction text into the output while the redactor reported success:

  - a nested dict under an **allow-listed** site key -- `redact_site` copied
    surviving values with a shallow dict comprehension, so
    `{"candidate": {"target": "lw\t$v0,0x10($sp)"}}` was emitted verbatim;
  - a payload in a **tuple** -- `model` keeps tuples through
    `dataclasses.asdict`, and the sweep entered lists only;
  - a payload used as a **mapping key** -- only key *names* were ever
    inspected, never key content;
  - `Target`, `TARGET`, `_target` -- the match was a case-sensitive
    `startswith`;
  - instruction text containing a `/`, which `_is_path_like` accepted as a
    filesystem path (real `objdump` source-interleaved output qualifies);
  - 3000-deep nesting, which raised an uncaught `RecursionError` out of the
    middle of a campaign.

  All six are closed and each has a regression test. The sweep now enters
  `dict`, `list`, `tuple`, `set` and `frozenset`, examines keys as well as
  values, requires keys to be shaped like field names, matches target-naming
  keys case- and prefix-insensitively, re-sweeps allow-listed values, and caps
  depth at `MAX_DEPTH` (64) with a new `RedactionError` instead of unwinding.
  `_is_path_like` now requires a value with no whitespace at all, since
  instruction text always has a separator and a path does not.

  **The claim is also restated where it was overstated.** `append_ledger`'s
  docstring said the ledger "cannot carry the ROM's instruction text at all".
  It cannot carry it *under a target-named field*, at any depth, in any
  container. It can still carry a target instruction stored under an innocuous
  key name or as a bare list element, because nothing here reads string
  contents. That residue is documented at the function, at `_sweep`, in the
  module docstring, and here -- and it is why ledgers stay gitignored rather
  than merely redacted.

- **The resume warning now reads the whole ledger.** Its docstring said it
  "scans the file"; the default capped at 4096 lines, so an unredacted record
  on line 4097 of a long campaign produced silence. It now streams every
  record by default, and when an explicit `scan_lines` cap is given and reached
  it says how far it got rather than implying the file was fully examined.

## 0.3.1 - 2026-07-30

- The bundled `n64-decomp-campaign` Agent Skill caught up with the tool it
  ships in: it now routes agents through the guided next-steps footer and the
  `guide` command instead of past them, mandates a known-match harness proof
  before any target comparison, adds the frontend-lineage escape hatch (a new
  `references/frontend-lineage.md`: impossibility-first discipline, the
  fingerprint-atlas method, dispatch-construct discrimination, and what
  alternate-frontend evidence does and does not establish), counterweights the
  spelling experiments with the field guide's dead-families table and the
  line-placement lever, extends the evidence ladder with the two
  frontend-provenance rungs, and names the lever-19 clean negative as a
  legitimate terminal result.

- The README shows the product: an ANSI-faithful SVG of a real fixture
  diagnosis under the tagline and a screenshot of the self-contained HTML
  report at the `--html` mention, both generated from shipped fixtures.

## 0.3.0 — 2026-07-30

Every verdict now ends in an address: the matching field-guide levers, the
command that prints them, and both answers to "do you have an instrumented
toolchain?". Around that, three more themes — input safety, so a comparison
never reports a confident verdict about two unrelated functions; visualization
parity, so an exported report and a bounded terminal carry the same evidence as
a full screen; and the documentation that joins a screen to a source edit.

- Added `decomp-workbench guide <topic>`. It prints the field guide's own
  sections for a playbook (`forced-color-oracle`), either verdict vocabulary
  (`register-permutation`, `allocation-mismatch`), or a lever number (`19`),
  from a copy that ships inside the package — no checkout and no network. Every
  `next:` footer now names the matching levers with a one-line action each and
  the command that expands them, and any playbook whose advice mentions a
  trace, a probe, or an oracle gives both answers to "do you have an
  instrumented toolchain?", so the reader without one is told which source
  levers to spend instead.

- Added [From verdict to edit](docs/from-verdict-to-edit.md), the walkthrough
  from a diagnosis on screen to the source change it implies, and a glossary of
  the field's vocabulary in the documentation index.

- Symbol selection now falls back to a unique case-insensitive match, at the
  parser and in `dump_object`'s objdump retry: Pascal-era frontends (`upas`)
  fold identifiers to lower case, and comparing those objects previously
  required an `objcopy --redefine-sym` round-trip. That retry and the
  missing-symbol evidence pass below are one objdump call, not two.

- New documentation from the SSB64 frontend-lineage campaign: alternate
  authentic frontends (`docs/alternate-frontends.md` — accom/ccom/upas
  inventory, invocation recipes, cross-generation ucode handoff, and the
  fingerprint-atlas method), field-guide levers 20-22 with two new dead
  families, and field notes (`docs/field-notes-2026-07-30-ssb64.md`)
  including an open comparator report: exact matches occasionally render a
  vestigial `aligned_schedule` residual.

- Fixed a missing-symbol error that blamed the build instead of the typo.
  `objdump --disassemble=NAME` that matches nothing succeeds and prints an
  empty stream, so the "defines:" list built from it announced `no symbols`
  about an object that plainly defines the function the reader misspelled — on
  real `.o` files, the primary path. A single unfiltered second pass now
  supplies that list.

- Stopped a coarse verdict from guessing a lever family. `allocation-mismatch`
  dumped `pool-position`'s seven levers even though the same two streams make
  `view` say `phase-shift` or `register-permutation`, whose levers are 14-16
  and 17-19 — a guess that contradicted the sentence above it telling the
  reader to run `view` because *it* names the family, and that leaked into
  `--json` and the HTML payload beside a `view.next` that disagreed. The
  verdict now names all three families with the `guide` command for each and
  picks none, led by the sentence saying why it cannot.

- `--width` no longer truncates the `next:` footer. Guidance wraps on word
  boundaries with an indented continuation, so a bounded terminal keeps the
  dead-family warnings instead of the setup sentence that preceded them.

- Added four one-line explanations where the vocabulary is first used: what a
  web is, what LCS buys, what the `pool` and `temp` lane classes are, and how
  to read the signature in causal order — plus a pointer to
  `--explain-keys`. The three in-tool notes are removable with `--terse`.
  `--html` now renders each lever as its own runnable
  `decomp-workbench guide N` snippet.

- Made the HTML report carry the evidence it claimed to. It is rebuilt from
  the same view model the terminal renderer consumes: a sticky verdict bar,
  register lanes with the divergent slot outlined, one linkable
  `<section id="hunk-N">` per hunk with context and divergence row classes, a
  per-row substitution cell whose colour swatch links to its web, and a `Webs`
  table linking each bijection to every hunk it explains. Lanes, hunk grouping,
  webs, and the `t7->t8 [w1]` annotations previously existed only inside the
  collapsed JSON blob, which is still there. Still one self-contained file with
  no script and no network.

- Fixed four comprehension defects in the terminal rendering. The verdict is
  bolded and coloured by family (green for exact, one hue per mismatch family)
  instead of being the only plain token beside a bold-red explanatory sentence,
  and `compare`/`compare-dumps`/`rank` gained the `--color` they never had, so
  batch triage can be colourized. `--width` now wraps a row's annotation to a
  continuation line instead of silently cutting a second web tag. Every
  non-matching row is annotated, in or out of the hunk being printed, so a
  context row in a known web no longer reads as an unexplained `register` site.
  The lane caret names its two units: `slot=5 aligned_row=12`, replacing
  `divergence=5 index=12` on screen **and in `--json`**, because one vocabulary
  across both audiences is the point of the metric registry.

- Added the highest-leverage fact to the header. A compact
  `webs: w1 t7->t8 x2, ...` line prints above the hunks, and the substituted
  register token inside the disassembly now takes its web's colour, so the
  annotation says *which* registers moved and the text says where.

- An unknown command now names itself and points at `decomp-workbench
  commands` instead of printing argparse's forty-odd-name `(choose from ...)`
  catalogue.

- Refused to report a confident verdict about two unrelated functions.
  With no `--function` and exactly one differently-named symbol on each side,
  `compare`, `view`, `diagnose`, and `rank` now print a warning ahead of the
  verdict, carry it in `--json`, and say which option fixes it. A multi-symbol
  input is still the documented whole-section mode and stays quiet.

- Made the novice path legible. The bare program name welcomes and exits `0`
  instead of printing a 44-command choice wall and exiting `2`; the usage line
  is one word plus a pointer to `commands`; the `commands` footer teaches the
  same flat spelling as README and START_HERE; `--symbol`/`--function` says
  what omitting it means; `docs/README.md` defines IDO, asm-processor,
  ugen/uopt, and decomp.me, which are also glossed at first use.

- Sharpened two error messages to the standard the census-key error sets.
  A missing symbol lists what each input actually defines, states that names
  are case-sensitive, and links the troubleshooting section; an objdump
  `file format not recognized` failure names the likely cause before quoting
  objdump's own words underneath.

- Put the trace back where the documentation always had it.
  `allocation-mismatch` now sends the reader to `view`/`diagnose` and the
  field-guide levers first, and gates the globalcolor/UGEN trace on those
  levers being exhausted *and* an instrumented toolchain already existing. The
  `pool-position` and `temp-fifo-phase` footers lead with their source-only
  branch for the same reason, and `pool-position` now says up front that it is
  one of three unresolved allocation families rather than implying a decision
  the verdict did not make.

- Gave every verdict an on-ramp. The `next:` footer of `compare`, `view`, and
  `diagnose` now keeps its expert content and adds the matching field-guide
  lever numbers with a one-line action each, the literal
  `decomp-workbench guide <playbook>` that prints them, and — for every
  playbook whose advice names a trace, a probe, or an oracle — both answers to
  "do you have an instrumented toolchain?", so the reader without one is told
  which source levers to spend instead. The new `guide` command accepts a
  playbook, either verdict vocabulary, or a lever number, and prints the field
  guide from inside the installed package with no checkout. A lever whose
  section is not in the shipped revision degrades to its one-line action rather
  than failing, and a missing document still answers with the one-liners and
  names where the full text lives.

- Main now identifies itself as `0.3.0.dev0` instead of reusing the published
  `0.2.0` identity for a substantially different development build.

- Completed the common diagnosis journey. `diagnose`/`diagnose-dumps` render
  exact comparison truth plus the decisive aligned mechanism evidence after
  loading each input once; `check-scratch --view` reuses the imported
  comparison. Terminal width/pager controls and self-contained accessible HTML
  reports preserve the same evidence, and every explicit output refuses to
  overwrite.

- Added a durable campaign cockpit. Runs create an identity-checked manifest
  and append-only ledger under `.decomp-workbench/` by default; `campaign
  status/note/resume/export` preserve the best trajectory, failures, active
  hypothesis, object basins, family collapse, and exact-stop state.
  `decomp-workbench-experiment-v1` sidecars validate deterministic parameter
  assignments and selected instruction regions. Cache status, dry-run prune,
  recoverable cross-filesystem trash, and collision-safe restore complete the
  state lifecycle.

- Added calibrated compiler-research adapters without redistributing compiler
  inputs: real-copy `toolchain init/calibrate/status`, section/relocation/symbol
  fidelity, scheduler `DKWB-SCHED-V1` records and hash-pinned external
  profiles, original/static pass differential, behavioral fingerprint
  microcases, cross-revision lineage, relocation-alias evidence, mandatory
  unedited replay calibration, project-visible work roots, and bounded process
  artifacts.

- Productized the allocator oracle. `oracle plan` always reports both p1/p2
  namespaces and plans only measured or explicit non-forbidden colors;
  `diff` aligns semantic web provenance rather than numeric IDs; `force/sweep`
  use the campaign engine and require an intact ready toolchain; `status/export`
  reopen persistent, ledger-idempotent evidence. Forced exactness remains
  explicitly causal evidence, never a source match.

- Added semantic allocator and source provenance views: stable web
  fingerprints, forbidden-color neighbor attribution, virtual/final stack-home
  ownership, and `trace-source` joins through retained preprocessor markers and
  `.file/.loc` directives while preserving ambiguous line matches. Runnable
  synthetic oracle, source/listing, scheduler, and complete experiment-grid
  examples are executed by documentation tests.

- Hardened the evidence boundary found during final review: selected-region
  scores now use LCS-aligned residual sites; allocator details and interference
  edges are phase-qualified; an exact forced build is causal only after a
  successful non-exact control; relocation aliases preserve kind and
  cardinality differences; short section tails and undecodable compiler bytes
  remain observable; and toolchain/cache operations preflight collisions
  without deleting or partially restoring another process's files.

- Standardized automation on one versioned JSON document for success and
  failure, including argparse errors; added a compact journey command map,
  non-breaking task-group aliases, and generated Bash/Zsh/Fish/PowerShell
  completions. CI now runs actionlint, the full suite on macOS, targeted
  Windows process/filesystem contracts, and wheel/sdist installation smoke
  tests in addition to Python 3.10–3.14 and strict static analysis.

- Compiler execution now has one lifecycle contract across `check-scratch`,
  `compile-rank`, and `campaign`: a 120-second per-candidate timeout by
  default, explicit environment and working-directory controls, and
  process-group cleanup so a wrapper's assembler or search child cannot
  outlive a timeout. Campaign ledgers and JSON summaries record the deadline;
  site-faithful scratch reports also record wrapper identity, cwd, explicit
  environment, duration, and timeout.

- Hardened scratch handoffs. ZIP members must come from one flat root instead
  of being silently combined by basename, expanded directories refuse nested
  or symbolic-link content instead of ignoring it, checksums must be real
  hexadecimal SHA-256 values, and impossible browser scores are rejected
  rather than rendered above 100% or below 0%.

- Standardized examples and campaign state on repository-root commands and
  `.decomp-workbench/`, taught `doctor --cache-dir` to inspect a project's
  actual cache, schema-versioned the doctor and scratch-check JSON reports,
  and expanded documentation tests to execute redistributable trace examples.

- Added `doctor` and `check-scratch` for the human handoff around decomp.me.
  `doctor` reports local readiness, validates an export or workbench bundle,
  and prints the exact shell-quoted next command. `check-scratch` safely reads
  a downloaded ZIP/directory without extraction, shows the browser score only
  as context, and compares the exported target/current objects (or retained
  objdump text) with the workbench's aligned oracle. Its optional compile mode
  reproduces the site's `ctx.c` + `#line 1 "src.c"` + candidate composition,
  supports explicit environment/cwd/timeout controls, and can retain the exact
  composed source and object for audit.

- `--objdump PATH` is now authoritative. A misspelled explicit path fails
  immediately instead of silently selecting a different host executable.
  `doctor` also verifies the selected reader against an exported `target.o`
  when available and reports large local campaign caches without modifying
  them.

- Fixed adjacent instruction swaps being misclassified as allocation or
  structure when unrelated relocation addends differed elsewhere. The shared
  aligned view now uses relocation-masked schedule identities, so the
  redistributable final-two-`li` fixture reports `aligned_schedule=2` and sends
  the user to the scheduling evidence ladder.

- Corrected an unsafe claim in runtime guidance, tutorials, postmortem, field
  notes, and the packaged Agent Skill: a region collapsing under `-g0` proves
  debug metadata participates and as1 can reach the target order, but does not
  prove source correctness. The eventual `vsprintf` match was the
  counterexample—a freer scheduler had rescued the wrong source topology.

- `CDX_FORCE` no longer kills the compiler when it names a color the web's
  interference mask already forbids. The instrumented pass **declines** the
  force, records
  `[CDX] force_declined phase=p2 site=dec proc=11 web=300 color=2 reg=v1 forbidden=0x…`,
  and lets the natural coloring stand. Six oracle probes across three campaigns
  could not be run at all because that case raised `SIGABRT`, and a sweep that
  hit one lost every result after it.

  The record prints whether or not `CDX_LOG` is set, and that is the semantic
  change worth knowing: a declined force is now *visible* and distinguishable
  from a force the pass never saw, so "the object did not change" no longer has
  two meanings. `site=dec` and `site=color` name which of the two force points
  declined. Forcing the split path (`p1:w9=s`) is never declined — no color
  mask can forbid it.

  The mask decode is now one rule in two places: `color_is_forbidden` in
  `globalcolor.py` and the generated C, checked against one table in the tests,
  anchored on the recorded observation that `forbidden0=0x7f800000` means
  exactly c1–c8. `trace-globalcolor` reports `forbidden_colors` on every
  allocator web, so a force sweep can be planned from one logging run instead
  of discovered one abort at a time.

- New `--census KEY=VALUE[,KEY=VALUE...]` on `compare`, `compare-dumps`,
  `view`, and `view-dumps`: assert values the command already reports and read
  the answer as an exit code — `0` when every predicate held, `3` when one
  failed, `2` when the question itself was wrong. One `PASS`/`FAIL` line prints
  per predicate, `--json` carries them under `census`, and the option is
  repeatable.

  Campaign agents rebuilt this filter at least seven times in one day as an
  objdump-and-regular-expression layer outside the workbench, and at least one
  of those copies keyed on the wrong instruction. `3` is deliberately not `1`:
  `--fail-on-mismatch` already means "this candidate is not a match", and a
  variant can be exactly the shape you are filtering for and still not be the
  match.

  Any key the command reports can be named, including the deprecated JSON
  spellings while they are still emitted; keys whose value is a list or an
  object are refused rather than silently compared; values compare by the
  reported type, so `exact=true` reads a boolean and `frame=-0x80` reads an
  integer in any base. Predicates are validated against the registry before the
  inputs are read, so a misspelled key in a long sweep costs one process rather
  than one compile. `--explain-keys` gained a fourth section for the keys a
  command wraps around a report (`accepted`, `acceptance_basis`, and the census
  results), which had never been explained anywhere.

- `compare` and `compare-dumps` now report the LCS-aligned residual beside the
  positional one, and **candidate ranking moved to it**. `aligned_total` leads
  the summary line; `aligned_structural`, `aligned_schedule`,
  `aligned_register`, `aligned_constant`, and `aligned_commutative` split it by
  mechanism in `--json`, in `campaign --json-summary`, and on a human line
  under the verdict. `rank`, `compile-rank`, `campaign`, and the object-basin
  order sort on `aligned_total` first, with the positional `words=` count as
  the tiebreaker.

  This was the most expensive tool gap of the dp64 campaign day: positional
  counting shifts on every insertion, so the candidate one edit away reads as
  a cascade while a candidate with a dozen unrelated allocation differences
  reads as close. It misranked candidates in six separate campaigns — a
  one-hunk 11-word variant sorted below a five-site 5-word variant, and two
  variants tied at 95 words that the aligned split (10 structural versus 8)
  separated immediately. The shipped insertion fixture reproduces it in
  miniature: `words=11`, `aligned_total=1`.

  The counts come from `view`'s alignment, not from a second aligner in
  `compare`: campaigns rebuilt an ad-hoc LCS ranker six times in one day, and
  two implementations of one idea would eventually print different numbers
  under the same name in two commands. `words=` is unchanged and still the
  matching oracle — a match is `exact=true` with `words=0`, and aligned rows
  that are relocation-controlled or displaced by an insertion are outside the
  residual by design, because neither is a difference a source change owns.

- Wrote the documentation for the person who arrives with one almost-matched
  function and no idea what the next command is. Three new narrative pages sit
  above the reference material and are the first thing the README points at:

  - `docs/START_HERE.md` — ten minutes, in order: run `compare`, read the
    verdict, run `view`, read the lanes and hunks, take the lever from the
    `next:` footer, change one thing, repeat. Every command in it runs against
    the shipped fixtures with no ROM, compiler, or toolchain, so a reader can
    follow the whole loop before touching their own project. It answers the
    three questions people actually arrive with, where they arise: you do not
    isolate the function (`compare` and `view` are symbol-scoped against your
    normal full-TU build, and isolation changes codegen); you do not need an
    agent or a permuter (the verdict names the mechanism and the footer names
    the lever — the permuter is a hypothesis generator, not a solver); and
    traces are the last resort for one verdict class, not the first step.
  - `docs/field-guide.md` — the IDO codegen levers as a playbook. Nineteen
    entries, each with the diff signature that points to it, the C before and
    after, why it works, the function it was proven on with the measured
    effect, and the verdict or playbook name that routes here. Plus the dead
    families, which are worth as much as the levers: `a|b` versus `b|a`,
    declaration-order permutation, bare discarded expressions, and the
    permuter on varargs.
  - `docs/walkthrough-30-near-matches.md` — batch triage for a backlog rather
    than a function: classify the whole pile with `compare --json` and
    `view --json`, rank by verdict class rather than word count, clear the
    one-variant classes first, then structure, then the register lanes, with
    portable POSIX shell for each step.

  The docs index is now a journey rather than an alphabet, every entry carries
  a "read this if...", and the compiler-internals pages are explicitly marked
  as the last resort they are. `tests/test_doc_commands.py` extracts every
  documented command line that reads a shipped fixture, runs it, and checks it
  against the output the page promises — so a command line that stops working,
  or a verdict that changes wording, fails the build instead of misleading a
  reader.

- Gave `view` and `view-dumps` the same option behavior as every other command
  that selects one function: `--symbol`/`--function` conflicts are rejected
  instead of resolved last-one-wins, and `--explain-keys` prints the registry.
  Both options now come from one shared module rather than a copy per command
  module. `view` and `view-dumps` also moved next to `compare` and
  `compare-dumps` in the help listing, where the inputs they read put them.

- Unified the two schema registries the merge left behind. The aligned view's
  keys now live in the shared metric registry beside the comparison and
  campaign keys, so `--explain-keys` explains `view` and `view-dumps` too, and
  a test asserts the registry and the view's output are one set in both
  directions: a key can neither be printed without an explanation nor
  explained without being printed. The view keeps its own namespace, because a
  spelling it shares with the comparison registry (`target_instructions`) is an
  aligned count there and a positional count here.

- Deduplicated the commutative-operand rule: `compare` and `view` shared two
  independent tables and two independent predicates that disagreed about the
  two-operand multiply form, so one residual could be `commutative-order` in
  one command and `register` in the other. Both now classify through
  `compare.commutative_swap`, and a table-driven test asserts the two commands
  name the same mechanism for a three-operand `or`, a two-operand `mult`, and
  the non-commutative controls.

- Kept every candidate a campaign actually ran: stopping on an exact match now
  waits for and records the candidates already in flight instead of discarding
  their objects and their ledger records, and a candidate that raises an
  unexpected error is recorded as a failed candidate rather than ending the
  run.
- Required a matching instruction multiset for `schedule-mismatch`, so a
  reordering that also moves a register is no longer reported as "not
  allocation".
- Escalated compiler termination from `SIGTERM` to `SIGKILL`, kept compilers in
  the workbench's session on Python 3.11+ (own process group, still attached to
  the terminal), and scoped the group-termination guarantee to POSIX in the
  documentation; Windows remains best effort.
- Gave the instrumented pass the same force-key grammar the workbench
  validates, so a partially formed control such as `p1:w9` or `p1:w9=zzz` is
  refused instead of silently forcing nothing.

- Established the packaged bundle under `src/decomp_workbench/skills` as the
  only skill tree, with a test that fails if a root-level `skills/` directory
  exists without matching what `install-skill` ships.
- Made the globalcolor instrumentation phase-explicit and self-describing:
  records carry `phase=p1`/`phase=p2`, `CDX_FORCE` keys must be phase-qualified
  (`p2:w55=c2`) and are rejected with both namespaces named — by `campaign
  --env` before a compile and by the pass itself — colors are decoded to
  machine registers in every record and in `trace-globalcolor`, and a
  symbol-named `CDX_PROC` now prints a procedure index table instead of
  silently selecting procedure 0.
- Documented the instrumentation fidelity gates as section-scoped
  (`.text`/`.rodata`/`.data`/relocations/symbols), because stock IDO under
  `-g3` is not file-level reproducible.
- Gave the campaign runner ownership of the processes it starts: compilers run
  in their own process group and are terminated with their children when a run
  fails or is interrupted, so a spawned search or assembler cannot outlive its
  campaign.
- Stopped campaigns on the first exact match by default (`--no-stop-on-exact`
  sweeps the whole grid) and removed the repeated target disassembly, so a
  variant costs one compiler run and one objdump run with the comparison in
  process.
- Split three verdicts out of the volume-based classes, each with the field
  lever attached: `constant-mismatch` (audit the flag/enum against the
  assembly), `commutative-order` (compound assignment, not the allocator), and
  `schedule-mismatch` (statement grouping and the `-g0` diagnostic).
- Unified human labels and JSON keys behind one metric registry and added
  `--explain-keys`. `words=` is now `"words"` in JSON; the previous long-form
  keys (`word_mismatches`, `candidate_instructions`, `candidate_frame_size`,
  and the rest) are deprecated and still emitted beside the canonical keys for
  one release.
- Reported every differing site regardless of verdict. `--show-diff` no longer
  prints only register groups, so a literal difference counted in `raw` can no
  longer be missing from the displayed evidence.
- Accepted `--function` as a second spelling of `--symbol` on every command
  that selects one function, and rejected conflicting values instead of
  silently keeping the last one.

- Added `view` and `view-dumps`: the aligned mechanism view. Two-pass LCS
  alignment over the opcode streams, per-hunk classification
  (structural/schedule/register/constant/commutative/relocation), per-class
  register lanes that include the matching instructions, a
  `prefix-exact@N` / `state-divergence@class:slot` signature line, grouped
  register webs, and lever guidance chosen by the dominant class. Aligned
  counts replace positional counts, which multiply a single insertion into a
  phantom cascade. Two anchorings are scored against each other so neither a
  run of repeated opcodes nor repeated instruction text can mispair the
  streams, a shifted branch offset is reported as `displacement` rather than
  claimed as byte identity, and `phase-shift` requires a real rotation cycle
  instead of the constant offset that any small register swap satisfies. Both
  commands accept reduced objdump text, `--json` uses the same keys as the
  human labels, and `--report-regs` emits per-aligned-row register operands for
  matching rows too.
- Completed a release-quality UX pass: packaged the Agent Skill with the
  distribution, added a safe installer, clarified comparison proof scope and
  cross-ROM JSON acceptance, hardened focused web lookups, and selected the
  true best representative for every campaign basin.
- Added the portable `n64-decomp-campaign` Agent Skill for Codex and Claude
  Code, including installation guidance and reusable DKR/SF64 campaign
  evidence, IDO patterns, and reproducibility practice.
- Added action-oriented comparison verdicts, relocation-only raw-difference
  explanations, and a deliberately separate cross-ROM structural-evidence
  mode.
- Made register diagnostics portable across GNU objdump dialects that do or do
  not print MIPS register names with a `$` prefix.
- Added object-basin reporting to campaigns, so source variants that compile
  to the same function bytes are visible in both terminal and JSON summaries.
- Added focused `trace-globalcolor --proc ... --web ...` inspection with
  trustworthy callee-saved register names for the pinned compiler profile.
- Published a final-function campaign guide covering the Hartley, Titania, and
  Aquas evidence patterns and the safe next action for each residual class.
- Refocused the documentation on decompilation problems, command outputs, and
  support boundaries.
- Replaced project-specific research narratives with concise workflows,
  operating principles, and a documentation index.
- Excluded unreachable zero alignment padding after a selected MIPS function's
  return delay slot from object and retained-dump comparisons.
- Added deterministic, upload-neutral decomp.me scratch bundles with copied
  target/context/source inputs, settings, checksums, and manual-use guidance.
- Added a five-function Castlevania 64 walkthrough and complete scratch inputs,
  including exact matches and three small scheduling/code-generation puzzles.
- Documented the supported IDO 5.3 and 7.1 workflow matrix and the narrower
  version boundary of the pinned deep-uopt instrumentation profiles.

## 0.2.0 — 2026-07-27

- Made exact comparison relocation-aware and conservative about missing or
  unknown relocation kinds.
- Added redistributable objdump-text fixtures and symbol filtering.
- Added parallel, cached campaigns with explicit provenance and JSONL ledgers.
- Added structured ugen trace parsing, FIFO validation, and logical-value
  reconstruction.
- Added `CSAVE`/`CUP`/`[CDX]` globalcolor reporting.
- Added hash-pinned, anchor-validated uopt globalcolor and alias profiles,
  including safe profile composition and alias-state reports.
- Added retained ugen→as1 listing replay.
- Added task-oriented guides, CC0 licensing, and clean-wheel validation.
- Published the workbench as a standalone repository with end-to-end developer
  workflows, centralized troubleshooting, and root-level CI.
- Added Python 3.10–3.14 CI, strict type checks, formatter enforcement, and
  release-distribution smoke tests.
- Fixed list-address filtering in FIFO replay and accepted non-finite
  globalcolor costs emitted by compiler diagnostics.
- Corrected the phase-two globalcolor web identifier used by decision logs and
  force controls, and required force controls to select one procedure.
- Added a reproducible instrumentation fidelity microcase and release
  validation record.

## 0.1.0 — 2026-07-26

- Initial object comparison, ranking, sequential candidate compilation, and
  generic ugen instrumentation package.
