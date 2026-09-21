"""Dates in file and folder names: finding them, formatting them, pruning them.

Used by the rename profiles (the ``{date}`` pattern token and the "remove dates" rule).

Finding: the date of a video comes from its file name, in the two styles Toolbox's own
DV workflow produces (DV ``clip-2006-07-13 17;48;08.dv``, converted MP4
``13 juli 2006 17-48-08.mp4``). A folder's date is the earliest date of the videos in it.

Formatting uses a small date spec written after the token, e.g. ``{date:YYYY MMMM D}``:

- ``YYYY`` four-digit year (2006), ``YY`` two-digit year (06)
- ``MMMM`` month name (July / juli), ``MMM`` short month name (Jul / jul)
- ``MM`` month with two digits (07), ``M`` month (7)
- ``DD`` day with two digits (03), ``D`` day (3)

Anything else in the spec is copied as is. Month names depend on the profile's date
language (``en`` or ``nl``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

DateTuple = Tuple[int, int, int]  # (year, month, day)

DATE_LOCALES = ("en", "nl")
DEFAULT_DATE_SPEC = "YYYY-MM-DD"
# Used to preview a pattern when no real date is known (the profile tester).
SAMPLE_DATE: DateTuple = (2006, 7, 13)

MONTHS = {
    "nl": (
        "januari", "februari", "maart", "april", "mei", "juni",
        "juli", "augustus", "september", "oktober", "november", "december",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
}
MONTHS_SHORT = {
    "nl": ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}

VIDEO_EXTENSIONS = {".dv", ".mp4", ".avi", ".mov", ".mkv", ".m4v"}

# DV: clip-2006-07-13 17;48;08.dv
_RE_DV_DATE = re.compile(r"clip-(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE)
# MP4 from the dv_to_mp4 converter: 13 juli 2006 17-48-08.mp4 (always Dutch month names)
_RE_MP4_DATE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(MONTHS["nl"]) + r")\s+(\d{4})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Finding dates
# ---------------------------------------------------------------------------

def parse_date_from_filename(name: str) -> Optional[DateTuple]:
    """Return (year, month, day) from a DV or converted-MP4 file name, or None."""
    m = _RE_DV_DATE.search(name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return (y, mo, d)

    m = _RE_MP4_DATE.search(name)
    if m:
        d, month_name, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = MONTHS["nl"].index(month_name) + 1
        if 1 <= d <= 31:
            return (y, month, d)

    return None


def earliest_date_in_folder(folder: Path) -> Optional[DateTuple]:
    """The earliest date found in the video file names in *folder* (searched recursively)."""
    dates = []
    try:
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                d = parse_date_from_filename(f.stem)
                if d:
                    dates.append(d)
    except OSError:
        pass  # unreadable subfolder: use what was found so far
    return min(dates) if dates else None


# ---------------------------------------------------------------------------
# Format specs
# ---------------------------------------------------------------------------

_SPEC_TOKEN_RE = re.compile(r"YYYY|YY|MMMM|MMM|MM|M|DD|D")


def validate_date_spec(spec: str) -> str:
    """Check a date format spec; return it unchanged or raise ``ValueError``."""
    if not isinstance(spec, str) or not spec:
        raise ValueError("A date format cannot be empty (for example YYYY-MM-DD).")
    if len(spec) > 40:
        raise ValueError("The date format is too long (max 40 characters).")
    if any(c in spec for c in "{}/\\") or any(ord(c) < 32 for c in spec):
        raise ValueError("A date format cannot contain { } / \\ or control characters.")
    if not _SPEC_TOKEN_RE.search(spec) or re.search(r"[YMD]", _SPEC_TOKEN_RE.sub("", spec)):
        raise ValueError(
            f"Invalid date format {spec!r}. Use YYYY, YY, MMMM, MMM, MM, M, DD and D "
            "(for example YYYY MMMM D)."
        )
    return spec


def format_date(date: DateTuple, spec: str, locale: str = "en") -> str:
    """Render *date* with *spec* using the month names of *locale*."""
    year, month, day = date
    months = MONTHS.get(locale, MONTHS["en"])
    short = MONTHS_SHORT.get(locale, MONTHS_SHORT["en"])
    values = {
        "YYYY": f"{year:04d}",
        "YY": f"{year % 100:02d}",
        "MMMM": months[month - 1],
        "MMM": short[month - 1],
        "MM": f"{month:02d}",
        "M": str(month),
        "DD": f"{day:02d}",
        "D": str(day),
    }
    return _SPEC_TOKEN_RE.sub(lambda m: values[m.group(0)], spec)


@dataclass(frozen=True)
class DateSpecRegex:
    """A regex that recognises text written with a date spec, and reads the date back."""

    pattern: str
    month_kind: str  # "name" | "short" | "num"
    locale: str

    def to_date(self, match: "re.Match[str]") -> Optional[DateTuple]:
        year, day = int(match.group("Y")), int(match.group("D"))
        raw = match.group("M")
        if self.month_kind == "num":
            month = int(raw)
        else:
            names = MONTHS[self.locale] if self.month_kind == "name" else MONTHS_SHORT[self.locale]
            lowered = [n.lower() for n in names]
            if raw.lower() not in lowered:
                return None
            month = lowered.index(raw.lower()) + 1
        if 1 <= month <= 12 and 1 <= day <= 31:
            return (year, month, day)
        return None


def literal_regex(text: str) -> str:
    """Regex for literal pattern text: whitespace runs match any whitespace."""
    return r"\s+".join(re.escape(part) for part in re.split(r"\s+", text)) if text else ""


def date_spec_regex(spec: str, locale: str = "en") -> Optional[DateSpecRegex]:
    """Regex for text made with *spec*, or None if the spec cannot be read back.

    Reading back needs a four-digit year, a month and a day, each exactly once.
    """
    months = "|".join(re.escape(m) for m in MONTHS[locale])
    shorts = "|".join(re.escape(m) for m in MONTHS_SHORT[locale])
    pieces = {
        "YYYY": r"(?P<Y>\d{4})",
        "MMMM": rf"(?P<M>{months})",
        "MMM": rf"(?P<M>{shorts})",
        "MM": r"(?P<M>\d{2})",
        "M": r"(?P<M>\d{1,2})",
        "DD": r"(?P<D>\d{2})",
        "D": r"(?P<D>\d{1,2})",
    }
    out: list[str] = []
    seen: list[str] = []
    month_kind = "num"
    pos = 0
    for m in _SPEC_TOKEN_RE.finditer(spec):
        token = m.group(0)
        if token not in pieces:  # YY: the century is unknown
            return None
        out.append(literal_regex(spec[pos : m.start()]))
        out.append(pieces[token])
        seen.append(token[0])
        if token == "MMMM":
            month_kind = "name"
        elif token == "MMM":
            month_kind = "short"
        pos = m.end()
    out.append(literal_regex(spec[pos:]))
    if sorted(seen) != ["D", "M", "Y"]:
        return None
    return DateSpecRegex("".join(out), month_kind, locale)


# ---------------------------------------------------------------------------
# Pruning dates out of a name
# ---------------------------------------------------------------------------

def prune_date_text(text: str, locale: str = "en") -> str:
    """Remove date-like parts from *text* ('Holiday 2006' -> 'Holiday').

    Handles a leading/trailing year, '13 juli 2006', 'juli 2006', '13 juli', '13-7-06'
    and '2006-07-13' styles; month names come from *locale*. Returns 'folder' if nothing
    is left.
    """
    months = "|".join(re.escape(m) for m in MONTHS[locale])
    s = text
    s = re.sub(r"\s*[-–—]?\s*\d{4}\s*$", "", s)
    s = re.sub(r"^\s*\d{4}\s*[-–—]?\s*", "", s)
    s = re.sub(r"\s*[-–—]?\s*\d{1,2}\s+(" + months + r")\s+\d{4}\b\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[-–—]?\s*(" + months + r")\s+\d{4}\b\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[-–—]?\s*\d{1,2}\s+(" + months + r")\b\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\d{1,2}-\d{1,2}-\d{2}\b\s*", "", s)
    s = re.sub(r"\d{4}[-/.\s]\d{1,2}[-/.\s]\d{1,2}\s*", "", s)
    s = re.sub(r"\s*\d{4}[-/.\s]\d{1,2}[-/.\s]\d{1,2}\s*", "", s)
    s = s.strip(" -–—\t")
    s = re.sub(r"\s+", " ", s).strip()
    return s or "folder"
