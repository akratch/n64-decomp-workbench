# Agent skill

`n64-decomp-campaign` is a portable [Agent Skills](https://agentskills.io)
bundle for late-stage N64 decompilation. It packages the reusable evidence and
campaign workflow from the DKR and Star Fox 64 work without including ROMs,
compiler binaries, target objects, or game source.

The canonical, version-controlled bundle is
[`skills/n64-decomp-campaign`](../skills/n64-decomp-campaign). Its `SKILL.md`
uses only portable `name` and `description` frontmatter. The adjacent
`agents/openai.yaml` provides optional Codex UI metadata and is not required by
Claude Code.

## Install for Codex

Copy or symlink the skill directory into your Codex skills directory. For a
checkout at `/path/to/n64-decomp-workbench`:

```sh
mkdir -p ~/.codex/skills
ln -s /path/to/n64-decomp-workbench/skills/n64-decomp-campaign \
  ~/.codex/skills/n64-decomp-campaign
```

Start a new Codex session, then invoke `$n64-decomp-campaign` or ask about a
late-stage N64 mismatch naturally.

## Install for Claude Code

Claude Code supports the same Agent Skills directory structure. Install it
personally or per project:

```sh
# Personal
mkdir -p ~/.claude/skills
ln -s /path/to/n64-decomp-workbench/skills/n64-decomp-campaign \
  ~/.claude/skills/n64-decomp-campaign

# Or, from a decomp project's root, make it project-local
mkdir -p .claude/skills
ln -s /path/to/n64-decomp-workbench/skills/n64-decomp-campaign \
  .claude/skills/n64-decomp-campaign
```

Invoke `/n64-decomp-campaign` directly or let Claude select it for a relevant
request. Claude Code discovers project skills from `.claude/skills/`; a
symlink keeps the installed skill aligned with this repository's updates.

## What it covers

- evidence hierarchy and final-oracle discipline;
- classification of structural, allocator, relocation, and cross-ROM residuals;
- IDO lifetime, fake-local, loop-form, and force-probe experiments;
- reproducible candidate campaigns and object-basin interpretation;
- safe public proof artifacts and a tooling-gap capture loop.

Use the workbench commands for actual comparison and trace analysis. The skill
teaches an agent which command/result is appropriate; it does not replace a
project's compiler, build, or verification tooling.
