#!/usr/bin/env python3
"""Process a video URL and output lecture notes, mindmap, or full results.

Usage:
    python scripts/process_video.py <url> [--title TITLE] [--language LANG] [--mode local|cloud] [--output-dir DIR] [--page NUMBER] [--format lecture|mindmap|full]

Examples:
    python scripts/process_video.py "https://www.bilibili.com/video/BV1xxx"
    python scripts/process_video.py "BV1xxx" --page 2 --format lecture
    python scripts/process_video.py "https://youtube.com/watch?v=xxx" --mode cloud --output-dir ./output
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
    parser = argparse.ArgumentParser(description="Process a video into lecture notes and mindmap")
    parser.add_argument("url", help="Video URL or BV number")
    parser.add_argument("--title", default=None, help="Video title (optional)")
    parser.add_argument("--language", default="zh", help="Transcription language (default: zh)")
    parser.add_argument("--mode", choices=["local", "cloud"], default=None, help="Transcribe mode")
    parser.add_argument("--output-dir", default=None, help="Output directory for result files")
    parser.add_argument("--page", type=int, default=None, help="Bilibili multi-page number")
    parser.add_argument("--format", choices=["lecture", "mindmap", "full"], default="full", help="Output format")
    args = parser.parse_args()

    settings = SkillSettings()
    if args.mode:
        from video_lecture_skill.models import TranscribeMode
        settings = settings.model_copy(update={"transcribe_mode": TranscribeMode(args.mode)})

    service = VideoLectureService(settings)
    result = service.process_and_wait(
        url=args.url,
        title=args.title,
        language=args.language,
        output_dir=args.output_dir,
        page_number=args.page,
    )

    if not result.get("success"):
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return 1

    if args.format == "lecture":
        print(result.get("lecture_md", ""))
    elif args.format == "mindmap":
        print(result.get("mindmap_mermaid", ""))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
