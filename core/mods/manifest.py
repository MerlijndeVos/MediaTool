"""Parse and validate a mod's ``mod.toml`` manifest.

A manifest is plain data: it never runs code. Loading (and therefore running) a mod's
``main.py`` only happens when the mod is actually used, see :mod:`core.mods.registry`.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .groups import canonical_group
from .manifest_errors import ManifestError
from .theme import ThemeSpec, parse_theme

# 2 added theme mods (`type = "theme"`), form sections/tabs, `show_if`, the multichoice, color and
# date params, the slider widget, actions and accents. Mods written for 1 keep working unchanged.
API_VERSION = 2
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
    "multichoice",
    "color",
    "date",
)
MOD_TYPES = ("tool", "theme")
UI_KINDS = ("form", "builtin")
RUN_MODES = ("preview_apply", "run")
CANCEL_MODES = ("immediate", "cooperative")
WIDTHS = ("full", "half")
WIDGETS = ("default", "slider")
LAYOUTS = ("sections", "tabs")
# Where a tool's tile takes its colour from: a category, or one of the status colours (all theme tokens).
ACCENTS = ("files", "media", "subtitles", "experimental", "other", "settings", "primary", "success", "warning", "danger")
THEME_GROUP = "Themes"
# The icons a mod can pick with `icon = "..."` (lucide names). Keep in step with
# web/frontend/src/lib/modIcons.ts: a test compares them. Unknown names fall back to "puzzle".
ICON_NAMES = (
    "archive", "audio-lines", "bar-chart-3", "calendar", "camera", "clipboard-list", "clock", "cloud",
    "code", "combine", "copy", "cpu", "database", "disc-3", "download", "eraser", "file", "file-audio",
    "file-image", "file-search", "file-text", "file-video", "files", "film", "folder", "folder-pen",
    "folder-search", "gauge", "globe", "hard-drive", "hash", "history", "image", "inbox", "languages",
    "layers", "link", "list-checks", "lock", "mail", "monitor", "music", "palette", "pen-line", "play",
    "puzzle", "scissors", "search", "settings", "shield", "sliders-horizontal", "sparkles", "star",
    "table", "tag", "trash-2", "upload", "video", "wand-sparkles", "wrench", "zap",
)
MAX_TEXT = 4000

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A theme has no code and no form: it only has [theme] and the descriptive keys.
THEME_FORBIDDEN = ("entry", "ui", "run", "permissions", "params", "sections", "actions", "accent", "group", "order", "icon")
CONDITION_OPS = ("equals", "not_equals", "in", "truthy")


class _Missing:
    """Marks 'no default' (``None`` is a valid default for nullable params)."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"


MISSING: Any = _Missing()


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Condition:
    """``show_if``: show a field or section only while another param has a certain value."""

    param: str
    op: str  # equals | not_equals | in | truthy | falsy
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"param": self.param, "op": self.op, "value": self.value}


@dataclass(frozen=True)
class SectionSpec:
    """A titled group of fields, optionally with an explanatory text and a ``show_if``."""

    id: str
    title: str
    text: str = ""
    show_if: Condition | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "show_if": self.show_if.to_dict() if self.show_if else None,
        }


