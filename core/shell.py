"""Open local paths with the OS default handler."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> None:
    """Open a file or folder with the system default application."""
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))

    if sys.platform == "win32":
        os.startfile(resolved)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(resolved)], check=True)
        return
    subprocess.run(["xdg-open", str(resolved)], check=True)
