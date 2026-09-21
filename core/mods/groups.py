"""Categories: the sections mods appear in, in the sidebar and on the home screen.

A mod picks its category with ``group`` in ``mod.toml``. This module is the single place that
decides what a category name means:

* Names are compared ignoring case and extra spaces, so ``media``, ``Media`` and ``" Media "``
  are the same section, shown with the existing spelling.
* Five sections are built in and always come first, in a fixed order. A mod's ``order`` only
  positions the mod inside its section, never the section itself.
* A genuinely new name creates a new section after the built-in ones (alphabetical).
* A name that merely *looks* like an existing one (``Subtitle``, ``Sub-titles``) is not merged,
  but it is reported so nobody ends up with a silent lookalike section.
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable

DEFAULT_GROUP = "Other"

# (name, what belongs there). The order here is the order on screen.
BUILTIN_GROUPS: tuple[tuple[str, str], ...] = (
    ("Files", "Tools that rename, move or organize files and folders."),
    ("Media", "Tools that convert, cut, join or download video and audio."),
    ("Subtitles", "Tools that translate or clean up subtitle files."),
    ("Experimental", "Specialised or unfinished utilities for less common jobs."),
    (DEFAULT_GROUP, "Anything that does not fit above. The default when a mod sets no group."),
)

BUILTIN_GROUP_NAMES: tuple[str, ...] = tuple(name for name, _ in BUILTIN_GROUPS)

_NEAR_MISS_RATIO = 0.84
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def clean_group(name: str) -> str:
    """Trim the name and collapse runs of whitespace. An empty name is the default group."""
    return " ".join(str(name).split()) or DEFAULT_GROUP


def group_key(name: str) -> str:
    """What makes two names 'the same section': case and spacing are ignored."""
    return clean_group(name).casefold()


def canonical_group(name: str, known: Iterable[str] = ()) -> str:
    """The spelling to use for *name*: an existing section's spelling if one matches, else its own.

    Built-in sections win over *known* (the categories other mods already introduced), so
    ``media`` is always ``Media``.
    """
    cleaned = clean_group(name)
    key = cleaned.casefold()
    for existing in (*BUILTIN_GROUP_NAMES, *known):
        if existing.casefold() == key:
            return existing
    return cleaned


def _loose_key(name: str) -> str:
    """Spelling-insensitive form: 'Sub-titles', 'subtitle' and 'Subtitles' all become 'subtitle'."""
    text = _NON_ALNUM.sub("", name.casefold())
    return text[:-1] if len(text) > 3 and text.endswith("s") else text


def near_miss(name: str, known: Iterable[str] = ()) -> str | None:
    """The existing section *name* looks like without being the same name, if any.

    Case and spacing differences are not near-misses (they merge); plurals, hyphens and small
    typos are.
    """
    cleaned = clean_group(name)
    key = cleaned.casefold()
    candidates = list(dict.fromkeys((*BUILTIN_GROUP_NAMES, *known)))
    if any(c.casefold() == key for c in candidates):
        return None
    loose = _loose_key(cleaned)
    best: tuple[float, str] | None = None
    for existing in candidates:
        other = _loose_key(existing)
        ratio = 1.0 if loose == other else difflib.SequenceMatcher(None, loose, other).ratio()
        if ratio >= _NEAR_MISS_RATIO and (best is None or ratio > best[0]):
            best = (ratio, existing)
    return best[1] if best else None


def near_miss_message(name: str, existing: str) -> str:
    return (
        f"The category '{clean_group(name)}' looks like the existing '{existing}' but is not the "
        f"same name, so it becomes a separate section. Use group = \"{existing}\" to join it."
    )


def group_rank(name: str) -> tuple[int, int, str]:
    """Sort key for sections: the built-in ones in their fixed order, then new ones A to Z."""
    key = group_key(name)
    for index, existing in enumerate(BUILTIN_GROUP_NAMES):
        if existing.casefold() == key:
            return (0, index, "")
    return (1, 0, key)


def is_builtin_group(name: str) -> bool:
    return group_rank(name)[0] == 0


def groups_help() -> str:
    """One line per built-in category, for the AI prompt and the docs."""
    return "\n".join(f"- {name}: {text}" for name, text in BUILTIN_GROUPS)
