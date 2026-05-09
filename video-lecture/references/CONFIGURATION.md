# Configuration Guide

All configuration uses environment variables with the `VLEC_` prefix. You can also create a `.env` file in the project root.

## Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_HOST` | `127.0.0.1` | REST API host |
| `VLEC_PORT` | `3839` | REST API port |
| `VLEC_DATA_DIR` | `~/.video-lecture/data` | Data storage directory |
| `VLEC_LANGUAGE` | `zh` | Default transcription language |
| `VLEC_OUTPUT_FORMATS` | `markdown,mermaid,json` | Default output formats (comma-separated) |

## Transcription Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_TRANSCRIBE_MODE` | `local` | Transcription mode: `local` or `cloud` |
| `VLEC_WHISPER_MODEL` | `base` | Whisper model size: tiny, base, small, medium, large |
| `VLEC_WHISPER_DEVICE` | `cpu` | Compute device: `cpu` or `cuda` |
| `VLEC_WHISPER_COMPUTE_TYPE` | `int8` | Compute type: int8, float16, etc. |

## LLM Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_OPENAI_API_KEY` | — | **Required** for LLM-powered lecture generation |
| `VLEC_OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL (supports compatible endpoints) |
| `VLEC_OPENAI_MODEL` | `gpt-4o-mini` | Model name |

### LLM Chunk Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_SUMMARY_CHUNK_TARGET_CHARS` | `2200` | Target chars per chunk |
| `VLEC_SUMMARY_CHUNK_OVERLAP_SEGMENTS` | `2` | Overlap segments between chunks |
| `VLEC_SUMMARY_CHUNK_CONCURRENCY` | `2` | Parallel chunk processing |
| `VLEC_SUMMARY_CHUNK_RETRY_COUNT` | `2` | Retry count per chunk |

## Knowledge Base Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_KNOWLEDGE_ENABLED` | `false` | Enable knowledge base features |
| `VLEC_KNOWLEDGE_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | Sentence-transformers model |
| `VLEC_KNOWLEDGE_CHROMA_PATH` | — | Custom ChromaDB path (default: `{data_dir}/knowledge_index`) |
| `VLEC_KNOWLEDGE_INDEX_AUTO_REBUILD` | `disabled` | Auto-rebuild index: `disabled`, `on_start`, `on_change` |
| `VLEC_KNOWLEDGE_LLM_MODE` | `same_as_main` | LLM mode: `same_as_main` or `custom` |
| `VLEC_KNOWLEDGE_LLM_ENABLED` | `false` | Enable custom LLM for knowledge features |
| `VLEC_KNOWLEDGE_LLM_BASE_URL` | — | Custom LLM base URL |
| `VLEC_KNOWLEDGE_LLM_MODEL` | — | Custom LLM model name |
| `VLEC_KNOWLEDGE_LLM_API_KEY` | — | Custom LLM API key |

## Export Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `VLEC_OBSIDIAN_OUTPUT_DIR` | — | Obsidian vault directory for export |
| `VLEC_EXPORT_TARGET` | `obsidian` | Default export target format |

## Quick Start

```bash
# Minimal setup
export VLEC_OPENAI_API_KEY=sk-your-key-here

# With knowledge base
export VLEC_KNOWLEDGE_ENABLED=true
pip install chromadb sentence-transformers

# With Obsidian export
export VLEC_OBSIDIAN_OUTPUT_DIR=~/ObsidianVault/VideoNotes

# Verify setup
python scripts/setup_check.py
```

## Fallback Behavior

When `VLEC_OPENAI_API_KEY` is not set, the skill automatically falls back to rule-based generation:
- Lecture notes: Generated from transcription segments with basic structuring
- Mindmaps: Generated from section titles with hierarchical layout
- Knowledge Q&A: Returns "knowledge base not available" message
- Auto-tagging: Not available (requires LLM)

The fallback ensures the skill never completely fails, but output quality is significantly lower than LLM-powered generation.
