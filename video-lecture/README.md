# Video Lecture Skill

> 🎬 视频转结构化讲义与思维导图工具，支持 B站、YouTube、抖音及本地文件

- 自动下载视频/提取音频
- 本地 Whisper 或云端 API 语音转写
- LLM 生成结构化讲义（章节、核心概念、示例、思考题）
- 生成 Mermaid 格式思维导图
- 支持关键帧截图，嵌入讲义
- 知识库语义搜索与 RAG 问答
- Obsidian 笔记导出
- 多页面视频汇总

---

## 快速开始

### 前置依赖

- Python 3.11+
- FFmpeg (音频/视频处理)

```bash
# 安装 FFmpeg
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install ffmpeg
# Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH
```

### 安装

```bash
# 克隆或下载项目
cd video-lecture

# 安装（开发模式）
pip install -e ".[dev]"
```

### 配置

复制 `assets/env.example` 到项目根目录或用户目录：
```bash
cp assets/env.example .env
# 编辑 .env 填入你的 API Key
```

最小配置只需设置 `VLEC_OPENAI_API_KEY`，其他使用默认值即可。

---

## 使用方式

### 方式 1：MCP 服务器（推荐，与 Claude Code / opencode 等集成）

在 Claude Code / opencode / Cursor 等支持 MCP 的工具中配置：

1. 打开 MCP 配置文件
   - Claude Code: `~/.config/claude/mcp.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. 添加以下配置（参考 [assets/mcp_config_example.json](file:///workspace/video-lecture/assets/mcp_config_example.json)）：

```json
{
  "mcpServers": {
    "video-lecture": {
      "command": "python",
      "args": ["/path/to/video-lecture/mcp_server.py"],
      "env": {
        "VLEC_OPENAI_API_KEY": "sk-your-api-key-here",
        "VLEC_OPENAI_BASE_URL": "https://api.openai.com/v1",
        "VLEC_TRANSCRIBE_MODE": "local"
      }
    }
  }
}
```

3. 重启 Claude Code，在聊天中询问视频相关问题或使用工具。

#### MCP 工具列表

| 工具 | 说明 |
|------|------|
| `process_video` | 处理在线视频，生成讲义和思维导图 |
| `process_local_file` | 处理本地视频或音频文件 |
| `resummary` | 复用已有转写，重新生成讲义 |
| `aggregate_summary` | 汇总多个任务，生成合集 |
| `extract_keyframes` | 从已处理视频提取关键帧截图 |
| `export_obsidian` | 导出为 Obsidian 格式笔记 |
| `save_results` | 保存到本地文件 |
| `search_knowledge` | 搜索知识库（需启用） |
| `ask_knowledge` | 基于知识库问答（需启用） |
| `add_tag` / `remove_tag` / `get_tags` | 标签管理 |
| `auto_tag` | 自动标签生成 |
| `get_tag_network` | 标签共现网络 |
| `get_knowledge_stats` | 知识库统计 |
| `get_lecture_only` | 仅获取讲义 |
| `get_mindmap_only` | 仅获取思维导图 |
| `setup_check` | 环境检查 |
| `get_capabilities` | 功能列表 |

---

### 方式 2：命令行

```bash
# 处理在线视频
video-lecture https://www.bilibili.com/video/BV1xxx

# 仅获取讲义
video-lecture https://youtu.be/xxx --language en

# 本地视频
video-lecture /path/to/video.mp4 --title "我的视频"

# 云端转写模式（更快，但需要 API）
video-lecture https://xxx --mode cloud

# 保存到指定目录
video-lecture https://xxx --output ./output

# 启动 HTTP API 服务
video-lecture --serve
```

---

### 方式 3：Python 编程调用

```python
from video_lecture_skill import VideoLectureService, SkillSettings

settings = SkillSettings()
settings.openai_api_key = "sk-..."

service = VideoLectureService(settings)

# 处理在线视频
result = service.process_and_wait(
    url="https://www.bilibili.com/video/BV1xxx",
    title="可选标题",
    language="zh"
)
print(result["lecture_md"])

# 处理本地文件
result = service.process_local_file(
    file_path="/path/to/video.mp4",
    title="本地视频"
)

# 关键帧截图
service.extract_keyframes(task_id=result["task_id"])
```

---

## 配置说明

所有配置项见 [assets/env.example](file:///workspace/video-lecture/assets/env.example)。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `VLEC_OPENAI_API_KEY` | 必填 | OpenAI/兼容 API Key |
| `VLEC_OPENAI_BASE_URL` | `https://api.openai.com/v1` | API 地址 |
| `VLEC_OPENAI_MODEL` | `gpt-4o-mini` | 使用的模型 |
| `VLEC_TRANSCRIBE_MODE` | `local` | `local` (Whisper) 或 `cloud` (API) |
| `VLEC_WHISPER_MODEL` | `base` | Whisper 模型大小 |
| `VLEC_WHISPER_DEVICE` | `cpu` | 推理设备：`cpu` / `cuda` / `mps` |
| `VLEC_LANGUAGE` | `zh` | 转写语言 |
| `VLEC_KNOWLEDGE_ENABLED` | `false` | 是否启用知识库 |
| `VLEC_OBSIDIAN_OUTPUT_DIR` | 空 | Obsidian 笔记默认保存目录 |
| `VLEC_DATA_DIR` | `~/.video-lecture/data` | 数据目录 |

---

## 知识库功能（可选）

启用知识库需要安装额外依赖：
```bash
pip install -e ".[knowledge]"
```

配置 `.env`：
```bash
VLEC_KNOWLEDGE_ENABLED=true
```

---

## 开发

```bash
# 运行测试
pytest tests/ -v
```

---

## 项目结构

```
video-lecture/
├── SKILL.md                # Agent Skills 规范入口
├── skill.yaml              # MCP 元数据
├── mcp_server.py           # MCP 服务器入口
├── pyproject.toml          # Python 项目配置
├── src/video_lecture_skill/  # 源代码
│   ├── service.py          # 核心服务
│   ├── pipeline.py         # 处理流程
│   ├── download.py         # 视频下载
│   ├── transcribe.py       # 语音转写
│   ├── lecture.py          # 讲义生成
│   ├── mindmap.py          # 思维导图
│   ├── frames.py           # 关键帧
│   ├── knowledge.py        # 知识库
│   ├── tags.py             # 标签
│   ├── llm.py              # LLM 调用
│   └── ...
├── assets/                 # 配置模板
├── references/             # 参考文档
└── tests/                  # 测试
```
