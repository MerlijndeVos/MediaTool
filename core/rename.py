"""Rename mode: TV show / movie / subtitle organizer (plus dedup).

Renames messy media into a clean Plex/Jellyfin/Kodi friendly layout, moves
matching subtitles alongside their video, supports an undo journal, and
includes the ``dedup`` helper that strips duplicate ``(N)`` filename suffixes.
"""

import argparse
import json
import os
import re
import sys
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .logging_setup import setup_simple_logging
from .paths import copy_path, ext_path, make_dirs, move_path, path_exists

VIDEO_EXTENSIONS: Set[str] = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".ts", ".m2ts", ".mts", ".mpg", ".mpeg", ".vob", ".divx", ".ogm",
}

SUBTITLE_EXTENSIONS: Set[str] = {
    ".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".smi", ".sup",
}

# Lowercase tokens that indicate a subtitle language code (ISO 639-1 / common 639-2).
SUB_LANG_TOKENS: Set[str] = {
    "en", "eng", "english", "nl", "dut", "nld", "dutch", "fr", "fra", "fre", "french",
    "de", "ger", "deu", "german", "es", "spa", "spanish", "it", "ita", "italian",
    "pt", "por", "portuguese", "pob", "sv", "swe", "swedish", "no", "nor", "norwegian",
    "da", "dan", "danish", "fi", "fin", "finnish", "pl", "pol", "polish", "ru", "rus",
    "russian", "ja", "jpn", "japanese", "zh", "chi", "zho", "chinese", "ko", "kor",
    "korean", "ar", "ara", "arabic", "tr", "tur", "turkish", "cs", "cze", "ces", "hu",
    "hun", "el", "gre", "ell", "he", "heb", "th", "tha", "vi", "vie", "ro", "ron", "rum",
    "uk", "ukr", "hr", "hrv", "sr", "srp", "sk", "slk", "slo", "sl", "slv", "bg", "bul",
    "et", "est", "lv", "lav", "lt", "lit", "id", "ind", "ms", "msa", "hi", "hin",
}

# Lowercase tokens that flag special subtitle variants (kept on the renamed sub).
SUB_FLAG_TOKENS: Set[str] = {"forced", "sdh", "cc", "hi", "default", "foreign"}

# Small words kept lowercase in Title Case (unless first word).
SMALL_WORDS: Set[str] = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "of", "to", "in", "on",
    "at", "by", "with", "vs", "from", "as", "into", "over", "per",
}

# Junk / release-info tokens stripped from titles. Matched case-insensitively as
# whole words on a space-normalized string.
JUNK_PATTERNS: List[str] = [
    r"\b\d{3,4}p\b", r"\b4k\b", r"\b2160p\b",
    r"\bweb[-\s]?dl\b", r"\bweb[-\s]?rip\b", r"\bwebrip\b", r"\bweb\b",
    r"\bblu[-\s]?ray\b", r"\bbluray\b", r"\bbrrip\b", r"\bbdrip\b", r"\bbdremux\b",
    r"\bhdtv\b", r"\bpdtv\b", r"\bdvdrip\b", r"\bdvdscr\b", r"\bdvd\b", r"\bhdrip\b",
    r"\bhddvd\b", r"\bcam\b", r"\bts\b", r"\btc\b", r"\bremux\b",
    r"\bx264\b", r"\bx265\b", r"\bh[-\s]?264\b", r"\bh[-\s]?265\b", r"\bhevc\b",
    r"\bavc\b", r"\bxvid\b", r"\bdivx\b", r"\bvp9\b", r"\bav1\b",
    r"\baac\d?\b", r"\bac3\b", r"\beac3\b", r"\bdts[-\s]?hd\b", r"\bdts\b",
    r"\btruehd\b", r"\batmos\b", r"\bdd[p]?\s?\d[\s.]?\d\b", r"\bflac\b", r"\bmp3\b",
    r"\bopus\b", r"\b\d[\s.]1\b",
    r"\b10\s?bit\b", r"\b8\s?bit\b", r"\bhdr10\+?\b", r"\bhdr\b", r"\bsdr\b",
    r"\bdolby\s?vision\b", r"\bdovi\b",
    r"\bproper\b", r"\brepack\b", r"\binternal\b", r"\breal\b", r"\buncut\b",
    r"\bamzn\b", r"\bnf\b", r"\bdsnp\b", r"\bhmax\b", r"\batvp\b", r"\bhulu\b", r"\bmax\b",
    r"\bremastered\b", r"\bextended\b", r"\bunrated\b", r"\btheatrical\b", r"\bimax\b",
    r"\bedition\b",
    r"\b\d\s?ch\b", r"\bre[-\s.]?enc(?:ode|oded)?\b", r"\bdual\b", r"\bmulti\b",
]
JUNK_RE = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)

