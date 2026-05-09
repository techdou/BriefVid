# Technical Reference

## Architecture

video-lecture-skill uses a layered architecture:

```
┌─────────────────────────────────────────┐
│  Interfaces (MCP / REST API / CLI)      │
├─────────────────────────────────────────┤
│  Service Layer (VideoLectureService)     │
├─────────────────────────────────────────┤
│  Pipeline (download → transcribe →      │
│            lecture → mindmap → export)   │
├─────────────────────────────────────────┤
│  Modules                                 │
│  ├── download.py    (yt-dlp)            │
│  ├── transcribe.py  (faster-whisper)    │
│  ├── lecture.py     (LLM + rules)       │
│  ├── mindmap.py     (LLM + rules)       │
│  ├── knowledge.py   (ChromaDB + RAG)    │
│  ├── tags.py        (LLM auto-tag)      │
│  └── export.py      (MD/Obsidian/JSON)  │
├─────────────────────────────────────────┤
│  Infrastructure                          │
│  ├── config.py     (SkillSettings)      │
│  ├── models.py     (Pydantic models)    │
│  └── errors.py     (Error hierarchy)    │
└─────────────────────────────────────────┘
```

## MCP Tools Reference

### Core Processing

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `process_video` | Full pipeline: download → transcribe → lecture → mindmap | `url`, `title`, `language`, `transcribe_mode`, `page_number` |
| `get_lecture_only` | Returns only the Markdown lecture | `url`, `title`, `language` |
| `get_mindmap_only` | Returns only the Mermaid mindmap | `url`, `title`, `language` |
| `save_results` | Process and save all files to a directory | `url`, `output_dir`, `title`, `language` |

### Knowledge Base

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `search_knowledge` | Semantic search across processed videos | `query`, `limit`, `tags` |
| `ask_knowledge` | RAG Q&A with LLM answer generation | `query`, `context_limit`, `history` |
| `get_knowledge_stats` | Statistics about the knowledge base | — |

### Tagging

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `add_tag` | Add a tag to a video | `video_id`, `tag` |
| `remove_tag` | Remove a tag from a video | `video_id`, `tag` |
| `get_tags` | List tags (all or for a video) | `video_id` (optional) |
| `auto_tag` | LLM auto-generate tags | `video_id`, `content` |
| `get_tag_network` | Tag co-occurrence network | `selected_tags`, `max_tags` |

### Advanced

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `resummary` | Re-generate summary from existing transcription | `task_id` |
| `aggregate_summary` | Combine multiple task results into one summary | `task_ids` (comma-separated) |
| `export_obsidian` | Export as Obsidian note with YAML frontmatter | `task_id`, `output_dir` |
| `get_capabilities` | Query supported platforms and features | — |

## MCP Resources

| URI | Description |
|-----|-------------|
| `video-lecture://config` | Current configuration snapshot |

## MCP Prompts

| Prompt | Description |
|--------|-------------|
| `video_lecture_prompt` | Template for requesting video lecture generation |

## Data Models

### VideoInfo

```python
class VideoInfo:
    id: str               # Auto-generated
    url: str              # Source URL
    title: str            # Video title
    platform: str         # bilibili / youtube / douyin / generic / local
    duration: float       # Duration in seconds
    thumbnail: str        # Cover image URL
    canonical_id: str     # Platform-specific ID (e.g., BV1xxx)
    pages: list           # Multi-page info (Bilibili)
    is_multi_page: bool   # Whether video has multiple pages
```

### PipelineResult

```python
class PipelineResult:
    video_info: VideoInfo
    transcription: TranscriptionResult
    lecture: LectureNote
    mindmap: MindmapResult
    overview: str                  # Core overview text
    key_points: list[str]          # Key takeaways
    knowledge_note_markdown: str   # Knowledge notes in Markdown
    timeline: list[dict]           # Chapter timeline with timestamps
    tags: list[str]                # Auto or manual tags
    artifacts: dict[str, str]      # Output file paths
```

## Error Codes

| Code | Message | Recoverable |
|------|---------|-------------|
| `DOWNLOAD_ERROR` | Video download failed | Yes |
| `TRANSCRIBE_ERROR` | Audio transcription failed | Yes |
| `LLM_ERROR` | LLM generation failed (auto-fallback to rules) | Yes |
| `UNSUPPORTED_PLATFORM` | Unsupported video platform | No |
| `TIMEOUT` | Processing timeout | Yes |
| `KNOWLEDGE_NOT_ENABLED` | Knowledge base not enabled | Yes |
| `KNOWLEDGE_DEPENDENCY_MISSING` | Missing chromadb/sentence-transformers | Yes |
| `TASK_NOT_FOUND` | Specified task does not exist | No |

## Pipeline Stages

| Stage | Progress | Description |
|-------|----------|-------------|
| preparing | 0-5 | Normalize video URL |
| downloading | 5-50 | Download video and extract audio |
| transcribing | 50-85 | Speech-to-text |
| lecture | 85-95 | Generate lecture notes |
| mindmap | 95-97 | Generate mindmap |
| exporting | 97-100 | Export result files |
| indexing | 100 | Index to knowledge base |
| completed | 100 | Done |
