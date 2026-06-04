"""VTS mode: join DVD title-set VOBs into one file per title.

A DVD VIDEO_TS folder splits each title across ~1 GB segments named
VTS_<set>_<part>.VOB (part 0 is the title-set menu; parts 1..N are content).
This mode joins the content parts of each title set in order and writes one
output file per title -- by default a lossless MKV remux (stream copy), or a
H.264 re-encode with --reencode.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .config import RE_VTS_VOB
from .logging_setup import setup_logging
from .naming import generate_unique_name, sanitize_filename
from .probe import is_valid_output
from .tools import (
    build_nvenc_video_args,
    build_x264_video_args,
    detect_nvenc_support,
    ensure_tools_available,
)


@dataclass
class TitleSet:
    """A DVD title set: its disc name, source folder and ordered VOB parts."""
    disc_name: str
    source_dir: Path
    set_number: int
    parts: List[Path]            # content VOBs, ordered by part number
    total_size: int              # combined size of the parts, in bytes


def disc_name_for(source_dir: Path) -> str:
    """Best-effort DVD name for a folder holding VOBs.

    VOBs usually live in a 'VIDEO_TS' subfolder, so the disc name is its parent
    (e.g. '...\\My Movie\\VIDEO_TS' -> 'My Movie'). When the VOBs sit directly in
    a folder, that folder's name is used.
    """
    if source_dir.name.upper() == "VIDEO_TS":
        name = source_dir.parent.name or source_dir.name
    else:
        name = source_dir.name
    return sanitize_filename(name) or "DVD"


def discover_title_sets(input_root: Path, include_menus: bool) -> List[TitleSet]:
    """Find DVD title sets under input_root, grouping VOB parts per title set."""
    # Group by (containing directory, title-set number) -> {part_number: path}.
    groups: Dict[Tuple[str, int], Dict[int, Path]] = {}
    for p in input_root.rglob("*"):
        if not p.is_file():
            continue
        m = RE_VTS_VOB.match(p.name)
        if not m:
            continue
        set_no = int(m.group(1))
        part_no = int(m.group(2))
        if part_no == 0 and not include_menus:
            continue
        key = (os.path.normcase(str(p.parent)), set_no)
        groups.setdefault(key, {})[part_no] = p

    title_sets: List[TitleSet] = []
    for (_dir_key, set_no), parts_map in groups.items():
        ordered_parts = [parts_map[k] for k in sorted(parts_map)]
        source_dir = ordered_parts[0].parent
        total = 0
        for part in ordered_parts:
            try:
                total += part.stat().st_size
            except OSError:
                pass
        title_sets.append(
            TitleSet(
                disc_name=disc_name_for(source_dir),
                source_dir=source_dir,
                set_number=set_no,
                parts=ordered_parts,
                total_size=total,
            )
        )

    title_sets.sort(key=lambda t: (t.disc_name.lower(), str(t.source_dir).lower(), t.set_number))
    return title_sets


def build_vts_ffmpeg_command(
    ffmpeg_bin: str,
    parts: List[Path],
    output_path: Path,
    output_format: str,
    reencode: bool,
    video_args: List[str],
    deinterlace: bool,
) -> List[str]:
    """Build the ffmpeg command that joins VOB parts into a single output.

    The MPEG program-stream segments are concatenated with ffmpeg's ``concat:``
    protocol (valid for DVD VOBs), then either stream-copied (lossless remux) or
    re-encoded to H.264. Plain paths are used for the concat string because the
    Windows extended-length prefix is not understood by that protocol parser.
    """
    concat_input = "concat:" + "|".join(str(p) for p in parts)
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        # DVD VOBs can have discontinuous timestamps across segment boundaries
        # and several multiplexed streams; these flags make joining robust.
        "-fflags",
        "+genpts",
        "-analyzeduration",
        "100M",
        "-probesize",
        "100M",
        "-i",
        concat_input,
    ]

    if reencode:
        if deinterlace:
            cmd += ["-vf", "bwdif=mode=send_field"]
        cmd += ["-pix_fmt", "yuv420p"]
        cmd += video_args
        cmd += ["-map", "0:v", "-map", "0:a?", "-c:a", "aac", "-b:a", "256k"]
        # MKV can carry the original DVD (VobSub) subtitles; copy them through.
        if output_format == "mkv":
            cmd += ["-map", "0:s?", "-c:s", "copy"]
    else:
        # Lossless remux: copy video + audio (+ DVD subtitles for MKV) as-is.
        cmd += ["-map", "0:v", "-map", "0:a?"]
        if output_format == "mkv":
            cmd += ["-map", "0:s?"]
        cmd += ["-c", "copy"]

    if output_format in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_path)]
    return cmd


def run_vts(args: argparse.Namespace) -> None:
    input_root: Path = args.input
    output_root: Path = args.output

    output_format = getattr(args, "output_format", "mkv").strip().lstrip(".").lower() or "mkv"
    output_ext = "." + output_format
    reencode = bool(args.reencode)
    include_menus = bool(args.include_menus)
    min_bytes = max(0, int(args.min_mb)) * 1024 * 1024

    deinterlace_mode = getattr(args, "deinterlace", "auto")
    if deinterlace_mode == "off":
        deinterlace = False
    elif deinterlace_mode == "on":
        deinterlace = True
    else:  # auto -> DVD video is typically interlaced
        deinterlace = True

    if not input_root.is_dir():
        print(f"Input root '{input_root}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    logger, failure_logger = setup_logging(output_root)

    logger.info("VTS (DVD) mode.")
    logger.info("Input root : %s", input_root)
    logger.info("Output root: %s", output_root)
    logger.info(
        "Mode=%s, output=%s, include_menus=%s, min_mb=%s, dry_run=%s",
        "re-encode" if reencode else "remux (stream copy)",
        output_ext, include_menus, args.min_mb, args.dry_run,
    )

    ffmpeg_bin, ffprobe_bin = ensure_tools_available(logger)

    # Video encoder args are only needed for re-encode.
    video_args: List[str] = []
    if reencode:
        nvenc_available = detect_nvenc_support(ffmpeg_bin, logger)
        if args.use_gpu == "off":
            use_nvenc = False
            logger.info("GPU usage disabled (--use-gpu off). Using libx264.")
        elif args.use_gpu == "on":
            if not nvenc_available:
                logger.error("NVENC requested (--use-gpu on) but not available. Aborting.")
                sys.exit(1)
            use_nvenc = True
            logger.info("Using NVENC (forced by --use-gpu on).")
        else:  # auto
            use_nvenc = nvenc_available
            logger.info("Using %s (--use-gpu auto).", "NVENC" if use_nvenc else "libx264")
        video_args = (
            build_nvenc_video_args(ffmpeg_bin, logger)
            if use_nvenc
            else build_x264_video_args(args.crf, args.preset, logger)
        )
        logger.info("Re-encode deinterlace: %s", deinterlace)

    title_sets = discover_title_sets(input_root, include_menus)
    if not title_sets:
        logger.info("No DVD title-set VOBs (VTS_xx_x.VOB) found under input root. Nothing to do.")
        return

    # Count converted title sets per disc so single-title discs get a clean
    # '<disc>.mkv' name, while multi-title discs get '<disc> - Title NN'.
    eligible = [t for t in title_sets if t.total_size >= min_bytes]
    per_disc_count: Dict[str, int] = {}
    for t in eligible:
        per_disc_count[t.disc_name] = per_disc_count.get(t.disc_name, 0) + 1

    logger.info(
        "Found %d title set(s); %d above the %d MB threshold.",
        len(title_sets), len(eligible), args.min_mb,
    )

    used_names_by_dir: Dict[Path, Set[str]] = {}
    total = len(title_sets)
    converted = 0
    skipped_existing = 0
    skipped_small = 0
    errors = 0
    dry_count = 0

    try:
        for idx, ts in enumerate(title_sets, start=1):
            size_mb = ts.total_size / (1024 * 1024)
            label = f"{ts.disc_name} (title set {ts.set_number:02d}, {len(ts.parts)} part(s), {size_mb:.0f} MB)"

            if ts.total_size < min_bytes:
                logger.info("Skipping small title set below %d MB: %s", args.min_mb, label)
                skipped_small += 1
                continue

            if per_disc_count.get(ts.disc_name, 0) > 1:
                base_stem = f"{ts.disc_name} - Title {ts.set_number:02d}"
            else:
                base_stem = ts.disc_name

            used_names = used_names_by_dir.setdefault(output_root, set())
            unique_name = generate_unique_name(output_root, base_stem, used_names, extension=output_ext)
            final_output = output_root / unique_name

            logger.info("Processing title set %d/%d: %s", idx, total, label)
            for part in ts.parts:
                logger.info("    part: %s", part)

            if args.dry_run:
                logger.info("[DRY-RUN] Would join -> '%s'", final_output)
                dry_count += 1
                continue

            output_root.mkdir(parents=True, exist_ok=True)

            if final_output.is_file() and is_valid_output(ffprobe_bin, final_output):
                logger.info("Skipping existing complete output: %s", final_output)
                skipped_existing += 1
                continue
            if final_output.is_file():
                logger.info("Existing output seems incomplete/corrupt, will re-create: %s", final_output)

            cmd = build_vts_ffmpeg_command(
                ffmpeg_bin, ts.parts, final_output, output_format, reencode, video_args, deinterlace
            )
            logger.info("Joining -> '%s'", final_output)
            logger.debug("ffmpeg command: %s", " ".join(cmd))

            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            except KeyboardInterrupt:
                logger.warning("Conversion interrupted by user (Ctrl+C) for: %s", label)
                raise
            except Exception as exc:
                logger.error("Exception while running ffmpeg for '%s': %s", label, exc)
                failure_logger.error("Exception for '%s': %s", label, exc)
                errors += 1
                continue

            if result.returncode != 0:
                stderr_tail = "\n".join(result.stderr.splitlines()[-20:])
                logger.error("ffmpeg failed for '%s' (exit %s). See failures.log for details.", label, result.returncode)
                failure_logger.error(
                    "ffmpeg failed for '%s' (exit %s). Last stderr lines:\n%s",
                    label, result.returncode, stderr_tail,
                )
                errors += 1
                continue

            if not is_valid_output(ffprobe_bin, final_output):
                logger.error("Output from ffmpeg seems invalid or too short: %s", final_output)
                failure_logger.error("Invalid/too short output for '%s' at '%s'", label, final_output)
                errors += 1
                continue

            logger.info("Successfully created: %s", final_output)
            converted += 1

    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Partial progress may have been made.")

    logger.info(
        "Summary: title_sets=%d, converted=%d, skipped_existing=%d, skipped_small=%d, errors=%d, dry_run=%d",
        total, converted, skipped_existing, skipped_small, errors, dry_count,
    )
    if args.dry_run:
        logger.info("Dry-run complete. Re-run without --dry-run to perform these conversions.")
    logger.info("Done.")
