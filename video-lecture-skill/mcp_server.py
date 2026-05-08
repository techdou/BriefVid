from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from video_lecture_skill import (
    SkillSettings,
    VideoLectureService,
    format_error_for_user,
)
from video_lecture_skill.models import TranscribeMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("video_lecture_mcp")

mcp = FastMCP(
    "video-lecture-skill",
    instructions=(
        "Video Lecture Skill - 视频转讲义与思维导图工具。\n"
        "支持 B站、YouTube、抖音等多平台视频链接，自动完成下载、转码、语音转写、"
        "LLM 生成结构化讲义和 Mermaid 思维导图。\n\n"
        "使用流程：\n"
        "1. 调用 process_video 提交视频链接，等待处理完成\n"
        "2. 处理结果中直接包含讲义(lecture_md)、思维导图(mindmap_mermaid)和转写文本(transcript)\n"
        "3. 如需保存到文件，调用 save_results 指定输出目录\n"
        "4. 调用 get_capabilities 查询支持的平台和功能\n\n"
        "注意事项：\n"
        "- 首次使用本地转写模式会下载 Whisper 模型文件\n"
        "- 需要配置 VLEC_OPENAI_API_KEY 才能使用 LLM 生成高质量讲义\n"
        "- LLM 不可用时会自动降级为本地规则生成"
    ),
)

_settings: SkillSettings | None = None
_service: VideoLectureService | None = None


def _get_service() -> VideoLectureService:
    global _settings, _service
    if _service is None:
        _settings = SkillSettings()
        _settings.ensure_dirs()
        _service = VideoLectureService(_settings)
    return _service


def _reset_service() -> None:
    global _settings, _service
    _service = None
    _settings = None


def _make_service_with_mode(transcribe_mode: TranscribeMode) -> VideoLectureService:
    base = _get_service()
    new_settings = base.settings.model_copy(update={"transcribe_mode": transcribe_mode})
    return VideoLectureService(new_settings)


def _truncate(value: str, max_len: int = 8000) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + f"\n...[已截断，原文共 {len(value)} 字]"


def _resolve_transcribe_mode(mode_str: str | None) -> TranscribeMode | None:
    if not mode_str:
        return None
    normalized = mode_str.strip().lower()
    if normalized in ("cloud", "api", "openai"):
        return TranscribeMode.CLOUD
    if normalized == "local":
        return TranscribeMode.LOCAL
    return None


