"""Shared helpers for starting the local API server."""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request


def pick_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Return *preferred* if bindable, otherwise an ephemeral port on *host*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, preferred))
            return preferred
        except OSError:
            sock.bind((host, 0))
            return sock.getsockname()[1]


def wait_for_server(base_url: str, timeout: float = 30.0) -> None:
    """Poll ``/api/health`` until the server responds or *timeout* expires."""
    health_url = f"{base_url.rstrip('/')}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready within {timeout:.0f}s ({health_url})")


def run_uvicorn(host: str, port: int, *, log_level: str = "info") -> None:
    import uvicorn

    uvicorn.run(
        "web.server:app",
        host=host,
        port=port,
        log_level=log_level,
    )
