from __future__ import annotations

import logging
import time

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


@router.get("/status")
async def status(request: Request) -> dict:
    generator = request.app.state.generator
    idle_timeout = generator.settings.idle_timeout
    loaded = generator.loaded
    idle_seconds = (
        round(time.monotonic() - generator._last_used)
        if loaded and generator._last_used > 0
        else None
    )
    return {
        "model": generator.settings.model,
        "quantize": generator.settings.quantize,
        "loaded": loaded,
        "idle_seconds": idle_seconds,
        "idle_timeout": idle_timeout,
    }
