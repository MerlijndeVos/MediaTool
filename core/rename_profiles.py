"""Rename format profiles: user-defined cleanup rules and output patterns.

A profile is shared by both rename modes (shows/movies and folders). It holds

* ``rules`` -- an ordered list of text cleanup steps applied to names,
* ``patterns`` -- optional output patterns per context (``tv``, ``movie``,
  ``generic``) built from ``{token}`` placeholders,
* ``strip_release_junk`` -- whether shows/movies mode removes the built-in list
  of release tags (``1080p``, ``WEB-DL``, ...),
* ``date_locale`` -- the language of month names for the ``{date}`` token and the
  "remove dates" rule (``en`` or ``nl``).

Profiles are plain JSON so they can be saved, sent over the API and produced by
the AI helper. Everything here is validated; nothing in a profile is executed.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .dates import (
    DATE_LOCALES,
    DEFAULT_DATE_SPEC,
    literal_regex,
    date_spec_regex,
    format_date,
    prune_date_text,
    validate_date_spec,
)
from .runtime import app_data_dir
from .text_utils import sentence_case, title_case

MAX_RULES = 40
MAX_NAME_LEN = 60
MAX_FIND_LEN = 200

RULE_TYPES = ("replace", "remove_words", "remove_brackets", "case", "regex_replace", "prune_date")
CASE_MODES = ("keep", "title", "lower", "upper", "sentence")
BRACKET_KINDS = ("[]", "()", "{}")

PATTERN_KEYS = ("tv", "movie", "generic")

# Tokens each pattern context understands.
PATTERN_TOKENS: Dict[str, Tuple[str, ...]] = {
    "tv": ("show", "season", "episode", "episode_end", "code", "title", "year"),
    "movie": ("title", "year"),
    # {date}: the earliest date in the video file names inside the folder (see core.dates)
    "generic": ("name", "parent", "n", "date"),
}

DEFAULT_PATTERNS: Dict[str, str] = {
    "tv": "{show} - {code} - {title}",
    "movie": "{title} ({year})",
    "generic": "{name}",
}

STANDARD_ID = "builtin:standard"
TIDY_ID = "builtin:tidy"
DATE_NAME_ID = "builtin:date-name"


class ProfileError(ValueError):
    """Raised when a profile (or part of one) is invalid."""


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    rules: Tuple[Dict[str, Any], ...] = ()
    patterns: Dict[str, str] = field(default_factory=dict)
    strip_release_junk: bool = True
    builtin: bool = False
    date_locale: str = "en"

    @property
    def title_case(self) -> bool:
        """True if the last case rule is Title Case (used by the franchise formatter)."""
        mode = None
        for rule in self.rules:
            if rule["type"] == "case":
                mode = rule["mode"]
        return mode == "title"

    def pattern(self, key: str) -> str:
        return self.patterns.get(key) or DEFAULT_PATTERNS[key]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "rules": [dict(r) for r in self.rules],
            "patterns": dict(self.patterns),
            "strip_release_junk": self.strip_release_junk,
            "date_locale": self.date_locale,
            "builtin": self.builtin,
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _clean_str(value: Any, field_name: str, *, max_len: int = MAX_FIND_LEN) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{field_name} must be text.")
    if len(value) > max_len:
        raise ProfileError(f"{field_name} is too long (max {max_len} characters).")
    return value


def _normalize_rule(raw: Any, index: int) -> Dict[str, Any]:
    where = f"Rule {index + 1}"
    if not isinstance(raw, dict):
        raise ProfileError(f"{where} must be an object.")
    rtype = raw.get("type")
    if rtype not in RULE_TYPES:
        raise ProfileError(f"{where}: unknown rule type {rtype!r}.")

    if rtype == "replace":
        find = _clean_str(raw.get("find", ""), f"{where} 'find'")
        if not find:
            raise ProfileError(f"{where}: 'find' cannot be empty.")
        return {"type": rtype, "find": find, "with": _clean_str(raw.get("with", ""), f"{where} 'with'")}

    if rtype == "remove_words":
        words = raw.get("words")
        if isinstance(words, str):
            words = [w for w in re.split(r"[,\n]", words)]
        if not isinstance(words, list):
            raise ProfileError(f"{where}: 'words' must be a list.")
        cleaned: List[str] = []
        seen = set()
        for w in words:
            w = _clean_str(w, f"{where} word", max_len=80).strip()
            if w and w.lower() not in seen:
                seen.add(w.lower())
                cleaned.append(w)
        if not cleaned:
            raise ProfileError(f"{where}: add at least one word to remove.")
        return {"type": rtype, "words": cleaned}

    if rtype == "remove_brackets":
        kinds = raw.get("brackets", list(BRACKET_KINDS))
        if not isinstance(kinds, list) or not kinds or any(k not in BRACKET_KINDS for k in kinds):
            raise ProfileError(f"{where}: 'brackets' must be a non-empty list of {', '.join(BRACKET_KINDS)}.")
        return {"type": rtype, "brackets": [k for k in BRACKET_KINDS if k in kinds]}

    if rtype == "prune_date":
        return {"type": rtype}

    if rtype == "case":
        mode = raw.get("mode")
        if mode not in CASE_MODES:
            raise ProfileError(f"{where}: case mode must be one of {', '.join(CASE_MODES)}.")
        return {"type": rtype, "mode": mode}

    # regex_replace
    pattern = _clean_str(raw.get("pattern", ""), f"{where} 'pattern'")
    if not pattern:
        raise ProfileError(f"{where}: regex pattern cannot be empty.")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ProfileError(f"{where}: invalid regex ({exc}).") from exc
    return {"type": rtype, "pattern": pattern, "with": _clean_str(raw.get("with", ""), f"{where} 'with'")}


_TOKEN_RE = re.compile(r"\{(\w+)(?::([^{}]*))?\}")
_SPEC_RE = re.compile(r"^(?:\d{1,2}|upper|lower|title)$")


def validate_pattern(pattern: str, key: str) -> str:
    """Check a pattern's tokens/specs for context *key*; return it unchanged."""
    pattern = _clean_str(pattern, f"{key} pattern", max_len=200)
    if "/" in pattern or "\\" in pattern:
        raise ProfileError("Patterns define the name only; they cannot contain / or \\.")
    allowed = PATTERN_TOKENS[key]
    for m in _TOKEN_RE.finditer(pattern):
        token, spec = m.group(1), m.group(2)
        if token not in allowed:
            raise ProfileError(
                f"Unknown token {{{token}}} in the {key} pattern. Available: "
                + ", ".join("{" + t + "}" for t in allowed)
                + "."
            )
        if token == "date":
            if spec is not None:
                try:
                    validate_date_spec(spec)
                except ValueError as exc:
                    raise ProfileError(str(exc)) from exc
        elif spec is not None and not _SPEC_RE.match(spec):
            raise ProfileError(f"Invalid format {{{token}:{spec}}} (use e.g. :02, :upper, :lower or :title).")
    if "{" in _TOKEN_RE.sub("", pattern) or "}" in _TOKEN_RE.sub("", pattern):
        raise ProfileError("Unbalanced { } in pattern.")
    if not _TOKEN_RE.search(pattern):
        raise ProfileError("A pattern needs at least one {token}.")
    return pattern


