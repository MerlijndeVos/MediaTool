"""Map parsed CLI arguments to :mod:`core` operations."""

import argparse
import sys
from typing import Callable

from . import mods_cli
from core import (
    run_audio,
    run_convert,
    run_dedup,
    run_download,
    run_rename,
    run_rename_folders,
    run_stitch,
    run_subtitle_cleanup,
    run_subtitle_translate,
    run_trim,
    run_vts,
)

CommandHandler = Callable[[argparse.Namespace], None]

COMMANDS: dict[str, CommandHandler] = {
    "convert": run_convert,
    "vts": run_vts,
    "rename": run_rename,
    "audio": run_audio,
    "dedup": run_dedup,
    "download": run_download,
    "trim": run_trim,
    "stitch": run_stitch,
    "rename_folders": run_rename_folders,
    "subtitle_translate": run_subtitle_translate,
    "subtitle_cleanup": run_subtitle_cleanup,
}


def dispatch(args: argparse.Namespace) -> None:
    """Run the subcommand selected on *args*."""
    handler = COMMANDS.get(args.command)
    if handler is None:
        if mods_cli.run_command(args):
            return
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(2)
    handler(args)
