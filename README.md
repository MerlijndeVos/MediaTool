<p align="center">
  <img src="packaging/icons/media-tool.png" alt="Media Tool" width="128" height="128" />
</p>

# Media Tool

Cross-platform desktop app for local video processing — convert, trim, stitch, organize libraries, download from YouTube, and more. Everything runs on your machine; nothing is uploaded.

**License:** [MIT](LICENSE)

## Features

| Tool | What it does |
|------|----------------|
| **Convert** | Batch-convert video (e.g. DV → H.264 MP4) with folder mirroring and optional NVENC |
| **Trim** | Cut seconds off the start/end of one file or a whole folder |
| **Stitch** | Join multiple clips end-to-end |
| **Download** | Save URLs as MP4 or MP3 via yt-dlp |
| **DVD (VTS)** | Join DVD `VIDEO_TS` VOB segments into MKV per title |
| **Rename** | Organize TV/movie files for Plex/Jellyfin-style libraries |
| **Audio** | Set default audio track in MKV files |
| **Dedup** | Strip `(2)` duplicate suffixes from filenames |
| **Folders** | Date-stamp subfolders (`2006 juli 13 - Holiday`) from video dates |

The UI includes drag-and-drop paths, live logs, per-job progress, dark mode, and native folder pickers in the desktop app.

## Install (end users)

Download the installer for your OS from **[GitHub Releases](https://github.com/MerlijndeVos/MediaTool/releases)** (tag `v0.1.0` or newer).

| Platform | File |
|----------|------|
| Windows | `MediaTool-Setup-*-win64.exe` |
| macOS | `MediaTool-*-macos.dmg` |
| Linux | `MediaTool-*-linux-*.AppImage` |

Installers are **unsigned**. Windows SmartScreen and macOS Gatekeeper may ask you to confirm once (“Run anyway” / “Open”).

**ffmpeg** is **not** included in the installer (keeps downloads small). On first launch the app downloads a one-time essentials build (~100 MB) into your user data folder. The app verifies the binaries run correctly and shows progress in the UI; use **Retry** if your OS or antivirus blocks them. Installers are unsigned — you may need to allow the app once, and on macOS check **System Settings → Privacy & Security** if ffmpeg is blocked after download.

## Run from source

Requires **Python 3.11+** and **Node.js 20+** (for building the UI).

```powershell
git clone https://github.com/MerlijndeVos/MediaTool.git
cd MediaTool
pip install -e ".[desktop]"
cd web/frontend && npm install && npm run build
cd ../..
python app.py
```

Equivalent entry points after install:

```powershell
media-tool-app          # desktop window
media-tool-web          # API + browser UI at http://127.0.0.1:8765/app/
media-tool convert --help   # CLI
```

### Dependency groups

| Group | Install | Use |
|-------|---------|-----|
| (default) | `pip install -e .` | CLI + yt-dlp |
| `web` | `pip install -e ".[web]"` | FastAPI server |
| `desktop` | `pip install -e ".[desktop]"` | pywebview app |
| `pack` | `pip install -e ".[pack]"` | PyInstaller (add to desktop for builds) |

All dependencies are declared in `pyproject.toml`.

### Web UI development

```powershell
# Terminal 1
pip install -e ".[web]"
python -m web

# Terminal 2
cd web/frontend && npm install && npm run dev
```

Open http://127.0.0.1:5173/app/ (Vite proxies `/api` to port 8765).

### Build installers locally

```powershell
pip install -e ".[desktop,pack]"
.\packaging\build.ps1
# → dist\MediaTool\MediaTool.exe
# Optional: iscc packaging\windows\setup.iss
```

Push a version tag to trigger CI builds for all three platforms:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Builds appear at https://github.com/MerlijndeVos/MediaTool/releases.

## Command line

Every feature is available as a subcommand. Examples:

```powershell
media-tool convert --input "C:\DV_in" --output "D:\DV_out"
media-tool vts --input "D:\DVD_rips" --output "E:\MKV_out" --dry-run
media-tool rename --input "Z:\Media" --dry-run
media-tool dedup --input "Z:\Media" --apply
media-tool download --url "https://youtu.be/…" --output "D:\Downloads"
media-tool trim --input "clip.mp4" --trim-start 10
media-tool stitch --input part1.mp4 --input part2.mp4 --output joined.mp4
media-tool rename_folders --root "D:\DV_out" --dry-run
```

Use `--help` on any subcommand for full options. GPU encoding (`--use-gpu auto|on|off`), CRF, presets, dry-run, and resume-safe output handling apply where relevant.

### External tools

| Tool | Required for | Notes |
|------|----------------|-------|
| ffmpeg / ffprobe | Convert, trim, stitch, VTS, download, audio default | Auto-downloaded on first app launch (or use a system install on PATH) |
| Node.js or Deno | YouTube downloads | Needed by yt-dlp for modern YouTube extraction |

## Architecture

Three layers share one `core/` library:

```
core/     ← all media logic (ffmpeg, yt-dlp, rename rules, …)
cli/      ← argparse → core
web/      ← FastAPI + React UI + pywebview desktop shell
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detail. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Built with

- [Python](https://python.org) 3.11 · [FastAPI](https://fastapi.tiangolo.com) · [uvicorn](https://www.uvicorn.org)
- [React](https://react.dev) · [Vite](https://vitejs.dev) · [Tailwind CSS](https://tailwindcss.com)
- [pywebview](https://pywebview.flowrl.com) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [ffmpeg](https://ffmpeg.org)
- [PyInstaller](https://pyinstaller.org) · GitHub Actions

## Legal

Only download or convert content you own or are licensed to use. YouTube downloads may violate YouTube’s Terms of Service if used on third-party content.
