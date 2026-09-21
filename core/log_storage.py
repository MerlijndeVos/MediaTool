"""Centralized on-disk log storage under the per-user app data directory."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from .runtime import app_data_dir


class LogFileInfo(TypedDict):
    name: str
    size_bytes: int
    modified_at: str


class LogsStats(TypedDict):
    path: str
    total_bytes: int
    file_count: int
    files: list[LogFileInfo]


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def operation_log_path(operation: str) -> Path:
    """Return the append-only log file path for an operation type."""
    safe = operation.replace("/", "_").replace("\\", "_")
    return logs_dir() / f"{safe}.log"


def undo_journals_dir() -> Path:
    path = app_data_dir() / "undo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def rename_undo_journal_path(dest_root: Path) -> Path:
    """Per-destination undo journal under app data (not in the media library)."""
    normalized = os.path.normcase(os.path.abspath(str(dest_root)))
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return undo_journals_dir() / f"rename_{key}.json"


def logs_stats() -> LogsStats:
    root = logs_dir()
    files: list[LogFileInfo] = []
    total = 0
    for f in sorted(root.glob("*.log")):
        stat = f.stat()
        size = stat.st_size
        total += size
        files.append(
            {
                "name": f.name,
                "size_bytes": size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return {
        "path": str(root),
        "total_bytes": total,
        "file_count": len(files),
        "files": files,
    }


def clear_logs() -> int:
    """Delete all log files. Returns how many files were removed."""
    root = logs_dir()
    deleted = 0
    for f in root.glob("*.log"):
        try:
            f.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


def resolve_log_file(name: str) -> Path:
    """Return a log file path, rejecting traversal outside the logs directory."""
    if not name or name != Path(name).name or not name.endswith(".log"):
        raise ValueError(f"Invalid log file name: {name!r}")
    path = logs_dir() / name
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


class LogChunk(TypedDict):
    name: str
    size_bytes: int
    start: int
    end: int
    has_earlier: bool
    lines: list[str]


_READ_BLOCK = 64 * 1024
_MAX_CHUNK_BYTES = 1024 * 1024


def read_log_chunk(name: str, *, end: int | None = None, max_lines: int = 500) -> LogChunk:
    """Read up to ``max_lines`` whole lines that finish at byte offset ``end`` (default: the end of the file).

    Logs can be large, so this reads backwards in blocks and never loads the whole file. The result
    carries ``start``: pass it back as ``end`` to get the lines before this chunk. A chunk is capped at
    about 1 MB, so a file with very long lines comes back in smaller pieces. Offsets are bytes, so a
    chunk stays valid while the file grows (new lines are only ever appended).
    """
    path = resolve_log_file(name)
    with path.open("rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        end = size if end is None else max(0, min(end, size))
        pos = end
        data = b""
        while pos > 0 and data.count(b"\n") <= max_lines and len(data) < _MAX_CHUNK_BYTES:
            step = min(_READ_BLOCK, pos)
            pos -= step
            fh.seek(pos)
            data = fh.read(step) + data
        segments = data.splitlines(keepends=True)
        if pos > 0 and len(segments) > 1:
            # The first line may have been cut off by the block boundary; leave it for the next chunk.
            fh.seek(pos - 1)
            if fh.read(1) != b"\n":
                pos += len(segments.pop(0))
    if len(segments) > max_lines:
        cut = len(segments) - max_lines
        pos += sum(len(s) for s in segments[:cut])
        segments = segments[cut:]
    return {
        "name": name,
        "size_bytes": size,
        "start": pos,
        "end": end,
        "has_earlier": pos > 0,
        "lines": [s.decode("utf-8", errors="replace").rstrip("\r\n") for s in segments],
    }
