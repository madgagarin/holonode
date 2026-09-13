# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from asyncio import CancelledError, create_task, sleep, wait_for
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

from pytest import mark
from rxon.models import TaskPayload
from rxon.testing import MockTransport

from holonode.worker import Worker


@mark.asyncio
async def test_graceful_shutdown_drains_tasks(mocker):
    transport = MockTransport(worker_id="test-worker")
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])
    worker._config.SHUTDOWN_TIMEOUT = 1.0

    task_completed = False

    @worker.skill("long_task")
    async def long_handler(params, **kwargs):
        nonlocal task_completed
        await sleep(0.5)
        task_completed = True
        return {"status": "success"}

    transport.push_task(TaskPayload(job_id="j1", task_id="t1", type="long_task", params={}, tracing_context={}))

    worker_task = create_task(worker.main())

    while worker._current_load == 0:
        await sleep(0.01)

    assert "t1" in worker._active_tasks

    worker._shutdown_event.set()

    await wait_for(worker_task, timeout=2.0)

    assert task_completed is True
    assert len(transport.results) == 1
    assert transport.results[0].status == "success"


@mark.asyncio
async def test_shutdown_timeout(mocker):
    transport = MockTransport(worker_id="test-worker")
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])
    worker._config.SHUTDOWN_TIMEOUT = 0.2

    task_interrupted = False

    @worker.skill("infinite_task")
    async def infinite_handler(params, **kwargs):
        nonlocal task_interrupted
        try:
            await sleep(10)
        except CancelledError:
            task_interrupted = True
            raise

    transport.push_task(TaskPayload(job_id="j1", task_id="t1", type="infinite_task", params={}, tracing_context={}))

    worker_task = create_task(worker.main())

    while worker._current_load == 0:
        await sleep(0.01)

    worker._shutdown_event.set()

    await wait_for(worker_task, timeout=1.0)

    assert task_interrupted is True


@mark.asyncio
async def test_shutdown_cleanup_on_cancellation(mocker):
    """
    Verifies that the finally block in worker.main() runs even if the task is cancelled.
    """
    transport = MockTransport(worker_id="test-worker")
    transport.send_heartbeat = AsyncMock(return_value={})
    transport.close = AsyncMock()

    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])
    worker._observability = MagicMock()
    worker._observability.shutdown = AsyncMock()

    worker_task = create_task(worker.main())

    await sleep(0.1)

    worker_task.cancel()

    with suppress(CancelledError):
        await worker_task

    offline_calls = [call for call in transport.send_heartbeat.call_args_list if call.args[0].status == "offline"]
    assert len(offline_calls) >= 1

    transport.close.assert_called()
    worker._observability.shutdown.assert_called_once()
