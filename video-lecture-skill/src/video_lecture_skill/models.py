from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskOutputFormat(str, Enum):
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
    JSON = "json"


class TranscribeMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class Segment(BaseModel):
    start: float
    end: float
    text: str


class VideoInfo(BaseModel):
    url: str = ""
    title: str = ""
    platform: str = ""
    duration: float | None = None
    thumbnail: str = ""
    canonical_id: str = ""


class TranscriptionResult(BaseModel):
    transcript: str = ""
    segments: list[Segment] = Field(default_factory=list)
    language: str = "zh"
    duration: float = 0.0


class LectureSection(BaseModel):
    title: str
    start: float = 0.0
    key_concepts: list[str] = Field(default_factory=list)
    explanation: str = ""
    examples: list[str] = Field(default_factory=list)
    quiz: list[str] = Field(default_factory=list)


class LectureNote(BaseModel):
    title: str = ""
    overview: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    sections: list[LectureSection] = Field(default_factory=list)
    summary: str = ""
    references: list[str] = Field(default_factory=list)
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None


class MindmapNode(BaseModel):
    label: str
    children: list[MindmapNode] = Field(default_factory=list)


class MindmapResult(BaseModel):
    title: str = ""
    mermaid: str = ""
    tree: MindmapNode = Field(default_factory=lambda: MindmapNode(label="root"))
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None


class TaskInput(BaseModel):
    url: str
    title: str | None = None
    language: str = "zh"
    output_formats: list[TaskOutputFormat] = Field(
        default_factory=lambda: [TaskOutputFormat.MARKDOWN, TaskOutputFormat.MERMAID, TaskOutputFormat.JSON]
    )
    transcribe_mode: TranscribeMode | None = None


class PipelineEvent(BaseModel):
    stage: str
    progress: int = 0
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    video_info: VideoInfo = Field(default_factory=VideoInfo)
    transcription: TranscriptionResult = Field(default_factory=TranscriptionResult)
    lecture: LectureNote = Field(default_factory=LectureNote)
    mindmap: MindmapResult = Field(default_factory=MindmapResult)
    artifacts: dict[str, str] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    task_input: TaskInput
    status: TaskStatus = TaskStatus.QUEUED
    result: PipelineResult | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float | None:
        if not self.created_at or not self.updated_at:
            return None
        return max(0.0, (self.updated_at - self.created_at).total_seconds())
