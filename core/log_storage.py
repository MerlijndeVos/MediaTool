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
