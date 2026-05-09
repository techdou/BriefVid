from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import httpx

from video_lecture_skill.models import (
    LectureNote,
    LectureSection,
    PipelineEvent,
    Segment,
    TranscriptionResult,
)

logger = logging.getLogger("video_lecture_skill.lecture")

_LECTURE_SYSTEM_PROMPT = (
    "你是一名专业的课程讲义整理助手。"
    "你的唯一任务是基于用户提供的视频转写内容，生成结构化的课程讲义。"
    "不得编造视频中没有出现的信息，不得输出 JSON 以外的任何文字。"
    "You must return valid json only."
)

_LECTURE_USER_TEMPLATE = """请阅读下面的视频转写内容，生成一份结构化课程讲义。
注意：你必须返回合法的 json 对象，且只返回 json。

目标：生成一份信息密度高、适合学习和复习的课程讲义。

强约束：
1. 必须输出合法 JSON，对象顶层只允许包含 title、overview、prerequisites、sections、summary、references 六个字段。
2. title 必须是讲义标题，简洁概括视频主题。
3. overview 必须是 2 到 4 句中文，概括课程核心内容和目标。
4. prerequisites 是前置知识要求列表，0 到 3 条，每条不超过 40 字。如果没有明确前置知识，返回空数组。
5. sections 是讲义章节，3 到 8 个，每个章节必须包含 title、start、key_concepts、explanation、examples、quiz。
   - title: 章节标题，简短有力
   - start: 视频时间点（秒），使用转写中真实出现的时间
   - key_concepts: 核心概念列表，2 到 4 个，每个 10 到 30 字
   - explanation: 详细讲解，80 到 250 字，内容忠实原文
   - examples: 示例或案例列表，0 到 2 个，每个 20 到 80 字
   - quiz: 随堂思考题列表，1 到 2 个，每个 15 到 50 字
6. summary 是课程总结，2 到 4 句，概括核心收获。
7. references 是延伸阅读建议，0 到 3 条，每条 10 到 40 字。
8. 不要写"本视频介绍了"这种空话，直接写内容。
9. 不要引用不存在的数据，不要补充外部背景。

输出格式示例：
{{"title":"","overview":"","prerequisites":[],"sections":[{{"title":"","start":0,"key_concepts":[],"explanation":"","examples":[],"quiz":[]}}],"summary":"","references":[]}}

视频标题：{title}

转写内容：
{transcript}

分段数据：
{segments_json}"""


def generate_lecture(
    transcription: TranscriptionResult,
    title: str,
    api_key: str,
    base_url: str,
    model: str,
    chunk_target_chars: int = 2200,
    chunk_overlap_segments: int = 2,
    chunk_concurrency: int = 2,
    chunk_retry_count: int = 2,
    emit: Callable[[PipelineEvent], None] | None = None,
) -> LectureNote:
    if not api_key:
        return _generate_lecture_rules(transcription, title)

    _emit(emit, "lecture", 88, f"正在生成讲义：{model}", {"llm_enabled": True})

    try:
        result = _generate_lecture_llm(
            transcription=transcription,
            title=title,
            api_key=api_key,
            base_url=base_url,
            model=model,
            chunk_target_chars=chunk_target_chars,
            chunk_overlap_segments=chunk_overlap_segments,
            chunk_concurrency=chunk_concurrency,
            chunk_retry_count=chunk_retry_count,
            emit=emit,
        )
    except Exception as exc:
        logger.warning("LLM lecture generation failed, fallback to rules: %s", exc)
        _emit(emit, "lecture", 91, f"LLM 不可用，已切换为本地规则讲义：{exc}", {"fallback": True})
        result = _generate_lecture_rules(transcription, title)

    _emit(emit, "lecture", 95, "讲义生成完成")
    return result


def _emit(emit_fn: Callable[[PipelineEvent], None] | None, stage: str, progress: int, message: str, payload: dict | None = None) -> None:
    if emit_fn is not None:
        emit_fn(PipelineEvent(stage=stage, progress=progress, message=message, payload=payload or {}))


