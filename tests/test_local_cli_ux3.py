# Copyright (c) 2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiohttp.test_utils import TestClient, TestServer
from msgspec import Struct
from orjson import dumps as orjson_dumps
from pydantic import BaseModel, Field
from pytest import MonkeyPatch, mark, raises

from holonode.__main__ import main, run_worker
from holonode.hud import WorkerHUD
from holonode.local_runner import (
    LocalMockTaskFiles,
    create_dev_app,
    execute_local_skill,
    inspect_worker_skills,
)
from holonode.observability import ObservabilityManager
from holonode.task_files import TaskFiles
from holonode.worker import OrchestratorClient, Worker


def test_worker_hud_lifecycle() -> None:
    hud = WorkerHUD(worker_id="worker-tui-01", enabled=True)
    assert hud.status == "idle"
    assert hud.completed_count == 0

    hud.task_started("task-01", "image_render")
    assert hud.status == "busy"
    assert "task-01" in hud.active_tasks

    line = hud.render_line()
    assert "worker-tui-01" in line
    assert "BUSY" in line
    assert "Active: " in line

    box = hud.render_box()
    assert "HOLARCHY WORKER HUD" in box
    assert "image_render" in box

    hud.task_finished("task-01", success=True)
    assert hud.status == "idle"
    assert hud.completed_count == 1
    assert hud.failed_count == 0

    hud.task_started("task-02", "audio_proc")
    hud.task_finished("task-02", success=False)
    assert hud.completed_count == 1
    assert hud.failed_count == 1


@mark.asyncio
async def test_local_mock_task_files(tmp_path: Path) -> None:
    task_dir = str(tmp_path / "task-100")
    files = LocalMockTaskFiles(task_dir=task_dir, task_id="task-100")

    file_path = await files.path_to("output.txt")
    assert file_path.startswith(task_dir)

    async with files.open("output.txt", mode="w") as f:
        await f.write("hello local worker")

    async with files.open("output.txt", mode="r") as f:
        content = await f.read()
    assert content == "hello local worker"

    with raises(PermissionError):
        await files.path_to("../../etc/passwd")


@mark.asyncio
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

    res1 = await execute_local_skill(worker, "math_add", params={"a": 3, "b": 7}, local_dir=local_dir)
    assert res1["status"] == "success"
    assert res1["result"] == 10

    res2 = await execute_local_skill(
        worker, "async_file_write", params={"text": "local payload content"}, local_dir=local_dir
    )
    assert res2["status"] == "success"
    assert res2["result"] == "written"
    tid = res2["task_id"]
    log_path = Path(local_dir) / tid / "log.txt"
    assert log_path.exists()
    assert log_path.read_text() == "local payload content"

    res3 = await execute_local_skill(worker, "failing_skill", local_dir=local_dir)
    assert res3["status"] == "failure"
    assert "Intentional local failure" in res3["error"]
    assert "Traceback" in res3["traceback"]

    res4 = await execute_local_skill(worker, "unknown_skill", local_dir=local_dir)
    assert res4["status"] == "failure"
    assert "not registered" in res4["error"]


@mark.asyncio
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


@mark.asyncio
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
        resp_ui = await client.get("/")
        assert resp_ui.status == 200
        html = await resp_ui.text()
        assert "Holonode Dev Testbench" in html

        resp_skills = await client.get("/api/skills")
        assert resp_skills.status == 200
        skills_data = await resp_skills.json()
        assert any(s["name"] == "echo" for s in skills_data)

        resp_echo = await client.get("/api/skills/echo")
        assert resp_echo.status == 200
        echo_schema = await resp_echo.json()
        assert echo_schema["name"] == "echo"
        assert echo_schema["risk"] == "low"

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

        resp_bad = await client.post(
            "/api/exec/echo",
            data=b"invalid json!!",
            headers={"Content-Type": "application/json"},
        )
        assert resp_bad.status == 400
    finally:
        await client.close()
        await server.close()


class GreetingParams(BaseModel):
    name: str = Field(default="World")


class GreetingResult(BaseModel):
    message: str
    tool_status: str


@mark.asyncio
async def test_execute_local_skill_pydantic_and_dependencies(tmp_path: Path) -> None:
    worker = Worker(worker_type="pydantic-local-worker")
    local_dir = str(tmp_path / "pydantic_tasks")

    @worker.skill("greet_and_tool")
    async def greet_and_tool(params: GreetingParams, orchestrator_client: OrchestratorClient) -> GreetingResult:
        tool_res = await orchestrator_client.call_skill("web_search", {"query": "hello"})
        return GreetingResult(
            message=f"Hello, {params.name}!",
            tool_status=tool_res.get("status", "unknown"),
        )

    res = await execute_local_skill(worker, "greet_and_tool", params={"name": "Alice"}, local_dir=local_dir)
    assert res["status"] == "success"
    assert res["result"] == {
        "message": "Hello, Alice!",
        "tool_status": "success",
    }
    serialized = orjson_dumps(res).decode()
    assert "Hello, Alice!" in serialized


