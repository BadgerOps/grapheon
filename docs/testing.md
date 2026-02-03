# Graphēon Testing

Tests are run with pytest under Python 3.12. Use the Nix dev shell for all Python commands.

## Run All Backend Tests

```bash
nix develop -c .venv/bin/python -m pytest
```

## Linting

```bash
nix develop -c .venv/bin/ruff check backend
```

## Notes

- Parser tests live in `backend/tests/` and `backend/test_parsers.py`.
- The frontend currently has no unit test runner configured.
