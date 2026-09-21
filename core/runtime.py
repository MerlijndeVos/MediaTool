"""Runtime paths for development installs and PyInstaller bundles."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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


APP_DIRNAME = "Toolbox"
# Before version 3.0 the app was called Media Tool and kept its data in this folder.
LEGACY_APP_DIRNAME = "MediaTool"


def _migrate_legacy_data_dir(root: Path) -> None:
    """Move settings, mods and the ffmpeg cache over from the old folder, once.

    Only when the new folder does not exist yet, so a fresh install or an already-migrated
    profile is never touched. If the move fails (folder in use, permissions) the app simply
    starts fresh in the new folder and the old one is left as it was.
    """
    old, new = root / LEGACY_APP_DIRNAME, root / APP_DIRNAME
    if new.exists() or not old.is_dir():
        return
    try:
        old.rename(new)
    except OSError as exc:
        logger.warning("Could not move data from %s to %s: %s", old, new, exc)


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
    _migrate_legacy_data_dir(root)
    path = root / APP_DIRNAME
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
