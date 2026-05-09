from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from video_lecture_skill.models import KeyframeInfo, LectureNote, LectureSection, format_timestamp

logger = logging.getLogger("video_lecture_skill.frames")


def _sanitize_label(value: str, max_len: int = 40) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in value)[:max_len]


def _find_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path
    for candidate in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(candidate).exists():
            return candidate
    return None


def _format_ffmpeg_seek(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    remainder = total - hours * 3600
    minutes = int(remainder // 60)
    secs = remainder - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def extract_frame(
    video_path: str | Path,
    timestamp: float,
    output_path: str | Path,
    *,
    width: int = 1280,
    quality: int = 2,
) -> bool:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        logger.warning("ffmpeg not found, cannot extract frame")
        return False

    video = Path(video_path)
    if not video.exists():
        logger.warning("video file not found: %s", video)
        return False

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    seek = _format_ffmpeg_seek(timestamp)
    cmd = [
        ffmpeg,
        "-y",
        "-ss", seek,
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", str(quality),
    ]
    if width > 0:
        cmd.extend(["-vf", f"scale={width}:-1"])
    cmd.append(str(output))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ffmpeg frame extraction failed: %s", exc)
        return False

    if result.returncode != 0 or not output.exists():
        logger.warning(
            "ffmpeg frame extraction failed: returncode=%s stderr=%s",
            result.returncode,
            result.stderr.strip()[:200],
        )
        return False

    return True


def extract_keyframes_from_sections(
    video_path: str | Path,
    lecture: LectureNote,
    output_dir: str | Path,
    *,
    width: int = 1280,
    quality: int = 2,
    max_frames: int = 20,
    offset_seconds: float = 0.5,
) -> list[KeyframeInfo]:
    video = Path(video_path)
    if not video.exists():
        logger.warning("video file not found: %s", video)
        return []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamps: list[tuple[float, str]] = []
    for section in lecture.sections:
        if section.start is not None and section.start >= 0:
            timestamps.append((section.start, section.title))

    if not timestamps:
        return []

    timestamps = timestamps[:max_frames]

    keyframes: list[KeyframeInfo] = []
    for index, (ts, title) in enumerate(timestamps):
        seek_ts = max(0.0, ts + offset_seconds)
        safe_title = _sanitize_label(title)
        frame_filename = f"frame_{index + 1:03d}_{safe_title}.jpg"
        frame_path = out_dir / frame_filename

        success = extract_frame(
            video_path=video,
            timestamp=seek_ts,
            output_path=frame_path,
            width=width,
            quality=quality,
        )

        if success:
            keyframes.append(KeyframeInfo(
                timestamp=ts,
                timestamp_label=format_timestamp(ts),
                section_title=title,
                image_path=str(frame_path),
            ))
        else:
            logger.info("skipped keyframe for section %d (%s) at %s", index + 1, title, format_timestamp(ts))

    return keyframes


def extract_keyframes_from_timestamps(
    video_path: str | Path,
    timestamps: list[float],
    labels: list[str] | None = None,
    output_dir: str | Path = "",
    *,
    width: int = 1280,
    quality: int = 2,
    max_frames: int = 20,
    offset_seconds: float = 0.5,
) -> list[KeyframeInfo]:
    video = Path(video_path)
    if not video.exists():
        logger.warning("video file not found: %s", video)
        return []

    out_dir = Path(output_dir) if output_dir else video.parent / "keyframes"
    out_dir.mkdir(parents=True, exist_ok=True)

    effective_timestamps = timestamps[:max_frames]
    effective_labels = labels[:max_frames] if labels else None

    keyframes: list[KeyframeInfo] = []
    for index, ts in enumerate(effective_timestamps):
        seek_ts = max(0.0, ts + offset_seconds)
        label = effective_labels[index] if effective_labels and index < len(effective_labels) else f"Frame {index + 1}"
        safe_label = _sanitize_label(label)
        frame_filename = f"frame_{index + 1:03d}_{safe_label}.jpg"
        frame_path = out_dir / frame_filename

        success = extract_frame(
            video_path=video,
            timestamp=seek_ts,
            output_path=frame_path,
            width=width,
            quality=quality,
        )

        if success:
            keyframes.append(KeyframeInfo(
                timestamp=ts,
                timestamp_label=format_timestamp(ts),
                section_title=label,
                image_path=str(frame_path),
            ))

    return keyframes
