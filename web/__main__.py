"""Run the Media Tool API server on localhost.

Usage::

    python -m web
    python -m web --port 8765
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.mods import set_safe_mode

from .run import require_port, run_uvicorn

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main() -> None:
    parser = argparse.ArgumentParser(description="Media Tool local API server")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port (default: {DEFAULT_PORT}; uses another free port if busy).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind address (default: {DEFAULT_HOST} — local only).",
    )
    parser.add_argument(
        "--no-mods",
        action="store_true",
        help="Safe mode: do not load user-installed mods (built-in features are unaffected).",
    )
    args = parser.parse_args()
    if args.no_mods:
        set_safe_mode(True)

    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Web dependencies are required. Install with:\n"
            '  pip install -e ".[web]"'
        ) from exc

    port = require_port(args.port, args.host) if args.host == DEFAULT_HOST else args.port
    print(f"Media Tool API: http://{args.host}:{port}")
    print(f"  OpenAPI docs: http://{args.host}:{port}/docs")
    frontend_dist = Path(__file__).resolve().parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        print(f"  Web UI:       http://{args.host}:{port}/app/")

    run_uvicorn(args.host, port)


if __name__ == "__main__":
    main()
