"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

CommandName = Literal[
    "convert",
    "vts",
    "rename",
    "audio",
    "dedup",
    "download",
    "trim",
    "stitch",
    "rename_folders",
]

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class ConvertParams(BaseModel):
    input: str
    output: str
    input_format: str = "dv"
    output_format: Literal["mp4", "mkv", "mov"] = "mp4"
    deinterlace: Literal["auto", "on", "off"] = "auto"
    use_gpu: Literal["auto", "on", "off"] = "auto"
    crf: int = Field(default=19, ge=0, le=51)
    preset: str = "slow"
    dry_run: bool = True
    prune_output: bool = False
    copy_useful_only: bool = False


class VtsParams(BaseModel):
    input: str
    output: str
    output_format: Literal["mkv", "mp4", "mov"] = "mkv"
    reencode: bool = False
    deinterlace: Literal["auto", "on", "off"] = "auto"
    use_gpu: Literal["auto", "on", "off"] = "auto"
    crf: int = Field(default=19, ge=0, le=51)
    preset: str = "slow"
    include_menus: bool = False
    min_mb: int = Field(default=50, ge=0)
    dry_run: bool = True


class RenameParams(BaseModel):
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


class AudioParams(BaseModel):
    input: str
    lang: str
    apply: bool = False
    set_language: bool = False
    no_recursive: bool = False


class DedupParams(BaseModel):
    input: str
    apply: bool = False


class DownloadParams(BaseModel):
    url: str
    output: str
    format: Literal["mp4", "mp3"] = "mp4"
    video_quality: Literal["best", "2160", "1440", "1080", "720", "480", "360"] = "best"
    audio_bitrate: int = Field(default=192, ge=64, le=320)
    playlist: bool = False
    no_playlist_index: bool = False


class TrimParams(BaseModel):
    input: str
    output: Optional[str] = None
    trim_start: str = "0"
    trim_end: str = "0"
    input_format: str = "mp4"
    no_recursive: bool = False
    reencode: bool = False
    replace: bool = False
    dry_run: bool = True


class StitchParams(BaseModel):
    input: list[str] = Field(min_length=1)
    output: str
    input_format: str = "mp4"
    no_recursive: bool = False
    reencode: bool = False
    dry_run: bool = True


class RenameFoldersParams(BaseModel):
    root: str
    dry_run: bool = True


PARAM_MODELS: dict[str, type[BaseModel]] = {
    "convert": ConvertParams,
    "vts": VtsParams,
    "rename": RenameParams,
    "audio": AudioParams,
    "dedup": DedupParams,
    "download": DownloadParams,
    "trim": TrimParams,
    "stitch": StitchParams,
    "rename_folders": RenameFoldersParams,
}


class JobCreateRequest(BaseModel):
    command: CommandName
    params: dict[str, Any] = Field(default_factory=dict)
    file_logging: bool = True


class JobSummary(BaseModel):
    id: str
    command: CommandName
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None


class JobCreateResponse(BaseModel):
    job: JobSummary
    events_url: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class UpdateCheckResponse(BaseModel):
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool = False
    can_install: bool = False
    download_url: Optional[str] = None
    asset_name: Optional[str] = None
    release_url: Optional[str] = None
    release_notes: Optional[str] = None
    error: Optional[str] = None


class UpdateApplyResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


class UpdateApplyStatusResponse(BaseModel):
    phase: Literal["idle", "downloading", "installing", "error"] = "idle"
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None


class CommandInfo(BaseModel):
    name: CommandName
    description: str


class CommandsResponse(BaseModel):
    commands: list[CommandInfo]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_params(command: str, params: dict[str, Any]) -> BaseModel:
    model_cls = PARAM_MODELS.get(command)
    if model_cls is None:
        raise ValueError(f"Unknown command: {command}")
    return model_cls.model_validate(params)
