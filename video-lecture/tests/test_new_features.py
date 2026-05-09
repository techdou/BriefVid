from __future__ import annotations

import json
from pathlib import Path

from video_lecture_skill.models import (
    InputType,
    KnowledgeAskResponse,
    KnowledgeChatHistoryItem,
    KnowledgeNetworkLink,
    KnowledgeNetworkNode,
    KnowledgeNetworkResponse,
    KnowledgeSearchResult,
    KnowledgeSourceRef,
    KnowledgeStatsResponse,
    TagItem,
    VideoPageInfo,
    VideoTagRecord,
)
from video_lecture_skill.config import SkillSettings
from video_lecture_skill.export import (
    export_obsidian,
    export_obsidian_to_file,
    _build_frontmatter,
    _format_key_points,
    _format_timeline,
    _normalize_embedded_note,
)
from video_lecture_skill.tags import TagStore
from video_lecture_skill.knowledge import (
    KnowledgeStore,
    KnowledgeAgent,
    format_anchor_seconds,
    _split_markdown_sections,
)
from video_lecture_skill.service import VideoLectureService


def test_input_type_enum():
    assert InputType.URL == "url"
    assert InputType.VIDEO_FILE == "video_file"
    assert InputType.AUDIO_FILE == "audio_file"
    assert InputType.TRANSCRIPT_TEXT == "transcript_text"


def test_video_page_info():
    page = VideoPageInfo(page=2, title="P2 测试", source_url="https://example.com?p=2")
    assert page.page == 2
    assert page.title == "P2 测试"


def test_video_info_multi_page():
    from video_lecture_skill.models import VideoInfo
    pages = [VideoPageInfo(page=1, title="P1"), VideoPageInfo(page=2, title="P2")]
    info = VideoInfo(title="测试", pages=pages, is_multi_page=True)
    assert info.is_multi_page is True
    assert len(info.pages) == 2


def test_knowledge_search_result():
    result = KnowledgeSearchResult(
        video_id="v1",
        title="测试视频",
        relevance_score=0.85,
        snippet="这是一段测试内容...",
        tags=["Python", "机器学习"],
        timestamp="05:30",
    )
    assert result.video_id == "v1"
    assert result.relevance_score == 0.85
    assert len(result.tags) == 2


def test_knowledge_ask_response():
    resp = KnowledgeAskResponse(
        query="什么是机器学习？",
        answer="机器学习是人工智能的一个分支...",
        sources=[KnowledgeSourceRef(video_id="v1", title="ML入门", relevance_score=0.9)],
    )
    assert resp.query == "什么是机器学习？"
    assert len(resp.sources) == 1


def test_knowledge_chat_history_item():
    item = KnowledgeChatHistoryItem(role="user", content="你好")
    assert item.role == "user"
    item2 = KnowledgeChatHistoryItem(role="assistant", content="你好！")
    assert item2.role == "assistant"


def test_tag_item():
    tag = TagItem(tag="Python", count=5)
    assert tag.tag == "Python"
    assert tag.count == 5


def test_video_tag_record():
    record = VideoTagRecord(video_id="v1", tag="ML", source="auto_llm", confidence=0.8)
    assert record.source == "auto_llm"
    assert record.confidence == 0.8


def test_knowledge_network_node():
    node = KnowledgeNetworkNode(id="tag_Python", label="Python", type="tag", count=5, degree=3)
    assert node.id == "tag_Python"
    assert node.degree == 3


def test_knowledge_network_link():
    link = KnowledgeNetworkLink(source="tag_Python", target="tag_ML", weight=2.0, kind="cooccurrence")
    assert link.kind == "cooccurrence"
    assert link.weight == 2.0


def test_knowledge_network_response():
    resp = KnowledgeNetworkResponse(
        nodes=[KnowledgeNetworkNode(label="Python")],
        links=[KnowledgeNetworkLink(source="tag_Python", target="tag_ML")],
        mode="overview",
        hidden_tag_count=5,
    )
    assert resp.mode == "overview"
    assert resp.hidden_tag_count == 5


def test_knowledge_stats_response():
    stats = KnowledgeStatsResponse(
        video_count=10,
        indexed_chunk_count=50,
        tag_count=8,
        untagged_video_count=2,
        knowledge_llm_available=True,
    )
    assert stats.video_count == 10
    assert stats.knowledge_llm_available is True


def test_format_anchor_seconds():
    assert format_anchor_seconds(None) is None
    assert format_anchor_seconds(0) == "00:00"
    assert format_anchor_seconds(65) == "01:05"
    assert format_anchor_seconds(3661) == "01:01:01"


def test_split_markdown_sections():
    sections = _split_markdown_sections("## 标题1\n内容1\n## 标题2\n内容2")
    assert len(sections) == 2
    assert sections[0][0] == "标题1"
    assert sections[1][0] == "标题2"


