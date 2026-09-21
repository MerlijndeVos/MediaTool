"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from core.paths import clean_path_string

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


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


class JobCreateRequest(BaseModel):
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    file_logging: bool = True


class JobSummary(BaseModel):
    id: str
    command: str
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
    name: str
    description: str


class CommandsResponse(BaseModel):
    commands: list[CommandInfo]


class ModsResponse(BaseModel):
    mods: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    safe_mode: bool = False
    mods_dir: str


class ModEnableRequest(BaseModel):
    enabled: bool


class LogFileInfo(BaseModel):
    name: str
    size_bytes: int
    modified_at: str


class LogsStatsResponse(BaseModel):
    path: str
    total_bytes: int
    file_count: int
    files: list[LogFileInfo]


class AiProviderSettings(BaseModel):
    """One provider's saved settings. The key itself is never sent back."""

    api_key_set: bool = False
    api_key_from_env: bool = False
    model: str = ""
    default_model: str = ""
    base_url: str = ""


class AiSettingsResponse(BaseModel):
    provider: str
    providers: dict[str, AiProviderSettings]


class SettingsResponse(BaseModel):
    file_logging: bool
    ai: AiSettingsResponse
    logs: LogsStatsResponse


class AiProviderUpdate(BaseModel):
    """Omitted/null fields are kept; an empty string clears the field."""

    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class AiSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    providers: Optional[dict[str, AiProviderUpdate]] = None


class SettingsUpdateRequest(BaseModel):
    file_logging: Optional[bool] = None
    ai: Optional[AiSettingsUpdate] = None


class AiTestRequest(AiProviderUpdate):
    """Try a provider with the (possibly unsaved) form values; blank fields use saved ones."""

    provider: str


class AiTestResponse(BaseModel):
    ok: bool
    message: str


class ClearLogsResponse(BaseModel):
    deleted_count: int
    logs: LogsStatsResponse


class OpenLogFileRequest(BaseModel):
    name: str


class LogChunkResponse(BaseModel):
    name: str
    size_bytes: int
    start: int
    end: int
    has_earlier: bool
    lines: list[str]


class OpenPathResponse(BaseModel):
    ok: bool = True


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
