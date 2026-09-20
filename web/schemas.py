"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.paths import clean_path_string
from core.rename_profiles import ProfileError, profile_from_dict

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
    "subtitle_translate",
    "subtitle_cleanup",
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
    # Format profile (cleanup rules + name patterns); None = standard behaviour.
    profile: Optional[dict[str, Any]] = None
    # "media" organizes shows/movies; "generic" renames folders and/or files in place.
    mode: Literal["media", "generic"] = "media"
    layout: bool = True
    targets: Literal["folders", "files", "both"] = "folders"
    max_depth: int = Field(default=1, ge=1, le=50)

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        try:
            return profile_from_dict(value).to_dict()
        except ProfileError as exc:
            raise ValueError(str(exc)) from exc


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
    output_name: Optional[str] = None
    playlist_subdir: Optional[str] = None
    playlist_index: Optional[int] = Field(default=None, ge=1)


class DownloadProbeRequest(BaseModel):
    url: str
    format: Literal["mp4", "mp3"] = "mp4"
    video_quality: Literal["best", "2160", "1440", "1080", "720", "480", "360"] = "best"
    audio_bitrate: int = Field(default=192, ge=64, le=320)


class DownloadProbeEntry(BaseModel):
    id: str
    title: str
    url: str
    duration: Optional[int] = None
    filesize: Optional[int] = None
    playlist_index: int = 1


class DownloadProbeResponse(BaseModel):
    url: str
    is_playlist: bool
    playlist_title: Optional[str] = None
    entries: list[DownloadProbeEntry]


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
    output_format: Literal["mp4", "mkv", "mov"] = "mp4"
    input_format: str = "mp4"
    no_recursive: bool = False
    reencode: bool = False
    dry_run: bool = True


class RenameFoldersParams(BaseModel):
    root: str
    dry_run: bool = True


class SubtitleTranslateParams(BaseModel):
    input: str
    source_lang: str = "auto"
    target_lang: str = "en"
    overwrite: bool = False
    dry_run: bool = True

    @field_validator("input")
    @classmethod
    def normalize_input(cls, value: str) -> str:
        return clean_path_string(value)


class SubtitleCleanupParams(BaseModel):
    input: str
    confirmed_removals: list[str] = Field(default_factory=list)
    junk_reviewed: bool = False
    dry_run: bool = True

    @field_validator("input")
    @classmethod
    def normalize_input(cls, value: str) -> str:
        return clean_path_string(value)


class SubtitleScanJunkRequest(BaseModel):
    input: str

    @field_validator("input")
    @classmethod
    def normalize_input(cls, value: str) -> str:
        return clean_path_string(value)


class SubtitleJunkItem(BaseModel):
    id: str
    file: str
    cue_index: int
    line_index: int
    text: str
    reason: str
    reason_label: str


class SubtitleScanJunkResponse(BaseModel):
    items: list[SubtitleJunkItem]
    detected_source_lang: Optional[str] = None


class LanguageOption(BaseModel):
    code: str
    label: str


class SubtitleLanguagesResponse(BaseModel):
    languages: list[LanguageOption]


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
    "subtitle_translate": SubtitleTranslateParams,
    "subtitle_cleanup": SubtitleCleanupParams,
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
    undo_available: bool = False
    undo_used: bool = False
    undo_op_count: Optional[int] = None
    undo_of: Optional[str] = None


class JobUndoResponse(BaseModel):
    job: JobSummary
    events_url: str
    source_job_id: str


class JobCreateResponse(BaseModel):
    job: JobSummary
    events_url: str


class RenameProfilesResponse(BaseModel):
    profiles: list[dict[str, Any]]


class RenameProfileSaveRequest(BaseModel):
    profile: dict[str, Any]


class RenameProfileTestRequest(BaseModel):
    profile: dict[str, Any]
    mode: Literal["media", "generic"] = "media"
    samples: list[str] = Field(min_length=1, max_length=20)


class RenameProfileTestItem(BaseModel):
    sample: str
    result: Optional[str] = None
    note: Optional[str] = None


class RenameProfileTestResponse(BaseModel):
    results: list[RenameProfileTestItem]


class RenameExample(BaseModel):
    before: str
    after: str


class RenameProfileGenerateRequest(BaseModel):
    mode: Literal["media", "generic"] = "media"
    examples: list[RenameExample] = Field(min_length=1, max_length=5)


class RenameProfileVerification(BaseModel):
    before: str
    expected: str
    actual: Optional[str] = None
    ok: bool


class RenameProfileGenerateResponse(BaseModel):
    profile: dict[str, Any]
    verification: list[RenameProfileVerification]
    all_ok: bool
    attempts: int
    model: str


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
    status_message: Optional[str] = None


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


class LogFileInfo(BaseModel):
    name: str
    size_bytes: int
    modified_at: str


class LogsStatsResponse(BaseModel):
    path: str
    total_bytes: int
    file_count: int
    files: list[LogFileInfo]


class SettingsResponse(BaseModel):
    file_logging: bool
    openai_api_key_set: bool = False
    openai_model: str = "gpt-4o-mini"
    logs: LogsStatsResponse


class SettingsUpdateRequest(BaseModel):
    file_logging: Optional[bool] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None


class ClearLogsResponse(BaseModel):
    deleted_count: int
    logs: LogsStatsResponse


class OpenLogFileRequest(BaseModel):
    name: str


class OpenPathResponse(BaseModel):
    ok: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_params(command: str, params: dict[str, Any]) -> BaseModel:
    model_cls = PARAM_MODELS.get(command)
    if model_cls is None:
        raise ValueError(f"Unknown command: {command}")
    return model_cls.model_validate(params)
