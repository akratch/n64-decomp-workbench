# Agent skill

`n64-decomp-campaign` is a portable [Agent Skills](https://agentskills.io)
bundle for late-stage N64 decompilation. It packages the reusable evidence and
campaign workflow from the DKR and Star Fox 64 work without including ROMs,
compiler binaries, target objects, or game source.

The canonical, version-controlled bundle is
[`src/decomp_workbench/skills/n64-decomp-campaign`](../src/decomp_workbench/skills/n64-decomp-campaign).
Its `SKILL.md` uses only portable `name` and `description` frontmatter. The
adjacent `agents/openai.yaml` provides optional Codex UI metadata and is not
required by Claude Code. The skill ships in wheels and source distributions as
well as the repository checkout.

That directory is the *only* copy. `install-skill` ships exactly that tree, so
there is no second skill directory at the repository root to keep in sync — a
hollow one there would make the skill look empty to anyone browsing the
repository. A test enforces this: if a root-level `skills/` directory exists,
its contents must match the packaged bundle file for file.

## Install for Codex

```sh
decomp-workbench install-skill codex
```

The installer copies the bundled skill to the active Codex home, honors
`CODEX_HOME`, and refuses to overwrite a different existing skill. Start a new
Codex session, then invoke `$n64-decomp-campaign` or ask about a late-stage N64
mismatch naturally.

## Install for Claude Code

Claude Code supports the same Agent Skills directory structure. Install it
personally:

```sh
decomp-workbench install-skill claude
```

Or install it into one decomp project:

```sh
decomp-workbench install-skill claude --destination .claude/skills
```

Invoke `/n64-decomp-campaign` directly or let Claude select it for a relevant
request. Re-running the installer is safe when the installed copy is current.
If it differs, the command reports the exact path and leaves it untouched.

## What it covers

- evidence hierarchy and final-oracle discipline;
- classification of structural, allocator, relocation, and cross-ROM residuals;
- IDO lifetime, fake-local, loop-form, and force-probe experiments;
- combined `diagnose` evidence and the field-guide lever selection;
- persistent campaign status, hypotheses, resume, experiment manifests,
  selected regions, and object-basin interpretation;
- semantic web/source correlation and calibrated allocator oracle discipline;
- safe decomp.me export checking and site-faithful source composition;
- compiler-ID/language/frontend separation and switch-lowering probes;
- safe public proof artifacts, automated handoff audits, and a tooling-gap
  capture loop.
- project-config discovery that refuses ambiguous object guesses, executable
  `next` argv with expected signals, sealed compiler environments, and durable
  campaign source-retention policies;
- the late-stage loop and its guards: `ranking check` before work is ordered by
  a ranking, `permute-doctor` before a search, `permute-sweep` for the bounded
  search, `permute classify` for the wall class the search *measured*, the
  `ownership:` verdict line with `diagnose --trace` behind it, and
  `--built-from` / `check-staleness` so no exactness claim rests on a stale
  build. See [permuter sweeps](permute-sweep.md) and
  [the aligned mechanism view](view.md).

Use the workbench commands for actual comparison and trace analysis. The skill
teaches an agent which command/result is appropriate; it does not replace a
project's compiler, build, or verification tooling.
