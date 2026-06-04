"""YouTube / yt-dlp downloads (CLI and GUI)."""

import argparse
import logging
import shutil
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from .logging_setup import close_log_handlers, setup_simple_logging
from .progress import get_active_hooks


class _YtdlpLogger:
    """Adapter so yt-dlp's internal messages flow into our standard logger."""

    def __init__(self, logger: logging.Logger, prefix: str = "") -> None:
        self._log = logger
        self._prefix = (prefix + " ") if prefix else ""

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        self._log.info("%s%s", self._prefix, msg)

    def info(self, msg: str) -> None:
        self._log.info("%s%s", self._prefix, msg)

    def warning(self, msg: str) -> None:
        self._log.warning("%s%s", self._prefix, msg)

    def error(self, msg: str) -> None:
        self._log.error("%s%s", self._prefix, msg)


class DownloadCancelled(Exception):
    """Raised to abort an in-progress GUI download cleanly."""


def ytdlp_progress_payload(d: dict) -> dict:
    """Normalize a yt-dlp progress-hook dict for :data:`LogHooks.on_progress`."""
    info = d.get("info_dict") or {}
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    done = d.get("downloaded_bytes") or 0
    return {
        "status": d.get("status"),
        "downloaded": done,
        "total": total,
        "pct": (done * 100.0 / total) if total else None,
        "speed": d.get("speed"),
        "eta": d.get("eta"),
        "filename": d.get("filename", ""),
        "title": info.get("title") or "",
        "playlist_index": info.get("playlist_index"),
        "n_entries": info.get("n_entries"),
    }


def make_ytdlp_progress_hook(logger: Optional[logging.Logger] = None):
    """Build a yt-dlp progress hook using active :class:`LogHooks` or *logger*."""
    last_logged = {"pct": -10}

    def hook(d: dict) -> None:
        payload = ytdlp_progress_payload(d)
        hooks = get_active_hooks()
        if hooks.on_progress is not None:
            try:
                hooks.on_progress(payload)
            except Exception:
                pass
            return
        if logger is None:
            return
        status = payload.get("status")
        if status == "downloading":
            pct = payload.get("pct")
            if pct is not None and pct >= last_logged["pct"] + 10:
                last_logged["pct"] = int(pct) - (int(pct) % 10)
                idx, count = payload.get("playlist_index"), payload.get("n_entries")
                where = f"[{idx}/{count}] " if idx and count else ""
                done = payload.get("downloaded") or 0
                logger.info("%sDownloading... %d%% (%.1f MB)", where, int(pct), done / 1_048_576)
        elif status == "finished":
            last_logged["pct"] = -10
            logger.info(
                "Download complete, post-processing: %s",
                Path(payload.get("filename", "")).name,
            )

    return hook


def _youtube_outtmpl(output_dir: Path, playlist: bool, no_playlist_index: bool) -> str:
    if playlist:
        if no_playlist_index:
            return str(output_dir / "%(playlist_title|Playlist)s" / "%(title)s.%(ext)s")
        return str(
            output_dir / "%(playlist_title|Playlist)s" / "%(playlist_index|0)03d - %(title)s.%(ext)s"
        )
    return str(output_dir / "%(title)s.%(ext)s")


def _youtube_js_runtimes(logger: Optional[logging.Logger] = None) -> dict:
    js_runtimes = {
        name: {}
        for name, exe in (
            ("deno", "deno"),
            ("node", "node"),
            ("bun", "bun"),
            ("quickjs", "qjs"),
        )
        if shutil.which(exe)
    }
    if logger is not None:
        if js_runtimes:
            logger.info("JavaScript runtime(s) for YouTube extraction: %s", ", ".join(js_runtimes))
        else:
            logger.warning(
                "No JavaScript runtime (deno/node/bun/quickjs) found on PATH. YouTube "
                "extraction is degraded and may fail with 'This video is not available'. "
                "Install Node.js or Deno to fix this."
            )
    return js_runtimes


def _youtube_format_opts(
    out_format: str,
    video_quality: str,
    audio_bitrate: int,
    logger: Optional[logging.Logger] = None,
) -> dict:
    opts: dict = {}
    if out_format == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(audio_bitrate),
            }
        ]
        if logger is not None:
            logger.info("Audio bitrate: %d kbps", audio_bitrate)
    else:
        if video_quality == "best":
            opts["format"] = (
                "bv*[vcodec^=avc1]+ba[acodec^=mp4a]"
                "/bv*[ext=mp4]+ba[ext=m4a]"
                "/b[ext=mp4]"
                "/bv*+ba/b"
            )
        else:
            h = video_quality
            if int(h) <= 1080:
                opts["format"] = (
                    f"bv*[vcodec^=avc1][height<=?{h}]+ba[acodec^=mp4a]"
                    f"/bv*[ext=mp4][height<=?{h}]+ba[ext=m4a]"
                    f"/b[ext=mp4][height<=?{h}]"
                    f"/bv*[height<=?{h}]+ba/b[height<=?{h}]"
                    f"/bv*+ba/b"
                )
            else:
                opts["format"] = (
                    f"bv*[ext=mp4][height<=?{h}]+ba[ext=m4a]"
                    f"/bv*[height<=?{h}]+ba[acodec^=mp4a]"
                    f"/bv*[height<=?{h}]+ba/b[height<=?{h}]"
                    f"/bv*+ba/b"
                )
            if logger is not None:
                logger.info("Max video height: %sp", h)
        opts["merge_output_format"] = "mp4"
    return opts


