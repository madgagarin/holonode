# Copyright (c) 2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from orjson import dumps as orjson_dumps

from holonode.hud import WorkerHUD
from holonode.local_runner import (
    LocalMockTaskFiles,
    create_dev_app,
    execute_local_skill,
    inspect_worker_skills,
)
from holonode.worker import Worker


def test_worker_hud_lifecycle() -> None:
    hud = WorkerHUD(worker_id="worker-tui-01", enabled=True)
    assert hud.status == "idle"
    assert hud.completed_count == 0

    # Task started
    hud.task_started("task-01", "image_render")
    assert hud.status == "busy"
    assert "task-01" in hud.active_tasks

    # Render line and box
    line = hud.render_line()
    assert "worker-tui-01" in line
    assert "BUSY" in line
    assert "Active: " in line

    box = hud.render_box()
    assert "HOLARCHY WORKER HUD" in box
    assert "image_render" in box

    # Task finished ok
    hud.task_finished("task-01", success=True)
    assert hud.status == "idle"
    assert hud.completed_count == 1
    assert hud.failed_count == 0

    # Task started and failed
    hud.task_started("task-02", "audio_proc")
    hud.task_finished("task-02", success=False)
    assert hud.completed_count == 1
    assert hud.failed_count == 1


@pytest.mark.asyncio
async def test_local_mock_task_files(tmp_path: Path) -> None:
    task_dir = str(tmp_path / "task-100")
    files = LocalMockTaskFiles(task_dir=task_dir, task_id="task-100")

    # Safe write and read
    file_path = await files.path_to("output.txt")
    assert file_path.startswith(task_dir)

    async with files.open("output.txt", mode="w") as f:
        await f.write("hello local worker")

    async with files.open("output.txt", mode="r") as f:
        content = await f.read()
    assert content == "hello local worker"

    # Path traversal protection
    with pytest.raises(PermissionError):
        await files.path_to("../../etc/passwd")


@pytest.mark.asyncio
async def test_execute_local_skill(tmp_path: Path) -> None:
    worker = Worker(worker_type="test-local-worker")
    local_dir = str(tmp_path / "local_tasks")

    @worker.skill("math_add")
    def math_add(a: int, b: int) -> int:
        return a + b

    @worker.skill("async_file_write")
    async def async_file_write(task_files: LocalMockTaskFiles, text: str) -> str:
        async with task_files.open("log.txt", "w") as f:
            await f.write(text)
        return "written"

    @worker.skill("failing_skill")
    def failing_skill() -> None:
        raise ValueError("Intentional local failure")

    # 1. Sync skill
    res1 = await execute_local_skill(worker, "math_add", params={"a": 3, "b": 7}, local_dir=local_dir)
    assert res1["status"] == "success"
    assert res1["result"] == 10

    # 2. Async skill with mock task files injection
    res2 = await execute_local_skill(
        worker, "async_file_write", params={"text": "local payload content"}, local_dir=local_dir
    )
    assert res2["status"] == "success"
    assert res2["result"] == "written"
    tid = res2["task_id"]
    log_path = Path(local_dir) / tid / "log.txt"
    assert log_path.exists()
    assert log_path.read_text() == "local payload content"

    # 3. Failing skill error capture
    res3 = await execute_local_skill(worker, "failing_skill", local_dir=local_dir)
    assert res3["status"] == "failure"
    assert "Intentional local failure" in res3["error"]
    assert "Traceback" in res3["traceback"]

    # 4. Unregistered skill
    res4 = await execute_local_skill(worker, "unknown_skill", local_dir=local_dir)
    assert res4["status"] == "failure"
    assert "not registered" in res4["error"]


@pytest.mark.asyncio
async def test_inspect_worker_skills() -> None:
    worker = Worker(worker_type="inspect-worker")

    @worker.skill("calc_risk", risk="high", permissions=["admin:calc"])
    def calc_risk(x: int) -> int:
        return x * 2

    skills = inspect_worker_skills(worker)
    assert len(skills) == 1
    assert skills[0]["name"] == "calc_risk"
    assert skills[0]["risk"] == "high"
    assert skills[0]["permissions"] == ["admin:calc"]


@pytest.mark.asyncio
async def test_dev_app_testbench(tmp_path: Path) -> None:
    worker = Worker(worker_type="dev-testbench-worker")
    local_dir = str(tmp_path / "dev_tasks")

    @worker.skill("echo", risk="low")
    def echo_skill(message: str = "hi") -> dict[str, str]:
        return {"echo": message}

    app = create_dev_app(worker=worker, local_dir=local_dir)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # 1. GET / (HTML testbench)
        resp_ui = await client.get("/")
        assert resp_ui.status == 200
        html = await resp_ui.text()
        assert "Holonode Dev Testbench" in html

        # 2. GET /api/skills
        resp_skills = await client.get("/api/skills")
        assert resp_skills.status == 200
        skills_data = await resp_skills.json()
        assert any(s["name"] == "echo" for s in skills_data)

        # 3. GET /api/skills/echo
        resp_echo = await client.get("/api/skills/echo")
        assert resp_echo.status == 200
        echo_schema = await resp_echo.json()
        assert echo_schema["name"] == "echo"
        assert echo_schema["risk"] == "low"

        # 4. POST /api/exec/echo
        exec_payload = {"message": "hello testbench"}
        resp_exec = await client.post(
            "/api/exec/echo",
            data=orjson_dumps(exec_payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp_exec.status == 200
        exec_res = await resp_exec.json()
        assert exec_res["status"] == "success"
        assert exec_res["result"] == {"echo": "hello testbench"}

        # 5. POST /api/exec/echo with invalid JSON
        resp_bad = await client.post(
            "/api/exec/echo",
            data=b"invalid json!!",
            headers={"Content-Type": "application/json"},
        )
        assert resp_bad.status == 400
    finally:
        await client.close()
        await server.close()