@mark.asyncio
async def test_worker_hud_on_task_signature_error() -> None:
    worker = Worker(worker_type="hud-error-worker")
    worker.hud.enabled = True
    worker._config.SECRET_KEY = "super-secret"
    worker._config.REQUIRE_TASK_SIGNATURE = True

    mock_client = AsyncMock()
    task_payload = {
        "task_id": "unauth-task-01",
        "job_id": "job-01",
        "type": "some_skill",
        "client": mock_client,
        "params": {},
    }

    worker.hud.task_started("unauth-task-01", "some_skill")
    assert worker.hud.status == "busy"
    assert "unauth-task-01" in worker.hud.active_tasks

    with raises(PermissionError):
        await worker._process_task(task_payload)

    assert "unauth-task-01" not in worker.hud.active_tasks
    assert worker.hud.status == "idle"
    assert worker.hud.failed_count == 1


def test_cli_run_options(monkeypatch: MonkeyPatch) -> None:
    mock_worker = MagicMock()
    mock_worker._config.WORKER_PORT = 8083
    mock_worker.hud.enabled = False

    monkeypatch.setattr("holonode.__main__._load_worker", lambda app: mock_worker)

    args = Namespace(app="mod:worker", health_check=True, port=None, hud=False)
    run_worker(args)
    assert mock_worker.run_with_health_check.called
    assert mock_worker._config.WORKER_PORT == 8083

    mock_worker.reset_mock()
    args2 = Namespace(app="mod:worker", health_check=False, port=9000, hud=True)
    run_worker(args2)
    assert mock_worker.run.called
    assert not mock_worker.run_with_health_check.called
    assert mock_worker._config.WORKER_PORT == 9000
    assert mock_worker.hud.enabled is True


def test_cli_arg_parsing(monkeypatch: MonkeyPatch) -> None:
    mock_run_worker = MagicMock()
    monkeypatch.setattr("holonode.__main__.run_worker", mock_run_worker)

    monkeypatch.setattr(
        "sys.argv",
        ["worker", "run", "--app", "sample:worker", "--port", "9000", "--no-health-check", "--hud"],
    )
    main()
    assert mock_run_worker.called
    args = mock_run_worker.call_args[0][0]
    assert args.app == "sample:worker"
    assert args.port == 9000
    assert args.health_check is False
    assert args.hud is True


@mark.asyncio
async def test_execute_local_skill_annotations(tmp_path: Path) -> None:
    worker = Worker(worker_type="annot-worker")
    local_dir = str(tmp_path / "annot_tasks")

    @worker.skill("skill_with_deps")
    async def skill_with_deps(
        files: TaskFiles,
        client: OrchestratorClient,
        obs: ObservabilityManager,
    ) -> dict[str, bool]:
        return {
            "has_files": isinstance(files, TaskFiles),
            "has_client": isinstance(client, OrchestratorClient),
            "has_obs": isinstance(obs, ObservabilityManager),
        }

    res = await execute_local_skill(worker, "skill_with_deps", local_dir=local_dir)
    assert res["status"] == "success"
    assert res["result"] == {
        "has_files": True,
        "has_client": True,
        "has_obs": True,
    }


class ItemPayload(Struct):
    title: str
    count: int


class ItemSummary(Struct):
    status: str
    items: list[ItemPayload]


@mark.asyncio
async def test_execute_local_skill_msgspec_struct(tmp_path: Path) -> None:
    worker = Worker(worker_type="struct-worker")
    local_dir = str(tmp_path / "struct_tasks")

    @worker.skill("process_items")
    async def process_items() -> ItemSummary:
        return ItemSummary(
            status="processed",
            items=[ItemPayload(title="A", count=1), ItemPayload(title="B", count=2)],
        )

    res = await execute_local_skill(worker, "process_items", local_dir=local_dir)
    assert res["status"] == "success"
    assert res["result"] == {
        "status": "processed",
        "items": [
            {"title": "A", "count": 1},
            {"title": "B", "count": 2},
        ],
    }
    # Verify that orjson serialization doesn't fail
    encoded = orjson_dumps(res)
    assert b"processed" in encoded
