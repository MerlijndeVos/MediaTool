"""Application version — canonical value is ``[project].version`` in pyproject.toml."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from .runtime import is_frozen, resource_root

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_BUNDLED_VERSION = ".bundled-version"


def normalize_version(raw: str) -> str:
    return raw.strip().lstrip("vV")


@lru_cache(maxsize=1)
def read_pyproject_version() -> str:
    with _PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    version = data.get("project", {}).get("version")
    if not version or not isinstance(version, str):
        raise RuntimeError(f"Missing [project].version in {_PYPROJECT}")
    return normalize_version(version)


def _read_bundled_version() -> str | None:
    path = resource_root() / _BUNDLED_VERSION
    if not path.is_file():
        return None
    text = normalize_version(path.read_text(encoding="utf-8"))
    return text or None


def app_version() -> str:
    """Version of the running app (bundled file when frozen, else installed metadata)."""
    if is_frozen():
        bundled = _read_bundled_version()
        if bundled:
            return bundled

    try:
        from importlib.metadata import version

        return normalize_version(version("media-tool"))
    except Exception:
        return read_pyproject_version()