def _generate_lecture_llm(
    transcription: TranscriptionResult,
    title: str,
    api_key: str,
    base_url: str,
    model: str,
    chunk_target_chars: int,
    chunk_overlap_segments: int,
    chunk_concurrency: int,
    chunk_retry_count: int,
    emit: Callable[[PipelineEvent], None] | None,
) -> LectureNote:
    base_url = base_url.rstrip("/")
    chunks = _build_chunks(transcription.segments, chunk_target_chars, chunk_overlap_segments)

    if not chunks:
        chunks = [{"index": 1, "transcript": transcription.transcript, "segments_json": json.dumps([s.model_dump() for s in transcription.segments], ensure_ascii=False)}]

    logger.info("lecture chunk plan model=%s chunks=%d", model, len(chunks))

    partial_summaries: list[dict] = []
    chunk_count = len(chunks)
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, chunk_concurrency)) as executor:
        future_map = {
            executor.submit(_request_lecture_chunk, base_url, api_key, model, title, chunk, chunk_count, chunk_retry_count): chunk
            for chunk in chunks
        }
        for future in as_completed(future_map):
            chunk = future_map[future]
            try:
                partial = future.result()
                partial_summaries.append(partial)
                completed += 1
                _emit(emit, "lecture", min(93, 88 + completed), f"已完成第 {completed}/{chunk_count} 个内容块")
            except Exception as exc:
                logger.warning("lecture chunk failed: %s", exc)
                completed += 1

    partial_summaries.sort(key=lambda item: int(item.get("chunk_index") or 0))

    aggregate_transcript, aggregate_segments = _build_aggregate_inputs(partial_summaries)
    merged = _request_lecture(
        base_url=base_url,
        api_key=api_key,
        model=model,
        title=title,
        transcript_excerpt=aggregate_transcript,
        segments_excerpt=aggregate_segments,
    )

    total_prompt = sum(_safe_int(p.get("llm_prompt_tokens")) or 0 for p in partial_summaries)
    total_completion = sum(_safe_int(p.get("llm_completion_tokens")) or 0 for p in partial_summaries)
    total_tokens = sum(_safe_int(p.get("llm_total_tokens")) or 0 for p in partial_summaries)
    merged["llm_prompt_tokens"] = total_prompt + (_safe_int(merged.get("llm_prompt_tokens")) or 0)
    merged["llm_completion_tokens"] = total_completion + (_safe_int(merged.get("llm_completion_tokens")) or 0)
    merged["llm_total_tokens"] = total_tokens + (_safe_int(merged.get("llm_total_tokens")) or 0)

    return _parse_lecture_json(merged, title)


def _request_lecture_chunk(
    base_url: str, api_key: str, model: str, title: str, chunk: dict, chunk_count: int, retry_count: int,
) -> dict:
    chunk_index = int(chunk["index"])
    last_error: Exception | None = None
    for attempt in range(retry_count + 1):
        try:
            partial = _request_lecture(
                base_url=base_url,
                api_key=api_key,
                model=model,
                title=f"{title} - 分块 {chunk_index}",
                transcript_excerpt=str(chunk["transcript"]),
                segments_excerpt=str(chunk["segments_json"]),
            )
            partial["chunk_index"] = chunk_index
            return partial
        except Exception as exc:
            last_error = exc
            logger.warning("lecture chunk %d attempt %d failed: %s", chunk_index, attempt + 1, exc)
    raise RuntimeError(str(last_error) if last_error else f"Chunk {chunk_index} failed")


def _request_lecture(
    base_url: str, api_key: str, model: str, title: str, transcript_excerpt: str, segments_excerpt: str,
) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content = _LECTURE_USER_TEMPLATE.format(
        title=title, transcript=transcript_excerpt, segments_json=segments_excerpt,
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _LECTURE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "enable_thinking": False,
    }

    with httpx.Client(timeout=180, follow_redirects=True) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()

    result_json = response.json()
    content = result_json["choices"][0]["message"]["content"]
    usage = result_json.get("usage") or {}
    parsed = _extract_json(content)
    parsed["llm_prompt_tokens"] = _safe_int(usage.get("prompt_tokens"))
    parsed["llm_completion_tokens"] = _safe_int(usage.get("completion_tokens"))
    parsed["llm_total_tokens"] = _safe_int(usage.get("total_tokens"))
    return parsed


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
    raise RuntimeError("LLM returned invalid JSON for lecture")


