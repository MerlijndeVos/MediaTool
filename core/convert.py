"""Batch conversion, trimming and stitching of video files.

Per the migration plan this module groups the three closely-related ffmpeg
pipelines:

* ``run_convert`` - batch format conversion with folder mirroring (DV->MP4, ...)
* ``run_trim``    - cut seconds off the start and/or end of a video
* ``run_stitch``  - join several videos end-to-end into one
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import DEFAULT_CRF, DEFAULT_X264_PRESET
from .logging_setup import setup_logging, setup_simple_logging
from .naming import generate_unique_name, parse_dutch_name_from_stem, sanitize_filename
from .paths import ext_path, make_dirs, move_path, path_exists
from .probe import get_media_duration, has_audio_stream, is_valid_output, parse_time_to_seconds
from .tools import (
    build_nvenc_video_args,
    build_x264_video_args,
    detect_nvenc_support,
    ensure_tools_available,
)


# =====================================================================
# Convert mode: batch format conversion (DV -> MP4, AVI -> MKV, ...)
# =====================================================================


def build_ffmpeg_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    video_args: List[str],
    deinterlace: bool,
    output_format: str,
) -> List[str]:
    # Archive-friendly re-encode: optional bwdif deinterlace (good for DV),
    # preserve SAR/DAR, yuv420p, all audio re-encoded to AAC 256k.
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",  # Overwrite output if re-encoding corrupt/incomplete file
        "-i",
        str(input_path),
    ]
    # Video filter (only when deinterlacing) and pixel format
    if deinterlace:
        cmd += ["-vf", "bwdif=mode=send_field"]
    cmd += ["-pix_fmt", "yuv420p"]
    # Video encoder
    cmd += video_args
    # Audio: include all audio streams if present
    cmd += [
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-c:a",
        "aac",
        "-b:a",
        "256k",
    ]
    # +faststart relocates the moov atom for progressive playback; it only
    # applies to MP4/MOV containers (Matroska ignores/rejects it).
    if output_format in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_path)]
    return cmd


def process_single_file(
    src_path: Path,
    input_root: Path,
    output_root: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    video_args: List[str],
    output_ext: str,
    deinterlace: bool,
    output_format: str,
    dry_run: bool,
    used_names_by_dir: Dict[Path, Set[str]],
    logger: logging.Logger,
    failure_logger: logging.Logger,
) -> Tuple[str, Optional[Path], Path]:
    """
    Process one source file.

    Returns (status, output_path_or_None, rel_dir).
    status: 'converted', 'skipped_existing', 'error', 'dry_run'
    """
    rel_path = src_path.relative_to(input_root)
    rel_dir = rel_path.parent
    dest_dir = output_root / rel_dir

    stem = src_path.stem
    dutch_name = parse_dutch_name_from_stem(stem)

    if dutch_name is None:
        base_stem = sanitize_filename(stem)
    else:
        base_stem = dutch_name

    used_names = used_names_by_dir.setdefault(dest_dir, set())
    unique_name = generate_unique_name(dest_dir, base_stem, used_names, extension=output_ext)

    final_output = dest_dir / unique_name

    if dry_run:
        logger.info(
            "[DRY-RUN] Would convert '%s' -> '%s'",
            src_path,
            final_output,
        )
        return "dry_run", final_output, rel_dir

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Resume-safety: skip if output already exists and looks complete
    if final_output.is_file() and is_valid_output(ffprobe_bin, final_output):
        logger.info("Skipping existing complete output: %s", final_output)
        return "skipped_existing", final_output, rel_dir

    if final_output.is_file():
        logger.info("Existing output seems incomplete/corrupt, will re-encode: %s", final_output)

    cmd = build_ffmpeg_command(
        ffmpeg_bin, src_path, final_output, video_args, deinterlace, output_format
    )
    logger.info("Converting '%s' -> '%s'", src_path, final_output)
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
        logger.warning("Conversion interrupted by user (Ctrl+C) for file: %s", src_path)
        raise
    except Exception as exc:
        logger.error("Exception while running ffmpeg for '%s': %s", src_path, exc)
        failure_logger.error("Exception for '%s': %s", src_path, exc)
        return "error", None, rel_dir

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.splitlines()[-20:])
        logger.error("ffmpeg failed for '%s' (exit %s). See failures.log for details.", src_path, result.returncode)
        failure_logger.error(
            "ffmpeg failed for '%s' (exit %s). Last stderr lines:\n%s",
            src_path,
            result.returncode,
            stderr_tail,
        )
        return "error", None, rel_dir

    if not is_valid_output(ffprobe_bin, final_output):
        logger.error("Output from ffmpeg seems invalid or too short: %s", final_output)
        failure_logger.error("Invalid/too short output for '%s' at '%s'", src_path, final_output)
        return "error", None, rel_dir

    logger.info("Successfully converted to: %s", final_output)
    return "converted", final_output, rel_dir


def prune_output_directories(
    output_root: Path,
    src_dirs: Set[Path],
    dirs_with_errors: Set[Path],
    output_ext: str,
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    for rel_dir in sorted(src_dirs):
        if rel_dir in dirs_with_errors:
            logger.info(
                "Skipping prune for '%s' because there were conversion errors in this folder.",
                rel_dir,
            )
            continue
        out_dir = output_root / rel_dir
        if not out_dir.is_dir():
            continue
        for item in out_dir.iterdir():
            if item.is_file() and item.suffix.lower() != output_ext:
                if dry_run:
                    logger.info("[DRY-RUN] Would delete file not matching output format: %s", item)
                else:
                    try:
                        logger.info("Deleting file not matching output format (prune-output): %s", item)
                        item.unlink()
                    except Exception as exc:
                        logger.warning("Failed to delete '%s': %s", item, exc)


def build_useful_only_tree(
    output_root: Path,
    successful_outputs: List[Path],
    dry_run: bool,
    logger: logging.Logger,
) -> None:
    if not successful_outputs:
        logger.info("No successful outputs to copy for --copy-useful-only.")
        return

    useful_root = output_root.with_name(output_root.name + "_useful")
    logger.info(
        "Creating 'useful-only' tree with only MP4s at: %s",
        useful_root,
    )

    for out_path in successful_outputs:
        try:
            rel = out_path.relative_to(output_root)
        except ValueError:
            # Should not happen, but guard just in case
            logger.warning("Output path not under output root, skipping: %s", out_path)
            continue

        target = useful_root / rel
        if dry_run:
            logger.info("[DRY-RUN] Would copy '%s' -> '%s'", out_path, target)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(out_path, target)
        except Exception as exc:
            logger.warning("Failed to copy '%s' to '%s': %s", out_path, target, exc)


def run_convert(args: argparse.Namespace) -> None:
    input_root: Path = args.input
    output_root: Path = args.output

    # Normalize formats: accept "dv" or ".DV", store as lowercase extensions.
    input_format = getattr(args, "input_format", "dv").strip().lstrip(".").lower() or "dv"
    output_format = getattr(args, "output_format", "mp4").strip().lstrip(".").lower() or "mp4"
    input_ext = "." + input_format
    output_ext = "." + output_format

    # Resolve deinterlace mode: 'auto' enables it only for interlaced DV sources.
    deinterlace_mode = getattr(args, "deinterlace", "auto")
    if deinterlace_mode == "on":
        deinterlace = True
    elif deinterlace_mode == "off":
        deinterlace = False
    else:  # auto
        deinterlace = input_format == "dv"

    if not input_root.is_dir():
        print(f"Input root '{input_root}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    logger, failure_logger = setup_logging(output_root)

    logger.info("Input root: %s", input_root)
    logger.info("Output root: %s", output_root)
    logger.info("Converting: %s -> %s (deinterlace=%s)", input_ext, output_ext, deinterlace)
    logger.info("Options: use_gpu=%s, crf=%s, preset=%s, dry_run=%s, prune_output=%s, copy_useful_only=%s",
                args.use_gpu, args.crf, args.preset, args.dry_run, args.prune_output, args.copy_useful_only)

    ffmpeg_bin, ffprobe_bin = ensure_tools_available(logger)

    nvenc_available = detect_nvenc_support(ffmpeg_bin, logger)
    use_nvenc = False
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
        if use_nvenc:
            logger.info("Using NVENC (--use-gpu auto and NVENC is available).")
        else:
            logger.info("NVENC not available; falling back to libx264 (--use-gpu auto).")

    if use_nvenc:
        video_args = build_nvenc_video_args(ffmpeg_bin, logger)
    else:
        video_args = build_x264_video_args(args.crf, args.preset, logger)

    # Collect source files matching the requested input format (case-insensitive).
    src_files = sorted(
        [p for p in input_root.rglob("*") if p.is_file() and p.suffix.lower() == input_ext],
        key=lambda p: str(p).lower(),
    )
    if not src_files:
        logger.info("No %s files found under input root. Nothing to do.", input_ext)
        return

    logger.info("Found %d %s files to consider.", len(src_files), input_ext)

    src_dirs: Set[Path] = set()
    for f in src_files:
        rel_dir = f.relative_to(input_root).parent
        src_dirs.add(rel_dir)

    used_names_by_dir: Dict[Path, Set[str]] = {}
    dirs_with_errors: Set[Path] = set()
    successful_outputs: List[Path] = []

    total = len(src_files)
    converted = 0
    skipped_existing = 0
    errors = 0
    dry_count = 0

    try:
        for idx, src in enumerate(src_files, start=1):
            logger.info("Processing file %d/%d: %s", idx, total, src)
            status, out_path, rel_dir = process_single_file(
                src_path=src,
                input_root=input_root,
                output_root=output_root,
                ffmpeg_bin=ffmpeg_bin,
                ffprobe_bin=ffprobe_bin,
                video_args=video_args,
                output_ext=output_ext,
                deinterlace=deinterlace,
                output_format=output_format,
                dry_run=args.dry_run,
                used_names_by_dir=used_names_by_dir,
                logger=logger,
                failure_logger=failure_logger,
            )

            if status == "converted":
                converted += 1
                if out_path is not None:
                    successful_outputs.append(out_path)
            elif status == "skipped_existing":
                skipped_existing += 1
            elif status == "error":
                errors += 1
                dirs_with_errors.add(rel_dir)
            elif status == "dry_run":
                dry_count += 1
            else:
                errors += 1
                dirs_with_errors.add(rel_dir)
                logger.warning("Unknown status '%s' for file '%s'", status, src)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Partial progress may have been made.")

    logger.info(
        "Summary: total=%d, converted=%d, skipped_existing=%d, errors=%d, dry_run_files=%d",
        total,
        converted,
        skipped_existing,
        errors,
        dry_count,
    )

    # Prune files not matching the output format from output directories (if requested)
    if args.prune_output:
        logger.info("Prune-output mode enabled. Cleaning %s-mismatched files from successful folders.", output_ext)
        prune_output_directories(
            output_root=output_root,
            src_dirs=src_dirs,
            dirs_with_errors=dirs_with_errors,
            output_ext=output_ext,
            dry_run=args.dry_run,
            logger=logger,
        )

    # Build "useful-only" tree containing only converted MP4 files
    if args.copy_useful_only:
        if args.dry_run:
            logger.info(
                "--copy-useful-only requested but running in --dry-run mode; "
                "no actual copy operations will be performed."
            )
        build_useful_only_tree(
            output_root=output_root,
            successful_outputs=successful_outputs,
            dry_run=args.dry_run,
            logger=logger,
        )

    logger.info("Done.")


# =====================================================================
# Trim mode: cut seconds off the start and/or end of a video
# =====================================================================


def build_trim_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    start: float,
    duration: Optional[float],
    reencode: bool,
    output_format: str,
) -> List[str]:
    """Build an ffmpeg command that copies (or re-encodes) the segment of
    *input_path* starting at *start* seconds and lasting *duration* seconds.
    """
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]
    # Input seeking (-ss before -i) is fast; modern ffmpeg keeps it accurate
    # even when re-encoding by decoding from the prior keyframe and discarding.
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(input_path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]

    if reencode:
        cmd += [
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-crf",
            str(DEFAULT_CRF),
            "-preset",
            DEFAULT_X264_PRESET,
            "-map",
            "0:v",
            "-map",
            "0:a?",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
        ]
    else:
        # Copy every stream untouched (lossless, near-instant).
        cmd += ["-map", "0", "-c", "copy"]

    # +faststart helps progressive playback for MP4/MOV; Matroska ignores it.
    if output_format in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_path)]
    return cmd


def _cleanup_temp(path: Path, logger: logging.Logger) -> None:
    """Best-effort removal of a leftover temp file from a failed replace."""
    try:
        os.remove(ext_path(path))
    except OSError as exc:
        logger.warning("Could not remove temp file '%s': %s", path, exc)


def run_trim(args: argparse.Namespace) -> None:
    input_path: Path = args.input
    output_dir: Optional[Path] = args.output
    dry_run = bool(args.dry_run)
    reencode = bool(args.reencode)
    replace = bool(args.replace)
    recursive = not bool(args.no_recursive)
    input_ext = "." + str(args.input_format).lower().lstrip(".")

    # In replace mode the trimmed file overwrites the source, so an output
    # folder makes no sense; ignore it rather than silently doing both.
    if replace and output_dir is not None:
        print("--replace overwrites the source files, so --output is ignored.", file=sys.stderr)
        output_dir = None

    start = parse_time_to_seconds(args.trim_start)
    end_cut = parse_time_to_seconds(args.trim_end)
    if start is None:
        print(f"Invalid --trim-start value: '{args.trim_start}'.", file=sys.stderr)
        sys.exit(1)
    if end_cut is None:
        print(f"Invalid --trim-end value: '{args.trim_end}'.", file=sys.stderr)
        sys.exit(1)
    if start == 0 and end_cut == 0:
        print(
            "Nothing to do: both --trim-start and --trim-end are 0. "
            "Specify how much to cut off the start and/or end.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not path_exists(input_path):
        print(
            f"Input '{input_path}' does not exist. "
            f"(If this is a network drive, make sure it is connected/mapped.)",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build the list of source files (single file or folder scan).
    if input_path.is_dir():
        if recursive:
            candidates = input_path.rglob("*")
        else:
            candidates = input_path.glob("*")
        src_files = sorted(
            [p for p in candidates if p.is_file() and p.suffix.lower() == input_ext],
            key=lambda p: str(p).lower(),
        )
        log_dir = output_dir if output_dir is not None else input_path
    else:
        src_files = [input_path]
        log_dir = output_dir if output_dir is not None else input_path.parent

    log_path = (log_dir / "trim.log") if not dry_run else None
    logger = setup_simple_logging("video_trim", log_path)

    logger.info("Trim mode (%s).", "DRY-RUN" if dry_run else "APPLY")
    logger.info("Input: %s", input_path)
    logger.info(
        "Cutting %.3fs off the start and %.3fs off the end (%s, %s).",
        start,
        end_cut,
        "re-encode" if reencode else "stream copy",
        "replace originals" if replace else "keep originals",
    )

    if not src_files:
        logger.warning(
            "No '%s' files found under '%s'. Nothing to trim.", input_ext, input_path
        )
        return

    ffmpeg_bin, ffprobe_bin = ensure_tools_available(logger)
    if output_dir is not None:
        make_dirs(output_dir)

    trimmed = skipped = failed = 0
    for src in src_files:
        duration = get_media_duration(ffprobe_bin, src)
        if duration is None:
            logger.error("SKIP '%s': could not read its duration with ffprobe.", src)
            failed += 1
            continue

        keep = duration - start - end_cut
        if keep <= 0:
            logger.error(
                "SKIP '%s': trimming %.3fs + %.3fs leaves nothing of its %.3fs runtime.",
                src, start, end_cut, duration,
            )
            failed += 1
            continue

        # Only pass -t when we actually cut something off the end.
        seg_duration = keep if end_cut > 0 else None
        ext = src.suffix
        output_format = ext.lower().lstrip(".")

        # In replace mode ffmpeg cannot read and write the same file, so it
        # writes to a temp file alongside the source that is swapped in on
        # success. The final destination is the source itself.
        if replace:
            final_output = src
            write_target = src.with_name(f"{src.stem}.trimtmp{ext}")
        elif output_dir is not None:
            if input_path.is_dir():
                rel = src.relative_to(input_path)
                final_output = output_dir / rel
            else:
                final_output = output_dir / src.name
            write_target = final_output
        else:
            final_output = src.with_name(f"{src.stem} - trimmed{ext}")
            write_target = final_output

        if dry_run:
            action = "trim in place" if replace else "trim"
            logger.info(
                "[DRY-RUN] would %s '%s' -> '%s' (keep %.3fs of %.3fs)",
                action, src, final_output, keep, duration,
            )
            trimmed += 1
            continue

        if not replace and final_output.resolve() == src.resolve():
            logger.error("SKIP '%s': output would overwrite the source file.", src)
            failed += 1
            continue
        if not replace and final_output.is_file() and is_valid_output(ffprobe_bin, final_output):
            logger.info("Skipping existing complete output: %s", final_output)
            skipped += 1
            continue

        make_dirs(write_target.parent)
        cmd = build_trim_command(
            ffmpeg_bin, src, write_target, start, seg_duration, reencode, output_format
        )
        logger.info("Trimming '%s' -> '%s' (keep %.3fs of %.3fs)", src, final_output, keep, duration)
        logger.debug("ffmpeg command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except Exception as exc:
            logger.error("FAILED to trim '%s': %s", src, exc)
            failed += 1
            if replace and path_exists(write_target):
                _cleanup_temp(write_target, logger)
            continue

        if result.returncode != 0 or not is_valid_output(ffprobe_bin, write_target):
            stderr_tail = (result.stderr or "").strip().splitlines()[-5:]
            logger.error(
                "FAILED to trim '%s' (ffmpeg exit %s). %s",
                src, result.returncode, " | ".join(stderr_tail),
            )
            failed += 1
            if replace and path_exists(write_target):
                _cleanup_temp(write_target, logger)
            continue

        # Swap the validated temp file over the original only after success.
        if replace:
            try:
                move_path(write_target, final_output)
            except Exception as exc:
                logger.error("FAILED to replace original '%s' with trimmed file: %s", src, exc)
                failed += 1
                _cleanup_temp(write_target, logger)
                continue
            logger.info("Replaced original with trimmed version: %s", final_output)
        else:
            logger.info("Successfully trimmed to: %s", final_output)
        trimmed += 1

    logger.info("Trim summary: trimmed=%d, skipped=%d, failed=%d.", trimmed, skipped, failed)
    if dry_run and trimmed:
        logger.info("Dry-run complete. Re-run without --dry-run to write these files.")
    logger.info("Done.")


# =====================================================================
# Stitch mode: join two or more videos into one
# =====================================================================


def write_concat_list(parts: List[Path], directory: Path) -> Path:
    """Write an ffmpeg concat-demuxer list file for *parts* and return its path.

    Each line is ``file '<absolute path>'`` with single quotes escaped, as the
    concat demuxer requires.
    """
    fd, name = tempfile.mkstemp(prefix="stitch_", suffix=".txt", dir=str(directory))
    list_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for part in parts:
                abs_path = str(part.resolve())
                escaped = abs_path.replace("'", "'\\''")
                fh.write(f"file '{escaped}'\n")
    except Exception:
        try:
            os.remove(name)
        except OSError:
            pass
        raise
    return list_path


def build_concat_copy_command(
    ffmpeg_bin: str,
    list_file: Path,
    output_path: Path,
    output_format: str,
) -> List[str]:
    """Lossless join via the concat demuxer (no re-encode). Needs matching codecs."""
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
    ]
    if output_format in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_path)]
    return cmd


def build_concat_reencode_command(
    ffmpeg_bin: str,
    parts: List[Path],
    output_path: Path,
    with_audio: bool,
    output_format: str,
) -> List[str]:
    """Re-encode join via the concat filter; tolerates mismatched inputs."""
    cmd: List[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]
    for part in parts:
        cmd += ["-i", str(part)]

    n = len(parts)
    if with_audio:
        streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        filt = f"{streams}concat=n={n}:v=1:a=1[v][a]"
    else:
        streams = "".join(f"[{i}:v:0]" for i in range(n))
        filt = f"{streams}concat=n={n}:v=1:a=0[v]"

    cmd += ["-filter_complex", filt, "-map", "[v]"]
    if with_audio:
        cmd += ["-map", "[a]"]
    cmd += [
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-crf",
        str(DEFAULT_CRF),
        "-preset",
        DEFAULT_X264_PRESET,
    ]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "256k"]
    if output_format in ("mp4", "mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(output_path)]
    return cmd


def run_stitch(args: argparse.Namespace) -> None:
    inputs: List[Path] = list(args.input)
    output: Path = args.output
    dry_run = bool(args.dry_run)
    reencode = bool(args.reencode)
    recursive = not bool(args.no_recursive)
    input_ext = "." + str(args.input_format).lower().lstrip(".")

    # Resolve the ordered list of parts. A single folder is expanded to every
    # matching file in it (sorted); otherwise each --input is a part in order.
    if len(inputs) == 1 and inputs[0].is_dir():
        folder = inputs[0]
        candidates = folder.rglob("*") if recursive else folder.glob("*")
        parts = sorted(
            [p for p in candidates if p.is_file() and p.suffix.lower() == input_ext],
            key=lambda p: str(p).lower(),
        )
    else:
        parts = inputs

    missing = [p for p in parts if not p.is_dir() and not path_exists(p)]
    if missing:
        for p in missing:
            print(f"Input '{p}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if len(parts) < 2:
        print(
            "Need at least two videos to stitch. Pass --input twice (one per part), "
            "or point --input at a folder that contains multiple matching files.",
            file=sys.stderr,
        )
        sys.exit(1)

    log_path = (output.parent / "stitch.log") if not dry_run else None
    logger = setup_simple_logging("video_stitch", log_path)

    logger.info("Stitch mode (%s).", "DRY-RUN" if dry_run else "APPLY")
    logger.info("Joining %d parts (%s):", len(parts), "re-encode" if reencode else "stream copy")
    for i, p in enumerate(parts, 1):
        logger.info("  %d. %s", i, p)
    logger.info("Output: %s", output)

    if dry_run:
        logger.info("[DRY-RUN] would write the joined video to '%s'.", output)
        logger.info("Dry-run complete. Re-run without --dry-run to write the file.")
        logger.info("Done.")
        return

    if output.resolve() in {p.resolve() for p in parts}:
        logger.error("Output '%s' is also one of the inputs; choose a different output path.", output)
        sys.exit(1)

    ffmpeg_bin, ffprobe_bin = ensure_tools_available(logger)
    make_dirs(output.parent)
    output_format = output.suffix.lower().lstrip(".")

    if reencode:
        # Concat filter needs consistent audio handling: only mux audio when
        # every part has it, otherwise the joined result is video-only.
        audio_flags = [has_audio_stream(ffprobe_bin, p) for p in parts]
        with_audio = all(audio_flags)
        if not with_audio and any(audio_flags):
            logger.warning(
                "Some parts have no audio track; the stitched video will be silent "
                "(video-only) to keep the join consistent."
            )
        cmd = build_concat_reencode_command(ffmpeg_bin, parts, output, with_audio, output_format)
        list_file = None
    else:
        try:
            list_file = write_concat_list(parts, output.parent)
        except Exception as exc:
            logger.error("Could not write the concat list file: %s", exc)
            sys.exit(1)
        cmd = build_concat_copy_command(ffmpeg_bin, list_file, output, output_format)

    logger.info("Stitching %d parts -> '%s'", len(parts), output)
    logger.debug("ffmpeg command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    finally:
        if list_file is not None:
            _cleanup_temp(list_file, logger)

    if result.returncode != 0 or not is_valid_output(ffprobe_bin, output):
        stderr_tail = (result.stderr or "").strip().splitlines()[-8:]
        logger.error(
            "FAILED to stitch (ffmpeg exit %s). %s",
            result.returncode, " | ".join(stderr_tail),
        )
        if not reencode:
            logger.error(
                "Stream copy needs all parts to share the same codec/resolution. "
                "Try again with --reencode to join clips that differ."
            )
        sys.exit(1)

    logger.info("Successfully stitched %d parts into: %s", len(parts), output)
    logger.info("Done.")