@dataclass(frozen=True)
class ActionSpec:
    """An extra button next to Run that calls ``action_<name>(params, ctx)`` in ``main.py``."""

    name: str
    label: str
    help: str = ""
    # Which params the function receives; None = all of them.
    params: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "help": self.help,
            "params": list(self.params) if self.params is not None else None,
        }


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
    section: str = ""
    show_if: Condition | None = None
    widget: str = "default"
    step: float | None = None

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
            "section": self.section,
            "show_if": self.show_if.to_dict() if self.show_if else None,
            "widget": self.widget,
            "step": self.step,
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
    type: str = "tool"
    theme: ThemeSpec | None = None
    layout: str = "sections"
    accent: str = ""
    sections: tuple[SectionSpec, ...] = ()
    actions: tuple[ActionSpec, ...] = ()

    @property
    def is_theme(self) -> bool:
        return self.type == "theme"

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
            "type": self.type,
            "group": self.group,
            "order": self.order,
            "icon": self.icon,
            "accent": self.accent,
            "ui": {
                "kind": self.ui_kind,
                "layout": self.layout,
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
            "sections": [x.to_dict() for x in self.sections],
            "actions": [a.to_dict() for a in self.actions],
            "theme": self.theme.to_dict() if self.theme else None,
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
        "multichoice": isinstance(value, list) and all(isinstance(v, str) for v in value),
        "json": isinstance(value, dict),
        "color": isinstance(value, str) and bool(COLOR_RE.match(value)),
        "date": isinstance(value, str) and _is_iso_date(value),
    }[spec_type]
    if not ok:
        hint = {"color": " (write a colour as #rrggbb)", "date": " (write a date as YYYY-MM-DD)"}.get(spec_type, "")
        raise ManifestError(f"{where}: value {value!r} does not match type '{spec_type}'{hint}.")
    if spec_type == "choice" and strict and value not in {c.value for c in choices}:
        raise ManifestError(f"{where}: value {value!r} is not one of the choices.")
    if spec_type == "multichoice" and not {c.value for c in choices} >= set(value):
        raise ManifestError(f"{where}: every value has to be one of the choices.")


def _is_iso_date(text: str) -> bool:
    if not DATE_RE.match(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _parse_condition(raw: Any, where: str) -> Condition:
    """``show_if = { param = "mode", equals = "advanced" }`` (or ``not_equals``, ``in``, ``truthy``)."""
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: 'show_if' must be a table such as {{ param = \"mode\", equals = \"advanced\" }}.")
    unknown = sorted(set(raw) - {"param", *CONDITION_OPS})
    if unknown:
        raise ManifestError(f"{where}: 'show_if' has unknown key '{unknown[0]}'. Use param plus one of: {', '.join(CONDITION_OPS)}.")
    param = _expect(raw, "param", str, f"{where} show_if")
    if not param or not PARAM_NAME_RE.match(param):
        raise ManifestError(f"{where}: 'show_if' needs 'param', the name of another field.")
    given = [op for op in CONDITION_OPS if op in raw]
    if len(given) > 1:
        raise ManifestError(f"{where}: 'show_if' takes only one of: {', '.join(CONDITION_OPS)}.")
    if not given:
        return Condition(param, "truthy", True)
    op = given[0]
    value = raw[op]
    if op == "truthy":
        if not isinstance(value, bool):
            raise ManifestError(f"{where}: show_if 'truthy' must be true or false.")
        return Condition(param, "truthy" if value else "falsy", value)
    if op == "in":
        if not isinstance(value, list) or not value or not all(_scalar(v) for v in value):
            raise ManifestError(f"{where}: show_if 'in' must be a non-empty list of values.")
        return Condition(param, "in", list(value))
    if not _scalar(value):
        raise ManifestError(f"{where}: show_if '{op}' must be a single value.")
    return Condition(param, op, value)


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
    if ptype in ("choice", "multichoice"):
        choices = _parse_choices(raw.get("choices"), where)
    elif "choices" in raw:
        raise ManifestError(f"{where}: 'choices' only applies to type 'choice' and 'multichoice'.")
    strict = bool(_expect(raw, "strict", bool, where, True))
    if ptype == "multichoice":
        strict = True

    minimum = _expect(raw, "min", (int, float), where)
    maximum = _expect(raw, "max", (int, float), where)
    if (minimum is not None or maximum is not None) and ptype not in ("number", "integer"):
        raise ManifestError(f"{where}: 'min'/'max' only apply to number and integer params.")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ManifestError(f"{where}: 'min' is larger than 'max'.")

    widget = _expect(raw, "widget", str, where, "default")
    if widget not in WIDGETS:
        raise ManifestError(f"{where}: 'widget' must be one of: {', '.join(WIDGETS)}.")
    step = _expect(raw, "step", (int, float), where)
    if widget == "slider":
        if ptype not in ("number", "integer"):
            raise ManifestError(f"{where}: the slider widget only works for number and integer params.")
        if minimum is None or maximum is None:
            raise ManifestError(f"{where}: a slider needs both 'min' and 'max'.")
    elif step is not None:
        raise ManifestError(f"{where}: 'step' only applies to the slider widget.")
    if step is not None and step <= 0:
        raise ManifestError(f"{where}: 'step' must be larger than 0.")

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

    section = _expect(raw, "section", str, where, "")
    show_if = _parse_condition(raw["show_if"], where) if "show_if" in raw else None
    if show_if is not None and show_if.param == name:
        raise ManifestError(f"{where}: 'show_if' cannot refer to the field itself.")

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
        section=section,
        show_if=show_if,
        widget=widget,
        step=step,
    )


def _parse_section(raw: Any, index: int) -> SectionSpec:
    where = f"sections[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} must be a table.")
    section_id = _expect(raw, "id", str, where)
    if not section_id or not ID_RE.match(section_id):
        raise ManifestError(f"{where}: 'id' must be lowercase letters, digits, '-' and '_' (got {section_id!r}).")
    where = f"section '{section_id}'"
    text = _expect(raw, "text", str, where, "")
    if len(text) > MAX_TEXT:
        raise ManifestError(f"{where}: 'text' is too long (at most {MAX_TEXT} characters).")
    return SectionSpec(
        id=section_id,
        title=_expect(raw, "title", str, where, section_id.replace("-", " ").replace("_", " ").capitalize()),
        text=text,
        show_if=_parse_condition(raw["show_if"], where) if "show_if" in raw else None,
    )


