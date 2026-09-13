# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from asyncio import create_task, sleep
from unittest.mock import patch

from pytest import mark
from rxon.models import WorkerCommand
from rxon.testing import MockTransport

from holonode.worker import Worker


@mark.asyncio
async def test_skill_no_docstring_and_no_version():
    """Checks that when docstring and version are missing, fields remain None or default."""
    worker = Worker()

    @worker.skill("no_meta_skill")
    async def my_handler(params: dict):
        return {"status": "success"}

    skill_info = worker._skill_handlers["no_meta_skill"]["info"]
    assert skill_info.description is None


@mark.asyncio
async def test_usage_checker_default_returns_object():
    """Checks that a ResourcesUsage object is returned by default."""
    worker = Worker()
    usage = worker._get_resources_usage()
    assert usage is not None
    assert hasattr(usage, "cpu_load_percent")


@mark.asyncio
async def test_command_dispatcher_error_in_handler():
    """Checks that an error in a command handler is logged but doesn't crash the listener."""
    transport = MockTransport()
    transport.connected = True
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])

    @worker.skill("fail_cmd")
    @worker.on_command("fail_cmd")
    async def handle_fail(command: WorkerCommand):
        raise RuntimeError("Handler Failed")

    with patch("holonode.worker.logger.error") as mock_log:
        listener_task = create_task(worker._listen_to_single_transport(transport))
        transport.push_command(WorkerCommand(command="fail_cmd"))

        await sleep(0.1)

        mock_log.assert_called()
        assert "Error handling command 'fail_cmd': Handler Failed" in mock_log.call_args[0][0]
        assert not listener_task.done()
        listener_task.cancel()


@mark.asyncio
async def test_command_dispatcher_unknown_command():
    """Checks logging when an unknown command is received."""
    transport = MockTransport()
    transport.connected = True
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])

    with patch("holonode.worker.logger.warning") as mock_log:
        listener_task = create_task(worker._listen_to_single_transport(transport))
        transport.push_command(WorkerCommand(command="unknown_alien_command"))

        await sleep(0.1)

        mock_log.assert_called()
        assert "Received unknown command: unknown_alien_command" in mock_log.call_args[0][0]
        listener_task.cancel()


@mark.asyncio
async def test_security_signing_with_default_token():
    """Checks that no signature is created if the token is default."""
    worker = Worker()
    worker._config.WORKER_TOKEN = "your-secret-worker-token"

    payload = {"data": "test"}
    security = worker._sign_payload_if_needed(payload)

    assert security is None


@mark.asyncio
async def test_security_signing_passes_raw_payload():
    """Checks that the SDK passes the payload as is to the signing function."""
    worker = Worker()
    worker._config.WORKER_TOKEN = "real-token"

    payload = {"data": "test", "null_field": None}

    with patch("holonode.worker.sign_payload", return_value="sig") as mock_sign:
        worker._sign_payload_if_needed(payload)

        args, _ = mock_sign.call_args
        assert args[0] == payload


@mark.asyncio
async def test_process_task_missing_skill():
    """Checks that an error is returned when a task for an unknown skill is received."""
    transport = MockTransport()
    transport.connected = True
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])

    task_payload = {"job_id": "j1", "task_id": "t1", "type": "non_existent_skill", "params": {}, "client": transport}

    await worker._process_task(task_payload)

    assert len(transport.results) == 1
    result = transport.results[0]
    assert result.status == "failure"
    assert "Unsupported skill" in result.error.message


@mark.asyncio
async def test_event_validation_strict_mode():
    """Checks that undeclared events are blocked in strict mode."""
    transport = MockTransport()
    transport.connected = True
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])
    worker._config.STRICT_EVENT_VALIDATION = True

    @worker.skill("strict_skill", events_schema={"known_event": {"type": "object"}})
    async def handler(send_event, **kwargs):
        await send_event("unknown_event", {"data": 1})
        return {"status": "success"}

    with patch("holonode.worker.logger.error") as mock_log:
        await worker._process_task(
            {"job_id": "j1", "task_id": "t1", "type": "strict_skill", "params": {}, "client": transport}
        )

        mock_log.assert_called()
        expected_msg = "Contract violation: Emitting undeclared event type 'unknown_event'. Blocked."
        assert expected_msg in mock_log.call_args[0][0]
        assert len(transport.emitted_events) == 0
