"""Local FastAPI backend for the Toolbox web UI."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .server import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
