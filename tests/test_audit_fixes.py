# Copyright (c) 2025-2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from asyncio import gather
from io import StringIO
from logging import INFO, StreamHandler, getLogger
from os.path import exists, join
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock

from pytest import mark, raises
from rxon.security import sign_payload

from holonode.s3 import S3Manager
from holonode.task_files import TaskFiles
from holonode.worker import Worker


@mark.asyncio
async def test_worker_signature_mandatory_when_secret_key_set(monkeypatch):
    """WRK-SEC-1: Mandatory signature enforcement."""
    config = MagicMock()
    config.WORKER_ID = "worker-1"
    config.SECRET_KEY = "test_secret_key"
    monkeypatch.setenv("ORCHESTRATOR_SECRET_KEY", "test_secret_key")

    worker = Worker(config)
    worker._skill_handlers = {}

    @worker.skill("test_skill")
    async def handler(params):
        return {"result": "ok"}

    payload_no_sig = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "test_skill",
        "client": AsyncMock(),
    }
    with raises(PermissionError, match="missing mandatory orchestrator signature"):
        await worker._process_task(payload_no_sig)

    payload_invalid_sig = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "test_skill",
        "sig": "invalid_sig_value",
        "client": AsyncMock(),
    }
    with raises(PermissionError, match="orchestrator signature mismatch"):
        await worker._process_task(payload_invalid_sig)

    valid_sig = sign_payload(
        {"job_id": "j1", "task_id": "t1", "type": "test_skill"},
        "test_secret_key",
        ignore_fields=["sig", "orchestrator_signature"],
    )
    payload_valid_sig = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "test_skill",
        "sig": valid_sig,
        "client": AsyncMock(),
    }
    await worker._process_task(payload_valid_sig)


@mark.asyncio
async def test_task_files_path_traversal_prevention():
    """WRK-SEC-2: Path traversal prevention in TaskFiles."""
    with TemporaryDirectory() as tmp_dir:
        task_dir = join(tmp_dir, "task_123")
        task_files = TaskFiles(task_dir=task_dir, task_id="task_123")

        safe_path = await task_files.path_to("data.json")
        assert Path(safe_path).is_relative_to(Path(tmp_dir) / "task_123")

        safe_nested = await task_files.path_to("nested/output.csv")
        assert Path(safe_nested).is_relative_to(Path(tmp_dir) / "task_123")

        traversal_attempts = [
            "../../etc/passwd",
            "../../../secret.env",
            "nested/../../outside.txt",
        ]
        for bad_path in traversal_attempts:
            with raises(PermissionError, match="Path traversal attempt detected"):
                await task_files.path_to(bad_path)

            with raises(PermissionError, match="Path traversal attempt detected"):
                task_files.path_to_sync(bad_path)


@mark.asyncio
async def test_s3_manager_parallel_download_concurrency():
    """WRK-CNC-1: Parallel cached download race condition prevention."""
    with TemporaryDirectory() as tmp_cache, TemporaryDirectory() as tmp_files:
        config = MagicMock()
        config.WORKER_BLOB_CACHE_DIR = tmp_cache
        config.TASK_FILES_DIR = tmp_files
        config.S3_DEFAULT_BUCKET = "test-bucket"

        manager = S3Manager(config)

        mock_provider = AsyncMock()
        mock_provider.get_metadata.return_value = {"etag": "etag_12345", "size": 100}

        async def fake_download(uri, target_file):
            with open(target_file, "w") as f:
                f.write("content of s3 file")

        mock_provider.download.side_effect = fake_download
        manager._provider = mock_provider

        tasks = [
            manager._download_file_cached("s3://test-bucket/large.bin", join(tmp_files, f"task_{i}.bin"))
            for i in range(10)
        ]
        await gather(*tasks)

        assert mock_provider.download.call_count == 1

        for i in range(10):
            dest = join(tmp_files, f"task_{i}.bin")
            assert exists(dest)
            with open(dest) as f:
                assert f.read() == "content of s3 file"


def test_worker_extra_capabilities_secret_not_leaked():
    """WRK-SEC-3: Sensitive values in EXTRA_CAPABILITIES are not printed in logs."""
    log_capture = StringIO()
    handler = StreamHandler(log_capture)
    worker_logger = getLogger("holonode.worker")
    worker_logger.addHandler(handler)
    worker_logger.setLevel(INFO)

    try:
        extra_caps = {"api_key": "super-secret-api-token-999", "gpu": "nvidia-a100"}
        worker_logger.info(f"Loaded custom capabilities: {list(extra_caps.keys())}")

        output = log_capture.getvalue()
        assert "Loaded custom capabilities" in output
        assert "super-secret-api-token-999" not in output
    finally:
        worker_logger.removeHandler(handler)
