"""DVD (VTS): join DVD VOB segments into one file per title (wraps ``core.vts.run_vts``)."""

import argparse
from pathlib import Path

from core.vts import run_vts


def run(params, ctx):
    p = params
    run_vts(
        argparse.Namespace(
            input=Path(p["input"]),
            output=Path(p["output"]),
            output_format=p["output_format"],
            reencode=p["reencode"],
            deinterlace=p["deinterlace"],
            use_gpu=p["use_gpu"],
            crf=p["crf"],
            preset=p["preset"],
            include_menus=p["include_menus"],
            min_mb=p["min_mb"],
            dry_run=p["dry_run"],
        )
    )
