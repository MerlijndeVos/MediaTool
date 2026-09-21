"""Deprecated: date-stamping folders is now a built-in rename profile.

The old "Rename Folders" tool renamed subfolders to ``YYYY maand DD - Description`` using the
earliest date in the video file names inside each folder. That is now the built-in profile
**Date + name (Dutch)** in the Rename tool's Folders mode, which also supports undo, other
date formats and English month names::

    toolbox rename --input D:\\DV_out --mode generic --profile "Date + name (Dutch)"

``toolbox rename_folders`` keeps working for existing scripts and just runs that.
"""

from __future__ import annotations

import argparse
import sys

from .rename_profiles import DATE_NAME_ID


def run_rename_folders(args: argparse.Namespace) -> None:
    """CLI entry point for the old ``rename_folders`` command (now the date profile)."""
    root = args.root
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    print(
        "Note: 'rename_folders' is deprecated. Use: toolbox rename --input <folder> "
        '--mode generic --profile "Date + name (Dutch)"',
        file=sys.stderr,
    )

    from .rename import run_rename

    run_rename(
        argparse.Namespace(
            input=root,
            output=None,
            type="auto",
            apply=not args.dry_run,
            copy=False,
            undo=False,
            prune_empty_dirs=False,
            no_titlecase=False,
            strip_words=[],
            bare_episode_numbers=False,
            default_sub_lang="en",
            profile=DATE_NAME_ID,
            mode="generic",
            layout=True,
            targets="folders",
            max_depth=1,
        )
    )
