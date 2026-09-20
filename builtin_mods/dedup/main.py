"""Fix Duplicates: strip "(2)" style suffixes (wraps ``core.rename.run_dedup``)."""

import argparse
from pathlib import Path

from core.rename import run_dedup


def run(params, ctx):
    run_dedup(argparse.Namespace(input=Path(params["input"]), apply=params["apply"]))
