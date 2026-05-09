from __future__ import annotations

import asyncio
import json
import logging

from mcp.server.fastmcp import FastMCP

from video_lecture_skill import (
    SkillSettings,
    VideoLectureService,
    format_error_for_user,
)
from video_lecture_skill.models import (
    KnowledgeChatHistoryItem,
    TranscribeMode,
)

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
        "核心功能：\n"
        "1. process_video: 处理视频，生成讲义和思维导图\n"
        "2. resummary: 复用已有转写文本重新生成摘要\n"
        "3. aggregate_summary: 汇总多个任务结果生成合集总结\n"
        "4. export_obsidian: 导出为 Obsidian 格式笔记（含 frontmatter）\n"
        "5. search_knowledge: 语义搜索知识库\n"
        "6. ask_knowledge: 基于知识库的 RAG 问答\n"
        "7. add_tag / remove_tag / get_tags: 标签管理\n"
        "8. auto_tag: LLM 自动打标签\n"
        "9. get_tag_network: 获取标签共现网络\n"
        "10. get_knowledge_stats: 知识库统计信息\n"
        "11. setup_check: 首次使用环境检查\n"
        "12. get_capabilities: 查询支持的平台和功能\n\n"
        "首次使用建议先调用 setup_check 确认环境就绪。\n\n"
        "注意事项：\n"
        "- 首次使用本地转写模式会下载 Whisper 模型文件\n"
        "- 需要配置 VLEC_OPENAI_API_KEY 才能使用 LLM 生成高质量讲义\n"
        "- 知识库功能需设置 VLEC_KNOWLEDGE_ENABLED=true 并安装 chromadb + sentence-transformers\n"
        "- Obsidian 导出需设置 VLEC_OBSIDIAN_OUTPUT_DIR 或调用时指定 output_dir\n"
        "- LLM 不可用时会自动降级为本地规则生成\n\n"
        "详细文档见 references/ 目录：REFERENCE.md（技术参考）、CAPABILITIES.md（能力矩阵）、CONFIGURATION.md（配置指南）"
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
    page_number: int | None = None,
) -> str:
    """将视频转换为结构化课程讲义和思维导图。

    输入视频链接，自动完成：下载视频 → 提取音频 → 语音转写 → 生成讲义 → 生成思维导图。
    支持 B站多P视频（通过 page_number 指定分P号）。
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
        page_number: B站多P视频分P号，可选，默认处理第1P
    """
    effective_mode = _resolve_transcribe_mode(transcribe_mode)
    service = _make_service_with_mode(effective_mode) if effective_mode else _get_service()

    def _run():
        return service.process_and_wait(url=url, title=title, language=language, page_number=page_number)

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
        "video_id": result.get("video_id", ""),
        "lecture_title": result.get("lecture_title", ""),
        "sections_count": result.get("sections_count", 0),
        "transcript_chars": result.get("transcript_chars", 0),
        "lecture_md": _truncate(result.get("lecture_md", ""), 12000),
        "mindmap_mermaid": _truncate(result.get("mindmap_mermaid", ""), 4000),
        "transcript": _truncate(result.get("transcript", ""), 6000),
        "artifacts": result.get("artifacts", {}),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def resummary(task_id: str) -> str:
    """复用已有任务的转写文本，重新生成讲义和思维导图。

    适用于对之前处理结果不满意，想用不同的 LLM 参数重新生成摘要的场景。
    会保留原始转写文本，只重新运行讲义生成和思维导图步骤。

    Args:
        task_id: 之前 process_video 返回的任务 ID
    """
    service = _get_service()

    def _run():
        return service.resummary(task_id=task_id)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def aggregate_summary(task_ids: str) -> str:
    """汇总多个任务的结果，生成合集总结讲义。

    适用于多P视频分别处理后，需要生成一个整体总结的场景。
    会将各任务的概览、要点、笔记合并后，由 LLM 生成综合讲义。

    Args:
        task_ids: 要汇总的任务 ID 列表，用逗号分隔，如 "task1,task2,task3"
    """
    service = _get_service()
    ids = [tid.strip() for tid in task_ids.split(",") if tid.strip()]

    def _run():
        return service.aggregate_summary(task_ids=ids)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def export_obsidian(
    task_id: str,
    output_dir: str | None = None,
) -> str:
    """将任务结果导出为 Obsidian 格式的 Markdown 笔记。

    生成的笔记包含 YAML frontmatter（标题、来源、平台、标签等元数据），
    以及核心概览、关键要点、章节时间线、知识笔记和思维导图等结构化内容。

    Args:
        task_id: 之前 process_video 返回的任务 ID
        output_dir: 输出目录的绝对路径，可选，默认使用 VLEC_OBSIDIAN_OUTPUT_DIR 配置
    """
    service = _get_service()

    def _run():
        return service.export_obsidian_note(task_id=task_id, output_dir=output_dir)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def search_knowledge(
    query: str,
    limit: int = 10,
    tags: str | None = None,
) -> str:
    """在知识库中语义搜索相关视频内容。

    基于向量相似度搜索已处理视频的摘要、章节和知识笔记。
    需要先启用知识库（VLEC_KNOWLEDGE_ENABLED=true）并处理过至少一个视频。

    Args:
        query: 搜索查询，支持自然语言
        limit: 返回结果数量上限，默认 10
        tags: 标签过滤，用逗号分隔，如 "Python,机器学习"
    """
    service = _get_service()
    tag_filter = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    def _run():
        return service.search_knowledge(query=query, limit=limit, tag_filter=tag_filter)

    try:
        results = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "query": query,
        "results": [r.model_dump(mode="json") for r in results],
        "total": len(results),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def ask_knowledge(
    query: str,
    context_limit: int = 5,
    history: str | None = None,
) -> str:
    """基于知识库的 RAG 问答。

    先语义搜索相关视频片段，再由 LLM 基于检索到的内容生成回答。
    支持多轮对话上下文。需要先启用知识库（VLEC_KNOWLEDGE_ENABLED=true）。

    Args:
        query: 用户问题
        context_limit: 检索上下文片段数量，默认 5
        history: 对话历史，JSON 数组格式，如 [{"role":"user","content":"之前的问题"},{"role":"assistant","content":"之前的回答"}]
    """
    service = _get_service()
    chat_history: list[KnowledgeChatHistoryItem] = []
    if history:
        try:
            items = json.loads(history)
            for item in items:
                chat_history.append(KnowledgeChatHistoryItem(
                    role=str(item.get("role", "user")),
                    content=str(item.get("content", "")),
                ))
        except (json.JSONDecodeError, AttributeError):
            pass

    def _run():
        return service.ask_knowledge(query=query, context_limit=context_limit, history=chat_history or None)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "query": result.query,
        "answer": result.answer,
        "sources": [s.model_dump(mode="json") for s in result.sources],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_tag(video_id: str, tag: str) -> str:
    """为视频添加标签。

    Args:
        video_id: 视频 ID
        tag: 标签名称
    """
    service = _get_service()
    success = service.add_tag(video_id, tag)
    return json.dumps({"success": success, "video_id": video_id, "tag": tag}, ensure_ascii=False)


