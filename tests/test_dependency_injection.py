# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from os.path import join

from pytest import mark
from rxon import Transport

from holonode import Worker
from holonode.task_files import TaskFiles


@mark.asyncio
async def test_task_files_injection(mocker):
    """Tests that TaskFiles object is correctly injected into the handler."""
    client = mocker.AsyncMock(spec=Transport)

    worker = Worker()
    worker._s3_manager.process_params = mocker.AsyncMock(return_value={})
    worker._s3_manager.process_result = mocker.AsyncMock(return_value={})
    worker._s3_manager.cleanup = mocker.AsyncMock()

    injected_task_files = None

    @worker.skill("di_task")
    async def handler(params: dict, tf: TaskFiles, **kwargs):
        nonlocal injected_task_files
        injected_task_files = tf
        await tf.path_to("test.txt")
        return {"status": "success"}

    task_data = {
        "job_id": "j1",
        "task_id": "t1",
        "type": "di_task",
        "params": {},
        "tracing_context": {},
        "client": client,
    }

    await worker._process_task(task_data)

    assert isinstance(injected_task_files, TaskFiles)
    expected_root = join(worker._config.TASK_FILES_DIR, "t1")
    assert injected_task_files._task_dir == expected_root
    worker._s3_manager.cleanup.assert_awaited_once_with("t1")


@mark.asyncio
async def test_task_files_read_write(tmp_path):
    """Tests high-level read/write methods of TaskFiles."""
    target_dir = tmp_path / "task_dir"
    tf = TaskFiles(str(target_dir), job_id="job1", task_id="task1")

    filename = "hello.txt"
    content = "Hello, World!"

    await tf.write(filename, content)
    assert (target_dir / filename).exists()

    read_content = await tf.read(filename)
    assert read_content == content


@mark.asyncio
async def test_task_files_list_exists(tmp_path):
    """Tests list() and exists() methods."""
    target_dir = tmp_path / "task_dir"
    tf = TaskFiles(str(target_dir), job_id="job1", task_id="task1")

    await tf.write("file1.txt", "data1")
    await tf.write("file2.txt", "data2")

    files = await tf.list()
    assert sorted(files) == ["file1.txt", "file2.txt"]

    assert await tf.exists("file1.txt")
    assert not await tf.exists("missing.txt")


@mark.asyncio
async def test_task_files_open_context(tmp_path):
    """Tests the async with files.open(...) context manager."""
    target_dir = tmp_path / "task_dir"
    tf = TaskFiles(str(target_dir), job_id="job1", task_id="task1")

    async with tf.open("stream.txt", mode="w") as f:
        await f.write("line1\n")
        await f.write("line2\n")

    content = await tf.read("stream.txt")
    assert content == "line1\nline2\n"


@mark.asyncio
async def test_task_files_nested_creation(tmp_path):
    """Tests that nested directories are created automatically."""
    target_dir = tmp_path / "task_dir"
    tf = TaskFiles(str(target_dir), job_id="job1", task_id="task1")

    nested_path = "sub/dir/test.txt"
    await tf.write(nested_path, "nested")

    assert (target_dir / "sub" / "dir" / "test.txt").exists()
    assert await tf.read(nested_path) == "nested"


@mark.asyncio
async def test_task_files_path_to(tmp_path):
    """Tests path_to method."""
    target_dir = tmp_path / "task_dir"
    tf = TaskFiles(str(target_dir), job_id="job1", task_id="task1")

    file_path = await tf.path_to("output.txt")

    assert target_dir.exists()
    assert file_path == join(str(target_dir), "output.txt")
