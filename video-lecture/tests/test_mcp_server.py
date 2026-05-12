from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from video_lecture_skill.models import TranscribeMode


def _make_success_result() -> dict:
    return {
        "success": True,
        "task_id": "test123",
        "status": "completed",
        "lecture_md": "# Test Lecture\n\n## 概述\n\nThis is a test overview.",
        "mindmap_mermaid": "mindmap\n  root\n    child1\n    child2",
        "transcript": "[00:00] Hello world\n[00:05] This is a test",
        "result_json": "{}",
        "lecture_title": "Test Lecture",
        "sections_count": 3,
        "transcript_chars": 50,
        "artifacts": {
            "transcript_path": "/tmp/test/transcript.txt",
            "lecture_md_path": "/tmp/test/lecture.md",
            "mindmap_mmd_path": "/tmp/test/mindmap.mmd",
            "result_json_path": "/tmp/test/result.json",
        },
        "events": [],
    }


def _make_failure_result() -> dict:
    return {
        "success": False,
        "task_id": "test456",
        "status": "failed",
        "error": "视频下载失败：Connection refused",
        "error_detail": "Connection refused",
        "events": [],
    }


def test_truncate_short():
    from mcp_server import _truncate
    assert _truncate("hello", 100) == "hello"


def test_truncate_long():
    from mcp_server import _truncate
    long_text = "a" * 100
    result = _truncate(long_text, 50)
    assert len(result) < 100
    assert "已截断" in result
    assert result.startswith("a" * 50)


def test_truncate_exact():
    from mcp_server import _truncate
    text = "a" * 50
    assert _truncate(text, 50) == text


def test_get_service_creates_instance():
    import mcp_server
    mcp_server._reset_service()
    service = mcp_server._get_service()
    assert service is not None
    assert mcp_server._service is service
    mcp_server._reset_service()


def test_get_service_reuses_instance():
    import mcp_server
    mcp_server._reset_service()
    s1 = mcp_server._get_service()
    s2 = mcp_server._get_service()
    assert s1 is s2
    mcp_server._reset_service()


def test_reset_service():
    import mcp_server
    mcp_server._reset_service()
    s1 = mcp_server._get_service()
    mcp_server._reset_service()
    s2 = mcp_server._get_service()
    assert s1 is not s2
    mcp_server._reset_service()


def test_resolve_transcribe_mode():
    from mcp_server import _resolve_transcribe_mode
    assert _resolve_transcribe_mode(None) is None
    assert _resolve_transcribe_mode("") is None
    assert _resolve_transcribe_mode("cloud") == TranscribeMode.CLOUD
    assert _resolve_transcribe_mode("API") == TranscribeMode.CLOUD
    assert _resolve_transcribe_mode("OpenAI") == TranscribeMode.CLOUD
    assert _resolve_transcribe_mode("local") == TranscribeMode.LOCAL
    assert _resolve_transcribe_mode("invalid") is None


def test_make_service_with_mode():
    import mcp_server
    mcp_server._reset_service()
    service = mcp_server._make_service_with_mode(TranscribeMode.CLOUD)
    assert service is not None
    assert service.settings.transcribe_mode == TranscribeMode.CLOUD
    mcp_server._reset_service()


@pytest.mark.asyncio
async def test_get_capabilities():
    from mcp_server import get_capabilities, _reset_service
    _reset_service()
    result = await get_capabilities()
    data = json.loads(result)
    assert "supported_platforms" in data
    assert "bilibili" in data["supported_platforms"]
    assert "transcribe_modes" in data
    assert "current_config" in data
    assert data["current_config"]["transcribe_mode"] in ("local", "cloud")
    _reset_service()


