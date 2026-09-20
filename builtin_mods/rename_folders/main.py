"""Rename Folders: date-stamp subfolders from the video dates inside them."""

from pathlib import Path

from core.rename_folders import process_root


def run(params, ctx):
    process_root(Path(params["root"]), params["dry_run"], log=ctx.log)
