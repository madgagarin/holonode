# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from asyncio import all_tasks, current_task, gather

from pytest_asyncio import fixture as async_fixture


@async_fixture(autouse=True)
async def cancel_all_tasks():
    yield
    tasks = [task for task in all_tasks() if task is not current_task()]
    for task in tasks:
        task.cancel()
    await gather(*tasks, return_exceptions=True)
