# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pytest import mark
from rxon import Transport

from holonode.worker import Worker


@dataclass
class SimpleDataclass:
    message: str
    count: int


@dataclass
class DataclassWithValidation:
    name: str
    age: int

    def __post_init__(self):
        if self.age < 18:
            raise ValueError("Must be at least 18")


@dataclass
class DataclassWithDefault:
    name: str
    active: bool = True
    tag: str | None = None


class PydanticModel(BaseModel):
    name: str
    value: float = Field(gt=0)


@mark.asyncio
async def test_process_task_with_default_dict(mocker):
    """Tests that a handler with a standard `dict` annotation receives the raw dict."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()

    received_params = None

    @worker.skill("dict_task")
    async def my_handler(params: dict, **kwargs):
        nonlocal received_params
        received_params = params
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "dict_task",
        "params": {"key": "value"},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    assert received_params == {"key": "value"}


@mark.asyncio
async def test_process_task_with_simple_dataclass_success(mocker):
    """Tests successful instantiation of a simple dataclass."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()
    received_params = None

    @worker.skill("dataclass_task")
    async def my_handler(params: SimpleDataclass, **kwargs):
        nonlocal received_params
        received_params = params
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "dataclass_task",
        "params": {"message": "hello", "count": 10},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    assert isinstance(received_params, SimpleDataclass)
    assert received_params.message == "hello"
    assert received_params.count == 10


@mark.asyncio
async def test_process_task_with_dataclass_validation_failure(mocker):
    """Tests that a validation error in a dataclass's __post_init__ is caught."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()

    @worker.skill("dataclass_validation_task")
    async def my_handler(params: DataclassWithValidation, **kwargs):
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "dataclass_validation_task",
        "params": {"name": "test", "age": 16},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    client.send_result.assert_called_once()
    payload = client.send_result.call_args.args[0]
    assert payload.status == "failure"
    assert payload.error.code == "INVALID_INPUT_ERROR"


@mark.asyncio
async def test_process_task_with_pydantic_success(mocker):
    """Tests successful validation and instantiation of a Pydantic model."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()
    received_params = None

    @worker.skill("pydantic_task")
    async def my_handler(params: PydanticModel, **kwargs):
        nonlocal received_params
        received_params = params
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "pydantic_task",
        "params": {"name": "test", "value": 123.45},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    assert isinstance(received_params, PydanticModel)
    assert received_params.name == "test"
    assert received_params.value == 123.45


@mark.asyncio
async def test_process_task_with_pydantic_validation_failure(mocker):
    """Tests that a Pydantic validation error is caught."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()

    @worker.skill("pydantic_validation_task")
    async def my_handler(params: PydanticModel, **kwargs):
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "pydantic_validation_task",
        "params": {"name": "test", "value": -5},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    client.send_result.assert_called_once()
    payload = client.send_result.call_args.args[0]
    assert payload.status == "failure"
    assert "expected" in payload.error.message.lower() or "validation" in payload.error.message.lower()


@mark.asyncio
async def test_process_task_with_dataclass_defaults(mocker):
    """Tests schema extraction for dataclasses with default and optional values."""
    client = mocker.AsyncMock(spec=Transport)
    worker = Worker()
    received_params = None

    @worker.skill("dataclass_default_task")
    async def my_handler(params: DataclassWithDefault, **kwargs):
        nonlocal received_params
        received_params = params
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "dataclass_default_task",
        "params": {"name": "only_required"},
        "tracing_context": {},
        "client": client,
    }
    await worker._process_task(task_data)

    assert isinstance(received_params, DataclassWithDefault)
    assert received_params.name == "only_required"
    assert received_params.active is True
    assert received_params.tag is None
