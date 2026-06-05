"""Background job execution and event streaming for the web API."""

from __future__ import annotations

import argparse
import json
import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core import config
from core import (
    DownloadCancelled,
    close_log_handlers,
    download_url,
    run_audio,
    run_convert,
    run_dedup,
    run_rename,
    run_stitch,
    run_trim,
    run_vts,
)
from core.progress import (
    CallbackLogHandler,
    LogHooks,
    attach_log_callback,
    detach_log_callback,
    set_active_hooks,
)
from core.rename import run_undo_from_journal
from core.rename_folders import process_root

from .schemas import (
    AudioParams,
    CommandName,
    ConvertParams,
    DedupParams,
    DownloadParams,
    JobStatus,
    RenameFoldersParams,
    RenameParams,
    StitchParams,
    TrimParams,
    VtsParams,
    utc_now_iso,
    validate_params,
)

COMMAND_LOGGERS: dict[str, tuple[str, ...]] = {
    "convert": ("dv_to_mp4", "dv_to_mp4.failures"),
    "vts": ("dv_to_mp4", "dv_to_mp4.failures"),
    "rename": ("video_rename",),
    "audio": ("video_audio",),
    "dedup": ("video_dedup",),
    "download": (),
    "trim": ("video_trim",),
    "stitch": ("video_stitch",),
    "rename_folders": (),
}


def _to_namespace(command: str, params: Any) -> argparse.Namespace:
    """Build an ``argparse.Namespace`` expected by :mod:`core` handlers."""
    if command == "convert":
        p: ConvertParams = params
        return argparse.Namespace(
            input=Path(p.input),
            output=Path(p.output),
            input_format=p.input_format,
            output_format=p.output_format,
            deinterlace=p.deinterlace,
            use_gpu=p.use_gpu,
            crf=p.crf,
            preset=p.preset,
            dry_run=p.dry_run,
            prune_output=p.prune_output,
            copy_useful_only=p.copy_useful_only,
        )
    if command == "vts":
        p = params
        return argparse.Namespace(
            input=Path(p.input),
            output=Path(p.output),
            output_format=p.output_format,
            reencode=p.reencode,
            deinterlace=p.deinterlace,
            use_gpu=p.use_gpu,
            crf=p.crf,
            preset=p.preset,
            include_menus=p.include_menus,
            min_mb=p.min_mb,
            dry_run=p.dry_run,
        )
    if command == "rename":
        p: RenameParams = params
        return argparse.Namespace(
            input=Path(p.input),
            output=Path(p.output) if p.output else None,
            type=p.type,
            apply=p.apply,
            copy=p.copy_files,
            undo=p.undo,
            prune_empty_dirs=p.prune_empty_dirs,
            no_titlecase=p.no_titlecase,
            strip_words=p.strip_words,
            bare_episode_numbers=p.bare_episode_numbers,
            default_sub_lang=p.default_sub_lang,
        )
    if command == "audio":
        p: AudioParams = params
        return argparse.Namespace(
            input=Path(p.input),
            lang=p.lang,
            apply=p.apply,
            set_language=p.set_language,
            no_recursive=p.no_recursive,
        )
    if command == "dedup":
        p: DedupParams = params
        return argparse.Namespace(input=Path(p.input), apply=p.apply)
    if command == "trim":
        p: TrimParams = params
        return argparse.Namespace(
            input=Path(p.input),
            output=Path(p.output) if p.output else None,
            trim_start=p.trim_start,
            trim_end=p.trim_end,
            input_format=p.input_format,
            no_recursive=p.no_recursive,
            reencode=p.reencode,
            replace=p.replace,
            dry_run=p.dry_run,
        )
    if command == "stitch":
        p: StitchParams = params
        return argparse.Namespace(
            input=[Path(x) for x in p.input],
            output=Path(p.output),
            output_format=p.output_format,
            input_format=p.input_format,
            no_recursive=p.no_recursive,
            reencode=p.reencode,
            dry_run=p.dry_run,
        )
    raise ValueError(f"No namespace mapping for command: {command}")


