#!/usr/bin/env python3
"""Optional: download ffmpeg into packaging/bundled-tools/bin for local testing.

Installers no longer bundle ffmpeg — the app downloads on first launch.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ffmpeg_bootstrap import ensure_ffmpeg_at  # noqa: E402

DEST = REPO_ROOT / "packaging" / "bundled-tools" / "bin"


def main() -> None:
    ensure_ffmpeg_at(DEST, log=print)
    print(f"Tools ready in {DEST}")


if __name__ == "__main__":
    main()
