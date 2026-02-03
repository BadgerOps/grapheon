# Contributing

Thanks for contributing. This repo standardizes on Python 3.12 and the Nix dev shell.

## Development Setup

```bash
nix develop
```

## Running the App

```bash
nix develop -c bash -lc "cd backend && uvicorn main:app --reload"
```

```bash
nix develop -c bash -lc "cd frontend && npm run dev"
```

## Tests and Lint

```bash
nix develop -c .venv/bin/python -m pytest
```

```bash
nix develop -c .venv/bin/ruff check backend
```

## Pull Requests

- Keep changes focused and describe the motivation.
- Update docs in `docs/` and top-level README files when behavior changes.
- Let CI run all checks before requesting review.

## Data and Secrets

- Do not commit `.env` files.
- Do not commit scan outputs like `*.xml` or binary artifacts like `.db` or `.pcap`.