def _parse_lecture_json(data: dict, fallback_title: str) -> LectureNote:
    sections: list[LectureSection] = []
    for i, sec in enumerate(data.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        sections.append(LectureSection(
            title=str(sec.get("title") or f"章节 {i + 1}"),
            start=float(sec.get("start") or 0),
            key_concepts=[str(c) for c in (sec.get("key_concepts") or []) if str(c).strip()],
            explanation=str(sec.get("explanation") or ""),
            examples=[str(e) for e in (sec.get("examples") or []) if str(e).strip()],
            quiz=[str(q) for q in (sec.get("quiz") or []) if str(q).strip()],
        ))

    return LectureNote(
        title=str(data.get("title") or fallback_title or "课程讲义"),
        overview=str(data.get("overview") or ""),
        prerequisites=[str(p) for p in (data.get("prerequisites") or []) if str(p).strip()],
        sections=sections,
        summary=str(data.get("summary") or ""),
        references=[str(r) for r in (data.get("references") or []) if str(r).strip()],
        llm_prompt_tokens=_safe_int(data.get("llm_prompt_tokens")),
        llm_completion_tokens=_safe_int(data.get("llm_completion_tokens")),
        llm_total_tokens=_safe_int(data.get("llm_total_tokens")),
    )


def _generate_lecture_rules(transcription: TranscriptionResult, title: str) -> LectureNote:
    lines = [line.strip() for line in transcription.transcript.splitlines() if line.strip()]
    overview = "\n".join(lines[:3])[:400]
    sections: list[LectureSection] = []
    segments = transcription.segments

    if segments:
        step = max(1, len(segments) // 5)
        for idx in range(0, len(segments), step):
            group = segments[idx : idx + step]
            if not group:
                continue
            group_text = " ".join(s.text for s in group if s.text.strip())
            sections.append(LectureSection(
                title=f"章节 {len(sections) + 1}",
                start=group[0].start,
                key_concepts=[s.text.strip()[:30] for s in group[:3] if s.text.strip()],
                explanation=group_text[:250],
            ))
            if len(sections) >= 6:
                break

    return LectureNote(
        title=title or "课程讲义",
        overview=overview,
        sections=sections,
        summary=overview[:200],
    )


def _build_chunks(segments: list[Segment], target_chars: int, overlap: int) -> list[dict]:
    if not segments:
        return []
    chunks: list[dict] = []
    start = 0
    index = 1
    total = len(segments)

    while start < total:
        current: list[Segment] = []
        current_chars = 0
        cursor = start
        while cursor < total:
            seg = segments[cursor]
            estimated = len(seg.text) + 24
            if current and current_chars + estimated > target_chars:
                break
            current.append(seg)
            current_chars += estimated
            cursor += 1
        if not current:
            current = [segments[start]]
            cursor = start + 1

        chunk_lines = [f"[{_fmt_sec(s.start)}] {s.text}" for s in current if s.text.strip()]
        compact = [{"start": s.start, "text": s.text.strip()[:120]} for s in current if s.text.strip()]
        chunks.append({
            "index": index,
            "transcript": "\n".join(chunk_lines)[:target_chars + 400],
            "segments_json": json.dumps(compact, ensure_ascii=False)[:target_chars + 400],
        })
        index += 1
        if cursor >= total:
            break
        start = max(cursor - overlap, start + 1)
    return chunks


def _build_aggregate_inputs(partials: list[dict]) -> tuple[str, str]:
    lines: list[str] = []
    segments: list[dict] = []
    for item in partials:
        ci = int(item.get("chunk_index") or 0)
        t = str(item.get("title") or f"分块 {ci}")
        ov = str(item.get("overview") or "").strip()
        lines.append(f"### 分块 {ci}: {t}")
        if ov:
            lines.append(f"概览：{ov}")
        for sec in (item.get("sections") or [])[:6]:
            if not isinstance(sec, dict):
                continue
            sec_title = str(sec.get("title") or "")
            sec_exp = str(sec.get("explanation") or "").strip()
            if sec_exp:
                lines.append(f"- {sec_title}：{sec_exp[:100]}")
                segments.append({"start": float(sec.get("start") or 0), "text": f"{sec_title}：{sec_exp[:140]}"})
        lines.append("")
    return "\n".join(lines).strip()[:5200], json.dumps(segments, ensure_ascii=False)[:2600]


def _fmt_sec(value: float) -> str:
    total = max(0, int(value))
    return f"{total // 60:02d}:{total % 60:02d}"


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
