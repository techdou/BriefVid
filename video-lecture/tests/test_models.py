from video_lecture_skill.models import (
    LectureNote,
    LectureSection,
    MindmapNode,
    MindmapResult,
    PipelineEvent,
    PipelineResult,
    Segment,
    TaskInput,
    TaskOutputFormat,
    TaskRecord,
    TaskStatus,
    TranscribeMode,
    TranscriptionResult,
    VideoInfo,
)


def test_segment_creation():
    seg = Segment(start=1.5, end=3.2, text="hello world")
    assert seg.start == 1.5
    assert seg.end == 3.2
    assert seg.text == "hello world"


def test_video_info_defaults():
    info = VideoInfo(url="https://example.com")
    assert info.url == "https://example.com"
    assert info.title == ""
    assert info.platform == ""
    assert info.duration is None


def test_transcription_result():
    result = TranscriptionResult(
        transcript="hello",
        segments=[Segment(start=0, end=1, text="hello")],
        language="en",
        duration=1.0,
    )
    assert result.transcript == "hello"
    assert len(result.segments) == 1
    assert result.language == "en"


def test_lecture_note():
    note = LectureNote(
        title="Test Lecture",
        overview="An overview",
        sections=[
            LectureSection(
                title="Section 1",
                start=0.0,
                key_concepts=["concept1"],
                explanation="explanation",
                examples=["example1"],
                quiz=["question1"],
            )
        ],
        summary="summary",
    )
    assert note.title == "Test Lecture"
    assert len(note.sections) == 1
    assert note.sections[0].key_concepts == ["concept1"]


def test_mindmap_node():
    node = MindmapNode(
        label="root",
        children=[
            MindmapNode(label="child1"),
            MindmapNode(label="child2", children=[MindmapNode(label="grandchild")]),
        ],
    )
    assert node.label == "root"
    assert len(node.children) == 2
    assert len(node.children[1].children) == 1


def test_mindmap_result():
    result = MindmapResult(
        title="Test Mindmap",
        mermaid="mindmap\n  root\n    child1",
        tree=MindmapNode(label="root", children=[MindmapNode(label="child1")]),
    )
    assert result.title == "Test Mindmap"
    assert "mindmap" in result.mermaid


def test_task_input_defaults():
    inp = TaskInput(url="https://example.com/video")
    assert inp.url == "https://example.com/video"
    assert inp.title is None
    assert inp.language == "zh"
    assert TaskOutputFormat.MARKDOWN in inp.output_formats
    assert inp.transcribe_mode is None


def test_task_record():
    inp = TaskInput(url="https://example.com/video", title="Test")
    record = TaskRecord(task_input=inp)
    assert record.status == TaskStatus.QUEUED
    assert record.result is None
    assert record.error_message is None
    assert len(record.task_id) > 0


def test_task_record_duration():
    from datetime import datetime, timezone, timedelta
    inp = TaskInput(url="https://example.com")
    now = datetime.now(timezone.utc)
    record = TaskRecord(
        task_input=inp,
        created_at=now,
        updated_at=now + timedelta(seconds=30),
    )
    assert record.duration_seconds == 30.0


def test_pipeline_event():
    event = PipelineEvent(stage="downloading", progress=50, message="downloading audio")
    assert event.stage == "downloading"
    assert event.progress == 50


def test_pipeline_result_defaults():
    result = PipelineResult()
    assert result.video_info.url == ""
    assert result.transcription.transcript == ""
    assert result.lecture.title == ""
    assert result.mindmap.mermaid == ""
    assert result.artifacts == {}


def test_transcribe_mode_enum():
    assert TranscribeMode.LOCAL == "local"
    assert TranscribeMode.CLOUD == "cloud"


def test_task_output_format_enum():
    assert TaskOutputFormat.MARKDOWN == "markdown"
    assert TaskOutputFormat.MERMAID == "mermaid"
    assert TaskOutputFormat.JSON == "json"
