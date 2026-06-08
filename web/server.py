"""FastAPI application for the Media Tool local web API."""

from __future__ import annotations

import asyncio
import json
import queue
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from core.download import probe_url
from core.subtitles import detect_lang_from_path, scan_junk
from core.subtitle_languages import language_options
from core.log_storage import clear_logs, logs_stats
from core.settings_store import load_settings, save_settings
from core.tools import get_tools_status, retry_bootstrap_background, start_bootstrap_background
from core.updates import check_for_update, get_apply_status, start_apply_update
from core.version import app_version
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .jobs import job_manager
from .schemas import (
    ClearLogsResponse,
    CommandInfo,
    CommandsResponse,
    DownloadProbeRequest,
    DownloadProbeResponse,
    HealthResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobSummary,
    JobUndoResponse,
    LogsStatsResponse,
    PARAM_MODELS,
    SettingsResponse,
    SettingsUpdateRequest,
    SubtitleLanguagesResponse,
    SubtitleScanJunkRequest,
    SubtitleScanJunkResponse,
    LanguageOption,
    SubtitleJunkItem,
    UpdateApplyResponse,
    UpdateApplyStatusResponse,
    UpdateCheckResponse,
    validate_params,
)

from .paths import FRONTEND_DIST


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    start_bootstrap_background()
    yield


app = FastAPI(
    title="Media Tool API",
    description="Local REST + SSE API for video conversion, rename, download, and related tools.",
    version=app_version(),
    lifespan=_lifespan,
)

# Allow the future React dev server and pywebview origin to call localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COMMAND_DESCRIPTIONS: dict[str, str] = {
    "convert": "Batch-convert video files with folder mirroring (DV→MP4, etc.).",
    "vts": "Join DVD VIDEO_TS VOB segments into one file per title.",
    "rename": "Organize TV/movie files and subtitles (Plex/Jellyfin style).",
    "audio": "Set default audio language in MKV files (ffmpeg stream copy).",
    "dedup": "Strip duplicate (N) suffixes from filenames.",
    "download": "Download URLs from yt-dlp supported sites as MP4 or MP3.",
    "trim": "Cut seconds off the start and/or end of videos.",
    "stitch": "Join multiple videos end-to-end.",
    "rename_folders": "Date-stamp subfolders (YYYY maand DD - Description).",
    "subtitle_translate": "Translate SRT subtitles with OpenAI.",
    "subtitle_cleanup": "Remove junk lines from SRT subtitles in place.",
}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(version=app_version())


@app.get("/api/updates/check", response_model=UpdateCheckResponse)
def updates_check() -> UpdateCheckResponse:
    return UpdateCheckResponse(**check_for_update().to_dict())


@app.post("/api/updates/apply", response_model=UpdateApplyResponse)
def updates_apply() -> UpdateApplyResponse:
    info = check_for_update()
    ok, detail = start_apply_update(info)
    return UpdateApplyResponse(ok=ok, detail=detail)


@app.get("/api/updates/status", response_model=UpdateApplyStatusResponse)
def updates_status() -> UpdateApplyStatusResponse:
    return UpdateApplyStatusResponse(**get_apply_status())


@app.get("/api/tools")
def tools_status() -> dict:
    return get_tools_status(auto_bootstrap=True)


@app.post("/api/tools/bootstrap")
def tools_bootstrap_retry() -> dict:
    retry_bootstrap_background()
    return get_tools_status(auto_bootstrap=False)


def _settings_response() -> SettingsResponse:
    settings = load_settings()
    api_key = str(settings.get("openai_api_key") or "").strip()
    return SettingsResponse(
        file_logging=bool(settings.get("file_logging", True)),
        openai_api_key_set=bool(api_key),
        openai_model=str(settings.get("openai_model") or "gpt-4o-mini"),
        logs=LogsStatsResponse(**logs_stats()),
    )


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _settings_response()


@app.patch("/api/settings", response_model=SettingsResponse)
def update_settings(body: SettingsUpdateRequest) -> SettingsResponse:
    updates = body.model_dump(exclude_unset=True)
    if "openai_api_key" in updates:
        key = updates["openai_api_key"]
        if key is not None and not str(key).strip():
            updates["openai_api_key"] = ""
    if updates:
        save_settings(**updates)
    return _settings_response()


@app.get("/api/subtitles/languages", response_model=SubtitleLanguagesResponse)
def subtitle_languages() -> SubtitleLanguagesResponse:
    return SubtitleLanguagesResponse(
        languages=[LanguageOption(**item) for item in language_options()],
    )


