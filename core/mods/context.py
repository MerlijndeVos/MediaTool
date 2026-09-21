"""The ``ctx`` object handed to a mod's ``run(params, ctx)``."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Any, Callable, Optional, Sequence

from ..subprocess_utils import no_window_kwargs

LogCallback = Callable[[str, int], None]
ProgressCallback = Callable[[dict], None]


class ModCancelled(Exception):
    """Raise from a mod to end the job as cancelled (not failed)."""


class ModContext:
    """What a mod can do while it runs: log, report progress, honor cancel, find tools."""

    def __init__(
        self,
        mod_id: str,
        *,
        job_id: str = "",
        cancel_event: Optional[threading.Event] = None,
        on_log: Optional[LogCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        self.mod_id = mod_id
        self.job_id = job_id
        self.cancel_event = cancel_event or threading.Event()
        self._on_log = on_log
        self._on_progress = on_progress
        self._logger = logging.getLogger(f"toolbox.mod.{mod_id}")
        self._tools: tuple[str, str] | None = None
        self.undo_manifest: Optional[dict] = None

    def log(self, message: str, level: int = logging.INFO) -> None:
        """Write a line to the job log."""
        if self._on_log is not None:
            self._on_log(str(message), level)
        else:
            self._logger.log(level, "%s", message)

    def progress(self, value: float | dict, status: str | None = None) -> None:
        """Report progress: a fraction 0.0-1.0, or a full payload dict (``pct``, ``status``, ...)."""
        if self._on_progress is None:
            return
        if isinstance(value, dict):
            self._on_progress(value)
            return
        pct = max(0.0, min(1.0, float(value))) * 100.0
        payload: dict[str, Any] = {"pct": pct}
        if status:
            payload["status"] = status
        self._on_progress(payload)

    def cancelled(self) -> bool:
        """True once the user asked to cancel. Check it in loops and stop early."""
        return self.cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled():
            raise ModCancelled()

    def set_undo_manifest(self, manifest: Optional[dict]) -> None:
        """Store what :func:`undo` (if the mod defines one) needs to reverse this run."""
        self.undo_manifest = manifest or None

    def _ensure_tools(self) -> tuple[str, str]:
        if self._tools is None:
            from ..tools import ensure_tools_available

            self._tools = ensure_tools_available(self._logger)
        return self._tools

    @property
    def ffmpeg(self) -> str:
        """Path to ffmpeg (downloads it first if it is missing)."""
        return self._ensure_tools()[0]

    @property
    def ffprobe(self) -> str:
        """Path to ffprobe."""
        return self._ensure_tools()[1]

    def run(self, cmd: Sequence[str], *, cwd: str | None = None, check: bool = True) -> int:
        """Run a program (argument list, never a shell string), streaming its output to the log.

        Stops the program when the job is cancelled. Raises ``RuntimeError`` on a non-zero
        exit code unless ``check=False``.
        """
        if isinstance(cmd, (str, bytes)):
            raise TypeError("ctx.run() takes a list of arguments, not a string.")
        args = [str(c) for c in cmd]
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **no_window_kwargs(),
        )

        def watch() -> None:
            while proc.poll() is None:
                if self.cancel_event.wait(0.25):
                    proc.terminate()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.log(line)
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
        if self.cancelled():
            raise ModCancelled()
        if check and code != 0:
            raise RuntimeError(f"{args[0]} exited with code {code}")
        return code
