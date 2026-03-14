"""Tests for the send_callback webhook helper."""
from __future__ import annotations

import json
import socket
from unittest.mock import patch

import pytest

from imago.models import ImageResult, TaskStatus
from imago.output.webhook import send_callback

_SAMPLE_IMAGES = [
    ImageResult(
        path="/output/img.png",
        seed=42,
        prompt="a cat",
        metadata_path="/output/img.json",
    )
]


# ── SSRF guard ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_private_ip_is_refused(caplog):
    """send_callback must silently refuse private-IP URLs."""
    await send_callback(
        "http://127.0.0.1/hook",
        "abc123",
        TaskStatus.COMPLETED,
        _SAMPLE_IMAGES,
    )
    assert "unsafe" in caplog.text.lower() or "refusing" in caplog.text.lower()


@pytest.mark.asyncio
async def test_callback_file_scheme_is_refused(caplog):
    """send_callback must refuse non-HTTP URL schemes such as file://."""
    await send_callback(
        "file:///etc/passwd",
        "abc123",
        TaskStatus.COMPLETED,
        [],
    )
    assert "unsafe" in caplog.text.lower() or "refusing" in caplog.text.lower()


# ── Happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_success(httpx_mock):
    httpx_mock.add_response(url="http://1.2.3.4/hook", status_code=200)

    await send_callback(
        "http://1.2.3.4/hook",
        "task42",
        TaskStatus.COMPLETED,
        _SAMPLE_IMAGES,
    )

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["task_id"] == "task42"
    assert payload["status"] == "completed"
    assert len(payload["images"]) == 1


@pytest.mark.asyncio
async def test_callback_failure_payload(httpx_mock):
    httpx_mock.add_response(url="http://1.2.3.4/hook", status_code=200)

    await send_callback(
        "http://1.2.3.4/hook",
        "task99",
        TaskStatus.FAILED,
        [],
        error="something went wrong",
    )

    requests = httpx_mock.get_requests()
    payload = json.loads(requests[0].content)
    assert payload["status"] == "failed"
    assert payload["error"] == "something went wrong"
    assert payload["images"] == []


@pytest.mark.asyncio
async def test_callback_http_error_is_swallowed(httpx_mock, caplog):
    """A non-2xx callback response must not propagate as an exception."""
    httpx_mock.add_response(url="http://1.2.3.4/hook", status_code=500)

    await send_callback(
        "http://1.2.3.4/hook",
        "task1",
        TaskStatus.COMPLETED,
        [],
    )
    # Errors are logged, not raised
    assert "failed" in caplog.text.lower() or "error" in caplog.text.lower()
