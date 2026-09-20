"""Convert: batch-convert videos between formats (wraps ``core.convert.run_convert``)."""

import argparse
from pathlib import Path

from core.convert import run_convert


def run(params, ctx):
    p = params
    run_convert(
        argparse.Namespace(
            input=Path(p["input"]),
            output=Path(p["output"]),
            input_format=p["input_format"],
            output_format=p["output_format"],
            deinterlace=p["deinterlace"],
            use_gpu=p["use_gpu"],
            crf=p["crf"],
            preset=p["preset"],
            dry_run=p["dry_run"],
            prune_output=p["prune_output"],
            copy_useful_only=p["copy_useful_only"],
        )
    )
