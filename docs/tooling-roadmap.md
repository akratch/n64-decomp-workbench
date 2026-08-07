# Historical tooling roadmap from live campaigns

> **Status (2026-07-30).** Every adapter-level item originally listed as
> “Next” below has landed: original/static pass differential, behavioral
> fingerprints and cross-ROM lineage, semantic web/interference joins,
> stack-home reports, marker-aware source/listing correlation, portable pass
> work roots and calibration, experiment manifests/regions, register
> permutations, relocation aliases, and stable scheduler records with
> hash-pinned external profiles. The mutation-recipe library and richer
> emitted-instruction joins remain research because safe equivalence and
> validated producer fields need project evidence. See
> [Product status](product-status.md). The original proposals remain below so
> their acceptance reasoning is not rewritten after the fact.

This backlog records gaps observed while applying the workbench to late-stage
N64 decompilation functions. It is intentionally project-neutral and excludes
ROMs, target objects, and proprietary compiler files.

## Implemented

- Compiler working directories are explicit campaign inputs through
  `--compile-cwd`; they are validated, recorded, and included in cache keys.
- `campaign --json-summary` provides bounded ranking output without compiler
  streams or instruction-level register diffs.
- Globalcolor decisions can be filtered by procedure and can expose allocator
  masks, remaining-register counts, IR metadata, and interference neighbors.
- CDX allocator decisions are joined with target web metadata, so procedure and
  dtype filtering works even without legacy `CSAVE`/`CUP` records.
- Detailed globalcolor traces expose every evaluated color's final cost,
  best-before value, caller/callee class, available-color masks, and secondary
  tie-break state.
- Focused globalcolor lookups require a procedure/web pair, suppress unrelated
  rows, and report available webs when a lookup misses.
- Campaign summaries group source variants by compiled function-byte hash and
  choose the best-ranked representative for each object basin.
- Comparison reports classify relocation-controlled raw differences, emit
  action-oriented verdicts, and keep cross-ROM acceptance separate from exact
  object evidence.
- Comparison and ranking share one LCS-aligned mechanism view. Pure
  instruction reorderings remain scheduling residuals even when unrelated
  relocation addends differ elsewhere.
- `doctor` reports retained-dump/object-reader readiness, validates scratch
  handoffs, and prints a shell-quoted next command.
- `check-scratch` safely reads decomp.me export ZIPs/directories without
  extracting them, separates browser score context from object truth, and can
  recompile `ctx.c` plus source with the site's language-aware `src.c`/`src.cxx`
  line-reset semantics.
- The portable Agent Skill ships in package artifacts and has a safe,
  idempotent installer for Codex and Claude Code.

## Open, observed 2026-08-06

These came out of the `--tie` and lever-28 integration pass. Each is a design
question rather than a missing line of code, which is why it is filed here
instead of shipped.

### A tie is scored but does not reach the verdict

`probe-lines` classifies from the reflow and its control only. A `tie` variant
that moves the object toward the target is reported in the target block and in
the `next:` routing, but the verdict vocabulary
(`line-sensitive`/`not-line-sensitive`/`nondeterministic`) has no way to say
"this reassignment is the one". Adding a fourth verdict changes a published
schema's value set and would have to answer what a *partially* correct tie is
called, which the current evidence does not settle. Until then the toward/away
counts are the result and the verdict is only about ownership.

### Tie sweeps are manual

The natural next tool after `--tie` is a sweep: one statement, several
candidate line numbers, ranked by toward/away. `campaign` already owns
variant sweeps with caching and a durable ledger, but its unit is a compiled
source variant, not a probe run, and `probe-lines` has neither `--census`
predicates nor a ledger. Either `probe-lines` grows a bounded `--tie-sweep`
with its own state, or the probe becomes expressible as a campaign mechanism.
Doing both would give the same experiment two homes.

### Lever 28's placement axis has no tool

Placement of an alias mark is now a measured tuning axis (140/131/106 words on
`func_ovl8_803787C0` at head/`j`-loop/innermost). That is a scoped, ordered
search over source positions with a zero-instruction invariant to check — the
same shape as `experiment compose`'s bounded substitutions, but positional. A
mechanism that emits the placement ladder and asserts the instruction-neutral
invariant would turn a hand sweep into a recorded one.

### `pool-position` cannot route a lever from the footer

`pool-position` is an ambiguous playbook: its footer deliberately names three
families and picks none, so a lever list never prints there. Lever 28 is
reachable only through evidence-gated prose in the neutral block or through
`guide`. The real fix is a verdict that separates the three allocation
families, which needs lane evidence `view` does not currently produce, not
another sentence in the footer.

## Open, observed 2026-08-08

From the `object_interaction` campaign's stage-attribution work. Both items are
real, both have a working campaign-local prototype, and both are filed here
rather than shipped because promoting them as they stand would put an
unmeasured claim behind a workbench command.

### A stage-capture harness for the IDO driver