def _parse_action(raw: Any, index: int) -> ActionSpec:
    where = f"actions[{index}]"
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} must be a table.")
    name = _expect(raw, "name", str, where)
    if not name or not PARAM_NAME_RE.match(name):
        raise ManifestError(f"{where}: 'name' must be lowercase letters, digits and underscores (got {name!r}).")
    where = f"action '{name}'"
    params = raw.get("params")
    if params is not None and (not isinstance(params, list) or not all(isinstance(p, str) for p in params)):
        raise ManifestError(f"{where}: 'params' must be a list of param names.")
    return ActionSpec(
        name=name,
        label=_expect(raw, "label", str, where, name.replace("_", " ").capitalize()),
        help=_expect(raw, "help", str, where, ""),
        params=tuple(params) if params is not None else None,
    )


def _check_layout(
    params: tuple[ParamSpec, ...],
    sections: tuple[SectionSpec, ...],
    actions: tuple[ActionSpec, ...],
    layout: str,
) -> None:
    """Cross-checks between params, sections and actions that a single table cannot see."""
    names = {p.name for p in params}
    section_by_id = {s.id: s for s in sections}
    if len(section_by_id) != len(sections):
        raise ManifestError("section ids must be unique.")
    if layout == "tabs" and not sections:
        raise ManifestError('[ui] layout = "tabs" needs at least one [[sections]] table.')
    for section in sections:
        if section.show_if and section.show_if.param not in names:
            raise ManifestError(f"section '{section.id}': show_if refers to unknown param '{section.show_if.param}'.")
    for p in params:
        if p.section and p.section not in section_by_id:
            raise ManifestError(f"param '{p.name}': section '{p.section}' is not defined. Add a [[sections]] table with that id.")
        if p.show_if and p.show_if.param not in names:
            raise ManifestError(f"param '{p.name}': show_if refers to unknown param '{p.show_if.param}'.")
        hideable = p.show_if is not None or (p.section and section_by_id[p.section].show_if is not None)
        if hideable and p.required:
            raise ManifestError(
                f"param '{p.name}' can be hidden by show_if, so it needs a default "
                "(or nullable = true): a hidden field sends nothing."
            )
    action_names = [a.name for a in actions]
    if len(set(action_names)) != len(action_names):
        raise ManifestError("action names must be unique.")
    for action in actions:
        missing = [n for n in (action.params or ()) if n not in names]
        if missing:
            raise ManifestError(f"action '{action.name}': unknown param '{missing[0]}'.")


