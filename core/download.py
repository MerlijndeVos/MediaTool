"""YouTube / yt-dlp downloads (CLI and GUI)."""

import argparse
import logging
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from .log_storage import operation_log_path
from .logging_setup import close_log_handlers, setup_simple_logging
from .progress import get_active_hooks

_INVALID_WIN_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _user_output_stem(name: str) -> str:
    """Keep user-provided spacing; drop only characters Windows paths cannot contain."""
    stem = _INVALID_WIN_PATH_CHARS.sub("", name.strip()).rstrip(". ")
    return stem or "download"


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


def _download_target_dirs(
    output_dir: Path,
    *,
    playlist_subdir: Optional[str] = None,
) -> list[Path]:
    dirs = [output_dir]
    if playlist_subdir:
        dirs.append(output_dir / _user_output_stem(playlist_subdir))
    return dirs


def _cleanup_cancelled_download(
    tracked: set[Path],
    dirs: list[Path],
    *,
    output_name: Optional[str] = None,
    playlist_index: Optional[int] = None,
    no_playlist_index: bool = False,
    logger: Optional[logging.Logger] = None,
    prefix: str = "",
) -> None:
    """Remove partial yt-dlp artifacts left behind after a cancelled download."""
    candidates: set[Path] = set()
    for path in tracked:
        candidates.add(path)
        part = Path(f"{path}.part")
        if part != path:
            candidates.add(part)

    stem_prefix: Optional[str] = None
    if output_name:
        stem = _user_output_stem(output_name)
        if playlist_index is not None and not no_playlist_index:
            stem_prefix = f"{playlist_index:03d} - {stem}"
        else:
            stem_prefix = stem

    for directory in dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for pattern in ("*.part", "*.ytdl", "*.frag"):
            candidates.update(directory.glob(pattern))
        if stem_prefix:
            for path in directory.iterdir():
                if not path.is_file():
                    continue
                name = path.name
                if name == stem_prefix or name.startswith(f"{stem_prefix}."):
                    candidates.add(path)

    for path in sorted(candidates, key=lambda p: len(p.name), reverse=True):
        if not path.is_file():
            continue
        try:
            path.unlink()
            if logger is not None:
                logger.info("%sRemoved partial file: %s", prefix, path.name)
        except OSError as exc:
            if logger is not None:
                logger.warning("%sCould not remove %s: %s", prefix, path.name, exc)


def _youtube_outtmpl(
    output_dir: Path,
    playlist: bool,
    no_playlist_index: bool,
    *,
    output_name: Optional[str] = None,
    playlist_subdir: Optional[str] = None,
    playlist_index: Optional[int] = None,
) -> str:
    if output_name:
        stem = _user_output_stem(output_name)
        if playlist_subdir:
            sub = _user_output_stem(playlist_subdir)
            if playlist_index is not None and not no_playlist_index:
                return str(output_dir / sub / f"{playlist_index:03d} - {stem}.%(ext)s")
            return str(output_dir / sub / f"{stem}.%(ext)s")
        return str(output_dir / f"{stem}.%(ext)s")
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


def _entry_filesize(info: dict) -> Optional[int]:
    size = info.get("filesize") or info.get("filesize_approx")
    if size:
        return int(size)
    for fmt in info.get("formats") or []:
        fmt_size = fmt.get("filesize") or fmt.get("filesize_approx")
        if fmt_size:
            return int(fmt_size)
    return None


