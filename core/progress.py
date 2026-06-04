"""Shared progress/log callbacks for CLI, GUI and future web front-ends.

Core operations primarily use :mod:`logging`. This module adds optional hooks so
a front-end can stream log lines or structured progress (e.g. yt-dlp download
percent) without replacing the logger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

_active_hooks: Optional["LogHooks"] = None

LogCallback = Callable[[str, int], None]
"""Receive a formatted log line and the record's ``levelno``."""

ProgressCallback = Callable[[dict], None]
"""Receive a structured progress payload (download status, bytes, pct, etc.)."""


@dataclass
class LogHooks:
    """Optional callbacks attached alongside standard logging."""

    on_log: Optional[LogCallback] = None
    on_progress: Optional[ProgressCallback] = None


class CallbackLogHandler(logging.Handler):
    """Forward formatted log records to an ``on_log`` callback."""

    def __init__(
        self,
        on_log: LogCallback,
        formatter: Optional[logging.Formatter] = None,
    ) -> None:
        super().__init__()
        if formatter is not None:
            self.setFormatter(formatter)
        elif not self.formatter:
            self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self._on_log = on_log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._on_log(self.format(record), record.levelno)
        except Exception:
            pass


def attach_log_callback(
    logger: logging.Logger,
    on_log: LogCallback,
    *,
    formatter: Optional[logging.Formatter] = None,
) -> CallbackLogHandler:
    """Add a handler that mirrors log output to ``on_log``. Returns the handler."""
    handler = CallbackLogHandler(on_log, formatter=formatter)
    logger.addHandler(handler)
    return handler


def detach_log_callback(logger: logging.Logger, handler: CallbackLogHandler) -> None:
    """Remove and close a callback handler installed by :func:`attach_log_callback`."""
    try:
        handler.close()
    except Exception:
        pass
    logger.removeHandler(handler)


def set_active_hooks(hooks: Optional[LogHooks]) -> None:
    """Set session hooks for the current front-end (CLI, web, tests)."""
    global _active_hooks
    _active_hooks = hooks


def get_active_hooks() -> LogHooks:
    """Return the active session hooks, or an empty :class:`LogHooks` instance."""
    return _active_hooks if _active_hooks is not None else LogHooks()
