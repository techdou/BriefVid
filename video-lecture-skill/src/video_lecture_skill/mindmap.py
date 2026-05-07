from __future__ import annotations

import json
import logging
from typing import Callable

import httpx

from video_lecture_skill.models import (
    LectureNote,
    MindmapNode,
    MindmapResult,
    PipelineEvent,
    TranscriptionResult,
)

logger = logging.getLogger("video_lecture_skill.mindmap")

_MINDMAP_SYSTEM_PROMPT = (
    "你是一名专业的思维导图生成助手。"
    "你的唯一任务是基于用户提供的视频讲义和转写内容，生成结构化的思维导图数据。"
    "不得编造视频中没有出现的信息，不得输出 JSON 以外的任何文字。"
    "You must return valid json only."
)

_MINDMAP_USER_TEMPLATE = """请基于下面的视频讲义和转写内容，生成一个思维导图的数据结构。
注意：你必须返回合法的 json 对象，且只返回 json。

目标：生成一棵层级清晰、信息密度高的思维导图，适合可视化展示和快速回顾。

强约束：
1. 必须输出合法 JSON，对象顶层只允许包含 title、root 两个字段。
2. title 是思维导图标题。
3. root 是根节点，包含 label 和 children。
4. 每个节点包含 label（节点文字）和 children（子节点列表）。
5. 根节点的 children 是主要章节/主题，3 到 8 个。
6. 每个章节下有 2 到 5 个子节点，代表核心概念或关键要点。
7. 子节点下可以再有一层，1 到 3 个更细的要点，但最多三层。
8. label 必须简洁，5 到 25 个字，不要长句。
9. 不要写"视频介绍了"这种空话，直接写核心概念。
10. 节点之间不要重复相同内容。

输出格式示例：
{{"title":"","root":{{"label":"","children":[{{"label":"","children":[{{"label":"","children":[]}}]}}]}}}}

视频标题：{title}

讲义概览：{overview}

讲义章节：
{sections_json}

转写节选：
{transcript_excerpt}"""


def generate_mindmap(
    transcription: TranscriptionResult,
    lecture: LectureNote,
    title: str,
    api_key: str,
    base_url: str,
    model: str,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> MindmapResult:
    if not api_key:
        result = _generate_mindmap_rules(lecture, title)
        _emit(emit, "mindmap", 97, "思维导图生成完成（本地规则）")
        return result

    _emit(emit, "mindmap", 95, f"正在生成思维导图：{model}")

    try:
        result = _generate_mindmap_llm(transcription, lecture, title, api_key, base_url, model)
    except Exception as exc:
        logger.warning("LLM mindmap generation failed, fallback to rules: %s", exc)
        result = _generate_mindmap_rules(lecture, title)

    _emit(emit, "mindmap", 97, "思维导图生成完成")
    return result


def _emit(emit_fn: Callable[[PipelineEvent], None] | None, stage: str, progress: int, message: str, payload: dict | None = None) -> None:
    if emit_fn is not None:
        emit_fn(PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {}))


def _generate_mindmap_llm(
    transcription: TranscriptionResult,
    lecture: LectureNote,
    title: str,
    api_key: str,
    base_url: str,
    model: str,
) -> MindmapResult:
    base_url = base_url.rstrip("/")
    sections_json = json.dumps(
        [{"title": s.title, "key_concepts": s.key_concepts, "explanation": s.explanation[:80]} for s in lecture.sections],
        ensure_ascii=False,
    )
    transcript_lines = [line.strip() for line in transcription.transcript.splitlines() if line.strip()]
    if len(transcript_lines) > 60:
        transcript_excerpt = "\n".join(transcript_lines[:30] + ["[...省略...]"] + transcript_lines[-20:])
    else:
        transcript_excerpt = transcription.transcript
    transcript_excerpt = transcript_excerpt[:3000]

    user_content = _MINDMAP_USER_TEMPLATE.format(
        title=title,
        overview=lecture.overview[:500],
        sections_json=sections_json[:2000],
        transcript_excerpt=transcript_excerpt,
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _MINDMAP_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
    }

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()

    result_json = response.json()
    content = result_json["choices"][0]["message"]["content"]
    usage = result_json.get("usage") or {}
    parsed = _extract_json(content)

    tree = _parse_tree(parsed.get("root") or {})
    mermaid = _tree_to_mermaid(title, tree)

    return MindmapResult(
        title=str(parsed.get("title") or title or "思维导图"),
        mermaid=mermaid,
        tree=tree,
        llm_prompt_tokens=_safe_int(usage.get("prompt_tokens")),
        llm_completion_tokens=_safe_int(usage.get("completion_tokens")),
        llm_total_tokens=_safe_int(usage.get("total_tokens")),
    )


def _generate_mindmap_rules(lecture: LectureNote, title: str) -> MindmapResult:
    children: list[MindmapNode] = []
    for section in lecture.sections:
        sec_children: list[MindmapNode] = []
        for concept in section.key_concepts[:5]:
            sec_children.append(MindmapNode(label=concept[:25]))
        if not sec_children and section.explanation:
            words = section.explanation.split()[:3]
            sec_children = [MindmapNode(label=w[:25]) for w in words if w]
        children.append(MindmapNode(label=section.title[:25], children=sec_children))

    if not children:
        for line in lecture.overview.split("。")[:5]:
            line = line.strip()
            if line:
                children.append(MindmapNode(label=line[:25]))

    tree = MindmapNode(label=title or "视频内容", children=children)
    mermaid = _tree_to_mermaid(title, tree)

    return MindmapResult(title=title or "思维导图", mermaid=mermaid, tree=tree)


def _tree_to_mermaid(title: str, tree: MindmapNode) -> str:
    lines = ["mindmap"]
    _render_mermaid_node(tree, 2, lines)
    return "\n".join(lines)


def _render_mermaid_node(node: MindmapNode, indent: int, lines: list[str]) -> None:
    prefix = " " * indent
    label = node.label.replace('"', "'").replace("\n", " ").strip()
    if not label:
        label = "..."
    lines.append(f"{prefix}{label}")
    for child in node.children:
        _render_mermaid_node(child, indent + 2, lines)


def _extract_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    for attempt_text in [content.strip(), text]:
        if not attempt_text:
            continue
        try:
            return json.loads(attempt_text)
        except json.JSONDecodeError:
            try:
                return json.loads(attempt_text, strict=False)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("LLM returned invalid JSON for mindmap")


def _parse_tree(data: dict) -> MindmapNode:
    if not isinstance(data, dict):
        return MindmapNode(label="root")
    label = str(data.get("label") or "root")
    children: list[MindmapNode] = []
    for child in (data.get("children") or []):
        if isinstance(child, dict):
            children.append(_parse_tree(child))
    return MindmapNode(label=label[:50], children=children)


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