# The optional multi-episode group deliberately forbids whitespace before the
# second number (uses [._&+-] not [\s._&+-]) so a spaced title number like
# 'S02E09 - 4 Days Out' is NOT misread as the range 'S02E09-E04'. Real ranges
# (S01E01-E02, S01E01-02, S01E01E02, S01E01&E02, S01E01+E02) are written tightly
# without spaces. '&' and '+' join double episodes (e.g. 'S03E14&E15').
RE_SXXEXX = re.compile(
    r"\bS(\d{1,2})[\s._-]?E(\d{1,3})(?:[._&+-]*E?(\d{1,3}))?\b", re.IGNORECASE
)
RE_XFORMAT = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{1,3})(?:[._&+-]*x?(\d{1,3}))?\b", re.IGNORECASE)
RE_SEASON_WORD = re.compile(r"\bseason[\s._-]*(\d{1,2}).*?episode[\s._-]*(\d{1,3})\b", re.IGNORECASE)
RE_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
RE_BRACKETS = re.compile(r"[\[\{][^\]\}]*[\]\}]")
# A standalone 1-3 digit number at the very end (not part of a longer number/year).
# Used by --bare-episode-numbers to treat 'Show 36' as Season 1, Episode 36.
RE_TRAILING_NUM = re.compile(r"(?<!\d)(\d{1,3})\s*$")
# A standalone 1-3 digit number that splits a show name from an optional episode
# title. Used by --bare-episode-numbers to treat 'Niels Holgersson 1 De kabouter'
# as Season 1, Episode 1, title 'De kabouter' (the title group is optional so a
# trailing 'Show 36' still works). The non-greedy show keeps the first such number.
RE_BARE_EP = re.compile(r"^(?P<show>.+?)\s+(?P<ep>\d{1,3})(?!\d)(?:\s+(?P<title>.+))?$")


@dataclass
class MediaInfo:
    kind: str  # "tv" or "movie"
    title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_end: Optional[int] = None
    episode_title: Optional[str] = None


@dataclass
class RenameOp:
    src: Path
    dst: Path
    kind: str  # "video" or "subtitle"


def _collapse_acronyms(text: str) -> str:
    """Collapse dotted acronyms so they survive separator normalization.

    'I.F.T.' -> 'IFT', 'S.W.A.T.' -> 'SWAT'. Only sequences of 2+ single
    letters each followed by a dot are affected, so 'Mr.' is left untouched.
    """
    return re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group(0).replace(".", ""), text)


def _strip_release_parens(text: str) -> str:
    """Remove (...) groups that contain release/quality junk.

    e.g. '(1080p BluRay x265 Silence)' is dropped entirely (including the
    trailing scene-group word), while a wrapped year like '(2008)' is preserved.
    A group containing a year is kept (so '(2006 1080p)' keeps the year, with
    its quality token cleaned up later).
    """
    return re.sub(
        r"\(([^()]*)\)",
        lambda m: ""
        if (JUNK_RE.search(m.group(1)) and not RE_YEAR.search(m.group(1)))
        else m.group(0),
        text,
    )


def normalize_separators(text: str) -> str:
    # Drop bracketed release tags like [RARBG] or {edition}; collapse dotted
    # acronyms; drop parenthetical release info (e.g. '(1080p x265 Silence)');
    # then turn ._() into spaces (a wrapped year survives as a bare number).
    text = RE_BRACKETS.sub(" ", text)
    text = _collapse_acronyms(text)
    text = _strip_release_parens(text)
    text = re.sub(r"[._()]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -._")


def strip_trailing_group(text: str) -> str:
    """Remove a trailing scene release group like ' -GROUP' or ' - RARBG'.

    Requires whitespace before the dash so legitimate hyphenated words
    (e.g. 'Spider-Man') and titles are preserved.
    """
    return re.sub(r"\s+-\s*[A-Za-z0-9]+\s*$", "", text).strip(" -._")


def remove_junk(text: str) -> str:
    text = JUNK_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -._")


def strip_release_group(text: str) -> str:
    """Remove a trailing scene release group like '-LUMI' or '-RARBG'.

    Unlike strip_trailing_group, this also handles groups attached directly to a
    preceding token without whitespace (e.g. 'ReEnc-LUMI'). To avoid harming real
    hyphenated titles (e.g. 'Spider-Man', 'Catch-22'), it only acts when the text
    clearly looks like a release -- i.e. it contains at least one known junk tag
    (resolution, codec, source, etc.).
    """
    if JUNK_RE.search(text):
        text = re.sub(r"-[A-Za-z0-9]{2,}\s*$", "", text)
    return text


def strip_trailing_words(text: str, words: Set[str]) -> str:
    """Remove trailing whole words (case-insensitive) that appear in *words*.

    Handy for dropping a release-group word that survived junk removal, e.g.
    'Pilot Silence' -> 'Pilot' when words={'silence'}. Returns '' if every
    word was stripped.
    """
    if not words or not text:
        return text
    parts = text.split(" ")
    while parts and parts[-1].lower() in words:
        parts.pop()
    return " ".join(parts).strip(" -._")


