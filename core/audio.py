"""Set the default audio language in MKV files (MKVToolNix).

Uses mkvmerge -J to read track layout and mkvpropedit to rewrite header flags
in place (no re-encode/remux).
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .logging_setup import setup_simple_logging
from .paths import ext_path, path_exists
from .tools import ensure_mkvtoolnix

# Map common language inputs to ISO 639-2/B codes mkvmerge reports.
LANG_ALIASES: Dict[str, str] = {
    "en": "eng", "eng": "eng", "english": "eng",
    "nl": "dut", "dut": "dut", "nld": "dut", "dutch": "dut", "flemish": "dut",
    "fr": "fre", "fre": "fre", "fra": "fre", "french": "fre",
    "de": "ger", "ger": "ger", "deu": "ger", "german": "ger",
    "es": "spa", "spa": "spa", "spanish": "spa",
    "it": "ita", "ita": "ita", "italian": "ita",
    "pt": "por", "por": "por", "portuguese": "por",
    "ja": "jpn", "jpn": "jpn", "japanese": "jpn",
    "zh": "chi", "chi": "chi", "zho": "chi", "chinese": "chi", "mandarin": "chi",
    "ko": "kor", "kor": "kor", "korean": "kor",
    "ru": "rus", "rus": "rus", "russian": "rus",
    "sv": "swe", "swe": "swe", "swedish": "swe",
    "no": "nor", "nor": "nor", "norwegian": "nor",
    "da": "dan", "dan": "dan", "danish": "dan",
    "fi": "fin", "fin": "fin", "finnish": "fin",
    "pl": "pol", "pol": "pol", "polish": "pol",
    "ar": "ara", "ara": "ara", "arabic": "ara",
    "tr": "tur", "tur": "tur", "turkish": "tur",
    "cs": "cze", "cze": "cze", "ces": "cze", "czech": "cze",
    "hu": "hun", "hun": "hun", "hungarian": "hun",
    "el": "gre", "gre": "gre", "ell": "gre", "greek": "gre",
    "he": "heb", "heb": "heb", "hebrew": "heb",
    "th": "tha", "tha": "tha", "thai": "tha",
    "vi": "vie", "vie": "vie", "vietnamese": "vie",
    "ro": "rum", "rum": "rum", "ron": "rum", "romanian": "rum",
    "uk": "ukr", "ukr": "ukr", "ukrainian": "ukr",
    "hr": "hrv", "hrv": "hrv", "croatian": "hrv",
    "sr": "srp", "srp": "srp", "serbian": "srp",
    "sk": "slo", "slo": "slo", "slk": "slo", "slovak": "slo",
    "sl": "slv", "slv": "slv", "slovenian": "slv",
    "bg": "bul", "bul": "bul", "bulgarian": "bul",
    "id": "ind", "ind": "ind", "indonesian": "ind",
    "ms": "may", "may": "may", "msa": "may", "malay": "may",
    "hi": "hin", "hin": "hin", "hindi": "hin",
}


@dataclass
class AudioTrack:
    """An audio track as reported by mkvmerge, with its 1-based audio position."""
    audio_index: int
    language: str
    is_default: bool
    codec: str
    name: str


def normalize_lang(value: Optional[str]) -> str:
    """Normalize a language string to a canonical ISO 639-2/B code for comparison."""
    if not value:
        return "und"
    v = value.strip().lower()
    if not v:
        return "und"
    primary = v.split("-")[0]
    return LANG_ALIASES.get(v) or LANG_ALIASES.get(primary) or primary


def probe_mkv_audio_tracks(mkvmerge_bin: str, mkv: Path, logger: logging.Logger) -> Optional[List[AudioTrack]]:
    """Return ordered audio tracks for an MKV, or None if it could not be probed."""
    try:
        result = subprocess.run(
            [mkvmerge_bin, "-J", ext_path(mkv)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except Exception as exc:
        logger.warning("Failed to run mkvmerge on '%s': %s", mkv, exc)
        return None

    if result.returncode not in (0, 1):
        logger.warning("mkvmerge could not read '%s' (exit %s).", mkv, result.returncode)
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("mkvmerge returned no parseable JSON for '%s'.", mkv)
        return None

    audio_tracks: List[AudioTrack] = []
    audio_index = 0
    for track in data.get("tracks", []):
        if track.get("type") != "audio":
            continue
        audio_index += 1
        props = track.get("properties", {}) or {}
        lang = props.get("language_ietf") or props.get("language") or "und"
        audio_tracks.append(
            AudioTrack(
                audio_index=audio_index,
                language=str(lang),
                is_default=bool(props.get("default_track", False)),
                codec=str(track.get("codec", "")),
                name=str(props.get("track_name", "") or ""),
            )
        )
    return audio_tracks


def plan_audio_edits(
    tracks: List[AudioTrack],
    target_lang: str,
    set_language: bool,
) -> Tuple[Optional[int], List[List[str]], bool]:
    """Build mkvpropedit --edit argument groups for one file."""
    target = normalize_lang(target_lang)
    chosen: Optional[AudioTrack] = next(
        (t for t in tracks if normalize_lang(t.language) == target), None
    )
    if chosen is None:
        return None, [], False

    needs_change = False
    edits: List[List[str]] = []
    for t in tracks:
        want_default = (t.audio_index == chosen.audio_index)
        group = ["--edit", f"track:a{t.audio_index}"]
        track_changed = False
        if t.is_default != want_default:
            group += ["--set", f"flag-default={1 if want_default else 0}"]
            track_changed = True
        if want_default and set_language and normalize_lang(t.language) != target:
            group += ["--set", f"language={target}"]
            track_changed = True
        if track_changed:
            edits.append(group)
            needs_change = True

    already_correct = not needs_change
    return chosen.audio_index, edits, already_correct


def apply_mkv_edits(
    mkvpropedit_bin: str,
    mkv: Path,
    edits: List[List[str]],
    logger: logging.Logger,
) -> bool:
    cmd = [mkvpropedit_bin, ext_path(mkv)]
    for group in edits:
        cmd += group
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except Exception as exc:
        logger.error("mkvpropedit failed to launch for '%s': %s", mkv, exc)
        return False

    if result.returncode != 0:
        logger.error(
            "mkvpropedit error on '%s' (exit %s): %s",
            mkv, result.returncode, result.stdout.strip(),
        )
        return False
    return True


def iter_mkv_files(input_path: Path, recursive: bool) -> List[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".mkv" else []
    found: List[Path] = []
    for current, dirs, files in os.walk(ext_path(input_path)):
        for name in files:
            if name.lower().endswith(".mkv"):
                found.append(Path(current) / name)
        if not recursive:
            dirs[:] = []
    found.sort()
    return found


def run_audio(args: argparse.Namespace) -> None:
    input_path: Path = args.input
    apply = bool(args.apply)
    recursive = not args.no_recursive
    set_language = bool(args.set_language)
    target_lang = normalize_lang(args.lang)

    if not path_exists(input_path):
        print(
            f"Input '{input_path}' does not exist. "
            f"(If this is a network drive, make sure it is connected/mapped.)",
            file=sys.stderr,
        )
        sys.exit(1)

    log_path = (input_path if input_path.is_dir() else input_path.parent) / "audio_default.log"
    logger = setup_simple_logging("video_audio", log_path if apply else None)

    mode = "APPLY" if apply else "DRY-RUN"
    logger.info("Audio mode (%s).", mode)
    logger.info("Input        : %s", input_path)
    logger.info("Target language: %s (normalized: %s)", args.lang, target_lang)
    logger.info("Set language tag on chosen track: %s | recursive: %s", set_language, recursive)

    mkvmerge_bin, mkvpropedit_bin = ensure_mkvtoolnix(logger)

    mkvs = iter_mkv_files(input_path, recursive)
    if not mkvs:
        logger.info("No .mkv files found under '%s'. Nothing to do.", input_path)
        return
    logger.info("Found %d MKV file(s).", len(mkvs))

    changed = 0
    already = 0
    no_match = 0
    failed = 0
    no_audio = 0

    for mkv in mkvs:
        tracks = probe_mkv_audio_tracks(mkvmerge_bin, mkv, logger)
        if tracks is None:
            failed += 1
            continue
        if not tracks:
            logger.info("SKIP (no audio tracks): %s", mkv)
            no_audio += 1
            continue

        chosen_idx, edits, already_correct = plan_audio_edits(tracks, target_lang, set_language)

        if chosen_idx is None:
            langs = ", ".join(f"a{t.audio_index}:{normalize_lang(t.language)}" for t in tracks)
            logger.warning("NO MATCH for '%s' in '%s' (audio tracks: %s)", target_lang, mkv, langs)
            no_match += 1
            continue

        if already_correct:
            logger.info("OK (already default a%d=%s): %s", chosen_idx, target_lang, mkv)
            already += 1
            continue

        if not apply:
            change_desc = " ".join(" ".join(g) for g in edits)
            logger.info(
                "[DRY-RUN] would set a%d (%s) default in '%s'  [%s]",
                chosen_idx, target_lang, mkv, change_desc,
            )
            changed += 1
            continue

        if apply_mkv_edits(mkvpropedit_bin, mkv, edits, logger):
            logger.info("UPDATED (a%d=%s default): %s", chosen_idx, target_lang, mkv)
            changed += 1
        else:
            failed += 1

    logger.info(
        "Summary: total=%d, %s=%d, already_correct=%d, no_match=%d, no_audio=%d, errors=%d",
        len(mkvs),
        "would_change" if not apply else "updated",
        changed, already, no_match, no_audio, failed,
    )
    if not apply and changed:
        logger.info("Dry-run complete. Re-run with --apply to perform these changes.")
    logger.info("Done.")
