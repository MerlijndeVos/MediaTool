"""Folder Report: an example mod for the declarative form (see MODDING.md).

``run`` walks a folder and reports with ``ctx.result(...)``; ``action_check_folder`` backs the
"Check folder" button. Nothing here changes a file.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

KINDS = {
    "video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".m4v", ".webm", ".ts", ".dv", ".vob"},
    "audio": {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"},
    "subtitle": {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"},
}
LABELS = {"video": "Video", "audio": "Audio", "image": "Images", "subtitle": "Subtitles", "other": "Everything else"}


def kind_of(path: Path) -> str:
    suffix = path.suffix.lower()
    return next((kind for kind, extensions in KINDS.items() if suffix in extensions), "other")


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def walk(root: Path, recursive: bool, include_hidden: bool = True):
    """Every file under *root* (the folder's own files only when not recursive)."""
    for path in root.rglob("*") if recursive else root.glob("*"):
        relative = path.relative_to(root).parts
        if not include_hidden and any(part.startswith(".") for part in relative):
            continue
        if path.is_file():
            yield path


def action_check_folder(params, ctx):
    """The "Check folder" button: a quick count, shown as a message."""
    root = Path(params["folder"])
    if not root.is_dir():
        return {"view": "message", "level": "error", "text": f"Not a folder: {root}"}
    count = total = 0
    for path in walk(root, params["recursive"]):
        count += 1
        total += path.stat().st_size
    return {"view": "message", "level": "success", "text": f"{count} file(s), {human_size(total)} in {root}."}


def run(params, ctx):
    root = Path(params["folder"])
    if not root.is_dir():
        raise RuntimeError(f"Not a folder: {root}")

    wanted = set(params["kinds"])
    minimum = params["min_size_mb"] * 1024 * 1024
    since = None
    if params.get("since"):
        since = datetime.combine(date.fromisoformat(params["since"]), time.min).timestamp()

    files = []  # (path, size, modified, kind)
    scanned = 0
    for path in walk(root, params["recursive"], params["include_hidden"]):
        ctx.raise_if_cancelled()  # stop early (and mark the job cancelled) if the user cancels
        scanned += 1
        if scanned % 500 == 0:
            ctx.progress(0.5, f"Looked at {scanned} files")
        try:
            info = path.stat()
        except OSError:
            continue
        kind = kind_of(path)
        if kind in wanted and info.st_size >= minimum and (since is None or info.st_mtime >= since):
            files.append((path, info.st_size, info.st_mtime, kind))

    ctx.log(f"{len(files)} of {scanned} file(s) match in {root}")
    if not files:
        ctx.result("message", level="warning", text="No files match these settings.")
        ctx.progress(1.0, "Done")
        return

    total = sum(size for _, size, _, _ in files)
    newest = max(files, key=lambda f: f[2])
    ctx.result(
        "counters",
        title="Overview",
        items={
            "Files": len(files),
            "Total size": human_size(total),
            "Average size": human_size(total / len(files)),
            "Last change": datetime.fromtimestamp(newest[2]).strftime("%Y-%m-%d"),
        },
    )

    by_kind: dict[str, list[int]] = {}
    for _, size, _, kind in files:
        by_kind.setdefault(kind, []).append(size)
    rows = [
        [LABELS[kind], len(sizes), human_size(sum(sizes)), f"{sum(sizes) * 100 / total:.0f}%"]
        for kind, sizes in sorted(by_kind.items(), key=lambda item: -sum(item[1]))
    ]
    ctx.result("table", title="By kind", columns=["Kind", "Files", "Size", "Share"], rows=rows)

    if params["show_files"]:
        order = {"size": lambda f: -f[1], "modified": lambda f: -f[2], "name": lambda f: f[0].name.lower()}
        chosen = sorted(files, key=order[params["sort_by"]])[: params["top"]]
        ctx.result(
            "files",
            title=f"Top {len(chosen)} by {params['sort_by']}",
            files=[{"path": str(path), "label": human_size(size)} for path, size, _, _ in chosen],
        )

    ctx.result(
        "markdown",
        text=(
            f"Report for `{root}`.\n\n"
            f"- {'Including' if params['recursive'] else 'Not including'} subfolders\n"
            f"- Kinds: {', '.join(LABELS[k] for k in LABELS if k in wanted)}\n"
            "- Nothing was changed: this mod only reads."
        ),
    )
    ctx.progress(1.0, "Done")
