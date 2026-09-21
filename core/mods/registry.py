"""Find, list and load mods.

Two places are searched:

* ``builtin_mods/`` next to the app: the features that ship with Toolbox. Always on.
* ``<app data>/mods/``: mods the user dropped in. **Off until the user enables them**, and
  skipped completely in safe mode (``--no-mods`` or ``TOOLBOX_NO_MODS=1``).

Reading a manifest never runs mod code. A mod's ``main.py`` is imported the first time the
mod is actually run.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

from ..runtime import app_data_dir, resource_root
from ..settings_store import load_settings, save_settings
from .manifest import MANIFEST_NAME, ManifestError, ModManifest, load_manifest

logger = logging.getLogger(__name__)

BUILTIN_DIRNAME = "builtin_mods"
USER_DIRNAME = "mods"
# Written into a mod's folder when it is installed from a git URL, folder, zip or file:
# where it came from and the exact commit, so the panel can show it and check for updates.
INSTALL_META = ".toolbox-install.json"
MODULE_PREFIX = "toolbox_mod_"
SAFE_MODE_ENV = "TOOLBOX_NO_MODS"
# The variable's name before version 3.0. Still honoured: silently ignoring a safety switch
# someone set to keep a misbehaving mod off would turn that mod back on after the update.
LEGACY_SAFE_MODE_ENV = "MEDIA_TOOL_NO_MODS"
_SAFE_MODE_ENVS = (SAFE_MODE_ENV, LEGACY_SAFE_MODE_ENV)


class ModError(RuntimeError):
    """A mod could not be found, loaded or run."""


@dataclass
class LoadError:
    path: str
    message: str
    mod_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "message": self.message, "id": self.mod_id}


@dataclass
class Mod:
    manifest: ModManifest
    source: str  # "builtin" | "user"
    path: Path
    enabled: bool
    _module: Optional[ModuleType] = field(default=None, repr=False)
    # Scratch space for the front-ends (e.g. the API caches the validation model here).
    cache: dict[str, Any] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def builtin(self) -> bool:
        return self.source == "builtin"

    def load_module(self) -> ModuleType:
        """Import the mod's entry file once. Raises :class:`ModError` if it cannot be loaded."""
        with self._lock:
            if self._module is not None:
                return self._module
            entry = (self.path / self.manifest.entry).resolve()
            try:
                entry.relative_to(self.path.resolve())
            except ValueError as exc:
                raise ModError(f"Mod '{self.id}': entry file is outside the mod folder.") from exc
            if not entry.is_file():
                raise ModError(f"Mod '{self.id}': entry file {self.manifest.entry} not found.")
            # Flat, dot-free name so relative imports (`from .helpers import x`) work.
            name = module_name(self.id)
            spec = importlib.util.spec_from_file_location(
                name, entry, submodule_search_locations=[str(self.path)]
            )
            if spec is None or spec.loader is None:
                raise ModError(f"Mod '{self.id}': cannot load {self.manifest.entry}.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as exc:
                sys.modules.pop(name, None)
                raise ModError(f"Mod '{self.id}' failed to load: {exc}") from exc
            if not callable(getattr(module, "run", None)):
                sys.modules.pop(name, None)
                raise ModError(f"Mod '{self.id}': {self.manifest.entry} must define run(params, ctx).")
            self._module = module
            return module

    def run_fn(self) -> Callable[..., Any]:
        return self.load_module().run

    def undo_fn(self) -> Callable[..., Any] | None:
        fn = getattr(self.load_module(), "undo", None)
        return fn if callable(fn) else None

    def params_class(self) -> type | None:
        """Optional pydantic model a mod can export as ``Params`` for validation."""
        cls = getattr(self.load_module(), "Params", None)
        return cls if isinstance(cls, type) else None

    def to_dict(self) -> dict[str, Any]:
        data = self.manifest.to_dict()
        data["source"] = self.source
        data["builtin"] = self.builtin
        data["enabled"] = self.enabled
        data["path"] = None if self.builtin else str(self.path)
        data["install"] = None if self.builtin else read_install_meta(self.path)
        return data


def module_name(mod_id: str) -> str:
    return MODULE_PREFIX + mod_id.replace("-", "_")


def unload_modules(mod_id: str) -> None:
    """Forget an imported mod (and its helper modules) so the next run imports it afresh."""
    name = module_name(mod_id)
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        sys.modules.pop(key, None)


def read_install_meta(mod_dir: Path) -> dict[str, Any] | None:
    """The record written when a mod was installed, or None for a mod that was just dropped in."""
    try:
        data = json.loads((mod_dir / INSTALL_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def safe_mode() -> bool:
    return any(
        os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
        for name in _SAFE_MODE_ENVS
    )


def set_safe_mode(enabled: bool = True) -> None:
    """Start with user mods off (built-in features are unaffected)."""
    if enabled:
        os.environ[SAFE_MODE_ENV] = "1"
    else:
        for name in _SAFE_MODE_ENVS:
            os.environ.pop(name, None)


def builtin_mods_dir() -> Path:
    return resource_root() / BUILTIN_DIRNAME


def user_mods_dir(create: bool = False) -> Path:
    path = app_data_dir() / USER_DIRNAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


class ModRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mods: dict[str, Mod] = {}
        self._errors: list[LoadError] = []
        self._loaded = False

    def _scan(self, directory: Path, source: str, enabled_user: set[str]) -> None:
        if not directory.is_dir():
            return
        for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            manifest_path = child / MANIFEST_NAME
            if not child.is_dir() or not manifest_path.is_file():
                continue
            try:
                manifest = load_manifest(manifest_path)
            except ManifestError as exc:
                logger.warning("Skipping mod folder %s: %s", child, exc)
                self._errors.append(LoadError(str(child), str(exc)))
                continue
            if manifest.id in self._mods:
                self._errors.append(
                    LoadError(
                        str(child),
                        f"id '{manifest.id}' is already used by another mod.",
                        manifest.id,
                    )
                )
                continue
            if source == "user" and manifest.ui_kind == "builtin":
                self._errors.append(
                    LoadError(
                        str(child),
                        "only built-in mods can use ui kind \"builtin\"; use kind = \"form\".",
                        manifest.id,
                    )
                )
                continue
            enabled = True if source == "builtin" else manifest.id in enabled_user
            self._mods[manifest.id] = Mod(manifest, source, child, enabled)

    def reload(self) -> None:
        """Rescan the built-in and user folders (mod modules already imported stay cached)."""
        with self._lock:
            self._mods = {}
            self._errors = []
            enabled_user = {str(x) for x in load_settings().get("enabled_mods", [])}
            self._scan(builtin_mods_dir(), "builtin", enabled_user)
            if not safe_mode():
                self._scan(user_mods_dir(), "user", enabled_user)
            self._loaded = True

    def _ensure(self) -> None:
        if not self._loaded:
            self.reload()

    def all(self) -> list[Mod]:
        """Every discovered mod, ordered by group position, then order, then name."""
        with self._lock:
            self._ensure()
            mods = list(self._mods.values())
        group_rank: dict[str, int] = {}
        for mod in mods:
            group_rank[mod.manifest.group] = min(
                group_rank.get(mod.manifest.group, mod.manifest.order), mod.manifest.order
            )
        return sorted(
            mods,
            key=lambda m: (group_rank[m.manifest.group], m.manifest.group, m.manifest.order, m.manifest.name.lower()),
        )

    def enabled(self) -> list[Mod]:
        return [m for m in self.all() if m.enabled]

    def get(self, mod_id: str) -> Mod | None:
        with self._lock:
            self._ensure()
            return self._mods.get(mod_id)

    def errors(self) -> list[LoadError]:
        with self._lock:
            self._ensure()
            return list(self._errors)

    def forget_enabled(self, mod_id: str) -> None:
        """Drop *mod_id* from the enabled list (used when a mod is removed)."""
        with self._lock:
            current = {str(x) for x in load_settings().get("enabled_mods", [])}
            if mod_id in current:
                current.discard(mod_id)
                save_settings(enabled_mods=sorted(current))

    def set_enabled(self, mod_id: str, enabled: bool) -> Mod:
        with self._lock:
            self._ensure()
            mod = self._mods.get(mod_id)
            if mod is None:
                raise ModError(f"Unknown mod: {mod_id}")
            if mod.builtin:
                raise ModError("Built-in features are always on.")
            current = {str(x) for x in load_settings().get("enabled_mods", [])}
            if enabled:
                current.add(mod_id)
            else:
                current.discard(mod_id)
            save_settings(enabled_mods=sorted(current))
            mod.enabled = enabled
            return mod


registry = ModRegistry()