@dataclass
class Job:
    id: str
    command: CommandName
    status: JobStatus = "queued"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    file_logging: bool = True
    params: Any = None
    namespace: Optional[argparse.Namespace] = None
    undo_manifest: Optional[dict] = None
    undo_used: bool = False
    undo_of: Optional[str] = None
    events: queue.Queue = field(default_factory=queue.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.put({"type": event_type, "data": {**payload, "job_id": self.id}})

    def undo_op_count(self) -> Optional[int]:
        if not self.undo_manifest:
            return None
        ops = self.undo_manifest.get("operations")
        return len(ops) if isinstance(ops, list) else None

    def undo_available(self) -> bool:
        return (
            self.command == "rename"
            and self.undo_of is None
            and self.status == "completed"
            and bool(self.undo_manifest)
            and not self.undo_used
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "exit_code": self.exit_code,
            "undo_available": self.undo_available(),
            "undo_used": self.undo_used,
            "undo_op_count": self.undo_op_count(),
            "undo_of": self.undo_of,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def create(
        self,
        command: CommandName,
        params: dict[str, Any],
        *,
        file_logging: bool = True,
    ) -> Job:
        validated = validate_params(command, params)
        job = Job(
            id=str(uuid.uuid4()),
            command=command,
            file_logging=file_logging,
            params=validated,
        )
        if command not in ("download", "rename_folders"):
            job.namespace = _to_namespace(command, validated)

        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job,),
            daemon=True,
            name=f"web-job-{job.id[:8]}",
        )
        job._thread = thread
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.status not in ("queued", "running"):
            return False
        job.cancel_event.set()
        if job.command != "download":
            job.status = "cancelled"
            job.finished_at = utc_now_iso()
            job.emit("status", {"status": "cancelled"})
            job.events.put(None)
        return True

    def undo_rename(self, source_job_id: str, *, file_logging: bool = True) -> Job:
        with self._lock:
            source = self._jobs.get(source_job_id)
        if source is None:
            raise KeyError("Job not found")
        if source.command != "rename" or source.undo_of is not None:
            raise ValueError("Only rename apply jobs can be undone")
        if source.status != "completed":
            raise ValueError("Job has not completed")
        if source.undo_used:
            raise ValueError("This rename has already been undone")
        if not source.undo_manifest:
            raise ValueError("Nothing to undo (preview run or no files changed)")

        job = Job(
            id=str(uuid.uuid4()),
            command="rename",
            file_logging=file_logging,
            undo_of=source_job_id,
        )
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job,),
            daemon=True,
            name=f"web-job-{job.id[:8]}",
        )
        job._thread = thread
        thread.start()
        return job

    def _status_payload(self, job: Job) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": job.status,
            "error": job.error,
            "exit_code": job.exit_code,
            "undo_available": job.undo_available(),
            "undo_used": job.undo_used,
            "undo_op_count": job.undo_op_count(),
        }
        if job.undo_of and job.status == "completed":
            payload["undo_source_job_id"] = job.undo_of
            payload["source_undo_used"] = True
        return payload

    def _run_job(self, job: Job) -> None:
        job.status = "running"
        job.started_at = utc_now_iso()
        job.emit("status", {"status": "running"})

        config.FILE_LOGGING_ENABLED = job.file_logging

        def on_log(message: str, levelno: int) -> None:
            job.emit("log", {"message": message, "level": levelno})

        def on_progress(payload: dict) -> None:
            job.emit("progress", payload)

        hooks = LogHooks(on_log=on_log, on_progress=on_progress)
        set_active_hooks(hooks)

        root = logging.getLogger()
        root.setLevel(logging.INFO)
        callback_handler = attach_log_callback(
            root,
            on_log,
            formatter=logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"),
        )

        try:
            if job.undo_of:
                self._run_rename_undo(job)
            elif job.command == "download":
                self._run_download(job)
            elif job.command == "rename_folders":
                self._run_rename_folders(job)
            else:
                self._run_core(job)
            if job.status == "running":
                job.status = "completed"
                job.exit_code = 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            job.exit_code = code
            if job.cancel_event.is_set():
                job.status = "cancelled"
            else:
                job.status = "failed"
                job.error = f"Exited with code {code}"
        except DownloadCancelled:
            job.status = "cancelled"
            job.exit_code = None
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.exit_code = 1
            logging.getLogger(__name__).exception("Job %s failed", job.id)
            job.emit("log", {"message": f"Error: {exc}", "level": logging.ERROR})
        finally:
            detach_log_callback(root, callback_handler)
            set_active_hooks(None)
            loggers = COMMAND_LOGGERS.get(job.command, ())
            if loggers:
                close_log_handlers(*loggers)
            if job.status in ("completed", "failed", "cancelled"):
                job.finished_at = utc_now_iso()
                job.emit("status", self._status_payload(job))
            job.events.put(None)

    def _run_core(self, job: Job) -> None:
        handlers: dict[str, Callable[..., Any]] = {
            "convert": run_convert,
            "vts": run_vts,
            "rename": run_rename,
            "audio": run_audio,
            "dedup": run_dedup,
            "trim": run_trim,
            "stitch": run_stitch,
        }
        handler = handlers[job.command]
        if job.cancel_event.is_set():
            job.status = "cancelled"
            return
        if job.command == "rename":
            manifest = run_rename(job.namespace)
            if manifest:
                job.undo_manifest = manifest
        else:
            handler(job.namespace)

    def _run_rename_undo(self, job: Job) -> None:
        source = self.get(job.undo_of or "")
        if source is None:
            raise ValueError(f"Source job not found: {job.undo_of}")
        if not source.undo_manifest:
            raise ValueError("Source job has no undo manifest")
        if source.undo_used:
            raise ValueError("Rename already undone")

        logger = logging.getLogger("video_rename")
        restored, failed, skipped = run_undo_from_journal(
            source.undo_manifest, apply=True, logger=logger
        )
        if failed > 0:
            job.status = "failed"
            job.exit_code = 1
            job.error = f"Undo failed for {failed} operation(s)"
        elif restored == 0:
            job.status = "failed"
            job.exit_code = 1
            job.error = "Nothing to undo (files missing or already restored)"
        else:
            with self._lock:
                source.undo_used = True
            if skipped:
                job.emit(
                    "log",
                    {
                        "message": f"Undo complete with {skipped} skipped operation(s).",
                        "level": logging.WARNING,
                    },
                )

    def _run_download(self, job: Job) -> None:
        p: DownloadParams = job.params
        if job.cancel_event.is_set():
            job.status = "cancelled"
            return

        def progress_cb(payload: dict) -> None:
            if job.cancel_event.is_set():
                return
            job.emit("progress", payload)

        try:
            download_url(
                url=p.url,
                output_dir=Path(p.output),
                out_format=p.format,
                video_quality=p.video_quality,
                audio_bitrate=p.audio_bitrate,
                playlist=p.playlist,
                no_playlist_index=p.no_playlist_index,
                output_name=p.output_name,
                playlist_subdir=p.playlist_subdir,
                playlist_index=p.playlist_index,
                progress_callback=progress_cb,
                cancel_event=job.cancel_event,
                tag=job.id[:8],
            )
            if job.cancel_event.is_set():
                job.status = "cancelled"
        except DownloadCancelled:
            job.status = "cancelled"

    def _run_rename_folders(self, job: Job) -> None:
        p: RenameFoldersParams = job.params
        if job.cancel_event.is_set():
            job.status = "cancelled"
            return

        def log_line(line: str) -> None:
            job.emit("log", {"message": line, "level": logging.INFO})

        process_root(Path(p.root), p.dry_run, log=log_line)


# Module-level singleton used by the FastAPI app.
job_manager = JobManager()
