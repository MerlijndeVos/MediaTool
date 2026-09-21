"""Mod system: features described by a ``mod.toml`` manifest plus a ``main.py`` with ``run()``.

Toolbox's own features are mods too (see ``builtin_mods/``), so the app and third-party
mods go through the same loader, job runner and UI. See ``MODDING.md``.
"""

from .context import ModCancelled, ModContext
from .manifest import (
    API_VERSION,
    ActionSpec,
    Condition,
    ManifestError,
    ModManifest,
    ParamSpec,
    SectionSpec,
    load_manifest,
    parse_manifest,
)
from . import groups, install, market, prompts, results, theme
from .registry import (
    DEFAULT_THEME_ID,
    LoadError,
    Mod,
    ModError,
    ModRegistry,
    Notice,
    builtin_mods_dir,
    read_install_meta,
    registry,
    safe_mode,
    set_safe_mode,
    user_mods_dir,
)

__all__ = [
    "API_VERSION",
    "ActionSpec",
    "Condition",
    "DEFAULT_THEME_ID",
    "LoadError",
    "ManifestError",
    "Mod",
    "ModCancelled",
    "ModContext",
    "ModError",
    "ModManifest",
    "ModRegistry",
    "Notice",
    "ParamSpec",
    "SectionSpec",
    "builtin_mods_dir",
    "load_manifest",
    "read_install_meta",
    "parse_manifest",
    "registry",
    "safe_mode",
    "set_safe_mode",
    "user_mods_dir",
]
