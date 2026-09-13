# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from unittest.mock import AsyncMock, patch

from pytest import fixture, mark
from rxon.testing import MockTransport

from holonode.worker import Worker


@fixture
def worker():
    return Worker()


@mark.asyncio
async def test_correct_event_emission(worker):
    """Tests that a correctly formatted event is successfully emitted and contains a timestamp."""
    transport = MockTransport()

    @worker.skill(events_schema={"status_update": {"type": "object", "properties": {"status": {"type": "string"}}}})
    async def my_task(params, send_event, **kwargs):
        await send_event("status_update", {"status": "processing"})
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "my_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 1
    event = transport.emitted_events[0]
    assert event.event_type == "status_update"
    assert event.payload == {"status": "processing"}
    assert event.timestamp is not None


@mark.asyncio
async def test_send_event_no_otel_safety(mocker):
    """
    Tests that emitting an event works safely even if 'opentelemetry' is not installed.
    Verifies that the original trace_context is preserved.
    """
    transport = MockTransport()
    worker = Worker()

    mocker.patch("holonode.worker.propagate", None, create=True)

    @worker.skill("no_otel_task")
    async def no_otel_task(params, send_event, **kwargs):
        await send_event("test_event", {"val": 42})
        return "ok"

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "no_otel_task",
        "params": {},
        "tracing_context": {"traceparent": "original-trace-id"},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 1
    event = transport.emitted_events[0]
    assert event.event_type == "test_event"
    assert event.trace_context == {"traceparent": "original-trace-id"}
    assert event.timestamp is not None


@mark.asyncio
async def test_incorrect_event_emission_blocked(worker, caplog):
    """Tests that an incorrectly formatted event is blocked and an error is logged."""
    transport = MockTransport()

    @worker.skill(events_schema={"status_update": {"type": "object", "properties": {"status": {"type": "string"}}}})
    async def my_task(params, send_event, **kwargs):
        await send_event("status_update", {"status": 123})
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "my_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 0
    assert "Local contract violation for event 'status_update'" in caplog.text


@mark.asyncio
async def test_undeclared_event_blocked_in_strict_mode(worker, caplog):
    """Tests that undeclared events are blocked if STRICT_EVENT_VALIDATION is True."""
    transport = MockTransport()
    worker._config.STRICT_EVENT_VALIDATION = True

    @worker.skill(events_schema={"status_update": {}})
    async def my_task(params, send_event, **kwargs):
        await send_event("undeclared_event", {"some": "data"})
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "my_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 0
    assert "Contract violation: Emitting undeclared event type 'undeclared_event'. Blocked." in caplog.text


@mark.asyncio
async def test_undeclared_event_allowed_in_non_strict_mode(worker, caplog):
    """Tests that undeclared events are allowed if STRICT_EVENT_VALIDATION is False."""
    transport = MockTransport()
    worker._config.STRICT_EVENT_VALIDATION = False

    @worker.skill(events_schema={"status_update": {}})
    async def my_task(params, send_event, **kwargs):
        await send_event("undeclared_event", {"some": "data"})
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "my_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 1
    assert transport.emitted_events[0].event_type == "undeclared_event"
    assert "Emitting undeclared event type 'undeclared_event'. Allowed by config." in caplog.text


@mark.asyncio
async def test_progress_event_always_allowed(worker, caplog):
    """Tests that 'progress' events are always allowed regardless of schema."""
    transport = MockTransport()
    worker._config.STRICT_EVENT_VALIDATION = True

    @worker.skill(events_schema={})
    async def my_task(params, send_event, **kwargs):
        await send_event("progress", {"progress": 0.5})
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "my_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    with (
        patch.object(worker._s3_manager, "process_params", new_callable=AsyncMock, return_value={}),
        patch.object(worker._s3_manager, "process_result", new_callable=AsyncMock, return_value=({}, {})),
    ):
        await worker._process_task(task_data)

    assert len(transport.emitted_events) == 1
    assert transport.emitted_events[0].event_type == "progress"
