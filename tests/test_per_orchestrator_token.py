# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from pytest import mark
from rxon.testing import MockTransport

from holonode.config import WorkerConfig
from holonode.worker import Worker


@mark.asyncio
async def test_per_orchestrator_token_usage(mocker):
    """
    Tests that the worker uses the correct token for each orchestrator
    by checking the transport configuration.
    """
    mock_config = WorkerConfig()
    mock_config.ORCHESTRATORS = [
        {"url": "http://orch1.com", "token": "token-for-orch1", "weight": 1},
        {"url": "http://orch2.com", "weight": 1},
    ]
    mock_config.WORKER_TOKEN = "global-fallback-token"

    def mock_create_transport(url, token, **kwargs):
        client = MockTransport(token=token)
        client.url = url  # type: ignore
        return client

    mocker.patch("holonode.worker.create_transport", side_effect=mock_create_transport)

    worker = Worker(config=mock_config)
    worker._init_clients()

    assert len(worker._clients) == 2

    client1 = next(c for o, c in worker._clients if o["url"] == "http://orch1.com")
    client2 = next(c for o, c in worker._clients if o["url"] == "http://orch2.com")

    assert client1.token == "token-for-orch1"
    assert client2.token == "global-fallback-token"
    assert client1.url == "http://orch1.com"
