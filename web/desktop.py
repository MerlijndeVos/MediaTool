"""Desktop shell: local API server + native pywebview window."""

from __future__ import annotations

import argparse
import os
import threading

from core.tools import bootstrap_ffmpeg
from core.updates import register_quit_callback

from .desktop_api import DesktopApi
from .paths import FRONTEND_DIST
from .run import pick_port, run_uvicorn, wait_for_server

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
WINDOW_TITLE = "Media Tool"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Media Tool desktop app")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Preferred TCP port (default: {DEFAULT_PORT}; uses another free port if busy).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind address (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable webview devtools (where supported).",
    )
    args = parser.parse_args(argv)

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "pywebview is required for the desktop app. Install with:\n"
            '  pip install -e ".[desktop]"'
        ) from exc

    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Web dependencies are required for the desktop app. Install with:\n"
            '  pip install -e ".[desktop]"'
        ) from exc

    if not FRONTEND_DIST.is_dir():
        raise SystemExit(
            "Frontend not built. Run:\n"
            "  cd web/frontend && npm install && npm run build"
        )

    bootstrap_ffmpeg(auto_download=True)

    port = pick_port(args.port, args.host) if args.host == DEFAULT_HOST else args.port
    base_url = f"http://{args.host}:{port}"
    app_url = f"{base_url}/app/"

    server = threading.Thread(
        target=run_uvicorn,
        kwargs={"host": args.host, "port": port, "log_level": "warning"},
        daemon=True,
        name="media-tool-api",
    )
    server.start()
    wait_for_server(base_url)

    window = webview.create_window(
        WINDOW_TITLE,
        app_url,
        js_api=DesktopApi(),
        width=1280,
        height=840,
        min_size=(960, 640),
    )

    def _quit_for_update() -> None:
        try:
            window.destroy()
        except Exception:
            pass
        os._exit(0)

    register_quit_callback(_quit_for_update)
    webview.start(debug=args.debug)


if __name__ == "__main__":
    main()
