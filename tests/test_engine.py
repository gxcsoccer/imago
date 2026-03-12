from imago.engine.generator import ImageGenerator


def test_generator_init(test_settings):
    gen = ImageGenerator(test_settings)
    assert gen._flux is None
    assert gen.settings == test_settings
