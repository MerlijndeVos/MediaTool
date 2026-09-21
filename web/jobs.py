"""Background job execution and event streaming for the web API.

Every feature is a mod (see :mod:`core.mods`): a job validates its parameters against the
mod, then calls the mod's ``run(params, ctx)`` on a background thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from core import close_log_handlers, config
from core.mods import Mod, ModCancelled, ModContext, ModError, registry
from core.mods.results import MAX_RESULTS_PER_JOB, openable_paths
from core.progress import (
    LogHooks,
    attach_log_callback,
    detach_log_callback,
    set_active_hooks,
)

from .mod_params import validate_params
from .schemas import JobStatus, utc_now_iso


@dataclass
class Job:
    id: str
    command: str
    status: JobStatus = "queued"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    file_logging: bool = True
    params: Optional[dict[str, Any]] = None
    undo_manifest: Optional[dict] = None
    undo_used: bool = False
    undo_of: Optional[str] = None
    # What the mod chose to show after the run (ctx.result). Sent to the page as "result" events.
    results: list[dict[str, Any]] = field(default_factory=list)
    events: queue.Queue = field(default_factory=queue.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.put({"type": event_type, "data": {**payload, "job_id": self.id}})

    def add_result(self, payload: dict[str, Any]) -> None:
        if len(self.results) >= MAX_RESULTS_PER_JOB:
            return
        self.results.append(payload)
        self.emit("result", payload)

    def result_paths(self) -> set[str]:
        """The files this job listed in a ``files`` result: the only ones the page may open."""
        return openable_paths(self.results)

    def undo_op_count(self) -> Optional[int]:
        if not self.undo_manifest:
            return None
        ops = self.undo_manifest.get("operations")
        return len(ops) if isinstance(ops, list) else None

    def renamed_root(self) -> Optional[dict]:
        """``{"from", "to"}`` when the job renamed the folder the user had selected, else None."""
        if not self.undo_manifest:
            return None
        value = self.undo_manifest.get("renamed_root")
        return value if isinstance(value, dict) else None

    def undo_available(self) -> bool:
        return (
            self.undo_of is None
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
            "renamed_root": self.renamed_root(),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Per-mod concurrency limits (``[run] max_concurrent`` in the manifest), created lazily.
        # Queuing a whole playlist would otherwise start every download at once, which makes
        # YouTube throttle the burst and reject some requests with HTTP 403.
        self._slots: dict[str, threading.BoundedSemaphore] = {}

    def _slot_for(self, mod: Mod) -> Optional[threading.BoundedSemaphore]:
        limit = mod.manifest.max_concurrent
        if limit <= 0:
            return None
        with self._lock:
            slot = self._slots.get(mod.id)
            if slot is None:
                slot = self._slots[mod.id] = threading.BoundedSemaphore(limit)
            return slot

    @staticmethod
    def _acquire_slot(slot: threading.BoundedSemaphore, job: Job) -> bool:
        """Block until a slot is free; False if the job was cancelled while waiting."""
        while not job.cancel_event.is_set():
            if slot.acquire(timeout=0.25):
                return True
        return False

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def _start(self, job: Job) -> None:
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

    def create(
        self,
        command: str,
        params: dict[str, Any],
        *,
        file_logging: bool = True,
    ) -> Job:
        validated = validate_params(command, params)
        job = Job(
            id=str(uuid.uuid4()),
            command=command,
            file_logging=file_logging,
            params=validated.model_dump(),
        )
        self._start(job)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.status not in ("queued", "running"):
            return False
        job.cancel_event.set()
        mod = registry.get(job.command)
        cooperative = mod is not None and mod.manifest.cancel == "cooperative"
        if not cooperative:
            job.status = "cancelled"
            job.finished_at = utc_now_iso()
            job.emit("status", {"status": "cancelled"})
            job.events.put(None)
        return True

    def undo_job(self, source_job_id: str, *, file_logging: bool = True) -> Job:
        with self._lock:
            source = self._jobs.get(source_job_id)
        if source is None:
            raise KeyError("Job not found")
        if source.undo_of is not None:
            raise ValueError("Only apply jobs can be undone")
        if source.status != "completed":
            raise ValueError("Job has not completed")
        if source.undo_used:
            raise ValueError("This job has already been undone")
        if not source.undo_manifest:
            raise ValueError("Nothing to undo (preview run or no files changed)")

        job = Job(
            id=str(uuid.uuid4()),
            command=source.command,
            file_logging=file_logging,
            undo_of=source_job_id,
        )
        self._start(job)
        return job

    def _status_payload(self, job: Job) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": job.status,
            "error": job.error,
            "exit_code": job.exit_code,
            "undo_available": job.undo_available(),
            "undo_used": job.undo_used,
            "undo_op_count": job.undo_op_count(),
            "renamed_root": job.renamed_root(),
        }
        if job.undo_of and job.status == "completed":
            payload["undo_source_job_id"] = job.undo_of
            payload["source_undo_used"] = True
        return payload

    def _run_job(self, job: Job) -> None:
        mod = registry.get(job.command)
        slot = self._slot_for(mod) if mod is not None else None
        holds_slot = False
        if slot is not None:
            holds_slot = self._acquire_slot(slot, job)
            if not holds_slot:
                job.status = "cancelled"
                job.finished_at = utc_now_iso()
                job.emit("status", self._status_payload(job))
                job.events.put(None)
                return

        job.status = "running"
        job.started_at = utc_now_iso()
        job.emit("status", {"status": "running"})

        config.FILE_LOGGING_ENABLED = job.file_logging

        def on_log(message: str, levelno: int) -> None:
            job.emit("log", {"message": message, "level": levelno})

        def on_progress(payload: dict) -> None:
            job.emit("progress", payload)

        def on_result(payload: dict) -> None:
            job.add_result(payload)

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
            if mod is None:
                raise ModError(f"Mod '{job.command}' is no longer available.")
            ctx = ModContext(
                mod.id,
                job_id=job.id,
                cancel_event=job.cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                on_result=on_result,
            )
            if job.undo_of:
                self._run_undo(job, mod, ctx)
            else:
                self._run_mod(job, mod, ctx)
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
        except ModCancelled:
            job.status = "cancelled"
            job.exit_code = None
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.exit_code = 1
            logging.getLogger(__name__).exception("Job %s failed", job.id)
            job.emit("log", {"message": f"Error: {exc}", "level": logging.ERROR})
        finally:
            if holds_slot and slot is not None:
                slot.release()
            detach_log_callback(root, callback_handler)
            set_active_hooks(None)
            if mod is not None and mod.manifest.loggers:
                close_log_handlers(*mod.manifest.loggers)
            if job.status in ("completed", "failed", "cancelled"):
                job.finished_at = utc_now_iso()
                job.emit("status", self._status_payload(job))
            job.events.put(None)

    def _run_mod(self, job: Job, mod: Mod, ctx: ModContext) -> None:
        if job.cancel_event.is_set():
            job.status = "cancelled"
            return
        run = mod.run_fn()
        run(dict(job.params or {}), ctx)
        if mod.manifest.undo and ctx.undo_manifest:
            job.undo_manifest = ctx.undo_manifest

    def _run_undo(self, job: Job, mod: Mod, ctx: ModContext) -> None:
        source = self.get(job.undo_of or "")
        if source is None:
            raise ValueError(f"Source job not found: {job.undo_of}")
        if not source.undo_manifest:
            raise ValueError("Source job has no undo manifest")
        if source.undo_used:
            raise ValueError("Already undone")
        undo = mod.undo_fn()
        if undo is None:
            raise ModError(f"Mod '{mod.id}' does not support undo.")

        result = undo(source.undo_manifest, ctx) or {}
        restored = int(result.get("restored", 0))
        failed = int(result.get("failed", 0))
        skipped = int(result.get("skipped", 0))
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


# Module-level singleton used by the FastAPI app.
job_manager = JobManager()
