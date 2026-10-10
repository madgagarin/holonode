# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from asyncio import create_task, sleep
from os import makedirs, readlink
from os.path import dirname, islink, join
from unittest.mock import AsyncMock, MagicMock, patch

from pytest import mark, raises
from rxon.exceptions import RxonRateLimitError
from rxon.models import ResourcesUsage, TaskResult
from rxon.testing import MockTransport
from rxon.transports.base import Transport
from rxon.transports.http import HttpTransport

from holonode.config import WorkerConfig
from holonode.s3 import S3Manager
from holonode.worker import OrchestratorClient, Worker


@mark.asyncio
async def test_telemetry_throttling():
    """Tests that resources usage is throttled using deadband logic."""
    worker = Worker()
    worker._telemetry_deadband = 5.0
    worker._telemetry_force_interval = 60.0

    usage1 = ResourcesUsage(cpu_load_percent=10.0, ram_used_gb=1.0)
    usage2 = ResourcesUsage(cpu_load_percent=12.0, ram_used_gb=1.02)
    usage3 = ResourcesUsage(cpu_load_percent=20.0, ram_used_gb=1.0)

    with patch.object(worker, "_get_resources_usage", side_effect=[usage1, usage2, usage3]):
        hb1 = worker._create_heartbeat_payload()
        assert hb1.usage == usage1
        assert worker._last_sent_usage == usage1

        hb2 = worker._create_heartbeat_payload()
        assert hb2.usage is None
        assert worker._last_sent_usage == usage1

        hb3 = worker._create_heartbeat_payload()
        assert hb3.usage == usage3
        assert worker._last_sent_usage == usage3


@mark.asyncio
async def test_etag_blob_caching(tmp_path):
    """Tests that S3 downloads are cached locally based on ETag."""
    config = WorkerConfig()
    config.S3_ENDPOINT_URL = "http://mock-s3"
    config.WORKER_BLOB_CACHE_DIR = str(tmp_path / "cache")
    config.TASK_FILES_DIR = str(tmp_path / "payloads")

    s3_manager = S3Manager(config)

    s3_manager._provider.get_metadata = AsyncMock(return_value={"etag": "etag-12345"})

    async def side_effect(uri, local_path):
        makedirs(dirname(local_path), exist_ok=True)
        with open(local_path, "w") as f:
            f.write("cached_data")

    s3_manager._provider.download = AsyncMock(side_effect=side_effect)

    params = {"file": "s3://my-bucket/model.bin"}
    processed1 = await s3_manager.process_params(params, task_id="t1")

    local_path = processed1["file"]
    assert s3_manager._provider.download.call_count == 1
    call_args = s3_manager._provider.download.call_args[0]
    assert call_args[0] == "s3://my-bucket/model.bin"
    assert "etag-12345" in call_args[1]
    assert islink(local_path)
    assert readlink(local_path) == join(config.WORKER_BLOB_CACHE_DIR, "etag-12345")

    s3_manager._provider.download.reset_mock()

    processed2 = await s3_manager.process_params(params, task_id="t2")
    local_path2 = processed2["file"]

    s3_manager._provider.download.assert_not_called()
    assert islink(local_path2)
    assert readlink(local_path2) == join(config.WORKER_BLOB_CACHE_DIR, "etag-12345")


