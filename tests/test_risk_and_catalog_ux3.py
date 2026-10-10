# Copyright (c) 2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from holonode.worker import SkillBlueprint, Worker


class InParams(BaseModel):
    query: str
    limit: int = 10


class OutParams(BaseModel):
    items: list[str]


def test_skill_registration_with_risk_and_permissions() -> None:
    worker = Worker(worker_type="data-worker")

    @worker.skill(
        "query_database",
        risk="high",
        permissions=["db:read", "db:write"],
        description="Executes complex database query.",
    )
    def query_database(params: InParams) -> OutParams:
        return OutParams(items=[params.query])

    @worker.skill("ping", description="Ping skill with default low risk")
    def ping() -> dict[str, str]:
        return {"status": "pong"}

    index = worker.get_skills_index()
    assert len(index) == 2
    index_by_name = {s["name"]: s for s in index}

    db_idx = index_by_name["query_database"]
    assert db_idx["risk"] == "high"
    assert db_idx["name"] == "query_database"
    assert "input_schema" not in db_idx

    ping_idx = index_by_name["ping"]
    assert ping_idx["risk"] == "low"
    assert "input_schema" not in ping_idx

    schema = worker.get_skill_schema("query_database")
    assert schema is not None
    assert schema["name"] == "query_database"
    assert schema["risk"] == "high"
    assert schema["permissions"] == ["db:read", "db:write"]
    assert schema["input_schema"] is not None
    assert schema["description"] == "Executes complex database query."

    assert worker.get_skill_schema("non_existent_skill") is None


def test_blueprint_skills_index() -> None:
    bp = SkillBlueprint()

    @bp.skill("compress_file", risk="medium", permissions=["fs:write"])
    def compress_file(params: dict[str, Any]) -> dict[str, Any]:
        return {"compressed": True}

    index = bp.get_skills_index()
    assert len(index) == 1
    assert index[0]["name"] == "compress_file"
    assert index[0]["risk"] == "medium"
