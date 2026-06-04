"""Media Tool command-line interface."""

from .args import parse_args

__all__ = ["parse_args", "main"]


def main() -> None:
    from .__main__ import main as _run

    _run()
