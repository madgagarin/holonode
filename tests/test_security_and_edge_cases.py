# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2025-2026 Dmitry Gagarin aka madgagarin

from asyncio import Event, create_task, sleep, wait_for
from os import symlink, unlink
from os.path import exists, islink
from unittest.mock import AsyncMock, MagicMock, patch

from pytest import mark, raises
from rxon.models import FileMetadata, HardwareDevice, InstalledArtifact, ResourcesUsage, TaskPayload
from rxon.security import sign_payload
from rxon.utils import to_dict

from holonode import s3 as s3_mod
from holonode.config import WorkerConfig
from holonode.s3 import S3Manager
from holonode.task_files import TaskFiles
from holonode.worker import Worker


@mark.asyncio
async def test_task_execution_with_valid_signature(monkeypatch):
    """Positive: Task with valid HMAC signature executes successfully."""
    secret = "orch_secret_12345"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.WORKER_ID = "w-test"
    config.WORKER_TOKEN = "tok"
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = True

    worker = Worker(config=config)
    executed = []

    @worker.skill(name="test_skill")
    async def my_skill(params: dict):
        executed.append(params["val"])
        return {"status": "success", "data": {"res": params["val"] * 2}}

    payload_obj = TaskPayload(
        job_id="job-1",
        task_id="task-1",
        type="test_skill",
        params={"val": 21},
        timestamp=1234567890,
    )
    raw = to_dict(payload_obj)
    raw["sig"] = sign_payload(raw, secret, ignore_fields=["sig", "orchestrator_signature"])
    mock_client = AsyncMock()
    raw["client"] = mock_client

    await worker._process_task(raw)

    assert executed == [21]
    assert mock_client.send_result.called
    result_arg = mock_client.send_result.call_args[0][0]
    assert result_arg.status == "success"
    assert result_arg.data == {"res": 42}


@mark.asyncio
async def test_task_execution_signature_missing_but_not_required(monkeypatch):
    """Positive / Migration: Signature missing when REQUIRE_TASK_SIGNATURE=False logs warning and runs."""
    secret = "orch_secret_12345"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.WORKER_ID = "w-test"
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = False

    worker = Worker(config=config)
    executed = []

    @worker.skill(name="test_skill")
    async def my_skill(params: dict):
        executed.append(True)
        return {"status": "success", "data": {}}

    payload_obj = TaskPayload(
        job_id="job-1",
        task_id="task-1",
        type="test_skill",
        params={},
        timestamp=1234567890,
    )
    raw = to_dict(payload_obj)
    raw["client"] = AsyncMock()
    assert "sig" not in raw

    await worker._process_task(raw)
    assert executed == [True]


@mark.asyncio
async def test_task_execution_missing_signature_rejected(monkeypatch):
    """Negative: Missing signature when REQUIRE_TASK_SIGNATURE=True raises PermissionError."""
    secret = "orch_secret_12345"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.WORKER_ID = "w-test"
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = True

    worker = Worker(config=config)

    @worker.skill(name="test_skill")
    async def my_skill(params: dict):
        return {}

    payload_obj = TaskPayload(job_id="job-1", task_id="task-1", type="test_skill", params={})
    raw = to_dict(payload_obj)
    raw["client"] = AsyncMock()

    with raises(PermissionError, match="missing mandatory orchestrator signature"):
        await worker._process_task(raw)


@mark.asyncio
async def test_task_execution_tampered_signature_rejected(monkeypatch):
    """Negative: Tampered signature or modified payload raises PermissionError."""
    secret = "orch_secret_12345"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = True

    worker = Worker(config=config)

    @worker.skill(name="test_skill")
    async def my_skill(params: dict):
        return {}

    payload_obj = TaskPayload(
        job_id="job-1",
        task_id="task-1",
        type="test_skill",
        params={"amount": 100},
        timestamp=1234567890,
    )
    raw = to_dict(payload_obj)
    raw["sig"] = sign_payload(raw, secret, ignore_fields=["sig", "orchestrator_signature"])
    raw["client"] = AsyncMock()

    raw["params"]["amount"] = 999999

    with raises(PermissionError, match="orchestrator signature mismatch"):
        await worker._process_task(raw)


