"""Audio Default: set the default audio track in MKV files (wraps ``core.audio.run_audio``)."""

import argparse
from pathlib import Path

from core.audio import run_audio


def run(params, ctx):
    p = params
    run_audio(
        argparse.Namespace(
            input=Path(p["input"]),
            lang=p["lang"],
            apply=p["apply"],
            set_language=p["set_language"],
            no_recursive=p["no_recursive"],
        )
    )
