"""Helpers for spawning child processes without flashing consoles on Windows."""

from __future__ import annotations

import subprocess
import sys


def no_window_kwargs() -> dict:
    """Extra subprocess.run kwargs to hide the console on Windows GUI apps."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
