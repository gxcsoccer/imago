from __future__ import annotations

import asyncio
import itertools
import logging

from imago.engine.generator import ImageGenerator
from imago.engine.queue import TaskQueue
from imago.models import GenerateRequest, ImageResult, TaskStatus
from imago.output.manager import OutputManager
from imago.output.webhook import send_callback
from imago.prompt.factory import PromptFactory

logger = logging.getLogger(__name__)


def _expand_variables(req: GenerateRequest) -> list[GenerateRequest]:
    if not req.variables:
        return [req]
    keys = list(req.variables.keys())
    values = [req.variables[k] for k in keys]
    expanded = []
    for combo in itertools.product(*values):
        mapping = dict(zip(keys, combo))
        intent = req.intent
        for k, v in mapping.items():
            intent = intent.replace(f"{{{k}}}", v)
        child = req.model_copy(update={"intent": intent, "variables": None})
        expanded.append(child)
    return expanded


async def run_worker(
    queue: TaskQueue,
    generator: ImageGenerator,
    output_mgr: OutputManager,
    prompt_factory: PromptFactory,
    poll_interval: float = 1.0,
) -> None:
    logger.info("Background worker started")
    while True:
        claimed = await queue.claim_next()
        if not claimed:
            await asyncio.sleep(poll_interval)
            continue

        task_id, req = claimed
        logger.info("Worker processing task %s", task_id)
        try:
            sub_requests = _expand_variables(req)
            results: list[ImageResult] = []

            # Count total images to generate
            total = sum(sr.count for sr in sub_requests)

            for sub_req in sub_requests:
                if sub_req.raw_prompt:
                    prompt = sub_req.intent
                else:
                    prompt = await prompt_factory.expand(sub_req.intent, sub_req.style)

                for _ in range(sub_req.count):
                    gen_result = await generator.generate(
                        prompt=prompt,
                        width=sub_req.width,
                        height=sub_req.height,
                        steps=sub_req.steps,
                        seed=sub_req.seed,
                    )
                    img_result = output_mgr.save(gen_result, sub_req.intent)
                    results.append(img_result)
                    await queue.update_progress(task_id, len(results), total, results)

            await queue.complete(task_id, results)

            if req.callback_url:
                await send_callback(
                    req.callback_url, task_id, TaskStatus.COMPLETED, results
                )
        except Exception as e:
            logger.exception("Task %s failed: %s", task_id, e)
            await queue.fail(task_id, str(e))

            if req.callback_url:
                await send_callback(
                    req.callback_url, task_id, TaskStatus.FAILED, [], error=str(e)
                )
