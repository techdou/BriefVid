from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("video_lecture_skill.models")


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
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    start: float
    end: float
    text: str


class InputType(str, Enum):
    URL = "url"
    VIDEO_FILE = "video_file"
    AUDIO_FILE = "audio_file"
    TRANSCRIPT_TEXT = "transcript_text"


class VideoPageInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    page: int = 1
    title: str = ""
    source_url: str = ""
    cover_url: str = ""
    duration: float | None = None


class VideoInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    url: str = ""
    title: str = ""
    platform: str = ""
    duration: float | None = None
    thumbnail: str = ""
    canonical_id: str = ""
    pages: list[VideoPageInfo] = Field(default_factory=list)
    is_multi_page: bool = False

    def to_openapi(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string", "example": self.id},
                "url": {"type": "string", "example": "https://www.bilibili.com/video/BV1xxx"},
                "title": {"type": "string", "example": "视频标题"},
                "platform": {"type": "string", "enum": ["bilibili", "youtube", "douyin", "generic"]},
                "duration": {"type": "number", "example": 3600.0},
                "thumbnail": {"type": "string", "format": "uri"},
                "canonical_id": {"type": "string"},
            },
        }


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    transcript: str = ""
    segments: list[Segment] = Field(default_factory=list)
    language: str = "zh"
    duration: float = 0.0

    def to_openapi(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "transcript": {"type": "string", "description": "带时间戳的转写文本"},
                "segments": {"type": "array", "items": {"$ref": "#/components/schemas/Segment"}},
                "language": {"type": "string"},
                "duration": {"type": "number"},
            },
        }


class LectureSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    start: float = 0.0
    key_concepts: list[str] = Field(default_factory=list)
    explanation: str = ""
    examples: list[str] = Field(default_factory=list)
    quiz: list[str] = Field(default_factory=list)


class LectureNote(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    overview: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    sections: list[LectureSection] = Field(default_factory=list)
    summary: str = ""
    references: list[str] = Field(default_factory=list)
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None

    def to_openapi(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "overview": {"type": "string"},
                "prerequisites": {"type": "array", "items": {"type": "string"}},
                "sections": {"type": "array", "items": {"$ref": "#/components/schemas/LectureSection"}},
                "summary": {"type": "string"},
                "references": {"type": "array", "items": {"type": "string"}},
            },
        }


class MindmapNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    label: str = ""
    children: list[MindmapNode] = Field(default_factory=list)


class MindmapResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = ""
    mermaid: str = ""
    tree: MindmapNode = Field(default_factory=lambda: MindmapNode(label="root"))
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    video_id: str = ""
    title: str = ""
    relevance_score: float = 0.0
    snippet: str = ""
    tags: list[str] = Field(default_factory=list)
    cover_url: str = ""
    timestamp: str | None = None
    video_title: str = ""
    page_title: str | None = None
    page_number: int | None = None


class KnowledgeSourceRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    video_id: str = ""
    title: str = ""
    relevance_score: float = 0.0
    timestamp: str | None = None
    video_title: str = ""
    page_title: str | None = None
    page_number: int | None = None


class KnowledgeAskResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    query: str = ""
    answer: str = ""
    sources: list[KnowledgeSourceRef] = Field(default_factory=list)


class KnowledgeChatHistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    role: str = "user"
    content: str = ""


class TagItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    tag: str = ""
    count: int = 0


class VideoTagRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    video_id: str = ""
    tag: str = ""
    source: str = "manual"
    confidence: float = 1.0


class KnowledgeNetworkNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = ""
    label: str = ""
    type: str = "tag"
    count: int = 0
    degree: int = 0
    focus: bool = False
    video_count: int = 0
    tags: list[str] = Field(default_factory=list)


class KnowledgeNetworkLink(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source: str = ""
    target: str = ""
    weight: float = 1.0
    kind: str = "cooccurrence"


class KnowledgeNetworkResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    nodes: list[KnowledgeNetworkNode] = Field(default_factory=list)
    links: list[KnowledgeNetworkLink] = Field(default_factory=list)
    mode: str = "overview"
    hidden_tag_count: int = 0
    selected_tags: list[str] = Field(default_factory=list)


class KnowledgeStatsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    video_count: int = 0
    indexed_chunk_count: int = 0
    tag_count: int = 0
    untagged_video_count: int = 0
    knowledge_llm_available: bool = False


class TaskInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    url: str = Field("", description="视频链接")
    title: str | None = Field(None, description="视频标题（可选）")
    language: str = Field("zh", description="转写语言")
    output_formats: list[TaskOutputFormat] = Field(
        default_factory=lambda: [TaskOutputFormat.MARKDOWN, TaskOutputFormat.MERMAID, TaskOutputFormat.JSON],
        description="输出格式列表",
    )
    transcribe_mode: TranscribeMode | None = Field(None, description="转写模式")
    input_type: InputType = Field(InputType.URL, description="输入类型")
    page_number: int | None = Field(None, description="B站多P视频分P号")
    source_transcript: str | None = Field(None, description="重摘要时复用的转写文本")

    def to_openapi(self) -> dict:
        return {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string",
                    "description": "视频链接（支持 B站、YouTube、抖音等）",
                    "example": "https://www.bilibili.com/video/BV1R6NFzXE1H/",
                },
                "title": {"type": "string", "description": "视频标题（可选）"},
                "language": {"type": "string", "enum": ["zh", "en", "ja", "ko", "auto"], "default": "zh"},
                "output_formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["markdown", "mermaid", "json"]},
                    "default": ["markdown", "mermaid", "json"],
                },
                "transcribe_mode": {"type": "string", "enum": ["local", "cloud"]},
            },
        }


class PipelineEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    stage: str
    progress: int = Field(..., ge=0, le=100)
    message: str
    payload: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KeyframeInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    timestamp: float = 0.0
    timestamp_label: str = ""
    section_title: str = ""
    image_path: str = ""
    image_url: str = ""
    width: int = 0
    height: int = 0


class PipelineResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    video_info: VideoInfo = Field(default_factory=VideoInfo)
    transcription: TranscriptionResult = Field(default_factory=TranscriptionResult)
    lecture: LectureNote = Field(default_factory=LectureNote)
    mindmap: MindmapResult = Field(default_factory=MindmapResult)
    artifacts: dict[str, str] = Field(default_factory=dict)
    overview: str = ""
    key_points: list[str] = Field(default_factory=list)
    knowledge_note_markdown: str = ""
    timeline: list[dict[str, object]] = Field(default_factory=list)
    segment_summaries: list[str] = Field(default_factory=list)
    mindmap_status: str | None = None
    mindmap_error_message: str | None = None
    tags: list[str] = Field(default_factory=list)
    keyframes: list[KeyframeInfo] = Field(default_factory=list)
    video_file_path: str = ""


class TaskRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    task_input: TaskInput
    status: TaskStatus = TaskStatus.QUEUED
    result: PipelineResult | None = None
    error_message: str | None = None
    video_id: str | None = None
    page_number: int | None = None
    page_title: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float | None:
        if not self.created_at or not self.updated_at:
            return None
        return max(0.0, (self.updated_at - self.created_at).total_seconds())


def validate_url(url: str) -> bool:
    return bool(url and url.strip())


def parse_timestamp(ts: str) -> float | None:
    match = re.match(r"(?:(\d+):)?(\d+):(\d+)", ts)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    return None
