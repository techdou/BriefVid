#!/usr/bin/env python3
"""Search the knowledge base or ask a question about processed videos.

Usage:
    python scripts/knowledge_query.py search "query text" [--limit N] [--tags tag1,tag2]
    python scripts/knowledge_query.py ask "question text" [--context-limit N]

Examples:
    python scripts/knowledge_query.py search "机器学习基础"
    python scripts/knowledge_query.py ask "什么是反向传播？" --context-limit 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.service import VideoLectureService


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the video knowledge base")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Semantic search in knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Max results")
    search_parser.add_argument("--tags", default=None, help="Tag filter (comma-separated)")

    ask_parser = subparsers.add_parser("ask", help="RAG Q&A over knowledge base")
    ask_parser.add_argument("query", help="Question")
    ask_parser.add_argument("--context-limit", type=int, default=5, help="Context chunks")

    args = parser.parse_args()
    settings = SkillSettings(knowledge_enabled=True)
    service = VideoLectureService(settings)

    if args.command == "search":
        tag_filter = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        results = service.search_knowledge(query=args.query, limit=args.limit, tag_filter=tag_filter)
        print(json.dumps(
            [r.model_dump(mode="json") for r in results],
            ensure_ascii=False, indent=2,
        ))
    elif args.command == "ask":
        response = service.ask_knowledge(query=args.query, context_limit=args.context_limit)
        print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
