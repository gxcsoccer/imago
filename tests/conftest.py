from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from imago.config import Settings
from imago.engine.generator import GeneratedImage


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture
def test_settings(tmp_output: Path) -> Settings:
    return Settings(
        output_dir=tmp_output,
        model="schnell",
        steps=2,
        width=256,
        height=256,
        quantize=8,
        anthropic_api_key="test-key",
    )


@pytest.fixture
def mock_image() -> MagicMock:
    img = MagicMock()
    img.save = MagicMock()
    return img


@pytest.fixture
def mock_generator(mock_image: MagicMock) -> AsyncMock:
    gen = AsyncMock()
    gen.generate = AsyncMock(
        return_value=GeneratedImage(image=mock_image, seed=42, prompt="test prompt")
    )
    return gen


@pytest.fixture
def client(test_settings: Settings, mock_generator: AsyncMock) -> TestClient:
    from imago.app import create_app

    app = create_app(test_settings, _generator=mock_generator)
    # Use lifespan context so queue gets initialized
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
