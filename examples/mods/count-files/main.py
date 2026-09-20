"""Count Files: an example mod. Counts files per extension and logs the result."""

from collections import Counter
from pathlib import Path


def run(params, ctx):
    root = Path(params["folder"])
    if not root.is_dir():
        raise RuntimeError(f"Not a folder: {root}")

    files = root.rglob("*") if params["recursive"] else root.glob("*")
    counts = Counter()
    total = 0
    for path in files:
        ctx.raise_if_cancelled()  # stop early (and mark the job cancelled) if the user cancels
        if path.is_file():
            counts[path.suffix.lower() or "(no extension)"] += 1
            total += 1

    ctx.log(f"{total} file(s) in {root}")
    for extension, count in counts.most_common(params["top"]):
        ctx.log(f"  {extension:<16} {count}")
    ctx.progress(1.0, "Done")
