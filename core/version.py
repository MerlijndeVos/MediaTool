"""Application version — canonical value is ``[project].version`` in pyproject.toml."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


@lru_cache(maxsize=1)
def read_pyproject_version() -> str:
    with _PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    version = data.get("project", {}).get("version")
    if not version or not isinstance(version, str):
        raise RuntimeError(f"Missing [project].version in {_PYPROJECT}")
    return version


def app_version() -> str:
    """Version of the running app (installed metadata, else pyproject.toml)."""
    try:
        from importlib.metadata import version

        return version("media-tool")
    except Exception:
        return read_pyproject_version()
