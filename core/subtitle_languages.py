"""Subtitle language codes and labels shared by core and API."""

from __future__ import annotations

from typing import Optional

from .rename import SUB_LANG_TOKENS

# Map filename tokens (ISO 639-1/2 and common names) to a canonical ISO 639-1 code.
LANG_TOKEN_TO_CODE: dict[str, str] = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "nl": "nl",
    "dut": "nl",
    "nld": "nl",
    "dutch": "nl",
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "de": "de",
    "ger": "de",
    "deu": "de",
    "german": "de",
    "es": "es",
    "spa": "es",
    "spanish": "es",
    "it": "it",
    "ita": "it",
    "italian": "it",
    "pt": "pt",
    "por": "pt",
    "portuguese": "pt",
    "pob": "pt",
    "sv": "sv",
    "swe": "sv",
    "swedish": "sv",
    "no": "no",
    "nor": "no",
    "norwegian": "no",
    "da": "da",
    "dan": "da",
    "danish": "da",
    "fi": "fi",
    "fin": "fi",
    "finnish": "fi",
    "pl": "pl",
    "pol": "pl",
    "polish": "pl",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "zh": "zh",
    "chi": "zh",
    "zho": "zh",
    "chinese": "zh",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "ar": "ar",
    "ara": "ar",
    "arabic": "ar",
    "tr": "tr",
    "tur": "tr",
    "turkish": "tr",
    "cs": "cs",
    "cze": "cs",
    "ces": "cs",
    "hu": "hu",
    "hun": "hu",
    "el": "el",
    "gre": "el",
    "ell": "el",
    "he": "he",
    "heb": "he",
    "th": "th",
    "tha": "th",
    "vi": "vi",
    "vie": "vi",
    "ro": "ro",
    "ron": "ro",
    "rum": "ro",
    "uk": "uk",
    "ukr": "uk",
    "hr": "hr",
    "hrv": "hr",
    "sr": "sr",
    "srp": "sr",
    "sk": "sk",
    "slk": "sk",
    "slo": "sk",
    "sl": "sl",
    "slv": "sl",
    "bg": "bg",
    "bul": "bg",
    "et": "et",
    "est": "et",
    "lv": "lv",
    "lav": "lv",
    "lt": "lt",
    "lit": "lt",
    "id": "id",
    "ind": "id",
    "ms": "ms",
    "msa": "ms",
    "hi": "hi",
    "hin": "hi",
}

LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "nl": "Dutch",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
    "tr": "Turkish",
    "cs": "Czech",
    "hu": "Hungarian",
    "el": "Greek",
    "he": "Hebrew",
    "th": "Thai",
    "vi": "Vietnamese",
    "ro": "Romanian",
    "uk": "Ukrainian",
    "hr": "Croatian",
    "sr": "Serbian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "bg": "Bulgarian",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "id": "Indonesian",
    "ms": "Malay",
    "hi": "Hindi",
}


def normalize_lang_code(token: str) -> Optional[str]:
    """Return a canonical ISO 639-1 code for *token*, or None if unknown."""
    if not token:
        return None
    key = token.strip().lower()
    if key in LANG_TOKEN_TO_CODE:
        return LANG_TOKEN_TO_CODE[key]
    if key in LANGUAGE_LABELS:
        return key
    return None


def language_options() -> list[dict[str, str]]:
    """Sorted language list for UI dropdowns."""
    return [
        {"code": code, "label": LANGUAGE_LABELS[code]}
        for code in sorted(LANGUAGE_LABELS.keys())
    ]


def is_known_lang_token(token: str) -> bool:
    return token.lower() in SUB_LANG_TOKENS