def download_url(
    *,
    url: str,
    output_dir: Path,
    out_format: str = "mp4",
    video_quality: str = "best",
    audio_bitrate: int = 192,
    playlist: bool = False,
    no_playlist_index: bool = False,
    progress_callback: Optional[Callable[[dict], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    tag: str = "",
) -> Optional[int]:
    """Download a URL with optional progress callbacks and cancellation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is not installed. Install it with: pip install yt-dlp "
            "(or: pip install -e .)."
        ) from exc

    try:
        from yt_dlp.utils import DownloadCancelled as _YtCancel  # type: ignore
    except Exception:
        _YtCancel = DownloadCancelled

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install ffmpeg (it is needed to merge "
            "video+audio and to create MP3 files)."
        )

    logger_name = f"youtube_download_{tag or url}"
    logger = setup_simple_logging(logger_name, output_dir / "download.log")
    prefix = (tag + " ") if tag else ""
    logger.info("%sDownloading %s as %s", prefix, url, out_format.upper())

    def progress_hook(d: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _YtCancel()
        if progress_callback is None:
            return
        try:
            progress_callback(ytdlp_progress_payload(d))
        except Exception:
            pass

    ydl_opts: dict = {
        "outtmpl": _youtube_outtmpl(output_dir, playlist, no_playlist_index),
        "noplaylist": not playlist,
        "ffmpeg_location": ffmpeg_path,
        "progress_hooks": [progress_hook],
        "logger": _YtdlpLogger(logger, prefix=tag),
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": playlist,
        "js_runtimes": _youtube_js_runtimes(logger),
    }
    ydl_opts.update(_youtube_format_opts(out_format, video_quality, int(audio_bitrate), logger))

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([url])
    except _YtCancel:
        logger.info("%sDownload cancelled.", prefix)
        raise DownloadCancelled()
    except DownloadCancelled:
        logger.info("%sDownload cancelled.", prefix)
        raise
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            logger.info("%sDownload cancelled.", prefix)
            raise DownloadCancelled()
        logger.error("%sDownload failed: %s", prefix, exc)
        raise RuntimeError(str(exc)) from exc
    finally:
        close_log_handlers(logger_name)

    if ret and not playlist:
        raise RuntimeError(f"yt-dlp reported one or more errors (exit code {ret}).")
    logger.info("%sDone.", prefix)
    return ret


def run_download(args: argparse.Namespace) -> None:
    """CLI entry point for YouTube downloads."""
    url: str = args.url
    output_dir: Path = args.output
    out_format: str = args.format
    video_quality: str = args.video_quality
    audio_bitrate: int = int(args.audio_bitrate)
    playlist: bool = bool(getattr(args, "playlist", False))
    no_playlist_index: bool = bool(getattr(args, "no_playlist_index", False))

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Could not create output folder '{output_dir}': {exc}", file=sys.stderr)
        sys.exit(1)

    logger = setup_simple_logging("youtube_download", output_dir / "download.log")
    logger.info("Downloading %s as %s", url, out_format.upper())
    logger.info("Output folder: %s", output_dir)
    logger.info("Playlist mode: %s", "on" if playlist else "off (single video)")

    try:
        import yt_dlp
    except ImportError:
        logger.error(
            "yt-dlp is not installed. Install it with: pip install yt-dlp "
            "(or: pip install -e .)."
        )
        sys.exit(1)

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        logger.error(
            "ffmpeg not found on PATH. Install ffmpeg (it is needed to merge "
            "video+audio and to create MP3 files)."
        )
        sys.exit(1)

    ydl_opts: dict = {
        "outtmpl": _youtube_outtmpl(output_dir, playlist, no_playlist_index),
        "noplaylist": not playlist,
        "ffmpeg_location": ffmpeg_path,
        "progress_hooks": [make_ytdlp_progress_hook(logger)],
        "logger": _YtdlpLogger(logger),
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": playlist,
        "js_runtimes": _youtube_js_runtimes(logger),
    }
    ydl_opts.update(_youtube_format_opts(out_format, video_quality, audio_bitrate, logger))

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ret = ydl.download([url])
    except Exception as exc:
        logger.error("Download failed: %s", exc)
        sys.exit(1)

    if ret:
        if playlist:
            logger.warning("Finished with some playlist items skipped (yt-dlp exit code %s).", ret)
        else:
            logger.error("yt-dlp reported one or more errors (exit code %s).", ret)
            sys.exit(1)

    logger.info("Done.")