def profile_from_dict(data: Any, *, builtin: bool = False) -> Profile:
    """Validate and normalise a profile dict (from the API, disk or the AI)."""
    if not isinstance(data, dict):
        raise ProfileError("Profile must be an object.")
    name = _clean_str(data.get("name", ""), "Profile name", max_len=MAX_NAME_LEN).strip()
    if not name:
        raise ProfileError("Give the profile a name.")

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ProfileError("'rules' must be a list.")
    if len(raw_rules) > MAX_RULES:
        raise ProfileError(f"Too many rules (max {MAX_RULES}).")
    rules = tuple(_normalize_rule(r, i) for i, r in enumerate(raw_rules))

    raw_patterns = data.get("patterns") or {}
    if not isinstance(raw_patterns, dict):
        raise ProfileError("'patterns' must be an object.")
    patterns: Dict[str, str] = {}
    for key, value in raw_patterns.items():
        if key not in PATTERN_KEYS:
            raise ProfileError(f"Unknown pattern key {key!r}.")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        patterns[key] = validate_pattern(value.strip() if isinstance(value, str) else value, key)

    date_locale = data.get("date_locale") or "en"
    if date_locale not in DATE_LOCALES:
        raise ProfileError(f"date_locale must be one of {', '.join(DATE_LOCALES)}.")

    pid = data.get("id")
    if not isinstance(pid, str) or not pid.strip():
        pid = uuid.uuid4().hex
    return Profile(
        id=pid.strip(),
        name=name,
        rules=rules,
        patterns=patterns,
        strip_release_junk=bool(data.get("strip_release_junk", True)),
        builtin=builtin,
        date_locale=date_locale,
    )


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------

_BRACKET_RE = {
    "[]": re.compile(r"\[[^\[\]]*\]"),
    "()": re.compile(r"\([^()]*\)"),
    "{}": re.compile(r"\{[^{}]*\}"),
}
_YEAR_PAREN_RE = re.compile(r"^\(\s*(?:19|20)\d{2}\s*\)$")


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def finalize_text(text: str) -> str:
    """Collapse whitespace and trim leftover edge separators."""
    return _collapse(text).strip(" -_.")


