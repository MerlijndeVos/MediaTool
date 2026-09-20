"""Clean Up: remove junk lines from SRT files in place (wraps ``core.subtitles``)."""

import argparse
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from core.paths import clean_path_string
from core.subtitles import run_subtitle_cleanup


class Params(BaseModel):
    input: str
    confirmed_removals: list[str] = Field(default_factory=list)
    junk_reviewed: bool = False
    dry_run: bool = True

    @field_validator("input")
    @classmethod
    def normalize_input(cls, value: str) -> str:
        return clean_path_string(value)


def run(params, ctx):
    p = params
    run_subtitle_cleanup(
        argparse.Namespace(
            input=Path(p["input"]),
            confirmed_removals=list(p["confirmed_removals"]),
            junk_reviewed=p["junk_reviewed"],
            dry_run=p["dry_run"],
        )
    )