@mark.asyncio
async def test_task_files_path_traversal_prevention(tmp_path):
    """Negative: Path traversal attempts via path_to and path_to_sync raise PermissionError."""
    task_dir = str(tmp_path / "task_dir")
    files = TaskFiles(task_dir=task_dir)

    safe_path_async = await files.path_to("data.csv")
    assert safe_path_async.startswith(str(tmp_path.resolve()))

    safe_path_sync = files.path_to_sync("data.csv")
    assert safe_path_sync.startswith(str(tmp_path.resolve()))

    traversal_inputs = [
        "../../etc/passwd",
        "../../../secret.env",
        "nested/../../outside.txt",
    ]

    for malicious in traversal_inputs:
        with raises(PermissionError, match="Path traversal attempt detected"):
            await files.path_to(malicious)

        with raises(PermissionError, match="Path traversal attempt detected"):
            files.path_to_sync(malicious)


@mark.asyncio
async def test_s3_atomic_download_failure_cleanup(tmp_path):
    """Negative: Download failure during atomic swap cleans up temporary cache file."""
    cache_dir = str(tmp_path / "cache")
    config = MagicMock()
    config.WORKER_BLOB_CACHE_DIR = cache_dir

    s3_manager = S3Manager(config=config)
    mock_provider = AsyncMock()
    mock_provider.get_metadata = AsyncMock(return_value={"etag": "etag-failing-test", "size": 100})
    mock_provider.download = AsyncMock(side_effect=RuntimeError("S3 network failure"))
    s3_manager._provider = mock_provider

    local_target = str(tmp_path / "target.bin")
    with raises(RuntimeError, match="S3 network failure"):
        await s3_manager._download_file_cached("s3://bucket/fail.bin", local_target)

    assert not exists(local_target)
    cache_file = f"{cache_dir}/etag-failing-test"
    assert not exists(cache_file)


def test_cost_per_skill_config_parsing_edge_cases(monkeypatch):
    """Boundary / Edge: COST_PER_SKILL handles invalid or malformed env values safely."""
    for invalid_val in ["", "[]", "null", "12345", "{invalid json}"]:
        monkeypatch.setenv("COST_PER_SKILL", invalid_val)
        cfg = WorkerConfig()
        assert isinstance(cfg.COST_PER_SKILL, dict)
        assert cfg.COST_PER_SKILL == {}

    monkeypatch.setenv("COST_PER_SKILL", '{"skill_a": 0.5, "skill_b": 0.0}')
    cfg_valid = WorkerConfig()
    assert cfg_valid.COST_PER_SKILL == {"skill_a": 0.5, "skill_b": 0.0}


@mark.asyncio
async def test_round_robin_polling_polls_all_clients_without_sleep():
    """Positive & Performance: ROUND_ROBIN polls multiple clients without sleep until a task is found."""
    config = WorkerConfig()
    config.MULTI_ORCHESTRATOR_MODE = "ROUND_ROBIN"
    worker = Worker(config=config)

    c1 = AsyncMock()
    c2 = AsyncMock()
    c3 = AsyncMock()

    worker._clients = [
        ({"url": "http://1", "weight": 1.0, "current_weight": 0.0}, c1),
        ({"url": "http://2", "weight": 1.0, "current_weight": 0.0}, c2),
        ({"url": "http://3", "weight": 1.0, "current_weight": 0.0}, c3),
    ]
    worker._total_orchestrator_weight = 3.0

    polled = []

    async def fake_poll(client):
        polled.append(client)
        return client is c2

    worker._poll_for_tasks_with_status = fake_poll

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        worker._shutdown_event = Event()
        worker._get_current_state = lambda: {"status": "available"}

        found_task = False
        for _ in range(len(worker._clients)):
            client = worker._get_next_client()
            if client and await worker._poll_for_tasks_with_status(client):
                found_task = True
                break
        if not found_task:
            await mock_sleep(0.5)

        assert found_task is True
        assert polled == [c1, c2]
        assert not mock_sleep.called


