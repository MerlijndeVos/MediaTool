# Architecture

Media Tool separates **business logic** from **front-ends**. Every feature is implemented once in `core/` and exposed through the CLI, HTTP API, and desktop app.

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop app (app.py / media-tool-app)                      │
│  pywebview window → http://127.0.0.1:<port>/app/            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│  Browser UI (optional)   │   React + Vite (web/frontend)     │
│  http://127.0.0.1:8765/app/  or dev server :5173            │
└──────────────────────────┼──────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼──────────────────────────────────┐
│  web/server.py — FastAPI                                      │
│  web/jobs.py   — background threads, job IDs, log streaming   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  core/                                                        │
│  convert · vts · rename · audio · download · rename_folders   │
│  tools · ffmpeg_bootstrap · progress · probe · paths          │
└──────────────────────────┬──────────────────────────────────┘
                           │ subprocess / filesystem
┌──────────────────────────▼──────────────────────────────────┐
│  ffmpeg · ffprobe · mkvmerge · yt-dlp (external)              │
└───────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  CLI (media-tool / python -m cli)                           │
│  cli/args.py → cli/dispatch.py → core.run_*                 │
└─────────────────────────────────────────────────────────────┘
```

## `core/`

| Module | Responsibility |
|--------|----------------|
| `convert.py` | Batch convert, trim, stitch |
| `vts.py` | DVD VIDEO_TS join |
| `rename.py` | Media library rename, dedup, undo journal |
| `rename_folders.py` | Date-stamp folder names from video filenames |
| `audio.py` | MKV default audio track |
| `download.py` | yt-dlp wrapper (CLI + cancellable API downloads) |
| `tools.py` | ffmpeg / MKVToolNix discovery, first-run bootstrap |
| `ffmpeg_bootstrap.py` | Download static ffmpeg builds per OS |
| `runtime.py` | Frozen-app paths, user data directory |
| `progress.py` | `on_log` / `on_progress` callbacks for any front-end |

`core` does not import FastAPI, React, pywebview, or argparse.

## `web/`

- **`server.py`** — REST endpoints, serves production React build at `/app/`
- **`jobs.py`** — Maps API jobs to `core` functions; SSE streams logs and progress
- **`schemas.py`** — Pydantic models (local paths, no upload)
- **`desktop.py`** — Starts uvicorn in a thread, opens pywebview
- **`desktop_api.py`** — Native file/folder dialogs for the React UI
- **`run.py`** — Shared port selection and uvicorn startup

Long-running work uses background threads with cancel support. The UI polls job status and subscribes to `/api/jobs/{id}/events`.

## `cli/`

- **`args.py`** — Subcommand definitions (mirrors API command set)
- **`dispatch.py`** — `command → core.run_*` table
- **`console.py`** — Installs console log/progress handlers via `core.progress`

## Packaging

PyInstaller `--onedir` bundles Python, dependencies, and `web/frontend/dist`. Per-OS installers are built in CI (Inno Setup, `.dmg`, AppImage). See `packaging/` and `.github/workflows/release.yml`.

## Design choices

- **Local paths only** — Large videos are never uploaded; the UI sends filesystem paths.
- **ffmpeg auto-download** — Reduces setup friction; MKVToolNix stays manual (hard to bundle cross-platform).
- **Unsigned installers** — Acceptable for friends/family; code signing can be added later.
- **Single repo** — Python backend and React frontend live together for simpler releases.
