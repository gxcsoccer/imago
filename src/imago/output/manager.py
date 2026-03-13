from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from imago.config import Settings
from imago.engine.generator import GeneratedImage
from imago.models import ImageResult

logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]


class OutputManager:
    def __init__(self, settings: Settings) -> None:
        self.output_dir = settings.output_dir.resolve()

    def save(
        self,
        result: GeneratedImage,
        intent: str,
        image_url: str | None = None,
        image_strength: float | None = None,
    ) -> ImageResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        subject = _slugify(intent)
        basename = f"{date_str}-{subject}-{result.seed}"
        img_path = self.output_dir / f"{basename}.png"
        meta_path = self.output_dir / f"{basename}.json"

        # Save image
        result.image.save(path=str(img_path))
        logger.info("Saved image: %s", img_path)

        # Save sidecar metadata
        metadata: dict[str, object] = {
            "prompt": result.prompt,
            "intent": intent,
            "seed": result.seed,
            "path": str(img_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if image_url is not None:
            metadata["image_url"] = image_url
            metadata["image_strength"] = image_strength
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        return ImageResult(
            path=str(img_path),
            seed=result.seed,
            prompt=result.prompt,
            metadata_path=str(meta_path),
        )