def title_case(text: str, enabled: bool) -> str:
    text = text.strip()
    if not text or not enabled:
        return text
    words = text.split(" ")
    out: List[str] = []
    for i, w in enumerate(words):
        if not w:
            continue
        lw = w.lower()
        if len(w) > 1 and w.isupper():
            out.append(w)  # keep acronyms like SWAT, FBI
        elif i != 0 and lw in SMALL_WORDS:
            out.append(lw)
        elif w[0].isalpha():
            out.append(w[0].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


def parse_media_info(
    stem: str,
    forced_type: str,
    titlecase_enabled: bool,
    strip_words: Optional[Set[str]] = None,
    bare_numbers: bool = False,
) -> Optional[MediaInfo]:
    """Parse a video file stem into TV or movie info. Returns None if unclassifiable."""
    strip_words = strip_words or set()
    if forced_type in ("auto", "tv"):
        info = _parse_tv(stem, titlecase_enabled, strip_words, bare_numbers)
        if info is not None:
            return info
        if forced_type == "tv":
            return None

    if forced_type in ("auto", "movie"):
        # In auto mode require a year so we don't reorganize unrelated files;
        # when the user forces --type movie we accept titles without a year.
        return _parse_movie(
            stem, titlecase_enabled, strip_words, require_year=(forced_type == "auto")
        )

    return None


def _parse_tv(
    stem: str,
    titlecase_enabled: bool,
    strip_words: Optional[Set[str]] = None,
    bare_numbers: bool = False,
) -> Optional[MediaInfo]:
    strip_words = strip_words or set()
    season = episode = episode_end = None
    split_at = end_at = None

    for rx in (RE_SXXEXX, RE_XFORMAT, RE_SEASON_WORD):
        m = rx.search(stem)
        if m:
            season, episode = int(m.group(1)), int(m.group(2))
            if rx is not RE_SEASON_WORD and m.lastindex and m.lastindex >= 3 and m.group(3):
                episode_end = int(m.group(3))
            split_at, end_at = m.start(), m.end()
            break

    # A multi-episode range must strictly increase; otherwise it is spurious
    # (e.g. a stray title number wrongly captured as the range end).
    if episode_end is not None and episode is not None and episode_end <= episode:
        episode_end = None

    if season is None:
        # Optional fallback: a bare number means Season 1, that episode. Handles
        # both a trailing number ('Full Metal Alchemist Brotherhood 36' -> S01E36)
        # and a number followed by an episode title
        # ('Niels Holgersson 1 De kabouter' -> S01E01 - De kabouter).
        if not bare_numbers:
            return None
        cleaned = remove_junk(normalize_separators(stem))
        bm = RE_BARE_EP.search(cleaned)
        if not bm:
            return None
        show = title_case(strip_trailing_group(bm.group("show")), titlecase_enabled)
        if not show:
            return None
        # Re-wrap a trailing year as 'Name (2008)' to match the SxxExx path.
        show = re.sub(r"\s+((?:19|20)\d{2})$", r" (\1)", show)
        episode_title = None
        title_part = bm.group("title")
        if title_part:
            tail = strip_trailing_group(remove_junk(normalize_separators(title_part)))
            tail = strip_trailing_words(tail, strip_words)
            episode_title = title_case(tail, titlecase_enabled) if tail else None
        return MediaInfo(
            kind="tv",
            title=show,
            season=1,
            episode=int(bm.group("ep")),
            episode_title=episode_title,
        )

    show = title_case(remove_junk(normalize_separators(stem[:split_at])), titlecase_enabled)
    if not show:
        return None

    # Re-wrap a trailing year as 'Name (2008)' (Plex/Jellyfin style) instead of
    # the flattened 'Name 2008' left after separator normalization.
    show = re.sub(r"\s+((?:19|20)\d{2})$", r" (\1)", show)

    # Drop a scene group attached to the tail (e.g. 'ReEnc-LUMI') before cleaning,
    # then strip the usual junk/release tags so we don't keep a fake episode title.
    tail_raw = strip_release_group(stem[end_at:])
    tail = strip_trailing_group(remove_junk(normalize_separators(tail_raw)))
    tail = strip_trailing_words(tail, strip_words)
    episode_title = title_case(tail, titlecase_enabled) if tail else None

    return MediaInfo(
        kind="tv",
        title=show,
        season=season,
        episode=episode,
        episode_end=episode_end,
        episode_title=episode_title,
    )


def _parse_movie(
    stem: str,
    titlecase_enabled: bool,
    strip_words: Optional[Set[str]] = None,
    require_year: bool = False,
) -> Optional[MediaInfo]:
    strip_words = strip_words or set()
    cleaned = normalize_separators(stem)
    year = None
    title_part = cleaned

    # Prefer the last year that is not at the very start (a leading year is likely the title).
    chosen = None
    for mt in RE_YEAR.finditer(cleaned):
        if mt.start() == 0:
            continue
        chosen = mt
    if chosen is not None:
        year = int(chosen.group(1))
        title_part = cleaned[: chosen.start()]
        # In auto mode a real movie has its year at the end (only release junk
        # may trail it). If meaningful words follow the year, this is probably a
        # featurette/extra like 'Gallery 1988 Art Show', not a movie -> reject.
        if require_year:
            trailing = remove_junk(cleaned[chosen.end():])
            if trailing:
                return None

    if require_year and year is None:
        return None

    title = strip_trailing_group(title_case(remove_junk(normalize_separators(title_part)), titlecase_enabled))
    if not title:
        title = strip_trailing_group(title_case(remove_junk(cleaned), titlecase_enabled))
    title = strip_trailing_words(title, strip_words)
    if not title:
        return None

    return MediaInfo(kind="movie", title=title, year=year)


def split_subtitle_suffix(stem: str) -> Tuple[str, str]:
    """Split a subtitle stem into (base_stem, suffix) where suffix holds trailing
    language/flag tags. Suffix is returned without a leading dot.

    e.g. 'Show.S01E01.en.forced' -> ('Show.S01E01', 'en.forced')
    """
    parts = stem.split(".")
    suffix_parts: List[str] = []
    while len(parts) > 1:
        last = parts[-1].lower()
        if last in SUB_LANG_TOKENS or last in SUB_FLAG_TOKENS:
            suffix_parts.insert(0, parts[-1])
            parts = parts[:-1]
        else:
            break
    return ".".join(parts), ".".join(suffix_parts)


def suffix_has_language(suffix: str) -> bool:
    """True if a subtitle suffix already carries a language token (vs. only
    flag tokens like 'forced'/'sdh', or being empty)."""
    return any(tok.lower() in SUB_LANG_TOKENS for tok in suffix.split(".") if tok)


def apply_default_sub_language(suffix: str, default_lang: Optional[str]) -> str:
    """Ensure a subtitle suffix carries a language code, defaulting untagged
    subtitles to *default_lang* (e.g. 'Show.srt' -> 'Show.en.srt').

    The default language is prepended ahead of any flag tokens so a forced
    track without a language becomes e.g. 'en.forced'. Subtitles that already
    name a language are left untouched. Passing a falsy *default_lang* disables
    the behavior.
    """
    if not default_lang or suffix_has_language(suffix):
        return suffix
    return f"{default_lang}.{suffix}" if suffix else default_lang


def reserve_name(
    dest_dir: Path,
    base_stem: str,
    extension: str,
    used: Set[str],
    ignore_path: Optional[Path] = None,
) -> str:
    """Return a unique filename within dest_dir, honoring already-used/planned names.

    *ignore_path* is the source file being renamed; an existing file at that exact
    path must not count as a collision, otherwise an already-correctly-named file
    would be needlessly bumped to a ' (2)' suffix.
    """
    ignore_norm = (
        os.path.normcase(os.path.abspath(ext_path(ignore_path)))
        if ignore_path is not None
        else None
    )

    def occupied(path: Path) -> bool:
        if not path_exists(path):
            return False
        if ignore_norm is not None and (
            os.path.normcase(os.path.abspath(ext_path(path))) == ignore_norm
        ):
            return False
        return True

    candidate = f"{base_stem}{extension}"
    key = candidate.lower()
    idx = 2
    while key in used or occupied(dest_dir / candidate):
        candidate = f"{base_stem} ({idx}){extension}"
        key = candidate.lower()
        idx += 1
    used.add(key)
    return candidate


def sanitize_component(name: str) -> str:
    """Sanitize a single path component (folder or file stem) for Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "Unknown"


def _show_key(text: str) -> str:
    """Comparison key for a show/movie title that ignores any embedded year and
    punctuation, e.g. 'Breaking Bad (2008)' and 'Breaking Bad' share the key
    'breaking bad'."""
    return _norm_key(RE_YEAR.sub(" ", text))


def _folder_is_title(folder_name: str, title: str) -> bool:
    """True if *folder_name* already represents *title* (ignoring a year and
    punctuation), e.g. 'Game of Thrones (2011)' matches show 'Game of Thrones'.

    Used to avoid creating a redundant nested show/movie folder when the rename
    runs in place with the destination root already being that title's folder.
    """
    fk = _show_key(folder_name)
    return bool(fk) and fk == _show_key(title)


def existing_show_folder_name(
    video: Path, input_root: Path, title: str
) -> Optional[str]:
    """Return the name of an existing ancestor folder of *video* (at or under
    *input_root*) that represents *title* ignoring year/punctuation.

    The on-disk folder name is treated as authoritative for the show's spelling
    and year, so e.g. a file 'Breaking Bad 2008 - S01E01' living under a folder
    named 'Breaking Bad' keeps the show name 'Breaking Bad' (no year added),
    instead of being moved into a new 'Breaking Bad (2008)' folder.
    """
    key = _show_key(title)
    if not key:
        return None
    parent = video.parent
    while True:
        if _show_key(parent.name) == key:
            return parent.name
        if parent == input_root:
            break
        nxt = parent.parent
        if nxt == parent:
            break
        parent = nxt
    return None


def build_target_dir_and_stem(info: MediaInfo, dest_root: Path) -> Tuple[Path, str]:
    if info.kind == "tv":
        show = sanitize_component(info.title)
        season_folder = f"Season {info.season:02d}"
        if info.episode_end:
            ep_code = f"S{info.season:02d}E{info.episode:02d}&E{info.episode_end:02d}"
        else:
            ep_code = f"S{info.season:02d}E{info.episode:02d}"
        if info.episode_title:
            stem = f"{show} - {ep_code} - {info.episode_title}"
        else:
            stem = f"{show} - {ep_code}"
        # If dest_root is already this show's folder, don't nest another one.
        if _folder_is_title(dest_root.name, info.title):
            target_dir = dest_root / season_folder
        else:
            target_dir = dest_root / show / season_folder
        return target_dir, sanitize_component(stem)

    # movie
    if info.year:
        name = f"{info.title} ({info.year})"
    else:
        name = info.title
    name = sanitize_component(name)
    # If dest_root is already this movie's folder, place the file directly in it.
    if _folder_is_title(dest_root.name, info.title):
        target_dir = dest_root
    else:
        target_dir = dest_root / name
    return target_dir, name


def scan_directory_group(
    files: List[Path],
) -> Tuple[List[Path], List[Path]]:
    """Split a directory's files into (videos, subtitles)."""
    videos = [f for f in files if f.suffix.lower() in VIDEO_EXTENSIONS]
    subs = [f for f in files if f.suffix.lower() in SUBTITLE_EXTENSIONS]
    return videos, subs


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def match_subtitle_to_video(sub: Path, videos: List[Path]) -> Optional[Path]:
    """Find the video a subtitle belongs to within the same directory."""
    if not videos:
        return None

    base, _suffix = split_subtitle_suffix(sub.stem)
    base_key = _norm_key(base)

    # 1) Exact normalized stem match.
    for v in videos:
        if _norm_key(v.stem) == base_key:
            return v

    # 2) Single video in the folder -> assume it owns the subtitle.
    if len(videos) == 1:
        return videos[0]

    # 3) Signature match via the same parser (TV: season+episode, movie: year).
    sub_info = parse_media_info(base, "auto", True)
    if sub_info is not None:
        for v in videos:
            v_info = parse_media_info(v.stem, "auto", True)
            if v_info is None or v_info.kind != sub_info.kind:
                continue
            if sub_info.kind == "tv" and (v_info.season, v_info.episode) == (sub_info.season, sub_info.episode):
                return v
            if sub_info.kind == "movie" and v_info.year == sub_info.year and _norm_key(v_info.title) == _norm_key(sub_info.title):
                return v

    # 4) Longest normalized-prefix match in either direction.
    best: Optional[Path] = None
    best_len = 0
    for v in videos:
        vk = _norm_key(v.stem)
        if (base_key.startswith(vk) or vk.startswith(base_key)) and len(vk) > best_len:
            best, best_len = v, len(vk)
    return best


def plan_rename(
    input_root: Path,
    dest_root: Path,
    forced_type: str,
    titlecase_enabled: bool,
    logger: logging.Logger,
    strip_words: Optional[Set[str]] = None,
    bare_numbers: bool = False,
    default_sub_lang: Optional[str] = "en",
) -> Tuple[List[RenameOp], List[Tuple[Path, str]]]:
    """Build the list of rename operations and a list of (path, reason) skips."""
    ops: List[RenameOp] = []
    skipped: List[Tuple[Path, str]] = []
    strip_words = strip_words or set()

    # Track reserved names per destination directory to avoid collisions.
    used_by_dir: Dict[str, Set[str]] = {}

    # Group source files by their containing directory.
    files_by_dir: Dict[Path, List[Path]] = {}
    for p in input_root.rglob("*"):
        if p.is_file():
            files_by_dir.setdefault(p.parent, []).append(p)

    for directory in sorted(files_by_dir, key=lambda d: str(d).lower()):
        videos, subs = scan_directory_group(files_by_dir[directory])

        # Map each video to its planned target so subtitles can follow.
        video_targets: Dict[Path, Tuple[Path, str]] = {}

        for video in sorted(videos, key=lambda v: v.name.lower()):
            info = parse_media_info(
                video.stem, forced_type, titlecase_enabled, strip_words, bare_numbers
            )
            if info is None:
                skipped.append((video, "could not classify (no SxxExx / year)"))
                continue

            # Respect an existing show folder: if the file already lives under a
            # folder that represents this show (ignoring year/punctuation), keep
            # that folder's exact name as the show title so we neither add nor
            # drop a year against the on-disk layout.
            if info.kind == "tv":
                existing = existing_show_folder_name(video, input_root, info.title)
                if existing:
                    info.title = existing

            target_dir, base_stem = build_target_dir_and_stem(info, dest_root)
            used = used_by_dir.setdefault(str(target_dir).lower(), set())
            ext = video.suffix.lower()
            new_name = reserve_name(target_dir, base_stem, ext, used, ignore_path=video)
            dst = target_dir / new_name

            video_targets[video] = (target_dir, Path(new_name).stem)

            if dst == video:
                skipped.append((video, "already correctly named"))
                continue
            ops.append(RenameOp(src=video, dst=dst, kind="video"))

        # Attach subtitles to their videos.
        for sub in sorted(subs, key=lambda s: s.name.lower()):
            owner = match_subtitle_to_video(sub, videos)
            if owner is None or owner not in video_targets:
                skipped.append((sub, "no matching video in folder"))
                continue
            target_dir, video_stem = video_targets[owner]
            _base, suffix = split_subtitle_suffix(sub.stem)
            suffix = apply_default_sub_language(suffix, default_sub_lang)
            used = used_by_dir.setdefault(str(target_dir).lower(), set())
            ext = sub.suffix.lower()
            sub_stem = f"{video_stem}.{suffix}" if suffix else video_stem
            # reserve_name appends " (2)" before extension if needed; build full stem first.
            new_name = reserve_name(target_dir, sub_stem, ext, used, ignore_path=sub)
            dst = target_dir / new_name
            if dst == sub:
                skipped.append((sub, "already correctly named"))
                continue
            ops.append(RenameOp(src=sub, dst=dst, kind="subtitle"))

    return ops, skipped


def execute_rename(
    ops: List[RenameOp],
    use_copy: bool,
    logger: logging.Logger,
) -> Tuple[int, int, List[RenameOp]]:
    """Perform the planned operations.

    Returns (succeeded, failed, done) where *done* is the list of operations
    that completed, so the caller can record them in an undo journal.
    """
    succeeded = 0
    failed = 0
    done: List[RenameOp] = []
    verb = "Copying" if use_copy else "Moving"
    for op in ops:
        try:
            make_dirs(op.dst.parent)
            logger.info("%s [%s] '%s' -> '%s'", verb, op.kind, op.src, op.dst)
            if use_copy:
                copy_path(op.src, op.dst)
            else:
                move_path(op.src, op.dst)
            succeeded += 1
            done.append(op)
        except Exception as exc:
            logger.error("FAILED to process '%s' -> '%s': %s", op.src, op.dst, exc)
            failed += 1
    return succeeded, failed, done


# Name of the journal file written next to the destination on every --apply
# run, recording what moved where so a subsequent --undo can reverse it.
UNDO_JOURNAL_NAME = "rename_undo.json"


def undo_journal_path(dest_root: Path) -> Path:
    return dest_root / UNDO_JOURNAL_NAME


def write_undo_journal(
    dest_root: Path,
    done: List[RenameOp],
    use_copy: bool,
    logger: logging.Logger,
) -> None:
    """Record the completed operations so they can be reversed later.

    Overwrites any previous journal so it always describes the most recent
    apply run ("undo the last rename").
    """
    if not done:
        return
    path = undo_journal_path(dest_root)
    data = {
        "version": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": "copy" if use_copy else "move",
        "operations": [
            {"src": str(op.src), "dst": str(op.dst), "kind": op.kind} for op in done
        ],
    }
    try:
        make_dirs(path.parent)
        with open(ext_path(path), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        logger.info("Wrote undo journal (%d op(s)): %s", len(done), path)
    except Exception as exc:  # journal is best-effort, never fail the run over it
        logger.warning("Could not write undo journal '%s': %s", path, exc)


def execute_undo(
    journal: dict,
    apply: bool,
    logger: logging.Logger,
) -> Tuple[int, int, int]:
    """Reverse the operations recorded in *journal*.

    A move is undone by moving the file back to its original path; a copy is
    undone by deleting the created copy (the original is left untouched).
    Returns (restored, failed, skipped).
    """
    use_copy = journal.get("action") == "copy"
    ops = journal.get("operations", [])
    restored = failed = skipped = 0
    # Reverse the original order so nested folders unwind cleanly.
    for entry in reversed(ops):
        src = Path(entry["src"])  # original location the file came from
        dst = Path(entry["dst"])  # where the file lives now

        if use_copy:
            # Undo a copy = remove the copy we created; never touch the original.
            if not path_exists(dst):
                logger.warning("Undo skip: copy not found at '%s'.", dst)
                skipped += 1
                continue
            if apply:
                try:
                    os.remove(ext_path(dst))
                    logger.info("Removed copy '%s'", dst)
                    restored += 1
                except Exception as exc:
                    logger.error("FAILED to remove copy '%s': %s", dst, exc)
                    failed += 1
            else:
                logger.info("[DRY-RUN] would remove copy '%s'", dst)
                restored += 1
            continue

        # Undo a move = put the file back where it came from.
        if not path_exists(dst):
            logger.warning("Undo skip: file not found at '%s' (moved/renamed since?).", dst)
            skipped += 1
            continue
        if path_exists(src):
            logger.warning("Undo skip: original path already exists '%s'.", src)
            skipped += 1
            continue
        if apply:
            try:
                make_dirs(src.parent)
                move_path(dst, src)
                logger.info("Restored '%s' -> '%s'", dst, src)
                restored += 1
            except Exception as exc:
                logger.error("FAILED to restore '%s' -> '%s': %s", dst, src, exc)
                failed += 1
        else:
            logger.info("[DRY-RUN] would restore '%s' -> '%s'", dst, src)
            restored += 1
    return restored, failed, skipped


def run_rename_undo(args: argparse.Namespace, logger: logging.Logger) -> None:
    """Reverse the most recent --apply rename run using its undo journal."""
    dest_root: Path = args.output if args.output is not None else args.input
    apply = bool(args.apply)
    path = undo_journal_path(dest_root)

    logger.info("Undo rename (%s).", "APPLY" if apply else "DRY-RUN")
    if not path_exists(path):
        logger.error(
            "No undo journal found at '%s'. Nothing to undo "
            "(only --apply runs create one, and an undo removes it).",
            path,
        )
        return
    try:
        with open(ext_path(path), "r", encoding="utf-8") as fh:
            journal = json.load(fh)
    except Exception as exc:
        logger.error("Could not read undo journal '%s': %s", path, exc)
        return

    ops = journal.get("operations", [])
    action = journal.get("action", "move")
    logger.info("Journal: %s (created %s)", path, journal.get("created", "?"))
    logger.info("Reversing %d %s operation(s) from the last rename.", len(ops), action)

    restored, failed, skipped = execute_undo(journal, apply, logger)
    logger.info("Undo result: restored=%d, failed=%d, skipped=%d.", restored, failed, skipped)

    if not apply:
        logger.info("Dry-run complete. Re-run with --undo --apply to perform the undo.")
        return

    # Drop the journal once the undo fully succeeded, so it cannot run twice.
    if failed == 0 and skipped == 0:
        try:
            os.remove(ext_path(path))
            logger.info("Removed undo journal '%s'.", path)
        except Exception as exc:
            logger.warning("Could not remove undo journal '%s': %s", path, exc)
    else:
        logger.info("Undo journal kept at '%s' (some operations did not reverse).", path)


def prune_empty_dirs(root: Path, dry_run: bool, logger: logging.Logger) -> None:
    """Remove directories left empty under root (bottom-up). Never removes root itself."""
    for current, dirs, files in os.walk(ext_path(root), topdown=False):
        # Skip the root directory itself.
        if os.path.normcase(current) == os.path.normcase(ext_path(root)):
            continue
        try:
            if not os.listdir(current):
                if dry_run:
                    logger.info("[DRY-RUN] Would remove empty folder: %s", current)
                else:
                    os.rmdir(current)
                    logger.info("Removed empty folder: %s", current)
        except OSError as exc:
            logger.warning("Could not remove '%s': %s", current, exc)


def run_rename(args: argparse.Namespace) -> None:
    input_root: Path = args.input
    dest_root: Path = args.output if args.output is not None else args.input
    apply = bool(args.apply)
    use_copy = bool(args.copy)
    forced_type: str = args.type
    titlecase_enabled = not args.no_titlecase
    # Accept comma- and/or space-separated words; compare case-insensitively.
    raw_strip = getattr(args, "strip_words", None) or []
    strip_words: Set[str] = {
        w.strip().lower()
        for chunk in raw_strip
        for w in chunk.split(",")
        if w.strip()
    }
    bare_numbers = bool(getattr(args, "bare_episode_numbers", False))
    raw_sub_lang = getattr(args, "default_sub_lang", "en")
    # An empty string disables defaulting; otherwise normalize to a lowercase code.
    default_sub_lang: Optional[str] = raw_sub_lang.strip().lower() or None

    if not input_root.is_dir():
        print(
            f"Input root '{input_root}' does not exist or is not a directory. "
            f"(If this is a network drive, make sure it is connected/mapped.)",
            file=sys.stderr,
        )
        sys.exit(1)

    # Put the log next to the destination so it is easy to find; best-effort.
    log_path = (dest_root / "rename.log") if apply else None
    logger = setup_simple_logging("video_rename", log_path)

    if getattr(args, "undo", False):
        run_rename_undo(args, logger)
        return

    mode = "APPLY" if apply else "DRY-RUN"
    action = "copy" if use_copy else "move"
    logger.info("Rename mode (%s).", mode)
    logger.info("Input root : %s", input_root)
    logger.info("Destination: %s%s", dest_root, " (in place)" if dest_root == input_root else "")
    logger.info("Type=%s, action=%s, title_case=%s, prune_empty_dirs=%s",
                forced_type, action, titlecase_enabled, args.prune_empty_dirs)
    logger.info("Strip words=%s, bare_episode_numbers=%s",
                sorted(strip_words) if strip_words else "(none)", bare_numbers)
    logger.info("Default subtitle language (untagged subs)=%s",
                default_sub_lang or "(disabled)")

    if use_copy and dest_root == input_root:
        logger.warning(
            "--copy with no --output will duplicate files into a new layout under the same root."
        )

    ops, skipped = plan_rename(
        input_root, dest_root, forced_type, titlecase_enabled, logger,
        strip_words=strip_words, bare_numbers=bare_numbers,
        default_sub_lang=default_sub_lang,
    )

    videos = sum(1 for o in ops if o.kind == "video")
    subtitles = sum(1 for o in ops if o.kind == "subtitle")
    logger.info("Planned operations: %d (videos=%d, subtitles=%d).", len(ops), videos, subtitles)

    if not apply:
        for op in ops:
            logger.info("[DRY-RUN] %s '%s' -> '%s'", op.kind, op.src, op.dst)
    else:
        succeeded, failed, done = execute_rename(ops, use_copy, logger)
        logger.info("Executed: succeeded=%d, failed=%d.", succeeded, failed)
        write_undo_journal(dest_root, done, use_copy, logger)

    if skipped:
        logger.info("Skipped %d file(s):", len(skipped))
        for path, reason in skipped:
            logger.info("  SKIP (%s): %s", reason, path)

    # Prune empty folders only when we actually moved files (copying leaves originals).
    if args.prune_empty_dirs and not use_copy:
        prune_empty_dirs(input_root, dry_run=not apply, logger=logger)
    elif args.prune_empty_dirs and use_copy:
        logger.info("--prune-empty-dirs ignored because --copy keeps originals in place.")

    if not apply:
        logger.info("Dry-run complete. Re-run with --apply to perform these changes.")
    logger.info("Done.")


# =====================================================================
# Dedup mode: strip duplicate "(N)" suffixes from filenames
# =====================================================================

# Matches a stem ending in a duplicate counter like "name (2)".
# Limited to 1-3 digits so it never strips a 4-digit year, e.g. "Movie (2020)".
RE_DUP_SUFFIX = re.compile(r"^(?P<base>.+?) \((?P<n>\d{1,3})\)$")


def dedup_target_for(path: Path) -> Optional[Path]:
    """Return the de-duplicated target path for *path*, or None if it has no
    ``(N)`` counter.

    Handles the counter whether it sits at the very end of the name
    (``name (2).srt``) or in front of subtitle language/flag tags
    (``name (2).en.srt`` -> ``name.en.srt``).
    """
    ext = path.suffix
    stem = path.stem

    # Counter right before the final extension, e.g. "name (2).srt" / "name.en (2).srt".
    m = RE_DUP_SUFFIX.match(stem)
    if m:
        return path.with_name(m.group("base") + ext)

    # For subtitles the counter may precede the language/flag tags, e.g.
    # "name (2).en.srt". Peel those tags off and look again.
    if ext.lower() in SUBTITLE_EXTENSIONS:
        base, suffix = split_subtitle_suffix(stem)
        m = RE_DUP_SUFFIX.match(base)
        if m:
            new_stem = f"{m.group('base')}.{suffix}" if suffix else m.group("base")
            return path.with_name(new_stem + ext)

    return None


def run_dedup(args: argparse.Namespace) -> None:
    input_root: Path = args.input
    apply = bool(args.apply)

    if not input_root.is_dir():
        print(
            f"Input '{input_root}' does not exist or is not a directory. "
            f"(If this is a network drive, make sure it is connected/mapped.)",
            file=sys.stderr,
        )
        sys.exit(1)

    log_path = (input_root / "dedup.log") if apply else None
    logger = setup_simple_logging("video_dedup", log_path)

    logger.info("Dedup mode (%s).", "APPLY" if apply else "DRY-RUN")
    logger.info("Input root: %s", input_root)

    # Collect every file, sorted, so behavior is deterministic and so a lower
    # counter is handled before a higher one mapping to the same base name.
    files: List[Path] = []
    for current, _dirs, names in os.walk(ext_path(input_root)):
        for name in names:
            files.append(Path(current) / name)
    files.sort(key=lambda p: str(p).lower())

    renamed = removed = skipped = 0
    # Base targets we've already claimed in this run (normalized for case-insensitive FS).
    planned: Set[str] = set()

    def norm(p: Path) -> str:
        return os.path.normcase(str(p))

    def size_of(p: Path) -> Optional[int]:
        try:
            return os.path.getsize(ext_path(p))
        except OSError:
            return None

    for f in files:
        target = dedup_target_for(f)
        if target is None:
            continue
        tnorm = norm(target)
        on_disk = path_exists(target)

        if not on_disk and tnorm not in planned:
            # Un-suffixed name is free: just strip the counter.
            if apply:
                try:
                    move_path(f, target)
                except Exception as exc:
                    logger.error("FAILED to rename '%s' -> '%s': %s", f, target, exc)
                    skipped += 1
                    continue
                logger.info("Renamed '%s' -> '%s'", f, target)
            else:
                logger.info("[DRY-RUN] would rename '%s' -> '%s'", f, target)
            planned.add(tnorm)
            renamed += 1
            continue

        # The un-suffixed name already exists (on disk or claimed this run).
        # Only delete the suffixed copy when it is clearly the same file (size match).
        dup_size = size_of(f)
        orig_size = size_of(target) if on_disk else None
        if on_disk and dup_size is not None and dup_size == orig_size:
            if apply:
                try:
                    os.remove(ext_path(f))
                except OSError as exc:
                    logger.error("FAILED to remove duplicate '%s': %s", f, exc)
                    skipped += 1
                    continue
                logger.info("Removed duplicate '%s' (identical to '%s')", f, target)
            else:
                logger.info("[DRY-RUN] would remove duplicate '%s' (identical to '%s')", f, target)
            removed += 1
        elif not on_disk and tnorm in planned:
            # An earlier copy this run already claimed the base name.
            if apply:
                try:
                    os.remove(ext_path(f))
                except OSError as exc:
                    logger.error("FAILED to remove extra duplicate '%s': %s", f, exc)
                    skipped += 1
                    continue
                logger.info("Removed extra duplicate '%s' (another copy maps to '%s')", f, target)
            else:
                logger.info("[DRY-RUN] would remove extra duplicate '%s' (another copy maps to '%s')", f, target)
            removed += 1
        else:
            logger.warning(
                "SKIP '%s': '%s' already exists with different content; leaving both in place.",
                f, target,
            )
            skipped += 1

    logger.info("Dedup summary: renamed=%d, removed_duplicates=%d, skipped=%d.",
                renamed, removed, skipped)
    if not apply and (renamed or removed):
        logger.info("Dry-run complete. Re-run with --apply to perform these changes.")
    logger.info("Done.")
