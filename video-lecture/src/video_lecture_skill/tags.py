from __future__ import annotations

import json
import logging
from collections import Counter
from itertools import combinations

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.llm import chat_completion
from video_lecture_skill.models import (
    KnowledgeNetworkLink,
    KnowledgeNetworkNode,
    KnowledgeNetworkResponse,
    TagItem,
    VideoTagRecord,
)

logger = logging.getLogger("video_lecture_skill.tags")


def _parse_json_payload(text: str) -> dict:
    cleaned = str(text or "").strip()
    if not cleaned:
        return {}
    fence_match = cleaned.rfind("```")
    if fence_match >= 0:
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}")
        if json_start >= 0 and json_end > json_start:
            cleaned = cleaned[json_start:json_end + 1]
    try:
        result = json.loads(cleaned)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        return {}


class TagStore:
    def __init__(self, settings: SkillSettings) -> None:
        self._settings = settings
        self._video_tags: dict[str, list[VideoTagRecord]] = {}

    def add_tag(self, video_id: str, tag: str, source: str = "manual", confidence: float = 1.0) -> bool:
        tag = str(tag or "").strip()
        if not tag:
            return False
        records = self._video_tags.setdefault(video_id, [])
        if any(r.tag == tag for r in records):
            return True
        records.append(VideoTagRecord(video_id=video_id, tag=tag, source=source, confidence=confidence))
        return True

    def remove_tag(self, video_id: str, tag: str) -> bool:
        records = self._video_tags.get(video_id, [])
        before = len(records)
        self._video_tags[video_id] = [r for r in records if r.tag != tag]
        return len(self._video_tags[video_id]) < before

    def get_tags_for_video(self, video_id: str) -> list[VideoTagRecord]:
        return list(self._video_tags.get(video_id, []))

    def get_all_tags(self) -> list[TagItem]:
        counter: Counter[str] = Counter()
        for records in self._video_tags.values():
            seen = {r.tag for r in records}
            for tag in seen:
                counter[tag] += 1
        return [TagItem(tag=tag, count=count) for tag, count in counter.most_common()]

    def get_all_video_tags(self) -> list[VideoTagRecord]:
        result: list[VideoTagRecord] = []
        for records in self._video_tags.values():
            result.extend(records)
        return result

    def list_untagged_video_ids(self, known_video_ids: list[str] | None = None) -> list[str]:
        if known_video_ids is None:
            return [vid for vid, records in self._video_tags.items() if not records]
        return [vid for vid in known_video_ids if not self._video_tags.get(vid)]

    def auto_tag_video(self, video_id: str, content: str) -> list[str]:
        if not content.strip():
            return []

        response_text = chat_completion(
            self._settings,
            system_prompt=(
                "你是一个知识库标签助手。请根据视频摘要和知识笔记，为视频生成 3 到 8 个简洁中文标签。"
                "只返回合法 JSON，对象格式必须为 {\"tags\": [\"标签1\", \"标签2\"]}。"
            ),
            user_prompt=content,
            require_json=True,
            max_tokens=200,
            temperature=0.1,
            timeout=30,
            fallback="",
        )
        payload = _parse_json_payload(response_text)
        raw_tags = payload.get("tags")
        if not isinstance(raw_tags, list):
            return []

        normalized_tags: list[str] = []
        seen: set[str] = set()
        for item in raw_tags:
            tag = str(item or "").strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            normalized_tags.append(tag)
            self.add_tag(video_id, tag, source="auto_llm", confidence=0.8)
        return normalized_tags

    def batch_auto_tag(self, video_contents: dict[str, str]) -> dict[str, list[str]]:
        results: dict[str, list[str]] = {}
        for video_id, content in video_contents.items():
            tags = self.auto_tag_video(video_id, content)
            results[video_id] = tags
        return results

    def get_network_data(
        self,
        selected_tags: list[str] | None = None,
        *,
        max_tags: int = 12,
        max_videos: int = 8,
    ) -> KnowledgeNetworkResponse:
        all_tags = self.get_all_tags()
        all_video_tags = self.get_all_video_tags()
        selected = [tag for tag in dict.fromkeys(selected_tags or []) if tag]
        tag_counts = {item.tag: item.count for item in all_tags}
        video_tag_map: dict[str, list[str]] = {}
        for item in all_video_tags:
            video_tag_map.setdefault(item.video_id, []).append(item.tag)

        tag_video_map: dict[str, set[str]] = {}
        cooccurrence: Counter[tuple[str, str]] = Counter()
        for video_id, tags in video_tag_map.items():
            unique_tags = sorted({tag for tag in tags if tag})
            for tag in unique_tags:
                tag_video_map.setdefault(tag, set()).add(video_id)
            for left, right in combinations(unique_tags, 2):
                cooccurrence[(left, right)] += 1

        tag_degree: Counter[str] = Counter()
        for (left, right), weight in cooccurrence.items():
            tag_degree[left] += weight
            tag_degree[right] += weight

        def tag_rank(tag: str) -> tuple[int, int, str]:
            return (tag_degree.get(tag, 0), tag_counts.get(tag, 0), tag)

        if selected:
            existing_selected = [tag for tag in selected if tag in tag_counts]
            related_scores: Counter[str] = Counter()
            for current_tag in existing_selected:
                for (left, right), weight in cooccurrence.items():
                    if left == current_tag and right not in existing_selected:
                        related_scores[right] += weight
                    elif right == current_tag and left not in existing_selected:
                        related_scores[left] += weight
            related_tags = [
                tag for tag, _score in sorted(
                    related_scores.items(),
                    key=lambda item: (item[1], tag_degree.get(item[0], 0), tag_counts.get(item[0], 0), item[0]),
                    reverse=True,
                )
            ]
            visible_tags = existing_selected + [
                tag for tag in related_tags if tag not in existing_selected
            ][:max(0, max_tags - len(existing_selected))]
            mode = "focus"
        else:
            ranked_tags = sorted(tag_counts, key=tag_rank, reverse=True)
            visible_tags = ranked_tags[:max_tags]
            mode = "overview"

        visible_tag_set = set(visible_tags)
        nodes: list[KnowledgeNetworkNode] = []
        for tag in visible_tags:
            nodes.append(KnowledgeNetworkNode(
                id=f"tag_{tag}",
                label=tag,
                type="tag",
                count=tag_counts.get(tag, 0),
                degree=tag_degree.get(tag, 0),
                focus=tag in selected,
                video_count=len(tag_video_map.get(tag, set())),
            ))

        links: list[KnowledgeNetworkLink] = []
        for (left, right), weight in cooccurrence.most_common():
            if left in visible_tag_set and right in visible_tag_set:
                links.append(KnowledgeNetworkLink(
                    source=f"tag_{left}",
                    target=f"tag_{right}",
                    weight=float(weight),
                    kind="cooccurrence",
                ))
            if len(links) >= max(10, len(visible_tags) * 2):
                break

        return KnowledgeNetworkResponse(
            nodes=nodes,
            links=links,
            mode=mode,
            hidden_tag_count=max(0, len(tag_counts) - len(visible_tags)),
            selected_tags=selected,
        )
