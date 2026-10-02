# AGENTS.md

Guidance for AI coding agents working on `exquisite`. Human contributors
should read [docs/development.md](docs/development.md); what the tool does
is described in the [documentation](https://soliplex.github.io/exquisite/).
(`CLAUDE.md` is a thin stub that imports this file, so Claude Code loads it
automatically.)

## Commands

```bash
uv sync --group dev                    # add --group docs for the docs site
uv run pytest                          # unit tests, 100% branch coverage gate
uv run pytest --no-cov tests/unit/test_rules.py   # a subset: skip the gate
uv run ruff check
uv run ruff format --check
uv run pre-commit run --all-files      # the pre-commit hooks
uv run --group docs zensical serve     # preview docs/ locally
```

The coverage gate lives in `addopts`, so it applies to every `pytest` run,
and a partial run fails on it unless `--no-cov` is passed. Coverage covers
`src/exquisite` *and* `tests/unit`: test code is held to 100% too.

## Examples are public and generic

This is a public repository. Every example, test fixture, and piece of
documentation draws on public documents: ISO standards, NIST Special
Publications, IETF RFCs. Never take names, paths, filenames, counts, or
anecdotes from any private corpus, even in disguise.

## Code conventions

- **Imports are at module top level.** Never import inside a function.
  Ruff enforces this (`PLC0415`).
- **Import modules, not their attributes.** Write `import pathlib` and
  `pathlib.Path`, or `from exquisite import rules` and `rules.Rules`, never
  `from pathlib import Path`. Give a module a `_mod` alias only when its
  bare name is also a parameter or variable in that file, as with
  `rules_mod`, since `rules` is a parameter almost everywhere. Ruff enforces
  this (`ICN003`), but only for the modules listed in
  `[tool.ruff.lint.flake8-import-conventions] banned-from`. Add each new
  package module, and each newly used library, to that list.
- **The package's modules form a DAG,** with `cli` at the top. Keep the
  import graph acyclic, without resorting to deferred imports.
- **One exception class per error message** (ruff `TRY003`). The class
  builds the message from structured arguments, and subclasses the builtin
  it replaces (`FileNotFoundError`, `ValueError`, …), so existing `except`
  clauses keep working.
- Lines are at most 79 characters; imports are one per line.

## Test conventions

Unit tests live in `tests/unit/`, one module per source module.

- **Setup, act, assert.** Each test has a setup phase, then the single call
  under test, then the assertions, with a blank line between phases. Put
  the act on its own line (`result = thing(...)`) when assertions follow.
- **Exactly one act per test.** When a scenario would call the unit more
  than once, parametrize it or split it into separate tests.
- **No `autouse` fixtures.** Request fixtures by name, so each test's
  dependencies show in its signature. `tests/unit/conftest.py` provides
  `data_root`, an empty data repository; `tests/unit/_builders.py` writes
  question sets, manifests and worksheets into it.

## Normalization changes are versioned

Worksheets record a digest of the normalization rules in effect, and the
digest covers the built-ins (`exquisite/rules.py`). A change to what the
built-in rules produce, whether to their tables or to the logic in
`designators.py` and `worksheets.relation`, regroups designators in every
worksheet. So it is never made silently:

1. Add an entry to `rules.NORMALIZATION_CHANGES`, saying what changed and
   why. Its key becomes the new `NORMALIZATION_VERSION`.
2. Add the matching hash to `GOLDEN` in
   `tests/unit/test_normalization_golden.py`; the failing test reports it.
3. Update the pinned digest in `test_builtin_digest_is_pinned`.
4. Note in the release that worksheets regenerate on their next refresh, and
   that validated ones are flagged for re-validation.

Both `NORMALIZATION_CHANGES` and `GOLDEN` are append-only. Never edit or
remove an existing entry. Behaviour particular to one corpus belongs in
that data repository's `exquisite.yaml`, not in the built-ins.

## Docs and releases

- **Docs** are a Zensical docset in `docs/`, with `zensical.toml` for local
  preview only. The published site is built by `soliplex/soliplex.github.io`,
  which has this repository as a submodule and copies its `docs/`. It is
  rebuilt when `trigger-docs-deploy.yml` dispatches to it. Never enable GitHub Pages on
  this repository: a project's own Pages site shadows its path on the
  shared one.
- **Releases** follow `soliplex`: set the version in `pyproject.toml` (and
  check that `uv.lock` agrees), tag, and publish a GitHub release. That
  triggers `pypi.yaml`, which publishes with the organization's
  `PYPI_API_TOKEN`.

## Known gaps

- Paths are rendered with `str(...)`, so Windows is not yet supported or
  tested (#12).
- Citations using `§` as a location marker, or written location-first
  (`Section 8.3 of RFC 9110`), do not reduce to a correct designator. Both
  are among the golden test's samples, so fixing them is a normalization
  change (see above).
