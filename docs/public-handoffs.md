# Audit a public proof handoff

A proof repository can be correct on its author's machine and incomplete on
GitHub. The usual failure is a README that points at a local provisioning file
or compiler variant which exists beside the project but was never tracked.
`audit-handoff` checks the exact publication tree before somebody else has to
discover that omission.

```sh
decomp-workbench handoff audit /path/to/public-proof-repo
```

The audit reports:

- broken relative Markdown links;
- path-like inline-code references such as
  `$PROJECT/tools/compiler/README.md` that do not exist in the handoff;
- absolute user-home paths;
- files present under the handoff root but absent from Git.

If a README intentionally points into the game project, declare that project
as a dependency root:

```sh
decomp-workbench handoff audit /path/to/public-proof-repo \
  --dependency-root /path/to/game-project
```

Resolving the path locally is not enough. The audit also asks Git whether the
dependency is tracked. A local-only `$PROJECT/tools/compiler/README.md` is
reported as `untracked-dependency`, because a fresh clone still cannot follow
it. Fix the handoff by publishing the provisioning recipe, linking its public
location, or replacing the dependency with a self-contained explanation.

Errors return exit `1`; invalid input returns `2`. `--json` emits the stable
`decomp-workbench-handoff-audit-v1` schema, and `--fail-on-warning` promotes a
non-Git-backed handoff warning to a failing gate.

Use repeatable `--exclude GLOB` only for a known generated or mirrored file
whose publication behavior has a separate test; exclusions are recorded in
the JSON report.

This is a publication check, not a decompilation oracle. A clean audit does
not prove function exactness, compiler provenance, or a matching project/ROM;
those remain separate evidence gates.
