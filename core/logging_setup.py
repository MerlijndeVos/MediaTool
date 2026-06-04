"""Logging setup shared by every operation.

File logging is gated on :data:`core.config.FILE_LOGGING_ENABLED`, which is read
*at call time* (via attribute access on the ``config`` module) so the GUI can
flip it at runtime. Console handlers are skipped when the root logger already
has handlers, because the GUI installs a root handler and relies on propagation
(and redirects ``sys.stderr`` into the same log queue).
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from . import config
from .paths import ext_path


def _reset_logger_handlers(logger: logging.Logger) -> None:
    """Detach existing handlers, closing file handles so the file is not locked.

    ``logging.Logger.handlers.clear()`` only drops the references; on Windows the
    underlying OS file handle stays open (and the log file stays locked) until the
    handler is explicitly closed. We close every handler before clearing.
    """
    for handler in list(logger.handlers):
        try:
            handler.close()
        except Exception:  # closing is best-effort
            pass
    logger.handlers.clear()


def close_log_handlers(*names: str) -> None:
    """Close and remove file handlers for the named loggers.

    Called when an operation finishes so its log file is released immediately and
    can be deleted while the GUI is still open.
    """
    for name in names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.close()
                except Exception:
                    pass
                logger.removeHandler(handler)


def setup_logging(output_root: Path) -> Tuple[logging.Logger, logging.Logger]:
    output_root.mkdir(parents=True, exist_ok=True)
    log_file = output_root / "convert.log"
    fail_log_file = output_root / "failures.log"

    logger = logging.getLogger("dv_to_mp4")
    logger.setLevel(logging.INFO)
    _reset_logger_handlers(logger)  # Avoid duplicate/locked handlers when called repeatedly

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Console handler.
    # Skip it when the root logger already has handlers: the GUI installs a
    # handler on the root logger and relies on propagation, and it also
    # redirects sys.stderr into the same log queue. Adding our own
    # StreamHandler there would surface every record twice.
    if not logging.getLogger().handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    failure_logger = logging.getLogger("dv_to_mp4.failures")
    failure_logger.setLevel(logging.WARNING)
    _reset_logger_handlers(failure_logger)

    logger.info("Logging initialized.")
    if config.FILE_LOGGING_ENABLED:
        # Main log file
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # Failures log file
        fh_fail = logging.FileHandler(fail_log_file, encoding="utf-8")
        fh_fail.setLevel(logging.WARNING)
        fh_fail.setFormatter(formatter)
        failure_logger.addHandler(fh_fail)

        logger.info("Main log: %s", log_file)
        logger.info("Failures log: %s", fail_log_file)
    else:
        logger.info("File logging disabled (no log file written).")

    return logger, failure_logger


def setup_simple_logging(name: str, log_path: Optional[Path]) -> logging.Logger:
    """Console logger with an optional log file.

    A file is only written when :data:`core.config.FILE_LOGGING_ENABLED` is true;
    otherwise no file handle is opened (so nothing is locked). The handle, when
    opened, is released by :func:`close_log_handlers` once the operation finishes.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    _reset_logger_handlers(logger)  # Avoid duplicate/locked handlers when called repeatedly
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Console handler. Skip it when the root logger already has handlers (the
    # GUI installs a root handler and relies on propagation, and also redirects
    # sys.stderr into the same log queue), otherwise every record is doubled.
    if not logging.getLogger().handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if log_path is not None and config.FILE_LOGGING_ENABLED:
        try:
            os.makedirs(ext_path(log_path.parent), exist_ok=True)
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as exc:  # logging to file is best-effort
            logger.warning("Could not open log file '%s': %s", log_path, exc)

    return logger
