"""ffprobe-based media inspection helpers."""

import subprocess
from pathlib import Path
from typing import Optional

from .config import MIN_VALID_DURATION_SECONDS


def is_valid_output(ffprobe_bin: str, path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        output = result.stdout.strip()
        if not output:
            return False
        try:
            duration = float(output)
        except ValueError:
            return False
        return duration > MIN_VALID_DURATION_SECONDS
    except Exception:
        return False


def parse_time_to_seconds(value: str) -> Optional[float]:
    """Parse a duration given as plain seconds (``10``, ``2.5``) or as a
    timestamp (``0:10``, ``1:02:03``, ``1:02:03.5``).

    Returns the number of seconds as a float, or None if it can't be parsed or
    is negative.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) > 3:
                return None
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + float(part)
        else:
            seconds = float(text)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return seconds


def get_media_duration(ffprobe_bin: str, path: Path) -> Optional[float]:
    """Return the duration of *path* in seconds via ffprobe, or None on failure."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    try:
        return float(output)
    except ValueError:
        return None


def has_audio_stream(ffprobe_bin: str, path: Path) -> bool:
    """Return True if *path* has at least one audio stream."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())
