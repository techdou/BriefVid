from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.download import download_audio, normalize_video_url
from video_lecture_skill.lecture import generate_lecture
from video_lecture_skill.mindmap import generate_mindmap
from video_lecture_skill.models import (
    PipelineEvent,
    PipelineResult,
    TaskInput,
    TranscribeMode,
    VideoInfo,
)
from video_lecture_skill.transcribe import transcribe_audio

logger = logging.getLogger("video_lecture_skill.pipeline")


def run_pipeline(
    task_input: TaskInput,
    settings: SkillSettings,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> PipelineResult:
    result = PipelineResult()

    def _emit(stage: str, progress: int, message: str, payload: dict | None = None) -> None:
        event = PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {})
        if emit is not None:
            emit(event)
        logger.info("pipeline stage=%s progress=%s message=%s", stage, progress, message)

    _emit("preparing", 5, "正在规范化视频链接")
    normalized_url, _ = normalize_video_url(task_input.url)

    task_dir = settings.tasks_dir / "latest"
    task_dir.mkdir(parents=True, exist_ok=True)

    _emit("downloading", 8, "正在探测视频信息")
    audio_path, video_info = download_audio(
        url=normalized_url,
        output_dir=task_dir,
        title=task_input.title,
        emit=_emit,
    )
    result.video_info = video_info

    transcribe_mode = task_input.transcribe_mode or settings.transcribe_mode
    _emit("transcribing", 50, f"开始语音转写（{transcribe_mode.value}模式）")

    transcription = transcribe_audio(
        audio_path=audio_path,
        mode=transcribe_mode,
        language=task_input.language,
        whisper_model=settings.whisper_model,
        whisper_device=settings.whisper_device,
        whisper_compute_type=settings.whisper_compute_type,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        duration=video_info.duration,
        emit=_emit,
    )
    result.transcription = transcription

    title = task_input.title or video_info.title or "视频"

    _emit("lecture", 86, "开始生成讲义")
    lecture = generate_lecture(
        transcription=transcription,
        title=title,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        chunk_target_chars=settings.summary_chunk_target_chars,
        chunk_overlap_segments=settings.summary_chunk_overlap_segments,
        chunk_concurrency=settings.summary_chunk_concurrency,
        chunk_retry_count=settings.summary_chunk_retry_count,
        emit=_emit,
    )
    result.lecture = lecture

    _emit("mindmap", 94, "开始生成思维导图")
    mindmap = generate_mindmap(
        transcription=transcription,
        lecture=lecture,
        title=title,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        emit=_emit,
    )
    result.mindmap = mindmap

    _emit("exporting", 97, "正在导出结果文件")
    artifacts = _export_results(task_dir, title, result)
    result.artifacts = artifacts

    _emit("completed", 100, "处理完成")
    logger.info("pipeline completed title=%s sections=%d", title, len(lecture.sections))
    return result


def _export_results(task_dir: Path, title: str, result: PipelineResult) -> dict[str, str]:
    artifacts: dict[str, str] = {}

    transcript_path = task_dir / "transcript.txt"
    transcript_path.write_text(result.transcription.transcript, encoding="utf-8")
    artifacts["transcript_path"] = str(transcript_path)

    lecture_md = _render_lecture_markdown(result)
    lecture_path = task_dir / "lecture.md"
    lecture_path.write_text(lecture_md, encoding="utf-8")
    artifacts["lecture_md_path"] = str(lecture_path)

    if result.mindmap.mermaid:
        mindmap_path = task_dir / "mindmap.mmd"
        mindmap_path.write_text(result.mindmap.mermaid, encoding="utf-8")
        artifacts["mindmap_mmd_path"] = str(mindmap_path)

    full_result_path = task_dir / "result.json"
    full_result_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts["result_json_path"] = str(full_result_path)

    return artifacts


def _render_lecture_markdown(result: PipelineResult) -> str:
    lecture = result.lecture
    lines: list[str] = []

    lines.append(f"# {lecture.title}")
    lines.append("")

    if lecture.overview:
        lines.append("## 概述")
        lines.append("")
        lines.append(lecture.overview)
        lines.append("")

    if lecture.prerequisites:
        lines.append("## 前置知识")
        lines.append("")
        for p in lecture.prerequisites:
            lines.append(f"- {p}")
        lines.append("")

    if lecture.sections:
        lines.append("## 讲义内容")
        lines.append("")
        for i, sec in enumerate(lecture.sections, 1):
            minutes = int(sec.start) // 60
            seconds = int(sec.start) % 60
            timestamp = f"{minutes:02d}:{seconds:02d}"
            lines.append(f"### {i}. {sec.title} `[{timestamp}]`")
            lines.append("")
            if sec.key_concepts:
                lines.append("**核心概念：** " + "、".join(sec.key_concepts))
                lines.append("")
            if sec.explanation:
                lines.append(sec.explanation)
                lines.append("")
            if sec.examples:
                lines.append("**示例：**")
                for ex in sec.examples:
                    lines.append(f"- {ex}")
                lines.append("")
            if sec.quiz:
                lines.append("**思考题：**")
                for q in sec.quiz:
                    lines.append(f"- {q}")
                lines.append("")

    if lecture.summary:
        lines.append("## 总结")
        lines.append("")
        lines.append(lecture.summary)
        lines.append("")

    if lecture.references:
        lines.append("## 延伸阅读")
        lines.append("")
        for r in lecture.references:
            lines.append(f"- {r}")
        lines.append("")

    if result.mindmap.mermaid:
        lines.append("## 思维导图")
        lines.append("")
        lines.append("```mermaid")
        lines.append(result.mindmap.mermaid)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
