"""Filename construction helpers shared by the convert and VTS pipelines."""

import re
from pathlib import Path
from typing import Optional, Set

from .config import DUTCH_MONTHS, RE_DATE, RE_TIME


def sanitize_filename(stem: str) -> str:
    # Remove characters invalid on Windows: <>:"/\\|?*
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", stem)
    sanitized = sanitized.strip().strip(".")
    if not sanitized:
        sanitized = "clip"
    return sanitized


def parse_dutch_name_from_stem(stem: str) -> Optional[str]:
    """
    Convert 'clip-YYYY-MM-DD HH;MM;SS' to 'DD maand YYYY HH-MM-SS' (Dutch names).
    If time is missing, return 'DD maand YYYY'.
    Return None if date cannot be parsed.
    """
    date_match = RE_DATE.search(stem)
    if not date_match:
        return None

    year = int(date_match.group(1))
    month = int(date_match.group(2))
    day = int(date_match.group(3))

    if not (1 <= month <= 12):
        return None

    month_name = DUTCH_MONTHS[month]
    date_str = f"{int(day)} {month_name} {year}"

    time_match = RE_TIME.search(stem)
    if not time_match:
        return date_str

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    second = int(time_match.group(3))

    time_str = f"{hour:02d}-{minute:02d}-{second:02d}"
    return f"{date_str} {time_str}"


def generate_unique_name(
    dest_dir: Path,
    base_stem: str,
    used_names: Set[str],
    extension: str = ".mp4",
) -> str:
    # Only disambiguate against names already chosen in THIS run. We deliberately
    # do NOT bump based on files already on disk: source files are processed in a
    # stable (sorted) order, so each one maps to the same output name on every
    # run. That keeps the converter resume-safe -- an existing, valid output is
    # then recognised and skipped by process_single_file instead of being
    # re-encoded to a spurious "name (2).mp4" duplicate.
    candidate = f"{base_stem}{extension}"
    idx = 2
    while candidate in used_names:
        candidate = f"{base_stem} ({idx}){extension}"
        idx += 1
    used_names.add(candidate)
    return candidate
