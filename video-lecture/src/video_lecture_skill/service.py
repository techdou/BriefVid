from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable
from uuid import uuid4

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.download import download_audio, normalize_video_url
from video_lecture_skill.errors import format_error_for_user
from video_lecture_skill.export import (
    export_json,
    export_markdown,
    export_mermaid,
    export_obsidian,
    export_obsidian_to_file,
    export_to_files,
    export_transcript,
)
from video_lecture_skill.frames import (
    extract_keyframes_from_sections,
    extract_keyframes_from_timestamps,
)
from video_lecture_skill.knowledge import KnowledgeAgent, KnowledgeStore
from video_lecture_skill.lecture import generate_lecture
from video_lecture_skill.models import (
    KeyframeInfo,
    KnowledgeAskResponse,
    KnowledgeChatHistoryItem,
    KnowledgeNetworkResponse,
    KnowledgeSearchResult,
    KnowledgeStatsResponse,
    PipelineEvent,
    PipelineResult,
    Segment,
    TaskInput,
    TagItem,
    TranscriptionResult,
    VideoTagRecord,
)
from video_lecture_skill.mindmap import generate_mindmap
from video_lecture_skill.tags import TagStore
from video_lecture_skill.transcribe import transcribe_audio

logger = logging.getLogger("video_lecture_skill.service")


