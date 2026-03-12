import time


def test_generate_returns_task_id(client):
    resp = client.post(
        "/generate",
        json={"intent": "a beautiful cat", "raw_prompt": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert len(data["task_id"]) == 12


def test_get_task(client, mock_generator):
    # Submit a task
    resp = client.post(
        "/generate",
        json={"intent": "a dog", "raw_prompt": True},
    )
    task_id = resp.json()["task_id"]

    # Give the worker a moment to process
    time.sleep(0.5)

    # Check task status
    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["status"] in ("pending", "running", "completed")


def test_get_task_not_found(client):
    resp = client.get("/tasks/nonexistent")
    assert resp.status_code == 404


def test_list_styles(client):
    resp = client.get("/styles")
    assert resp.status_code == 200
    styles = resp.json()
    assert len(styles) == 6
    names = {s["name"] for s in styles}
    assert "cinematic" in names
