"""Media Tool core library.

All business logic lives here, independent of any front-end. The CLI
(``cli`` package), web API (``web``), and desktop app all call the same
``run_*`` entry points.
"""

from . import config

from .config import (
    DEFAULT_CRF,
    DEFAULT_X264_PRESET,
    DEFAULT_VTS_MIN_MB,
)
from .logging_setup import (
    setup_logging,
    setup_simple_logging,
    close_log_handlers,
)
from .convert import run_convert, run_trim, run_stitch
from .vts import run_vts
from .rename import run_rename, run_dedup
from .audio import run_audio
from .download import run_download, download_url, DownloadCancelled
from .rename_folders import run_rename_folders
from .progress import (
    CallbackLogHandler,
    LogHooks,
    LogCallback,
    ProgressCallback,
    attach_log_callback,
    detach_log_callback,
    get_active_hooks,
    set_active_hooks,
)

__all__ = [
    "config",
    "DEFAULT_CRF",
    "DEFAULT_X264_PRESET",
    "DEFAULT_VTS_MIN_MB",
    "setup_logging",
    "setup_simple_logging",
    "close_log_handlers",
    "run_convert",
    "run_trim",
    "run_stitch",
    "run_vts",
    "run_rename",
    "run_dedup",
    "run_audio",
    "run_download",
    "download_url",
    "DownloadCancelled",
    "run_rename_folders",
    "CallbackLogHandler",
    "LogHooks",
    "LogCallback",
    "ProgressCallback",
    "attach_log_callback",
    "detach_log_callback",
    "get_active_hooks",
    "set_active_hooks",
]
