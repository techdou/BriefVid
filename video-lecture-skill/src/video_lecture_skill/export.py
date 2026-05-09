from __future__ import annotations

import json
from pathlib import Path

from video_lecture_skill.models import (
    LectureNote,
    MindmapResult,
    PipelineResult,
    Segment,
    TranscriptionResult,
    VideoInfo,
)


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
            minutes = int(sec.start) // 60
            seconds = int(sec.start) % 60
            timestamp = f"{minutes:02d}:{seconds:02d}"
            lines.append(f"### {i}. {sec.title} `[{timestamp}]`")
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
