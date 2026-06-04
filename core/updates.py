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
from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal

from .runtime import app_data_dir, is_frozen, resource_root
from .version import app_version

logger = logging.getLogger(__name__)

GITHUB_REPO = "MerlijndeVos/MediaTool"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}"
GITHUB_LATEST = f"{GITHUB_API}/releases/latest"
USER_AGENT = "MediaTool-updater"
TOKEN_ENV_VARS = ("MEDIA_TOOL_GITHUB_TOKEN", "GITHUB_TOKEN")
TOKEN_FILENAME = "github_token"

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


@lru_cache(maxsize=1)
def get_github_token() -> str | None:
    """Read-only token for private release checks (env, app data, or CI-bundled file)."""
    for key in TOKEN_ENV_VARS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    for path in _token_file_paths():
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            logger.debug("Could not read token file %s", path, exc_info=True)
    return None


def _token_file_paths() -> tuple[Path, ...]:
    bundled = resource_root() / TOKEN_FILENAME
    return (app_data_dir() / TOKEN_FILENAME, bundled)


def _github_headers(*, for_download: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/octet-stream" if for_download else "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_get(url: str, timeout: float) -> tuple[int, dict | None, str | None]:
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return exc.code, None, body
    except Exception as exc:
        return -1, None, str(exc)


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
        if name.endswith(pattern) or (
            sys.platform == "linux"
            and name.endswith(".AppImage")
            and pattern.split("-linux-")[-1] in name
        ):
            return asset
    if sys.platform == "linux":
        for asset in assets:
            name = str(asset.get("name", ""))
            if name.endswith(".AppImage"):
                return asset
    return None


def _asset_download_url(asset: dict) -> str | None:
    asset_id = asset.get("id")
    if asset_id is not None and get_github_token():
        return f"{GITHUB_API}/releases/assets/{int(asset_id)}"
    url = asset.get("browser_download_url")
    return str(url) if url else None


def _releases_error_message(http_code: int, *, has_token: bool) -> str:
    if http_code == 401:
        return "GitHub token was rejected. Replace it and try again."
    if http_code == 403:
        return "GitHub token cannot read releases. It needs repository read access."
    if http_code == 404:
        if not has_token:
            return (
                "Cannot reach releases on this private repository. "
                "Add a read-only GitHub token (see CONTRIBUTING.md)."
            )
        return "No published releases yet."
    if http_code > 0:
        return f"Could not check for updates (HTTP {http_code})."
    return "Could not check for updates (network error)."


def _status_message(
    *,
    current: str,
    latest_version: str | None,
    update_available: bool,
    download_url: str | None,
    error: str | None,
) -> str | None:
    if error:
        return None
    if update_available:
        return None
    if latest_version and _is_newer(latest_version, current) and not download_url:
        return f"v{latest_version} is available — no installer for this platform on the release."
    if latest_version and not _is_newer(latest_version, current):
        return "You're up to date."
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
    status_message: str | None = None
    authenticated: bool = False

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
            "status_message": self.status_message,
            "authenticated": self.authenticated,
        }


def _base_info(current: str, can_install: bool, *, authenticated: bool) -> dict:
    return {
        "current_version": current,
        "can_install": can_install,
        "authenticated": authenticated,
        "release_url": f"https://github.com/{GITHUB_REPO}/releases",
    }


def check_for_update(timeout: float = 15.0) -> UpdateInfo:
    current = app_version()
    can_install = is_frozen()
    has_token = bool(get_github_token())

    status, payload, err_body = _github_get(GITHUB_LATEST, timeout)
    if status != 200 or not payload:
        error = _releases_error_message(status, has_token=has_token)
        if status not in {401, 403, 404} and err_body:
            logger.debug("Update check failed: %s", err_body[:500])
        base = _base_info(current, can_install, authenticated=has_token)
        return UpdateInfo(
            **base,
            latest_version=None,
            update_available=False,
            download_url=None,
            asset_name=None,
            release_notes=None,
            error=error,
            status_message=None,
        )

    tag = str(payload.get("tag_name", "")).lstrip("vV")
    latest_version = tag or None
    asset = _pick_asset(list(payload.get("assets") or []))
    download_url = _asset_download_url(asset) if asset else None
    asset_name = str(asset.get("name")) if asset else None
    release_url = str(payload.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases")
    release_notes = str(payload.get("body") or "").strip() or None
    update_available = bool(latest_version and _is_newer(latest_version, current) and download_url)
    error = None
    status_message = _status_message(
        current=current,
        latest_version=latest_version,
        update_available=update_available,
        download_url=download_url,
        error=error,
    )

    return UpdateInfo(
        current_version=current,
        latest_version=latest_version,
        update_available=update_available,
        can_install=can_install,
        download_url=download_url,
        asset_name=asset_name,
        release_url=release_url,
        release_notes=release_notes,
        error=error,
        status_message=status_message,
        authenticated=has_token,
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
    headers = {"User-Agent": USER_AGENT}
    if get_github_token() and "api.github.com" in url:
        headers = _github_headers(for_download=True)
    req = urllib.request.Request(url, headers=headers)
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
    if not get_github_token() and info.download_url.startswith("https://api.github.com/"):
        _set_state(
            phase="error",
            error="A GitHub token is required to download updates from a private repository.",
        )
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
    if info.download_url.startswith("https://api.github.com/") and not get_github_token():
        return (
            False,
            "A GitHub token is required to install updates from a private repository.",
        )

    with _lock:
        if _state["phase"] in {"downloading", "installing"}:
            return False, "An update is already in progress."

    thread = threading.Thread(target=_apply_update_worker, args=(info,), daemon=True, name="media-tool-update")
    thread.start()
    return True, None