def probe_url(
    *,
    url: str,
    out_format: str = "mp4",
    video_quality: str = "best",
    audio_bitrate: int = 192,
) -> dict:
    """Extract metadata for a URL without downloading."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is not installed. Install it with: pip install yt-dlp "
            "(or: pip install -e .)."
        ) from exc

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        "extract_flat": "in_playlist",
        "js_runtimes": _youtube_js_runtimes(),
    }
    ydl_opts.update(_youtube_format_opts(out_format, video_quality, int(audio_bitrate)))

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise RuntimeError("Could not extract information for this URL.")

    entries_raw = info.get("entries")
    is_playlist = info.get("_type") == "playlist" or (
        entries_raw is not None and len(entries_raw) > 1
    )
    playlist_title = info.get("playlist_title") or info.get("title")

    entries: list[dict] = []
    if entries_raw:
        for idx, entry in enumerate(entries_raw, start=1):
            if entry is None:
                continue
            if entry.get("_type") == "url" and not entry.get("title"):
                continue
            entry_url = entry.get("webpage_url") or entry.get("url") or url
            title = entry.get("title") or f"Video {idx}"
            playlist_index = entry.get("playlist_index") or idx
            entries.append(
                {
                    "id": str(entry.get("id") or playlist_index),
                    "title": title,
                    "url": entry_url,
                    "duration": entry.get("duration"),
                    "filesize": _entry_filesize(entry),
                    "playlist_index": playlist_index,
                }
            )
    else:
        entries.append(
            {
                "id": str(info.get("id") or "1"),
                "title": info.get("title") or "Video",
                "url": info.get("webpage_url") or url,
                "duration": info.get("duration"),
                "filesize": _entry_filesize(info),
                "playlist_index": 1,
            }
        )
        is_playlist = False

    if not entries:
        raise RuntimeError("No downloadable videos found at this URL.")

    return {
        "url": url,
        "is_playlist": is_playlist,
        "playlist_title": playlist_title if is_playlist else None,
        "entries": entries,
    }


def download_url(
    *,
    url: str,
    output_dir: Path,
    out_format: str = "mp4",
    video_quality: str = "best",
    audio_bitrate: int = 192,
    playlist: bool = False,
    no_playlist_index: bool = False,
    output_name: Optional[str] = None,
    playlist_subdir: Optional[str] = None,
    playlist_index: Optional[int] = None,
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
    logger = setup_simple_logging(logger_name, operation_log_path("download"))
    prefix = (tag + " ") if tag else ""
    logger.info("%sDownloading %s as %s", prefix, url, out_format.upper())

    tracked_paths: set[Path] = set()
    target_dirs = _download_target_dirs(output_dir, playlist_subdir=playlist_subdir)
    cancelled = False

    def progress_hook(d: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _YtCancel()
        for key in ("filename", "tmpfilename"):
            value = d.get(key)
            if value:
                tracked_paths.add(Path(value))
        if progress_callback is None:
            return
        try:
            progress_callback(ytdlp_progress_payload(d))
        except Exception:
            pass

    def handle_cancel() -> None:
        nonlocal cancelled
        if cancelled:
            return
        cancelled = True
        logger.info("%sDownload cancelled.", prefix)
        _cleanup_cancelled_download(
            tracked_paths,
            target_dirs,
            output_name=output_name,
            playlist_index=playlist_index,
            no_playlist_index=no_playlist_index,
            logger=logger,
            prefix=prefix,
        )

    single_item = output_name is not None or not playlist
    ydl_opts: dict = {
        "restrictfilenames": False,
        "windowsfilenames": False,
        "outtmpl": _youtube_outtmpl(
            output_dir,
            playlist and not output_name,
            no_playlist_index,
            output_name=output_name,
            playlist_subdir=playlist_subdir,
            playlist_index=playlist_index,
        ),
        "noplaylist": single_item,
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
        handle_cancel()
        raise DownloadCancelled()
    except DownloadCancelled:
        handle_cancel()
        raise
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            handle_cancel()
            raise DownloadCancelled()
        logger.error("%sDownload failed: %s", prefix, exc)
        raise RuntimeError(str(exc)) from exc
    finally:
        close_log_handlers(logger_name)

    if cancel_event is not None and cancel_event.is_set():
        handle_cancel()
        raise DownloadCancelled()

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

    logger = setup_simple_logging("youtube_download", operation_log_path("download"))
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
        "restrictfilenames": False,
        "windowsfilenames": False,
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
