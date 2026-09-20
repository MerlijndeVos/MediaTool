"""Download: save URLs as MP4 or MP3 with yt-dlp (wraps ``core.download.download_url``).

Cancelling is cooperative (``[run] cancel = "cooperative"``): the download itself notices
the cancel event and stops, so the job is only marked cancelled once yt-dlp has let go.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from core.download import DownloadCancelled, download_url
from core.mods import ModCancelled


class Params(BaseModel):
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


def run(params, ctx):
    p = params

    def progress_cb(payload: dict) -> None:
        if ctx.cancelled():
            return
        ctx.progress(payload)

    try:
        download_url(
            url=p["url"],
            output_dir=Path(p["output"]),
            out_format=p["format"],
            video_quality=p["video_quality"],
            audio_bitrate=p["audio_bitrate"],
            playlist=p["playlist"],
            no_playlist_index=p["no_playlist_index"],
            output_name=p["output_name"],
            playlist_subdir=p["playlist_subdir"],
            playlist_index=p["playlist_index"],
            progress_callback=progress_cb,
            cancel_event=ctx.cancel_event,
            tag=ctx.job_id[:8],
        )
    except DownloadCancelled:
        raise ModCancelled() from None
    ctx.raise_if_cancelled()
