"""Toolbox command-line interface.

Run with::

    python -m cli convert --input ... --output ...
    toolbox convert --input ... --output ...   # after pip install -e .
"""

import sys

from .args import parse_args
from .console import cli_session
from .dispatch import dispatch


def main() -> None:
    args = parse_args()
    file_logging = not bool(getattr(args, "no_file_log", False))

    try:
        with cli_session(file_logging=file_logging):
            dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