@mark.asyncio
async def test_polling_loop_immediate_exit_on_shutdown():
    """Boundary / Lifecycle: Setting _shutdown_event terminates the polling loop immediately."""
    config = WorkerConfig()
    config.MULTI_ORCHESTRATOR_MODE = "ROUND_ROBIN"
    worker = Worker(config=config)
    worker._clients = [({"url": "http://1", "weight": 1.0, "current_weight": 0.0}, AsyncMock())]
    worker._shutdown_event = Event()
    worker._shutdown_event.set()
    worker._registered_event = Event()
    worker._registered_event.set()

    loop_task = create_task(worker._start_polling())
    await wait_for(loop_task, timeout=1.0)
    assert loop_task.done()


@mark.asyncio
async def test_orchestrator_signature_fallback(monkeypatch):
    """Positive & Negative: Fallback to orchestrator_signature when sig is not set on TaskPayload."""
    secret = "orch_secret_fallback_test"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.WORKER_ID = "w-sig-test"
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = True

    worker = Worker(config=config)
    executed = []

    @worker.skill(name="test_skill")
    async def my_skill(params: dict):
        executed.append(params["x"])
        return {"status": "success", "data": {}}

    base_dict = {
        "job_id": "job-fallback-1",
        "task_id": "task-fallback-1",
        "type": "test_skill",
        "params": {"x": 42},
        "timestamp": 1234567890,
    }
    valid_sig = sign_payload(base_dict, secret, ignore_fields=["sig", "orchestrator_signature"])
    payload_raw = dict(base_dict)
    payload_raw["orchestrator_signature"] = valid_sig
    payload_raw["client"] = AsyncMock()

    await worker._process_task(payload_raw)
    assert executed == [42]

    payload_bad = dict(base_dict)
    payload_bad["task_id"] = "task-fallback-2"
    payload_bad["orchestrator_signature"] = "invalid_sig_abc"
    payload_bad["client"] = AsyncMock()

    with raises(PermissionError, match="orchestrator signature mismatch"):
        await worker._process_task(payload_bad)