def _remove_brackets(text: str, kinds: List[str], keep_year_parens: bool) -> str:
    for kind in kinds:
        rx = _BRACKET_RE[kind]

        def sub(m: "re.Match[str]", kind: str = kind) -> str:
            if keep_year_parens and kind == "()" and _YEAR_PAREN_RE.match(m.group(0)):
                return m.group(0)
            return " "

        for _ in range(3):  # nested brackets
            new = rx.sub(sub, text)
            if new == text:
                break
            text = new
    return text


def _remove_words(text: str, words: List[str]) -> str:
    ordered = sorted({w.lower() for w in words}, key=len, reverse=True)
    # Whole words, where "_" counts as a separator ([^\W_] = letters/digits only),
    # so "kick_free_download" matches "free" and "download".
    rx = re.compile(
        r"(?<![^\W_])(?:" + "|".join(re.escape(w) for w in ordered) + r")(?![^\W_])",
        re.IGNORECASE,
    )
    return rx.sub(" ", text)


def apply_rules(
    text: str,
    rules: Tuple[Dict[str, Any], ...],
    *,
    keep_year_parens: bool = False,
    date_locale: str = "en",
) -> str:
    """Run *rules* in order over *text* and tidy the result.

    With ``keep_year_parens`` a ``(2008)`` style year survives bracket removal
    (shows/movies mode relies on it). *date_locale* picks the month names the
    "remove dates" rule recognises.
    """
    for rule in rules:
        rtype = rule["type"]
        if rtype == "replace":
            text = text.replace(rule["find"], rule["with"])
        elif rtype == "remove_words":
            text = _remove_words(text, rule["words"])
        elif rtype == "remove_brackets":
            text = _remove_brackets(text, rule["brackets"], keep_year_parens)
        elif rtype == "case":
            mode = rule["mode"]
            text = _collapse(text)
            if mode == "title":
                text = title_case(text)
            elif mode == "lower":
                text = text.lower()
            elif mode == "upper":
                text = text.upper()
            elif mode == "sentence":
                text = sentence_case(text)
        elif rtype == "regex_replace":
            text = re.sub(rule["pattern"], rule["with"], text)
        elif rtype == "prune_date":
            text = prune_date_text(text, date_locale)
    return finalize_text(text)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def pattern_uses_token(pattern: str, token: str) -> bool:
    return any(m.group(1) == token for m in _TOKEN_RE.finditer(pattern))


def reverse_pattern(pattern: str, text: str, locale: str = "en") -> Optional[Tuple[Tuple[int, int, int], str]]:
    """Read ``(date, name)`` back out of *text* if it was already made with *pattern*.

    Only patterns built from ``{date}`` and ``{name}`` (plain text around them is fine)
    can be read back. This is what makes re-running a date rename harmless: a folder that
    already looks like ``2006 juli 13 - Holiday`` keeps its own date and is renamed from
    ``Holiday``, instead of getting a second date stuck on the front.
    """
    parts: List[str] = []
    date_rx = None
    have_name = False
    pos = 0
    for m in _TOKEN_RE.finditer(pattern):
        parts.append(literal_regex(pattern[pos : m.start()]))
        token, spec = m.group(1), m.group(2)
        if token == "date" and date_rx is None:
            date_rx = date_spec_regex(spec or DEFAULT_DATE_SPEC, locale)
            if date_rx is None:
                return None
            parts.append(date_rx.pattern)
        elif token == "name" and not have_name and spec is None:
            have_name = True
            parts.append(r"(?P<name>.+)")
        else:
            return None
        pos = m.end()
    parts.append(literal_regex(pattern[pos:]))
    if date_rx is None or not have_name:
        return None
    match = re.fullmatch("".join(parts), text.strip(), flags=re.IGNORECASE)
    if match is None:
        return None
    date = date_rx.to_date(match)
    if date is None:
        return None
    return date, match.group("name")


def render_pattern(pattern: str, values: Dict[str, Any], *, date_locale: str = "en") -> str:
    """Fill ``{token}`` / ``{token:spec}`` placeholders from *values*.

    ``{date}`` takes a ``(year, month, day)`` tuple and a date format such as
    ``{date:YYYY MMMM D}`` (see :mod:`core.dates`).

    Empty values are dropped together with the separators/brackets around them,
    so ``{show} - {code} - {title}`` without a title gives ``Show - S01E01``
    and ``{title} ({year})`` without a year gives ``Title``.
    """
    any_empty = False

    def sub(m: "re.Match[str]") -> str:
        nonlocal any_empty
        token, spec = m.group(1), m.group(2)
        value = values.get(token)
        if value is None or value == "":
            any_empty = True
            return ""
        if token == "date":
            return format_date(value, spec or DEFAULT_DATE_SPEC, date_locale)
        if spec:
            if spec.isdigit():
                try:
                    return str(int(value)).zfill(int(spec))
                except (TypeError, ValueError):
                    return str(value)
            if spec == "upper":
                return str(value).upper()
            if spec == "lower":
                return str(value).lower()
            if spec == "title":
                return title_case(str(value))
        return str(value)

    out = _TOKEN_RE.sub(sub, pattern)
    if any_empty:
        out = re.sub(r"\(\s*\)|\[\s*\]", "", out)
        out = _collapse(out)
        out = re.sub(r"(?:\s*-\s*){2,}", " - ", out)
    return finalize_text(out)


