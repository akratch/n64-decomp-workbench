# Release checklist

Use this checklist from the package root. It covers the redistributable
workbench; compiler and game inputs have separate fidelity gates.

## Source and metadata

1. Update `version` in `pyproject.toml`, `__version__` in
   `src/decomp_workbench/__init__.py`, and `CHANGELOG.md`.
2. Run:

   ```sh
   decomp-workbench handoff audit . --fail-on-warning \
     --exclude src/decomp_workbench/docs/field-guide.md
   ```

   The excluded file is a tested, byte-identical package-data mirror whose
   links belong to the canonical `docs/` copy. Then confirm each pinned
   external provenance link, which remains a network check.
3. Check the source tree for ROMs, objects, compiler binaries, credentials,
   absolute user paths, and generated build products.
4. Audit every attributed third-party example. Confirm the CV64 scratch
   payloads remain absent as required by
   [`examples/cv64/NOTICE.md`](../examples/cv64/NOTICE.md). Attribution,
   absence of a ROM file, and a public upstream repository are not substitutes
   for redistribution permission.
5. Review `git diff --check` and the complete staged diff.

## Automated checks

```sh
python -m unittest discover -s tests -v
bandit -r src -ll
codespell README.md CHANGELOG.md CONTRIBUTING.md docs examples src tests
actionlint .github/workflows/*.yml
ruff check src tests
ruff format --check src tests
mypy src tests
python -m build
python -m twine check dist/*
check-wheel-contents dist/*.whl
```

Run the test suite on every supported Python minor release. The repository
workflow covers Python 3.10 through 3.14 and builds both distribution formats.

Install the wheel and source distribution into separate empty environments.
For each one, run:

```sh
decomp-workbench --version
decomp-workbench compare-dumps \
  examples/fixtures/target.objdump \
  examples/fixtures/relocated-match.objdump \
  --fail-on-mismatch
decomp-workbench diagnose-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep --json
decomp-workbench doctor examples/fixtures/decompme-export --json
decomp-workbench check-scratch examples/fixtures/decompme-export --json
decomp-workbench trace-fifo examples/traces/ugen-fifo.log \
  --registers t6,t7,t8 \
  --fail-on-violation
decomp-workbench trace-source \
  examples/traces/oracle.log \
  examples/traces/oracle-source.i \
  --listing examples/traces/oracle-listing.s \
  --source-file candidate.c --json
decomp-workbench oracle plan examples/traces/oracle.log --json
decomp-workbench experiment validate \
  examples/experiments/statement-grouping/experiment.json --json
decomp-workbench commands --json
decomp-workbench project init . --json
```

Inspect both archives. The wheel should contain only the Python package and
license metadata, including the package-owned Agent Skill resources. The source
distribution should also contain the documentation, examples, and tests listed
by `MANIFEST.in`, including `.i` preprocessor fixtures. Install the skill from
each artifact into a temporary destination and validate its `SKILL.md`. Scan
both member lists for ROM/object/compiler extensions and inspect every
unexpected binary member.

Do not publish while an uncleared third-party payload is present in either
archive.

## Toolchain-dependent checks

Before claiming compatibility with a real workflow:

1. Compare one real MIPS object with itself using the intended GNU-compatible
   objdump. Confirm the symbol instruction count, relocation count, and
   `exact=true`.
2. Compile a small campaign through the actual project wrapper. Run it twice
   and confirm that the second pass uses the cache and that the JSONL ledger
   contains source, target, compiler, objdump, environment, and comparison
   provenance.
3. Generate each instrumentation profile from its pinned upstream source and
   compile the resulting host C.
4. Complete the disabled-instrumentation, positive-control, collateral, and
   project-output checks in
   [Compiler instrumentation](compiler-instrumentation.md#required-fidelity-gates).
5. Replay an unedited retained listing before interpreting any edited replay.

These checks require user-supplied toolchains and project inputs. They are not
substituted by the package's synthetic unit tests.

## Tag and publish

1. Build distributions from the exact clean commit to be tagged.
2. Create an annotated `vX.Y.Z` tag and verify that the documentation URLs in
   package metadata resolve at that tag.
3. Push the tag. `.github/workflows/release.yml` refuses a tag that differs
   from `pyproject.toml`, refuses development versions, rebuilds and checks both
   artifacts, then publishes them through the protected `pypi` environment and
   PyPI trusted publishing. Require manual approval on that environment and
   review it before approving the run. The official publisher also creates
   PEP 740 publish attestations for both artifacts by default; verify that the
   release files show those attestations on PyPI. See the official
   [PyPA publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
   and [PyPI attestation documentation](https://docs.pypi.org/attestations/producing-attestations/).
   For the first release, register a pending publisher with owner `akratch`,
   repository `n64-decomp-workbench`, workflow `release.yml`, and environment
   `pypi` before pushing the tag.
4. Install the published wheel in a new environment and rerun the smoke test.
5. Record artifact hashes and the published project URL in the release notes.
