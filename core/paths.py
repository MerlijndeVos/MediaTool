"""Network-drive / long-path safe filesystem helpers (Windows).

Mapped network drives (e.g. ``Z:\\...``) behave like normal drive letters and
work out of the box. UNC paths (``\\\\server\\share\\...``) also work, but both
can exceed the legacy 260-character MAX_PATH limit when folders get deep.
Prefixing a path with the Windows extended-length marker lets the OS accept
long paths and avoids surprises on network shares.
"""

import os
import shutil
from pathlib import Path


def ext_path(path: Path) -> str:
    """Return a filesystem path string safe for long paths / UNC on Windows.

    On non-Windows platforms (or for relative paths) the plain string is returned.
    """
    if os.name != "nt":
        return str(path)

    # Only absolute paths can be expressed in extended-length form.
    raw = str(path)
    if raw.startswith("\\\\?\\") or raw.startswith("\\\\.\\"):
        return raw
    if not path.is_absolute():
        return raw

    if raw.startswith("\\\\"):
        # UNC: \\server\share\...  ->  \\?\UNC\server\share\...
        return "\\\\?\\UNC\\" + raw.lstrip("\\")
    return "\\\\?\\" + raw


def path_exists(path: Path) -> bool:
    return os.path.exists(ext_path(path))


def make_dirs(path: Path) -> None:
    os.makedirs(ext_path(path), exist_ok=True)


def move_path(src: Path, dst: Path) -> None:
    """Move src -> dst, handling same-volume rename and cross-volume copy."""
    src_s, dst_s = ext_path(src), ext_path(dst)
    try:
        os.replace(src_s, dst_s)
    except OSError:
        # Different volume (e.g. local -> network share) or other rename limit.
        shutil.move(src_s, dst_s)


def copy_path(src: Path, dst: Path) -> None:
    shutil.copy2(ext_path(src), ext_path(dst))
