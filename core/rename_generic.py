"""Rename mode 2 ("Other"): apply a format profile to folder and/or file names.

Unlike the shows/movies mode nothing is parsed or moved: each name is cleaned by
the profile's rules, then run through its ``generic`` pattern (tokens ``{name}``,
``{parent}``, ``{n}`` and ``{date}``). Renames happen in place, and are journalled so
they can be undone.

``{date}`` is the earliest date in the names of the videos inside a folder (for a file:
the date in its own name). An item with no date is skipped, and an item that already
looks like the pattern (``2006 juli 13 - Holiday``) keeps its date and is only re-tidied,
so running the rename again changes nothing.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple, Union

from .dates import SAMPLE_DATE, DateTuple, earliest_date_in_folder, format_date, parse_date_from_filename
from .rename import (
    RenameOp,
    build_undo_journal,
    execute_rename,
    reserve_name,
    write_undo_journal,
)
from .rename_profiles import Profile, apply_rules, pattern_uses_token, render_pattern, reverse_pattern

TARGETS = ("folders", "files", "both")
MAX_DEPTH_LIMIT = 50

# Never renamed: OS bookkeeping files and anything hidden.
IGNORED_FILES: Set[str] = {"thumbs.db", "desktop.ini", ".ds_store"}

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


DateSource = Union[DateTuple, Callable[[], Optional[DateTuple]], None]

SKIP_NO_DATE = "no date found in the videos"


def generic_new_name(
    profile: Profile,
    stem: str,
    parent: str,
    n: int,
    date: DateSource = None,
) -> Optional[str]:
    """Return the profile-formatted name for *stem* (without extension).

    *date* is a ``(year, month, day)`` tuple or a function that finds one (only called when
    the pattern needs it). Returns ``None`` when the pattern uses ``{date}`` and no date is
    available: such an item is left alone.
    """
    pattern = profile.pattern("generic")
    if pattern_uses_token(pattern, "date"):
        # Already made with this pattern? Then its own date wins and the rest is the name.
        already = reverse_pattern(pattern, stem, profile.date_locale)
        if already is not None:
            date, stem = already
        elif callable(date):
            date = date()
        if date is None:
            return None
    cleaned = apply_rules(stem, profile.rules, date_locale=profile.date_locale) or stem
    rendered = render_pattern(
        pattern,
        {"name": cleaned, "parent": parent, "n": n, "date": date},
        date_locale=profile.date_locale,
    )
    rendered = re.sub(r"\s+", " ", _INVALID_CHARS.sub("", rendered)).strip(" .")
    return rendered or stem


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".") or path.name.lower() in IGNORED_FILES


def plan_generic_rename(
    root: Path,
    targets: str,
    max_depth: int,
    profile: Profile,
    logger: Optional[logging.Logger] = None,
) -> Tuple[List[RenameOp], List[Tuple[Path, str]]]:
    """Plan renames under *root*: ``targets`` is folders/files/both, ``max_depth``
    counts levels below *root* (1 = direct children only)."""
    if targets not in TARGETS:
        raise ValueError(f"targets must be one of {', '.join(TARGETS)}")
    max_depth = max(1, min(int(max_depth), MAX_DEPTH_LIMIT))

    ops: List[RenameOp] = []
    skipped: List[Tuple[Path, str]] = []

    def parent_label(directory: Path) -> str:
        return apply_rules(directory.name, profile.rules, date_locale=profile.date_locale) or directory.name

    def plan_level(directory: Path, depth: int) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            skipped.append((directory, f"cannot read folder ({exc})"))
            return

        dirs = [e for e in entries if e.is_dir() and not e.is_symlink() and not e.name.startswith(".")]
        files = [e for e in entries if e.is_file() and not _is_hidden(e)]
        parent = parent_label(directory)
        used: Set[str] = set()

        def plan_entry(entry: Path, n: int, kind: str) -> None:
            suffix = entry.suffix if kind == "file" else ""
            stem = entry.stem if kind == "file" else entry.name
            if kind == "file":
                date_source: DateSource = parse_date_from_filename(entry.name)
            else:
                date_source = lambda entry=entry: earliest_date_in_folder(entry)  # noqa: E731
            new_stem = generic_new_name(profile, stem, parent, n, date_source)
            if new_stem is None:
                skipped.append((entry, SKIP_NO_DATE))
                return
            new_name = reserve_name(directory, new_stem, suffix, used, ignore_path=entry)
            if new_name == entry.name:
                skipped.append((entry, "already correctly named"))
                return
            ops.append(RenameOp(src=entry, dst=directory / new_name, kind=kind))

        if targets in ("folders", "both"):
            for n, folder in enumerate(dirs, start=1):
                plan_entry(folder, n, "folder")
        if targets in ("files", "both"):
            for n, file in enumerate(files, start=1):
                plan_entry(file, n, "file")

        if depth < max_depth:
            for folder in dirs:
                plan_level(folder, depth + 1)

    plan_level(root, 1)

    # Children first: a folder is only renamed after everything inside it, so the
    # paths recorded for the children stay valid (and the undo journal unwinds
    # cleanly in reverse order).
    ops.sort(key=lambda op: len(op.src.parts), reverse=True)
    return ops, skipped


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def run_generic_rename(
    args: argparse.Namespace,
    logger: logging.Logger,
    profile: Profile,
) -> Optional[dict]:
    """Plan (and optionally apply) a Other-mode rename. Returns the undo manifest."""
    root: Path = args.input
    apply = bool(args.apply)
    targets = getattr(args, "targets", "folders")
    max_depth = int(getattr(args, "max_depth", 1))

    logger.info("Folders rename mode (%s).", "APPLY" if apply else "DRY-RUN")
    logger.info("Root: %s", root)
    logger.info(
        "Profile: %s | targets=%s | depth=%d",
        profile.name,
        targets,
        max(1, min(max_depth, MAX_DEPTH_LIMIT)),
    )
    logger.info("Pattern: %s", profile.pattern("generic"))
    if pattern_uses_token(profile.pattern("generic"), "date"):
        logger.info("Dates come from the video file names in each folder; month names: %s.", profile.date_locale)

    ops, skipped = plan_generic_rename(root, targets, max_depth, profile, logger)
    folders = sum(1 for o in ops if o.kind == "folder")
    files = sum(1 for o in ops if o.kind == "file")
    logger.info("Planned renames: %d (folders=%d, files=%d).", len(ops), folders, files)

    undo_manifest: Optional[dict] = None
    if not apply:
        for op in ops:
            logger.info("[DRY-RUN] %s '%s' -> '%s'", op.kind, _rel(op.src, root), op.dst.name)
    else:
        succeeded, failed, done = execute_rename(ops, False, logger)
        logger.info("Executed: succeeded=%d, failed=%d.", succeeded, failed)
        if done:
            undo_manifest = build_undo_journal(
                done, False, dest_root=root, input_root=root, mode="generic"
            )
            write_undo_journal(root, done, False, logger, input_root=root, mode="generic")

    if skipped:
        already = sum(1 for _, reason in skipped if reason == "already correctly named")
        other = [(p, r) for p, r in skipped if r != "already correctly named"]
        logger.info("Unchanged: %d already correctly named.", already)
        for path, reason in other:
            logger.info("  SKIP (%s): %s", reason, path)

    if not apply:
        logger.info("Dry-run complete. Apply to perform these renames.")
    logger.info("Done.")
    return undo_manifest


def preview_generic(
    profile: Profile, name: str, parent: str = "Parent", n: int = 1
) -> Tuple[str, Optional[str]]:
    """Format a single sample name; returns ``(result, note)``.

    A sample has no videos to read a date from, so a pattern with ``{date}`` uses a sample
    date (unless the name already carries one) and the note says so.
    """
    parent_clean = apply_rules(parent, profile.rules, date_locale=profile.date_locale) or parent
    pattern = profile.pattern("generic")
    date: DateSource = None
    note: Optional[str] = None
    if pattern_uses_token(pattern, "date") and reverse_pattern(pattern, name, profile.date_locale) is None:
        date = SAMPLE_DATE
        note = (
            f"Sample date {format_date(SAMPLE_DATE, 'D MMMM YYYY', 'en')} used; "
            "real runs read it from the videos in each folder."
        )
    result = generic_new_name(profile, name, parent_clean, n, date)
    return (result if result is not None else name), note


def preview_generic_name(profile: Profile, name: str, parent: str = "Parent", n: int = 1) -> str:
    """Format a single sample name (used by AI verification)."""
    return preview_generic(profile, name, parent, n)[0]


__all__ = [
    "TARGETS",
    "generic_new_name",
    "plan_generic_rename",
    "preview_generic",
    "preview_generic_name",
    "run_generic_rename",
]