@mcp.tool()
async def remove_tag(video_id: str, tag: str) -> str:
    """移除视频的指定标签。

    Args:
        video_id: 视频 ID
        tag: 要移除的标签名称
    """
    service = _get_service()
    success = service.remove_tag(video_id, tag)
    return json.dumps({"success": success, "video_id": video_id, "tag": tag}, ensure_ascii=False)


@mcp.tool()
async def get_tags(video_id: str | None = None) -> str:
    """获取标签列表。

    如果指定 video_id，返回该视频的标签；否则返回所有标签及其计数。

    Args:
        video_id: 视频 ID，可选
    """
    service = _get_service()
    if video_id:
        records = service.get_tags_for_video(video_id)
        return json.dumps({
            "video_id": video_id,
            "tags": [r.model_dump(mode="json") for r in records],
        }, ensure_ascii=False, indent=2)
    tags = service.get_all_tags()
    return json.dumps({
        "items": [t.model_dump(mode="json") for t in tags],
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def auto_tag(video_id: str, content: str) -> str:
    """使用 LLM 自动为视频生成标签。

    根据视频摘要和知识笔记内容，自动生成 3-8 个中文标签。

    Args:
        video_id: 视频 ID
        content: 视频摘要内容（概览、要点、笔记等），用于生成标签
    """
    service = _get_service()

    def _run():
        return service.auto_tag_video(video_id, content)

    try:
        tags = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps({"success": True, "video_id": video_id, "tags": tags}, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_tag_network(
    selected_tags: str | None = None,
    max_tags: int = 12,
) -> str:
    """获取标签共现网络数据。

    返回标签节点和标签之间的共现关系链接，可用于可视化标签网络。
    如果指定 selected_tags，则聚焦模式返回相关标签和视频。

    Args:
        selected_tags: 选中的标签，用逗号分隔，如 "Python,机器学习"，可选
        max_tags: 最大显示标签数，默认 12
    """
    service = _get_service()
    tags = [t.strip() for t in selected_tags.split(",") if t.strip()] if selected_tags else None

    def _run():
        return service.get_tag_network(selected_tags=tags, max_tags=max_tags)

    try:
        result = await _run_sync(_run)
    except Exception as exc:
        return json.dumps({"success": False, "error": format_error_for_user(exc)}, ensure_ascii=False)

    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_knowledge_stats() -> str:
    """获取知识库统计信息。

    返回已处理视频数量、索引块数量、标签数量等统计数据。
    """
    service = _get_service()
    stats = service.get_knowledge_stats()
    return json.dumps(stats.model_dump(mode="json"), ensure_ascii=False, indent=2)


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
async def setup_check() -> str:
    """首次使用环境检查，验证所有必需和可选依赖是否就绪。

    返回每个依赖项的状态（✅ 就绪 / ❌ 缺失 / ⚠️ 可选未安装）。
    建议在首次使用 video-lecture-skill 前调用此工具确认环境。
    """
    import shutil
    import sys

    checks: list[dict[str, str]] = []

    major, minor = sys.version_info[:2]
    checks.append({
        "name": "Python >= 3.11",
        "status": "ok" if major >= 3 and minor >= 11 else "missing",
        "detail": f"Python {major}.{minor}",
        "required": "true",
    })

    ffmpeg_path = shutil.which("ffmpeg")
    checks.append({
        "name": "ffmpeg",
        "status": "ok" if ffmpeg_path else "missing",
        "detail": f"found at {ffmpeg_path}" if ffmpeg_path else "not found",
        "required": "true",
    })

    try:
        import yt_dlp
        checks.append({"name": "yt-dlp", "status": "ok", "detail": "installed", "required": "true"})
    except ImportError:
        checks.append({"name": "yt-dlp", "status": "missing", "detail": "pip install yt-dlp", "required": "true"})

    try:
        import faster_whisper
        checks.append({"name": "faster-whisper", "status": "ok", "detail": "installed", "required": "true"})
    except ImportError:
        checks.append({"name": "faster-whisper", "status": "missing", "detail": "pip install faster-whisper", "required": "true"})

    import os
    api_key = os.environ.get("VLEC_OPENAI_API_KEY", "")
    checks.append({
        "name": "VLEC_OPENAI_API_KEY",
        "status": "ok" if api_key else "missing",
        "detail": "set" if api_key else "not set — export VLEC_OPENAI_API_KEY=sk-...",
        "required": "true",
    })

    try:
        import chromadb
        checks.append({"name": "chromadb", "status": "ok", "detail": "installed", "required": "false"})
    except ImportError:
        checks.append({"name": "chromadb", "status": "optional", "detail": "pip install chromadb (for knowledge base)", "required": "false"})

    try:
        import sentence_transformers
        checks.append({"name": "sentence-transformers", "status": "ok", "detail": "installed", "required": "false"})
    except ImportError:
        checks.append({"name": "sentence-transformers", "status": "optional", "detail": "pip install sentence-transformers (for knowledge base)", "required": "false"})

    all_required_ok = all(c["status"] == "ok" for c in checks if c["required"] == "true")

    return json.dumps({
        "success": True,
        "all_required_ok": all_required_ok,
        "checks": checks,
        "recommendation": "All required dependencies ready." if all_required_ok else "Some required dependencies are missing. Please install them.",
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
        "knowledge_enabled": service.settings.knowledge_enabled,
        "obsidian_output_dir": service.settings.obsidian_output_dir,
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
        "knowledge_enabled": s.knowledge_enabled,
        "knowledge_embedding_model": s.knowledge_embedding_model,
        "obsidian_output_dir": s.obsidian_output_dir,
        "export_target": s.export_target,
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
    parts.append("4. 如需导出为 Obsidian 笔记，可使用 export_obsidian 工具")
    parts.append("5. 如需搜索知识库，可使用 search_knowledge 工具")
    return "\n".join(parts)


def main():
    logger.info("starting video-lecture-skill MCP server")
    mcp.run()


if __name__ == "__main__":
    main()