@mark.asyncio
async def test_polling_task_no_load_leak_on_signature_or_policy_rejection(monkeypatch):
    """Positive, Negative & Boundary: Rejected tasks (signature/policy) must not leak _current_load or freeze worker."""
    secret = "orch_secret_load_test"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", secret)

    config = WorkerConfig()
    config.WORKER_ID = "w-leak-test"
    config.SECRET_KEY = secret
    config.REQUIRE_TASK_SIGNATURE = True

    worker = Worker(config=config)

    @worker.skill(name="skill_leak_test")
    async def my_skill(params: dict):
        return {"status": "success", "data": {}}

    bad_payload = TaskPayload(
        job_id="job-bad",
        task_id="task-bad-1",
        type="skill_leak_test",
        params={},
        timestamp=1234567890,
    )
    mock_client = AsyncMock()
    mock_client.poll_task = AsyncMock(return_value=bad_payload)

    polled = await worker._poll_for_tasks_with_status(mock_client)
    assert polled is True
    await sleep(0.05)

    assert worker._current_load == 0
    assert "task-bad-1" not in worker._active_tasks
    assert len(worker._active_tasks) == 0

    policy_payload = TaskPayload(
        job_id="job-pol",
        task_id="task-pol-1",
        type="skill_leak_test",
        params={},
        policy={"allowed_skills": ["allowed_only_skill"]},
        timestamp=1234567890,
    )
    raw_policy = to_dict(policy_payload)
    sig_policy = sign_payload(raw_policy, secret, ignore_fields=["sig", "orchestrator_signature"])
    policy_payload = TaskPayload(
        job_id="job-pol",
        task_id="task-pol-1",
        type="skill_leak_test",
        params={},
        policy={"allowed_skills": ["allowed_only_skill"]},
        timestamp=1234567890,
        sig=sig_policy,
    )
    mock_client.poll_task = AsyncMock(return_value=policy_payload)

    polled = await worker._poll_for_tasks_with_status(mock_client)
    assert polled is True
    await sleep(0.05)

    assert worker._current_load == 0
    assert "task-pol-1" not in worker._active_tasks
    assert len(worker._active_tasks) == 0

    for i in range(10):
        t_id = f"task-consecutive-bad-{i}"
        mock_client.poll_task = AsyncMock(
            return_value=TaskPayload(
                job_id=f"job-{i}",
                task_id=t_id,
                type="skill_leak_test",
                params={},
                timestamp=1234567890,
            )
        )
        polled = await worker._poll_for_tasks_with_status(mock_client)
        assert polled is True
        await sleep(0.01)

    assert worker._current_load == 0
    assert len(worker._active_tasks) == 0
    state = worker._get_current_state()
    assert state["status"] in ("idle", "available")
    assert state["status"] not in ("busy", "full")

    valid_payload = TaskPayload(
        job_id="job-good",
        task_id="task-good-1",
        type="skill_leak_test",
        params={},
        timestamp=1234567890,
    )
    raw_dict = to_dict(valid_payload)
    sig = sign_payload(raw_dict, secret, ignore_fields=["sig", "orchestrator_signature"])
    valid_payload = TaskPayload(
        job_id="job-good",
        task_id="task-good-1",
        type="skill_leak_test",
        params={},
        timestamp=1234567890,
        sig=sig,
    )
    mock_client.poll_task = AsyncMock(return_value=valid_payload)
    mock_client.send_result = AsyncMock(return_value=True)

    polled = await worker._poll_for_tasks_with_status(mock_client)
    assert polled is True
    await sleep(0.05)

    assert worker._current_load == 0
    assert len(worker._active_tasks) == 0
    assert mock_client.send_result.called


@mark.asyncio
async def test_task_files_absolute_path_inside_task_dir(tmp_path):
    """Positive, Negative & Boundary: TaskFiles path_to/path_to_sync with absolute and relative paths."""
    task_dir = tmp_path / "task_workspace"
    files = TaskFiles(task_dir=str(task_dir))

    rel_async = await files.path_to("sub/data.json")
    rel_sync = files.path_to_sync("sub/data.json")
    expected_rel = str((task_dir / "sub" / "data.json").resolve())
    assert rel_async == expected_rel
    assert rel_sync == expected_rel

    abs_inside = str((task_dir / "sub" / "output.csv").resolve())
    res_async = await files.path_to(abs_inside)
    res_sync = files.path_to_sync(abs_inside)
    assert res_async == abs_inside
    assert res_sync == abs_inside
    assert str(task_dir) not in res_async.replace(str(task_dir), "", 1)

    root_async = await files.path_to(str(task_dir.resolve()))
    root_sync = files.path_to_sync(str(task_dir.resolve()))
    assert root_async == str(task_dir.resolve())
    assert root_sync == str(task_dir.resolve())

    abs_outside = str(tmp_path / "outside_dir" / "secret.env")
    with raises(PermissionError, match="Path traversal attempt detected"):
        await files.path_to(abs_outside)
    with raises(PermissionError, match="Path traversal attempt detected"):
        files.path_to_sync(abs_outside)

    with raises(PermissionError, match="Path traversal attempt detected"):
        await files.path_to("/etc/passwd")
    with raises(PermissionError, match="Path traversal attempt detected"):
        files.path_to_sync("/etc/passwd")


