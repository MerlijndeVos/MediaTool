"""Console output for the CLI via :mod:`core.progress` callbacks.

The CLI installs a root log handler and optional progress hooks so all
``core`` operations share one output path. Child loggers propagate to the
root handler; per-operation file logs are still written when enabled.
"""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from typing import Iterator, Optional

from core import config
from core.progress import (
    CallbackLogHandler,
    LogHooks,
    attach_log_callback,
    detach_log_callback,
    set_active_hooks,
)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def console_log(message: str, levelno: int) -> None:
    """Print a formatted log line to the console (warnings/errors on stderr)."""
    stream = sys.stderr if levelno >= logging.WARNING else sys.stdout
    print(message, file=stream, flush=True)


def console_progress(payload: dict) -> None:
    """Print download progress for CLI (overwrites the same stderr line)."""
    status = payload.get("status")
    if status == "downloading":
        pct = payload.get("pct")
        title = (payload.get("title") or "")[:40]
        if pct is not None:
            idx = payload.get("playlist_index")
            count = payload.get("n_entries")
            where = f"[{idx}/{count}] " if idx and count else ""
            label = f"{where}{title}: " if title else where
            print(f"\r{label}Downloading… {pct:.0f}%   ", end="", file=sys.stderr, flush=True)
    elif status == "finished":
        name = payload.get("filename") or ""
        if name:
            print(f"\rPost-processing: {name}          ", file=sys.stderr, flush=True)
        print(file=sys.stderr, flush=True)


def console_result(payload: dict) -> None:
    """Print a mod's ``ctx.result(...)`` as plain text (the app draws the same data as a table, tiles, ...)."""
    view = payload.get("view")
    if payload.get("title"):
        print(f"\n{payload['title']}", flush=True)
    if view == "table":
        columns = [str(c) for c in payload.get("columns", [])]
        rows = [[str(cell) for cell in row] for row in payload.get("rows", [])]
        widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(columns)]
        print("  ".join(c.ljust(w) for c, w in zip(columns, widths)).rstrip())
        for row in rows:
            print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())
        if payload.get("truncated"):
            print("... (more rows were left out)")
    elif view == "counters":
        for item in payload.get("items", []):
            print(f"{item['label']}: {item['value']}")
    elif view == "files":
        for item in payload.get("files", []):
            print(item["path"] + (f"  ({item['label']})" if item.get("label") else ""))
    elif view == "markdown":
        print(payload.get("text", ""))
    elif view == "image":
        print(f"[image: {payload.get('alt', '')}]")
    elif view == "message":
        stream = sys.stderr if payload.get("level") in ("warning", "error") else sys.stdout
        print(payload.get("text", ""), file=stream, flush=True)


@contextmanager
def cli_session(*, file_logging: bool = True) -> Iterator[LogHooks]:
    """Configure logging/progress hooks for a single CLI invocation."""
    config.FILE_LOGGING_ENABLED = file_logging
    hooks = LogHooks(on_log=console_log, on_progress=console_progress)
    set_active_hooks(hooks)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler: Optional[CallbackLogHandler] = None
    if not any(isinstance(h, CallbackLogHandler) for h in root.handlers):
        handler = attach_log_callback(
            root,
            console_log,
            formatter=logging.Formatter(_LOG_FORMAT),
        )

    try:
        yield hooks
    finally:
        if handler is not None:
            detach_log_callback(root, handler)
        set_active_hooks(None)
