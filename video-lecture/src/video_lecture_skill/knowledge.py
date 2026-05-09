from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.llm import chat_completion
from video_lecture_skill.models import (
    KnowledgeAskResponse,
    KnowledgeChatHistoryItem,
    KnowledgeSearchResult,
    KnowledgeSourceRef,
    PipelineResult,
    format_timestamp,
)

logger = logging.getLogger("video_lecture_skill.knowledge")

KNOWLEDGE_QA_SYSTEM_PROMPT = (
    "你是视频知识库助手，任务是把用户的视频知识库整理成可信的学习洞察。"
    "请严格基于给出的知识库片段回答，不要编造片段之外的具体事实。"
    "但只要片段能支持合理归纳，就要主动多回答一点：概括主题、解释为什么、"
    "补充相关分支，并给出可行动的学习建议。"
    "如果确实完全没有相关片段，只需简短说明没有检索到足够相关的知识片段。"
    "回答使用中文。"
)

EMPTY_KNOWLEDGE_ANSWER = "这次没有检索到足够相关的知识片段。可以换一个关键词再试。"


def format_anchor_seconds(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    return format_timestamp(seconds)


def _import_optional(module_name: str):
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return None
    return importlib.import_module(module_name)


def _split_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    content = str(markdown or "").strip()
    if not content:
        return []
    sections: list[tuple[str, str]] = []
    current_title = "知识笔记"
    current_lines: list[str] = []
    for line in content.splitlines():
        if re.match(r"^\s{0,3}#{1,3}\s+", line):
            if current_lines:
                section_body = "\n".join(current_lines).strip()
                if section_body:
                    sections.append((current_title, section_body))
            current_title = re.sub(r"^\s{0,3}#{1,3}\s+", "", line).strip() or "知识笔记"
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        section_body = "\n".join(current_lines).strip()
        if section_body:
            sections.append((current_title, section_body))
    return sections


class KnowledgeStore:
    def __init__(self, settings: SkillSettings) -> None:
        self._settings = settings
        self._chroma_path = settings.knowledge_index_dir
        self._model_name = settings.knowledge_embedding_model
        self._embedder = None
        self._collection = None
        self._video_results: dict[str, PipelineResult] = {}
        self._video_tags: dict[str, list[str]] = {}

    def _get_embedder(self):
        if self._embedder is None:
            sentence_transformers = _import_optional("sentence_transformers")
            if sentence_transformers is None:
                raise RuntimeError("缺少 sentence-transformers 依赖，无法构建知识库索引。")
            self._embedder = sentence_transformers.SentenceTransformer(self._model_name)
        return self._embedder

    def _get_collection(self):
        if self._collection is None:
            chromadb = _import_optional("chromadb")
            if chromadb is None:
                raise RuntimeError("缺少 chromadb 依赖，无法构建知识库索引。")
            self._chroma_path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self._chroma_path))
            self._collection = client.get_or_create_collection(
                name="video_lecture_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._get_embedder().encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]

    def register_result(self, video_id: str, result: PipelineResult, tags: list[str] | None = None) -> None:
        self._video_results[video_id] = result
        if tags is not None:
            self._video_tags[video_id] = tags

    def _build_chunks_for_video(self, video_id: str) -> list[dict[str, object]]:
        result = self._video_results.get(video_id)
        if result is None:
            return []
        display_title = result.lecture.title or result.video_info.title or "视频"
        chunk_specs: list[dict[str, object]] = []

        overview_parts = [str(result.overview or "").strip(), *[str(item).strip() for item in result.key_points if str(item).strip()]]
        overview_text = "\n".join([part for part in overview_parts if part]).strip()
        if overview_text:
            chunk_specs.append({
                "index_type": "video_summary",
                "segment_order": 0,
                "anchor_label": None,
                "anchor_seconds": None,
                "content": f"{display_title}\n{overview_text}",
            })

        for index, chapter in enumerate(result.timeline):
            if not isinstance(chapter, dict):
                continue
            title = str(chapter.get("title") or f"章节 {index + 1}").strip()
            summary = str(chapter.get("summary") or "").strip()
            start_raw = chapter.get("start")
            start = float(start_raw) if isinstance(start_raw, (int, float)) else None
            content = "\n".join([display_title, title, summary]).strip()
            if summary:
                chunk_specs.append({
                    "index_type": "chapter",
                    "segment_order": index + 1,
                    "anchor_label": title,
                    "anchor_seconds": start,
                    "content": content,
                })

        for index, (title, body) in enumerate(_split_markdown_sections(result.knowledge_note_markdown)):
            chunk_specs.append({
                "index_type": "knowledge_note",
                "segment_order": index + 1,
                "anchor_label": title,
                "anchor_seconds": None,
                "content": f"{display_title}\n{title}\n{body}".strip(),
            })

        return [item for item in chunk_specs if str(item["content"]).strip()]

    def index_video(self, video_id: str) -> bool:
        chunk_specs = self._build_chunks_for_video(video_id)
        if not chunk_specs:
            return False

        collection = self._get_collection()
        try:
            collection.delete(where={"video_id": video_id})
        except Exception:
            pass

        texts = [str(item["content"]) for item in chunk_specs]
        vectors = self._embed_texts(texts)
        tags = self._video_tags.get(video_id, [])

        ids = [f"{video_id}:{item['index_type']}:{item['segment_order'] or 0}" for item in chunk_specs]
        metadatas = [
            {
                "video_id": video_id,
                "index_type": str(item["index_type"]),
                "anchor_label": str(item["anchor_label"] or ""),
                "anchor_seconds": float(item["anchor_seconds"]) if item["anchor_seconds"] is not None else -1.0,
                "tags_json": json.dumps(tags, ensure_ascii=False),
            }
            for item in chunk_specs
        ]
        collection.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)
        return True

    def remove_video(self, video_id: str) -> bool:
        self._video_results.pop(video_id, None)
        self._video_tags.pop(video_id, None)
        try:
            self._get_collection().delete(where={"video_id": video_id})
        except Exception:
            pass
        return True

    def rebuild_index(self) -> int:
        collection = self._get_collection()
        try:
            existing = collection.get()
            ids = existing.get("ids") if isinstance(existing, dict) else None
            if ids:
                collection.delete(ids=ids)
        except Exception:
            pass

        count = 0
        for video_id in list(self._video_results):
            if self.index_video(video_id):
                count += 1
        return count

    def _query_candidates(
        self,
        query: str,
        limit: int,
        tag_filter: list[str] | None = None,
    ) -> list[dict[str, object]]:
        cleaned_query = str(query or "").strip()
        if not cleaned_query:
            return []

        query_embedding = self._embed_texts([cleaned_query])[0]
        effective_limit = max(limit * 4, 12)
        query_result = self._get_collection().query(
            query_embeddings=[query_embedding],
            n_results=effective_limit,
        )

        ids = query_result.get("ids", [[]])[0] if isinstance(query_result, dict) else []
        documents = query_result.get("documents", [[]])[0] if isinstance(query_result, dict) else []
        metadatas = query_result.get("metadatas", [[]])[0] if isinstance(query_result, dict) else []
        distances = query_result.get("distances", [[]])[0] if isinstance(query_result, dict) else []

        allowed_video_ids: set[str] | None = None
        if tag_filter:
            selected = {tag.strip() for tag in tag_filter if str(tag).strip()}
            if selected:
                allowed_video_ids = {
                    vid for vid, tags in self._video_tags.items() if selected & set(tags)
                }

        candidates: list[dict[str, object]] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            video_id = str(metadata.get("video_id") or "")
            if allowed_video_ids is not None and video_id not in allowed_video_ids:
                continue
            distance = float(distances[index]) if index < len(distances) else 1.0
            relevance = max(0.0, 1.0 - distance / 2.0)
            candidates.append({
                "chunk_id": chunk_id,
                "video_id": video_id,
                "document": documents[index] if index < len(documents) else "",
                "metadata": metadata,
                "relevance_score": round(relevance, 4),
            })
        return candidates

    def search(self, query: str, limit: int = 10, tag_filter: list[str] | None = None) -> list[KnowledgeSearchResult]:
        candidates = self._query_candidates(query, limit, tag_filter)
        if not candidates:
            return []

        grouped: dict[str, dict[str, object]] = {}
        for candidate in candidates:
            video_id = str(candidate["video_id"])
            current = grouped.get(video_id)
            if current is None or float(candidate["relevance_score"]) > float(current["relevance_score"]):
                grouped[video_id] = candidate

        ordered = sorted(grouped.values(), key=lambda item: float(item["relevance_score"]), reverse=True)[:max(1, limit)]
        results: list[KnowledgeSearchResult] = []
        for candidate in ordered:
            video_id = str(candidate["video_id"])
            result = self._video_results.get(video_id)
            metadata = candidate["metadata"] if isinstance(candidate["metadata"], dict) else {}
            video_title = (result.lecture.title or result.video_info.title) if result else str(metadata.get("title") or "未知视频")
            snippet = str(candidate["document"]).strip().replace("\n", " ")
            snippet = snippet[:180].rstrip() + ("..." if len(snippet) > 180 else "")
            tags = self._video_tags.get(video_id, [])
            anchor_seconds = float(metadata["anchor_seconds"]) if metadata.get("anchor_seconds") not in {None, "", -1, -1.0} else None
            results.append(KnowledgeSearchResult(
                video_id=video_id,
                title=video_title,
                relevance_score=float(candidate["relevance_score"]),
                snippet=snippet,
                tags=tags,
                timestamp=format_anchor_seconds(anchor_seconds),
            ))
        return results

    def search_chunks(self, query: str, limit: int = 5, tag_filter: list[str] | None = None) -> list[dict[str, object]]:
        candidates = self._query_candidates(query, limit, tag_filter)
        return candidates[:max(1, limit)]


