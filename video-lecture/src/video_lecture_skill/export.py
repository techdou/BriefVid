from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from video_lecture_skill.models import (
    KeyframeInfo,
    LectureNote,
    MindmapResult,
    PipelineResult,
    Segment,
    TranscriptionResult,
    VideoInfo,
    format_timestamp,
)


def _find_keyframe_for_section(result: PipelineResult, section_start: float) -> KeyframeInfo | None:
    if not result.keyframes:
        return None
    best = None
    best_diff = float("inf")
    for kf in result.keyframes:
        diff = abs(kf.timestamp - section_start)
        if diff < best_diff:
            best_diff = diff
            best = kf
    if best is not None and best_diff <= 30.0:
        return best
    return None


def export_markdown(result: PipelineResult) -> str:
    lecture = result.lecture
    lines: list[str] = []

    lines.append(f"# {lecture.title}")
    lines.append("")

    if lecture.overview:
        lines.append("## 概述")
        lines.append("")
        lines.append(lecture.overview)
        lines.append("")

    if lecture.prerequisites:
        lines.append("## 前置知识")
        lines.append("")
        for p in lecture.prerequisites:
            lines.append(f"- {p}")
        lines.append("")

    if lecture.sections:
        lines.append("## 讲义内容")
        lines.append("")
        for i, sec in enumerate(lecture.sections, 1):
            timestamp = format_timestamp(sec.start)
            lines.append(f"### {i}. {sec.title} `[{timestamp}]`")
            lines.append("")
            keyframe = _find_keyframe_for_section(result, sec.start)
            if keyframe:
                img_ref = keyframe.image_path or keyframe.image_url
                if img_ref:
                    lines.append(f"![{sec.title}]({img_ref})")
                    lines.append("")
            if sec.key_concepts:
                lines.append("**核心概念：** " + "、".join(sec.key_concepts))
                lines.append("")
            if sec.explanation:
                lines.append(sec.explanation)
                lines.append("")
            if sec.examples:
                lines.append("**示例：**")
                for ex in sec.examples:
                    lines.append(f"- {ex}")
                lines.append("")
            if sec.quiz:
                lines.append("**思考题：**")
                for q in sec.quiz:
                    lines.append(f"- {q}")
                lines.append("")

    if lecture.summary:
        lines.append("## 总结")
        lines.append("")
        lines.append(lecture.summary)
        lines.append("")

    if lecture.references:
        lines.append("## 延伸阅读")
        lines.append("")
        for r in lecture.references:
            lines.append(f"- {r}")
        lines.append("")

    if result.mindmap.mermaid:
        lines.append("## 思维导图")
        lines.append("")
        lines.append("```mermaid")
        lines.append(result.mindmap.mermaid)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def export_mermaid(result: PipelineResult) -> str:
    return result.mindmap.mermaid or ""


