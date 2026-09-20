"""AI-assisted creation of rename format profiles.

The model only *writes a profile* (rules, patterns, a short name) from one or
more ``before -> after`` examples. It never sees the library and never renames
anything: the result is validated like any hand-made profile, then verified by
running it on the user's own examples.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .openai_client import new_client, openai_model
from .rename import SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS, preview_media_name
from .rename_generic import preview_generic_name
from .rename_profiles import (
    BRACKET_KINDS,
    CASE_MODES,
    PATTERN_TOKENS,
    Profile,
    ProfileError,
    profile_from_dict,
)

MODES = ("media", "generic")
MAX_EXAMPLES = 5
MAX_EXAMPLE_LEN = 300
MAX_ATTEMPTS = 2


def _system_prompt(mode: str) -> str:
    if mode == "media":
        context = (
            "The tool renames TV episodes and movies. It already finds the show/movie title, "
            "season, episode and year by itself and always turns dots/underscores into spaces "
            "and removes [bracket] tags. Your profile only decides how the *title text* is "
            "cleaned and what the final file name looks like.\n"
            "Patterns: \"tv\" (episodes, tokens "
            + ", ".join("{" + t + "}" for t in PATTERN_TOKENS["tv"])
            + ") and \"movie\" (tokens "
            + ", ".join("{" + t + "}" for t in PATTERN_TOKENS["movie"])
            + "). {code} is like S01E02 (S01E02&E03 for double episodes). Defaults: tv "
            "\"{show} - {code} - {title}\", movie \"{title} ({year})\". Only set a pattern when the "
            "example needs a different one. {season:02} zero-pads to 2 digits; :upper, :lower "
            "and :title change case. A token with no value is dropped together with the "
            "separators around it.\n"
            "\"strip_release_junk\": true removes tags like 1080p/WEB-DL/x265 (default); false keeps them.\n"
            "Leave folder layout alone; you only shape file names."
        )
    else:
        context = (
            "The tool renames folders and/or files by cleaning each name (without extension). "
            "Pattern key: \"generic\" with tokens "
            + ", ".join("{" + t + "}" for t in PATTERN_TOKENS["generic"])
            + ". {name} is the cleaned original name, {parent} the cleaned name of the containing "
            "folder, {n} a 1-based counter among siblings ({n:02} zero-pads). Default pattern "
            "\"{name}\": only set one when the example adds or reorders parts. Set "
            "\"strip_release_junk\" to false."
        )
    return (
        "You design rename profiles for a file-renaming tool. Reply with ONE JSON object only:\n"
        '{"name": "<short profile name, max 30 chars>", "rules": [...], '
        '"patterns": {...}, "strip_release_junk": true|false}\n\n'
        f"{context}\n\n"
        "Rules run in order over each name. Allowed rule objects:\n"
        '- {"type": "replace", "find": "<text>", "with": "<text>"}  (literal, every occurrence)\n'
        '- {"type": "remove_words", "words": ["a", "b"]}  (whole words, case-insensitive)\n'
        f'- {{"type": "remove_brackets", "brackets": [{", ".join(chr(34) + b + chr(34) for b in BRACKET_KINDS)}]}}'
        "  (removes the bracket AND its content; pick only the kinds needed)\n"
        f'- {{"type": "case", "mode": one of {", ".join(CASE_MODES)}}}\n'
        '- {"type": "regex_replace", "pattern": "<python regex>", "with": "<text>"}  '
        "(last resort, only when nothing simpler works)\n\n"
        "Prefer the simplest rules that reproduce ALL examples. Whitespace is collapsed and "
        "leading/trailing spaces, dashes, dots and underscores are trimmed automatically. "
        "Do not invent tokens. Patterns must not contain / or \\. Give a short descriptive "
        "name (e.g. \"Sample pack tidy\")."
    )


def _strip_known_ext(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in VIDEO_EXTENSIONS or suffix in SUBTITLE_EXTENSIONS:
        return name[: -len(suffix)]
    return name


def _strip_shared_suffix(before: str, after: str) -> tuple[str, str]:
    """Drop a file extension present on both sides (folders mode examples)."""
    sb, sa = Path(before).suffix, Path(after).suffix
    if sb and sb.lower() == sa.lower() and len(sb) <= 6 and " " not in sb:
        return before[: -len(sb)], after[: -len(sa)]
    return before, after


def _apply(profile: Profile, mode: str, before: str) -> Optional[str]:
    if mode == "media":
        out = preview_media_name(profile, before)
        return None if out is None else _strip_known_ext(out)
    return preview_generic_name(profile, before)


def verify_profile(profile: Profile, mode: str, examples: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Run *profile* over each example and report whether it gives the expected name."""
    results: List[Dict[str, Any]] = []
    for ex in examples:
        before, after = ex["before"], ex["after"]
        if mode == "media":
            before_c, after_c = _strip_known_ext(before), _strip_known_ext(after)
        else:
            before_c, after_c = _strip_shared_suffix(before, after)
        actual = _apply(profile, mode, before_c)
        results.append(
            {
                "before": before,
                "expected": after,
                "actual": actual,
                "ok": actual == after_c,
            }
        )
    return results