# ---------------------------------------------------------------------------
# Built-in profiles and storage
# ---------------------------------------------------------------------------

def builtin_profiles() -> List[Profile]:
    return [
        Profile(
            id=STANDARD_ID,
            name="Standard",
            rules=({"type": "case", "mode": "title"},),
            strip_release_junk=True,
            builtin=True,
        ),
        Profile(
            id=TIDY_ID,
            name="Tidy names",
            rules=(
                {"type": "replace", "find": "_", "with": " "},
                {"type": "replace", "find": ".", "with": " "},
                {"type": "remove_brackets", "brackets": ["[]", "{}"]},
            ),
            strip_release_junk=False,
            builtin=True,
        ),
        Profile(
            # Folders mode. Reproduces the old "Rename Folders" tool: 2006 juli 13 - Holiday.
            id=DATE_NAME_ID,
            name="Date + name (Dutch)",
            rules=({"type": "prune_date"},),
            patterns={"generic": "{date:YYYY MMMM D} - {name}"},
            strip_release_junk=False,
            builtin=True,
            date_locale="nl",
        ),
    ]


def standard_profile(*, title_case_enabled: bool = True) -> Profile:
    """Profile equivalent to the historic behaviour (Title Case + release cleanup)."""
    rules = ({"type": "case", "mode": "title"},) if title_case_enabled else ()
    return Profile(id=STANDARD_ID, name="Standard", rules=rules, strip_release_junk=True, builtin=True)


def _profiles_path() -> Path:
    return app_data_dir() / "rename_profiles.json"


def load_user_profiles() -> List[Profile]:
    path = _profiles_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("profiles", []) if isinstance(data, dict) else []
    except Exception:
        return []
    profiles: List[Profile] = []
    for item in raw:
        try:
            profiles.append(profile_from_dict(item))
        except ProfileError:
            continue  # skip a corrupt entry instead of breaking the whole list
    return profiles


def _write_user_profiles(profiles: List[Profile]) -> None:
    path = _profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": [{**p.to_dict(), "builtin": False} for p in profiles]}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def list_profiles() -> List[Profile]:
    return builtin_profiles() + load_user_profiles()


def get_profile(ident: str) -> Optional[Profile]:
    """Find a profile by id or (case-insensitive) name."""
    ident = (ident or "").strip()
    if not ident:
        return None
    for p in list_profiles():
        if p.id == ident:
            return p
    for p in list_profiles():
        if p.name.lower() == ident.lower():
            return p
    return None


def load_profile_spec(spec: Any) -> Optional[Profile]:
    """Resolve a profile from a Profile, a dict, a saved id/name, or a .json file path."""
    if spec is None or spec == "":
        return None
    if isinstance(spec, Profile):
        return spec
    if isinstance(spec, dict):
        return profile_from_dict(spec)
    text = str(spec)
    found = get_profile(text)
    if found is not None:
        return found
    path = Path(text)
    if path.is_file():
        try:
            return profile_from_dict(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"Profile file is not valid JSON: {exc}") from exc
    raise ProfileError(f"Profile not found: {text}")


def save_profile(data: Any) -> Profile:
    """Create or update a user profile. Built-ins cannot be overwritten."""
    profile = profile_from_dict(data)
    if any(b.id == profile.id for b in builtin_profiles()):
        profile = Profile(**{**profile.__dict__, "id": uuid.uuid4().hex})
    users = load_user_profiles()
    for other in list_profiles():
        if other.id != profile.id and other.name.lower() == profile.name.lower():
            raise ProfileError(f"A profile named '{profile.name}' already exists.")
    for i, existing in enumerate(users):
        if existing.id == profile.id:
            users[i] = profile
            break
    else:
        users.append(profile)
    _write_user_profiles(users)
    return profile


def delete_profile(profile_id: str) -> bool:
    if any(b.id == profile_id for b in builtin_profiles()):
        raise ProfileError("Built-in profiles cannot be deleted.")
    users = load_user_profiles()
    kept = [p for p in users if p.id != profile_id]
    if len(kept) == len(users):
        return False
    _write_user_profiles(kept)
    return True
