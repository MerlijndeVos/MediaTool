"""The mod market: a public index of mods that people can browse, search and install.

The index is one JSON file (default: ``market/index.json`` in the Toolbox repository). Each entry
points at a git repository **and an exact commit**, so what someone installs is what was listed.
Listing means only that the entry is well-formed: the project does not review mods, and the app
says so wherever it offers one. The trust prompt always shows the code that was really
downloaded, and warns when it disagrees with the listing. See ``market/README.md``.

Format (``"format": 1``)::

    {"format": 1, "mods": [{
        "id": "count-files", "name": "Count Files", "description": "...", "author": "...",
        "version": "1.0.0", "repo": "https://github.com/owner/repo", "commit": "<40 hex>",
        "path": "folder/in/repo",            # optional
        "type": "tool",                      # optional: "tool" (default) or "theme"
        "group": "Files",                    # optional: the menu section a tool appears in
        "swatches": ["#fdf6e3", "..."],      # optional: up to 8 #rrggbb colours, for themes
        "tags": ["files"], "license": "MIT", "homepage": "https://...",  # optional
        "permissions": {"network": false, "writes_files": false, "runs_programs": false}
    }]}
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

from .groups import canonical_group
from .install import SHA_RE, InstallError, _http_get, parse_git_url
from .manifest import API_VERSION, ID_RE, MOD_TYPES
from .registry import ModError

DEFAULT_MARKET_URL = "https://raw.githubusercontent.com/MerlijndeVos/Toolbox/main/market/index.json"
MARKET_URL_ENV = "TOOLBOX_MARKET_URL"
INDEX_FORMAT = 1
MAX_INDEX_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 600
MAX_TAGS = 8
MAX_SWATCHES = 8
SWATCH_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def market_url() -> str:
    return os.environ.get(MARKET_URL_ENV, "").strip() or DEFAULT_MARKET_URL


def _text(raw: dict[str, Any], key: str, limit: int, *, required: bool = False) -> str:
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"'{key}' is required")
    if len(value) > limit:
        raise ValueError(f"'{key}' is too long")
    return value


def parse_entry(raw: Any) -> dict[str, Any]:
    """Validate one index entry and return it in a normalised form. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("an entry must be an object")
    mod_id = _text(raw, "id", 40, required=True)
    if not ID_RE.match(mod_id):
        raise ValueError(f"'{mod_id}' is not a valid mod id")
    commit = _text(raw, "commit", 40, required=True).lower()
    if not SHA_RE.match(commit):
        raise ValueError("'commit' must be the full 40-character commit hash")
    try:
        source = parse_git_url(_text(raw, "repo", 300, required=True), subdir=_text(raw, "path", 200))
    except InstallError as exc:
        raise ValueError(str(exc)) from exc
    if source.ref:
        raise ValueError("'repo' must be the plain repository address; the commit goes in 'commit'")
    api_version = raw.get("api_version", API_VERSION)
    if not isinstance(api_version, int) or isinstance(api_version, bool):
        raise ValueError("'api_version' must be a number")
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError("'tags' must be a list of text")
    homepage = _text(raw, "homepage", 300)
    if homepage and not homepage.lower().startswith("https://"):
        raise ValueError("'homepage' must be an https address")
    mod_type = raw.get("type", "tool")
    if mod_type not in MOD_TYPES:
        raise ValueError(f"'type' must be one of: {', '.join(MOD_TYPES)}")
    swatches = raw.get("swatches", [])
    if not isinstance(swatches, list) or not all(isinstance(c, str) and SWATCH_RE.match(c) for c in swatches):
        raise ValueError("'swatches' must be a list of #rrggbb colours")
    if len(swatches) > MAX_SWATCHES:
        raise ValueError(f"'swatches' can have at most {MAX_SWATCHES} colours")
    group = _text(raw, "group", 40)
    perms = raw.get("permissions")
    if perms is not None:
        if not isinstance(perms, dict) or not all(isinstance(v, bool) for v in perms.values()):
            raise ValueError("'permissions' must be a table of true/false values")
        perms = {k: bool(perms.get(k, False)) for k in ("network", "writes_files", "runs_programs")}
    return {
        "id": mod_id,
        "name": _text(raw, "name", 80, required=True),
        "description": _text(raw, "description", 400),
        "author": _text(raw, "author", 80),
        "version": _text(raw, "version", 40) or "0.0.0",
        "api_version": api_version,
        "type": mod_type,
        # Empty when the listing does not say; the trust prompt shows the real one from the code.
        "group": canonical_group(group) if group and mod_type == "tool" else "",
        "swatches": [c.lower() for c in swatches],
        "repo": source.url,
        "path": source.subdir,
        "commit": commit,
        "tags": [t.strip().lower()[:24] for t in tags if t.strip()][:MAX_TAGS],
        "license": _text(raw, "license", 40),
        "homepage": homepage,
        "permissions": perms,
    }


def parse_index(data: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """(entries, problems). One bad entry is skipped and reported; it never hides the rest."""
    if not isinstance(data, dict) or not isinstance(data.get("mods"), list):
        raise ModError("The market index is not in the expected format.")
    if data.get("format", INDEX_FORMAT) != INDEX_FORMAT:
        raise ModError("The market index is from a newer version of Toolbox. Update the app to browse it.")
    entries: list[dict[str, Any]] = []
    problems: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(data["mods"]):
        try:
            entry = parse_entry(raw)
        except ValueError as exc:
            label = raw.get("id") if isinstance(raw, dict) else i
            problems.append(f"{label}: {exc}")
            continue
        if entry["id"] in seen:
            problems.append(f"{entry['id']}: listed twice")
            continue
        seen.add(entry["id"])
        entries.append(entry)
    return entries, problems


def matches(entry: dict[str, Any], query: str) -> bool:
    words = query.lower().split()
    haystack = " ".join(
        [entry["id"], entry["name"], entry["description"], entry["author"], entry["type"], entry["group"], " ".join(entry["tags"])]
    ).lower()
    return all(w in haystack for w in words)


def fetch_market(force: bool = False) -> dict[str, Any]:
    """The listed mods, from a short-lived cache unless *force*. Never raises: errors come back in the result."""
    url = market_url()
    with _lock:
        cached = _cache.get("result")
        if cached and not force and cached["url"] == url and time.time() - cached["at"] < CACHE_SECONDS:
            return cached["value"]
    try:
        body = _http_get(url, limit=MAX_INDEX_BYTES)
        entries, problems = parse_index(json.loads(body.decode("utf-8")))
        value = {"url": url, "mods": entries, "problems": problems, "error": None}
    except (InstallError, ModError, ValueError) as exc:
        value = {"url": url, "mods": [], "problems": [], "error": f"Could not load the market: {exc}"}
    with _lock:
        if value["error"] is None:
            _cache["result"] = {"url": url, "at": time.time(), "value": value}
        else:
            _cache.pop("result", None)
    return value
