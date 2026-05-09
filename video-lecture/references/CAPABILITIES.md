# Capabilities

## Supported Platforms

| Platform | URL Format | Multi-Page | Notes |
|----------|-----------|------------|-------|
| Bilibili | `bilibili.com/video/BVxxx` or `BVxxx` | ✅ | Supports multi-P via `page_number` |
| YouTube | `youtube.com/watch?v=xxx` or `youtu.be/xxx` | ❌ | — |
| Douyin | `douyin.com/video/xxx` | ❌ | — |
| Generic | Any yt-dlp supported URL | ❌ | Depends on yt-dlp |
| Local | File path | ❌ | Video or audio file |

## Transcription Modes

| Mode | Engine | Requirements | Quality | Speed |
|------|--------|-------------|---------|-------|
| `local` | faster-whisper | whisper model download | Good | Medium |
| `cloud` | OpenAI Whisper API | `VLEC_OPENAI_API_KEY` | Best | Fast |

## Output Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Markdown | `.md` | Structured lecture with sections, concepts, examples, quizzes |
| Mermaid | `.mmd` | Hierarchical mindmap in Mermaid syntax |
| JSON | `.json` | Complete PipelineResult object |
| Obsidian | `.md` | Markdown with YAML frontmatter metadata |
| Transcript | `.txt` | Timestamped transcription text |

## Feature Matrix

| Feature | MCP Tool | Script | CLI | REST API |
|---------|----------|--------|-----|----------|
| Process video | `process_video` | `scripts/process_video.py` | ✅ | `POST /process` |
| Get lecture only | `get_lecture_only` | `scripts/process_video.py --format lecture` | ✅ | `POST /lecture` |
| Get mindmap only | `get_mindmap_only` | `scripts/process_video.py --format mindmap` | ✅ | `POST /mindmap` |
| Save to files | `save_results` | `scripts/process_video.py --output-dir` | ✅ | `POST /save` |
| Knowledge search | `search_knowledge` | `scripts/knowledge_query.py search` | ✅ | `POST /knowledge/search` |
| Knowledge Q&A | `ask_knowledge` | `scripts/knowledge_query.py ask` | ✅ | `POST /knowledge/ask` |
| Add tag | `add_tag` | — | ✅ | `POST /tags/add` |
| Remove tag | `remove_tag` | — | ✅ | `DELETE /tags/remove` |
| Auto tag | `auto_tag` | — | ✅ | `POST /tags/auto` |
| Tag network | `get_tag_network` | — | ✅ | `GET /tags/network` |
| Resummary | `resummary` | — | ✅ | `POST /resummary` |
| Aggregate summary | `aggregate_summary` | — | ✅ | `POST /aggregate` |
| Export Obsidian | `export_obsidian` | `scripts/export_obsidian.py` | ✅ | `POST /export/obsidian` |
| Knowledge stats | `get_knowledge_stats` | — | ✅ | `GET /knowledge/stats` |
| Capabilities | `get_capabilities` | — | ✅ | `GET /capabilities` |

## Resource Limits

| Limit | Value |
|-------|-------|
| Max video duration | 7200 seconds (2 hours) |
| Max transcript chars | 500,000 |
| Max lecture sections | 20 |
| Max concurrent tasks | 5 |
| Max knowledge search results | 50 |
| Max tag network nodes | 50 |