**The gap.** Answering "which stage decides X" means running `cfe`, `uopt`,
`ugen`, and `as1` by hand on the composed translation unit, which means
scraping `cc -show`, re-quoting `-Amachine(mips)` past the shell, threading the
`-XS<symtab>` temporary between the four stages, and then proving the
hand-driven object is byte-identical to the driver's. That is roughly forty
minutes of setup, it is the *only* way to attribute a decision to a stage, and
two campaigns (`ovl8`, `ge007`) have now built it independently as a local
shell script. The `ge007` prototype is 23 lines and hard-codes every path.

**The shape it would take.** `decomp-workbench stages SRC.c --cc DRIVER
--outdir D`: parse `cc -show`, replay the four stages retaining `.B`, `.O`,
`.s`, and `.o`, then assert the replayed object is byte-identical to the
driver's and fail loudly when it is not. The identity assertion is the whole
value — a replay that silently differs from the driver attributes decisions to
the wrong stage, which is worse than no harness.

**Why it is not shipped yet.** The command is only as good as its model of one
driver's `-show` output, and the workbench has exactly one measured driver: the
IDO 5.3 recompilation this campaign used. `cc -show` is not a stable interface,
the stage set is version-specific (7.1 differs, `accom` differs more), and the
`-XS` temporary threading is a driver detail rather than a documented contract.
Shipping a `stages` command implies it works for a reader's compiler, and this
repository's rule is that a claim carries its provenance. The honest sequence
is: first a *recorded* `-show` transcript format that a reader can supply for
their own driver (redistributable, like the existing objdump fixtures), then a
replay engine over that record, then the identity gate. Note also that
`pass replay-as1` and `toolchain calibrate` already own the "replay a pass and
prove it reproduces the object" contract; a stage harness should extend that
vocabulary rather than open a second one.

**Prototype:** `p3f/work/stages.sh` in the `ge007-object-interaction` campaign
(not redistributable: it names a local toolchain and include tree).

### A ucode record decoder

**The gap.** The `cfe`/`uopt` intermediate streams decode with a small, fixed
record format — 8 bytes per record, an opcode record `[op][ty][flags:2]
[word:4]`, with operand records `[00 00 00][kind][value:4]` following some
opcodes — and every campaign that has needed it has rediscovered that by
inspection. A decoder plus a `--diff A B` mode reporting differing record
ranges is the one query a "which stage owns this decision" investigation
actually runs.

**The known correction, recorded here so it is not rediscovered a third
time.** A decoder written for `accom` 4.1 (`phase3-bdump.py` in the `ssb64`
overlay-8 campaign repository, which is not this repository and is deliberately
not edited by this note) does decode IDO 5.3 streams — the record format is the
same — but it carries one real bug for `cfe.B`: **opcode `0x49` carries two
operand records, not one.** A decoder using the "one operand record may follow
an opcode" heuristic goes out of phase at the first `0x49` and mis-pairs every
record after it. `uopt.O` is unaffected in practice because its expression code
holds no bare `0x49` runs. Opcode identities confirmed by micro-probe on 5.3:
`0x01` add, `0x36` iload, `0x51` line, `0x52` push, `0x5b` mul, `0x7b` store;
type byte low nibble `d` means float.

**Why it is not shipped yet.** The opcode table is empirical and partial. About
two dozen opcodes are named, most of them with a question mark, and the operand
arity that makes the stream parseable at all is known for a handful. A decoder
in this repository would print `op49` beside `add` with no way for a reader to
tell the probed identification from the guessed one — the same failure the
register-profile evidence strings exist to prevent. The shippable version is a
per-opcode **arity** table (which is what parsing needs, and which a probe can
establish one opcode at a time) with the arity's provenance recorded per entry,
plus `--diff`; the mnemonic table stays advisory and clearly labelled until
probed. Until then the format and the `0x49` correction are documented here so
the next campaign starts from the fixed version.

**Prototype:** `p3f/udump.py` in the `ge007-object-interaction` campaign.

## Original proposals (now implemented unless noted)

### Original-pass differential adapter

Add a reusable adapter that runs a user-supplied original IRIX pass under
QEMU/Docker and compares it with a static recompilation at each retained pass
boundary. Requirements:

- no compiler binaries or generated proprietary sources in this repository;
- explicit mounts and path rebasing for host temporary directories;
- a project-visible temporary directory on macOS, where Docker cannot normally
  access per-user `/var/folders` paths;
- hashes for the original pass, static pass, input, output, and downstream
  assembler;
- disabled-instrumentation and unedited-replay fidelity gates.

### Compiler-variant fingerprinting

Build a redistributable microcase suite that distinguishes compiler/pass
variants by control-flow lowering, stack-home selection, scheduling, and
register-allocation tie behavior. A project should be able to identify a
toolchain variant before running a large source campaign.

Add a cross-ROM fingerprint mode for projects with multiple revisions or
regions. Given equivalent symbol ranges, it should compare instruction
sequences after relocation normalization, identify byte-identical compiler
idioms, and distinguish stable source/compiler lineage from a one-ROM anomaly.
Reports must record ROM and extraction hashes without redistributing ROM data.

