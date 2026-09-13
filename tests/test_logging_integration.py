# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from io import StringIO
from logging import INFO, Formatter, LogRecord, StreamHandler, getLogger

from orjson import loads as orjson_loads
from pytest import mark
from pythonjsonlogger.json import JsonFormatter
from rxon.testing import MockTransport

from holonode.logging import _context_filter, clear_context, set_context, setup_logging
from holonode.worker import Worker


def test_setup_logging_text(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    setup_logging(worker_id="test-worker")

    root_logger = getLogger()
    handler = root_logger.handlers[0]
    assert isinstance(handler.formatter, Formatter)


def test_context_filter():
    _context_filter.context = {}
    set_context(test_key="test_value")

    record = LogRecord("name", INFO, "pathname", 10, "message", None, None)
    _context_filter.filter(record)

    assert record.test_key == "test_value"

    clear_context("test_key")
    record2 = LogRecord("name", INFO, "pathname", 10, "message", None, None)
    _context_filter.filter(record2)
    assert not hasattr(record2, "test_key")


@mark.asyncio
async def test_worker_logging_context(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")

    root_logger = getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    transport = MockTransport(worker_id="worker-1")

    worker = Worker(worker_type="test", clients=[({"url": "http://test", "weight": 1}, transport)])

    log_capture = StringIO()
    handler = StreamHandler(log_capture)
    formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(worker_id)s %(task_id)s %(job_id)s")
    handler.setFormatter(formatter)
    handler.addFilter(_context_filter)
    root_logger.addHandler(handler)

    @worker.skill("test_task")
    async def task_handler(params, **kwargs):
        getLogger("test").info("Inside task")
        return {"status": "success"}

    task_data = {
        "job_id": "job-123",
        "task_id": "task-456",
        "type": "test_task",
        "params": {},
        "tracing_context": {},
        "client": transport,
    }

    await worker._process_task(task_data)

    log_output = log_capture.getvalue().splitlines()
    task_log = next(line for line in log_output if "Inside task" in line)
    log_data = orjson_loads(task_log)

    assert log_data["task_id"] == "task-456"
    assert log_data["job_id"] == "job-123"
    assert log_data["message"] == "Inside task"
