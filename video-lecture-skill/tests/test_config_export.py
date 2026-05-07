from video_lecture_skill.config import SkillSettings, TranscribeMode
from video_lecture_skill.export import export_json, export_markdown, export_mermaid, export_transcript
from video_lecture_skill.models import (
    LectureNote,
    LectureSection,
    MindmapNode,
    MindmapResult,
    PipelineResult,
    Segment,
    TranscriptionResult,
    VideoInfo,
)


def test_settings_defaults():
    settings = SkillSettings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 3839
    assert settings.transcribe_mode == TranscribeMode.LOCAL
    assert settings.whisper_model == "base"
    assert settings.language == "zh"


def test_settings_output_format_list():
    settings = SkillSettings(output_formats="markdown,mermaid,json")
    assert settings.output_format_list == ["markdown", "mermaid", "json"]


def test_settings_tasks_dir():
    settings = SkillSettings()
    assert settings.tasks_dir == settings.data_dir / "tasks"


def test_settings_cache_dir():
    settings = SkillSettings()
    assert settings.cache_dir == settings.data_dir / "cache"


def test_export_markdown():
    result = PipelineResult(
        video_info=VideoInfo(url="https://example.com", title="Test Video"),
        transcription=TranscriptionResult(transcript="Hello world", segments=[Segment(start=0, end=5, text="Hello world")]),
        lecture=LectureNote(
            title="Test Lecture",
            overview="This is an overview",
            sections=[
                LectureSection(
                    title="Section 1",
                    start=0,
                    key_concepts=["concept1"],
                    explanation="explanation text",
                    examples=["example1"],
                    quiz=["question1"],
                )
            ],
            summary="summary text",
            references=["ref1"],
        ),
        mindmap=MindmapResult(
            title="Test Mindmap",
            mermaid="mindmap\n  root\n    child1",
            tree=MindmapNode(label="root", children=[MindmapNode(label="child1")]),
        ),
    )

    md = export_markdown(result)
    assert "# Test Lecture" in md
    assert "概述" in md
    assert "Section 1" in md
    assert "concept1" in md
    assert "思维导图" in md
    assert "mindmap" in md


def test_export_mermaid():
    result = PipelineResult(
        mindmap=MindmapResult(mermaid="mindmap\n  root\n    child1"),
    )
    assert export_mermaid(result) == "mindmap\n  root\n    child1"


def test_export_transcript():
    result = PipelineResult(
        transcription=TranscriptionResult(transcript="Hello world"),
    )
    assert export_transcript(result) == "Hello world"


def test_export_json():
    result = PipelineResult(
        video_info=VideoInfo(url="https://example.com"),
    )
    json_str = export_json(result)
    import json
    parsed = json.loads(json_str)
    assert "video_info" in parsed
    assert "transcription" in parsed
    assert "lecture" in parsed
    assert "mindmap" in parsed


def test_export_to_files(tmp_path):
    result = PipelineResult(
        video_info=VideoInfo(url="https://example.com", title="Test"),
        transcription=TranscriptionResult(transcript="Hello world"),
        lecture=LectureNote(title="Test Lecture", overview="overview"),
        mindmap=MindmapResult(mermaid="mindmap\n  root"),
    )
    from video_lecture_skill.export import export_to_files
    artifacts = export_to_files(result, tmp_path / "output")
    assert "transcript" in artifacts
    assert "lecture_md" in artifacts
    assert "result_json" in artifacts
    assert (tmp_path / "output" / "transcript.txt").exists()
    assert (tmp_path / "output" / "lecture.md").exists()
    assert (tmp_path / "output" / "result.json").exists()
