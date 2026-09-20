"""Trim: cut time off the start and/or end of videos (wraps ``core.convert.run_trim``)."""

import argparse
from pathlib import Path

from core.convert import run_trim


def run(params, ctx):
    p = params
    run_trim(
        argparse.Namespace(
            input=Path(p["input"]),
            output=Path(p["output"]) if p["output"] else None,
            trim_start=p["trim_start"],
            trim_end=p["trim_end"],
            input_format=p["input_format"],
            no_recursive=p["no_recursive"],
            reencode=p["reencode"],
            replace=p["replace"],
            dry_run=p["dry_run"],
        )
    )
