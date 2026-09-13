# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from unittest.mock import MagicMock, patch

from pytest import mark

from holonode import observability
from holonode.observability import ObservabilityManager


def test_observability_manager_no_op():
    """Tests that ObservabilityManager works even if OTel is not installed."""
    with patch("holonode.observability._HAS_OTEL", False):
        manager = ObservabilityManager(enabled=True)
        assert manager.enabled is False

        with manager.start_task_span("test", "t1", "j1") as span:
            assert span is None

        manager.record_task_finished("test", "success", 1.0)
        manager.record_s3_op("upload", "success")


@mark.asyncio
async def test_observability_integration_logic():
    """Tests basic functionality of ObservabilityManager logic."""
    with patch("holonode.observability._HAS_OTEL", True):
        manager = ObservabilityManager(enabled=False)

        manager.enabled = True
        manager.tracer = MagicMock()
        manager.meter = MagicMock()
        manager.tasks_total = MagicMock()
        manager.tasks_duration = MagicMock()
        manager.s3_ops_total = MagicMock()

        with manager.start_task_span("test-task", "t1", "j1"):
            pass

        manager.tracer.start_as_current_span.assert_called_once()

        manager.record_task_finished("test-task", "success", 0.5)
        manager.tasks_total.add.assert_called()
        manager.tasks_duration.record.assert_called()


@mark.asyncio
async def test_observability_shutdown(mocker):
    """Tests that shutdown flushes and closes providers."""
    with patch("holonode.observability._HAS_OTEL", True):
        manager = ObservabilityManager(enabled=True)
        manager._tracer_provider = mocker.Mock()
        manager._meter_provider = mocker.Mock()

        await manager.shutdown()

        manager._tracer_provider.shutdown.assert_called_once()
        manager._meter_provider.shutdown.assert_called_once()


def test_observability_manager_otlp_vs_console_config(mocker):
    """Tests that the manager chooses OTLP or Console based on env vars."""
    with patch("holonode.observability._HAS_OTEL", True):
        mocker.patch("holonode.observability.metrics", create=True)
        mocker.patch("holonode.observability.trace", create=True)
        mocker.patch("holonode.observability.Resource", create=True)
        mocker.patch("holonode.observability.ResourceAttributes", create=True)
        mocker.patch("holonode.observability.OTLPMetricExporter", create=True)
        mocker.patch("holonode.observability.ConsoleMetricExporter", create=True)
        mocker.patch("holonode.observability.PeriodicExportingMetricReader", create=True)
        mocker.patch("holonode.observability.MeterProvider", create=True)

        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4317"}):
            manager = ObservabilityManager(enabled=True)
            assert manager.enabled is True
            assert observability.OTLPMetricExporter.called

        with patch.dict("os.environ", {}, clear=True):
            manager = ObservabilityManager(enabled=True)
            assert observability.ConsoleMetricExporter.called


def test_observability_disabled_mode_safety():
    """Tests that record methods don't crash when disabled."""
    with patch("holonode.observability._HAS_OTEL", True):
        manager = ObservabilityManager(enabled=False)
        assert manager.enabled is False
        assert manager.meter is None

        manager.record_task_finished("task", "ok", 1.0)
        manager.record_s3_op("op", "ok")
