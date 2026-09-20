"""Parse and validate a mod's ``mod.toml`` manifest.

A manifest is plain data: it never runs code. Loading (and therefore running) a mod's
``main.py`` only happens when the mod is actually used, see :mod:`core.mods.registry`.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

API_VERSION = 1
MANIFEST_NAME = "mod.toml"

ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
PARAM_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,39}$")
# Names the CLI already uses for its own subcommands.
RESERVED_IDS = frozenset({"mods"})

PARAM_TYPES = (
    "text",
    "number",
    "integer",
    "bool",
    "choice",
    "folder",
    "file",
    "files",
    "list",
    "json",
)
UI_KINDS = ("form", "builtin")
RUN_MODES = ("preview_apply", "run")
CANCEL_MODES = ("immediate", "cooperative")
WIDTHS = ("full", "half")


class _Missing:
    """Marks 'no default' (``None`` is a valid default for nullable params)."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"


MISSING: Any = _Missing()


class ManifestError(ValueError):
    """The manifest is malformed; the message says what to fix."""


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    label: str
    help: str = ""
    placeholder: str = ""
    required: bool = False
    default: Any = MISSING
    # Value the form starts with when it differs from the API default.
    initial: Any = MISSING
    choices: tuple[Choice, ...] = ()
    # choice params: False = the dropdown only suggests values, any string is accepted.
    strict: bool = True
    minimum: float | None = None
    maximum: float | None = None
    ui: bool = True
    width: str = "full"
    nullable: bool = False

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "label": self.label,
            "help": self.help,
            "placeholder": self.placeholder,
            "required": self.required,
            "choices": [{"value": c.value, "label": c.label} for c in self.choices],
            "strict": self.strict,
            "min": self.minimum,
            "max": self.maximum,
            "ui": self.ui,
            "width": self.width,
            "nullable": self.nullable,
        }
        if self.has_default:
            data["default"] = self.default
        if self.initial is not MISSING:
            data["initial"] = self.initial
        return data


@dataclass(frozen=True)
class Permissions:
    """Advisory only: shown to the user, never enforced."""

    network: bool = False
    writes_files: bool = False
    runs_programs: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "network": self.network,
            "writes_files": self.writes_files,
            "runs_programs": self.runs_programs,
        }


@dataclass(frozen=True)
class ModManifest:
    id: str
    name: str
    description: str = ""
    version: str = "0.0.0"
    author: str = ""
    api_version: int = API_VERSION
    group: str = "Other"
    order: int = 1000
    icon: str = "puzzle"
    entry: str = "main.py"
    ui_kind: str = "form"
    ui_panel: str = ""
    run_mode: str = "preview_apply"
    mode_param: str = "dry_run"
    mode_inverted: bool = False
    apply_hint: str = ""
    loggers: tuple[str, ...] = ()
    max_concurrent: int = 0
    cancel: str = "immediate"
    undo: bool = False
    permissions: Permissions = field(default_factory=Permissions)
    params: tuple[ParamSpec, ...] = ()

    def param(self, name: str) -> ParamSpec | None:
        for spec in self.params:
            if spec.name == name:
                return spec
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "group": self.group,
            "order": self.order,
            "icon": self.icon,
            "ui": {
                "kind": self.ui_kind,
                "panel": self.ui_panel,
                "run_mode": self.run_mode,
                "mode_param": self.mode_param,
                "mode_inverted": self.mode_inverted,
                "apply_hint": self.apply_hint,
            },
            "run": {
                "max_concurrent": self.max_concurrent,
                "cancel": self.cancel,
                "undo": self.undo,
            },
            "permissions": self.permissions.to_dict(),
            "params": [p.to_dict() for p in self.params],
        }


def _expect(table: dict[str, Any], key: str, kind: type | tuple[type, ...], where: str, default: Any = None) -> Any:
    if key not in table:
        return default
    value = table[key]
    # bool is an int subclass; never accept True/False where a number is expected.
    if isinstance(value, bool) and kind in (int, float, (int, float)):
        raise ManifestError(f"{where}: '{key}' must be a number, not true/false.")
    if not isinstance(value, kind):
        names = kind.__name__ if isinstance(kind, type) else " or ".join(k.__name__ for k in kind)
        raise ManifestError(f"{where}: '{key}' must be {names}.")
    return value