@mark.asyncio
async def test_s3_broken_symlink_recovery_and_edge_cases(tmp_path):
    """Positive & Boundary: S3Manager._download_file_cached safely recovers from broken symlinks."""
    cache_dir = str(tmp_path / "cache")
    config = MagicMock()
    config.WORKER_BLOB_CACHE_DIR = cache_dir

    s3_manager = S3Manager(config=config)
    mock_provider = AsyncMock()
    mock_provider.get_metadata = AsyncMock(return_value={"etag": "etag-symlink-test", "size": 12})

    async def fake_download(uri, target_file):
        with open(target_file, "w") as f:
            f.write("hello s3 file")

    mock_provider.download = AsyncMock(side_effect=fake_download)
    s3_manager._provider = mock_provider

    local_target = str(tmp_path / "broken_link.txt")
    non_existent_target = str(tmp_path / "ghost_file.txt")

    symlink(non_existent_target, local_target)
    assert islink(local_target)
    assert not exists(local_target)

    await s3_manager._download_file_cached("s3://bucket/test.txt", local_target)

    assert exists(local_target)
    with open(local_target) as f:
        assert f.read() == "hello s3 file"

    unlink(local_target)
    symlink(non_existent_target, local_target)
    assert islink(local_target)
    assert not exists(local_target)

    await s3_manager._download_file_cached("s3://bucket/test.txt", local_target)

    assert exists(local_target)
    with open(local_target) as f:
        assert f.read() == "hello s3 file"

    mock_provider.get_metadata = AsyncMock(return_value={"etag": "etag-broken-tmp", "size": 10})
    mock_provider.download = AsyncMock(side_effect=OSError("network drop"))
    fail_target = str(tmp_path / "fail.txt")
    with raises(OSError, match="network drop"):
        await s3_manager._download_file_cached("s3://bucket/fail.txt", fail_target)
    assert not exists(fail_target)


@mark.asyncio
async def test_task_files_download_file_creates_nested_dirs_and_cleans_broken_symlinks(tmp_path):
    """Positive & Boundary: download_file automatically creates missing parent dirs and cleans broken symlinks."""
    task_dir = tmp_path / "task_workspace"
    mock_s3 = MagicMock()
    mock_provider = AsyncMock()

    async def fake_download(uri, target_file):
        with open(target_file, "w") as f:
            f.write("content downloaded from s3")

    mock_provider.download = AsyncMock(side_effect=fake_download)
    mock_s3._provider = mock_provider

    files = TaskFiles(task_dir=str(task_dir), s3_manager=mock_s3)

    nested_file = "deeply/nested/dir/downloaded_data.txt"
    res_path = await files.download_file("s3://bucket/data.txt", nested_file)
    assert exists(res_path)
    with open(res_path) as f:
        assert f.read() == "content downloaded from s3"

    broken_link_file = "broken_symlink_download.txt"
    target_link_path = await files.path_to(broken_link_file)
    symlink(str(task_dir / "ghost_file.txt"), target_link_path)
    assert islink(target_link_path)
    assert not exists(target_link_path)

    res_path2 = await files.download_file("s3://bucket/data.txt", broken_link_file)
    assert exists(res_path2)
    with open(res_path2) as f:
        assert f.read() == "content downloaded from s3"


@mark.asyncio
async def test_s3_uncached_download_handles_broken_symlinks(tmp_path):
    """Positive & Boundary: Uncached download (etag=None) replaces broken symlinks without FileNotFoundError."""
    config = MagicMock()
    s3_manager = S3Manager(config=config)
    mock_provider = AsyncMock()
    mock_provider.get_metadata = AsyncMock(return_value=None)

    async def fake_download(uri, target_file):
        with open(target_file, "w") as f:
            f.write("direct s3 content")

    mock_provider.download = AsyncMock(side_effect=fake_download)
    s3_manager._provider = mock_provider

    local_target = str(tmp_path / "uncached_broken_link.txt")
    symlink(str(tmp_path / "phantom.txt"), local_target)
    assert islink(local_target)
    assert not exists(local_target)

    await s3_manager._download_file_cached("s3://bucket/direct.txt", local_target)
    assert exists(local_target)
    with open(local_target) as f:
        assert f.read() == "direct s3 content"


