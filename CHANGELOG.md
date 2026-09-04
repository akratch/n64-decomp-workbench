# Changelog

Narrative release notes with the design reasoning behind each change are kept
in [design notes](docs/history/design-notes.md).

## Unreleased

### A pool-rotation lever, and the length gate in front of it

- **`diagnose` names two new classes, `pool-rotation` and `pool-population`,
  and reads the pool lanes' *lengths* before either.** Equal lengths are the
  precondition for calling a colour-only residual a rotation; unequal lengths
  are a web population difference no colour lever reaches.
  `overlay43FilterImage` (Mickey's Speedway USA, 2026-09-03) was recorded as
  "one cyclic pool rotation" while its lanes were 18 slots against 15, and
  forcing the rotation to the target's colours raised opcode mismatches from 8
  to 10. The block prints that counter-example where the gate fires.
- **The owning sweep is named from the CDX colouring records, or not at all.**
  p2 visits webs in ascending web number with the lowest free colour and its
  save cost is inert; p1 is repeated max-save selection with the web number
  only as a tie-break (**L83**, **L84**). Neither law says a rotation is
  thereby reachable: `overlay40FadeRecords` is 21 p2 decisions with pool lanes
  equal at 27 slots and is recorded unreachable, its load definition sitting in
  a different web partition, which no visit order produces. Two disassemblies
  cannot say which sweep owns a colour, so with no capture the block asks for
  `CDX_LOG=1` instead of guessing. `--ladder` is now read twice — as an itable for the declared-local
  count, and as a colouring log for the sweep — and a capture carrying only
  the colouring records is reported and kept rather than refused.
- **For a p1 tie it names the tie group; the direction is p2's, and is a
  reading rather than a lever.** The save and the members are records. The
  direction follows from lowest-free-colour, which the captures establish for
  p2 alone, so it is offered for a p2 pair, withheld for a p1 one, and stated
  only for a two-register transposition with one coloured web on each side —
  and stated as a reading of the rule, because no recorded edit has reordered a
  pair. A tie is p1's tie-break and not by itself a lever: webs 13 and 22 tie
  at save 1.5 with identical interference records, do not interfere, and are
  not colour-reachable. A register two webs hold names no pair and asks for
  `CDX_DETAIL_WEB`.
- **`reachability` reports a recorded force experiment and never its
  absence.** New `--force-result` takes an oracle sweep JSON: `proven` at
  `words=0`, `unreachable` for a declined or instruction-adding force, null
  for a run that neither closed nor failed. On `overlay4UpdateObjectMotion`
  three pinned colours took an 8-word residual to `words=0` — a complete
  reachability proof that the function still does not match, which is exactly
  the distinction the field exists to draw.
- **No renumbering edit is named without the capture that confirms it.** Both
  spellings tried from the numbering model on that function were plausible and
  neither moved a web number, because cfe had already coalesced the store one
  of them depended on. The `needs` entry demanding a second capture is
  structural, not advisory.
- **Laws L83-L86**, the two sweeps' orders, the one spelling measured to move
  a web number (declare the truncated local narrow so the truncation happens
  at the store: the synthetic temp went from web 48 to 49, both threshold webs
  took the target's colours, 8 differing words to 3, reproduced
  byte-identically under the stock toolchain — its partner stayed at web 50, so
  the pair never reordered and the law claims no reordering) and four that move
  none. Field guide lever 44,
  `from-verdict-to-edit` §5a, and backlog item 16: plan the force experiment
  rather than leaving it to be typed.

- `instrument-drop-in` passes `--in-place` when a plan rewrites a source in
  place; the generated script previously stopped at its first step, leaving
  the old drop-in installed (found rebuilding the Mickey toolchain,
  2026-09-03).

## Unreleased

### Lever-block corrections from the first field test

Ten resident plateaus were diagnosed with the 0.8.0 block; three defects
followed, all of them the block claiming more than its evidence carried.

- **`temp-ring` named a family without checking the construct.** A pop count
  says which line to edit; each pop-cost rule was measured on one construct,
  and nothing checked that the charged line was it. `read-the-field-directly`
  was named for a line whose local holds a cast integer constant, and three
  spellings of the edit compiled byte-identically. `diagnose --source` now
  reads the charged line, `measurements.constructs_by_line` reports what it
  found, and a line holding no construct with a measured pop cost yields no
  family and a reason saying which construct it does hold. Without `--source`
  the class is still named and the family is not.
- **`stack-home` ranked on frame arithmetic and ignored the pool lane it had
  just printed.** On a six-line function with equal frames and one displaced
  home the frame-only rule named "reuse a dead local as the carrier", and no
  dead local existed; the pool lane's surplus web named declaration placement,
  which closed two stack constants and took the residual from 8 words to 6. The
  ranking is now lane evidence, then frame delta, then displaced-home count,
  stated in `STACK_HOME_RANKING` and in the docs.
- **A met catalogue proof was printed as a footnote.** `debug_text_width` got
  `none-known` with three `capture:` lines while `uopt-coalescing-tie-break`
  sat under `see_also` — and one build confirmed that proof byte-for-byte. A
  proof whose precondition the evidence meets is now the verdict:
  `lever_class=unreachable` citing it. Every proof gains a `precondition`
  sentence, printed under `see_also` as `applies when:` when it cannot be
  checked from two disassemblies.

The field test also confirmed the block's `none-known` on `func_8003A2C8` as
correct and useful — `permuter-target` plus the note that a target register is
ring-only is a measurement no hand lever can argue with — and lever 43 now
records that.

## 0.8.0 - 2026-09-03

### The lever diagnosis

- `diagnose` and `diagnose-dumps` gain a `lever` block: the concrete
  source-edit class a residual's evidence supports, with the evidence lines
  behind it, or the proof that no edit reaches it. Four classes, each read from
  a different input — `stack-home` from the two prologues and, with `--ladder`,
  a CDX frame ladder's declared-local count; `temp-ring` from `--ring-trace`'s
  pops per source line against the target's temp lane; `line-order` from
  `--emit-trace`'s line-order conflicts; `unreachable` from `--as1-trace`,
  where the key that decided a selection says outright whether the line lever
  reaches a block.
- Every edit family and every proof carries the function and date it was
  measured on, and the alternatives carry the discriminator that would select
  them instead. `edit_family` is null whenever the input that would name it is
  absent, and `needs` then names the capture that produces it: guessing an edit
  family from a residual's shape is how `overlay40UpdateEntries` acquired an
  "unreachable by statement placement" verdict a trace overturned the same day.
  `stack-home` is the exception the contract spells out, because its family is
  picked from the frame pair the disassembly already carries.
- Three `unreachable` sub-classes are catalogue entries printed under
  `see_also`, never as the diagnosis: nothing in two disassemblies
  distinguishes uopt's address folding, an argument/return coalescing tie, or
  the exhausted spellings at a pointer add. Each records what would reopen it.
- The block is a namespaced sub-document (`lever`, `lever_schema`) and is
  absent on an exact comparison, which has no residual to explain. Field-guide
  levers 40-43 and [from verdict to edit](docs/from-verdict-to-edit.md) reach
  each class from the screen in one step.

### Compiler laws L72-L82

- Eleven laws from an overlay lever cohort of seven lanes and 22 targets with
  measured work, 2026-09-02/03; the laws name 19 of them, plus one resident
  function outside the cohort. Seven say what an edit does: the declared block
  rounds to 8 so a declaration can be free (L72), the declared *count* moves a
  call-crossing home between frame regions (L73), an 8-byte aggregate declared
  last sits below the temp region and holds the frame (L74), a field read
  through a local and an index scaled twice each cost one ring pop (L76, L77),
  a pool-carried accumulate keeps a field in its web (L78), and a hoisted
  invariant carries the loop header's line (L80).
- Four say what no edit does, which is the expensive half: the exhausted
  spellings at a pointer add, and the one rewrite that moved its temp order
  but not to the target's (L75); as1's chain decided above the line key, with
  its leftover-node corollary (L79); uopt's address fold ignoring statement
  placement (L81); and an argument/return coalescing tie (L82). L79 records
  three different readings of where `besttime` sits in as1's chain — the
  hand-offs', this workbench's decoder's, and L59's, which omits it. Nothing
  shipped depends on which is right; improvement-backlog item 15 is where it
  has to be settled.

### One instrumented drop-in, and a check that it survived

- `instrument-drop-in` prints the reproducible recipe for a `cc` carrying both
  passes' profiles: the uopt CDX allocator profiles and the ugen free-list and
  emit-order hooks, with their hash gates, the run-time variables each is
  switched on with, the fidelity gates in the order they are run, and the
  scheduler trace that needs no drop-in at all. `--script` writes it as a
  runnable script it refuses to overwrite.
- `check-drop-in` scans built compiler binaries for each profile's injected
  markers and exits non-zero when one is missing. The claim is one-sided and
  the report says so: a marker present proves the profile was compiled in, a
  marker absent proves it was not, and neither proves it fires. A campaign lost
  its uopt CDX profile to a ugen-only rebuild and four analysts re-derived that
  from the same empty log over two days before anyone read the binary.

### ugen emit-order provenance

- `instrument-ugen --emit-provenance` hooks all 67 ibuffer emit helpers and
  `trace-emit` decodes the resulting `DKWB-EMIT-V1` records: per basic block,
  the order ugen wrote instruction records and the source line each carries
  into the assembler, plus the **line-order conflicts** — adjacent instruction
  records whose lines, not whose dependences, decide their order.
- This closes improvement-backlog item #3(b), which had been filed as
  unhookable. The premise was a category error: ugen has no instruction
  scheduler at all — no ready list, no dependence DAG, no delay-slot filler in
  its 431 named functions — so it has no slot to report. The scheduler is
  `as1`'s and already traceable via `cc -Wa,-R`. What ugen owns is that
  scheduler's *input*, and the emit helpers are discrete single-entry
  functions, so a helper hook reaches it after all.
- The lever this exposes: a loop-invariant address hoisted into a preheader is
  stamped with the loop header's line, so any initialiser above the loop wins
  as1's minimised line key with no dependence edge behind it. Putting the
  initialiser on the loop header's physical line removes the separation. Two
  Mickey's Speedway residuals whose handoffs had recorded the schedule as
  sourceless closed on it: `overlay40UpdateEntries` 44/46 → exact, and
  `overlay57HandleModeInput` → exact under relocation-masked comparison.
- `trace-emit` reports no slot, ready-list position or delay-slot occupancy.
  ugen does not decide them; the report's `proof` says so and points at
  `trace-scheduler --from-as1-r`.

### Evidence lifecycle and campaign memory

- Campaigns now preserve current, measured best, and accepted state as three
  explicit concepts. `campaign checkpoint` archives source/object pairs in an
  immutable content-addressed store; `campaign restore-best` refuses drift,
  creates a recoverable backup, and replaces atomically; `campaign accept`
  records an exact-by-default manifest pointer rather than relying on a loose
  winner file. Manifest reinitialization preserves these fields.
- `campaign dossier-add` and `campaign dossier-list` provide append-only,
  machine-queryable negative space. Canonical bounded records carry function,
  hypothesis, lever, result, outcome, do-not-repeat status, and evidence. IDs
  are deterministic over substantive contents, duplicates are refused, and
  reads recompute IDs so edited history cannot masquerade as the original
  experiment.
- `campaign readiness` rehashes a versioned target queue and separates
  promotion-ready, codegen-ready, relocation-identity-maintenance, and
  remeasurement work. A stale measurement never enters a source lane;
  plateaued work is eligible only for a new evidence-producing mechanism.
  Measurements must bind target/candidate roles to those exact artifact hashes.
  Relocation reports and their nested evidence are transitively hash-checked
  and their static synthesis and identity join are replayed.
- Every campaign manifest writer now shares the lifecycle transaction lock;
  immutable candidate metadata and measured object hashes are revalidated at
  checkpoint/acceptance, and restore refuses a destination changed mid-copy.
  Dossier recovery tolerates only an actually unterminated final record.

### Compiler-decision provenance

- `instrument-ugen` now stamps free-list events with a producer procedure
  ordinal. `trace fifo --ucode --symbol` maps that ordinal to the candidate's
  retained Ucode procedure name, binds optional candidate-object identity, and
  refuses mixed procedure scopes. The claim is intentionally candidate-only;
  no target allocator trace is inferred from machine code.
- `trace pre` adds a stable procedure/block/expression PRE and speculative-
  hoist decision contract with identity-aligned differentials.
  `instrument pre` is a source-hash-pinned, uniqueness-checked adapter for
  project-reviewed generated-uopt profiles and names the fidelity/positive
  controls required before a profile becomes evidence. No universal generated
  compiler patch is claimed.
- Scheduler records can carry emitted slot, source file/statement, decision
  reason, and the complete ready set. Profiles that declare
  `provenance_required=true` must emit the complete required subset; readers
  preserve it through reports/diffs, validate ready-set cardinality,
  uniqueness, and chosen-node membership, and count only complete events.

### Promotion proof contracts

- `reloc-surface --identity-provider` joins each exact object relocation site
  to a project-owned canonical namespace/module/section/offset identity and
  distinguishes resolved, unknown, and contradicted sites. The interface is
  declarative, so overlay atlas formats remain in their owning projects.
- `reloc-proof` composes but never conflates fallback-static relocation
  evidence and promoted-linked exact bytes. It rehashes reports and nested
  artifacts, replays static synthesis, the identity-provider join, and linked
  byte classification, and requires shipped-table corroboration, complete
  identities, a bound project range map, one owning section, the same target
  image, the selected candidate object, and an exact named linked range.
  Receipts are replayable; artifact identity is content-based, so timestamp-only
  changes do not invalidate them.

### The linked image as an oracle

- `reloc-surface`, `linked-compare`, and a `permute-doctor` that routes
  between them. A game whose code modules ship **unrelocated** patches every
  relocation site from the module's own table after the module loads, so what
  the image stores at a site is the record's stored addend, not an address.
  A translation unit cannot express that: it emits an ordinary reference to a
  placeholder symbol that has no address in this build, and every project's
  answer is a linker assignment giving that placeholder the shipped addend as
  its value -- hand-derived, per function, from the target's relocation table.
  That ritual, not the C, is what gates such a project's candidate pool, and
  while it is unresolved the permuter can never score zero on those functions
  either: the target names symbols the scratch cannot.

  `reloc-surface` generates the values instead. For a candidate whose schedule
  already agrees at the site, each is a pure function of the stored addends --
  `(synthetic_vma & 0xF0000000) | (imm26 << 2)` for a call, `(hi << 16) + sext16(lo)` for a
  pair, the word itself for an `R_MIPS_32` -- less the addend the object's own
  instruction carries, which is what lets one base symbol serve many field
  references. Inputs are the module's objects, a section map the host writes
  once (`decomp-workbench-module-map-v1`: module image range, section ranges,
  per-object text placement, synthetic VMA, and optionally the shipped
  relocation table), and the target image; outputs are a linker symbol block,
  an alias block, and `--audit` against whatever block a project already
  hand-wrote. It refuses rather than guesses: two sites demanding different
  values are a schedule divergence *at the site*, reported with both values
  and every conflicting site, because a link that succeeds on an invented
  addend is quietly wrong.

  `linked-compare` is the oracle that then applies. Given the image the host
  built, the target image, and each function's image range (`--range
  NAME:START:END`, or a `decomp-workbench-image-ranges-v1` file), it classifies
  every range `exact` / `text-exact` (the range agrees; collateral outside it)
  / `text-differs N words` / `size-differs` (different image lengths, or a
  range past the image), with the first differing offset inside and outside
  each range. No build orchestration: only the
  project knows how it builds, and the host-side loop is written out in the
  documentation rather than guessed at here.

  `permute-doctor --target-object` closes the loop by telling this case apart
  from L69's badly-configured scratch, which has the same symptom -- a search
  that finds nothing. When every `R_MIPS_26` site in the target names a
  symbol the candidate object does not carry, it warns that the score cannot
  reach zero and names `linked-compare`. `--candidate-object` is what makes
  that a measurement: a site naming the containing function is equally the
  shape of ordinary self-recursion, so the candidate is checked first, and
  without one the report says recursion is the other reading.

  The measurements behind all of it are Mickey's Speedway USA's: 1773/1773
  hand-written values reproduced with zero refusals, and a measurable
  candidate pool that moved from 110/279 to 150/279 once the surface was
  generated rather than hand-written. Recorded as **L71** on the IDO 5.3 laws
  page: the linked image is the only oracle for unrelocated-module code. See
  [The linked image as an oracle](docs/linked-oracle.md). Closes backlog #14.

## 0.7.0 - 2026-08-28

### Permuter sweeps and scratch fidelity

- `permute-sweep` and `permute-doctor`: a first-class driver for bounded
  decomp-permuter searches, with the scratch fidelity a transferable result
  needs. Every project ends up writing this batch loop, and each rewrite
  re-introduces the same three faults. The codegen flags are recovered from
  the project's own `make -n <object>` -- after touching the source, because
  a dry run prints nothing for an up-to-date object, and with backslash
  continuations joined, because make echoes a recipe whose flags commonly sit
  on the line that does not name the compiler. Any post-compile `objcopy`
  chain is replicated into the scratch's `compile.sh`, so the scratch object
  is the object the real link would get; passes that cannot be replicated are
  named in `recipe.txt` rather than silently dropped. `--stack-diffs` is
  always passed, since a normalized score reports a match for a spill at the
  wrong slot. The queue is ordered closest-first from a ranking with unranked
  functions last, launches are niced and gated on the load average where the
  host has one (a host without `getloadavg` is told the gate is inert rather
  than reported as idle), `--resume` continues a summary and retries the rows
  that errored, and `--extend-minutes` re-seeds only a search that was still
  descending when its window closed. Every tool the sweep starts owns its
  process group, so a search that runs out of time takes its `-j` workers
  with it instead of leaving them compiling through the next function. Promotion is out
  of scope by design: a scratch score of 0 is a candidate until the project's
  authoritative build says otherwise. `permute-doctor <function>` answers the
  three preflight questions -- real flags, replicated chain, a base that
  compiles to a finite non-zero score -- before an hour is spent on a
  function. See [Permuter sweeps](docs/permute-sweep.md).

- `permute-sweep` and `permute-doctor` now measure the scratch object against
  the object the project's own build produces, and repair it when they can.
  decomp-permuter's importer does not hand a translation unit to the compiler:
  it preprocesses it, and for every macro named in `[preserve_macros]` injects
  a stub definition of its own through `#pragma _permuter latedefine`, which is
  what lets the permuter permute inside a macro call. Where the stub expands to
  something the real header macro does not -- the N64 `gDP*`/`gSP*` display-list
  macros are the standard case -- the scratch compiles a different function, and
  every score measured on it describes code the build never emits (Mickey's
  `particles.c func_80041CE4`: a -136 frame in the scratch against -128 in the
  build). After each import the scratch's own base is compiled through the
  scratch's own `compile.sh` -- the one carrying the recovered flags and the
  replicated `objcopy` chain -- and compared with the project's object through
  the same object oracle `compare` uses, reported as `scratch_fidelity:
  identical | differs(N words) | unknown | unchecked` in the doctor, in the
  sweep's table, and in each summary row. The comparison is the function's own
  words rather than whole sections, because a scratch holds one pruned function
  where the project object holds a translation unit. A difference is a loud
  warning; `--require-fidelity` makes it a refusal, having spent the import and
  nothing else, and `--no-fidelity` skips the check. When the scratch differs
  and the importer did preserve macros, the import is retried through
  `[permuter] preserve_macro_modes` (default `["configured", "none"]`, and any
  other entry is a narrowing regex) and the first mode whose object is identical
  wins -- `none` giving up the ability to permute inside those macro calls,
  which is the right price for searching the object the build actually has.
  Modes that reach `import.py` identically collapse, a scratch that preserved
  nothing is not retried, and with no identical mode the smallest measured
  difference is kept. See [Permuter sweeps](docs/permute-sweep.md).

- `permute classify` (`permute-classify`): a sweep's `summary.json` now
  assigns each function a measured wall class instead of a hand-written one.
  Wall classes were argued from verdict prose, and the class that says
  "nothing will move this" has repeatedly been wrong -- expensively, because
  it is the class that routes a function away from a cheap search and towards
  a bespoke instrumentation build. `MATCHED` is `best == 0`;
  `P_STUCK_DESCENDING` improved on the base and either earned its extension
  or landed its best candidate in the final third of the window, and is the
  only class that routes to trace levers or a human; `P_STUCK_FLAT` never
  improved, or improved only in its opening minutes, and is the pool from
  which the case for deeper instrumentation is argued; `IMPORT_FAULT` never
  scored a base at all and routes to fixing the scratch, because a function
  nobody searched is not evidence of a wall. The report is a pasteable
  markdown table, or JSON under
  `decomp-workbench-permute-classify-v1`. To carry that, each sweep result
  now records `best_output_mtime_fraction` (where in the searched window the
  best candidate landed), `window_seconds` and `hit_cap` -- decomp-permuter
  overwrites its output directories, so nothing else keeps that timing. A
  summary written without the fraction is classed as descending rather than
  flat: absent evidence is not evidence of a plateau. See
  [Permuter sweeps](docs/permute-sweep.md).

- `ranking stamp` and `ranking check`: a closeness ranking now records the
  tree hash it was measured against, so a consumer can tell a measurement
  from a memory. A ranking decays within hours -- a function that has since
  matched is still in it -- and one campaign's snapshot was read as an
  ownership ledger long after it had stopped describing the tree. `stamp`
  adds one `stamp` key (tree hash plus `generated_at`) without reshaping the
  rows, and rewrites the file atomically; both ranking spellings are accepted,
  though a bare-list ranking comes back wrapped under `functions`, because
  JSON has nowhere to hang a key on a list. Re-stamping the same tree keeps
  the original timestamp, because a field refreshed on every run cannot say
  how old a measurement is. `permute-sweep` and `permute-doctor` check the
  ranking they were handed: a stamp that contradicts HEAD, or one that
  cannot be compared to it, prints a loud warning, an unstamped ranking gets
  a quiet note, and `--require-fresh` refuses to run on anything but a match.
  See [Permuter sweeps](docs/permute-sweep.md).

- A `[permuter]` project-configuration table, so a project states its
  permuter inputs once instead of re-deriving them per sweep. It holds no
  codegen flags on purpose.

- `[permuter] step_timeout_seconds` (default 600), one bounded policy for
  the scratch phase. The search window and the `make -n` recipe recovery were
  the only bounded things a sweep had, and the recovery's bound was a private
  120-second default nothing could reach: `import.py` and the fidelity compile
  each started a child with no deadline at all, and the fidelity check adds up
  to two of them per import mode per function, so a single hung compiler held
  a whole sweep open with nothing to show for it. `run_owned` could always end
  a process group on a timeout; it had never been given one here. The key now
  sets all three, which also raises the recipe recovery's deadline from 120
  seconds to the same configured value. A `make -n`
  that expires degrades to the fallback flags with the warning that says so;
  an import or fidelity compile that expires is an error for that function,
  naming the key that bounds it, and the sweep moves on.

### Build staleness

- A build-freshness guard on every comparison, and `check-staleness` for the
  hosts that wrap one. A comparison answers "are these two objects the same",
  never "is this object the thing my last edit produced", and the two are
  indistinguishable on screen: an operator confirming a match at ROM level got
  a silent **0 differing words** from a `build/` image that had never been
  relinked after the source edit, and the false match survived several verify
  cycles. `compare`, `compare-dumps`, `diagnose` and `diagnose-dumps` now
  state what they compared and when each side was built, ahead of the verdict,
  and `--built-from PATH` (repeatable) names the inputs those artifacts were
  built from. A compared artifact older than one of its inputs is refused
  before anything is disassembled, because the failure being guarded is a
  *false positive* -- a stale comparison does not look wrong, it looks like a
  match. `--allow-stale` downgrades the refusal to a warning printed above the
  verdict, and never suppresses the report. `--json` carries the whole thing
  as a namespaced `staleness` block with its own `staleness_schema`.
  `decomp-workbench check-staleness a b c` checks a chain named in build order
  without running a comparison at all -- every earlier path is an input to
  every later one, so a ROM relinked after its object but before the source
  was recompiled is reported stale against the source -- and `--sha256`
  records a content hash per artifact so a wrapper that keeps the report can
  tell a rebuild that changed something from one that changed nothing. Hosts
  can call `staleness.staleness_report(...)` directly. Two limits are
  deliberate: modification time is evidence rather than proof, which is why
  the escape hatch exists, and equal timestamps are not staleness, because a
  guard that fires on a fast build is a guard that gets disabled (the default
  tolerance is one second). A report only certifies what it read: a comparison
  run without `--built-from` compared nothing, so its block says
  `status: unknown` with `comparisons: 0` rather than `fresh`. See
  [Object comparison](docs/object-comparison.md#is-the-thing-you-compared-the-thing-you-just-built).

- `check-staleness --tolerance` takes `DEFAULT_TOLERANCE_SECONDS` as its
  default instead of a second hardcoded `1.0`, so tuning the constant cannot
  move the library's freshness verdict and leave the command's behind. It
  also refuses a negative window, which was never a stricter check: `-60`
  calls an artifact built thirty seconds *after* its input stale, and a
  reader who sees a good build reported stale learns to ignore the verdict
  entirely. Zero remains legal.

### Verdict routing and ownership

- `routing` beside every verdict, and a routing sentence on the verdicts that
  used to read as walls. A verdict names the *mechanism*; it has never named
  the **tool**, and readers filled that gap themselves: "interference-forbidden
  colour" and "list-scheduler slot-fill -- no source lever" were taken as proof
  that two functions could not be matched, a bespoke instrumentation build was
  funded to explain why, and a twenty-minute permuter run then matched both.
  `view`, `view-dumps`, `diagnose` and `diagnose-dumps` now print
  `routing=permuter-first|structural|import-fix|none` in the verdict header and
  carry it in JSON, and any allocation, colour, or schedule tie ends its footer
  with *no HAND lever found -- this is a permuter target; run the sweep before
  concluding a wall*, followed by the two commands that do it. `HAND` is the
  whole correction: what the analysis established is that no lever a human
  types into the C file reaches the residual, which is a claim about the lever
  set and not about the function. Lever 19 and the `forced-color-oracle`
  onramp were reworded the same way -- a clean forced-colour cascade is a
  stopping point for hand search, and a wall is recorded only after
  `permute classify` reports a measured search that was flat. This change is
  the additive v2 bump of both verdict schemas -- every existing key unchanged,
  `routing` the only addition -- which the ownership entry above then carried
  to `decomp-workbench-diagnosis-v3` and `decomp-workbench-view-v3` in the
  same release.

- `owning_pass` and `reachability` beside the verdict, so a residual names the
  compiler decision behind it and not only its shape. `routing` said which
  *tool* a residual belongs to; it still did not say **why**, and the three
  actionably-different cases hiding behind one register verdict -- a colourable
  tie a lever moves, a colour that is *forbidden* rather than underpriced, and
  a decision the instrument does not expose -- demand opposite responses. They
  were being separated by hand, one `CDX_FORCE` probe per function, on
  functions where the probe was always going to decline. `view`,
  `view-dumps`, `diagnose` and `diagnose-dumps` now print an `ownership:` line
  under the verdict carrying
  `owning_pass=cfe-spelling|rodata-load-form|stack-home-assignment|uopt-globalcolor|ugen-temp-ring|g0-scheduler|none|unknown`,
  `reachability=source-reachable|permuter-target|pass-owned|unknown`, and
  `ownership_basis=trace|heuristic|none`. The basis is never omitted: an
  answer read off two disassemblies and an answer read out of a compiler trace
  are different claims, and a screen that spelled them the same way would be
  inviting a reader to act on a guess as though it were a measurement.
  `globalcolor.pass_evidence` is the bridge that supplies the measured half --
  a declined force or a `regsleft=0` contest, the one fact two disassemblies
  cannot show. A `pass-owned` residual routes `permuter-first` like any other
  tie, because "no handle this evidence exposes" is a statement about the
  levers to hand and never about the function. Each ownership footer ends at
  the law for its pass. The schemas bump to `decomp-workbench-diagnosis-v3`
  and `decomp-workbench-view-v3`, additively: nothing was removed or renamed,
  and the three fields are the only additions.

- `diagnose --trace PATH`, with `--trace-proc N` / `--trace-web N` to scope
  it, so `ownership_basis=trace` is reachable from a terminal.
  `globalcolor.pass_evidence` was the producer of the measured ownership
  basis and nothing called it: every screen said `heuristic`, including the
  ones an operator was reading beside an instrumented-uopt trace. The scope
  arguments are the substance rather than a convenience -- a trace covers a
  whole compilation and a residual is one function's, so *some* declined
  force in the file is nearly certain and reading it as this residual's
  would manufacture a measurement out of an unrelated decision. The footer
  names the trace and the scope when the trace settles ownership, and says
  the trace settled nothing when it does not, because a silent `heuristic`
  after a `--trace` run reads as the trace having agreed when it was never
  asked. `examples/fixtures/globalcolor-declined.log` is a synthetic trace
  carrying both outcomes.

- Layout-aware verdicts: on `structure-mismatch` and `schedule-mismatch` --
  the two verdicts a block permutation lands on -- `compare` now runs the
  shift-tolerant aligner itself and reports the edit script, the moved-block
  count and rows, and `rows_away` beside `words`, in text and under `layout`
  in `--json`. One campaign candidate whose real edit script was a single
  relocated 29-row block reported 1,791 differing words and was ranked below
  strictly worse candidates. Documented as Trap 8 in `docs/metric-traps.md`.

- `view.__all__` exports the routing vocabulary -- `ROUTING_VALUES` and the
  four names it holds -- along with every member of the `owning_pass`,
  `reachability` and `ownership_basis` vocabularies and `routing_for`. They
  were public in every practical sense and missing from the one file that
  says what the module offers, so a consumer switching on `routing` could
  not get the names from it. A test asserts the property, not the list.

### Compiler laws and the `guide`

- Nine campaign-verified IDO 5.3 laws (L62-L70), from a whole-ROM
  decompilation rather than one procedure, several of which that campaign had
  to re-derive from scratch because they were nowhere on the page. L62 a float
  scalar's load form is decided by its value (rodata `lwc1` iff the low
  halfword is non-zero) and only that form joins the invariant-load group;
  L63 declaration order places a call-crossing spill, reconfirming L53 with
  the lever spelled out; L64 the integer temp ring is seeded
  `t6 t7 t8 t9 t0..t5`; L65 a folded redundant mask emits no instruction and
  still pops the ring once -- the phantom pop, usable in both directions;
  L66 a web feeding a call argument inherits that argument register at cost 0;
  L67 a comparison prints its copy-propagated variable first, so operand order
  is a readout and not a lever; L68 a jump table's bytes are the case mapping,
  and matching `.text` is not evidence the mapping is right. L69 and L70 are
  measurement laws about harnesses that lie: a permuter that finds nothing
  instantly is a setup fault (eight of twelve such verdicts were one wrong ISA
  flag in the scratch), and an isolated `cc -c` does not schedule like the
  project path (56 instructions against 58 on the same source).

- `decomp-workbench guide laws ERA LAW` prints one law instead of the whole
  page. Footers had been citing individual laws for a release before the
  command could answer one, so a reader who pasted the citation got the
  document and had to find the law by hand. `L64`, `64` and `law 64` are one
  address; an unrecognised number names the range that era carries rather than
  printing everything. Every lever family whose mechanism is written down now
  ends its `guide` output with that command, and every verdict that names an
  owning pass ends its footer with it, so a residual points at its law.

- `docs/compiler-laws/ido-7.1.md`: the IDO 7.1 law book, 19 laws from the
  SSB64 `func_ovl0_800CEF4C` campaign (one word to `exact=true`). `as1`'s
  `peep_reg` copy propagation and `update_ctnt`'s six-gate cross-block carry
  (a fact reaches only a single-predecessor fallthrough, then is filtered
  against the taken target's live-in mask); `as1` mutating its content state
  before it deletes redundant code, which is what makes a zero-instruction
  barrier possible; ugen's branch-to-next eliminator saturating at **two**
  conditional branches; the synthesized jump-table range guard whose subtract
  is an atomic tree child; uopt's ghost edge from an empty pure conditional
  and its `num + 1` depth-first block order; the goto-pair fallthrough
  inversion and opposing-arm ballast; the globalcolor priority model and the
  dead-read dial arithmetic; per-use-site FP literal pools; the 24-way phase
  provenance matrix (ugen+as1 determine the basin, cfe/uopt do not); and the
  extracted-target literal-pool defect. Each law carries its evidence tier,
  its probe artifact, and the claim it falsified. The two clauses that
  shipped provisional (L9's owning pass, L11's survival condition) were
  closed the same day by directed probes -- a `cc -K` cfe-output capture
  and a nine-variant reaching-definition grid -- and their receipts are
  inline; no clause on the page is provisional.

- `guide laws ido71` serves that page, and the era token now accepts the
  document and prose spellings (`ido-7.1`, `IDO 7.1`, `7.1`) as well.

- Field-guide levers 34-39 and two playbooks (`copy-propagation-barrier`,
  `dispatch-layout`): the conditional branch-to-next barrier, goto-pair parity
  steering, opposing-arm ballast, Duff-nesting for switch body layout, the
  `x ? x : x` selector temp, and the IDO 7.1 read-count dial as arithmetic.
  Eight IDO 7.1 families joined the dead-families table.

- Law L66 (call-argument colour affinity) carries a `Scope` line marking it
  a single observation. Its T1 receipt is one trace of one procedure -- one
  call, one argument register, one web whose only consumer was that argument
  -- and with no scope it read as general IDO 5.3 behaviour. The scope names
  the neighbouring cases nobody measured, which are where this cost and
  L58's forbidden mask meet.

### Traces, streams and phase capture

- Trace commands name a binary pass-boundary stream instead of failing on
  decode. `capture make` leaves the Ucode uopt hands ugen and the Binasm ugen
  hands as1 on disk beside the textual traces, under the compiler's own
  temporary-file names, so nothing about a name says which is which; feeding
  one to `trace-summary` produced a raw `UnicodeDecodeError`, and feeding one
  whose record words happen to be small integers produced something worse -- a
  clean decode and *zero events*. `trace.read_trace_source` is now the single
  reader behind `trace-summary`, `trace-fifo`, `trace-alias`, `trace-a71`,
  `trace-scheduler`, `trace-source`, `copy-decisions`, the `allocator-*`
  commands, `oracle` and `diagnose --trace`. A stream is refused by name, with
  its record count, the decoder that reads it (`ucode window` / `binasm
  window`), and the Tier-2 instrumentation that produces a textual trace
  instead. Framing decides it, delegated to `streams.detect_format`, so a
  trace command and `stream diff` cannot disagree about what a file is; a NUL
  or a tenth of the file in control bytes, with no diagnostic line anywhere,
  is what separates a stream from text that merely decodes. A file that only
  *contains* binary is recovered rather than refused: its diagnostic lines are
  parsed, its replaced bytes counted, and a `warning:` on stderr states both.
  The trace commands still decode no records -- a stream carries records, not
  the decisions that produced them, and printing a record window under a trace
  command would blur the Tier-1/Tier-2 boundary this was meant to clarify.

- `capture make <ido-root> <dest>` generates an arg-preserving wrapper
  toolchain around any IDO root: one POSIX shell wrapper, phase-named symlinks
  for ugen/as0/as1, the untouched binaries kept as `<phase>.real`, and a
  self-alias so a version-directory compiler root keeps working.

- `capture runs <dest>` lists collected runs with phase, exit status, argv
  roles, and retained stream sizes; the run layout matches the ad hoc original
  so previously collected captures still read.

- `pass replay-ugen <ucode>` replays a retained or patched Ucode stream through
  stock ugen and as1 with a capture run's exact argv shape -- including the
  symbol table ugen mutates in place -- and verifies the object against the
  capture's own; `--require-identical` makes that fidelity gate an exit status.

- `ucode patch` performs record-framed insertion, replacement and deletion with
  `--fresh-label` allocation above every label the stream uses, and refuses to
  write a stream the decoder cannot read back.

- `ucode window` / `binasm window` print the decoded records around a byte
  offset or `#record-index`, detecting the stream format from record framing.

- `stream diff` aligns two Ucode or Binasm streams by decoded record and
  reports the first divergence plus a shift-tolerant side-by-side edit script.

- `docs/phase-capture.md`: the whole journey -- capture, decode, window, diff,
  patch, replay -- with the cef4c conditional-branch barrier as the worked
  example and a claim table per rung.

- `pass ucode` statically decodes retained IDO binary Ucode switch dispatches,
  including the selector expression, XJP range/default/case labels, and dense
  case-target table.

- `pass binasm` statically inspects one fixed-record ugen-to-as1 boundary,
  summarizes IDO 7.1 `-peepdbg` copy rewrites, and turns exact barrier-probe
  cells into source-search families without overstating upstream survival.

- `trace a71` parses and diffs the compact IDO 7.1 final-color stream,
  decoding priorities and masks while warning that web IDs are run-local and
  the producer's historical `refs`/`defs` fields are invalid.

- `instrument-ugen` now stamps the register each temp allocator **returned**,
  not only the request it was handed, exposing both temp-ring pop sequences.
  `f_get_free_reg` (integer) and `f_get_free_fp_reg` (fp) take a class/hint
  descriptor in `a0` (a recorded trace showed values such as 96, 176, and 208
  that no object uses as that register) and return the chosen register in `v0`;
  the old hooks logged `a0`, so a study of "which register does the n-th temp
  get" -- the exact question a temp ring poses -- read the request, not the
  result. `f_get_free_reg` was not hooked at all, and `f_alloc_reg` (`ALLOC`)
  never fires, so the integer temp ring was invisible. Return-site hooks now
  emit distinct `ALLOC_GP_RESULT` / `ALLOC_FP_RESULT` records carrying `v0`,
  and the entry `ALLOC_GP` / `ALLOC_FP` records are kept so a request that
  resolves to an already-live register (a phantom pop) is visible as such.
  Validated on Mickey `func_80012574`: the integer stream reads back as
  `t6 t7` and the fp stream is the `$f4 $f6 $f8 $f10` ring rotating in dequeue
  order (`36 38 40 42`, ugen's `32 + n` fp numbering), confirming
  `FP_LOCAL_RING` from the pop side.

- `instrument-ugen` stamps ugen's current source line (`line=`, the value
  `f_warning` prints as `line %d`) on every free-list record, so a temp-ring
  pop ties to the source construct that consumed it. Two pops sharing one line
  is a phantom pop -- e.g. a redundant `entry->blue & 0xFFFFU` on a `u8` field
  allocates a temp that is then folded away, advancing the ring one phase; the
  line that gains or loses a pop is the exact statement to edit. Confirmed on
  Mickey `func_8001A154`, where line provenance located the phantom pop
  (removing the mask realigns the whole field-copy ring to the target).

- `trace` decodes ugen's unified register space: a free-list `reg` of `32`-`63`
  now names an fp register (`36` -> `$f4`), while integer results stay their
  conventional names (`14` -> `t6`) and a value at or above `64` stays numeric
  so an `ALLOC_*` request descriptor is never misread as a register. Every
  `ALLOC_*` event normalizes to the `allocate` action (previously any `ALLOC_*`
  beyond bare `ALLOC` fell through to the raw tag name).

- `parse_binasm` and `parse_ucode` accept bytes or a path, so a patched stream
  held in memory and a retained capture file use one entry point.

- The Binasm decoder names five record families it used to leave unknown --
  positive-index label definitions, jump-table entries, section switches,
  procedure and stream-header records -- and frames a float literal's ASCII
  digits as payload instead of word-decoding them into invented families. Each
  record now carries `evidence`: `calibrated`, `inferred`, or `none`.

- `ucode patch` refuses an edit placed between a Binasm float literal and its
  own ASCII payload records. That boundary frames like a record boundary and
  is not one -- the literal declares how many bytes follow it -- so an
  insertion there was read as the literal's digits and silently vanished while
  the decode-back check passed, because any 16-byte multiple decodes as
  Binasm. The check now compares record framing on both sides of the edit
  (`result.framing_preserved`, `result.framing_error`), which also catches a
  spec that turns its own neighbours into a literal's payload.

- Stream format detection no longer reads a zero-padded Ucode stream as
  Binasm. Every all-zero 16-byte window decodes as an `empty` Binasm record,
  and counting those as recognized let a tail of padding clear the 75% gate.

- `pass binasm` only calls a record `calibrated` in the form a probe
  established. A family is matched on the high half of its opcode word, and a
  record whose low half was nonzero -- a variant nobody has observed -- was
  reported as calibrated evidence *with those bits deleted from the output*.
  They are now rendered as `flags=0x....` and the record reads `inferred`; an
  instruction record whose opcode is not one of the as0-probed set, and a
  `.set` mode number no probe named, stop counting as calibrated too.

- `pass ucode --json` declares its report schema, which the suite's
  schema-coverage check required.

### Comparison, sweeps and audits

- `compare --watch-rows` scores a chosen set of positional rows as
  healed/broken columns -- `r49=49,cx2=1620,...`, or `@probes.json` for a
  named set -- and reports the signature in text and as `watch_rows` /
  `watch_signature` in `--json`. The same option is on `compare-dumps`,
  `rank` (one signature per ranked row), and `sweep build`. A six-column
  signature over discriminating rows was the fitness function that converged
  one endgame after `opcodes` conflated schedule with allocation and `words`
  over-charged a permutation.

- `sweep build` compiles a wave of candidate sources and scores it into one
  table: bounded pool (`--jobs 4`), `nice -n 10`, a skip for any object whose
  source *and* compile command are unchanged, the standard metric columns, the
  watch-row signature, the verdict, and stable ordering (`--sort words |
  rows-away | watch | name`, every order breaking ties on the label). Takes
  files, directories, or a generated sweep directory. The productized form of
  a scorer three campaign sessions rewrote by hand.

- `target audit TARGET.o [--rom --rom-offset --va] [--json]` verifies a
  campaign/scratch target object's scope before anyone spends time matching
  against it: ELF sanity (relocation entry counts against `sh_entsize`,
  symbol table consistency), the literal-pool truncation heuristic (a
  function-owned literal pool externalized and `.rodata` truncated exactly
  at the jump table boundary to hide it — the cef4c defect), a data-scope
  report of every undefined symbol reached through a `%hi`/`%lo` pair, and
  an optional read-only ROM cross-check. Verdict `ok`/`warnings`/`defects`
  gates campaign registration (exit 0/1/2). New generic ELF32 big-endian
  reader (`decomp_workbench.elf`: sections, symbols, relocations) backs it.
  See `docs/target-audit.md`.

- `compare --symbol` (and `--function`) no longer carves a function's prologue
  out of its body on an object whose code carries interior labels. The
  selector ended the selection at the first `<label>:` header after the named
  symbol, and a ROM-extracted target object has a symbol for every jump-table
  destination *inside* one function: one campaign's probe reported
  `words=1799 opcodes=1798 gaps=1798` for two objects that differed by a
  single word. The extent now comes from the object's own symbol table --
  `st_size`, else the next `STT_FUNC`, else the section end -- and the parser
  selects by address rather than by label. `compare-dumps`, which has no
  object to read, keeps the selection open across any label a conditional
  branch *inside the selection so far* reaches. See `docs/known-defects.md`.

- That text-only rule is now scoped to the function being selected. Read over
  the whole dump, it let a function whose entry is its own loop head vouch for
  itself, so selecting the function before it ran on through that function's
  body and every function after it that did the same.

- `symbol_extent` no longer swallows the next function in a handwritten-
  assembly object. Only `STT_FUNC` could terminate a size-0 symbol, and a
  hand-written `.s` file has no `STT_FUNC` at all -- every entry is a bare
  `.globl` label, `STT_NOTYPE` and sizeless -- so the first function's extent
  ran to the end of the section. The next externally bound symbol terminates
  it too; a *local* untyped label (a jump-table destination) still never does.

- `sweep build` gives every candidate its own object, cache entry, and row.
  Outputs were keyed on the bare file stem, so same-named sources from two
  input directories raced to compile one object and both rows scored whichever
  compile finished last; a colliding stem now carries a short path digest, and
  the wave reports the collision. The build fingerprint also carries the
  compiler's own identity, as `campaign`'s cache key always has: swapping the
  toolchain behind an unchanged path used to serve every stale object as
  `cached`. Existing `.sweep-build.json` sidecars rebuild once.

- `sweep build` no longer drops a `sweep.json` variant whose `.c` file is
  missing. It now gets a `failed` row saying the source does not exist, which
  is the module's own invariant: a candidate that vanishes from the table
  reads as a candidate that was never tried.

- `target audit` no longer forges the literal-pool truncation defect on a
  healthy object. Every `.rodata` word relocating into `.text` counted as a
  jump-table word, so a `const` array of function pointers ending `.rodata`
  produced the same zero-bytes-left-over coincidence the defect is read from.
  The defect now additionally requires the relocated run to be dense,
  ascending, and to start the section; the same coincidence without that shape
  is a `warning` (`rodata-ends-at-text-relocated-words`) naming which half did
  not hold. A relocation offset past `.rodata`'s own end is reported as
  `rodata-relocation-out-of-range` instead of making the byte count negative.

- `--watch-rows` no longer renames the report it is merged into. The block
  carried a top-level `schema`, so `compare --json --watch-rows` announced
  itself as a watch-row set rather than a comparison and `rank` stamped the
  same id onto every `results[]` entry. The sub-document's identity is now
  `watch_schema`, and every key the block contributes is namespaced.

- Internal: `sweep build` and `target audit` joined the discovery surface;
  five copies of the streaming file digest and a second, divergent nice-prefix
  helper import `campaign`'s; `replay_ugen`'s two copies of the pass
  launch/capture/blame block became one helper; the unreferenced
  `signature_table` and `watch_header` are gone; the aligner's verdict set is
  built from named constants and the two docstrings that still said
  "structure-mismatch only" are corrected; and each hand-rolled ELF
  reader/writer now names `decomp_workbench.elf` as its intended home.

### Documentation, provenance and the agent skill

- A discoverability pass over the late-stage commands. `permute-sweep`,
  `permute-doctor`, `permute classify`, `ranking stamp`/`check`,
  `check-staleness` and `--built-from`, `diagnose --trace`, the `ownership:`
  verdict line and laws L62-L70 each had a documented home and no route to it:
  a reader who did not already know the name would not meet one on the README,
  in `START_HERE`, in the documentation index, in the `commands` map, in the
  field guide, or in the agent skill. Each of those now names them where a
  reader is already looking, with one line and the canonical link. README gains
  a **late-stage campaign loop** section -- rank, preflight, sweep, classify,
  route, verify -- with the two guards spelled out, because the expensive
  mistakes at this stage are all measurements of the wrong thing: a ranking
  stamped against a tree that no longer exists, and a comparison against a
  build older than the edit. The `commands` footer carries the same order in
  one line, and the packaged agent skill runs it as steps rather than as prose.

- Agent skill: `references/evidence-ladder.md` v2 adds byte-pattern search,
  phase-capture decode/diff, and Ucode patch-and-replay as evidence rungs,
  plus "prove at the boundary, then hunt C" doctrine.

- Agent skill: new `references/late-stage-doctrine.md` — mechanism
  composition (prove levers in isolation, compose late), saturation-scope
  hygiene (negatives are basin-local; re-open dials after equilibrium
  shifts), per-site heal-signature fitness over scalar metrics, and target
  trust (audit target section scope at campaign registration).

- Agent skill: `references/campaign-hygiene.md` documents the fan-out
  pattern — asserted-unique-anchor generators, waved sweeps with interim
  standings, mid-flight steering, and byte-search verification of agent
  claims.

- `docs/final-function-campaigns.md`: the cef4c case study, from the
  99.91% hosted frontier through allocator reverse-engineering, the
  one-word `as1` wall, the conditional-fjp barrier proof, mechanism
  composition to `words=0`, and the target-scope fix.

- CONTRIBUTING records the redistribution basis for **symbol-level
  citations**, and the IDO 5.3 laws page and the permuter-sweep page state
  it at the point of use. Both cite real function names, sizes, frame sizes
  and register groups, and neither carried the notice CONTRIBUTING asks of a
  worked example with binary-derived material. A measurement result from
  which no instruction can be reconstructed is a different class from that
  payload; saying so once means the next page does not re-litigate it, and
  the line stays where it already was -- no instruction text, no
  disassembly, no hexdump, in any encoding.

- The documentation-output checker no longer attributes a `text` transcript to
  a runnable command that did not immediately precede it, which made a correct
  page fail because an intervening example was written against `target.o`.

## 0.6.0 - 2026-08-17

### Added

- Compiler law L61: the ugen FP expression-temp assignment closed form, with
  measured per-statement temp costs.
- `docs/roadmap.md`: the evidence-backed blocker list that defines 1.0.
- Campaign guidance: re-sweep the cache after shared-context changes; record
  accepted matches in the ledger, not loose files.
- Troubleshooting: host-environment folklore (zsh word splitting, macOS
  codesign kills, BSD userland, stale build artifacts).
- Public-match-check: the two-clone recipe for recon over a large public
  repository.
- `public-match-check` queries public decomp.me for an existing match by name,
  `--address`, and `--max-score`/`--instructions`; `--fail-on-match`, `--json`.
- `fetch-scratch SLUG [--outdir]` downloads one validated scratch export;
  an already-fetched scratch is reported without a request unless `--force`.
- A shared standard-library HTTP client: identifying `User-Agent` with
  `--contact`, one retry with backoff, and an explicit refusal on HTTP 403.

### Changed

- README routes to `decomp-workbench commands` and the docs index instead of
  duplicating both; link definitions are relative.
- CHANGELOG entries are one-liners; the narrative release notes moved verbatim
  to `docs/history/design-notes.md`.
- Dated campaign records moved to `docs/history/`; the docs index gained a
  History table; `product-status`, `ido-support`, and the quality checklist
  carry as-of dates.
- `docs/tooling-roadmap.md` retired to history; its open items live on the
  roadmap.
- Superseded drafts deleted: the elite product review, the skill feed, and the
  endgame walkthrough page (its example now lives in `campaigns.md`).
- Release tags now attach the built distributions to a GitHub release; the
  PyPI publish job is gated to `v1*` tags until the trusted publisher is
  registered at 1.0.
- `commands --json` carries a top-level `network` inventory of which commands
  may open a connection, replacing the blanket `safety.network: false`.
- `view` reports `verdict: register-ring-only` for ring-temp-only residuals;
  `--emit-force-spec` refuses a wholly ring-only residual.
- `trace-globalcolor --lineage-table` explains an empty result and that
  lineage records need `CDX_LINEAGE_TABLES` at capture time.
- Documentation corrections: field-guide lever 28, source-probes,
  object-comparison, troubleshooting, and decompme-exports pages.

### Fixed

- A relocation whose sides name different symbols is counted as
  `relocation_symbol_mismatches` (`reloc_syms=`) instead of masked to zero.
- `--function` on a target with a stripped symbol falls back to the
  whole-section positional path with a warning, across all comparison commands.
- `trace-scheduler` capture guidance captures both output streams, and
  `besttime` enters the tie-break chain above `aftercycles`.
- An instruction that slides inside a block reports as a schedule decision
  instead of `structural`.
- Control characters from objdump are dropped at the parse boundary and no
  longer reach `--json` (tab is kept).

## 0.5.0 - 2026-08-12

### Added

- `trace-frame` prints the frame ladder from `CDX_SYMTAB` or `webdetail`
  records, with `--ops`; the `CDX_SYMTAB` patch ships in the package.
- `trace-scheduler --from-as1-r` reads `as1`'s native `-R` selection trace
  (`cc -Wa,-R`, byte-inert), computing `tie=` from the losing candidates.
- `shift audit --blobs auto`/`--emit-whitelist`/`--elf`, `shift rehearse`
  `--base-elf`/`--anchor auto`, new `shift config verify` and `shift plan`.
- `shift audit` (static pin/word ranking) and `shift rehearse` (delta-corrected
  relink requiring `unexplained=0`, two deltas); `docs/shiftability.md`.
- `--OPTION-from FILE` on every list-valued option, with a shell-lint test
  over documented and shipped shell.
- `note reserve` claims a note identifier with `O_EXCL`; `note add` refuses
  another owner's reservation without `--author`/`--force`.
- `campaign survey` reads a manifest-less campaign directory: stages, findings
  logs, sweep manifests, and instrument-gate stamps, with `--budget`.
- `instrument gate` records the identity gate as a stamp with hashes and
  scope; `--verify` re-runs the comparison and reports `STALE`.
- `sweep regress/hoist/commute/copies/fuse` (plus `donors` and `carriers`),
  keyed by (site, class, carrier); `sweep ingest`; `docs/sweeps.md`.
- `slots` prices fusion donors per frame offset, marking width-punned slots
  `PUN`, with `--source --volatile-probe DIR` variant emission.
- `probe-equiv` prints a non-escaping local's same-value ranges between
  definitions, with `--at LINE --at LINE` for the pairwise question.
- `probe-deadread` lists positions where a discarded read can move the
  allocator, with the spelling table, `--reach textual`, and `--write DIR`.
- `trace-cascade` prints every allocator round at a `--frame-offset` site;
  `trace-order` ranks the colouring order; `trace-blocks` intersects webs.
- `align`/`align-dumps` print the edit script between instruction streams with
  a distance headline, `--window LO..HI`, and shift-diff JSON.
- `phase` reads the scratch-ring phase per named row slot, printing coset,
  quotiented, and positional counts; `docs/shift-and-phase.md`.
- `--disassembly-cache DIR` on `align`/`phase`, trusted only when an entry
  proves it is a complete disassembly of the object on disk.
- `compare` and `diagnose` name each commutative operand pair in
  `commutative_findings`, including crossed operand loads.
- `SweepCoverage` records visited/excluded points and derives
  *swept-exhaustively* versus *sampled*; `experiment compose --step N`.
- `force-rows`/`force-rows-dumps` report which object rows an allocator
  control owns, with `--target`, `--gap N`, and `BYTE-INERT` results.
- `window`/`window-dumps` print named aligned rows side by side in the
  `aligned_row` numbering `compare --json` publishes.
- `experiment review-mutation` gates a sweep winner on its diff, flagging
  `read-before-definition`/`definition-removed` and `write-removed`.
- `probe-lines --tie STATEMENT=LINE` tests a line-owned schedule verdict via a
  `#line` reassignment, with `next:` routing on every verdict.
- Field-guide lever 28: alias a local (`if (&x);`) to remove it from the
  allocation contest, with `trace-globalcolor` symptom annotations.
- Field-guide lever 2 (accom operand reversal) and lever 26 (the pad slot for
  vacated stack slots).
- `experiment inspect-source` inventories suspicious statics; `experiment
  compose` applies bounded exact-text transformations with a sidecar.
- `object collateral` compares all in-scope section, relocation, and symbol
  contents, separating `outside-selected-function` changes.
- The SSSV endgame [case study](case-studies/sssv-func-802963D0.md), with
  field-guide lever 27 and the packaged Agent Skill workflow.
- `handoff audit` gates public proof repositories: relative paths, absolute
  user paths, untracked files, and cross-project dependencies.
- Redistributable dense-four and dense-five switch-lowering probes report
  comparison chain versus computed jump across frontends.
- Field-guide lever 25: line-number ties by splicing, with a
  [case study](case-studies/ssb64-unref-800036B4.md).
- `check-scratch` reports line-splice hazards in `code.c`, including a
  backslash followed by trailing whitespace.

### Changed

- Documentation and worked examples carry executable, tested contracts, with
  uncleared third-party CV64 payloads removed.
- The workbench fails closed at the seams: objdump ELF probes, sealed campaign
  environments, a `.decomp-workbench.toml` layer, and Windows contracts.
- Campaign endgames finish with receipts: experiment v2 controls and coverage,
  `campaign finish` gates, and `campaign package --finish-receipt`.
- `trace-webs --against` reports which identity field failed alignment and
  whether a rebuild would help, per field and producing record.
- Late-stage campaigns preserve evidence: `ACCEPTED` leads, `campaign
  --rank-by temp-prefix`, `trace fifo --emission-map`, `campaign package`.
- `next` routes an allocation-shaped verdict to `oracle plan` at family rank,
  ahead of region attribution; `docs/oracle.md` explains the ceiling rule.
- `compare` prints a `raw-vs-words:` note whenever `raw` exceeds `words`,
  naming the relocation-controlled floor.
- Literal-pool accesses are compared by resolved slot: new `pool` and
  `pool_layout` classes; same-symbol different-addend sites are `pool_layout`.
- Aligned row counts say when they are not comparable: `opcodes=`/`gaps=`, an
  alignment caution, and mixed-alignment ranking on `words`.
- `score` prints one screen line (`sha ni frame ld st coset`), with `--slot
  OFFSET` narrowing and a coset caution.
- `next` routes an instruction-count difference to `align` and a float run to
  `phase`.
- Instrument records name what they measure: `nocs` as three named fields,
  `class` as the IR register class, and the new `ALLOC_FP` hook.
- Every generated sweep edit states its base, refusing on SHA-256 mismatch,
  failed anchors, or `--frozen LO..HI` zones.
- Scratch acceptance separates linked exactness, raw word identity, and
  relocation identity, reported as `decomp_me_score_proxy_exact`.
- Allocator comparisons expose uncertainty: ambiguous webs block `aligned`,
  and empty captures report `no-evidence` with nonzero status.
- Allocator trace comparison separates identity from outcome, reporting
  carrier substitution instead of false identity.
- `oracle force` accepts a validated comma-separated force set and records the
  baseline-to-forced instruction delta.
- `trace copy-decisions` reports coalesce-versus-temporary outcomes with a
  conservative parser and is listed in group help and completion.
- Frame recovery and campaign handoff retain diagnostic state, with a
  wrong-frame playbook and visible metadata recovery.
- Scratch bundles record label, compiler ID, language, and preset separately;
  `check-scratch` reports the frontend and uses `src.cxx` for old C++.
- Line-layout guidance is frontend-specific: cfe splice behavior kept separate
  from NCC/EDG statement attribution.
- Frontend-lineage guidance no longer generalizes `cfe` to all of IDO and
  requires inspecting the actual phase command and intermediate.
- The campaign skill carries the campaign-strategy lessons: scoped negatives,
  residual-fixing variants as baselines, and credited falsifiers.

### Fixed

- No data-selecting option may default to a directory outside the workbench's
  own `.decomp-workbench` state, and a test enforces it.
- `coset=?` (no ring-carrying rows) is no longer reported as a rotation.
- `decomp-workbench probe` and `decomp-workbench sweep` list their operations
  instead of answering "not a command".
- One corrected float colour map (`c24=$f0` through `c29=$f18`), served by
  `register_for_color` to every trace report.
- The IDO 5.3 float temp ring is documented as four wide (`f4 f6 f8 f10`);
  `f16`/`f18` are withdrawn before the first allocation.
- `audit-handoff` failure on a relative root quotes the argument as typed and
  the working directory it was resolved against.
- The `--register-profile ido53` pool/temp split is corrected from probes,
  with the old table as `unverified` and `register_profile_evidence` in JSON.
- Symbol-table asymmetry no longer manufactures relocation rows: branch and
  jump destinations are normalized on both sides before classing.
- `cache` and `context` print their operation map and exit 0 without an
  operation, matching the other command groups.
- `view` and `view-dumps` accept the long-advertised `--show-all`.
- `check-scratch` accepts current C++ export members (`code.c++`/`ctx.c++`,
  plus `.cc`, `.cpp`, `.cxx`) instead of reporting `code.c` missing.
- `python -m decomp_workbench` works instead of failing with "No module named
  decomp_workbench.__main__".

## 0.4.0 - 2026-07-31

### Added

- `diagnose --candidate-listing LISTING.s` reports per-site `.loc` statement
  lines, promoting `playbook=line-assignment-probe` on a boundary majority.
- `probe-lines` proves or refutes line-assignment sensitivity via
  token-identical line reflow; `docs/line-assignment-probe.md`.
- `context lint` flags `#if`/`#elif` guards whose identifiers are all
  undefined; `check-scratch` runs it over ctx+code (lever 24).
- `score` windows a function via `--function` or `--between` with a relocation
  floor and `--control` checks; `matrix` clusters variants into attractors.

### Changed

- Campaign ledgers redact the target ROM's instruction text: salted 16-bit
  `target_digest`, masked opcodes, and salts in a `<ledger>.salt` sidecar.
- Ledger redaction filters site records through the `SITE_KEEP` allow-list;
  the salt is load-bearing, and `--html`/`force_spec` are documented leaks.

### Fixed

- The redaction sweep enters all container types, inspects keys and
  allow-listed values, and caps depth (six demonstrated bypasses closed).
- The unredacted-ledger resume warning streams every record instead of capping
  at 4096 lines, and says how far an explicit cap got.

## 0.3.1 - 2026-07-30

### Changed

- The bundled Agent Skill routes agents through the `next:` footer and
  `guide`, mandates a harness proof, and adds `references/frontend-lineage.md`.
- The README shows an ANSI-faithful SVG of a fixture diagnosis and a
  screenshot of the HTML report, both generated from shipped fixtures.

## 0.3.0 - 2026-07-30

### Added

- `decomp-workbench guide <topic>` prints the packaged field guide's sections
  for a playbook, verdict vocabulary, or lever number, offline.
- [From verdict to edit](docs/from-verdict-to-edit.md) walkthrough and a
  glossary in the documentation index.
- Alternate-frontend documentation: `docs/alternate-frontends.md`, field-guide
  levers 20-22, and SSB64 field notes.
- Four one-line vocabulary explanations at first use, removable with
  `--terse`; `--html` renders each lever as a runnable `guide N` snippet.
- A compact `webs:` header line, with substituted register tokens coloured by
  web.
- Every `next:` footer names the matching field-guide levers, the `guide`
  command, and both answers to "do you have an instrumented toolchain?".
- `diagnose`/`diagnose-dumps` render exact truth plus aligned mechanism
  evidence; `check-scratch --view` reuses the imported comparison.
- A durable campaign cockpit: manifest and append-only ledger under
  `.decomp-workbench/`, `campaign status/note/resume/export`, sidecars.
- Compiler-research adapters: `toolchain init/calibrate/status`,
  `DKWB-SCHED-V1` records, hash-pinned profiles, fingerprint microcases.
- Semantic allocator and source provenance views: web fingerprints, stack-home
  ownership, and `trace-source` joins through `.file`/`.loc`.
- `--census KEY=VALUE[,...]` on the comparison commands: assert reported
  values as exit codes (0 pass, 3 fail, 2 bad question).
- Three narrative pages: `docs/START_HERE.md`, `docs/field-guide.md`, and
  `docs/walkthrough-30-near-matches.md`, with executed doc-command tests.
- `doctor` (readiness and bundle validation) and `check-scratch`
  (extraction-free scratch reading with an optional compile mode).
- Three verdicts split out of the volume-based classes: `constant-mismatch`,
  `commutative-order`, and `schedule-mismatch`, each with its lever.
- `--function` as a second spelling of `--symbol` on every single-function
  command, with conflicting values rejected.
- `view` and `view-dumps`: the aligned mechanism view with two-pass LCS
  alignment, per-hunk classes, register lanes, webs, and lever guidance.
- The portable `n64-decomp-campaign` Agent Skill for Codex and Claude Code,
  with installation guidance and reusable campaign evidence.
- Action-oriented comparison verdicts, relocation-only raw-difference
  explanations, and a separate cross-ROM structural-evidence mode.
- Object-basin reporting in campaigns, visible in terminal and JSON summaries.
- Focused `trace-globalcolor --proc ... --web ...` inspection with trustworthy
  callee-saved register names.
- A final-function campaign guide covering the Hartley, Titania, and Aquas
  evidence patterns.
- Deterministic, upload-neutral decomp.me scratch bundles with copied inputs,
  settings, and checksums.
- A five-function Castlevania 64 walkthrough with complete scratch inputs.
- Documentation of the supported IDO 5.3 and 7.1 workflow matrix and the
  instrumentation profiles' version boundary.

### Changed

- Symbol selection falls back to a unique case-insensitive match, for
  identifier-folding frontends such as `upas`.
- `--width` wraps the `next:` footer on word boundaries with indented
  continuations instead of truncating it.
- The HTML report is rebuilt from the terminal's view model: verdict bar,
  lanes, linkable hunks, and a `Webs` table — still one self-contained file.
- An unknown command names itself and points at `decomp-workbench commands`
  instead of printing argparse's full catalogue.
- With no `--function` and one differently-named symbol per side, the
  comparison commands warn ahead of the verdict and name the fixing option.
- The novice path is legible: the bare program name welcomes and exits 0, and
  `docs/README.md` glosses IDO, asm-processor, ugen/uopt, and decomp.me.
- Missing-symbol and objdump `file format not recognized` errors name the
  likely cause before quoting the tool.
- `allocation-mismatch` footers lead with `view`/`diagnose` and the levers,
  gating traces on lever exhaustion plus an existing instrumented toolchain.
- Main identifies itself as `0.3.0.dev0` instead of reusing the published
  `0.2.0` identity.
- The allocator oracle is productized: `oracle plan/diff/force/sweep` use the
  campaign engine and `status/export` reopen persistent evidence.
- Evidence boundaries hardened: LCS-aligned region scores, phase-qualified
  allocator details, and forced exactness causal only after a control.
- Automation standardized on one versioned JSON document, with a command map,
  task-group aliases, shell completions, and expanded CI.
- Compiler execution shares one lifecycle contract: 120-second default
  timeout, explicit environment/cwd controls, and process-group cleanup.
- Scratch handoffs hardened: one flat ZIP root, refused nested or symlinked
  content, real SHA-256 checksums, and rejected impossible scores.
- Examples and campaign state standardized on repository-root commands and
  `.decomp-workbench/`, with schema-versioned JSON reports.
- `--objdump PATH` is authoritative: a misspelled explicit path fails
  immediately, and `doctor` verifies the reader against `target.o`.
- `schedule-mismatch` requires a matching instruction multiset, so a
  reordering that also moves a register is not "not allocation".
- Compiler termination escalates from `SIGTERM` to `SIGKILL`, with own process
  groups on Python 3.11+ and the guarantee scoped to POSIX.
- The packaged bundle under `src/decomp_workbench/skills` is the only skill
  tree, enforced by a test.
- Globalcolor instrumentation is phase-explicit: `phase=p1`/`p2` records,
  phase-qualified `CDX_FORCE` keys, and decoded machine registers.
- Instrumentation fidelity gates are documented as section-scoped, because
  stock IDO under `-g3` is not file-level reproducible.
- The campaign runner owns its process groups, terminating compilers with
  their children on failure or interrupt.
- Campaigns stop on the first exact match by default (`--no-stop-on-exact`
  sweeps the whole grid), with the repeated target disassembly removed.
- Human labels and JSON keys unified behind one metric registry with
  `--explain-keys`; long-form JSON keys deprecated for one release.
- `view`/`view-dumps` reject `--symbol`/`--function` conflicts, gain
  `--explain-keys`, and move beside `compare` in the help listing.
- The aligned view's keys live in the shared metric registry, with a
  two-direction test between registry and output.
- A release-quality UX pass: packaged Agent Skill, safe installer, clarified
  proof scope, and true best basin representatives.
- `compare` and `compare-dumps` report the LCS-aligned residual beside the
  positional one, and ranking sorts on `aligned_total` first.
- Documentation refocused on decompilation problems, command outputs, and
  support boundaries.
- Project-specific research narratives replaced with concise workflows,
  operating principles, and a documentation index.

### Fixed

- A missing-symbol error no longer blames the build for a typo: an unfiltered
  second objdump pass supplies the real "defines:" list.
- `allocation-mismatch` no longer guesses a lever family: it names all three
  unresolved families with the `guide` command for each and picks none.
- Four terminal rendering defects: family-coloured verdicts, `--color` on
  `compare`/`rank`, wrapped annotations, and `slot=/aligned_row=` labels.
- Adjacent instruction swaps are no longer misclassified when unrelated
  relocation addends differ; the view uses relocation-masked identities.
- An unsafe claim corrected across guidance: a region collapsing under `-g0`
  does not prove source correctness (the `vsprintf` counterexample).
- `CDX_FORCE` no longer aborts on a forbidden color: the pass declines,
  records `force_declined`, and `trace-globalcolor` reports `forbidden_colors`.
- The commutative-operand rule is deduplicated: `compare` and `view` classify
  through one `compare.commutative_swap` predicate.
- Stopping on an exact match records candidates already in flight, and an
  unexpected candidate error is recorded rather than ending the run.
- The instrumented pass validates the workbench's force-key grammar, refusing
  a partially formed control instead of silently forcing nothing.
- `--show-diff` reports every differing site regardless of verdict, not only
  register groups.
- Register diagnostics are portable across GNU objdump dialects with or
  without the `$` register prefix.
- Unreachable zero alignment padding after a selected MIPS function's return
  delay slot is excluded from comparisons.

## 0.2.0 - 2026-07-27

### Added

- Redistributable objdump-text fixtures and symbol filtering.
- Parallel, cached campaigns with explicit provenance and JSONL ledgers.
- Structured ugen trace parsing, FIFO validation, and logical-value
  reconstruction.
- `CSAVE`/`CUP`/`[CDX]` globalcolor reporting.
- Hash-pinned, anchor-validated uopt globalcolor and alias profiles, with safe
  profile composition and alias-state reports.
- Retained ugen-to-as1 listing replay.
- Task-oriented guides, CC0 licensing, and clean-wheel validation.
- The workbench published as a standalone repository with end-to-end
  workflows, centralized troubleshooting, and root-level CI.
- Python 3.10-3.14 CI, strict type checks, formatter enforcement, and
  release-distribution smoke tests.
- A reproducible instrumentation fidelity microcase and release validation
  record.

### Changed

- Exact comparison is relocation-aware and conservative about missing or
  unknown relocation kinds.

### Fixed

- List-address filtering in FIFO replay, and acceptance of non-finite
  globalcolor costs emitted by compiler diagnostics.
- The phase-two globalcolor web identifier used by decision logs and force
  controls; force controls must select one procedure.

## 0.1.0 - 2026-07-26

### Added

- Initial object comparison, ranking, sequential candidate compilation, and
  generic ugen instrumentation package.
