"""First-run download of ffmpeg/ffprobe builds sized for Toolbox."""

from __future__ import annotations

import io
import logging
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .runtime import bundled_tools_dir, exe_suffix, tool_filename
from .subprocess_utils import no_window_kwargs

LogFn = Callable[[str], None]

# Essentials / evermeet include libx264, NVENC, AAC, etc.
GYAN_WINDOWS_ESSENTIALS = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
BTBN_LATEST = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
EVERMEET_FFMPEG = "https://evermeet.cx/ffmpeg/getrelease/zip"
EVERMEET_FFPROBE = "https://evermeet.cx/ffprobe/getrelease/zip"


def _download(url: str, dest: Path, log: LogFn) -> None:
    log(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Toolbox/0.1"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    dest.write_bytes(data)


def _platform_archive() -> tuple[str, str]:
    """Return (download_url, archive_kind) for the current platform."""
    machine = platform.machine().lower()

    if sys.platform == "win32":
        return GYAN_WINDOWS_ESSENTIALS, "zip-tools"
    if sys.platform == "darwin":
        return "", "evermeet"
    if machine in {"aarch64", "arm64"}:
        return f"{BTBN_LATEST}/ffmpeg-master-latest-linuxarm64-gpl.tar.xz", "tar-xz-btbn"
    return f"{BTBN_LATEST}/ffmpeg-master-latest-linux64-gpl.tar.xz", "tar-xz-btbn"


def _extract_tools_zip(data: bytes, dest: Path) -> None:
    """Extract ffmpeg/ffprobe from a zip with a .../bin/ layout (gyan, BtbN)."""
    wanted = {tool_filename("ffmpeg"), tool_filename("ffprobe"), "ffmpeg", "ffprobe"}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            base = Path(name).name
            if base not in wanted:
                continue
            tool = "ffmpeg" if base.startswith("ffmpeg") else "ffprobe"
            out = dest / tool_filename(tool)
            out.write_bytes(zf.read(name))
            if exe_suffix() == "":
                out.chmod(0o755)


def _extract_btbn_tar_xz(data: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tf:
        for member in tf.getmembers():
            if member.name.endswith("/bin/ffmpeg") or member.name.endswith("/bin/ffprobe"):
                base = Path(member.name).name
                out = dest / tool_filename(base)
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                out.write_bytes(extracted.read())
                out.chmod(0o755)


def _extract_evermeet_zip(data: bytes, dest: Path, tool: str) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(tool):
                out = dest / tool_filename(tool)
                out.write_bytes(zf.read(name))
                if exe_suffix() == "":
                    out.chmod(0o755)
                return
    raise RuntimeError(f"{tool} not found in evermeet archive")


def _evermeet_download(dest: Path, log: LogFn) -> None:
    tmp = dest.parent / "_download"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg_zip = tmp / "ffmpeg.zip"
        ffprobe_zip = tmp / "ffprobe.zip"
        _download(EVERMEET_FFMPEG, ffmpeg_zip, log)
        _download(EVERMEET_FFPROBE, ffprobe_zip, log)
        _extract_evermeet_zip(ffmpeg_zip.read_bytes(), dest, "ffmpeg")
        _extract_evermeet_zip(ffprobe_zip.read_bytes(), dest, "ffprobe")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _unblock_windows(path: Path) -> None:
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Unblock-File -LiteralPath '{path}'",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
            **no_window_kwargs(),
        )
    except Exception:
        pass


def prepare_downloaded_tools(dest: Path) -> None:
    """Make downloaded binaries runnable on unsigned / first-run installs."""
    for name in ("ffmpeg", "ffprobe"):
        tool = dest / tool_filename(name)
        if not tool.is_file():
            continue
        if sys.platform != "win32":
            tool.chmod(0o755)
        if sys.platform == "darwin":
            subprocess.run(
                ["xattr", "-cr", str(tool)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        elif sys.platform == "win32":
            _unblock_windows(tool)


def _run_failure_hint(tool: str, exc: BaseException) -> str:
    if sys.platform == "darwin":
        return (
            f"{tool} could not run ({exc}). macOS may block unsigned downloads: "
            "open System Settings → Privacy & Security and allow it, or try Retry."
        )
    if sys.platform == "win32":
        return (
            f"{tool} could not run ({exc}). Windows or your antivirus may have blocked "
            "the download — check protection history, allow ffmpeg, then Retry."
        )
    return f"{tool} could not run: {exc}"


def verify_tools(ffmpeg_path: str, ffprobe_path: str) -> tuple[bool, str]:
    """Run -version on both binaries; return (ok, error_message)."""
    for label, path in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)):
        if not path:
            return False, f"{label} path is missing."
        try:
            result = subprocess.run(
                [path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
                check=False,
                **no_window_kwargs(),
            )
        except OSError as exc:
            return False, _run_failure_hint(label, exc)
        except subprocess.TimeoutExpired:
            return False, f"{label} timed out while starting."
        if result.returncode != 0:
            detail = (result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit code {result.returncode}"
            return False, f"{label} failed to start: {tail}"
    return True, ""


def remove_downloaded_tools(dest: Path) -> None:
    for name in ("ffmpeg", "ffprobe"):
        tool = dest / tool_filename(name)
        if tool.is_file():
            tool.unlink()


def ensure_ffmpeg_at(
    dest: Path,
    log: Optional[LogFn] = None,
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Download ffmpeg/ffprobe into dest if missing. Returns bin directory."""
    dest.mkdir(parents=True, exist_ok=True)
    ffmpeg = dest / tool_filename("ffmpeg")
    ffprobe = dest / tool_filename("ffprobe")

    emit: LogFn = log or (lambda msg: logger.info(msg) if logger else print(msg))

    if ffmpeg.is_file() and ffprobe.is_file():
        prepare_downloaded_tools(dest)
        ok, err = verify_tools(str(ffmpeg), str(ffprobe))
        if ok:
            return dest
        emit(f"Existing ffmpeg failed verification — re-downloading ({err})")
        remove_downloaded_tools(dest)

    emit("Downloading ffmpeg (first run, one-time ~100 MB)…")
    url, kind = _platform_archive()
    tmp = dest.parent / "_download"
    tmp.mkdir(parents=True, exist_ok=True)
    archive = tmp / "ffmpeg-archive"

    try:
        if kind == "evermeet":
            _evermeet_download(dest, emit)
        else:
            _download(url, archive, emit)
            data = archive.read_bytes()
            if kind == "zip-tools":
                _extract_tools_zip(data, dest)
            elif kind == "zip-btbn":
                try:
                    _extract_tools_zip(data, dest)
                except Exception:
                    emit("Archive extraction failed; trying evermeet.cx fallback…")
                    _evermeet_download(dest, emit)
            else:
                _extract_btbn_tar_xz(data, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError("ffmpeg download completed but binaries are missing.")

    prepare_downloaded_tools(dest)
    ok, err = verify_tools(str(ffmpeg), str(ffprobe))
    if not ok:
        remove_downloaded_tools(dest)
        raise RuntimeError(err)

    emit(f"ffmpeg installed to {dest}")
    return dest


def ensure_ffmpeg_downloaded(
    log: Optional[LogFn] = None,
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Download ffmpeg/ffprobe into the user tools dir if missing. Returns bin directory."""
    return ensure_ffmpeg_at(bundled_tools_dir(), log=log, logger=logger)