### Stable allocator web fingerprints

Numeric web IDs are useful within one compiler input but are not durable across
source changes. Derive a fingerprint from data type, virtual stack home,
def/use basic blocks, expression ancestry, and interference neighborhood.
Reports should map equivalent webs between candidates and explain added or
removed interference edges.

The first comparison mode should align decision streams by semantic provenance
(`dtype`, virtual stack home, table/chain identity, and basic-block context),
not numeric web ID. Folded definitions can renumber every later web while
changing only one real lifetime, making a raw line diff actively misleading.

The report should also identify the already-colored neighbor responsible for
each forbidden color and show its semantic counterpart in the other
candidate. Late-stage campaigns need an answer such as “color 1 became
unavailable because this lifetime now intersects that carrier,” not just two
large neighbor lists.

### Stack-home provenance

Classify each spill home as a named source local, compiler temporary, outgoing
argument home, or allocator-created spill. Expose the virtual offset before
final frame layout and show which source/IR change moved a value between those
classes. This is essential when one source form has the target registers but a
named-local home, while another has the correct anonymous-temporary home.

Provide an offset-centric report that maps every use of a selected final stack
offset back to its web and source/IR owner. Also compare two candidates by
stack-home ownership so a campaign can answer which value displaced a local by
one slot, rather than only reporting that `N(sp)` changed.

### Source and listing correlation

Improve IR-to-source correlation beyond compiler line fields, which can be
coarse or synthetic after preprocessing. Retain preprocessor line markers and
map allocator webs to source expressions and late-pass listing locations.

### Pass-listing portability

Add preflight checks and normalization for host-specific listing paths,
temporary-file visibility, and C-library formatting differences such as
`ecvt`/`fcvt`. An unedited listing replay must remain the mandatory calibration
cell.

### Campaign experiment manifests

Accept a sidecar manifest describing each transformation family and its
parameters. Summaries should report basin transitions and keep the top
candidate per structural signature without embedding unbounded detail.

Ship a project-neutral library of source-equivalent late-stage mutations:
repeated folded conditions, neutral integer operations, nested assignments,
statement grouping, equivalent pointer arithmetic, declaration-order
permutations, and lifetime-carrier placements. These patterns repeatedly
matter in mature IDO decomps. The campaign runner should optionally stop or
deprioritize redundant experiments as compiled function-byte basins arrive,
avoiding unnecessary work after a generator begins producing repeated
outcomes.

Include adjacent repeated indexed empty conditions as a first-class mutation,
with configurable expression, repetition count, and placement anchor. Live IDO
campaigns show that two otherwise code-free indexed conditions can perturb
allocator priorities and colors even when the final instruction stream contains
no trace of the conditions.

Include emission-free comma-expression conditions such as
`if ((carrier, live_value)) {}` at configurable definition/use boundaries.
These are not interchangeable with a plain `if (live_value) {}` in IDO's
optimizer: the comma form can change expression ancestry and allocator web
priority while emitting no instructions. Mutation manifests must retain the
carrier, live value, repetition count, and placement so the causal dimension is
visible after object deduplication.

Add constraint-decomposition scoring for late-stage crossings. Users should be
able to select an instruction region that must remain byte-exact while ranking
the rest of the function separately. Summaries should call out candidates such
as “selected region exact; only one stack-home family regressed” and list the
instruction indices sharing that residual operand. A single global word count
hides this useful structure.

### Register-web swap diagnostics

When two candidates have identical opcode schedules and their remaining
differences form a consistent register permutation, report the permutation and
the affected instruction indices. If compiler allocator instrumentation is
available, map the registers back to stable web fingerprints and optionally
emit a diagnostic force specification for an oracle build.

The force build is evidence only, never a source match. Its report should state
whether the permutation makes the function exact and which source webs must be
re-prioritized. This turns a late-stage register-color residual into a bounded
source mutation problem instead of another broad structural search.

### Linked-address relocation aliases

Classify relocation aliases that resolve to the same linked address. This
occurs when a loop endpoint can be spelled either as `array + count` or as the
next adjacent symbol: a ROM-derived target may choose the successor symbol
while the compiler object retains the base symbol plus an addend. Reports
should identify these as resolved-address-equivalent aliases, list both
spellings, and recommend the project link/ROM check instead of prompting source
changes. External score importers should keep this class separate from genuine
instruction mismatches.

### Deeper late-pass controls

Extend opt-in UGEN/AS1 diagnostics to cover expression evaluation order,
temporary-register carrier selection, and schedule decisions. Controls remain
experimental evidence and must never be presented as source-level matches.

The first scheduler profile should emit a stable, documented record for each
selected node: procedure, block, cycle, opcode, source line, ready-set size,
and the tie-break that won. Calibrate it with an instrumentation-off binary
identity gate and an unedited as0/as1 replay. Do not productize the current
unlabeled pointer dump: a trace whose fields require reverse-engineering every
run is not a user interface.
