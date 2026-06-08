"""Discovery and capability probing for external tools.

Locates ffmpeg/ffprobe (downloaded on first run or on PATH) and probes ffmpeg's
NVENC capabilities.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from .config import NVENC_AQ_STRENGTH, NVENC_CQ_TARGET
from .ffmpeg_bootstrap import ensure_ffmpeg_downloaded, remove_downloaded_tools, verify_tools
from .runtime import bundled_tools_dir, install_bundled_tools_dir, tool_filename


class BootstrapPhase(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    READY = "ready"
    FAILED = "failed"


_bootstrap_lock = threading.Lock()
_bootstrap_thread: Optional[threading.Thread] = None
_bootstrap_phase = BootstrapPhase.IDLE
_bootstrap_message = ""
_bootstrap_error: Optional[str] = None
_verified_pair: Optional[tuple[str, str]] = None


def _set_bootstrap_state(
    phase: BootstrapPhase,
    message: str = "",
    error: Optional[str] = None,
) -> None:
    global _bootstrap_phase, _bootstrap_message, _bootstrap_error
    with _bootstrap_lock:
        _bootstrap_phase = phase
        _bootstrap_message = message
        _bootstrap_error = error


def get_bootstrap_state() -> dict:
    with _bootstrap_lock:
        return {
            "phase": _bootstrap_phase.value,
            "message": _bootstrap_message,
            "error": _bootstrap_error,
        }


def _tool_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    install_bin = install_bundled_tools_dir()
    if install_bin.is_dir():
        dirs.append(install_bin)
    dirs.append(bundled_tools_dir())
    return dirs


def _prepend_tools_path() -> None:
    path = os.environ.get("PATH", "")
    existing = set(path.split(os.pathsep))
    prefix: list[str] = []
    for tools_bin in _tool_search_dirs():
        entry = str(tools_bin)
        if entry not in existing:
            prefix.append(entry)
            existing.add(entry)
    if prefix:
        os.environ["PATH"] = os.pathsep.join(prefix) + os.pathsep + path


def _find_tool(name: str) -> tuple[Optional[str], str]:
    filename = tool_filename(name)
    for tools_bin in _tool_search_dirs():
        candidate = tools_bin / filename
        if candidate.is_file():
            return str(candidate), "bundled"
    found = shutil.which(name)
    if found:
        return found, "path"
    return None, "none"


def _invalidate_verify_cache() -> None:
    global _verified_pair
    _verified_pair = None


def _mark_tools_ready(ffmpeg_path: str, ffprobe_path: str) -> None:
    global _verified_pair
    _verified_pair = (ffmpeg_path, ffprobe_path)
    _set_bootstrap_state(BootstrapPhase.READY, "ffmpeg is ready.")


def _tools_ready() -> bool:
    """Return True when ffmpeg/ffprobe are present and last verification succeeded."""
    global _verified_pair
    _prepend_tools_path()
    ffmpeg_path, _ = _find_tool("ffmpeg")
    ffprobe_path, _ = _find_tool("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        _verified_pair = None
        return False
    pair = (ffmpeg_path, ffprobe_path)
    if _verified_pair == pair:
        return True
    ok, _ = verify_tools(ffmpeg_path, ffprobe_path)
    if ok:
        _verified_pair = pair
        return True
    _verified_pair = None
    return False


def _bootstrap_worker() -> None:
    try:
        _set_bootstrap_state(BootstrapPhase.CHECKING, "Checking for ffmpeg…")
        if _tools_ready():
            return

        def emit(msg: str) -> None:
            _set_bootstrap_state(BootstrapPhase.DOWNLOADING, msg)

        ensure_ffmpeg_downloaded(log=emit)
        _prepend_tools_path()

        _set_bootstrap_state(BootstrapPhase.VERIFYING, "Verifying ffmpeg…")
        ffmpeg_path, _ = _find_tool("ffmpeg")
        ffprobe_path, _ = _find_tool("ffprobe")
        ok, err = verify_tools(ffmpeg_path or "", ffprobe_path or "")
        if not ok:
            raise RuntimeError(err or "ffmpeg verification failed.")

        _mark_tools_ready(ffmpeg_path or "", ffprobe_path or "")
    except Exception as exc:
        _set_bootstrap_state(
            BootstrapPhase.FAILED,
            "ffmpeg setup failed.",
            str(exc),
        )


def start_bootstrap_background() -> None:
    """Start a background first-run ffmpeg install if tools are not yet ready."""
    global _bootstrap_thread
    with _bootstrap_lock:
        if _bootstrap_phase in {BootstrapPhase.DOWNLOADING, BootstrapPhase.VERIFYING, BootstrapPhase.CHECKING}:
            return
        if _bootstrap_thread is not None and _bootstrap_thread.is_alive():
            return
        if _bootstrap_phase == BootstrapPhase.READY and _tools_ready():
            return

    if _tools_ready():
        return

    with _bootstrap_lock:
        _bootstrap_thread = threading.Thread(
            target=_bootstrap_worker,
            daemon=True,
            name="ffmpeg-bootstrap",
        )
        _bootstrap_thread.start()


def retry_bootstrap_background() -> None:
    """Retry a failed or interrupted first-run ffmpeg install."""
    global _bootstrap_thread
    with _bootstrap_lock:
        if _bootstrap_thread is not None and _bootstrap_thread.is_alive():
            return
        _bootstrap_phase = BootstrapPhase.IDLE
        _bootstrap_error = None
    _invalidate_verify_cache()
    remove_downloaded_tools(bundled_tools_dir())
    start_bootstrap_background()


def bootstrap_ffmpeg(logger: Optional[logging.Logger] = None, auto_download: bool = True) -> bool:
    """Ensure ffmpeg/ffprobe exist, optionally downloading on first run (blocking)."""
    _prepend_tools_path()
    ffmpeg, _ = _find_tool("ffmpeg")
    ffprobe, _ = _find_tool("ffprobe")
    if ffmpeg and ffprobe:
        ok, _ = verify_tools(ffmpeg, ffprobe)
        if ok:
            _mark_tools_ready(ffmpeg, ffprobe)
            return True

    if not auto_download:
        return False

    log_fn = (lambda msg: logger.info(msg)) if logger else print
    try:
        _set_bootstrap_state(BootstrapPhase.DOWNLOADING, "Downloading ffmpeg…")
        ensure_ffmpeg_downloaded(log=log_fn, logger=logger)
        _prepend_tools_path()
        ready = _tools_ready()
        if ready:
            ffmpeg_path, _ = _find_tool("ffmpeg")
            ffprobe_path, _ = _find_tool("ffprobe")
            if ffmpeg_path and ffprobe_path:
                _mark_tools_ready(ffmpeg_path, ffprobe_path)
        else:
            _set_bootstrap_state(BootstrapPhase.FAILED, "ffmpeg setup failed.", "Verification failed.")
        return ready
    except Exception as exc:
        if logger:
            logger.error("Failed to download ffmpeg: %s", exc)
        _set_bootstrap_state(BootstrapPhase.FAILED, "ffmpeg setup failed.", str(exc))
        return False


def get_tools_status(auto_bootstrap: bool = False) -> dict:
    """Return availability of external tools for the web UI."""
    if auto_bootstrap:
        start_bootstrap_background()
    else:
        _prepend_tools_path()

    ffmpeg_path, ffmpeg_source = _find_tool("ffmpeg")
    ffprobe_path, _ = _find_tool("ffprobe")
    bootstrap = get_bootstrap_state()
    phase = bootstrap["phase"]

    if phase == BootstrapPhase.READY.value:
        available = True
    elif phase in {
        BootstrapPhase.FAILED.value,
        BootstrapPhase.DOWNLOADING.value,
        BootstrapPhase.CHECKING.value,
        BootstrapPhase.VERIFYING.value,
    }:
        available = False
    else:
        available = _tools_ready()
        if available and ffmpeg_path and ffprobe_path:
            _mark_tools_ready(ffmpeg_path, ffprobe_path)
            bootstrap = get_bootstrap_state()

    return {
        "ffmpeg": {
            "available": available,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "source": ffmpeg_source if ffmpeg_path else "none",
        },
        "bootstrap": bootstrap,
    }


def ensure_tools_available(logger: logging.Logger, auto_download: bool = True) -> Tuple[str, str]:
    if auto_download:
        bootstrap_ffmpeg(logger=logger, auto_download=True)
    _prepend_tools_path()

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path and auto_download:
        try:
            ensure_ffmpeg_downloaded(logger=logger)
            _prepend_tools_path()
            ffmpeg_path = shutil.which("ffmpeg")
            ffprobe_path = shutil.which("ffprobe")
        except Exception as exc:
            logger.error("Failed to download ffmpeg: %s", exc)

    if not ffmpeg_path:
        logger.error(
            "ffmpeg not found. Wait for the first-run download in the app, or install ffmpeg manually."
        )
        sys.exit(1)
    if not ffprobe_path:
        logger.error("ffprobe not found. Please install ffmpeg (includes ffprobe).")
        sys.exit(1)

    logger.info("Using ffmpeg at: %s", ffmpeg_path)
    logger.info("Using ffprobe at: %s", ffprobe_path)
    return ffmpeg_path, ffprobe_path


def detect_nvenc_support(ffmpeg_bin: str, logger: logging.Logger) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except Exception as exc:
        logger.warning("Failed to query ffmpeg encoders: %s", exc)
        return False

    if "h264_nvenc" in result.stdout:
        logger.info("NVENC (h264_nvenc) encoder is available.")
        return True

    logger.info("NVENC (h264_nvenc) encoder not found in ffmpeg encoders.")
    return False


def get_nvenc_help(ffmpeg_bin: str, logger: logging.Logger) -> str:
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-h", "encoder=h264_nvenc"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("Failed to get NVENC help from ffmpeg, return code %s.", result.returncode)
            return ""
        return result.stdout
    except Exception as exc:
        logger.warning("Exception while getting NVENC help: %s", exc)
        return ""


def nvenc_option_supported(help_text: str, option_name: str) -> bool:
    if not help_text:
        return False
    return option_name in help_text


def choose_nvenc_preset(help_text: str, logger: logging.Logger) -> str:
    if "p7" in help_text:
        logger.info("Using NVENC preset: p7")
        return "p7"
    if "slow" in help_text:
        logger.info("Using NVENC preset: slow")
        return "slow"
    logger.info("Using NVENC preset: default")
    return "default"


def choose_nvenc_rc_mode(help_text: str, logger: logging.Logger) -> Optional[str]:
    if "vbr_hq" in help_text:
        logger.info("Using NVENC rate control: vbr_hq")
        return "vbr_hq"
    if "vbr" in help_text:
        logger.info("Using NVENC rate control: vbr")
        return "vbr"
    if "constqp" in help_text:
        logger.info("Using NVENC rate control: constqp")
        return "constqp"
    logger.info("No advanced NVENC rate control modes detected; using encoder default.")
    return None


def build_nvenc_video_args(
    ffmpeg_bin: str,
    logger: logging.Logger,
    cq_target: int = NVENC_CQ_TARGET,
    aq_strength: int = NVENC_AQ_STRENGTH,
) -> List[str]:
    help_text = get_nvenc_help(ffmpeg_bin, logger)
    args: List[str] = ["-c:v", "h264_nvenc"]

    preset = choose_nvenc_preset(help_text, logger)
    args += ["-preset", preset]

    rc_mode = choose_nvenc_rc_mode(help_text, logger)
    if rc_mode:
        args += ["-rc", rc_mode]
        if rc_mode in {"vbr", "vbr_hq"}:
            args += ["-b:v", "0"]
    if nvenc_option_supported(help_text, "cq"):
        args += ["-cq", str(cq_target)]
    elif nvenc_option_supported(help_text, "qp"):
        args += ["-qp", str(cq_target)]

    args += ["-profile:v", "high"]

    if nvenc_option_supported(help_text, "spatial_aq"):
        args += ["-spatial_aq", "1"]
    if nvenc_option_supported(help_text, "temporal_aq"):
        args += ["-temporal_aq", "1"]
    if nvenc_option_supported(help_text, "aq-strength"):
        args += ["-aq-strength", str(aq_strength)]

    logger.info("Using NVENC video args: %s", " ".join(args))
    return args


def build_x264_video_args(crf: int, preset: str, logger: logging.Logger) -> List[str]:
    args = [
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-profile:v",
        "high",
    ]
    logger.info("Using libx264 video args: %s", " ".join(args))
    return args
