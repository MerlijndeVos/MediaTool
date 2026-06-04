"""Discovery and capability probing for external tools.

This module locates the external binaries the toolkit shells out to (ffmpeg,
ffprobe and MKVToolNix) and probes ffmpeg's NVENC capabilities, building the
matching video-encoder argument lists.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .config import NVENC_AQ_STRENGTH, NVENC_CQ_TARGET
from .ffmpeg_bootstrap import ensure_ffmpeg_downloaded
from .runtime import bundled_tools_dir, tool_filename

MKVTOOLNIX_URL = "https://mkvtoolnix.download/"


def _prepend_tools_path() -> None:
    tools_bin = str(bundled_tools_dir())
    path = os.environ.get("PATH", "")
    if tools_bin not in path.split(os.pathsep):
        os.environ["PATH"] = tools_bin + os.pathsep + path


def _find_tool(name: str) -> tuple[Optional[str], str]:
    found = shutil.which(name)
    if found:
        bundled = bundled_tools_dir() / tool_filename(name)
        source = "bundled" if bundled.resolve() == Path(found).resolve() else "path"
        return found, source
    return None, "none"


def bootstrap_ffmpeg(logger: Optional[logging.Logger] = None, auto_download: bool = True) -> bool:
    """Ensure ffmpeg/ffprobe exist, optionally downloading on first run."""
    ffmpeg, _ = _find_tool("ffmpeg")
    ffprobe, _ = _find_tool("ffprobe")
    if ffmpeg and ffprobe:
        return True
    if not auto_download:
        return False

    log_fn = (lambda msg: logger.info(msg)) if logger else print
    try:
        ensure_ffmpeg_downloaded(log=log_fn, logger=logger)
        _prepend_tools_path()
        return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    except Exception as exc:
        if logger:
            logger.error("Failed to download ffmpeg: %s", exc)
        return False


def get_tools_status(auto_bootstrap: bool = False) -> dict:
    """Return availability of external tools for the web UI."""
    if auto_bootstrap:
        bootstrap_ffmpeg(auto_download=True)

    ffmpeg_path, ffmpeg_source = _find_tool("ffmpeg")
    ffprobe_path, ffprobe_source = _find_tool("ffprobe")
    mkvmerge, _ = _find_tool("mkvmerge")
    mkvpropedit, _ = _find_tool("mkvpropedit")
    mkv_ok = bool(mkvmerge and mkvpropedit)

    return {
        "ffmpeg": {
            "available": bool(ffmpeg_path and ffprobe_path),
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "source": ffmpeg_source if ffmpeg_path else "none",
        },
        "mkvtoolnix": {
            "available": mkv_ok,
            "mkvmerge_path": mkvmerge,
            "mkvpropedit_path": mkvpropedit,
            "install_url": MKVTOOLNIX_URL,
            "message": None
            if mkv_ok
            else "MKVToolNix is required for Audio Default and some DVD features. Install it and add mkvmerge to PATH.",
        },
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
            "ffmpeg not found on PATH. Install ffmpeg or restart the app to trigger the first-run download."
        )
        sys.exit(1)
    if not ffprobe_path:
        logger.error("ffprobe not found on PATH. Please install ffmpeg (includes ffprobe).")
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
    # Prefer modern p7 ("slowest, best quality") if available, otherwise fall back to "slow" or "default"
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
        # For vbr / vbr_hq, a zero target bitrate with CQ is a common pattern for "quality-based" mode
        if rc_mode in {"vbr", "vbr_hq"}:
            args += ["-b:v", "0"]
    # Try to use a CQ-like option if available
    if nvenc_option_supported(help_text, "cq"):
        args += ["-cq", str(cq_target)]
    elif nvenc_option_supported(help_text, "qp"):
        # Fallback: use qp as a rough equivalent if cq is not available
        args += ["-qp", str(cq_target)]

    # High profile if supported
    args += ["-profile:v", "high"]

    # Adaptive quantization options if available
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


def ensure_mkvtoolnix(logger: logging.Logger) -> Tuple[str, str]:
    mkvmerge = shutil.which("mkvmerge")
    mkvpropedit = shutil.which("mkvpropedit")
    if not mkvmerge or not mkvpropedit:
        logger.error(
            "MKVToolNix not found on PATH (need mkvmerge + mkvpropedit). "
            "Install it from %s and ensure its folder is on PATH.",
            MKVTOOLNIX_URL,
        )
        sys.exit(1)
    logger.info("Using mkvmerge at   : %s", mkvmerge)
    logger.info("Using mkvpropedit at: %s", mkvpropedit)
    return mkvmerge, mkvpropedit
