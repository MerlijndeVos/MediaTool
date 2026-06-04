"""Check GitHub Releases and apply in-app updates for the packaged desktop app."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .runtime import app_data_dir, is_frozen

logger = logging.getLogger(__name__)

GITHUB_REPO = "MerlijndeVos/MediaTool"
GITHUB_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "MediaTool-updater"

UpdatePhase = Literal["idle", "downloading", "installing", "error"]

_quit_callback: Callable[[], None] | None = None
_lock = threading.Lock()
_state: dict = {
    "phase": "idle",
    "progress": 0.0,
    "message": "",
    "error": None,
}


def register_quit_callback(fn: Callable[[], None]) -> None:
    global _quit_callback
    _quit_callback = fn


def app_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("media-tool")
    except Exception:
        return "0.1.0"


def _parse_version(raw: str) -> tuple[int, int, int]:
    text = raw.strip().lstrip("vV")
    parts: list[int] = []
    for segment in text.split(".")[:3]:
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _linux_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine


def _asset_pattern() -> str:
    if sys.platform == "win32":
        return "-win64.exe"
    if sys.platform == "darwin":
        return "-macos.dmg"
    return f"-linux-{_linux_arch()}.AppImage"


def _pick_asset(assets: list[dict]) -> dict | None:
    pattern = _asset_pattern()
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.endswith(pattern) or (sys.platform == "linux" and name.endswith(".AppImage") and pattern.split("-linux-")[-1] in name):
            return asset
    if sys.platform == "linux":
        for asset in assets:
            name = str(asset.get("name", ""))
            if name.endswith(".AppImage"):
                return asset
    return None


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str | None
    update_available: bool
    can_install: bool
    download_url: str | None
    asset_name: str | None
    release_url: str | None
    release_notes: str | None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "can_install": self.can_install,
            "download_url": self.download_url,
            "asset_name": self.asset_name,
            "release_url": self.release_url,
            "release_notes": self.release_notes,
            "error": self.error,
        }


def check_for_update(timeout: float = 15.0) -> UpdateInfo:
    current = app_version()
    can_install = is_frozen()

    try:
        req = urllib.request.Request(
            GITHUB_LATEST,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateInfo(
                current_version=current,
                latest_version=None,
                update_available=False,
                can_install=can_install,
                download_url=None,
                asset_name=None,
                release_url=f"https://github.com/{GITHUB_REPO}/releases",
                release_notes=None,
                error="No published releases yet.",
            )
        return UpdateInfo(
            current_version=current,
            latest_version=None,
            update_available=False,
            can_install=can_install,
            download_url=None,
            asset_name=None,
            release_url=f"https://github.com/{GITHUB_REPO}/releases",
            release_notes=None,
            error=f"Could not check for updates (HTTP {exc.code}).",
        )
    except Exception as exc:
        logger.debug("Update check failed", exc_info=True)
        return UpdateInfo(
            current_version=current,
            latest_version=None,
            update_available=False,
            can_install=can_install,
            download_url=None,
            asset_name=None,
            release_url=f"https://github.com/{GITHUB_REPO}/releases",
            release_notes=None,
            error=f"Could not check for updates ({exc}).",
        )

    tag = str(payload.get("tag_name", "")).lstrip("vV")
    latest_version = tag or None
    asset = _pick_asset(list(payload.get("assets") or []))
    download_url = str(asset.get("browser_download_url")) if asset else None
    asset_name = str(asset.get("name")) if asset else None
    release_url = str(payload.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases")
    release_notes = str(payload.get("body") or "").strip() or None
    update_available = bool(latest_version and _is_newer(latest_version, current) and download_url)

    return UpdateInfo(
        current_version=current,
        latest_version=latest_version,
        update_available=update_available,
        can_install=can_install,
        download_url=download_url,
        asset_name=asset_name,
        release_url=release_url,
        release_notes=release_notes,
    )


def get_apply_status() -> dict:
    with _lock:
        return dict(_state)


def _set_state(
    *,
    phase: UpdatePhase | None = None,
    progress: float | None = None,
    message: str | None = None,
    error: str | None = None,
    clear_error: bool = False,
) -> None:
    with _lock:
        if phase is not None:
            _state["phase"] = phase
        if progress is not None:
            _state["progress"] = progress
        if message is not None:
            _state["message"] = message
        if clear_error:
            _state["error"] = None
        if error is not None:
            _state["error"] = error


def _download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        chunk_size = 256 * 1024
        with dest.open("wb") as out:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                read += len(chunk)
                if total > 0:
                    pct = min(99.0, (read / total) * 100.0)
                    _set_state(
                        progress=pct,
                        message=f"Downloading update… {pct:.0f}%",
                    )


def _launch_installer(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(
            [
                str(path),
                "/VERYSILENT",
                "/CLOSEAPPLICATIONS",
                "/RESTARTAPPLICATIONS",
            ],
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], close_fds=True)
        return

    path.chmod(path.stat().st_mode | 0o111)
    subprocess.Popen([str(path)], close_fds=True, start_new_session=True)


def _quit_app() -> None:
    if _quit_callback is not None:
        try:
            _quit_callback()
            return
        except Exception:
            logger.debug("Quit callback failed", exc_info=True)
    os._exit(0)


def _apply_update_worker(info: UpdateInfo) -> None:
    if not info.download_url or not info.asset_name:
        _set_state(phase="error", error="No installer found for this platform.")
        return

    cache_dir = app_data_dir() / "updates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / info.asset_name

    try:
        _set_state(phase="downloading", progress=0.0, message="Downloading update…", clear_error=True)
        _download_file(info.download_url, dest)
        _set_state(phase="installing", progress=100.0, message="Launching installer…")
        _launch_installer(dest)
        threading.Timer(1.0, _quit_app).start()
    except Exception as exc:
        logger.exception("Update apply failed")
        _set_state(phase="error", error=str(exc))


def start_apply_update(info: UpdateInfo) -> tuple[bool, str | None]:
    if not is_frozen():
        return False, "In-app updates are only available in the installed desktop app."
    if not info.update_available or not info.download_url:
        return False, "No update is available."

    with _lock:
        if _state["phase"] in {"downloading", "installing"}:
            return False, "An update is already in progress."

    thread = threading.Thread(target=_apply_update_worker, args=(info,), daemon=True, name="media-tool-update")
    thread.start()
    return True, None
