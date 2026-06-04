"""First-run download of static ffmpeg/ffprobe builds."""

from __future__ import annotations

import io
import logging
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .runtime import bundled_tools_dir, exe_suffix, tool_filename

LogFn = Callable[[str], None]

# BtbN static GPL builds (Windows/Linux/macOS). macOS falls back to evermeet if needed.
BTBN_LATEST = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
EVERMEET_FFMPEG = "https://evermeet.cx/ffmpeg/getrelease/zip"
EVERMEET_FFPROBE = "https://evermeet.cx/ffprobe/getrelease/zip"


def _download(url: str, dest: Path, log: LogFn) -> None:
    log(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "MediaTool/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)


def _platform_archive() -> tuple[str, str]:
    machine = platform.machine().lower()

    if sys.platform == "win32":
        return f"{BTBN_LATEST}/ffmpeg-master-latest-win64-gpl.zip", "zip-btbn"
    if sys.platform == "darwin":
        if machine in {"arm64", "aarch64"}:
            return f"{BTBN_LATEST}/ffmpeg-master-latest-macosarm64-gpl.zip", "zip-btbn"
        return f"{BTBN_LATEST}/ffmpeg-master-latest-macos64-gpl.zip", "zip-btbn"
    if machine in {"aarch64", "arm64"}:
        return f"{BTBN_LATEST}/ffmpeg-master-latest-linuxarm64-gpl.tar.xz", "tar-xz-btbn"
    return f"{BTBN_LATEST}/ffmpeg-master-latest-linux64-gpl.tar.xz", "tar-xz-btbn"


def _extract_btbn_zip(data: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.endswith("/bin/ffmpeg") or n.endswith("/bin/ffprobe")]
        if not names:
            names = [n for n in zf.namelist() if n.endswith("ffmpeg") or n.endswith("ffprobe")]
        for name in names:
            base = Path(name).name
            if base not in {"ffmpeg", "ffprobe"}:
                continue
            out = dest / tool_filename(base)
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


def _evermeet_fallback(dest: Path, log: LogFn) -> None:
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


def ensure_ffmpeg_downloaded(
    log: Optional[LogFn] = None,
    logger: Optional[logging.Logger] = None,
) -> Path:
    """Download ffmpeg/ffprobe into the user tools dir if missing. Returns bin directory."""
    dest = bundled_tools_dir()
    ffmpeg = dest / tool_filename("ffmpeg")
    ffprobe = dest / tool_filename("ffprobe")
    if ffmpeg.is_file() and ffprobe.is_file():
        return dest

    emit: LogFn = log or (lambda msg: logger.info(msg) if logger else print(msg))

    emit("ffmpeg not found — downloading static build (first run only)…")
    url, kind = _platform_archive()
    tmp = dest.parent / "_download"
    tmp.mkdir(parents=True, exist_ok=True)
    archive = tmp / "ffmpeg-archive"

    try:
        _download(url, archive, emit)
        data = archive.read_bytes()
        if kind == "zip-btbn":
            try:
                _extract_btbn_zip(data, dest)
            except Exception:
                emit("BtbN archive failed; trying evermeet.cx fallback…")
                _evermeet_fallback(dest, emit)
        else:
            _extract_btbn_tar_xz(data, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError("ffmpeg download completed but binaries are missing.")

    emit(f"ffmpeg installed to {dest}")
    return dest
