"""Stitch: join clips end-to-end (wraps ``core.convert.run_stitch``).

The form is a custom panel (ordered file list), so the parameters are validated by ``Params``
below instead of being described in ``mod.toml``.
"""

import argparse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.convert import run_stitch


class Params(BaseModel):
    input: list[str] = Field(min_length=1)
    output: str
    output_format: Literal["mp4", "mkv", "mov"] = "mp4"
    input_format: str = "mp4"
    no_recursive: bool = False
    reencode: bool = False
    dry_run: bool = True


def run(params, ctx):
    p = params
    run_stitch(
        argparse.Namespace(
            input=[Path(x) for x in p["input"]],
            output=Path(p["output"]),
            output_format=p["output_format"],
            input_format=p["input_format"],
            no_recursive=p["no_recursive"],
            reencode=p["reencode"],
            dry_run=p["dry_run"],
        )
    )