def _uses_api_2(params: tuple[ParamSpec, ...], sections: tuple, actions: tuple, layout: str, accent: str) -> str | None:
    """The first feature that needs mod API 2, or None."""
    if sections:
        return "[[sections]]"
    if actions:
        return "[[actions]]"
    if layout != "sections":
        return f'[ui] layout = "{layout}"'
    if accent:
        return "'accent'"
    for p in params:
        if p.type in ("multichoice", "color", "date"):
            return f"the '{p.type}' param type"
        if p.widget != "default":
            return f"the '{p.widget}' widget"
        if p.show_if:
            return "'show_if'"
        if p.section:
            return "'section'"
    return None


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
            f"needs mod API version {api_version}, but this Toolbox supports {API_VERSION}. "
            "Update Toolbox or use an older version of the mod."
        )
    if api_version < 1:
        raise ManifestError("'api_version' must be 1 or higher.")
    # What the author declared: a manifest that does not say counts as 1, so anything newer has to be asked for.
    declared_api = api_version if "api_version" in data else 1

    mod_type = _expect(data, "type", str, where, "tool")
    if mod_type not in MOD_TYPES:
        raise ManifestError(f"'type' must be one of: {', '.join(MOD_TYPES)}.")

    common: dict[str, Any] = dict(
        id=mod_id,
        name=name,
        description=_expect(data, "description", str, where, ""),
        version=str(_expect(data, "version", str, where, "0.0.0")),
        author=_expect(data, "author", str, where, ""),
        api_version=api_version,
        type=mod_type,
    )

    if mod_type == "theme":
        for key in THEME_FORBIDDEN:
            if key in data:
                raise ManifestError(f"a theme cannot have '{key}'; it only has the [theme] table.")
        if declared_api < 2:
            raise ManifestError("theme mods need mod API version 2; set api_version = 2 in mod.toml.")
        return ModManifest(**common, group=THEME_GROUP, entry="", run_mode="run", theme=parse_theme(data.get("theme")))

    if "theme" in data:
        raise ManifestError('a [theme] table only belongs in a theme mod; add type = "theme".')

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
    layout = _expect(ui, "layout", str, "[ui]", "sections")
    if layout not in LAYOUTS:
        raise ManifestError(f"[ui] 'layout' must be one of: {', '.join(LAYOUTS)}.")

    raw_params = data.get("params", [])
    if not isinstance(raw_params, list):
        raise ManifestError("'params' must be a list of [[params]] tables.")
    params = tuple(_parse_param(p, i) for i, p in enumerate(raw_params))
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise ManifestError("param names must be unique.")

    raw_sections = data.get("sections", [])
    if not isinstance(raw_sections, list):
        raise ManifestError("'sections' must be a list of [[sections]] tables.")
    sections = tuple(_parse_section(s, i) for i, s in enumerate(raw_sections))
    raw_actions = data.get("actions", [])
    if not isinstance(raw_actions, list):
        raise ManifestError("'actions' must be a list of [[actions]] tables.")
    actions = tuple(_parse_action(a, i) for i, a in enumerate(raw_actions))
    _check_layout(params, sections, actions, layout)

    accent = _expect(data, "accent", str, where, "")
    if accent and accent not in ACCENTS:
        raise ManifestError(f"'accent' must be one of: {', '.join(ACCENTS)}.")

    feature = _uses_api_2(params, sections, actions, layout, accent)
    if feature and declared_api < 2:
        raise ManifestError(f"{feature} needs mod API version 2; set api_version = 2 in mod.toml.")

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
        **common,
        group=canonical_group(_expect(data, "group", str, where, "Other")),
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
        layout=layout,
        accent=accent,
        sections=sections,
        actions=actions,
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
