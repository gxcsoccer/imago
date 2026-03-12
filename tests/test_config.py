from pathlib import Path

from imago.config import Settings


def test_default_settings():
    s = Settings()
    assert s.port == 8420
    assert s.model == "schnell"
    assert s.steps == 4
    assert s.width == 1024
    assert s.height == 1024


def test_custom_settings():
    s = Settings(port=9000, model="dev", steps=8, output_dir=Path("/tmp/test"))
    assert s.port == 9000
    assert s.model == "dev"
    assert s.output_dir == Path("/tmp/test")