def _build_knowledge_user_prompt(
    query: str,
    context_blocks: list[str],
    history: list[KnowledgeChatHistoryItem] | None = None,
) -> str:
    history_text = ""
    if history:
        lines = []
        for item in history[-8:]:
            label = "用户" if item.role == "user" else "助手"
            lines.append(f"{label}：{item.content}")
        history_text = "\n".join(lines)
    history_block = f"本轮会话上下文：\n---\n{history_text}\n---\n\n" if history_text else ""
    return (
        f"用户问题：{query}\n\n"
        + history_block
        + "相关视频内容：\n---\n"
        + "\n\n".join(context_blocks)
        + "\n---\n\n"
        + "请按下面原则组织回答：\n"
        "1. 先直接回答问题，不要先道歉或免责声明。\n"
        "2. 如果适合，按主题分组，并说明每组主题背后的依据。\n"
        "3. 可以给出下一步学习建议，但必须和片段内容相关。\n"
        "4. 不要输出空泛句子。"
    )


class KnowledgeAgent:
    def __init__(self, store: KnowledgeStore, settings: SkillSettings) -> None:
        self._store = store
        self._settings = settings

    def ask(
        self,
        query: str,
        context_limit: int = 5,
        history: list[KnowledgeChatHistoryItem] | None = None,
    ) -> KnowledgeAskResponse:
        cleaned_query = str(query or "").strip()
        if not cleaned_query:
            return KnowledgeAskResponse(query="", answer=EMPTY_KNOWLEDGE_ANSWER, sources=[])

        chunks = self._store.search_chunks(cleaned_query, limit=context_limit)
        if not chunks:
            return KnowledgeAskResponse(query=cleaned_query, answer=EMPTY_KNOWLEDGE_ANSWER, sources=[])

        context_blocks: list[str] = []
        sources: list[KnowledgeSourceRef] = []
        seen_sources: set[tuple[str, str | None]] = set()
        for item in chunks:
            video_id = str(item["video_id"])
            metadata = item["metadata"] if isinstance(item["metadata"], dict) else {}
            result = self._store._video_results.get(video_id)
            video_title = (result.lecture.title or result.video_info.title) if result else "未知视频"
            anchor_seconds = float(metadata["anchor_seconds"]) if metadata.get("anchor_seconds") not in {None, "", -1, -1.0} else None
            timestamp = format_anchor_seconds(anchor_seconds)
            context_blocks.append(
                f"[视频：{video_title}]\n[时间：{timestamp or '未标注'}]\n{str(item['document']).strip()}"
            )
            key = (video_id, timestamp)
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(KnowledgeSourceRef(
                    video_id=video_id,
                    title=video_title,
                    relevance_score=float(item["relevance_score"]),
                    timestamp=timestamp,
                ))

        answer = chat_completion(
            self._settings,
            system_prompt=KNOWLEDGE_QA_SYSTEM_PROMPT,
            user_prompt=_build_knowledge_user_prompt(cleaned_query, context_blocks, history),
            max_tokens=1100,
            temperature=0.28,
            timeout=60,
            fallback=EMPTY_KNOWLEDGE_ANSWER,
        )
        return KnowledgeAskResponse(query=cleaned_query, answer=answer, sources=sources)
