from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.export import export_to_files
from video_lecture_skill.models import TaskInput, TaskOutputFormat, TranscribeMode
from video_lecture_skill.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Video Lecture Skill - 视频转讲义与思维导图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  video-lecture https://www.bilibili.com/video/BV1R6NFzXE1H/
  video-lecture https://www.youtube.com/watch?v=dQw4w9WgXcQ --title "视频标题"
  video-lecture https://www.bilibili.com/video/BV1R6NFzXE1H/ --mode cloud --output ./output
        """,
    )
    parser.add_argument("url", help="视频链接（支持B站、YouTube、抖音等）")
    parser.add_argument("--title", "-t", help="视频标题（可选，默认自动探测）")
    parser.add_argument("--language", "-l", default="zh", help="转写语言（默认 zh）")
    parser.add_argument("--mode", "-m", choices=["local", "cloud"], default=None, help="转写模式：local=本地Whisper, cloud=云API")
    parser.add_argument("--output", "-o", default=None, help="输出目录（默认 ~/.video-lecture/data/tasks/latest）")
    parser.add_argument("--api-key", default=None, help="OpenAI API Key（也可通过 VLEC_OPENAI_API_KEY 环境变量设置）")
    parser.add_argument("--base-url", default=None, help="OpenAI Base URL（也可通过 VLEC_OPENAI_BASE_URL 环境变量设置）")
    parser.add_argument("--model", default=None, help="LLM 模型名（也可通过 VLEC_OPENAI_MODEL 环境变量设置）")
    parser.add_argument("--serve", "-s", action="store_true", help="启动 API 服务模式")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    settings = SkillSettings()
    settings.ensure_dirs()

    if args.api_key:
        settings = settings.model_copy(update={"openai_api_key": args.api_key})
    if args.base_url:
        settings = settings.model_copy(update={"openai_base_url": args.base_url})
    if args.model:
        settings = settings.model_copy(update={"openai_model": args.model})

    if args.serve:
        return _serve(settings)

    return _process(args, settings)


def _process(args: argparse.Namespace, settings: SkillSettings) -> int:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

    console = Console()
    console.print(f"[bold blue]🎬 Video Lecture Skill[/bold blue]")
    console.print(f"视频链接: {args.url}")

    transcribe_mode = TranscribeMode.CLOUD if args.mode == "cloud" else settings.transcribe_mode

    task_input = TaskInput(
        url=args.url,
        title=args.title,
        language=args.language,
        transcribe_mode=transcribe_mode,
    )

    output_dir = Path(args.output) if args.output else None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("处理中...", total=100)

        def on_event(event):
            progress.update(task, completed=event.progress, description=f"[{event.stage}] {event.message}")

        try:
            result = run_pipeline(task_input=task_input, settings=settings, emit=on_event)
        except Exception as exc:
            console.print(f"[bold red]❌ 处理失败: {exc}[/bold red]")
            return 1

    if output_dir:
        artifacts = export_to_files(result, output_dir)
    else:
        artifacts = result.artifacts

    console.print("\n[bold green]✅ 处理完成！[/bold green]")
    console.print(f"  标题: {result.lecture.title}")
    console.print(f"  章节数: {len(result.lecture.sections)}")
    console.print(f"  转写字数: {len(result.transcription.transcript)}")

    if artifacts:
        console.print("\n[bold]输出文件:[/bold]")
        for key, path in artifacts.items():
            console.print(f"  {key}: {path}")

    return 0


def _serve(settings: SkillSettings) -> int:
    import uvicorn

    from video_lecture_skill.api import app

    logging.info("starting api server host=%s port=%s", settings.host, settings.port)
    uvicorn.run(app, host=settings.host, port=settings.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
