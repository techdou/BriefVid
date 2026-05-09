#!/usr/bin/env python3
"""Export a processed task result as an Obsidian Markdown note.

Usage:
    python scripts/export_obsidian.py <task_id> [--output-dir DIR]

Examples:
    python scripts/export_obsidian.py abc123 --output-dir ~/ObsidianVault/VideoNotes
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
    parser = argparse.ArgumentParser(description="Export task result as Obsidian note")
    parser.add_argument("task_id", help="Task ID from a previous process_video run")
    parser.add_argument("--output-dir", default=None, help="Obsidian vault directory")
    args = parser.parse_args()

    settings = SkillSettings()
    service = VideoLectureService(settings)
    result = service.export_obsidian_note(task_id=args.task_id, output_dir=args.output_dir)

    if not result.get("success"):
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
