from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import Lock, Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from video_lecture_skill.config import SkillSettings
from video_lecture_skill.export import export_json, export_markdown, export_mermaid, export_transcript
from video_lecture_skill.models import TaskInput, TaskOutputFormat, TaskRecord, TaskStatus
from video_lecture_skill.pipeline import run_pipeline

logger = logging.getLogger("video_lecture_skill.api")

settings = SkillSettings()
settings.ensure_dirs()


class TaskCreateRequest(BaseModel):
    url: str
    title: str | None = None
    language: str = "zh"
    output_formats: list[TaskOutputFormat] = Field(
        default_factory=lambda: [TaskOutputFormat.MARKDOWN, TaskOutputFormat.MERMAID, TaskOutputFormat.JSON]
    )


class TaskSummaryResponse(BaseModel):
    task_id: str
    status: TaskStatus
    url: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskDetailResponse(TaskSummaryResponse):
    lecture_md: str | None = None
    mindmap_mermaid: str | None = None
    transcript: str | None = None
    result_json: str | None = None
    error_message: str | None = None


class TaskProgressResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    latest_stage: str | None = None
    latest_message: str | None = None


class TaskEventRecord(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    stage: str
    progress: int = 0
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


_tasks: dict[str, TaskRecord] = {}
_events: dict[str, list[TaskEventRecord]] = {}
_lock = Lock()


def _store_task(record: TaskRecord) -> None:
    with _lock:
        _tasks[record.task_id] = record
        if record.task_id not in _events:
            _events[record.task_id] = []


def _append_event(task_id: str, stage: str, progress: int, message: str) -> None:
    with _lock:
        event = TaskEventRecord(task_id=task_id, stage=stage, progress=progress, message=message)
        if task_id not in _events:
            _events[task_id] = []
        _events[task_id].append(event)


def _update_task_status(task_id: str, task_status: TaskStatus, error_message: str | None = None) -> None:
    with _lock:
        if task_id in _tasks:
            record = _tasks[task_id]
            updated = record.model_copy(update={
                "status": task_status,
                "error_message": error_message,
                "updated_at": datetime.now(timezone.utc),
            })
            _tasks[task_id] = updated


def _run_task(task_id: str, task_input: TaskInput) -> None:
    _append_event(task_id, "queued", 0, "任务已进入后台队列")
    _update_task_status(task_id, TaskStatus.RUNNING)
    _append_event(task_id, "running", 5, "任务开始执行")

    try:
        result = run_pipeline(
            task_input=task_input,
            settings=settings,
            emit=lambda event: _append_event(task_id, event.stage, event.progress, event.message),
        )
        with _lock:
            if task_id in _tasks:
                record = _tasks[task_id]
                _tasks[task_id] = record.model_copy(update={
                    "status": TaskStatus.COMPLETED,
                    "result": result,
                    "updated_at": datetime.now(timezone.utc),
                })
        _append_event(task_id, "completed", 100, "任务已完成")
    except Exception as exc:
        logger.exception("task failed task_id=%s error=%s", task_id, exc)
        _update_task_status(task_id, TaskStatus.FAILED, str(exc))
        _append_event(task_id, "failed", 100, f"任务执行失败：{exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("video-lecture-skill api starting host=%s port=%s", settings.host, settings.port)
    yield
    logger.info("video-lecture-skill api shutdown")


app = FastAPI(
    title="Video Lecture Skill API",
    version="0.1.0",
    description="视频转讲义与思维导图 Skill 后端 API",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "video-lecture-skill", "version": "0.1.0"}


@app.post("/api/v1/tasks", response_model=TaskSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_task(request: TaskCreateRequest):
    task_input = TaskInput(
        url=request.url,
        title=request.title,
        language=request.language,
        output_formats=request.output_formats,
    )
    record = TaskRecord(task_input=task_input)
    _store_task(record)

    thread = Thread(target=_run_task, args=(record.task_id, task_input), daemon=True)
    thread.start()

    return TaskSummaryResponse(
        task_id=record.task_id,
        status=record.status,
        url=task_input.url,
        title=task_input.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/api/v1/tasks", response_model=list[TaskSummaryResponse])
def list_tasks():
    with _lock:
        return [
            TaskSummaryResponse(
                task_id=r.task_id,
                status=r.status,
                url=r.task_input.url,
                title=r.task_input.title,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in _tasks.values()
        ]


@app.get("/api/v1/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: str):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")

    lecture_md = export_markdown(record.result) if record.result else None
    mindmap_mermaid = export_mermaid(record.result) if record.result else None
    transcript = export_transcript(record.result) if record.result else None
    result_json = export_json(record.result) if record.result else None

    return TaskDetailResponse(
        task_id=record.task_id,
        status=record.status,
        url=record.task_input.url,
        title=record.task_input.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
        lecture_md=lecture_md,
        mindmap_mermaid=mindmap_mermaid,
        transcript=transcript,
        result_json=result_json,
        error_message=record.error_message,
    )


@app.get("/api/v1/tasks/{task_id}/lecture")
def get_lecture(task_id: str):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if record.result is None:
        raise HTTPException(status_code=400, detail="Task result not ready")
    return {"lecture_md": export_markdown(record.result)}


@app.get("/api/v1/tasks/{task_id}/mindmap")
def get_mindmap(task_id: str):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if record.result is None:
        raise HTTPException(status_code=400, detail="Task result not ready")
    return {"mermaid": export_mermaid(record.result)}


@app.get("/api/v1/tasks/{task_id}/transcript")
def get_transcript(task_id: str):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if record.result is None:
        raise HTTPException(status_code=400, detail="Task result not ready")
    return {"transcript": export_transcript(record.result)}


@app.get("/api/v1/tasks/{task_id}/progress", response_model=TaskProgressResponse)
def get_task_progress(task_id: str):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    with _lock:
        events = _events.get(task_id, [])
    latest = events[-1] if events else None
    return TaskProgressResponse(
        task_id=record.task_id,
        status=record.status,
        progress=latest.progress if latest else 0,
        latest_stage=latest.stage if latest else None,
        latest_message=latest.message if latest else None,
    )


@app.get("/api/v1/tasks/{task_id}/events/stream")
async def stream_task_events(task_id: str, after: str | None = None):
    with _lock:
        record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_seen = after
        idle_ticks = 0
        terminal_statuses = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}

        while True:
            with _lock:
                current_record = _tasks.get(task_id)
                events = _events.get(task_id, [])

            if current_record is None:
                yield f"event: error\ndata: {{\"message\":\"Task not found.\"}}\n\n"
                return

            new_events = []
            for ev in events:
                if last_seen is None or ev.created_at.isoformat() > last_seen:
                    new_events.append(ev)

            if new_events:
                idle_ticks = 0
                for ev in new_events:
                    last_seen = ev.created_at.isoformat()
                    payload = {
                        "event": {"stage": ev.stage, "progress": ev.progress, "message": ev.message},
                        "status": current_record.status.value,
                    }
                    yield f"event: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                idle_ticks += 1

            with _lock:
                current_record = _tasks.get(task_id)
            if current_record is not None and current_record.status in terminal_statuses:
                if idle_ticks >= 2:
                    return

            if idle_ticks >= 20:
                yield "event: heartbeat\ndata: {}\n\n"
                idle_ticks = 0

            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/v1/tasks/{task_id}")
def delete_task(task_id: str):
    with _lock:
        if task_id not in _tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        del _tasks[task_id]
        _events.pop(task_id, None)
    return {"deleted": True, "task_id": task_id}
