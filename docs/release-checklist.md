# Release checklist

Use this checklist from the package root. It covers the redistributable
workbench; compiler and game inputs have separate fidelity gates.

## Source and metadata

1. Update `version` in `pyproject.toml`, `__version__` in
   `src/decomp_workbench/__init__.py`, and `CHANGELOG.md`.
2. Confirm every local Markdown link and each pinned external provenance link.
3. Check the source tree for ROMs, objects, compiler binaries, credentials,
   absolute user paths, and generated build products.
4. Review `git diff --check` and the complete staged diff.

## Automated checks

```sh
python -m unittest discover -s tests -v
bandit -r src -ll
codespell README.md CHANGELOG.md CONTRIBUTING.md case-studies docs examples research-archive src tests
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
```

Inspect both archives. The wheel should contain only the Python package and
license metadata. The source distribution should also contain the
documentation, examples, and tests listed by `MANIFEST.in`.

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
2. Create an annotated version tag and verify that the documentation URLs in
   package metadata resolve at that tag.
3. Publish only the artifacts built from the tagged commit.
4. Install the published wheel in a new environment and rerun the smoke test.
5. Record artifact hashes and the published project URL in the release notes.
