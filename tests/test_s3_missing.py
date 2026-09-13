# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from importlib import import_module
from sys import modules
from unittest.mock import patch

from pytest import mark, raises

from holonode.config import WorkerConfig


@mark.asyncio
async def test_s3_missing_dependency():
    """
    Tests that S3Manager raises appropriate errors when 'obstore' is not installed.
    """
    if "holonode.s3" in modules:
        del modules["holonode.s3"]

    with patch.dict(modules, {"obstore": None}):
        s3_module = import_module("holonode.s3")

        assert s3_module._HAS_S3 is False

        config = WorkerConfig()
        config.S3_ENDPOINT_URL = "http://localhost:9000"

        manager = s3_module.S3Manager(config)

        with raises(RuntimeError) as excinfo:
            manager._provider._check_availability()
        assert "install 'holonode[s3]'" in str(excinfo.value)

        with raises(RuntimeError):
            await manager.process_params({"file": "s3://bucket/file"}, "task-1")

    if "holonode.s3" in modules:
        del modules["holonode.s3"]


@mark.asyncio
async def test_metrics_missing_dependency():
    """
    Tests that ObservabilityManager enters No-op mode when 'opentelemetry' is not installed.
    """
    if "holonode.observability" in modules:
        del modules["holonode.observability"]

    with patch.dict(
        modules,
        {
            "opentelemetry": None,
            "opentelemetry.metrics": None,
            "opentelemetry.trace": None,
            "opentelemetry.sdk": None,
            "opentelemetry.exporter": None,
            "opentelemetry.exporter.prometheus": None,
            "prometheus_client": None,
        },
    ):
        obs_module = import_module("holonode.observability")

        assert obs_module._HAS_OTEL is False

        manager = obs_module.ObservabilityManager(enabled=True)
        assert manager.enabled is False

        with manager.start_task_span("task", "t1", "j1") as span:
            assert span is None

        manager.record_task_finished("task", "success", 1.0)

    if "holonode.observability" in modules:
        del modules["holonode.observability"]
