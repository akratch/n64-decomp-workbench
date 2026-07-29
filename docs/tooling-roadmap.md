# Tooling roadmap from live campaigns

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
  recompile `ctx.c` plus source with the site's `#line 1 "src.c"` semantics.
- The portable Agent Skill ships in package artifacts and has a safe,
  idempotent installer for Codex and Claude Code.

## Next

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
