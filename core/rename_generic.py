"""Rename mode 2 ("Other"): apply a format profile to folder and/or file names.

Unlike the shows/movies mode nothing is parsed or moved: each name is cleaned by
the profile's rules, then run through its ``generic`` pattern (tokens ``{name}``,
``{parent}``, ``{n}`` and ``{date}``). Renames happen in place, and are journalled so
they can be undone.

``{date}`` is the earliest date in the names of the videos inside a folder (for a file:
the date in its own name). An item with no date is skipped, and an item that already
looks like the pattern (``2006 juli 13 - Holiday``) keeps its date and is only re-tidied,
so running the rename again changes nothing.

The selected folder itself can be renamed too (``include_root``). It goes last, after
everything inside it, so the paths planned for the children stay valid. For it ``{parent}``
is the folder it sits in and ``{n}`` is 1.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Set, Tuple, Union

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

# Reading a folder to sample it stops here, so a huge library is never walked to the end.
MAX_SCAN_ITEMS = 5000

# Never renamed: OS bookkeeping files and anything hidden.
IGNORED_FILES: Set[str] = {"thumbs.db", "desktop.ini", ".ds_store"}

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


DateSource = Union[DateTuple, Callable[[], Optional[DateTuple]], None]

SKIP_NO_DATE = "no date found in the videos"


@dataclass(frozen=True)
class Item:
    """One folder or file a rename looks at."""

    path: Path
    kind: str  # "folder" or "file"
    directory: Path  # the folder it sits in (for the selected folder itself: its parent)
    n: int  # 1-based position among the entries of the same kind in that folder
    is_root: bool = False


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


def normalize_root(root: Path) -> Path:
    """Absolute form of *root* (``.`` and trailing slashes resolved, symlinks left alone)."""
    return Path(os.path.abspath(root))


def check_root_renamable(root: Path) -> None:
    """Refuse a root with no name of its own: a drive or share root such as ``C:\\`` or ``/``."""
    root = normalize_root(root)
    if root.parent == root or not root.name:
        raise ValueError(
            f"'{root}' is a drive or share root and cannot be renamed. "
            "Pick a folder inside it, or turn off renaming the selected folder."
        )


def check_options(targets: str, include_root: bool) -> None:
    """Validate the ``targets`` / ``include_root`` combination; raises ``ValueError``."""
    if targets not in TARGETS:
        raise ValueError(f"targets must be one of {', '.join(TARGETS)}")
    if include_root and targets == "files":
        raise ValueError(
            "The selected folder is a folder: choose 'Folders' or 'Folders and files' to rename it too."
        )


def clamp_depth(max_depth: int) -> int:
    return max(1, min(int(max_depth), MAX_DEPTH_LIMIT))


def _list_dir(directory: Path, skipped: List[Tuple[Path, str]]) -> Optional[Tuple[List[Path], List[Path]]]:
    """Sorted ``(folders, files)`` directly inside *directory*, or None when it cannot be read."""
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        skipped.append((directory, f"cannot read folder ({exc})"))
        return None
    dirs = [e for e in entries if e.is_dir() and not e.is_symlink() and not e.name.startswith(".")]
    files = [e for e in entries if e.is_file() and not _is_hidden(e)]
    return dirs, files


def _walk(
    directory: Path, depth: int, max_depth: int, skipped: List[Tuple[Path, str]]
) -> Iterator[Tuple[Path, List[Path], List[Path]]]:
    """Yield ``(directory, folders, files)`` for *directory* and, down to *max_depth*, each folder below."""
    listing = _list_dir(directory, skipped)
    if listing is None:
        return
    dirs, files = listing
    yield directory, dirs, files
    if depth < max_depth:
        for folder in dirs:
            yield from _walk(folder, depth + 1, max_depth, skipped)


def scan_items(
    root: Path,
    targets: str,
    max_depth: int,
    *,
    include_root: bool = False,
    limit: int = MAX_SCAN_ITEMS,
) -> Tuple[List[Item], bool]:
    """List what a rename of *root* looks at, without working out any names.

    Returns ``(items, truncated)``. The walk stops once *limit* items are found (``truncated``
    is then True), so a huge library is not read to the end just to sample it.
    """
    check_options(targets, include_root)
    root = normalize_root(root)
    if include_root:
        check_root_renamable(root)
    items: List[Item] = []
    truncated = False
    for directory, dirs, files in _walk(root, 1, clamp_depth(max_depth), []):
        if targets in ("folders", "both"):
            items.extend(Item(f, "folder", directory, n) for n, f in enumerate(dirs, start=1))
        if targets in ("files", "both"):
            items.extend(Item(f, "file", directory, n) for n, f in enumerate(files, start=1))
        if len(items) >= limit:
            truncated = True
            items = items[:limit]
            break
    if include_root:
        items.append(Item(root, "folder", root.parent, 1, is_root=True))
    return items, truncated


def parent_label(profile: Profile, directory: Path) -> str:
    """The cleaned name of the folder an item sits in (what ``{parent}`` stands for)."""
    return apply_rules(directory.name, profile.rules, date_locale=profile.date_locale) or directory.name


def item_date_source(item: Item) -> DateSource:
    """Where an item's ``{date}`` comes from: its own name for a file, the videos inside for a folder."""
    if item.kind == "file":
        return parse_date_from_filename(item.path.name)
    return lambda path=item.path: earliest_date_in_folder(path)  # noqa: E731


def item_new_stem(profile: Profile, item: Item) -> Optional[str]:
    """The name (without extension) *profile* gives *item*; None when it needs a date and has none."""
    stem = item.path.stem if item.kind == "file" else item.path.name
    return generic_new_name(profile, stem, parent_label(profile, item.directory), item.n, item_date_source(item))


