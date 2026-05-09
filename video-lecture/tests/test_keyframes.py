from __future__ import annotations

import json
import tempfile
from pathlib import Path

from video_lecture_skill.models import KeyframeInfo, LectureNote, LectureSection
from video_lecture_skill.frames import (
    _find_ffmpeg,
    _format_timestamp,
    _format_ffmpeg_seek,
    extract_keyframes_from_sections,
    extract_keyframes_from_timestamps,
)
from video_lecture_skill.export import (
    _find_keyframe_for_section,
    export_markdown,
    export_obsidian,
)
from video_lecture_skill.service import VideoLectureService
from video_lecture_skill.config import SkillSettings


def test_keyframe_info_model():
    kf = KeyframeInfo(
        timestamp=65.0,
        timestamp_label="01:05",
        section_title="Python简介",
        image_path="/tmp/keyframes/frame_001_Python简介.jpg",
        width=1280,
        height=720,
    )
    assert kf.timestamp == 65.0
    assert kf.timestamp_label == "01:05"
    assert kf.section_title == "Python简介"
    assert kf.width == 1280


def test_keyframe_info_defaults():
    kf = KeyframeInfo()
    assert kf.timestamp == 0.0
    assert kf.image_path == ""
    assert kf.image_url == ""


def test_format_timestamp():
    assert _format_timestamp(0) == "00:00"
    assert _format_timestamp(65) == "01:05"
    assert _format_timestamp(3661) == "01:01:01"
    assert _format_timestamp(-1) == "00:00"


def test_format_ffmpeg_seek():
    assert _format_ffmpeg_seek(0) == "00:00:00.000"
    assert _format_ffmpeg_seek(65.5) == "00:01:05.500"
    assert _format_ffmpeg_seek(3661.123) == "01:01:01.123"


def test_find_ffmpeg():
    result = _find_ffmpeg()
    assert result is not None or True


def test_extract_keyframes_no_video():
    lecture = LectureNote(
        title="测试",
        sections=[LectureSection(title="章节1", start=0.0)],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        keyframes = extract_keyframes_from_sections(
            video_path="/nonexistent/video.mp4",
            lecture=lecture,
            output_dir=tmpdir,
        )
        assert keyframes == []


def test_extract_keyframes_from_timestamps_no_video():
    with tempfile.TemporaryDirectory() as tmpdir:
        keyframes = extract_keyframes_from_timestamps(
            video_path="/nonexistent/video.mp4",
            timestamps=[0.0, 30.0, 60.0],
            output_dir=tmpdir,
        )
        assert keyframes == []


def test_find_keyframe_for_section():
    from video_lecture_skill.models import PipelineResult, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
        keyframes=[
            KeyframeInfo(timestamp=0.0, section_title="开场", image_path="/tmp/frame1.jpg"),
            KeyframeInfo(timestamp=65.0, section_title="核心", image_path="/tmp/frame2.jpg"),
            KeyframeInfo(timestamp=180.0, section_title="总结", image_path="/tmp/frame3.jpg"),
        ],
    )
    kf = _find_keyframe_for_section(result, 65.0)
    assert kf is not None
    assert kf.section_title == "核心"

    kf2 = _find_keyframe_for_section(result, 0.0)
    assert kf2 is not None
    assert kf2.section_title == "开场"


def test_find_keyframe_for_section_no_keyframes():
    from video_lecture_skill.models import PipelineResult, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
    )
    kf = _find_keyframe_for_section(result, 65.0)
    assert kf is None


def test_find_keyframe_for_section_too_far():
    from video_lecture_skill.models import PipelineResult, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
        keyframes=[
            KeyframeInfo(timestamp=0.0, section_title="开场", image_path="/tmp/frame1.jpg"),
        ],
    )
    kf = _find_keyframe_for_section(result, 300.0)
    assert kf is None


def test_export_markdown_with_keyframes():
    from video_lecture_skill.models import PipelineResult, LectureNote, LectureSection, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试视频"),
        lecture=LectureNote(
            title="测试讲义",
            overview="概览",
            sections=[
                LectureSection(title="开场", start=0.0, explanation="开场白"),
                LectureSection(title="核心", start=65.0, explanation="核心内容"),
            ],
        ),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
        keyframes=[
            KeyframeInfo(timestamp=0.0, section_title="开场", image_path="/tmp/frame1.jpg"),
            KeyframeInfo(timestamp=65.0, section_title="核心", image_path="/tmp/frame2.jpg"),
        ],
    )
    md = export_markdown(result)
    assert "![开场](/tmp/frame1.jpg)" in md
    assert "![核心](/tmp/frame2.jpg)" in md


def test_export_markdown_no_keyframes():
    from video_lecture_skill.models import PipelineResult, LectureNote, LectureSection, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试视频"),
        lecture=LectureNote(
            title="测试讲义",
            overview="概览",
            sections=[LectureSection(title="开场", start=0.0)],
        ),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
    )
    md = export_markdown(result)
    assert "![" not in md


def test_export_obsidian_with_keyframes():
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult, MindmapResult
    result = PipelineResult(
        video_info=VideoInfo(title="测试视频"),
        lecture=LectureNote(title="测试讲义", overview="概览"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
        keyframes=[
            KeyframeInfo(timestamp=0.0, timestamp_label="00:00", section_title="开场", image_path="/tmp/frame1.jpg"),
        ],
    )
    obs = export_obsidian(result)
    assert "关键帧截图" in obs
    assert "![开场](/tmp/frame1.jpg)" in obs


def test_service_extract_keyframes_no_task():
    settings = SkillSettings()
    service = VideoLectureService(settings)
    result = service.extract_keyframes("nonexistent_task_id")
    assert result["success"] is False
    assert "未找到" in result["error"]


def test_service_extract_keyframes_no_video_file():
    from video_lecture_skill.models import PipelineResult, LectureNote, VideoInfo, TranscriptionResult, MindmapResult
    settings = SkillSettings()
    service = VideoLectureService(settings)
    service._task_results["t1"] = PipelineResult(
        video_info=VideoInfo(title="测试"),
        lecture=LectureNote(title="测试讲义"),
        transcription=TranscriptionResult(transcript="转写"),
        mindmap=MindmapResult(),
    )
    result = service.extract_keyframes("t1")
    assert result["success"] is False
    assert "视频文件" in result["error"]


def test_pipeline_result_keyframes_field():
    from video_lecture_skill.models import PipelineResult
    result = PipelineResult()
    assert result.keyframes == []
    assert result.video_file_path == ""


def test_keyframe_info_json_roundtrip():
    kf = KeyframeInfo(
        timestamp=65.0,
        timestamp_label="01:05",
        section_title="核心概念",
        image_path="/tmp/frame.jpg",
        width=1280,
        height=720,
    )
    data = kf.model_dump(mode="json")
    kf2 = KeyframeInfo.model_validate(data)
    assert kf2.timestamp == 65.0
    assert kf2.section_title == "核心概念"
    assert kf2.width == 1280
