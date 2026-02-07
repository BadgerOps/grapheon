# Agent Notes

- Standard runtime is Python 3.12. Use `.python-version` and the Nix dev shell.
- Run all Python and npm commands via `nix develop`.
- After any code change, run `nix develop -c .venv/bin/python -m pytest`.
- Keep documentation in `docs/` and top-level README files in sync with behavior changes.
- Do not commit secrets or binary artifacts like `.env`, `*.xml`, databases, or pcaps.
- Graph export converters live in `backend/export_converters/`. Add new formats there and register endpoints in `routers/export.py`.
