"""Rename folders containing videos to: "YYYY maand DD - Description".

Example::

    Holiday 2006\\clip-2006-07-13 17;48;08.dv
    -> 2006 juli 13 - Holiday

The date is extracted from video filenames inside each folder (DV or MP4 naming).
Description is the original folder name.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable, Optional, Tuple

DUTCH_MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
]
MONTH_NAME_TO_NUM = {m: i for i, m in enumerate(DUTCH_MONTHS, 1)}

# DV: clip-2006-07-13 17;48;08.dv
RE_DV_DATE = re.compile(r"clip-(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE)
# MP4: 13 juli 2006 17-48-08.mp4 (from dv_to_mp4 converter)
RE_MP4_DATE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(DUTCH_MONTHS) + r")\s+(\d{4})",
    re.IGNORECASE,
)
# Already renamed: 2006 juli 13 - Something (captures date + description for re-pruning)
RE_ALREADY_RENAMED = re.compile(
    r"^(\d{4})\s+(" + "|".join(DUTCH_MONTHS) + r")\s+(\d{1,2})\s+-\s+(.+)$",
    re.IGNORECASE,
)

VIDEO_EXTENSIONS = {".dv", ".mp4", ".avi", ".mov", ".mkv", ".m4v"}


def parse_date_from_filename(name: str) -> Optional[Tuple[int, int, int]]:
    """Return (year, month, day) or None."""
    m = RE_DV_DATE.search(name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return (y, mo, d)

    m = RE_MP4_DATE.search(name)
    if m:
        d, month_name, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        mo = MONTH_NAME_TO_NUM.get(month_name)
        if mo and 1 <= d <= 31:
            return (y, mo, d)

    return None


def earliest_date_in_folder(folder: Path) -> Optional[Tuple[int, int, int]]:
    """Find earliest (year, month, day) from video filenames in folder (recursive)."""
    dates = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            d = parse_date_from_filename(f.stem)
            if d:
                dates.append(d)
    return min(dates) if dates else None


def prune_date_from_description(description: str) -> str:
    """Remove date-like parts from the description (e.g. 'Holiday 2006' -> 'Holiday')."""
    s = description
    s = re.sub(r"\s*[-–—]?\s*\d{4}\s*$", "", s)
    s = re.sub(r"^\s*\d{4}\s*[-–—]?\s*", "", s)
    s = re.sub(
        r"\s*[-–—]?\s*\d{1,2}\s+(" + "|".join(DUTCH_MONTHS) + r")\s+\d{4}\b\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\s*[-–—]?\s*(" + "|".join(DUTCH_MONTHS) + r")\s+\d{4}\b\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\s*[-–—]?\s*\d{1,2}\s+(" + "|".join(DUTCH_MONTHS) + r")\b\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s*\d{1,2}-\d{1,2}-\d{2}\b\s*", "", s)
    s = re.sub(r"\d{4}[-/.\s]\d{1,2}[-/.\s]\d{1,2}\s*", "", s)
    s = re.sub(r"\s*\d{4}[-/.\s]\d{1,2}[-/.\s]\d{1,2}\s*", "", s)
    s = s.strip(" -–—\t")
    s = re.sub(r"\s+", " ", s).strip()
    return s or "folder"


def format_folder_name(year: int, month: int, day: int, description: str) -> str:
    """Format as 'YYYY maand DD - Description'."""
    month_name = DUTCH_MONTHS[month - 1]
    desc = prune_date_from_description(description)
    return f"{year} {month_name} {day} - {desc}"


def parse_already_renamed(name: str) -> Optional[Tuple[int, int, int, str]]:
    """If folder matches our pattern, return (year, month, day, description)."""
    m = RE_ALREADY_RENAMED.match(name)
    if not m:
        return None
    year = int(m.group(1))
    month_name = m.group(2).lower()
    month = MONTH_NAME_TO_NUM.get(month_name)
    if not month:
        return None
    day = int(m.group(3))
    description = m.group(4)
    return (year, month, day, description)


def sanitize_for_windows(name: str) -> str:
    """Remove characters invalid in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip().strip(".") or "folder"


def process_root(
    root: Path,
    dry_run: bool,
    log: Callable[[str], None] = print,
) -> dict:
    """Rename direct subfolders of ``root`` to "YYYY maand DD - Description"."""
    renamed = 0
    skipped_no_date = 0
    skipped_already = 0

    subfolders = sorted([p for p in root.iterdir() if p.is_dir()])

    for folder in subfolders:
        orig_name = folder.name

        parsed = parse_already_renamed(orig_name)
        if parsed:
            year, month, day, description = parsed
            new_name = format_folder_name(year, month, day, description)
            new_name = sanitize_for_windows(new_name)
            if new_name != orig_name:
                new_path = folder.parent / new_name
                if new_path.exists() and new_path != folder:
                    log(f"Skipping (target exists): {folder} -> {new_name}")
                elif dry_run:
                    log(f"[DRY-RUN] Would rename: {orig_name}")
                    log(f"          -> {new_name}")
                else:
                    try:
                        folder.rename(new_path)
                        log(f"Renamed: {orig_name} -> {new_name}")
                        renamed += 1
                    except OSError as e:
                        log(f"Error renaming '{folder}': {e}")
            else:
                skipped_already += 1
            continue

        date_tuple = earliest_date_in_folder(folder)
        if not date_tuple:
            log(f"Skipping (no date in videos): {folder}")
            skipped_no_date += 1
            continue

        year, month, day = date_tuple
        new_name = format_folder_name(year, month, day, orig_name)
        new_name = sanitize_for_windows(new_name)

        if new_name == orig_name:
            continue

        new_path = folder.parent / new_name
        if new_path.exists() and new_path != folder:
            log(f"Skipping (target exists): {folder} -> {new_name}")
            continue

        if dry_run:
            log(f"[DRY-RUN] Would rename: {folder.name}")
            log(f"          -> {new_name}")
        else:
            try:
                folder.rename(new_path)
                log(f"Renamed: {orig_name} -> {new_name}")
                renamed += 1
            except OSError as e:
                log(f"Error renaming '{folder}': {e}")

    summary = {
        "renamed": renamed,
        "skipped_no_date": skipped_no_date,
        "skipped_already": skipped_already,
    }
    if dry_run:
        log(
            f"\n[DRY-RUN] Done. Would rename: {renamed}, "
            f"skipped (no date): {skipped_no_date}, skipped (already): {skipped_already}"
        )
    else:
        log(
            f"\nDone. Renamed: {renamed}, skipped (no date): {skipped_no_date}, "
            f"skipped (already): {skipped_already}"
        )
    return summary


def run_rename_folders(args: argparse.Namespace) -> None:
    """CLI / programmatic entry point for folder date-stamping."""
    root: Path = args.root
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    process_root(root, bool(args.dry_run))


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Rename folders to "YYYY maand DD - Description" using dates from video filenames.'
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Root folder containing subfolders to rename.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be renamed without making changes.",
    )
    run_rename_folders(parser.parse_args())


if __name__ == "__main__":
    main()
