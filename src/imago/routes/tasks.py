from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from imago.models import TaskResult

router = APIRouter()


@router.get("/tasks/{task_id}", response_model=TaskResult)
async def get_task(task_id: str, request: Request) -> TaskResult:
    queue = request.app.state.queue
    task = await queue.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
