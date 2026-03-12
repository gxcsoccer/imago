from unittest.mock import MagicMock

from imago.engine.generator import GeneratedImage
from imago.output.manager import OutputManager, _slugify


def test_slugify():
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("a cat on Mars") == "a-cat-on-mars"
    assert _slugify("") == ""


def test_output_manager_save(test_settings, mock_image):
    mgr = OutputManager(test_settings)
    result = GeneratedImage(image=mock_image, seed=12345, prompt="a lovely cat")
    img_result = mgr.save(result, intent="a cat")

    assert img_result.seed == 12345
    assert img_result.prompt == "a lovely cat"
    assert "a-cat" in img_result.path
    assert img_result.metadata_path.endswith(".json")
    mock_image.save.assert_called_once()
