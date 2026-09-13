# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from pytest import mark

from holonode.worker import Worker


@mark.asyncio
async def test_heartbeat_cooldown(mocker):
    transport = mocker.AsyncMock()
    worker = Worker(clients=[({"url": "http://test", "weight": 1}, transport)])
    worker._heartbeat_cooldown = 1.0

    await worker._send_single_heartbeat(transport)
    assert transport.send_heartbeat.call_count == 1

    await worker._send_single_heartbeat(transport)
    assert transport.send_heartbeat.call_count == 1

    worker._last_heartbeat_times[transport] -= 2.0
    await worker._send_single_heartbeat(transport)
    assert transport.send_heartbeat.call_count == 2
