from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


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
        None, ge=0.0, le=1.0,
        description="How much of the reference image to preserve (0.0=ignore, 1.0=keep exactly). "
                    "For style transfer use 0.25-0.35. For subtle edits use 0.5-0.7. Default 0.35.",
    )

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"callback_url scheme must be 'http' or 'https', got {parsed.scheme!r}"
            )
        if not parsed.hostname:
            raise ValueError("callback_url must include a hostname")
        return v

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parsed = urlparse(v)
        # Allow local paths (empty scheme) but reject any non-HTTP URI scheme
        # to prevent file://, ftp://, data:// etc. from reaching the worker.
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"image_url scheme must be 'http' or 'https' (or a bare local path), "
                f"got {parsed.scheme!r}"
            )
        return v


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