def _clean_examples(examples: Any) -> List[Dict[str, str]]:
    if not isinstance(examples, list) or not examples:
        raise ProfileError("Give at least one example (before and after).")
    if len(examples) > MAX_EXAMPLES:
        raise ProfileError(f"Use at most {MAX_EXAMPLES} examples.")
    cleaned: List[Dict[str, str]] = []
    for ex in examples:
        before = str((ex or {}).get("before", "")).strip()
        after = str((ex or {}).get("after", "")).strip()
        if not before or not after:
            raise ProfileError("Each example needs both a 'before' and an 'after' name.")
        if len(before) > MAX_EXAMPLE_LEN or len(after) > MAX_EXAMPLE_LEN:
            raise ProfileError("Example names are too long.")
        cleaned.append({"before": before, "after": after})
    return cleaned


def generate_profile(
    examples: Any,
    mode: str,
    *,
    model: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Ask the model for a profile that turns each *before* into its *after*.

    Returns ``{"profile", "verification", "all_ok", "attempts", "model"}``. The
    profile is a validated draft (not saved). If the first draft misses an
    example, the mismatch is fed back once for a correction.
    """
    if mode not in MODES:
        raise ProfileError("mode must be 'media' or 'generic'.")
    examples = _clean_examples(examples)
    model_name = openai_model(model)
    client = client or new_client()

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": _system_prompt(mode)},
        {"role": "user", "content": "Examples (before -> after):\n" + json.dumps(examples, ensure_ascii=False, indent=1)},
    ]

    best: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        messages.append({"role": "assistant", "content": raw})

        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data.pop("id", None)  # never trust an id from the model
            profile = profile_from_dict(data)
        except (json.JSONDecodeError, ProfileError) as exc:
            last_error = str(exc)
            messages.append(
                {"role": "user", "content": f"That profile was invalid: {exc}. Reply with corrected JSON only."}
            )
            continue

        verification = verify_profile(profile, mode, examples)
        all_ok = all(v["ok"] for v in verification)
        best = {
            "profile": profile.to_dict(),
            "verification": verification,
            "all_ok": all_ok,
            "attempts": attempt,
            "model": model_name,
        }
        if all_ok:
            return best

        misses = "; ".join(
            f"{v['before']!r} gave {v['actual']!r} but should give {v['expected']!r}"
            for v in verification
            if not v["ok"]
        )
        messages.append(
            {"role": "user", "content": f"Your profile does not reproduce every example: {misses}. Fix it and reply with corrected JSON only."}
        )

    if best is None:
        raise ProfileError(f"The AI did not return a usable profile ({last_error}). Try rewording the example.")
    return best