@app.post("/api/subtitles/scan-junk", response_model=SubtitleScanJunkResponse)
def subtitle_scan_junk(body: SubtitleScanJunkRequest) -> SubtitleScanJunkResponse:
    from pathlib import Path

    from core.paths import clean_path_string, path_exists, path_is_dir, path_is_file

    input_path = Path(clean_path_string(body.input))
    if not path_exists(input_path):
        raise HTTPException(status_code=422, detail=f"Input path not found: {input_path}")
    try:
        items = scan_junk(input_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    detected: Optional[str] = None
    if path_is_file(input_path):
        detected = detect_lang_from_path(input_path)
    elif path_is_dir(input_path):
        for path in sorted(input_path.rglob("*.srt")):
            detected = detect_lang_from_path(path)
            if detected:
                break

    return SubtitleScanJunkResponse(
        items=[SubtitleJunkItem(**item.to_dict()) for item in items],
        detected_source_lang=detected,
    )


@app.delete("/api/settings/logs", response_model=ClearLogsResponse)
def delete_logs() -> ClearLogsResponse:
    deleted = clear_logs()
    return ClearLogsResponse(deleted_count=deleted, logs=LogsStatsResponse(**logs_stats()))


@app.get("/api/commands", response_model=CommandsResponse)
def list_commands() -> CommandsResponse:
    commands = [
        CommandInfo(name=name, description=COMMAND_DESCRIPTIONS.get(name, ""))
        for name in PARAM_MODELS
    ]
    return CommandsResponse(commands=commands)  # type: ignore[arg-type]


@app.get("/api/commands/{command}/schema")
def command_schema(command: str) -> dict:
    model_cls = PARAM_MODELS.get(command)
    if model_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown command: {command}")
    return model_cls.model_json_schema()


@app.get("/api/jobs", response_model=list[JobSummary])
def list_jobs() -> list[JobSummary]:
    jobs = sorted(job_manager.list_jobs(), key=lambda j: j.created_at, reverse=True)
    return [JobSummary(**j.to_dict()) for j in jobs]


@app.get("/api/jobs/{job_id}", response_model=JobSummary)
def get_job(job_id: str) -> JobSummary:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobSummary(**job.to_dict())


@app.post("/api/download/probe", response_model=DownloadProbeResponse)
def download_probe(body: DownloadProbeRequest) -> DownloadProbeResponse:
    try:
        result = probe_url(
            url=body.url,
            out_format=body.format,
            video_quality=body.video_quality,
            audio_bitrate=body.audio_bitrate,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DownloadProbeResponse(**result)


@app.post("/api/jobs", response_model=JobCreateResponse, status_code=201)
def create_job(body: JobCreateRequest) -> JobCreateResponse:
    try:
        validate_params(body.command, body.params)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = job_manager.create(
        body.command,
        body.params,
        file_logging=body.file_logging,
    )
    summary = JobSummary(**job.to_dict())
    return JobCreateResponse(
        job=summary,
        events_url=f"/api/jobs/{job.id}/events",
    )


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not job_manager.cancel(job_id):
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=409, detail=f"Job cannot be cancelled (status={job.status})")
    return {"ok": True, "job_id": job_id}


@app.post("/api/jobs/{job_id}/undo", response_model=JobUndoResponse, status_code=201)
def undo_rename_job(job_id: str) -> JobUndoResponse:
    try:
        job = job_manager.undo_rename(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    summary = JobSummary(**job.to_dict())
    return JobUndoResponse(
        job=summary,
        events_url=f"/api/jobs/{job.id}/events",
        source_job_id=job_id,
    )


async def _sse_stream(job_id: str) -> AsyncIterator[str]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    loop = asyncio.get_running_loop()

    while True:
        try:
            item = await loop.run_in_executor(None, job.events.get, True, 30.0)
        except queue.Empty:  # timeout waiting for events
            yield ": keepalive\n\n"
            continue

        if item is None:
            yield f"event: end\ndata: {json.dumps({'job_id': job_id})}\n\n"
            break

        event_type = item.get("type", "message")
        data = json.dumps(item.get("data", {}))
        yield f"event: {event_type}\ndata: {data}\n\n"


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _sse_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
def root() -> dict:
    return {
        "name": "Media Tool API",
        "docs": "/docs",
        "health": "/api/health",
        "app": "/app/" if FRONTEND_DIST.is_dir() else None,
    }


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/app/assets", StaticFiles(directory=assets_dir), name="app-assets")

    @app.get("/app")
    @app.get("/app/{rest:path}")
    def spa_app(rest: str = "") -> FileResponse:
        """React UI (production build from ``web/frontend``)."""
        candidate = FRONTEND_DIST / rest
        if rest and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend not built. Run: cd web/frontend && npm run build")
        return FileResponse(index)