@mark.asyncio
async def test_polling_task_no_load_leak_on_malformed_metadata():
    """Negative & Boundary: Malformed task payload failing msgspec deserialization does not leak load."""
    config = WorkerConfig()
    config.WORKER_ID = "w-malformed-test"
    worker = Worker(config=config)

    @worker.skill(name="test_skill")
    async def my_skill(params):
        return {}

    mock_client = AsyncMock()
    bad_task = TaskPayload(
        job_id="job-bad-meta",
        task_id="task-bad-meta-1",
        type="test_skill",
        params={},
        params_metadata={"bad_key": 99999},  # type: ignore
        timestamp=1234567890,
    )
    mock_client.poll_task = AsyncMock(return_value=bad_task)

    polled = await worker._poll_for_tasks_with_status(mock_client)
    assert polled is True
    await sleep(0.05)

    assert worker._current_load == 0
    assert "task-bad-meta-1" not in worker._active_tasks
    assert len(worker._active_tasks) == 0


@mark.asyncio
async def test_process_task_missing_client_graceful_handling():
    """Negative: _process_task handles missing client dictionary entry gracefully without crashing."""
    config = WorkerConfig()
    worker = Worker(config=config)
    payload = {"task_id": "t1", "job_id": "j1", "type": "s1"}
    await worker._process_task(payload)


@mark.asyncio
async def test_telemetry_changed_significantly_none_handling():
    """Boundary & Negative: _is_telemetry_changed_significantly handles None values without AttributeError."""
    config = WorkerConfig()
    worker = Worker(config=config)

    worker._last_sent_usage = None
    assert worker._is_telemetry_changed_significantly(None) is False

    usage_obj = ResourcesUsage(cpu_load_percent=10.0, ram_used_gb=1.0)
    assert worker._is_telemetry_changed_significantly(usage_obj) is True

    worker._last_sent_usage = usage_obj
    assert worker._is_telemetry_changed_significantly(None) is True


def test_create_registration_payload_with_typed_objects():
    """Positive & Boundary: Registration payload handles HardwareDevice and InstalledArtifact instances."""
    config = WorkerConfig()
    config.RESOURCES["devices"] = [
        HardwareDevice(type="gpu", model="nvidia-h100", id="0", properties={"memory_gb": 80})
    ]
    config.INSTALLED_ARTIFACTS = [InstalledArtifact(name="model_weights", version="1.0.0")]

    worker = Worker(config=config)
    payload = worker._create_registration_payload()

    assert payload.resources.devices is not None
    assert len(payload.resources.devices) == 1
    assert payload.resources.devices[0].model == "nvidia-h100"
    assert payload.installed_artifacts is not None
    assert len(payload.installed_artifacts) == 1
    assert payload.installed_artifacts[0].name == "model_weights"


