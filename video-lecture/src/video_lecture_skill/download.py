from __future__ import annotations

import logging
import math
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL

from video_lecture_skill.models import PipelineEvent, VideoInfo

logger = logging.getLogger("video_lecture_skill.download")

_BILIBILI_PATTERN = re.compile(r"(BV[0-9A-Za-z]+)", re.IGNORECASE)
_YOUTUBE_PATTERN = re.compile(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})")
_DOUYIN_PATTERN = re.compile(r"douyin\.com/video/(\d+)")


def normalize_video_url(value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    match = _BILIBILI_PATTERN.search(raw)
    if match:
        bvid = match.group(1)
        return f"https://www.bilibili.com/video/{bvid}", bvid
    match = _YOUTUBE_PATTERN.search(raw)
    if match:
        vid = match.group(1)
        return f"https://www.youtube.com/watch?v={vid}", vid
    match = _DOUYIN_PATTERN.search(raw)
    if match:
        vid = match.group(1)
        return raw, vid
    return raw, ""


def detect_platform(url: str) -> str:
    lower = url.lower()
    if "bilibili.com" in lower or "b23.tv" in lower:
        return "bilibili"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "douyin.com" in lower:
        return "douyin"
    return "generic"


def probe_video(url: str) -> VideoInfo:
    normalized_url, canonical_id = normalize_video_url(url)
    platform = detect_platform(normalized_url)
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(normalized_url, download=False)
    if not isinstance(info, dict):
        raise ValueError(f"Failed to probe video metadata from {normalized_url}")
    title = str(info.get("title") or canonical_id or normalized_url)
    thumbnail = str(info.get("thumbnail") or "")
    duration = float(info["duration"]) if info.get("duration") else None
    actual_id = str(info.get("id") or canonical_id or normalized_url)
    return VideoInfo(
        url=normalized_url,
        title=title,
        platform=platform,
        duration=duration,
        thumbnail=thumbnail,
        canonical_id=actual_id,
    )


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[\\/:*?\"<>|]+", "_", value).strip()
    return sanitized[:120] or "video_audio"


def download_audio(
    url: str,
    output_dir: Path,
    title: str | None = None,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> tuple[Path, VideoInfo]:
    normalized_url, _ = normalize_video_url(url)
    video_info = probe_video(normalized_url)
    safe_title = sanitize_filename(title or video_info.title or "video")
    output_template = str(output_dir / f"{safe_title}.%(ext)s")

    download_state = {"value": 20, "last_emit_time": 0.0}

    def _emit(stage: str, progress: int, message: str, payload: dict | None = None) -> None:
        if emit is not None:
            emit(PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {}))

    def progress_hook(data: dict) -> None:
        status = str(data.get("status") or "")
        if status == "downloading":
            now = time.monotonic()
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = int(data.get("downloaded_bytes") or 0)
            speed = data.get("speed")
            eta = data.get("eta")
            if total and downloaded:
                ratio = max(0.0, min(1.0, float(downloaded) / float(total)))
                progress = min(42, 22 + int(ratio * 20))
            else:
                progress = min(38, 22 + min(14, int(math.log10(max(downloaded, 1))) * 2))
            should_emit = (
                progress > download_state["value"]
                or now - download_state["last_emit_time"] >= 0.8
            )
            if should_emit:
                download_state["value"] = progress
                download_state["last_emit_time"] = now
                size_msg = f"已下载 {_format_bytes(downloaded)}"
                if total:
                    size_msg += f" / {_format_bytes(int(total))}"
                if speed:
                    size_msg += f" 速度 {_format_bytes(int(speed))}/s"
                _emit("downloading", progress, size_msg, {
                    "downloaded_bytes": downloaded,
                    "total_bytes": int(total) if total else None,
                    "speed": int(speed) if speed else None,
                })
        elif status == "finished":
            _emit("downloading", 44, "音频下载完成，正在提取音轨")

    def postprocessor_hook(data: dict) -> None:
        status = str(data.get("status") or "")
        if status == "started":
            _emit("downloading", 46, "正在提取 MP3 音频")
        elif status == "finished":
            _emit("downloading", 48, "音频提取完成")

    ffmpeg_path = shutil.which("ffmpeg")
    options: dict = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if ffmpeg_path:
        options["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

    _emit("downloading", 20, "正在连接音频源")
    with YoutubeDL(options) as ydl:
        ydl.download([normalized_url])

    candidates = sorted(output_dir.glob(f"{safe_title}.*"))
    if not candidates:
        raise RuntimeError("Audio download failed: no output file found")

    _emit("downloading", 48, "音频文件已就绪")
    return candidates[0], video_info


def download_video(
    url: str,
    output_dir: Path,
    title: str | None = None,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> tuple[Path, VideoInfo]:
    normalized_url, _ = normalize_video_url(url)
    video_info = probe_video(normalized_url)
    safe_title = sanitize_filename(title or video_info.title or "video")
    output_template = str(output_dir / f"{safe_title}_video.%(ext)s")

    def _emit(stage: str, progress: int, message: str, payload: dict | None = None) -> None:
        if emit is not None:
            emit(PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {}))

    ffmpeg_path = shutil.which("ffmpeg")
    options: dict = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
    }
    if ffmpeg_path:
        options["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

    _emit("downloading", 20, "正在下载视频文件（用于关键帧截取）")
    with YoutubeDL(options) as ydl:
        ydl.download([normalized_url])

    candidates = sorted(output_dir.glob(f"{safe_title}_video.*"))
    if not candidates:
        _emit("downloading", 48, "视频文件下载失败，关键帧截取将不可用")
        return Path(""), video_info

    _emit("downloading", 48, "视频文件已就绪")
    return candidates[0], video_info


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(max(value, 0))
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)}{units[unit_index]}"
    return f"{size:.1f}{units[unit_index]}"
