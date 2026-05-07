from __future__ import annotations

import logging
from typing import Literal
from uuid import uuid4

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.download import download_audio, normalize_video_url
from video_lecture_skill.errors import format_error_for_user
from video_lecture_skill.export import export_json, export_markdown, export_mermaid, export_transcript, export_to_files
from video_lecture_skill.lecture import generate_lecture
from video_lecture_skill.models import PipelineEvent, PipelineResult, TaskInput
from video_lecture_skill.transcribe import transcribe_audio
from video_lecture_skill.mindmap import generate_mindmap

logger = logging.getLogger("video_lecture_skill.service")


class VideoLectureService:
    def __init__(self, settings: SkillSettings | None = None):
        self.settings = settings or SkillSettings()
        self.settings.ensure_dirs()

    def process(
        self,
        url: str,
        title: str | None = None,
        language: str = "zh",
        wait: bool = True,
        output_dir: str | None = None,
    ) -> dict:
        task_id = uuid4().hex
        logger.info("process start task_id=%s url=%s", task_id, url)

        events: list[PipelineEvent] = []
        last_result: PipelineResult | None = None

        def on_event(event: PipelineEvent) -> None:
            events.append(event)
            logger.info("task_id=%s stage=%s progress=%s", task_id, event.stage, event.progress)

        try:
            task_input = TaskInput(
                url=url,
                title=title,
                language=language,
            )

            result = run_sync(
                task_input=task_input,
                settings=self.settings,
                emit=on_event,
            )
            last_result = result

            if output_dir:
                from pathlib import Path
                artifacts = export_to_files(result, Path(output_dir))
                result = result.model_copy(update={"artifacts": artifacts})

            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "lecture_md": export_markdown(result),
                "mindmap_mermaid": export_mermaid(result),
                "transcript": export_transcript(result),
                "result_json": export_json(result),
                "lecture_title": result.lecture.title,
                "sections_count": len(result.lecture.sections),
                "transcript_chars": len(result.transcription.transcript),
                "artifacts": result.artifacts,
                "events": [e.model_dump() for e in events],
            }

        except Exception as exc:
            logger.exception("process failed task_id=%s error=%s", task_id, exc)
            return {
                "success": False,
                "task_id": task_id,
                "status": "failed",
                "error": format_error_for_user(exc),
                "error_detail": str(exc),
                "events": [e.model_dump() for e in events],
            }

    def process_and_wait(
        self,
        url: str,
        title: str | None = None,
        language: str = "zh",
        timeout: int = 3600,
        output_dir: str | None = None,
    ) -> dict:
        return self.process(url, title, language, wait=True, output_dir=output_dir)

    def get_capabilities(self) -> dict:
        return {
            "supported_platforms": ["bilibili", "youtube", "douyin", "generic"],
            "transcribe_modes": ["local", "cloud"],
            "output_formats": ["markdown", "mermaid", "json", "html"],
            "features": [
                "video_download",
                "audio_transcription",
                "lecture_generation",
                "mindmap_generation",
                "multi_format_export",
                "progress_tracking",
                "sse_streaming",
            ],
            "limits": {
                "max_video_duration_seconds": 7200,
                "max_transcript_chars": 500000,
                "max_lecture_sections": 20,
            },
        }


def run_sync(
    task_input: TaskInput,
    settings: SkillSettings,
    emit: callable | None = None,
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

    _emit("transcribing", 50, f"开始语音转写（{settings.transcribe_mode.value}模式）")

    transcription = transcribe_audio(
        audio_path=audio_path,
        mode=task_input.transcribe_mode or settings.transcribe_mode,
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


def _export_results(task_dir, title, result):
    artifacts = {}

    transcript_path = task_dir / "transcript.txt"
    transcript_path.write_text(result.transcription.transcript, encoding="utf-8")
    artifacts["transcript_path"] = str(transcript_path)

    lecture_md = export_markdown(result)
    lecture_path = task_dir / "lecture.md"
    lecture_path.write_text(lecture_md, encoding="utf-8")
    artifacts["lecture_md_path"] = str(lecture_path)

    if result.mindmap.mermaid:
        mindmap_path = task_dir / "mindmap.mmd"
        mindmap_path.write_text(result.mindmap.mermaid, encoding="utf-8")
        artifacts["mindmap_mmd_path"] = str(mindmap_path)

    full_result_path = task_dir / "result.json"
    full_result_path.write_text(export_json(result), encoding="utf-8")
    artifacts["result_json_path"] = str(full_result_path)

    return artifacts
