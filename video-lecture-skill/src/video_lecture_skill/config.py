from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from video_lecture_skill.models import TranscribeMode


def _default_data_dir() -> Path:
    return Path.home() / ".video-lecture" / "data"


class SkillSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VLEC_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 3839
    data_dir: Path = Field(default_factory=_default_data_dir)

    transcribe_mode: TranscribeMode = TranscribeMode.LOCAL
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    language: str = "zh"
    output_formats: str = "markdown,mermaid,json"

    summary_chunk_target_chars: int = 2200
    summary_chunk_overlap_segments: int = 2
    summary_chunk_concurrency: int = 2
    summary_chunk_retry_count: int = 2

    @field_validator("transcribe_mode", mode="before")
    @classmethod
    def _normalize_transcribe_mode(cls, value: str | None) -> TranscribeMode:
        if value is None:
            return TranscribeMode.LOCAL
        normalized = str(value).strip().lower()
        if normalized in ("cloud", "api", "openai"):
            return TranscribeMode.CLOUD
        return TranscribeMode.LOCAL

    @property
    def tasks_dir(self) -> Path:
        return self.data_dir / "tasks"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def output_format_list(self) -> list[str]:
        return [fmt.strip() for fmt in self.output_formats.split(",") if fmt.strip()]

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
