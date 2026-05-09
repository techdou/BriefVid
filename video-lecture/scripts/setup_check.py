#!/usr/bin/env python3
"""Environment setup check for video-lecture-skill.

Run this script to verify that all required and optional dependencies
are installed and configured correctly.
"""
from __future__ import annotations

import shutil
import sys


def _check_python_version() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 11:
        return True, f"Python {major}.{minor}"
    return False, f"Python {major}.{minor} (need >= 3.11)"


def _check_ffmpeg() -> tuple[bool, str]:
    path = shutil.which("ffmpeg")
    if path:
        return True, f"found at {path}"
    return False, "not found — install ffmpeg and add to PATH"


def _check_yt_dlp() -> tuple[bool, str]:
    path = shutil.which("yt-dlp")
    if path:
        return True, f"found at {path}"
    try:
        import yt_dlp
        return True, f"Python package {getattr(yt_dlp, 'version', 'ok')}"
    except ImportError:
        return False, "not found — pip install yt-dlp"


def _check_faster_whisper() -> tuple[bool, str]:
    try:
        import faster_whisper
        return True, f"version {getattr(faster_whisper, '__version__', 'ok')}"
    except ImportError:
        return False, "not found — pip install faster-whisper"


def _check_openai_key() -> tuple[bool, str]:
    import os
    key = os.environ.get("VLEC_OPENAI_API_KEY", "")
    if key:
        return True, f"set ({key[:4]}...{key[-4:]})"
    return False, "not set — export VLEC_OPENAI_API_KEY=sk-..."


def _check_chromadb() -> tuple[bool, str]:
    try:
        import chromadb
        return True, f"version {getattr(chromadb, '__version__', 'ok')}"
    except ImportError:
        return False, "not found (optional) — pip install chromadb"


def _check_sentence_transformers() -> tuple[bool, str]:
    try:
        import sentence_transformers
        return True, f"version {getattr(sentence_transformers, '__version__', 'ok')}"
    except ImportError:
        return False, "not found (optional) — pip install sentence-transformers"


def _check_mcp() -> tuple[bool, str]:
    try:
        import mcp
        return True, "installed"
    except ImportError:
        return False, "not found (optional) — pip install mcp"


def main() -> int:
    checks = [
        ("Python >= 3.11", _check_python_version, True),
        ("ffmpeg", _check_ffmpeg, True),
        ("yt-dlp", _check_yt_dlp, True),
        ("faster-whisper", _check_faster_whisper, True),
        ("VLEC_OPENAI_API_KEY", _check_openai_key, True),
        ("chromadb", _check_chromadb, False),
        ("sentence-transformers", _check_sentence_transformers, False),
        ("mcp", _check_mcp, False),
    ]

    print("=" * 60)
    print("video-lecture-skill — Setup Check")
    print("=" * 60)

    all_required_ok = True
    for name, check_fn, required in checks:
        ok, detail = check_fn()
        status = "✅" if ok else ("❌" if required else "⚠️")
        label = "required" if required else "optional"
        print(f"  {status} {name} [{label}]: {detail}")
        if required and not ok:
            all_required_ok = False

    print("=" * 60)
    if all_required_ok:
        print("All required dependencies are ready. Optional features may need additional packages.")
        return 0
    print("Some required dependencies are missing. Please install them before using this skill.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