def test_split_markdown_sections_empty():
    assert _split_markdown_sections("") == []
    assert _split_markdown_sections(None) == []


def test_build_frontmatter():
    result = _build_frontmatter({"title": "测试", "tags": ["a", "b"]})
    assert "---" in result
    assert '"测试"' in result
    assert "- \"a\"" in result


def test_format_key_points():
    assert _format_key_points(["要点1", "要点2"]) == "- 要点1\n- 要点2"
    assert _format_key_points([]) == "- 暂无关键要点。"


def test_format_timeline():
    result = _format_timeline([{"title": "章节1", "summary": "摘要1", "start": 60}])
    assert "章节1" in result
    assert "摘要1" in result
    assert "01:00" in result


def test_format_timeline_empty():
    assert _format_timeline([]) == "- 暂无章节时间线。"


def test_normalize_embedded_note():
    assert _normalize_embedded_note("", "标题") == "暂无知识笔记正文。"
    result = _normalize_embedded_note("# 标题\n内容", "标题")
    assert "内容" in result


def test_export_obsidian():
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(url="https://example.com", title="测试视频", platform="bilibili", canonical_id="BV1xxx"),
        lecture=LectureNote(title="测试讲义", overview="这是概览"),
        transcription=TranscriptionResult(transcript="转写内容"),
        mindmap=MindmapResult(mermaid="mindmap\n  root"),
        overview="概览内容",
        key_points=["要点1", "要点2"],
        knowledge_note_markdown="## 笔记\n笔记内容",
        timeline=[{"title": "章节1", "summary": "摘要1", "start": 0}],
        tags=["Python", "ML"],
    )
    obsidian_md = export_obsidian(result, source_url="https://example.com", platform="bilibili", tags=["test"])
    assert "---" in obsidian_md
    assert "title:" in obsidian_md
    assert "核心概览" in obsidian_md
    assert "关键要点" in obsidian_md
    assert "章节时间线" in obsidian_md
    assert "知识笔记" in obsidian_md


def test_export_obsidian_to_file(tmp_path):
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(url="https://example.com", title="测试视频"),
        lecture=LectureNote(title="测试讲义"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
    )
    path, overwritten = export_obsidian_to_file(result, tmp_path, tags=["test"])
    assert path.exists()
    assert overwritten is False
    content = path.read_text(encoding="utf-8")
    assert "---" in content


def test_tag_store_add_and_remove():
    settings = SkillSettings()
    store = TagStore(settings)
    assert store.add_tag("v1", "Python")
    assert store.add_tag("v1", "ML")
    assert store.add_tag("v2", "Python")
    tags = store.get_tags_for_video("v1")
    assert len(tags) == 2
    all_tags = store.get_all_tags()
    assert len(all_tags) == 2
    python_tag = next(t for t in all_tags if t.tag == "Python")
    assert python_tag.count == 2
    assert store.remove_tag("v1", "Python")
    tags_after = store.get_tags_for_video("v1")
    assert len(tags_after) == 1


def test_tag_store_add_duplicate():
    settings = SkillSettings()
    store = TagStore(settings)
    assert store.add_tag("v1", "Python")
    assert store.add_tag("v1", "Python")
    tags = store.get_tags_for_video("v1")
    assert len(tags) == 1


def test_tag_store_network():
    settings = SkillSettings()
    store = TagStore(settings)
    store.add_tag("v1", "Python")
    store.add_tag("v1", "ML")
    store.add_tag("v2", "Python")
    store.add_tag("v2", "深度学习")
    network = store.get_network_data()
    assert network.mode == "overview"
    assert len(network.nodes) > 0
    assert len(network.links) > 0


def test_tag_store_network_focus():
    settings = SkillSettings()
    store = TagStore(settings)
    store.add_tag("v1", "Python")
    store.add_tag("v1", "ML")
    store.add_tag("v2", "Python")
    store.add_tag("v2", "深度学习")
    network = store.get_network_data(selected_tags=["Python"])
    assert network.mode == "focus"
    assert "Python" in network.selected_tags


def test_knowledge_store_register_and_build_chunks():
    settings = SkillSettings()
    store = KnowledgeStore(settings)
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试视频"),
        lecture=LectureNote(title="测试讲义", overview="这是概览"),
        transcription=TranscriptionResult(transcript="转写内容"),
        overview="概览",
        key_points=["要点1"],
        knowledge_note_markdown="## 笔记\n笔记内容",
        timeline=[{"title": "章节1", "summary": "摘要1", "start": 0}],
    )
    store.register_result("v1", result, tags=["Python"])
    chunks = store._build_chunks_for_video("v1")
    assert len(chunks) > 0


