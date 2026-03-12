from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from imago.models import GenerateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate")
async def generate(req: GenerateRequest, request: Request) -> dict:
    queue = request.app.state.queue
    task_id = await queue.submit(req)
    return {"task_id": task_id}


@router.get("/styles")
async def list_styles(request: Request) -> list[dict[str, str]]:
    return request.app.state.style_registry.list_styles()
