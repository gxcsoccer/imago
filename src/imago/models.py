from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    intent: str = Field(..., description="Natural language intent or raw prompt")
    style: str | None = Field(None, description="Style template name")
    raw_prompt: bool = Field(False, description="If True, skip prompt expansion")
    count: int = Field(1, ge=1, le=20)
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    seed: int | None = None
    output: list[str] = Field(default_factory=lambda: ["local"])
    variables: dict[str, list[str]] | None = Field(
        None, description="Variables for cartesian product expansion"
    )
    callback_url: str | None = None
    image_url: str | None = Field(
        None, description="Reference image for img2img: local path or HTTP URL"
    )
    image_strength: float | None = Field(
        None, ge=0.0, le=1.0, description="How much to preserve from reference image (0.0-1.0)"
    )


class ImageResult(BaseModel):
    path: str
    seed: int
    prompt: str
    metadata_path: str


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    request: GenerateRequest
    images: list[ImageResult] = Field(default_factory=list)
    error: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