class VideoLectureService:
    MAX_TASK_RESULTS = 200

    def __init__(self, settings: SkillSettings | None = None):
        self.settings = settings or SkillSettings()
        self.settings.ensure_dirs()
        self._knowledge_store: KnowledgeStore | None = None
        self._tag_store: TagStore | None = None
        self._knowledge_agent: KnowledgeAgent | None = None
        self._task_results: dict[str, PipelineResult] = {}

    @property
    def knowledge_store(self) -> KnowledgeStore:
        if self._knowledge_store is None:
            self._knowledge_store = KnowledgeStore(self.settings)
        return self._knowledge_store

    @property
    def tag_store(self) -> TagStore:
        if self._tag_store is None:
            self._tag_store = TagStore(self.settings)
        return self._tag_store

    @property
    def knowledge_agent(self) -> KnowledgeAgent:
        if self._knowledge_agent is None:
            self._knowledge_agent = KnowledgeAgent(self.knowledge_store, self.settings)
        return self._knowledge_agent

    def process(
        self,
        url: str,
        title: str | None = None,
        language: str = "zh",
        wait: bool = True,
        output_dir: str | None = None,
        page_number: int | None = None,
    ) -> dict:
        task_id = uuid4().hex
        logger.info("process start task_id=%s url=%s page=%s", task_id, url, page_number)

        events: list[PipelineEvent] = []

        def on_event(event: PipelineEvent) -> None:
            events.append(event)
            logger.info("task_id=%s stage=%s progress=%s", task_id, event.stage, event.progress)

        try:
            task_input = TaskInput(
                url=url,
                title=title,
                language=language,
                page_number=page_number,
            )

            result = run_sync(
                task_input=task_input,
                settings=self.settings,
                emit=on_event,
            )

            video_id = result.video_info.canonical_id or result.video_info.id
            self._task_results[task_id] = result
            self._evict_old_tasks()

            if self.settings.knowledge_enabled:
                self.knowledge_store.register_result(video_id, result)
                self.knowledge_store.index_video(video_id)

            if output_dir:
                artifacts = export_to_files(result, Path(output_dir))
                result = result.model_copy(update={"artifacts": artifacts})

            return {
                "success": True,
                "task_id": task_id,
                "video_id": video_id,
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
        page_number: int | None = None,
    ) -> dict:
        return self.process(url, title, language, wait=True, output_dir=output_dir, page_number=page_number)

    def resummary(
        self,
        task_id: str,
    ) -> dict:
        existing = self._task_results.get(task_id)
        if existing is None:
            return {
                "success": False,
                "task_id": task_id,
                "error": "未找到指定任务的结果，无法重摘要。",
            }

        if not existing.transcription.transcript.strip():
            return {
                "success": False,
                "task_id": task_id,
                "error": "指定任务没有可复用的转写文本。",
            }

        new_task_id = uuid4().hex
        try:
            title = existing.lecture.title or existing.video_info.title or "视频"
            lecture = generate_lecture(
                transcription=existing.transcription,
                title=title,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                chunk_target_chars=self.settings.summary_chunk_target_chars,
                chunk_overlap_segments=self.settings.summary_chunk_overlap_segments,
                chunk_concurrency=self.settings.summary_chunk_concurrency,
                chunk_retry_count=self.settings.summary_chunk_retry_count,
            )
            mindmap = generate_mindmap(
                transcription=existing.transcription,
                lecture=lecture,
                title=title,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
            )
            new_result = existing.model_copy(update={
                "lecture": lecture,
                "mindmap": mindmap,
            })
            self._task_results[new_task_id] = new_result

            video_id = existing.video_info.canonical_id or existing.video_info.id
            if self.settings.knowledge_enabled:
                self.knowledge_store.register_result(video_id, new_result)
                self.knowledge_store.index_video(video_id)

            return {
                "success": True,
                "task_id": new_task_id,
                "source_task_id": task_id,
                "status": "completed",
                "lecture_md": export_markdown(new_result),
                "mindmap_mermaid": export_mermaid(new_result),
                "lecture_title": lecture.title,
                "sections_count": len(lecture.sections),
            }
        except Exception as exc:
            logger.exception("resummary failed task_id=%s error=%s", new_task_id, exc)
            return {
                "success": False,
                "task_id": new_task_id,
                "error": format_error_for_user(exc),
            }

    def aggregate_summary(
        self,
        task_ids: list[str],
    ) -> dict:
        source_results: list[tuple[str, PipelineResult]] = []
        for tid in task_ids:
            result = self._task_results.get(tid)
            if result is not None:
                source_results.append((tid, result))

        if not source_results:
            return {
                "success": False,
                "error": "没有找到可汇总的任务结果。",
            }

        transcript_parts: list[str] = []
        segments: list[dict[str, object]] = []
        for tid, result in source_results:
            title = result.lecture.title or result.video_info.title or f"任务{tid}"
            overview = str(result.overview or result.lecture.overview or "").strip()
            key_points = [str(item).strip() for item in result.key_points if str(item).strip()][:8]
            note = str(result.knowledge_note_markdown or "").strip()[:360]

            section_lines = [f"## {title}"]
            if overview:
                section_lines.append(f"[概览] {overview[:520]}")
            if key_points:
                section_lines.append(f"[要点] {'；'.join(key_points)}")
            if note:
                section_lines.append(f"[笔记] {note}")

            transcript_parts.append("\n".join(section_lines).strip())
            segments.append({
                "start": 0.0,
                "end": 0.0,
                "text": f"{title}：{overview or title}",
            })

        aggregate_title = "｜".join(
            set(result.lecture.title or result.video_info.title for _, result in source_results)
        ) + "｜合集总结"

        aggregate_transcription = TranscriptionResult(
            transcript="\n\n".join(transcript_parts),
            segments=[Segment(start=s["start"], end=s["end"], text=str(s["text"])) for s in segments],
            language=source_results[0][1].transcription.language,
        )

        try:
            lecture = generate_lecture(
                transcription=aggregate_transcription,
                title=aggregate_title,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                chunk_target_chars=self.settings.summary_chunk_target_chars,
                chunk_overlap_segments=self.settings.summary_chunk_overlap_segments,
                chunk_concurrency=self.settings.summary_chunk_concurrency,
                chunk_retry_count=self.settings.summary_chunk_retry_count,
            )
            mindmap = generate_mindmap(
                transcription=aggregate_transcription,
                lecture=lecture,
                title=aggregate_title,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
            )
            aggregate_result = PipelineResult(
                video_info=source_results[0][1].video_info,
                transcription=aggregate_transcription,
                lecture=lecture,
                mindmap=mindmap,
                overview=lecture.overview,
                key_points=lecture.sections[0].key_concepts if lecture.sections else [],
                knowledge_note_markdown=lecture.overview,
            )

            new_task_id = uuid4().hex
            self._task_results[new_task_id] = aggregate_result

            return {
                "success": True,
                "task_id": new_task_id,
                "source_task_ids": task_ids,
                "status": "completed",
                "lecture_md": export_markdown(aggregate_result),
                "mindmap_mermaid": export_mermaid(aggregate_result),
                "lecture_title": aggregate_title,
                "sections_count": len(lecture.sections),
            }
        except Exception as exc:
            logger.exception("aggregate_summary failed error=%s", exc)
            return {
                "success": False,
                "error": format_error_for_user(exc),
            }

    def export_obsidian_note(
        self,
        task_id: str,
        output_dir: str | None = None,
    ) -> dict:
        result = self._task_results.get(task_id)
        if result is None:
            return {"success": False, "error": "未找到指定任务的结果。"}

        target_dir = self.settings.output_dir
        if output_dir:
            target_dir = Path(output_dir).expanduser()
        if target_dir is None:
            return {"success": False, "error": "未配置 Obsidian 输出目录，请设置 VLEC_OBSIDIAN_OUTPUT_DIR 或指定 output_dir。"}

        try:
            path, overwritten = export_obsidian_to_file(
                result,
                target_dir,
                source_url=result.video_info.url,
                platform=result.video_info.platform,
                video_id=result.video_info.canonical_id,
                task_id=task_id,
                tags=result.tags,
            )
            return {
                "success": True,
                "task_id": task_id,
                "path": str(path),
                "file_name": path.name,
                "overwritten": overwritten,
                "target_format": "obsidian",
            }
        except Exception as exc:
            logger.exception("export_obsidian failed task_id=%s error=%s", task_id, exc)
            return {"success": False, "error": format_error_for_user(exc)}

    def search_knowledge(
        self,
        query: str,
        limit: int = 10,
        tag_filter: list[str] | None = None,
    ) -> list[KnowledgeSearchResult]:
        if not self.settings.knowledge_enabled:
            return []
        return self.knowledge_store.search(query, limit=limit, tag_filter=tag_filter)

    def ask_knowledge(
        self,
        query: str,
        context_limit: int = 5,
        history: list[KnowledgeChatHistoryItem] | None = None,
    ) -> KnowledgeAskResponse:
        if not self.settings.knowledge_enabled:
            return KnowledgeAskResponse(query=query, answer="知识库未启用。", sources=[])
        return self.knowledge_agent.ask(query, context_limit=context_limit, history=history)

    def add_tag(self, video_id: str, tag: str) -> bool:
        return self.tag_store.add_tag(video_id, tag)

    def remove_tag(self, video_id: str, tag: str) -> bool:
        return self.tag_store.remove_tag(video_id, tag)

    def get_tags_for_video(self, video_id: str) -> list[VideoTagRecord]:
        return self.tag_store.get_tags_for_video(video_id)

    def get_all_tags(self) -> list[TagItem]:
        return self.tag_store.get_all_tags()

    def auto_tag_video(self, video_id: str, content: str) -> list[str]:
        return self.tag_store.auto_tag_video(video_id, content)

    def get_tag_network(
        self,
        selected_tags: list[str] | None = None,
        max_tags: int = 12,
        max_videos: int = 8,
    ) -> KnowledgeNetworkResponse:
        return self.tag_store.get_network_data(selected_tags, max_tags=max_tags, max_videos=max_videos)

    def get_knowledge_stats(self) -> KnowledgeStatsResponse:
        indexed_chunk_count = 0
        try:
            if self._knowledge_store is not None:
                chunk_count = self._knowledge_store.get_indexed_chunk_count()
                indexed_chunk_count = chunk_count
        except Exception:
            pass

        all_tags = self.tag_store.get_all_tags()
        tagged_video_ids: set[str] = set()
        for record in self.tag_store.get_all_video_tags():
            tagged_video_ids.add(record.video_id)
        untagged_count = max(0, len(self._task_results) - len(tagged_video_ids & set(self._task_results.keys())))

        return KnowledgeStatsResponse(
            video_count=len(self._task_results),
            indexed_chunk_count=indexed_chunk_count,
            tag_count=len(all_tags),
            untagged_video_count=untagged_count,
            knowledge_llm_available=bool(self.settings.knowledge_enabled and self.settings.openai_api_key),
        )

    def extract_keyframes(
        self,
        task_id: str,
        timestamps: list[float] | None = None,
        labels: list[str] | None = None,
        width: int = 1280,
        max_frames: int = 20,
    ) -> dict:
        existing = self._task_results.get(task_id)
        if existing is None:
            return {"success": False, "error": "未找到指定任务的结果。"}

        video_path = existing.video_file_path
        if not video_path:
            return {"success": False, "error": "该任务没有本地视频文件，无法截帧。请确保视频已下载到本地。"}

        video = Path(video_path)
        if not video.exists():
            return {"success": False, "error": f"视频文件不存在：{video_path}"}

        output_dir = self.settings.tasks_dir / task_id / "keyframes"

        try:
            if timestamps:
                keyframes = extract_keyframes_from_timestamps(
                    video_path=video,
                    timestamps=timestamps,
                    labels=labels,
                    output_dir=output_dir,
                    width=width,
                    max_frames=max_frames,
                )
            else:
                keyframes = extract_keyframes_from_sections(
                    video_path=video,
                    lecture=existing.lecture,
                    output_dir=output_dir,
                    width=width,
                    max_frames=max_frames,
                )

            updated = existing.model_copy(update={"keyframes": keyframes})
            self._task_results[task_id] = updated

            return {
                "success": True,
                "task_id": task_id,
                "keyframes_count": len(keyframes),
                "keyframes": [kf.model_dump(mode="json") for kf in keyframes],
            }
        except Exception as exc:
            logger.exception("extract_keyframes failed task_id=%s error=%s", task_id, exc)
            return {"success": False, "error": format_error_for_user(exc)}

    def _evict_old_tasks(self) -> None:
        if len(self._task_results) <= self.MAX_TASK_RESULTS:
            return
        oldest_keys = list(self._task_results.keys())[: len(self._task_results) - self.MAX_TASK_RESULTS]
        for key in oldest_keys:
            self._task_results.pop(key, None)

    def get_capabilities(self) -> dict:
        return {
            "supported_platforms": ["bilibili", "youtube", "douyin", "generic", "local"],
            "transcribe_modes": ["local", "cloud"],
            "output_formats": ["markdown", "mermaid", "json", "obsidian"],
            "features": [
                "video_download",
                "audio_transcription",
                "lecture_generation",
                "mindmap_generation",
                "multi_format_export",
                "progress_tracking",
                "sse_streaming",
                "knowledge_base_rag",
                "knowledge_search",
                "knowledge_qa",
                "auto_tagging",
                "tag_network",
                "multi_page_video",
                "aggregate_summary",
                "resummary",
                "local_video_upload",
                "obsidian_export",
                "keyframe_extraction",
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
    emit: Callable | None = None,
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
    result.video_file_path = str(audio_path)

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
    result.overview = lecture.overview
    result.key_points = [c for s in lecture.sections for c in s.key_concepts]
    result.knowledge_note_markdown = lecture.overview

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
