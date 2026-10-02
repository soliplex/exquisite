# Development

```bash
uv sync --group dev
uv run pytest            # unit tests, with a 100% branch-coverage gate
uv run ruff check
uv run ruff format --check
uv run pre-commit install    # optional:  run the same checks on commit
uv run --group docs zensical serve    # preview these docs locally
```

The coverage gate applies to every `pytest` run, so pass `--no-cov` when
running a subset, e.g. `uv run pytest --no-cov tests/unit/test_rules.py`.
