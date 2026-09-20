"""Mod system: features described by a ``mod.toml`` manifest plus a ``main.py`` with ``run()``.

Media Tool's own features are mods too (see ``builtin_mods/``), so the app and third-party
mods go through the same loader, job runner and UI. See ``MODDING.md``.
"""

from .context import ModCancelled, ModContext
from .manifest import (
    API_VERSION,
    ManifestError,
    ModManifest,
    ParamSpec,
    load_manifest,
    parse_manifest,
)
from .registry import (
    LoadError,
    Mod,
    ModError,
    ModRegistry,
    builtin_mods_dir,
    registry,
    safe_mode,
    set_safe_mode,
    user_mods_dir,
)

__all__ = [
    "API_VERSION",
    "LoadError",
    "ManifestError",
    "Mod",
    "ModCancelled",
    "ModContext",
    "ModError",
    "ModManifest",
    "ModRegistry",
    "ParamSpec",
    "builtin_mods_dir",
    "load_manifest",
    "parse_manifest",
    "registry",
    "safe_mode",
    "set_safe_mode",
    "user_mods_dir",
]
