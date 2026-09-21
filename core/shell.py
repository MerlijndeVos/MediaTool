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


# Files that would run a program when "opened". The page may only reveal these in their folder.
NOT_OPENED_SUFFIXES = frozenset(
    {
        ".exe", ".dll", ".so", ".dylib", ".pyd", ".bat", ".cmd", ".ps1", ".sh", ".jar", ".msi", ".scr",
        ".vbs", ".com", ".lnk", ".url", ".reg", ".hta", ".js", ".jse", ".wsf", ".msc", ".py", ".pyw",
        ".app", ".command", ".appimage", ".desktop",
    }
)


def can_open_directly(path: Path) -> bool:
    """False for anything that could start a program; those are shown in their folder instead."""
    return path.is_dir() or path.suffix.lower() not in NOT_OPENED_SUFFIXES


def reveal_path(path: Path) -> None:
    """Show a file in its folder (selected where the OS supports it) without opening it."""
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))
    if sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{resolved}"], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(resolved)], check=True)
    else:
        subprocess.run(["xdg-open", str(resolved.parent)], check=True)
