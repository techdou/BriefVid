from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from video_lecture_skill.models import (
    PipelineResult,
    TaskRecord,
    TaskStatus,
)

logger = logging.getLogger("video_lecture_skill.task_store")


class TaskStore:
    def __init__(self, tasks_dir: Path, max_tasks: int = 200):
        self._tasks_dir = tasks_dir / "results"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._max_tasks = max_tasks
        self._lock = threading.Lock()
        self._cache: dict[str, PipelineResult] = {}
        self._records: dict[str, TaskRecord] = {}
        self._load_all()

    def _task_path(self, task_id: str) -> Path:
        return self._tasks_dir / f"{task_id}.json"

    def _record_path(self, task_id: str) -> Path:
        return self._tasks_dir / f"{task_id}.record.json"

    def _load_all(self) -> None:
        for fp in self._tasks_dir.glob("*.json"):
            if fp.name.endswith(".record.json"):
                continue
            task_id = fp.stem
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                self._cache[task_id] = PipelineResult.model_validate(data)
            except Exception as exc:
                logger.warning("failed to load task %s: %s", task_id, exc)

        for fp in self._tasks_dir.glob("*.record.json"):
            task_id = fp.stem.replace(".record", "")
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                self._records[task_id] = TaskRecord.model_validate(data)
            except Exception as exc:
                logger.warning("failed to load record %s: %s", task_id, exc)

        logger.info("TaskStore loaded %d results, %d records", len(self._cache), len(self._records))

    def save(self, task_id: str, result: PipelineResult) -> None:
        with self._lock:
            self._cache[task_id] = result
            try:
                self._task_path(task_id).write_text(
                    result.model_dump_json(indent=2), encoding="utf-8"
                )
            except Exception as exc:
                logger.error("failed to persist task %s: %s", task_id, exc)
            self._evict()

    def save_record(self, task_id: str, record: TaskRecord) -> None:
        with self._lock:
            self._records[task_id] = record
            try:
                self._record_path(task_id).write_text(
                    record.model_dump_json(indent=2), encoding="utf-8"
                )
            except Exception as exc:
                logger.error("failed to persist record %s: %s", task_id, exc)

    def get(self, task_id: str) -> PipelineResult | None:
        with self._lock:
            return self._cache.get(task_id)

    def get_record(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def delete(self, task_id: str) -> bool:
        with self._lock:
            removed = False
            if task_id in self._cache:
                del self._cache[task_id]
                removed = True
            if task_id in self._records:
                del self._records[task_id]
            tp = self._task_path(task_id)
            if tp.exists():
                tp.unlink()
                removed = True
            rp = self._record_path(task_id)
            if rp.exists():
                rp.unlink()
                removed = True
            return removed

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TaskRecord]:
        with self._lock:
            records = list(self._records.values())

        if status is not None:
            records = [r for r in records if r.status == status]

        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[offset : offset + limit]

    def list_all_ids(self) -> list[str]:
        with self._lock:
            return list(self._cache.keys())

    def update_record_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: str | None = None,
        result: PipelineResult | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if error_message is not None:
                record.error_message = error_message
            if result is not None:
                record.result = result
                self._cache[task_id] = result
                try:
                    self._task_path(task_id).write_text(
                        result.model_dump_json(indent=2), encoding="utf-8"
                    )
                except Exception as exc:
                    logger.error("failed to persist task %s: %s", task_id, exc)
            try:
                self._record_path(task_id).write_text(
                    record.model_dump_json(indent=2), encoding="utf-8"
                )
            except Exception as exc:
                logger.error("failed to persist record %s: %s", task_id, exc)
            return record

    def count(self) -> int:
        with self._lock:
            return len(self._cache)

    def _evict(self) -> None:
        if len(self._cache) <= self._max_tasks:
            return
        sorted_ids = sorted(
            self._cache.keys(),
            key=lambda tid: self._records[tid].created_at if tid in self._records else datetime.min.replace(tzinfo=timezone.utc),
        )
        to_remove = sorted_ids[: len(self._cache) - self._max_tasks]
        for tid in to_remove:
            self._cache.pop(tid, None)
            self._records.pop(tid, None)
            tp = self._task_path(tid)
            if tp.exists():
                tp.unlink()
            rp = self._record_path(tid)
            if rp.exists():
                rp.unlink()
        logger.info("evicted %d old tasks", len(to_remove))
