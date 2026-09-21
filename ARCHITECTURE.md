# Architecture

Toolbox separates **business logic** from **front-ends**. Every feature is implemented once in `core/` and exposed through the CLI, HTTP API, and desktop app.

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop app (app.py / toolbox-app)                      │
│  pywebview window → http://127.0.0.1:<port>/app/            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│  Browser UI (optional)   │   React + Vite (web/frontend)    │
│  http://127.0.0.1:8765/app/  or dev server :5173            │
└──────────────────────────┼──────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼──────────────────────────────────┐
│  web/server.py — FastAPI                                    │
│  web/jobs.py   — background threads, job IDs, log streaming │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  core/                                                      │
│  convert · vts · rename · audio · download · rename_folders │
│  tools · ffmpeg_bootstrap · progress · probe · paths        │
└──────────────────────────┬──────────────────────────────────┘
                           │ subprocess / filesystem
┌──────────────────────────▼──────────────────────────────────┐
│  ffmpeg · ffprobe · yt-dlp (ffmpeg first-run download)      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CLI (toolbox / python -m cli)                           │
│  cli/args.py → cli/dispatch.py → core.run_*                 │
└─────────────────────────────────────────────────────────────┘
```

## `core/`

| Module | Responsibility |
|--------|----------------|
| `convert.py` | Batch convert, trim, stitch |
| `vts.py` | DVD VIDEO_TS join |
| `rename.py` | Media library rename (shows/movies), dedup, undo journal |
| `rename_profiles.py` | Format profiles: cleanup rules, name patterns, saved-profile store |
| `rename_generic.py` | Folders mode: rename folders/files in place with a profile |
| `rename_ai.py` | AI-generated profiles from before/after examples (verified, never renames) |
| `openai_client.py` | Shared OpenAI key/model settings |
| `rename_folders.py` | Date-stamp folder names from video filenames |
| `audio.py` | MKV default audio track |
| `download.py` | yt-dlp wrapper (CLI + cancellable API downloads) |
| `tools.py` | ffmpeg discovery, background first-run bootstrap + verify |
| `ffmpeg_bootstrap.py` | Download static ffmpeg builds per OS |
| `runtime.py` | Frozen-app paths, user data directory |
| `progress.py` | `on_log` / `on_progress` callbacks for any front-end |
| `mods/` | The mod system: manifest parser, registry (built-in + user mods), the `ctx` a mod receives |

`core` does not import FastAPI, React, pywebview, or argparse.

## `web/`

- **`server.py`** — REST endpoints, serves production React build at `/app/`
- **`jobs.py`** — Runs any mod as a background job (concurrency limit, cancel, undo); SSE streams logs and progress
- **`mod_params.py`** — Builds each mod's request-validation model from its manifest (or its own `Params`)
- **`schemas.py`** — Pydantic models (local paths, no upload)
- **`desktop.py`** — Starts uvicorn in a thread, opens pywebview
- **`desktop_api.py`** — Native file/folder dialogs for the React UI
- **`run.py`** — Shared port selection and uvicorn startup

Long-running work uses background threads with cancel support. The UI polls job status and subscribes to `/api/jobs/{id}/events`.

## `cli/`

- **`args.py`** — Subcommand definitions for the built-in features
- **`dispatch.py`** — `command → core.run_*` table
- **`mods_cli.py`** — `toolbox mods ...` and one generated subcommand per enabled user mod
- **`console.py`** — Installs console log/progress handlers via `core.progress`

## Mods

Every feature is a **mod**: a folder with a `mod.toml` manifest (name, group, parameters, ...)
and a `main.py` with `run(params, ctx)`. Toolbox's own features live in `builtin_mods/`;
users can add more under `<app data>/mods/` (off until enabled). See [MODDING.md](MODDING.md).

```
builtin_mods/<id>/   mod.toml + main.py        (ship with the app, always on)
<app data>/mods/<id>/  mod.toml + main.py      (user mods, opt-in, skipped in safe mode)
        │
core/mods/registry.py   discovers manifests (never runs mod code), imports main.py on first use
        │
web/mod_params.py       manifest [[params]] → pydantic model   ─┐
web/jobs.py             validate → mod.run(params, ctx)          ├─ /api/jobs, /api/mods, /api/commands
web/frontend            /api/mods → nav, home tiles, generated ModForm (or a built-in custom panel)
cli/mods_cli.py         manifest [[params]] → argparse flags (user mods; built-ins keep cli/args.py)
```

The built-in mods are thin wrappers around the `core` functions. Features whose form is too
rich for a manifest (Stitch, Download, Rename, the subtitle tools) set `[ui] kind = "builtin"`
to use a React panel that ships with the app and export their own `Params` model; only
built-in mods may do that. Mods run in the app's own process on a job thread.

## Packaging

PyInstaller `--onedir` bundles Python, dependencies, `web/frontend/dist` and `builtin_mods/`. Per-OS installers are built in CI (Inno Setup, `.dmg`, AppImage). See `packaging/` and `.github/workflows/release.yml`.

## Design choices

- **Local paths only** — Large videos are never uploaded; the UI sends filesystem paths.
- **ffmpeg first-run download** — Keeps installers small; downloads essentials builds, verifies they run, clears macOS quarantine / Windows MOTW, with UI progress and retry.
- **Unsigned installers** — Acceptable for friends/family; code signing can be added later.
- **Single repo** — Python backend and React frontend live together for simpler releases.