def export_json(result: PipelineResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def export_transcript(result: PipelineResult) -> str:
    return result.transcription.transcript


def export_to_files(result: PipelineResult, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    transcript_path = output_dir / "transcript.txt"
    transcript_path.write_text(export_transcript(result), encoding="utf-8")
    artifacts["transcript"] = str(transcript_path)

    lecture_path = output_dir / "lecture.md"
    lecture_path.write_text(export_markdown(result), encoding="utf-8")
    artifacts["lecture_md"] = str(lecture_path)

    if result.mindmap.mermaid:
        mindmap_path = output_dir / "mindmap.mmd"
        mindmap_path.write_text(export_mermaid(result), encoding="utf-8")
        artifacts["mindmap_mmd"] = str(mindmap_path)

    result_path = output_dir / "result.json"
    result_path.write_text(export_json(result), encoding="utf-8")
    artifacts["result_json"] = str(result_path)

    return artifacts


def _build_frontmatter(payload: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in payload.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=False)}")
            continue
        lines.append(f"{key}: {json.dumps(str(value or ''), ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _format_key_points(key_points: list[str]) -> str:
    items = [str(item).strip() for item in key_points if str(item).strip()]
    if not items:
        return "- 暂无关键要点。"
    return "\n".join(f"- {item}" for item in items)


def _format_timeline(timeline: list[dict[str, object]]) -> str:
    items: list[str] = []
    for entry in timeline:
        title = str(entry.get("title") or "").strip() or "未命名章节"
        summary = str(entry.get("summary") or "").strip()
        start = format_timestamp(entry.get("start"))
        line = f"- `{start}` **{title}**"
        if summary:
            line = f"{line}: {summary}"
        items.append(line)
    if not items:
        return "- 暂无章节时间线。"
    return "\n".join(items)


def _normalize_embedded_note(markdown: str, title: str) -> str:
    text = str(markdown or "").strip()
    if not text:
        return "暂无知识笔记正文。"
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    normalized = "\n".join(lines).strip()
    return normalized or "暂无知识笔记正文。"


def _build_markdown_body(
    *,
    title: str,
    overview: str,
    knowledge_note_markdown: str,
    key_points: list[str],
    timeline: list[dict[str, object]],
    mindmap_mermaid: str | None = None,
    keyframes: list[KeyframeInfo] | None = None,
) -> str:
    sections = [
        f"# {title}",
        "## 核心概览",
        str(overview or "").strip() or "暂无核心概览。",
        "## 关键要点",
        _format_key_points(key_points),
        "## 章节时间线",
        _format_timeline(timeline),
    ]
    if keyframes:
        frame_lines = ["## 关键帧截图"]
        for kf in keyframes:
            img_ref = kf.image_path or kf.image_url
            if not img_ref:
                continue
            label = f"{kf.timestamp_label} {kf.section_title}".strip()
            frame_lines.append(f"### {label}")
            frame_lines.append(f"![{kf.section_title}]({img_ref})")
            frame_lines.append("")
        if len(frame_lines) > 1:
            sections.extend(frame_lines)
    sections.extend([
        "## 知识笔记",
        _normalize_embedded_note(knowledge_note_markdown, title),
    ])
    if mindmap_mermaid:
        sections.extend([
            "## 思维导图",
            "```mermaid",
            mindmap_mermaid,
            "```",
        ])
    return "\n\n".join(section.strip() for section in sections if str(section).strip())


def export_obsidian(
    result: PipelineResult,
    *,
    source_url: str = "",
    platform: str = "",
    video_id: str = "",
    task_id: str = "",
    tags: list[str] | None = None,
    created_at: datetime | None = None,
) -> str:
    title = result.lecture.title or result.video_info.title or "视频笔记"
    body = _build_markdown_body(
        title=title,
        overview=result.overview or result.lecture.overview,
        knowledge_note_markdown=result.knowledge_note_markdown,
        key_points=result.key_points,
        timeline=result.timeline,
        mindmap_mermaid=result.mindmap.mermaid or None,
        keyframes=result.keyframes or None,
    )
    export_time = datetime.now()
    frontmatter = _build_frontmatter({
        "title": title,
        "source_url": str(source_url or result.video_info.url or ""),
        "platform": str(platform or result.video_info.platform or ""),
        "video_id": str(video_id or result.video_info.canonical_id or ""),
        "task_id": str(task_id or ""),
        "created_at": (created_at or export_time).isoformat(),
        "exported_at": export_time.isoformat(),
        "tags": [str(tag).strip() for tag in (tags or result.tags or []) if str(tag).strip()],
    })
    return f"{frontmatter}\n\n{body}".strip()


def export_obsidian_to_file(
    result: PipelineResult,
    output_dir: Path,
    *,
    source_url: str = "",
    platform: str = "",
    video_id: str = "",
    task_id: str = "",
    tags: list[str] | None = None,
    created_at: datetime | None = None,
) -> tuple[Path, bool]:
    output_dir.mkdir(parents=True, exist_ok=True)
    title = result.lecture.title or result.video_info.title or "视频笔记"
    safe_title = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|]', "", title)).strip(" .") or "VideoNote"
    export_time = datetime.now()
    file_name = f"{safe_title} {export_time.date().isoformat()}.md"

    content = export_obsidian(
        result,
        source_url=source_url,
        platform=platform,
        video_id=video_id,
        task_id=task_id,
        tags=tags,
        created_at=created_at,
    )

    base_candidate = output_dir / file_name
    suffix = base_candidate.suffix or ".md"
    stem = base_candidate.stem
    counter = 1
    while True:
        candidate = base_candidate if counter == 1 else output_dir / f"{stem} ({counter}){suffix}"
        try:
            with candidate.open("x", encoding="utf-8") as handle:
                handle.write(content)
        except FileExistsError:
            counter += 1
            continue
        return candidate, counter > 1
