from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import httpx

from video_lecture_skill.models import PipelineEvent, Segment, TranscriptionResult, TranscribeMode

logger = logging.getLogger("video_lecture_skill.transcribe")


def transcribe_audio(
    audio_path: Path,
    mode: TranscribeMode,
    language: str = "zh",
    whisper_model: str = "base",
    whisper_device: str = "cpu",
    whisper_compute_type: str = "int8",
    openai_api_key: str = "",
    openai_base_url: str = "",
    duration: float | None = None,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> TranscriptionResult:
    if mode == TranscribeMode.CLOUD:
        return _transcribe_cloud(audio_path, language, openai_api_key, openai_base_url, emit)
    return _transcribe_local(audio_path, language, whisper_model, whisper_device, whisper_compute_type, duration, emit)


def _emit(emit_fn: Callable[[PipelineEvent], None] | None, stage: str, progress: int, message: str, payload: dict | None = None) -> None:
    if emit_fn is not None:
        emit_fn(PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {}))


def _transcribe_local(
    audio_path: Path,
    language: str,
    model_name: str,
    device: str,
    compute_type: str,
    duration: float | None,
    emit: Callable[[PipelineEvent], None] | None,
) -> TranscriptionResult:
    _emit(emit, "transcribing", 52, f"正在加载转写模型 {model_name}", {"model": model_name, "device": device})

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install it with: pip install faster-whisper"
        ) from exc

    _emit(emit, "transcribing", 56, "开始转写音频内容")
    logger.info("local transcription start audio=%s model=%s device=%s", audio_path, model_name, device)

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    raw_segments, info = model.transcribe(str(audio_path), language=language, vad_filter=True)

    segments: list[Segment] = []
    transcript_lines: list[str] = []
    last_progress = 56

    for segment in raw_segments:
        seg = Segment(start=round(segment.start, 3), end=round(segment.end, 3), text=segment.text.strip())
        segments.append(seg)
        transcript_lines.append(f"[{_format_timestamp(seg.start)}] {seg.text}")

        if duration and duration > 0:
            progress = min(82, 56 + int((seg.end / duration) * 24))
        else:
            progress = min(82, 56 + min(24, len(segments)))

        if progress > last_progress:
            last_progress = progress
            _emit(emit, "transcribing", progress, f"正在转写，已识别 {len(segments)} 段")

    transcript = "\n".join(transcript_lines)
    if not transcript.strip():
        raise RuntimeError("Transcription produced empty output")

    _emit(emit, "transcribing", 84, f"转写完成，共识别 {len(segments)} 段")
    logger.info("local transcription finish segments=%d transcript_chars=%d", len(segments), len(transcript))

    return TranscriptionResult(
        transcript=transcript,
        segments=segments,
        language=info.language if hasattr(info, "language") else language,
        duration=duration or 0.0,
    )


def _transcribe_cloud(
    audio_path: Path,
    language: str,
    api_key: str,
    base_url: str,
    emit: Callable[[PipelineEvent], None] | None,
) -> TranscriptionResult:
    if not api_key:
        raise RuntimeError("OpenAI API key is required for cloud transcription mode")
    if not base_url:
        base_url = "https://api.openai.com/v1"

    _emit(emit, "transcribing", 52, "正在上传音频到云转写服务")
    logger.info("cloud transcription start audio=%s base_url=%s", audio_path, base_url)

    url = f"{base_url.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    with audio_path.open("rb") as audio_file:
        files = {"file": (audio_path.name, audio_file, "audio/mpeg")}
        data = {"model": "whisper-1", "language": language, "response_format": "verbose_json"}

        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()

    result = response.json()
    _emit(emit, "transcribing", 84, "云转写完成")

    segments: list[Segment] = []
    transcript_lines: list[str] = []
    for seg in result.get("segments", []):
        s = Segment(start=seg.get("start", 0), end=seg.get("end", 0), text=seg.get("text", "").strip())
        segments.append(s)
        transcript_lines.append(f"[{_format_timestamp(s.start)}] {s.text}")

    transcript = result.get("text", "\n".join(transcript_lines))
    if not transcript.strip():
        transcript = "\n".join(transcript_lines)

    return TranscriptionResult(
        transcript=transcript,
        segments=segments,
        language=result.get("language", language),
        duration=result.get("duration", 0.0),
    )


def _format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
