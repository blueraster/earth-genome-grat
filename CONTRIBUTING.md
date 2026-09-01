# Contributing

## Setup

```bash
uv sync
```

This installs runtime and dev dependencies into a local `.venv`.

## Workflow

1. Create a branch for your change.
2. Make the change, with tests in `tests/`.
3. Run the checks before opening a PR:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   ```

4. Open a pull request describing the change and, if user-facing, add an entry
   to [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`.

## Code style

- Formatting and linting are enforced by [ruff](https://docs.astral.sh/ruff/).
- Public functions and classes should have type annotations (checked by mypy
  in strict mode).