def _parse_choices(raw: Any, where: str) -> tuple[Choice, ...]:
    if not isinstance(raw, list) or not raw:
        raise ManifestError(f"{where}: 'choices' must be a non-empty list.")
    out: list[Choice] = []
    for item in raw:
        if isinstance(item, str):
            out.append(Choice(item, item))
        elif isinstance(item, dict) and isinstance(item.get("value"), str):
            value = item["value"]
            label = item.get("label", value)
            if not isinstance(label, str):
                raise ManifestError(f"{where}: a choice 'label' must be text.")
            out.append(Choice(value, label))
        else:
            raise ManifestError(f"{where}: each choice is a string or a {{value, label}} table.")
    if len({c.value for c in out}) != len(out):
        raise ManifestError(f"{where}: choice values must be unique.")
    return tuple(out)


def _check_value(value: Any, spec_type: str, where: str, *, nullable: bool, choices: tuple[Choice, ...], strict: bool) -> None:
    if value is None:
        if not nullable:
            raise ManifestError(f"{where}: null is only allowed when nullable = true.")
        return
    ok = {
        "text": isinstance(value, str),
        "folder": isinstance(value, str),
        "file": isinstance(value, str),
        "choice": isinstance(value, str),
        "bool": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "files": isinstance(value, list) and all(isinstance(v, str) for v in value),
        "list": isinstance(value, list) and all(isinstance(v, str) for v in value),
        "json": isinstance(value, dict),
    }[spec_type]
    if not ok:
        raise ManifestError(f"{where}: value {value!r} does not match type '{spec_type}'.")
    if spec_type == "choice" and strict and value not in {c.value for c in choices}:
        raise ManifestError(f"{where}: value {value!r} is not one of the choices.")


def _parse_param(raw: Any, index: int) -> ParamSpec:
    where = f"params[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} must be a table.")
    name = _expect(raw, "name", str, where)
    if not name or not PARAM_NAME_RE.match(name):
        raise ManifestError(f"{where}: 'name' must be lowercase letters, digits and underscores (got {name!r}).")
    where = f"param '{name}'"
    ptype = _expect(raw, "type", str, where, "text")
    if ptype not in PARAM_TYPES:
        raise ManifestError(f"{where}: unknown type {ptype!r}. Use one of: {', '.join(PARAM_TYPES)}.")

    nullable = bool(_expect(raw, "nullable", bool, where, False))
    choices: tuple[Choice, ...] = ()
    if ptype == "choice":
        choices = _parse_choices(raw.get("choices"), where)
    elif "choices" in raw:
        raise ManifestError(f"{where}: 'choices' only applies to type 'choice'.")
    strict = bool(_expect(raw, "strict", bool, where, True))

    minimum = _expect(raw, "min", (int, float), where)
    maximum = _expect(raw, "max", (int, float), where)
    if (minimum is not None or maximum is not None) and ptype not in ("number", "integer"):
        raise ManifestError(f"{where}: 'min'/'max' only apply to number and integer params.")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ManifestError(f"{where}: 'min' is larger than 'max'.")

    default = raw["default"] if "default" in raw else MISSING
    initial = raw["initial"] if "initial" in raw else MISSING
    if default is not MISSING:
        _check_value(default, ptype, f"{where} default", nullable=nullable, choices=choices, strict=strict)
    if initial is not MISSING:
        _check_value(initial, ptype, f"{where} initial", nullable=nullable, choices=choices, strict=strict)

    required = _expect(raw, "required", bool, where)
    if required is None:
        required = default is MISSING and not nullable
    if nullable and default is MISSING:
        default = None

    width = _expect(raw, "width", str, where, "full")
    if width not in WIDTHS:
        raise ManifestError(f"{where}: 'width' must be 'full' or 'half'.")

    label = _expect(raw, "label", str, where, name.replace("_", " ").capitalize())
    return ParamSpec(
        name=name,
        type=ptype,
        label=label,
        help=_expect(raw, "help", str, where, ""),
        placeholder=_expect(raw, "placeholder", str, where, ""),
        required=required,
        default=default,
        initial=initial,
        choices=choices,
        strict=strict,
        minimum=minimum,
        maximum=maximum,
        ui=bool(_expect(raw, "ui", bool, where, True)),
        width=width,
        nullable=nullable,
    )


