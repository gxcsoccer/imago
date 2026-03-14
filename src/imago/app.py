import asyncio
import logging

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from imago.config import Settings, settings
from imago.engine.generator import ImageGenerator
from imago.engine.queue import TaskQueue
from imago.engine.worker import run_worker
from imago.output.manager import OutputManager
from imago.prompt.factory import PromptFactory
from imago.prompt.styles import StyleRegistry
from imago.routes import generate, tasks


def create_app(
    app_settings: Settings | None = None,
    _generator: ImageGenerator | None = None,
) -> FastAPI:
    s = app_settings or settings

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Style registry
    style_registry = StyleRegistry()
    style_registry.load_directory()

    # Core components
    generator = _generator or ImageGenerator(s)
    output_mgr = OutputManager(s)
    prompt_factory = PromptFactory(s, style_registry)
    queue = TaskQueue()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await queue.init()
        worker_task = asyncio.create_task(
            run_worker(queue, generator, output_mgr, prompt_factory)
        )
        if isinstance(generator, ImageGenerator):
            await generator.start_idle_watcher()
        yield
        worker_task.cancel()
        await queue.close()

    app = FastAPI(title="Imago", version="0.1.0", lifespan=lifespan)

    app.state.generator = generator
    app.state.output_mgr = output_mgr
    app.state.style_registry = style_registry
    app.state.prompt_factory = prompt_factory
    app.state.queue = queue

    # Routes
    app.include_router(generate.router)
    app.include_router(tasks.router)

    return app


def main() -> None:
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
