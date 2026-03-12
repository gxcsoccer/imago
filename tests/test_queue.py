import pytest

from imago.engine.queue import TaskQueue
from imago.models import GenerateRequest, ImageResult


@pytest.fixture
async def queue(tmp_path):
    q = TaskQueue(db_path=str(tmp_path / "test.db"))
    await q.init()
    yield q
    await q.close()


async def test_submit_and_get(queue):
    req = GenerateRequest(intent="a cat", raw_prompt=True)
    task_id = await queue.submit(req)
    assert len(task_id) == 12

    task = await queue.get(task_id)
    assert task.status.value == "pending"
    assert task.request.intent == "a cat"


async def test_claim_and_complete(queue):
    req = GenerateRequest(intent="a dog", raw_prompt=True)
    task_id = await queue.submit(req)

    claimed = await queue.claim_next()
    assert claimed is not None
    assert claimed[0] == task_id

    task = await queue.get(task_id)
    assert task.status.value == "running"

    images = [ImageResult(path="/tmp/test.png", seed=42, prompt="a dog", metadata_path="/tmp/test.json")]
    await queue.complete(task_id, images)

    task = await queue.get(task_id)
    assert task.status.value == "completed"
    assert len(task.images) == 1


async def test_claim_empty(queue):
    assert await queue.claim_next() is None


async def test_fail_with_retry(queue):
    req = GenerateRequest(intent="fail test", raw_prompt=True)
    task_id = await queue.submit(req)
    await queue.claim_next()

    retried = await queue.fail(task_id, "boom")
    assert retried is True

    task = await queue.get(task_id)
    assert task.status.value == "pending"


async def test_fail_permanently(queue):
    req = GenerateRequest(intent="fail forever", raw_prompt=True)
    task_id = await queue.submit(req)

    # Exhaust retries
    for _ in range(3):
        await queue.claim_next()
        retried = await queue.fail(task_id, "boom")

    task = await queue.get(task_id)
    assert task.status.value == "failed"
    assert task.error == "boom"