@mark.asyncio
async def test_result_queue_uploader():
    """Tests that task results are uploaded asynchronously via asyncio.Queue."""
    worker = Worker()
    transport = AsyncMock(spec=MockTransport)

    @worker.skill("test-skill")
    async def handler(params):
        return {"data": "test_ok"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "test-skill",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    uploader_task = create_task(worker._result_queue_worker())

    await worker._process_task(task_data)

    assert worker._result_queue.qsize() == 1 or transport.send_result.called

    await sleep(0.1)

    transport.send_result.assert_called_once()
    uploader_task.cancel()


@mark.asyncio
async def test_orchestrator_client_injection():
    """Tests that OrchestratorClient is injected successfully and can be invoked."""
    worker = Worker()

    class DummyHttpTransport(HttpTransport):
        def __init__(self):
            self.base_url = "http://mock-orchestrator"
            self._headers = {}
            self._session = MagicMock()
            self.result_retries = 3
            self.result_retry_delay = 0.1

    transport = DummyHttpTransport()

    injected_client = None

    @worker.skill("ai_agent_skill")
    async def ai_handler(params, orchestrator_client: OrchestratorClient, **kwargs):
        nonlocal injected_client
        injected_client = orchestrator_client
        await orchestrator_client.call_skill("web_search", {"query": "test"})
        return {"status": "ok"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "ai_agent_skill",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    response_mock = MagicMock()
    response_mock.status = 200
    response_mock.json = AsyncMock(return_value={"result": "found"})

    cm_mock = MagicMock()
    cm_mock.__aenter__ = AsyncMock(return_value=response_mock)
    cm_mock.__aexit__ = AsyncMock(return_value=None)
    transport._session.post = MagicMock(return_value=cm_mock)

    await worker._process_task(task_data)

    assert injected_client is not None
    assert isinstance(injected_client, OrchestratorClient)
    transport._session.post.assert_called_once()


@mark.asyncio
async def test_telemetry_throttling_edges():
    """Tests boundary values, force timeout, and zero RAM scenarios in telemetry throttling."""
    worker = Worker()
    worker._telemetry_deadband = 5.0
    worker._telemetry_force_interval = 2.0

    usage_zero = ResourcesUsage(cpu_load_percent=10.0, ram_used_gb=0.0)
    usage_next = ResourcesUsage(cpu_load_percent=10.0, ram_used_gb=1.0)
    with patch.object(worker, "_get_resources_usage", side_effect=[usage_zero, usage_next]):
        hb1 = worker._create_heartbeat_payload()
        assert hb1.usage == usage_zero

        hb2 = worker._create_heartbeat_payload()
        assert hb2.usage == usage_next

    worker = Worker()
    worker._telemetry_deadband = 5.0
    worker._telemetry_force_interval = 0.5

    usage1 = ResourcesUsage(cpu_load_percent=10.0, ram_used_gb=1.0)
    with patch.object(worker, "_get_resources_usage", return_value=usage1):
        hb1 = worker._create_heartbeat_payload()
        assert hb1.usage == usage1

        hb2 = worker._create_heartbeat_payload()
        assert hb2.usage is None

        await sleep(0.6)

        hb3 = worker._create_heartbeat_payload()
        assert hb3.usage == usage1


@mark.asyncio
async def test_etag_blob_caching_edge_cases(tmp_path):
    """Tests missing ETag and pre-existing local file conflicts during blob caching."""
    config = WorkerConfig()
    config.S3_ENDPOINT_URL = "http://mock-s3"
    config.WORKER_BLOB_CACHE_DIR = str(tmp_path / "cache")
    config.TASK_FILES_DIR = str(tmp_path / "payloads")

    s3_manager = S3Manager(config)

    s3_manager._provider.get_metadata = AsyncMock(return_value=None)
    s3_manager._provider.download = AsyncMock()

    params = {"file": "s3://my-bucket/no-etag.bin"}
    processed = await s3_manager.process_params(params, task_id="t_no_etag")
    local_path = processed["file"]

    s3_manager._provider.download.assert_called_once_with("s3://my-bucket/no-etag.bin", local_path)
    assert not islink(local_path)

    s3_manager._provider.get_metadata = AsyncMock(return_value={"etag": "conflict-etag"})

    async def side_effect(uri, local_path):
        makedirs(dirname(local_path), exist_ok=True)
        with open(local_path, "w") as f:
            f.write("data")

    s3_manager._provider.download = AsyncMock(side_effect=side_effect)

    local_root = join(config.TASK_FILES_DIR, "t_conflict")
    makedirs(local_root, exist_ok=True)
    conflict_file = join(local_root, "conflict.bin")
    with open(conflict_file, "w") as f:
        f.write("old_conflict_data")

    params_conflict = {"file": "s3://my-bucket/conflict.bin"}
    processed_conflict = await s3_manager.process_params(params_conflict, task_id="t_conflict")
    local_path_conflict = processed_conflict["file"]

    assert islink(local_path_conflict)
    assert readlink(local_path_conflict) == join(config.WORKER_BLOB_CACHE_DIR, "conflict-etag")


@mark.asyncio
async def test_result_uploader_error_handling():
    """Tests 429 Rate Limit Retry-After and network failures in the result uploader."""
    worker = Worker()
    worker._config.RESULT_MAX_RETRIES = 2
    worker._config.RESULT_RETRY_INITIAL_DELAY = 0.01

    transport = AsyncMock(spec=MockTransport)
    transport.send_result.side_effect = [RxonRateLimitError("Rate limit", details={"retry_after": 0.05}), True]

    result = TaskResult(job_id="j1", task_id="t1", worker_id="w1", status="success", timestamp=123)

    uploader_task = create_task(worker._result_queue_worker())
    await worker._result_queue.put((transport, result))

    await sleep(0.15)

    assert transport.send_result.call_count == 2
    uploader_task.cancel()


@mark.asyncio
async def test_orchestrator_client_error_handling():
    """Tests error response handling and mock fallbacks in OrchestratorClient."""
    mock_transport = AsyncMock(spec=Transport)
    worker = Worker()

    client = OrchestratorClient(mock_transport, worker)
    res = await client.call_skill("some_skill", {"x": 1})
    assert res["status"] == "success"
    assert res["data"]["mocked"] is True

    class DummyHttpTransport(HttpTransport):
        def __init__(self):
            self.base_url = "http://mock-orchestrator"
            self._headers = {}
            self._session = MagicMock()
            self.result_retries = 3
            self.result_retry_delay = 0.1

    transport = DummyHttpTransport()

    response_mock = MagicMock()
    response_mock.status = 500
    response_mock.text = AsyncMock(return_value="Internal Server Error")

    cm_mock = MagicMock()
    cm_mock.__aenter__.return_value = response_mock
    transport._session.post = MagicMock(return_value=cm_mock)

    client = OrchestratorClient(transport, worker)
    with raises(RuntimeError, match="Orchestrator returned HTTP 500: Internal Server Error"):
        await client.call_skill("failing_skill", {})
