from video_lecture_skill.lecture import _generate_lecture_rules, _build_chunks, _parse_lecture_json
from video_lecture_skill.mindmap import _generate_mindmap_rules, _tree_to_mermaid
from video_lecture_skill.models import LectureNote, LectureSection, MindmapNode, MindmapResult, Segment, TranscriptionResult


def test_lecture_rules_generation():
    transcription = TranscriptionResult(
        transcript="[00:00] Hello world\n[00:05] This is a test\n[00:10] Another line",
        segments=[
            Segment(start=0, end=5, text="Hello world"),
            Segment(start=5, end=10, text="This is a test"),
            Segment(start=10, end=15, text="Another line"),
        ],
        duration=15.0,
    )
    result = _generate_lecture_rules(transcription, "Test Video")
    assert result.title == "Test Video"
    assert len(result.sections) > 0


def test_lecture_parse_json():
    data = {
        "title": "Test",
        "overview": "overview text",
        "prerequisites": ["prereq1"],
        "sections": [
            {
                "title": "Section 1",
                "start": 0,
                "key_concepts": ["concept1"],
                "explanation": "explanation",
                "examples": ["example1"],
                "quiz": ["question1"],
            }
        ],
        "summary": "summary",
        "references": ["ref1"],
    }
    result = _parse_lecture_json(data, "Fallback")
    assert result.title == "Test"
    assert len(result.sections) == 1
    assert result.sections[0].key_concepts == ["concept1"]


def test_build_chunks_empty():
    assert _build_chunks([], 2200, 2) == []


def test_build_chunks_basic():
    segments = [Segment(start=i * 5, end=(i + 1) * 5, text=f"Segment {i} " * 20) for i in range(10)]
    chunks = _build_chunks(segments, 200, 1)
    assert len(chunks) > 0
    assert all("transcript" in c and "segments_json" in c for c in chunks)


def test_mindmap_rules_generation():
    lecture = LectureNote(
        title="Test",
        overview="overview",
        sections=[
            LectureSection(title="S1", start=0, key_concepts=["c1", "c2"], explanation="exp"),
            LectureSection(title="S2", start=60, key_concepts=["c3"], explanation="exp2"),
        ],
        summary="summary",
    )
    result = _generate_mindmap_rules(lecture, "Test Video")
    assert result.title == "Test Video"
    assert len(result.mermaid) > 0
    assert "mindmap" in result.mermaid
    assert result.tree.label == "Test Video"
    assert len(result.tree.children) > 0


def test_tree_to_mermaid():
    tree = MindmapNode(
        label="Root",
        children=[
            MindmapNode(label="Child 1", children=[MindmapNode(label="Grandchild")]),
            MindmapNode(label="Child 2"),
        ],
    )
    mermaid = _tree_to_mermaid("Test", tree)
    assert "mindmap" in mermaid
    assert "Root" in mermaid
    assert "Child 1" in mermaid
    assert "Grandchild" in mermaid
    assert "Child 2" in mermaid


def test_mindmap_rules_empty_lecture():
    lecture = LectureNote(title="Empty", overview="some overview text here")
    result = _generate_mindmap_rules(lecture, "Empty")
    assert result.title == "Empty"
    assert result.tree.label == "Empty"
