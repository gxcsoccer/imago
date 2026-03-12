from imago.prompt.styles import StyleRegistry


def test_style_registry_loads():
    registry = StyleRegistry()
    registry.load_directory()
    styles = registry.list_styles()
    assert len(styles) == 6
    names = {s["name"] for s in styles}
    assert "cinematic" in names
    assert "product" in names
    assert "finance_editorial" in names


def test_style_registry_get():
    registry = StyleRegistry()
    registry.load_directory()
    style = registry.get("cinematic")
    assert style is not None
    assert style.name == "cinematic"
    assert "cinematic" in style.prefix.lower()


def test_style_registry_get_missing():
    registry = StyleRegistry()
    registry.load_directory()
    assert registry.get("nonexistent") is None