def parse_manifest(data: dict[str, Any]) -> ModManifest:
    """Validate the parsed TOML *data* and return a :class:`ModManifest`."""
    where = "manifest"
    mod_id = _expect(data, "id", str, where)
    if not mod_id or not ID_RE.match(mod_id):
        raise ManifestError(
            "'id' is required: lowercase letters, digits, '-' and '_', starting with a letter "
            f"(got {mod_id!r})."
        )
    if mod_id in RESERVED_IDS:
        raise ManifestError(f"'{mod_id}' is a reserved id; pick another.")
    name = _expect(data, "name", str, where)
    if not name:
        raise ManifestError("'name' is required.")

    api_version = _expect(data, "api_version", int, where, API_VERSION)
    if api_version > API_VERSION:
        raise ManifestError(
            f"needs mod API version {api_version}, but this Media Tool supports {API_VERSION}. "
            "Update Media Tool or use an older version of the mod."
        )
    if api_version < 1:
        raise ManifestError("'api_version' must be 1 or higher.")

    entry = _expect(data, "entry", str, where, "main.py")
    entry_path = Path(entry)
    if entry_path.is_absolute() or ".." in entry_path.parts or entry_path.suffix != ".py":
        raise ManifestError("'entry' must be a .py file inside the mod folder.")

    ui = _expect(data, "ui", dict, where, {})
    run = _expect(data, "run", dict, where, {})
    perms = _expect(data, "permissions", dict, where, {})

    ui_kind = _expect(ui, "kind", str, "[ui]", "form")
    if ui_kind not in UI_KINDS:
        raise ManifestError(f"[ui] 'kind' must be one of: {', '.join(UI_KINDS)}.")
    ui_panel = _expect(ui, "panel", str, "[ui]", "")
    if ui_kind == "builtin" and not ui_panel:
        raise ManifestError("[ui] kind = \"builtin\" needs a 'panel'.")
    run_mode = _expect(ui, "run_mode", str, "[ui]", "preview_apply")
    if run_mode not in RUN_MODES:
        raise ManifestError(f"[ui] 'run_mode' must be one of: {', '.join(RUN_MODES)}.")

    raw_params = data.get("params", [])
    if not isinstance(raw_params, list):
        raise ManifestError("'params' must be a list of [[params]] tables.")
    params = tuple(_parse_param(p, i) for i, p in enumerate(raw_params))
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise ManifestError("param names must be unique.")

    mode_param = _expect(ui, "mode_param", str, "[ui]", "dry_run")
    if ui_kind == "form" and run_mode == "preview_apply":
        target = next((p for p in params if p.name == mode_param), None)
        if target is None or target.type != "bool":
            raise ManifestError(
                f"[ui] run_mode = \"preview_apply\" needs a bool param named '{mode_param}' "
                "(set [ui] mode_param, or use run_mode = \"run\")."
            )

    cancel = _expect(run, "cancel", str, "[run]", "immediate")
    if cancel not in CANCEL_MODES:
        raise ManifestError(f"[run] 'cancel' must be one of: {', '.join(CANCEL_MODES)}.")
    max_concurrent = _expect(run, "max_concurrent", int, "[run]", 0)
    if max_concurrent < 0:
        raise ManifestError("[run] 'max_concurrent' cannot be negative.")
    loggers = _expect(run, "loggers", list, "[run]", [])
    if not all(isinstance(x, str) for x in loggers):
        raise ManifestError("[run] 'loggers' must be a list of logger names.")

    return ModManifest(
        id=mod_id,
        name=name,
        description=_expect(data, "description", str, where, ""),
        version=str(_expect(data, "version", str, where, "0.0.0")),
        author=_expect(data, "author", str, where, ""),
        api_version=api_version,
        group=_expect(data, "group", str, where, "Other") or "Other",
        order=_expect(data, "order", int, where, 1000),
        icon=_expect(data, "icon", str, where, "puzzle"),
        entry=entry,
        ui_kind=ui_kind,
        ui_panel=ui_panel,
        run_mode=run_mode,
        mode_param=mode_param,
        mode_inverted=bool(_expect(ui, "mode_inverted", bool, "[ui]", False)),
        apply_hint=_expect(ui, "apply_hint", str, "[ui]", ""),
        loggers=tuple(loggers),
        max_concurrent=max_concurrent,
        cancel=cancel,
        undo=bool(_expect(run, "undo", bool, "[run]", False)),
        permissions=Permissions(
            network=bool(_expect(perms, "network", bool, "[permissions]", False)),
            writes_files=bool(_expect(perms, "writes_files", bool, "[permissions]", False)),
            runs_programs=bool(_expect(perms, "runs_programs", bool, "[permissions]", False)),
        ),
        params=params,
    )


def load_manifest(path: Path) -> ModManifest:
    """Read *path* (a ``mod.toml``) and return its validated manifest."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot read {path.name}: {exc}") from exc
    return parse_manifest(data)
