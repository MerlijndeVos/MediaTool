"""Build the request-validation model for a mod's parameters.

A mod can export its own pydantic ``Params`` class (for validation the manifest cannot
express); otherwise the model is generated from the ``[[params]]`` tables in ``mod.toml``.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Annotated, Any, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, create_model

from core.mods import Mod, ModError, ParamSpec, registry

_lock = threading.Lock()
COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


def _iso_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a date written as YYYY-MM-DD") from exc
    return value


def _annotation(spec: ParamSpec) -> Any:
    kind = spec.type
    if kind in ("text", "folder", "file"):
        base: Any = str
    elif kind == "integer":
        base = int
    elif kind == "number":
        base = float
    elif kind == "bool":
        base = bool
    elif kind == "choice":
        base = Literal[tuple(c.value for c in spec.choices)] if spec.strict else str  # type: ignore[valid-type]
    elif kind in ("files", "list"):
        base = list[str]
    elif kind == "multichoice":
        base = list[Literal[tuple(c.value for c in spec.choices)]]  # type: ignore[valid-type]
    elif kind == "color":
        base = Annotated[str, Field(pattern=COLOR_PATTERN)]
    elif kind == "date":
        base = Annotated[str, AfterValidator(_iso_date)]
    else:  # json
        base = dict[str, Any]
    return Optional[base] if spec.nullable else base


def _field(spec: ParamSpec) -> Any:
    kwargs: dict[str, Any] = {}
    if spec.minimum is not None:
        kwargs["ge"] = spec.minimum
    if spec.maximum is not None:
        kwargs["le"] = spec.maximum
    if spec.required:
        return Field(..., **kwargs)
    default = spec.default
    if isinstance(default, (list, dict)):
        return Field(default_factory=lambda d=default: type(d)(d), **kwargs)
    return Field(default=default, **kwargs)


def _generate(mod: Mod, names: tuple[str, ...] | None = None) -> type[BaseModel]:
    specs = [spec for spec in mod.manifest.params if names is None or spec.name in names]
    fields = {spec.name: (_annotation(spec), _field(spec)) for spec in specs}
    title = "".join(part.capitalize() for part in mod.id.replace("-", "_").split("_")) + "Params"
    return create_model(title, **fields)  # type: ignore[call-overload]


def action_params_model(mod: Mod, names: tuple[str, ...] | None) -> type[BaseModel]:
    """Validates just the params an action receives (all of them when *names* is None)."""
    return _generate(mod, names)


def params_model(mod: Mod) -> type[BaseModel]:
    """The pydantic model that validates job parameters for *mod*.

    Generated from the manifest when it declares ``[[params]]``; a mod without them (the
    built-in mods with a custom panel) must export a ``Params`` model instead.
    """
    with _lock:
        cached = mod.cache.get("params_model")
        if cached is not None:
            return cached
    if mod.manifest.params:
        model = _generate(mod)
    else:
        custom = mod.params_class()
        if custom is not None and not issubclass(custom, BaseModel):
            raise ModError(f"Mod '{mod.id}': Params must be a pydantic BaseModel.")
        model = custom or _generate(mod)
    with _lock:
        mod.cache["params_model"] = model
    return model


def get_enabled_mod(mod_id: str) -> Mod:
    mod = registry.get(mod_id)
    if mod is None:
        raise ValueError(f"Unknown command: {mod_id}")
    if mod.is_theme:
        raise ValueError(f"'{mod_id}' is a theme, not a tool: there is nothing to run.")
    if not mod.enabled:
        raise ValueError(f"Mod '{mod_id}' is turned off. Enable it in Settings → Mods.")
    return mod


def validate_params(mod_id: str, params: dict[str, Any]) -> BaseModel:
    """Validate *params* for the enabled mod *mod_id*; raises ``ValueError`` when invalid."""
    mod = get_enabled_mod(mod_id)
    return params_model(mod).model_validate(params)
