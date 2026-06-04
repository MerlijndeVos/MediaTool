# Contributing

Thanks for your interest in Media Tool. New features should land in `core/` first, then get wired into the CLI and web API.

## Development setup

```powershell
git clone <repo-url> && cd media-tool
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[desktop,pack]"

cd web/frontend && npm install && npm run build
cd ../..
python app.py
```

## Project layout

| Path | Purpose |
|------|---------|
| `core/` | All media processing logic |
| `cli/` | Command-line interface |
| `web/server.py` | FastAPI app |
| `web/frontend/` | React UI |
| `web/jobs.py` | API job runner |
| `app.py` | Desktop entry point |
| `packaging/` | PyInstaller spec and installer scripts |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture.

## Adding a feature

1. Implement logic in `core/` with logging via the standard `logging` module (respects `core.progress` hooks).
2. Add CLI args in `cli/args.py` and register the handler in `cli/dispatch.py`.
3. Add a Pydantic params model in `web/schemas.py` and a job handler in `web/jobs.py`.
4. Add a form/panel in `web/frontend/src/components/ToolPanel.tsx` if the UI needs it.
5. Test via CLI and the desktop app.

## Frontend

```powershell
python -m web
cd web/frontend && npm run dev
```

Build before committing UI changes:

```powershell
cd web/frontend && npm run build
```

## Releases

Tag with semver (`v0.1.0`). GitHub Actions builds Windows, macOS, and Linux artifacts and publishes them to Releases.

Local Windows bundle:

```powershell
.\packaging\build.ps1
```

## Code style

- Match existing patterns in the file you edit.
- Keep `core/` free of web/CLI imports.
- Prefer focused diffs; avoid drive-by refactors.
- Python 3.11+ type hints where they clarify intent.

## Issues and PRs

Open an issue for large changes before starting work. PRs should describe what was tested (CLI command, UI flow, or packaging build).