def test_knowledge_store_no_result():
    settings = SkillSettings()
    store = KnowledgeStore(settings)
    chunks = store._build_chunks_for_video("nonexistent")
    assert chunks == []


def test_service_knowledge_disabled():
    settings = SkillSettings(knowledge_enabled=False)
    service = VideoLectureService(settings)
    results = service.search_knowledge("测试查询")
    assert results == []
    resp = service.ask_knowledge("测试问题")
    assert "未启用" in resp.answer


def test_service_tag_operations():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    assert service.add_tag("v1", "Python")
    tags = service.get_tags_for_video("v1")
    assert len(tags) == 1
    all_tags = service.get_all_tags()
    assert len(all_tags) == 1
    assert service.remove_tag("v1", "Python")
    tags_after = service.get_tags_for_video("v1")
    assert len(tags_after) == 0


def test_service_knowledge_stats():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    stats = service.get_knowledge_stats()
    assert stats.video_count == 0
    assert stats.tag_count == 0


def test_service_resummary_no_task():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    result = service.resummary("nonexistent_task_id")
    assert result["success"] is False
    assert "未找到" in result["error"]


def test_service_aggregate_no_tasks():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    result = service.aggregate_summary(["nonexistent1", "nonexistent2"])
    assert result["success"] is False
    assert "没有找到" in result["error"]


def test_service_export_obsidian_no_task():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    result = service.export_obsidian_note("nonexistent_task_id")
    assert result["success"] is False


def test_service_export_obsidian_no_output_dir():
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult, MindmapResult
    settings = SkillSettings(obsidian_output_dir="")
    service = VideoLectureService(settings)
    service._task_results["t1"] = PipelineResult(
        video_info=VideoInfo(title="测试"),
        lecture=LectureNote(title="测试讲义"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
    )
    result = service.export_obsidian_note("t1")
    assert result["success"] is False
    assert "Obsidian" in result["error"]


def test_config_knowledge_settings():
    settings = SkillSettings(
        knowledge_enabled=True,
        knowledge_embedding_model="BAAI/bge-small-zh-v1.5",
        knowledge_llm_mode="same_as_main",
    )
    assert settings.knowledge_enabled is True
    assert settings.knowledge_embedding_model == "BAAI/bge-small-zh-v1.5"


def test_config_effective_knowledge_llm_config():
    settings = SkillSettings(
        openai_api_key="key1",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
        knowledge_llm_mode="same_as_main",
    )
    config = settings.effective_knowledge_llm_config
    assert config["api_key"] == "key1"
    assert config["model"] == "gpt-4o-mini"


def test_config_effective_knowledge_llm_custom():
    settings = SkillSettings(
        openai_api_key="key1",
        knowledge_llm_mode="custom",
        knowledge_llm_enabled=True,
        knowledge_llm_api_key="key2",
        knowledge_llm_base_url="https://custom.api.com",
        knowledge_llm_model="custom-model",
    )
    config = settings.effective_knowledge_llm_config
    assert config["api_key"] == "key2"
    assert config["model"] == "custom-model"


def test_config_knowledge_index_dir():
    settings = SkillSettings()
    assert settings.knowledge_index_dir == settings.data_dir / "knowledge_index"


def test_config_output_dir():
    settings = SkillSettings(obsidian_output_dir="/tmp/obsidian")
    assert settings.output_dir == Path("/tmp/obsidian")
    settings2 = SkillSettings(obsidian_output_dir="")
    assert settings2.output_dir is None


def test_pipeline_result_new_fields():
    from video_lecture_skill.models import PipelineResult
    result = PipelineResult(
        overview="概览",
        key_points=["要点1"],
        knowledge_note_markdown="## 笔记",
        timeline=[{"title": "章节1"}],
        segment_summaries=["摘要1"],
        mindmap_status="ready",
        tags=["Python"],
    )
    assert result.overview == "概览"
    assert result.key_points == ["要点1"]
    assert result.knowledge_note_markdown == "## 笔记"
    assert result.mindmap_status == "ready"
    assert result.tags == ["Python"]


def test_task_record_new_fields():
    from video_lecture_skill.models import TaskRecord, TaskInput
    record = TaskRecord(
        task_input=TaskInput(url="https://example.com"),
        video_id="v1",
        page_number=2,
        page_title="P2 测试",
    )
    assert record.video_id == "v1"
    assert record.page_number == 2
    assert record.page_title == "P2 测试"


def test_task_input_new_fields():
    from video_lecture_skill.models import TaskInput
    task = TaskInput(
        url="https://example.com",
        input_type=InputType.URL,
        page_number=3,
        source_transcript="之前的转写文本",
    )
    assert task.input_type == InputType.URL
    assert task.page_number == 3
    assert task.source_transcript == "之前的转写文本"
