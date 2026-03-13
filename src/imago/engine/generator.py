from __future__ import annotations

import asyncio
import gc
import logging
import random
import time
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
        self._last_used: float = 0.0
        self._idle_task: asyncio.Task | None = None

    @property
    def loaded(self) -> bool:
        return self._flux is not None

    def _load_model(self) -> object:
        if self._flux is not None:
            self._last_used = time.monotonic()
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
        self._last_used = time.monotonic()
        logger.info("FLUX model loaded")
        return self._flux

    def unload_model(self) -> None:
        if self._flux is None:
            return
        logger.info("Unloading FLUX model to free memory")
        self._flux = None
        gc.collect()
        # mlx uses a metal cache that can be cleared
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass
        logger.info("FLUX model unloaded")

    async def start_idle_watcher(self) -> None:
        """Start background task that unloads model after idle timeout."""
        timeout = self.settings.idle_timeout
        if timeout <= 0:
            return
        if self._idle_task is not None:
            return

        async def _watch() -> None:
            while True:
                await asyncio.sleep(30)  # check every 30s
                if self._flux is None or self._last_used <= 0:
                    continue
                idle = time.monotonic() - self._last_used
                if idle < timeout:
                    continue
                # Do NOT unload if a generation is in progress.
                # Try to acquire the GPU semaphore without blocking;
                # if we can't, a task is running.
                sem = _get_semaphore()
                if sem.locked():
                    logger.debug("Idle timeout reached but GPU is busy, skipping unload")
                    continue
                logger.info(
                    "Model idle for %.0fs (threshold %ds), unloading",
                    idle, timeout,
                )
                self.unload_model()

        self._idle_task = asyncio.create_task(_watch())

    def _generate_sync(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: int | None,
        image_path: str | None = None,
        image_strength: float | None = None,
    ) -> GeneratedImage:
        flux = self._load_model()
        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        kwargs: dict[str, object] = dict(
            seed=seed,
            prompt=prompt,
            num_inference_steps=steps,
            height=height,
            width=width,
        )
        if image_path is not None:
            kwargs["image_path"] = image_path
            kwargs["image_strength"] = image_strength if image_strength is not None else 0.4

        result = flux.generate_image(**kwargs)
        self._last_used = time.monotonic()
        return GeneratedImage(image=result, seed=seed, prompt=prompt)

    async def generate(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        steps: int | None = None,
        seed: int | None = None,
        image_path: str | None = None,
        image_strength: float | None = None,
    ) -> GeneratedImage:
        s = self.settings
        w = width or s.width
        h = height or s.height
        st = steps or s.steps

        async with _get_semaphore():
            return await asyncio.to_thread(
                self._generate_sync, prompt, w, h, st, seed, image_path, image_strength
            )
