from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Protocol, TypeVar

from video_lecture_skill.models import PipelineEvent, PipelineResult, TaskInput

logger = logging.getLogger("video_lecture_skill.pipeline_base")

PipelineEventReporter = Callable[[PipelineEvent], None]

T = TypeVar("T")


class Stage(ABC):
    name: str
    min_progress: int
    max_progress: int

    @abstractmethod
    def execute(self, context: PipelineContext, emit: PipelineEventReporter | None) -> PipelineContext:
        raise NotImplementedError


class PipelineContext:
    task_input: TaskInput
    video_info: dict | None = None
    audio_path: str | None = None
    transcription: dict | None = None
    lecture: dict | None = None
    mindmap: dict | None = None
    metadata: dict = {}

    def __init__(self, task_input: TaskInput):
        self.task_input = task_input


class Pipeline(ABC):
    name: str

    @abstractmethod
    def get_stages(self) -> list[Stage]:
        raise NotImplementedError

    def run(
        self,
        task_input: TaskInput,
        emit: PipelineEventReporter | None = None,
    ) -> PipelineResult:
        context = PipelineContext(task_input)

        def _emit(stage: str, progress: int, message: str, payload: dict | None = None) -> None:
            event = PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {})
            if emit is not None:
                emit(event)
            logger.info("pipeline stage=%s progress=%s message=%s", stage, progress, message)

        for stage in self.get_stages():
            try:
                context = stage.execute(context, _emit)
            except Exception as exc:
                logger.exception("pipeline stage failed stage=%s error=%s", stage.name, exc)
                raise

        return self._build_result(context)

    @abstractmethod
    def _build_result(self, context: PipelineContext) -> PipelineResult:
        raise NotImplementedError


class Transcriber(Protocol):
    def __call__(
        self,
        audio_path: str,
        language: str,
        emit: PipelineEventReporter | None,
    ) -> dict:
        ...


class LLMSummarizer(Protocol):
    def __call__(
        self,
        transcript: str,
        title: str,
        emit: PipelineEventReporter | None,
    ) -> dict:
        ...


def create_default_pipeline(
    download_fn: Callable,
    transcribe_fn: Transcriber,
    lecture_fn: LLMSummarizer,
    mindmap_fn: LLMSummarizer,
) -> Pipeline:
    return DefaultPipeline(download_fn, transcribe_fn, lecture_fn, mindmap_fn)


class DefaultPipeline(Pipeline):
    name = "video-lecture-default"

    def __init__(
        self,
        download_fn: Callable,
        transcribe_fn: Transcriber,
        lecture_fn: LLMSummarizer,
        mindmap_fn: LLMSummarizer,
    ):
        self.download_fn = download_fn
        self.transcribe_fn = transcribe_fn
        self.lecture_fn = lecture_fn
        self.mindmap_fn = mindmap_fn

    def get_stages(self) -> list[Stage]:
        return [
            DownloadStage(self.download_fn),
            TranscribeStage(self.transcribe_fn),
            LectureStage(self.lecture_fn),
            MindmapStage(self.mindmap_fn),
        ]

    def _build_result(self, context: PipelineContext) -> PipelineResult:
        from video_lecture_skill.models import (
            LectureNote,
            MindmapNode,
            MindmapResult,
            PipelineResult,
            TranscriptionResult,
            VideoInfo,
        )

        video_info = context.video_info or {}
        video = VideoInfo(
            url=video_info.get("url", ""),
            title=video_info.get("title", ""),
            platform=video_info.get("platform", ""),
            duration=video_info.get("duration"),
            thumbnail=video_info.get("thumbnail", ""),
            canonical_id=video_info.get("canonical_id", ""),
        )

        transcription = context.transcription or {}
        segments = [type("Segment", (), s)() for s in transcription.get("segments", [])]
        trans = TranscriptionResult(
            transcript=transcription.get("transcript", ""),
            segments=[],
            language=transcription.get("language", "zh"),
            duration=transcription.get("duration", 0.0),
        )

        lecture = context.lecture or {}
        lect = LectureNote(
            title=lecture.get("title", ""),
            overview=lecture.get("overview", ""),
            prerequisites=lecture.get("prerequisites", []),
            summary=lecture.get("summary", ""),
            references=lecture.get("references", []),
        )

        mindmap = context.mindmap or {}
        mm_tree = mindmap.get("tree", {})
        mind = MindmapResult(
            title=mindmap.get("title", ""),
            mermaid=mindmap.get("mermaid", ""),
            tree=MindmapNode(label=mm_tree.get("label", "root"), children=[]),
        )

        return PipelineResult(
            video_info=video,
            transcription=trans,
            lecture=lect,
            mindmap=mind,
            artifacts=context.metadata.get("artifacts", {}),
        )


class DownloadStage(Stage):
    name = "downloading"
    min_progress = 5
    max_progress = 50

    def __init__(self, download_fn: Callable):
        self.download_fn = download_fn

    def execute(self, context: PipelineContext, emit: PipelineEventReporter | None) -> PipelineContext:
        emit(self.name, self.min_progress, "正在下载视频")
        result = self.download_fn(context.task_input.url, emit)
        context.audio_path = result["audio_path"]
        context.video_info = result["video_info"]
        emit(self.name, self.max_progress, "下载完成")
        return context


class TranscribeStage(Stage):
    name = "transcribing"
    min_progress = 50
    max_progress = 85

    def __init__(self, transcribe_fn: Transcriber):
        self.transcribe_fn = transcribe_fn

    def execute(self, context: PipelineContext, emit: PipelineEventReporter | None) -> PipelineContext:
        emit(self.name, self.min_progress, "正在转写音频")
        result = self.transcribe_fn(context.audio_path, context.task_input.language, emit)
        context.transcription = result
        emit(self.name, self.max_progress, "转写完成")
        return context


class LectureStage(Stage):
    name = "lecture"
    min_progress = 85
    max_progress = 95

    def __init__(self, lecture_fn: LLMSummarizer):
        self.lecture_fn = lecture_fn

    def execute(self, context: PipelineContext, emit: PipelineEventReporter | None) -> PipelineContext:
        emit(self.name, self.min_progress, "正在生成讲义")
        title = context.task_input.title or context.video_info.get("title", "视频")
        result = self.lecture_fn(context.transcription["transcript"], title, emit)
        context.lecture = result
        emit(self.name, self.max_progress, "讲义生成完成")
        return context


class MindmapStage(Stage):
    name = "mindmap"
    min_progress = 95
    max_progress = 99

    def __init__(self, mindmap_fn: LLMSummarizer):
        self.mindmap_fn = mindmap_fn

    def execute(self, context: PipelineContext, emit: PipelineEventReporter | None) -> PipelineContext:
        emit(self.name, self.min_progress, "正在生成思维导图")
        title = context.task_input.title or context.video_info.get("title", "视频")
        result = self.mindmap_fn(context.transcription["transcript"], title, emit)
        context.mindmap = result
        emit(self.name, self.max_progress, "思维导图生成完成")
        return context
