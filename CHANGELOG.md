# Changelog

Narrative release notes with the design reasoning behind each change are kept
in [design notes](docs/history/design-notes.md).

## Unreleased

### Fixed

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
- `target audit` no longer forges the literal-pool truncation defect on a
  healthy object. Every `.rodata` word relocating into `.text` counted as a
  jump-table word, so a `const` array of function pointers ending `.rodata`
  produced the same zero-bytes-left-over coincidence the defect is read from.
  The defect now additionally requires the relocated run to be dense,
  ascending, and to start the section; the same coincidence without that shape
  is a `warning` (`rodata-ends-at-text-relocated-words`) naming which half did
  not hold. A relocation offset past `.rodata`'s own end is reported as
  `rodata-relocation-out-of-range` instead of making the byte count negative.
- `pass binasm` only calls a record `calibrated` in the form a probe
  established. A family is matched on the high half of its opcode word, and a
  record whose low half was nonzero -- a variant nobody has observed -- was
  reported as calibrated evidence *with those bits deleted from the output*.
  They are now rendered as `flags=0x....` and the record reads `inferred`; an
  instruction record whose opcode is not one of the as0-probed set, and a
  `.set` mode number no probe named, stop counting as calibrated too.
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
- `pass ucode --json` declares its report schema, which the suite's
  schema-coverage check required.
- The documentation-output checker no longer attributes a `text` transcript to
  a runnable command that did not immediately precede it, which made a correct
  page fail because an intervening example was written against `target.o`.

### Added

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
- Layout-aware verdicts: on `structure-mismatch` and `schedule-mismatch` --
  the two verdicts a block permutation lands on -- `compare` now runs the
  shift-tolerant aligner itself and reports the edit script, the moved-block
  count and rows, and `rows_away` beside `words`, in text and under `layout`
  in `--json`. One campaign candidate whose real edit script was a single
  relocated 29-row block reported 1,791 differing words and was ranked below
  strictly worse candidates. Documented as Trap 8 in `docs/metric-traps.md`.
- `pass ucode` statically decodes retained IDO binary Ucode switch dispatches,
  including the selector expression, XJP range/default/case labels, and dense
  case-target table.
- `pass binasm` statically inspects one fixed-record ugen-to-as1 boundary,
  summarizes IDO 7.1 `-peepdbg` copy rewrites, and turns exact barrier-probe
  cells into source-search families without overstating upstream survival.
- `trace a71` parses and diffs the compact IDO 7.1 final-color stream,
  decoding priorities and masks while warning that web IDs are run-local and
  the producer's historical `refs`/`defs` fields are invalid.
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

### Changed

- `parse_binasm` and `parse_ucode` accept bytes or a path, so a patched stream
  held in memory and a retained capture file use one entry point.
- The Binasm decoder names five record families it used to leave unknown --
  positive-index label definitions, jump-table entries, section switches,
  procedure and stream-header records -- and frames a float literal's ASCII
  digits as payload instead of word-decoding them into invented families. Each
  record now carries `evidence`: `calibrated`, `inferred`, or `none`.

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