def plan_generic_rename(
    root: Path,
    targets: str,
    max_depth: int,
    profile: Profile,
    logger: Optional[logging.Logger] = None,
    include_root: bool = False,
) -> Tuple[List[RenameOp], List[Tuple[Path, str]]]:
    """Plan renames under *root*: ``targets`` is folders/files/both, ``max_depth``
    counts levels below *root* (1 = direct children only). With ``include_root`` the
    folder *root* itself is renamed too, after everything inside it."""
    check_options(targets, include_root)
    max_depth = clamp_depth(max_depth)
    root = normalize_root(root)
    if include_root:
        check_root_renamable(root)

    ops: List[RenameOp] = []
    skipped: List[Tuple[Path, str]] = []

    def plan_item(item: Item, used: Set[str]) -> None:
        suffix = item.path.suffix if item.kind == "file" else ""
        new_stem = item_new_stem(profile, item)
        if new_stem is None:
            skipped.append((item.path, SKIP_NO_DATE))
            return
        new_name = reserve_name(item.directory, new_stem, suffix, used, ignore_path=item.path)
        if new_name == item.path.name:
            skipped.append((item.path, "already correctly named"))
            return
        ops.append(RenameOp(src=item.path, dst=item.directory / new_name, kind=item.kind))

    for directory, dirs, files in _walk(root, 1, max_depth, skipped):
        used: Set[str] = set()
        if targets in ("folders", "both"):
            for n, folder in enumerate(dirs, start=1):
                plan_item(Item(folder, "folder", directory, n), used)
        if targets in ("files", "both"):
            for n, file in enumerate(files, start=1):
                plan_item(Item(file, "file", directory, n), used)

    if include_root:
        # The selected folder has its own siblings (in its parent), so its own set of taken names.
        plan_item(Item(root, "folder", root.parent, 1, is_root=True), set())

    # Children first: a folder is only renamed after everything inside it, so the
    # paths recorded for the children stay valid (and the undo journal unwinds
    # cleanly in reverse order). The selected folder has the fewest path parts, so it is last.
    ops.sort(key=lambda op: len(op.src.parts), reverse=True)
    return ops, skipped


def _rel(path: Path, root: Path) -> str:
    if path == root:
        return f"(the selected folder) {path.name}"
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
    root: Path = normalize_root(args.input)
    apply = bool(args.apply)
    targets = getattr(args, "targets", "folders")
    max_depth = int(getattr(args, "max_depth", 1))
    include_root = bool(getattr(args, "include_root", False))

    logger.info("Folders rename mode (%s).", "APPLY" if apply else "DRY-RUN")
    logger.info("Root: %s", root)
    logger.info(
        "Profile: %s | targets=%s | depth=%d | include selected folder=%s",
        profile.name,
        targets,
        clamp_depth(max_depth),
        "yes" if include_root else "no",
    )
    logger.info("Pattern: %s", profile.pattern("generic"))
    if pattern_uses_token(profile.pattern("generic"), "date"):
        logger.info("Dates come from the video file names in each folder; month names: %s.", profile.date_locale)

    ops, skipped = plan_generic_rename(root, targets, max_depth, profile, logger, include_root=include_root)
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
            # If the selected folder itself was renamed, the old path is gone: the journal is filed
            # under the new one, which is also what --undo --input has to be pointed at.
            root_op = next((op for op in done if op.src == root), None)
            renamed_root = {"from": str(root), "to": str(root_op.dst)} if root_op is not None else None
            journal_root = root_op.dst if root_op is not None else root
            undo_manifest = build_undo_journal(
                done, False, dest_root=journal_root, input_root=journal_root, mode="generic",
                renamed_root=renamed_root,
            )
            write_undo_journal(
                journal_root, done, False, logger, input_root=journal_root, mode="generic",
                renamed_root=renamed_root,
            )
            if root_op is not None:
                logger.info("The selected folder is now '%s'.", root_op.dst)
                logger.info("To undo from the command line, use --input '%s'.", root_op.dst)

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
    profile: Profile,
    name: str,
    parent: str = "Parent",
    n: int = 1,
    date: Optional[DateTuple] = None,
) -> Tuple[str, Optional[str]]:
    """Format a single sample name; returns ``(result, note)``.

    A sample has no videos to read a date from, so a pattern with ``{date}`` uses a sample
    date (unless the name already carries one, or *date* is given) and the note says so.
    """
    parent_clean = apply_rules(parent, profile.rules, date_locale=profile.date_locale) or parent
    pattern = profile.pattern("generic")
    note: Optional[str] = None
    if (
        date is None
        and pattern_uses_token(pattern, "date")
        and reverse_pattern(pattern, name, profile.date_locale) is None
    ):
        date = SAMPLE_DATE
        note = (
            f"Sample date {format_date(SAMPLE_DATE, 'D MMMM YYYY', 'en')} used; "
            "real runs read it from the videos in each folder."
        )
    result = generic_new_name(profile, name, parent_clean, n, date)
    return (result if result is not None else name), note


def preview_generic_name(
    profile: Profile,
    name: str,
    parent: str = "Parent",
    n: int = 1,
    date: Optional[DateTuple] = None,
) -> str:
    """Format a single sample name (used by AI verification)."""
    return preview_generic(profile, name, parent, n, date)[0]


__all__ = [
    "TARGETS",
    "Item",
    "check_options",
    "check_root_renamable",
    "generic_new_name",
    "item_date_source",
    "item_new_stem",
    "normalize_root",
    "parent_label",
    "plan_generic_rename",
    "preview_generic",
    "preview_generic_name",
    "run_generic_rename",
    "scan_items",
]
