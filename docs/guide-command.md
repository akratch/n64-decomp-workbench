# The `guide` command

`diagnose` and `view` end with a `next:` footer that names a mechanism and a
`playbook`. `guide` is the other half of that sentence: it prints the
[field guide](field-guide.md) levers behind the name, so the concept the
verdict used is one paste away instead of one search away.

```sh
decomp-workbench guide                       # the topic index
decomp-workbench guide forced-color-oracle   # a playbook
decomp-workbench guide register-permutation  # a verdict
decomp-workbench guide 19                    # a lever number
```

## What a footer looks like now

Every verdict's footer keeps its expert content and gains three things: the
matching lever numbers with a one-line action each, the literal `guide` command
for that playbook, and — where the expert line names a trace, a probe, or an
oracle — both answers to "do you have an instrumented toolchain?".

```sh
decomp-workbench diagnose-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/register-mismatch.objdump
```

```text
next: all visible register differences form one bijection (f0->f1): report one downstream allocation outcome, not N sites.
      one visible bijection does NOT prove one source web or one source edit: inspect the desired color's interference producers; a staggered ladder of invisible blockers can cause the outcome.
      callee-saved tie-breaks resist blind source search; use a forced color probe to measure the smallest causal web set before choosing more variants.
      field guide levers for playbook=forced-color-oracle:
        lever 17: only with a copy-shaped residue OR check-scratch's measured late v0/v1 call-return occupancy hypothesis: test one explicit `int`/K&R return-category variant at the declaration and definition
        lever 18: only when the residue contains a move/copy: give a genuinely repeated expression a named intermediate so the coalesced copy lands on the other value
        lever 19: the callee-saved tie-break is a uopt ordering decision: force the smallest measured causal web set (often one, sometimes a staggered blocker ladder), inspect every cascade, and compare paired formation, save/totalsave, and decision-trace order; no one scalar is priority proof
      read them: decomp-workbench guide forced-color-oracle
      have an instrumented toolchain? docs/compiler-instrumentation.md, then decomp-workbench diagnose ... --emit-force-spec force.json and decomp-workbench oracle plan TRACE.log to build the two-phase grid.
      don't have one? first inspect the residue for an actual move/copy site, or run check-scratch --view with a project object to test the strict late v0/v1 call-return occupancy shape. If either gate fires, lever 17 is one variant; lever 18 still requires a visible copy and repeated source expression. Otherwise go directly to lever 19; a clean forced-color cascade is a legitimate stopping point - record it, bundle the scratch, take the next function.
```

The two-branch line matters more than it looks. "Prefer a forced color probe on
an instrumented toolchain" was true and unusable for the many readers who do not
have one, and it never said what they should do instead. The copy-site gate is
equally important: a repeated register in disassembly is not a
"twice-referenced expression" in source.

## Topics

| Topic | Example | Resolves to |
|---|---|---|
| playbook | `forced-color-oracle` | that playbook's levers, in priority order |
| playbook | `frontend-lineage` | levers 20-22, reached by evidence rather than by a verdict |
| verdict | `register-permutation`, `allocation-mismatch` | the playbook for that verdict, then its levers |
| lever number | `19` | one section, plus the playbooks that reach it |

Both verdict vocabularies work: the aligned mechanism names printed by `view`
and `diagnose` (`register-permutation`, `phase-shift`, `structure`) and the
exactness names printed by `compare` (`allocation-mismatch`,
`schedule-mismatch`). Whatever the terminal printed is a valid topic.

`--width` and `--pager` behave exactly as they do on `view` and `diagnose`.

## Where the text comes from

The guide travels inside the installed package, so `guide` works with no
checkout and no network. The lever *numbering* is the stable address: the
mapping in the code cites numbers and carries its own one-line action for each,
so a lever whose section is not in the installed revision still prints
something a reader can act on rather than failing. That is not hypothetical —
levers 20-22 were numbered and actionable here for a release cycle while their
prose was still being written — and it means an installation whose packaged
guide is older than its code degrades to:

```markdown
### 20. (not in the shipped field guide)

before concluding 'hand-patched object', fingerprint the other authentic
frontends (accom/ccom, upas) feeding the same backend
```

If the packaged document is missing entirely — a stripped install — `guide`
prints the same one-line actions, names the two places the full text lives, and
exits non-zero.

## See also

- [Field guide](field-guide.md) — the levers themselves.
- [Start here](START_HERE.md) — the loop the footer sits inside.
- [Compiler instrumentation](compiler-instrumentation.md) — the "have an
  instrumented toolchain?" branch.
- [Aligned mechanism view](view.md) — the command that names the mechanism.