async def _run_sync(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@mcp.tool()
async def process_video(
    url: str,
    title: str | None = None,
    language: str = "zh",
    transcribe_mode: str | None = None,
) -> str:
    """将视频转换为结构化课程讲义和思维导图。

    输入视频链接，自动完成：下载视频 → 提取音频 → 语音转写 → 生成讲义 → 生成思维导图。
    处理时间取决于视频长度，通常需要 1-5 分钟。

    Args:
        url: 视频链接，支持以下格式：
            - B站: https://www.bilibili.com/video/BV1xxx 或直接 BV1xxx
            - YouTube: https://www.youtube.com/watch?v=xxx 或 https://youtu.be/xxx
            - 抖音: https://www.douyin.com/video/xxx
            - 其他: 任何 yt-dlp 支持的链接
        title: 视频标题，可选，默认自动从视频元数据获取
        language: 转写语言代码，默认 zh，可选 en/ja/ko/auto
        transcribe_mode: 转写模式，可选 local(本地Whisper) 或 cloud(云API)，默认使用配置值
    """
    effective_mode = _resolve_transcribe_mode(transcribe_mode)
    service = _make_service_with_mode(effective_mode) if effective_mode else _get_service()

    def _run():
        return service.process_and_wait(url=url, title=title, language=language)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        logger.exception("process_video failed: %s", exc)
        return json.dumps({
            "success": False,
            "error": format_error_for_user(exc),
            "error_detail": str(exc),
        }, ensure_ascii=False, indent=2)

    if not result.get("success"):
        return json.dumps({
            "success": False,
            "error": result.get("error", "Unknown error"),
            "task_id": result.get("task_id"),
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "success": True,
        "task_id": result.get("task_id"),
        "lecture_title": result.get("lecture_title", ""),
        "sections_count": result.get("sections_count", 0),
        "transcript_chars": result.get("transcript_chars", 0),
        "lecture_md": _truncate(result.get("lecture_md", ""), 12000),
        "mindmap_mermaid": _truncate(result.get("mindmap_mermaid", ""), 4000),
        "transcript": _truncate(result.get("transcript", ""), 6000),
        "artifacts": result.get("artifacts", {}),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_lecture_only(
    url: str,
    title: str | None = None,
    language: str = "zh",
) -> str:
    """仅获取视频的课程讲义（Markdown格式），不包含转写原文。

    适用于只需要讲义、不需要思维导图和转写文本的场景，返回内容更精简。

    Args:
        url: 视频链接（同 process_video 支持的格式）
        title: 视频标题，可选
        language: 转写语言代码，默认 zh
    """
    service = _get_service()

    def _run():
        return service.process_and_wait(url=url, title=title, language=language)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    if not result.get("success"):
        return json.dumps({"success": False, "error": result.get("error")}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "lecture_title": result.get("lecture_title"),
        "sections_count": result.get("sections_count"),
        "lecture_md": _truncate(result.get("lecture_md", ""), 16000),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_mindmap_only(
    url: str,
    title: str | None = None,
    language: str = "zh",
) -> str:
    """仅获取视频的思维导图（Mermaid格式）。

    适用于只需要思维导图、不需要完整讲义的场景。

    Args:
        url: 视频链接（同 process_video 支持的格式）
        title: 视频标题，可选
        language: 转写语言代码，默认 zh
    """
    service = _get_service()

    def _run():
        return service.process_and_wait(url=url, title=title, language=language)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    if not result.get("success"):
        return json.dumps({"success": False, "error": result.get("error")}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "lecture_title": result.get("lecture_title"),
        "mindmap_mermaid": _truncate(result.get("mindmap_mermaid", ""), 8000),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def save_results(
    url: str,
    output_dir: str,
    title: str | None = None,
    language: str = "zh",
) -> str:
    """处理视频并将结果保存到指定目录的文件中。

    会在输出目录下生成以下文件：
    - transcript.txt: 带时间戳的转写文本
    - lecture.md: Markdown 格式课程讲义
    - mindmap.mmd: Mermaid 格式思维导图
    - result.json: 完整结果 JSON

    Args:
        url: 视频链接（同 process_video 支持的格式）
        output_dir: 输出目录的绝对路径
        title: 视频标题，可选
        language: 转写语言代码，默认 zh
    """
    service = _get_service()

    def _run():
        return service.process_and_wait(url=url, title=title, language=language, output_dir=output_dir)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    if not result.get("success"):
        return json.dumps({"success": False, "error": result.get("error")}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "lecture_title": result.get("lecture_title"),
        "sections_count": result.get("sections_count"),
        "saved_files": result.get("artifacts", {}),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_capabilities() -> str:
    """查询 video-lecture-skill 支持的平台、转写模式和输出格式。

    返回当前 Skill 的能力描述、支持的视频平台列表和资源限制信息。
    """
    service = _get_service()
    caps = service.get_capabilities()
    caps["current_config"] = {
        "transcribe_mode": service.settings.transcribe_mode.value,
        "whisper_model": service.settings.whisper_model,
        "openai_model": service.settings.openai_model,
        "language": service.settings.language,
        "data_dir": str(service.settings.data_dir),
    }
    return json.dumps(caps, ensure_ascii=False, indent=2)


@mcp.resource("video-lecture://config")
def get_config() -> str:
    """获取当前 video-lecture-skill 的配置信息。"""
    service = _get_service()
    s = service.settings
    return json.dumps({
        "host": s.host,
        "port": s.port,
        "data_dir": str(s.data_dir),
        "transcribe_mode": s.transcribe_mode.value,
        "whisper_model": s.whisper_model,
        "whisper_device": s.whisper_device,
        "openai_base_url": s.openai_base_url,
        "openai_model": s.openai_model,
        "language": s.language,
        "output_formats": s.output_format_list,
    }, ensure_ascii=False, indent=2)


@mcp.prompt()
def video_lecture_prompt(url: str, title: str = "") -> str:
    """生成用于请求视频讲义整理的提示词模板。"""
    parts = ["请帮我将以下视频整理成结构化的课程讲义和思维导图。"]
    parts.append(f"视频链接：{url}")
    if title:
        parts.append(f"视频标题：{title}")
    parts.append("")
    parts.append("要求：")
    parts.append("1. 生成包含章节标题、核心概念、详细讲解、示例和思考题的 Markdown 讲义")
    parts.append("2. 生成 Mermaid 格式的思维导图，层级清晰")
    parts.append("3. 讲义内容忠实于视频原文，不编造信息")
    return "\n".join(parts)


def main():
    logger.info("starting video-lecture-skill MCP server")
    mcp.run()


if __name__ == "__main__":
    main()
