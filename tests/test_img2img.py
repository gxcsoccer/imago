"""Tests for img2img functionality."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imago.engine.generator import GeneratedImage
from imago.models import GenerateRequest
from imago.output.manager import OutputManager


# ── Model tests ──────────────────────────────────────────────


def test_generate_request_accepts_img2img_fields():
    req = GenerateRequest(
        intent="make it warmer",
        image_url="/path/to/ref.png",
        image_strength=0.6,
    )
    assert req.image_url == "/path/to/ref.png"
    assert req.image_strength == 0.6


def test_generate_request_img2img_fields_optional():
    req = GenerateRequest(intent="a cat")
    assert req.image_url is None
    assert req.image_strength is None


def test_image_strength_validation():
    with pytest.raises(Exception):
        GenerateRequest(intent="x", image_strength=1.5)
    with pytest.raises(Exception):
        GenerateRequest(intent="x", image_strength=-0.1)


# ── Output metadata tests ───────────────────────────────────


def test_output_metadata_includes_img2img(test_settings):
    mock_image = MagicMock()
    mock_image.save = MagicMock()

    mgr = OutputManager(test_settings)
    result = GeneratedImage(image=mock_image, seed=99, prompt="warmer tones")
    img_result = mgr.save(
        result,
        intent="warm it up",
        image_url="/ref/photo.png",
        image_strength=0.5,
    )

    meta = json.loads(Path(img_result.metadata_path).read_text())
    assert meta["image_url"] == "/ref/photo.png"
    assert meta["image_strength"] == 0.5


def test_output_metadata_no_img2img_fields(test_settings):
    mock_image = MagicMock()
    mock_image.save = MagicMock()

    mgr = OutputManager(test_settings)
    result = GeneratedImage(image=mock_image, seed=99, prompt="a cat")
    img_result = mgr.save(result, intent="a cat")

    meta = json.loads(Path(img_result.metadata_path).read_text())
    assert "image_url" not in meta
    assert "image_strength" not in meta


# ── Resolve image tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_image_local_path():
    from imago.engine.worker import _resolve_image

    result = await _resolve_image("/some/local/file.png", Path("/tmp"))
    assert result == "/some/local/file.png"


@pytest.mark.asyncio
async def test_resolve_image_http_download(tmp_path, httpx_mock):
    from imago.engine.worker import _resolve_image

    httpx_mock.add_response(
        url="https://example.com/photo.png",
        content=b"\x89PNG fake image data",
    )

    result = await _resolve_image("https://example.com/photo.png", tmp_path)

    assert result.startswith(str(tmp_path / "_ref"))
    assert result.endswith(".png")
    assert Path(result).read_bytes() == b"\x89PNG fake image data"


# ── Route tests ──────────────────────────────────────────────


def test_generate_img2img_returns_task_id(client):
    resp = client.post(
        "/generate",
        json={
            "intent": "cyberpunk style",
            "image_url": "/path/to/ref.png",
            "image_strength": 0.5,
            "raw_prompt": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data


def test_generate_rejects_invalid_strength(client):
    resp = client.post(
        "/generate",
        json={
            "intent": "test",
            "image_url": "/ref.png",
            "image_strength": 2.0,
        },
    )
    assert resp.status_code == 422
