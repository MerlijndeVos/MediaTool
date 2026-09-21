"""Rename: organize shows/movies or clean up names with format profiles (``core.rename``).

Applied renames leave an undo manifest; ``undo()`` reverses one.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.paths import clean_path_string
from core.rename import run_rename, run_undo_from_journal
from core.rename_generic import check_options, check_root_renamable
from core.rename_profiles import ProfileError, profile_from_dict


class Params(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input: str
    output: Optional[str] = None
    type: Literal["auto", "tv", "movie"] = "auto"
    apply: bool = False
    copy_files: bool = Field(default=False, alias="copy")
    undo: bool = False
    prune_empty_dirs: bool = False
    no_titlecase: bool = False
    strip_words: list[str] = Field(default_factory=list)
    bare_episode_numbers: bool = False
    default_sub_lang: str = "en"
    # Format profile (cleanup rules + name patterns); None = standard behaviour.
    profile: Optional[dict[str, Any]] = None
    # "media" organizes shows/movies; "generic" renames folders and/or files in place.
    mode: Literal["media", "generic"] = "media"
    layout: bool = True
    targets: Literal["folders", "files", "both"] = "folders"
    max_depth: int = Field(default=1, ge=1, le=50)
    # Generic mode: also rename the selected folder itself, after everything inside it.
    include_root: bool = False

    @model_validator(mode="after")
    def _validate_include_root(self) -> "Params":
        if not self.include_root:
            return self
        if self.mode != "generic":
            raise ValueError("Renaming the selected folder only works in the Other mode.")
        try:
            check_options(self.targets, True)
            check_root_renamable(Path(clean_path_string(self.input)))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        try:
            return profile_from_dict(value).to_dict()
        except ProfileError as exc:
            raise ValueError(str(exc)) from exc


def run(params, ctx):
    p = params
    manifest = run_rename(
        argparse.Namespace(
            input=Path(p["input"]),
            output=Path(p["output"]) if p["output"] else None,
            type=p["type"],
            apply=p["apply"],
            copy=p["copy_files"],
            undo=p["undo"],
            prune_empty_dirs=p["prune_empty_dirs"],
            no_titlecase=p["no_titlecase"],
            strip_words=p["strip_words"],
            bare_episode_numbers=p["bare_episode_numbers"],
            default_sub_lang=p["default_sub_lang"],
            profile=p["profile"],
            mode=p["mode"],
            layout=p["layout"],
            targets=p["targets"],
            max_depth=p["max_depth"],
            include_root=p["include_root"],
        )
    )
    if manifest:
        ctx.set_undo_manifest(manifest)


def undo(manifest, ctx):
    """Reverse a rename from its undo manifest; returns counts for the job runner."""
    restored, failed, skipped = run_undo_from_journal(
        manifest, apply=True, logger=logging.getLogger("video_rename")
    )
    return {"restored": restored, "failed": failed, "skipped": skipped}
