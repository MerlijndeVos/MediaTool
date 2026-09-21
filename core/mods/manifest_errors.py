"""The error raised for a malformed ``mod.toml`` (kept apart so the theme parser can raise it too)."""

from __future__ import annotations


class ManifestError(ValueError):
    """The manifest is malformed; the message says what to fix."""
