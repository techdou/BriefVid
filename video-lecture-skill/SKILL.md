---
name: video-lecture
description: >
  Convert video lectures into structured Markdown notes, Mermaid mindmaps, and Obsidian notes.
  Supports Bilibili (multi-page), YouTube, Douyin, and local video/audio files.
  Includes knowledge base RAG search & Q&A, auto-tagging, tag network visualization,
  aggregate summary across multiple pages, resummary, and Obsidian export with YAML frontmatter.
  Use when the user wants to: summarize a video, generate lecture notes, create a mindmap,
  search video knowledge, ask questions about video content, tag videos, or export to Obsidian.
license: MIT
compatibility: Requires Python 3.11+, ffmpeg, and optional chromadb + sentence-transformers for knowledge base features.
metadata:
  version: "0.2.0"
  author: community
  api_version: "v2"
  entry_point: "video_lecture_skill.api:app"
  cli_entry: "video_lecture_skill.cli:main"
  config_prefix: VLEC_
  mcp_entry: "mcp_server:main"
allowed-tools: Bash(python:*) Bash(ffmpeg:*) Bash(yt-dlp:*) Read Write
---

# Video Lecture Skill

> 视频转讲义与思维导图 — 输入视频链接，自动生成结构化课程笔记和知识库

## When to Use

当用户请求以下操作时使用此 Skill：

- 将视频内容整理成讲义或笔记
- 生成视频的思维导图
- 搜索或提问已处理视频的知识内容
- 为视频添加标签或查看标签网络
- 导出笔记到 Obsidian
- 处理 B 站多 P 视频，生成合集总结
- 重新生成已有视频的摘要（重摘要）
- 处理本地视频或音频文件

## Instructions

### 1. 首次使用检查

首次使用时，运行环境检查脚本确认依赖是否就绪：

```bash
python scripts/setup_check.py
```

如果报告缺少依赖，按提示安装后再继续。

### 2. 处理视频生成讲义

通过 MCP 工具 `process_video` 处理视频：

- **必填参数**：`url` — 视频链接
- **可选参数**：`title`（标题）、`language`（语言，默认 zh）、`transcribe_mode`（local/cloud）、`page_number`（B 站分 P 号）

支持的链接格式：
- B 站：`https://www.bilibili.com/video/BV1xxx` 或直接 `BV1xxx`
- YouTube：`https://www.youtube.com/watch?v=xxx` 或 `https://youtu.be/xxx`
- 抖音：`https://www.douyin.com/video/xxx`
- 本地文件：直接传入文件路径

示例：
```
process_video(url="https://www.bilibili.com/video/BV1R6NFzXE1H/")
process_video(url="BV1R6NFzXE1H", page_number=2)
```

### 3. 仅获取讲义或思维导图

如果只需要部分结果，使用更轻量的工具：

- `get_lecture_only` — 仅返回 Markdown 讲义
- `get_mindmap_only` — 仅返回 Mermaid 思维导图

### 4. 知识库搜索与问答

处理过的视频会自动索引到知识库（需启用 `VLEC_KNOWLEDGE_ENABLED=true`）：

- `search_knowledge(query="机器学习基础")` — 语义搜索相关视频片段
- `ask_knowledge(query="什么是反向传播？")` — 基于知识库的 RAG 问答

问答支持多轮对话，传入 `history` 参数即可。

### 5. 标签管理

- `add_tag(video_id, tag)` — 手动添加标签
- `auto_tag(video_id, content)` — LLM 自动生成 3-8 个标签
- `get_tag_network(selected_tags="Python,ML")` — 查看标签共现网络
- `get_tags(video_id)` — 查看视频标签

### 6. 多 P 视频聚合与重摘要

- `aggregate_summary(task_ids="t1,t2,t3")` — 汇总多个任务结果
- `resummary(task_id)` — 复用转写文本重新生成摘要

### 7. 导出为 Obsidian 笔记

```
export_obsidian(task_id="xxx", output_dir="/path/to/obsidian/vault")
```

生成的笔记包含 YAML frontmatter（标题、来源、平台、标签等元数据）和结构化正文。

### 8. 保存结果到文件

```
save_results(url="https://...", output_dir="/path/to/output")
```

会在指定目录生成 transcript.txt、lecture.md、mindmap.mmd、result.json。

## Edge Cases

- **LLM 不可用**：自动降级为本地规则生成，讲义质量会降低但不会失败
- **视频下载失败**：返回 DOWNLOAD_ERROR，通常是网络问题或链接无效，建议用户检查链接
- **转写超时**：长视频（>2 小时）建议使用 cloud 模式转写
- **知识库未启用**：search_knowledge 和 ask_knowledge 会返回提示信息
- **B 站多 P 视频**：默认只处理第 1 P，需指定 `page_number` 处理其他分 P
- **Obsidian 导出目录不存在**：会自动创建

## Configuration

环境变量以 `VLEC_` 为前缀，关键配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VLEC_TRANSCRIBE_MODE` | local | 转写模式：local 或 cloud |
| `VLEC_OPENAI_API_KEY` | — | LLM API 密钥（必需，用于生成高质量讲义） |
| `VLEC_OPENAI_BASE_URL` | https://api.openai.com/v1 | LLM API 地址 |
| `VLEC_OPENAI_MODEL` | gpt-4o-mini | LLM 模型名称 |
| `VLEC_KNOWLEDGE_ENABLED` | false | 是否启用知识库 |
| `VLEC_OBSIDIAN_OUTPUT_DIR` | — | Obsidian 导出目录 |

完整配置参考见 [references/CONFIGURATION.md](references/CONFIGURATION.md)。

## Capabilities

完整能力列表见 [references/CAPABILITIES.md](references/CAPABILITIES.md)。
