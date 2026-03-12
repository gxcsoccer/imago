from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class StyleTemplate:
    name: str
    description: str
    prefix: str
    suffix: str
    example_expansions: list[dict[str, str]] = field(default_factory=list)


class StyleRegistry:
    def __init__(self) -> None:
        self._styles: dict[str, StyleTemplate] = {}

    def load_directory(self, path: Path | None = None) -> None:
        d = path or TEMPLATES_DIR
        for f in sorted(d.glob("*.yaml")):
            data = yaml.safe_load(f.read_text())
            style = StyleTemplate(
                name=data["name"],
                description=data["description"],
                prefix=data["prefix"],
                suffix=data["suffix"],
                example_expansions=data.get("example_expansions", []),
            )
            self._styles[style.name] = style
            logger.debug("Loaded style: %s", style.name)
        logger.info("Loaded %d style templates", len(self._styles))

    def get(self, name: str) -> StyleTemplate | None:
        return self._styles.get(name)

    def list_styles(self) -> list[dict[str, str]]:
        return [
            {"name": s.name, "description": s.description}
            for s in self._styles.values()
        ]
