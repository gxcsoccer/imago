from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

from imago.config import Settings

logger = logging.getLogger(__name__)

# Semaphore to serialize GPU access
_gpu_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _gpu_semaphore
    if _gpu_semaphore is None:
        _gpu_semaphore = asyncio.Semaphore(1)
    return _gpu_semaphore


@dataclass
class GeneratedImage:
    image: object  # mflux GeneratedImage (has .image PIL and .save())
    seed: int
    prompt: str


class ImageGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._flux: object | None = None

    def _load_model(self) -> object:
        if self._flux is not None:
            return self._flux
        logger.info(
            "Loading FLUX model=%s quantize=%s",
            self.settings.model,
            self.settings.quantize,
        )
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux.variants.txt2img.flux import Flux1

        model_config = ModelConfig.from_name(self.settings.model)
        self._flux = Flux1(
            model_config=model_config,
            quantize=self.settings.quantize,
        )
        logger.info("FLUX model loaded")
        return self._flux

    def _generate_sync(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: int | None,
    ) -> GeneratedImage:
        flux = self._load_model()
        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        result = flux.generate_image(
            seed=seed,
            prompt=prompt,
            num_inference_steps=steps,
            height=height,
            width=width,
        )
        return GeneratedImage(image=result, seed=seed, prompt=prompt)

    async def generate(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        seed: int | None = None,
    ) -> GeneratedImage:
        s = self.settings
        w = width or s.width
        h = height or s.height
        st = steps or s.steps

        async with _get_semaphore():
            return await asyncio.to_thread(
                self._generate_sync, prompt, w, h, st, seed
            )
