"""FastAPI application for the Media Tool local web API."""

from __future__ import annotations

import asyncio
import json
import queue
from contextlib import asynccontextmanager
from typing import AsyncIterator

from core.tools import bootstrap_ffmpeg, get_tools_status
from core.updates import app_version, check_for_update, get_apply_status, start_apply_update
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .jobs import job_manager
from .schemas import (
    CommandInfo,
    CommandsResponse,
    HealthResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobSummary,
    PARAM_MODELS,
    UpdateApplyResponse,
    UpdateApplyStatusResponse,
    UpdateCheckResponse,
    validate_params,
)

from .paths import FRONTEND_DIST


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    bootstrap_ffmpeg(auto_download=True)
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
    "audio": "Set default audio language in MKV files (MKVToolNix).",
    "dedup": "Strip duplicate (N) suffixes from filenames.",
    "download": "Download YouTube/other URLs as MP4 or MP3 (yt-dlp).",
    "trim": "Cut seconds off the start and/or end of videos.",
    "stitch": "Join multiple videos end-to-end.",
    "rename_folders": "Date-stamp subfolders (YYYY maand DD - Description).",
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
    return get_tools_status(auto_bootstrap=False)


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
