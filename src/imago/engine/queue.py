from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import aiosqlite

from imago.models import GenerateRequest, ImageResult, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    request TEXT NOT NULL,
    images TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    progress TEXT NOT NULL DEFAULT '{}',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class TaskQueue:
    def __init__(self, db_path: str = "imago_tasks.db") -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        # Reset any tasks stuck in "running" from a previous crash
        await self._db.execute(
            "UPDATE tasks SET status = 'pending' WHERE status = 'running'"
        )
        await self._db.commit()
        logger.info("TaskQueue initialized (db=%s)", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def submit(self, request: GenerateRequest) -> str:
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO tasks (id, status, request, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, "pending", request.model_dump_json(), now, now),
        )
        await self._db.commit()
        logger.info("Task %s submitted", task_id)
        return task_id

    async def claim_next(self) -> tuple[str, GenerateRequest] | None:
        cursor = await self._db.execute(
            "SELECT id, request FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        task_id = row["id"]
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        await self._db.commit()
        req = GenerateRequest.model_validate_json(row["request"])
        return task_id, req

    async def update_progress(
        self, task_id: str, completed: int, total: int, images: list[ImageResult]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        progress = json.dumps({"completed": completed, "total": total})
        images_json = json.dumps([img.model_dump() for img in images])
        await self._db.execute(
            "UPDATE tasks SET progress = ?, images = ?, updated_at = ? WHERE id = ?",
            (progress, images_json, now, task_id),
        )
        await self._db.commit()

    async def complete(self, task_id: str, images: list[ImageResult]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        images_json = json.dumps([img.model_dump() for img in images])
        await self._db.execute(
            "UPDATE tasks SET status = 'completed', images = ?, updated_at = ? WHERE id = ?",
            (images_json, now, task_id),
        )
        await self._db.commit()
        logger.info("Task %s completed (%d images)", task_id, len(images))

    async def fail(self, task_id: str, error: str) -> bool:
        """Mark task as failed. Returns True if it was re-queued for retry."""
        cursor = await self._db.execute(
            "SELECT retry_count, max_retries FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        now = datetime.now(timezone.utc).isoformat()

        if row and row["retry_count"] < row["max_retries"]:
            await self._db.execute(
                "UPDATE tasks SET status = 'pending', retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            await self._db.commit()
            logger.warning("Task %s failed, re-queued (retry %d)", task_id, row["retry_count"] + 1)
            return True

        await self._db.execute(
            "UPDATE tasks SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (error, now, task_id),
        )
        await self._db.commit()
        logger.error("Task %s failed permanently: %s", task_id, error)
        return False

    async def get(self, task_id: str) -> TaskResult | None:
        cursor = await self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return TaskResult(
            task_id=row["id"],
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            request=GenerateRequest.model_validate_json(row["request"]),
            images=[ImageResult(**img) for img in json.loads(row["images"])],
            error=row["error"],
            progress=json.loads(row["progress"]),
        )
