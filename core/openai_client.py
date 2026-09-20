"""OpenAI settings shared by the features that call the API (subtitles, rename profiles)."""

from __future__ import annotations

import os
from typing import Any, Optional

from .settings_store import load_settings

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def openai_api_key() -> str:
    settings = load_settings()
    key = (settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "OpenAI API key not configured. Add it in Logging settings or set OPENAI_API_KEY."
        )
    return key


def openai_model(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    settings = load_settings()
    return str(settings.get("openai_model") or DEFAULT_OPENAI_MODEL)


def new_client() -> Any:
    """Build an OpenAI client from the saved key."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The openai package is not installed. Reinstall Media Tool with web/desktop extras."
        ) from exc
    return OpenAI(api_key=openai_api_key())
