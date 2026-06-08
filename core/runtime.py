"""Runtime paths for development installs and PyInstaller bundles."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory containing bundled read-only assets (``_MEIPASS`` when frozen)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """Directory containing the running executable (useful when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return resource_root()


def app_data_dir() -> Path:
    """Writable per-user data directory (cached ffmpeg, logs, etc.)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    path = root / "MediaTool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_bundled_tools_dir() -> Path:
    """Directory where the installer ships ffmpeg/ffprobe (PyInstaller onedir)."""
    return install_root() / "tools" / "bin"


def bundled_tools_dir() -> Path:
    """Directory where first-run ffmpeg downloads are stored."""
    path = app_data_dir() / "tools" / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frontend_dist_dir() -> Path:
    return resource_root() / "web" / "frontend" / "dist"


def exe_suffix() -> str:
    return ".exe" if sys.platform == "win32" else ""


def tool_filename(name: str) -> str:
    return f"{name}{exe_suffix()}"
