"""Result views: how a mod shows what it found, instead of only writing lines to the log.

A mod calls ``ctx.result(view, ...)``; Toolbox turns that into plain data (nothing a mod sends is
ever rendered as HTML) and the interface draws it with its own components::

    ctx.result("table", title="By extension", columns=["Extension", "Files"], rows=[[".mp4", 12]])
    ctx.result("counters", items={"Files": 12, "Size": "3.4 GB"})
    ctx.result("files", title="Largest", files=["D:/a.mkv", {"path": "D:/b.mkv", "label": "b"}])
    ctx.result("markdown", text="**Done.** See the log for details.")
    ctx.result("image", path="D:/preview.png")
    ctx.result("message", text="Connected.", level="success")

Everything is capped so a runaway mod cannot flood the interface: see the ``MAX_*`` constants.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

VIEWS = ("table", "counters", "files", "markdown", "image", "message")
LEVELS = ("info", "success", "warning", "error")

MAX_TITLE = 120
MAX_COLUMNS = 20
MAX_ROWS = 500
MAX_CELL = 300
MAX_COUNTERS = 24
MAX_FILES = 300
MAX_MARKDOWN = 20_000
MAX_IMAGE_BYTES = 3 * 1024 * 1024
# Only formats a browser shows as a plain picture. SVG is left out on purpose.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
# A run may report this many results in all (a mod that calls ctx.result in a loop gets cut off).
MAX_RESULTS_PER_JOB = 20


class ResultError(ValueError):
    """The mod asked for a result that cannot be shown; the message tells the author what to fix."""


def _text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cell(value: Any) -> str | int | float:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return value
    return _text(value, MAX_CELL)


def _table(fields: dict[str, Any]) -> dict[str, Any]:
    columns = fields.get("columns")
    rows = fields.get("rows")
    if not isinstance(columns, (list, tuple)) or not columns:
        raise ResultError("a table result needs columns=[...] (a list of column titles).")
    if not isinstance(rows, (list, tuple)):
        raise ResultError("a table result needs rows=[[...], ...] (a list of rows).")
    columns = [_text(c, 80) for c in list(columns)[:MAX_COLUMNS]]
    out_rows: list[list[Any]] = []
    for row in list(rows)[:MAX_ROWS]:
        if not isinstance(row, (list, tuple)):
            raise ResultError("every table row must be a list of cells.")
        cells = [_cell(v) for v in list(row)[: len(columns)]]
        cells += [""] * (len(columns) - len(cells))
        out_rows.append(cells)
    return {"columns": columns, "rows": out_rows, "truncated": len(rows) > MAX_ROWS}


def _counters(fields: dict[str, Any]) -> dict[str, Any]:
    items = fields.get("items")
    if isinstance(items, dict):
        pairs = list(items.items())
    elif isinstance(items, (list, tuple)):
        pairs = []
        for item in items:
            if isinstance(item, dict) and "label" in item:
                pairs.append((item["label"], item.get("value", "")))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                pairs.append((item[0], item[1]))
            else:
                raise ResultError("counters items must be a dict or a list of (label, value) pairs.")
    else:
        raise ResultError("a counters result needs items={label: value, ...}.")
    return {"items": [{"label": _text(k, 60), "value": _text(v, 60)} for k, v in pairs[:MAX_COUNTERS]]}


def _files(fields: dict[str, Any]) -> dict[str, Any]:
    files = fields.get("files")
    if not isinstance(files, (list, tuple)):
        raise ResultError("a files result needs files=[path, ...].")
    out: list[dict[str, str]] = []
    for item in list(files)[:MAX_FILES]:
        if isinstance(item, dict):
            path, label = item.get("path"), item.get("label")
        else:
            path, label = item, None
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ResultError("every file needs a path.")
        entry = {"path": str(path)}
        if label:
            entry["label"] = _text(label, 200)
        out.append(entry)
    return {"files": out, "truncated": len(files) > MAX_FILES}


def _markdown(fields: dict[str, Any]) -> dict[str, Any]:
    text = fields.get("text")
    if not isinstance(text, str):
        raise ResultError("a markdown result needs text=\"...\".")
    return {"text": text[:MAX_MARKDOWN]}


def _image(fields: dict[str, Any]) -> dict[str, Any]:
    raw = fields.get("path")
    if not isinstance(raw, (str, Path)):
        raise ResultError("an image result needs path=\"...\" (a .png, .jpg, .gif or .webp file).")
    path = Path(raw)
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime is None:
        raise ResultError("images can be .png, .jpg, .gif or .webp.")
    try:
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise ResultError(f"that image is too large to show ({size // 1024} KB; the limit is {MAX_IMAGE_BYTES // 1024} KB).")
        data = path.read_bytes()
    except OSError as exc:
        raise ResultError(f"cannot read the image: {exc}") from exc
    return {"src": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", "alt": _text(fields.get("alt") or path.name, 200)}


def _message(fields: dict[str, Any]) -> dict[str, Any]:
    text = fields.get("text")
    if not isinstance(text, str):
        raise ResultError("a message result needs text=\"...\".")
    level = fields.get("level", "info")
    if level not in LEVELS:
        raise ResultError(f"a message level is one of: {', '.join(LEVELS)}.")
    return {"text": text[:2000], "level": level}


_BUILDERS = {
    "table": _table,
    "counters": _counters,
    "files": _files,
    "markdown": _markdown,
    "image": _image,
    "message": _message,
}


def build_result(view: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Validate one result and return it as plain, size-limited data."""
    builder = _BUILDERS.get(view)
    if builder is None:
        raise ResultError(f"unknown result view {view!r}. Use one of: {', '.join(VIEWS)}.")
    payload = {"view": view, "title": _text(fields.get("title", ""), MAX_TITLE)}
    payload.update(builder(fields))
    return payload


def from_return(value: Any) -> list[dict[str, Any]]:
    """What an action function may return: nothing, text, a result dict, or a list of those."""
    if value is None:
        return []
    if isinstance(value, str):
        return [build_result("message", {"text": value})]
    if isinstance(value, dict):
        if "view" not in value:
            raise ResultError('an action returns text or a dict with a "view" key (see ctx.result).')
        fields = {k: v for k, v in value.items() if k != "view"}
        return [build_result(str(value["view"]), fields)]
    if isinstance(value, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in value:
            out.extend(from_return(item))
        return out
    raise ResultError("an action returns text, a dict with a \"view\" key, or a list of those.")


def openable_paths(results: list[dict[str, Any]]) -> set[str]:
    """Paths a ``files`` result lists: the only ones the interface may ask to open or reveal."""
    return {f["path"] for r in results if r.get("view") == "files" for f in r.get("files", [])}

