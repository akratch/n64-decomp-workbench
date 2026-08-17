# Contributing

Contributions should make a late-stage decompilation investigation easier to
run, inspect, or reproduce without requiring copyrighted project inputs.

## Development setup

```sh
python3 -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m unittest discover -s tests -v
bandit -r src -ll
codespell README.md CHANGELOG.md CONTRIBUTING.md docs examples src tests
ruff check src tests
ruff format --check src tests
mypy src tests
```

The test runner is `unittest`, not pytest. pytest is not part of the dev
extras; install it separately if you want it.

The core package intentionally uses the Python standard library on Python 3.11
and newer; Python 3.10 installs `tomli` solely for compatible project-config
parsing. Keep optional integrations isolated and document their failure mode
when unavailable.

## Reporting an issue

Check [Troubleshooting](docs/troubleshooting.md) first. If the problem remains,
include the command, exit code, `decomp-workbench --version`, Python and host
versions, expected and actual behavior, and the smallest redistributable input
that reproduces it. For instrumentation problems, also include the upstream
commit, generated-source hash, enabled environment variables, and whether the
disabled-instrumentation fidelity check passed.

Do not attach ROMs, proprietary compiler binaries, complete generated compiler
sources, or project objects whose terms do not allow redistribution. Reduced
objdump text and synthetic traces are preferred.

## Design expectations

- Prefer small commands that compose through files and JSON.
- Never invoke user-supplied compiler commands through a shell.
- Keep exact verification separate from heuristic ranking.
- Refuse unknown generated compiler source instead of silently applying a
  version-specific patch.
- Prefer target-specific search scripts in their project repository. A
  self-contained walkthrough may live here when its inputs are redistributable,
  narrowly scoped, attributed, and clearly separated from synthetic fixtures.
- Add a synthetic or redistributable fixture for every parser and model.
- Record the origin and limits of compiler behavior claims.

## Adding an instrumentation profile

An instrumentation profile must include:

1. Upstream repository and commit.
2. SHA-256 of the unmodified generated source.
3. Exact, uniqueness-checked anchors.
4. A test that rejects a missing or duplicated anchor.
5. Environment variables and output format.
6. A disabled-instrumentation fidelity procedure.
7. Clear separation between tracing and behavior-changing controls.

Do not commit original compiler binaries or generated sources whose
redistribution terms are unclear.

Worked examples that include third-party source, generated context, or
assembly derived from a game binary need an explicit notice and a recorded
redistribution basis. Attribution or a public upstream repository alone is not
enough. If that basis cannot be recorded, commit a reproducible recipe and
synthetic metadata instead of the payload.

## Licensing

By contributing original material here, you agree to dedicate it under
[CC0 1.0 Universal](LICENSE.md). Do not submit third-party material unless its
terms permit that treatment and its provenance is documented.

Maintainers should complete the [release checklist](docs/release-checklist.md)
before tagging or publishing a distribution.