@pytest.mark.asyncio
async def test_process_video_success():
    from mcp_server import process_video, _reset_service
    _reset_service()
    mock_result = _make_success_result()

    with patch("mcp_server._get_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_service.settings = MagicMock()
        mock_get_service.return_value = mock_service

        result = await process_video(url="https://www.bilibili.com/video/BV1test")
        data = json.loads(result)

    assert data["success"] is True
    assert data["lecture_title"] == "Test Lecture"
    assert data["sections_count"] == 3
    assert "lecture_md" in data
    assert "mindmap_mermaid" in data
    assert "transcript" in data
    _reset_service()


@pytest.mark.asyncio
async def test_process_video_failure():
    from mcp_server import process_video, _reset_service
    _reset_service()
    mock_result = _make_failure_result()

    with patch("mcp_server._get_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_service.settings = MagicMock()
        mock_get_service.return_value = mock_service

        result = await process_video(url="https://invalid.url/video")
        data = json.loads(result)

    assert data["success"] is False
    assert "error" in data
    _reset_service()


@pytest.mark.asyncio
async def test_process_video_with_transcribe_mode():
    from mcp_server import process_video, _reset_service
    _reset_service()
    mock_result = _make_success_result()

    with patch("mcp_server._make_service_with_mode") as mock_make:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_make.return_value = mock_service

        result = await process_video(
            url="https://www.bilibili.com/video/BV1test",
            transcribe_mode="cloud",
        )
        data = json.loads(result)

    assert data["success"] is True
    mock_make.assert_called_once_with(TranscribeMode.CLOUD)
    _reset_service()


@pytest.mark.asyncio
async def test_get_lecture_only_success():
    from mcp_server import get_lecture_only, _reset_service
    _reset_service()
    mock_result = _make_success_result()

    with patch("mcp_server._get_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_get_service.return_value = mock_service

        result = await get_lecture_only(url="https://www.bilibili.com/video/BV1test")
        data = json.loads(result)

    assert data["success"] is True
    assert "lecture_md" in data
    assert "mindmap_mermaid" not in data
    _reset_service()


@pytest.mark.asyncio
async def test_get_mindmap_only_success():
    from mcp_server import get_mindmap_only, _reset_service
    _reset_service()
    mock_result = _make_success_result()

    with patch("mcp_server._get_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_get_service.return_value = mock_service

        result = await get_mindmap_only(url="https://www.bilibili.com/video/BV1test")
        data = json.loads(result)

    assert data["success"] is True
    assert "mindmap_mermaid" in data
    assert "lecture_md" not in data
    _reset_service()


@pytest.mark.asyncio
async def test_save_results_success():
    from mcp_server import save_results, _reset_service
    _reset_service()
    mock_result = _make_success_result()

    with patch("mcp_server._get_service") as mock_get_service:
        mock_service = MagicMock()
        mock_service.process_and_wait.return_value = mock_result
        mock_get_service.return_value = mock_service

        result = await save_results(
            url="https://www.bilibili.com/video/BV1test",
            output_dir="/tmp/test-output",
        )
        data = json.loads(result)

    assert data["success"] is True
    assert "saved_files" in data
    _reset_service()


def test_get_config_resource():
    from mcp_server import config_resource, _reset_service
    _reset_service()
    result = config_resource()
    data = json.loads(result)
    assert "transcribe_mode" in data
    assert "whisper_model" in data
    assert "openai_model" in data
    assert "data_dir" in data
    _reset_service()


def test_video_lecture_prompt():
    from mcp_server import video_lecture_prompt
    result = video_lecture_prompt(url="https://test.com/video", title="Test Title")
    assert "https://test.com/video" in result
    assert "Test Title" in result
    assert "讲义" in result
    assert "思维导图" in result


def test_video_lecture_prompt_no_title():
    from mcp_server import video_lecture_prompt
    result = video_lecture_prompt(url="https://test.com/video")
    assert "https://test.com/video" in result
    assert "讲义" in result


def test_mcp_server_metadata():
    from mcp_server import mcp
    assert mcp.name == "video-lecture-skill"
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    assert "process_video" in tool_names
    assert "get_lecture_only" in tool_names
    assert "get_mindmap_only" in tool_names
    assert "save_results" in tool_names
    assert "get_capabilities" in tool_names