def test_worker_config_secret_key_env_precedence(monkeypatch):
    """Positive & Boundary: WorkerConfig.SECRET_KEY respects environment variables."""
    monkeypatch.delenv("ORCHESTRATOR_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    cfg1 = WorkerConfig()
    assert cfg1.SECRET_KEY == ""

    monkeypatch.setenv("SECRET_KEY", "fallback_secret")
    cfg2 = WorkerConfig()
    assert cfg2.SECRET_KEY == "fallback_secret"

    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", "primary_secret")
    cfg3 = WorkerConfig()
    assert cfg3.SECRET_KEY == "primary_secret"


@mark.asyncio
async def test_task_files_exists_path_traversal_and_positive(tmp_path):
    """Positive, Negative & Boundary: TaskFiles.exists verifies existence safely and blocks traversal."""
    task_dir = tmp_path / "task_workspace"
    task_dir.mkdir()
    (task_dir / "valid_file.txt").write_text("content")

    files = TaskFiles(task_dir=str(task_dir))

    assert await files.exists("valid_file.txt") is True
    assert await files.exists("non_existent.txt") is False

    with raises(PermissionError, match="Path traversal attempt detected"):
        await files.exists("../../etc/passwd")

    with raises(PermissionError, match="Path traversal attempt detected"):
        await files.exists("/etc/shadow")


@mark.asyncio
async def test_task_files_upload_dir_validation_and_traversal(tmp_path):
    """Positive, Negative & Boundary: upload_dir validates directory existence, type, and blocks traversal."""
    task_dir = tmp_path / "task_workspace"
    task_dir.mkdir()
    sub_dir = task_dir / "my_models"
    sub_dir.mkdir()
    (sub_dir / "weights.bin").write_bytes(b"12345")
    (sub_dir / "config.json").write_text('{"name": "test"}')

    regular_file = task_dir / "simple_file.txt"
    regular_file.write_text("not a directory")

    mock_s3 = MagicMock()
    mock_s3._config.S3_DEFAULT_BUCKET = "test-bucket"
    mock_s3._config.TASK_FILES_DIR = str(tmp_path)
    mock_provider = AsyncMock()
    mock_provider.upload = AsyncMock(return_value="etag-12345")
    mock_s3._provider = mock_provider
    mock_s3.process_result = S3Manager.process_result.__get__(mock_s3, S3Manager)
    mock_s3._upload_folder = S3Manager._upload_folder.__get__(mock_s3, S3Manager)
    mock_s3._active_ops = 0
    mock_s3._observability = MagicMock()

    files = TaskFiles(task_dir=str(task_dir), job_id="job-dir-test", s3_manager=mock_s3)

    with raises(PermissionError, match="Path traversal attempt detected"):
        await files.upload_dir("../../etc")

    with raises(FileNotFoundError, match="Directory not found"):
        await files.upload_dir("nonexistent_subfolder")

    with raises(NotADirectoryError, match="Path is not a directory"):
        await files.upload_dir("simple_file.txt")

    meta = await files.upload_dir("my_models")
    assert meta.uri == "s3://test-bucket/job-dir-test/my_models/"
    assert meta.size == 5 + len('{"name": "test"}')
    assert mock_provider.upload.call_count == 2


@mark.asyncio
async def test_s3_manager_process_result_directory_support(tmp_path):
    """Positive & Boundary: S3Manager.process_result recursively uploads directories without IsADirectoryError."""
    config = MagicMock()
    config.S3_ENDPOINT_URL = "http://localhost:9000"
    config.S3_DEFAULT_BUCKET = "bucket-dir"
    config.TASK_FILES_DIR = str(tmp_path)

    s3_manager = S3Manager(config=config)
    mock_provider = AsyncMock()
    mock_provider.upload = AsyncMock(return_value="etag-dir-file")
    s3_manager._provider = mock_provider

    folder = tmp_path / "task-100" / "artifacts"
    folder.mkdir(parents=True)
    (folder / "file1.dat").write_bytes(b"data1")
    (folder / "file2.dat").write_bytes(b"data222")

    result = {"output_dir": str(folder)}
    updated_result, meta_map = await s3_manager.process_result(result, s3_prefix="task-100")

    assert updated_result["output_dir"] == "s3://bucket-dir/task-100/artifacts/"
    assert "output_dir" in meta_map
    assert meta_map["output_dir"].uri == "s3://bucket-dir/task-100/artifacts/"
    assert meta_map["output_dir"].size == len(b"data1") + len(b"data222")
    assert mock_provider.upload.call_count == 2


@mark.asyncio
async def test_s3_manager_download_folder_path_traversal_protection(tmp_path):
    """Negative & Boundary: _download_folder rejects S3 keys with path traversal attempts."""
    config = MagicMock()
    config.S3_ENDPOINT_URL = "http://localhost:9000"
    config.S3_DEFAULT_BUCKET = "bucket-traversal"
    config.TASK_FILES_DIR = str(tmp_path)

    s3_manager = s3_mod.S3Manager(config=config)

    mock_store = MagicMock()
    mock_obj = MagicMock()
    mock_obj.path = "job-safe/../../../etc/cron.d/evil"

    class MockCollect:
        async def collect(self):
            return [mock_obj]

    with patch.object(s3_mod, "obstore_list", return_value=MockCollect()):
        mock_provider = AsyncMock()
        mock_provider._get_store = MagicMock(return_value=mock_store)
        s3_manager._provider = mock_provider

        local_dir = str(tmp_path / "safe_local_dir")
        with raises(PermissionError, match="Path traversal attempt in S3 key"):
            await s3_manager._download_folder("s3://bucket-traversal/job-safe/", local_dir)


@mark.asyncio
async def test_process_task_missing_client_cleans_up_active_tasks_and_load():
    """Negative & Boundary: Missing client transport cleans up active task registry and decrements load."""
    config = WorkerConfig()
    worker = Worker(config=config)
    worker._current_load = 1
    dummy_task = MagicMock()
    worker._active_tasks["t-missing-client"] = dummy_task

    raw_payload = {"task_id": "t-missing-client", "job_id": "j1", "type": "some_skill"}
    await worker._process_task(raw_payload)

    assert worker._current_load == 0
    assert "t-missing-client" not in worker._active_tasks


@mark.asyncio
async def test_process_task_finally_guarantees_cleanup_on_cleanup_exception():
    """Boundary: Guaranteed load and active task cleanup even if S3 cleanup or reporting crashes."""
    config = WorkerConfig()
    worker = Worker(config=config)

    @worker.skill(name="safe_skill")
    async def run(params):
        return {"ok": True}

    mock_client = AsyncMock()
    mock_client.send_result = AsyncMock(side_effect=RuntimeError("fatal orchestrator network drop"))

    mock_s3 = MagicMock()
    mock_s3.cleanup = AsyncMock(side_effect=OSError("filesystem unmount during cleanup"))
    mock_s3.process_params = AsyncMock(side_effect=lambda p, *args, **kwargs: p)
    mock_s3.process_result = AsyncMock(side_effect=lambda r, *args, **kwargs: (r, {}))
    worker._s3_manager = mock_s3

    worker._current_load = 1
    dummy_task = MagicMock()
    worker._active_tasks["t-fatal-cleanup"] = dummy_task

    raw_payload = {
        "task_id": "t-fatal-cleanup",
        "job_id": "j-fatal",
        "type": "safe_skill",
        "params": {},
        "client": mock_client,
    }

    await worker._process_task(raw_payload)

    assert worker._current_load == 0
    assert "t-fatal-cleanup" not in worker._active_tasks


@mark.asyncio
async def test_download_file_size_mismatch_cleans_up_corrupted_file(tmp_path):
    """Negative & Boundary: download_file removes partially downloaded file on size mismatch."""
    task_dir = tmp_path / "task_workspace"
    mock_s3 = MagicMock()
    mock_provider = AsyncMock()

    async def fake_download(uri, target_file):
        with open(target_file, "w") as f:
            f.write("partial content")

    mock_provider.download = AsyncMock(side_effect=fake_download)
    mock_s3._provider = mock_provider

    files = TaskFiles(task_dir=str(task_dir), s3_manager=mock_s3)
    verify_meta = FileMetadata(uri="s3://bucket/test.bin", size=99999)

    with raises(ValueError, match="Size mismatch for s3://bucket/test.bin"):
        await files.download_file("s3://bucket/test.bin", "corrupted.bin", verify_meta=verify_meta)

    target_path = await files.path_to("corrupted.bin")
    assert not exists(target_path)
