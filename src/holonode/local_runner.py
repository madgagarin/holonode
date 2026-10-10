# Copyright (c) 2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from inspect import Parameter, get_annotations, iscoroutinefunction, signature
from os.path import join as path_join
from time import perf_counter
from traceback import format_exc
from typing import TYPE_CHECKING, Any, cast, get_type_hints
from uuid import uuid4

from aiohttp import web
from msgspec import to_builtins
from orjson import dumps as orjson_dumps
from orjson import loads as orjson_loads

from holonode.observability import ObservabilityManager
from holonode.task_files import TaskFiles
from holonode.worker import OrchestratorClient

if TYPE_CHECKING:
    from holonode.worker import Worker


def _serialize_result_val(val: Any) -> Any:
    """Recursively serializes Pydantic models, msgspec Structs, or dataclasses into dicts."""
    if hasattr(val, "model_dump"):
        return val.model_dump()
    if hasattr(val, "dict") and callable(getattr(val, "dict", None)):
        return val.dict()
    if hasattr(val, "__struct_fields__"):
        return to_builtins(val)
    if is_dataclass(val) and not isinstance(val, type):
        return asdict(val)
    if isinstance(val, list):
        return [_serialize_result_val(item) for item in val]
    if isinstance(val, dict):
        return {k: _serialize_result_val(v) for k, v in val.items()}
    return val


class LocalMockTaskFiles(TaskFiles):
    """Mock TaskFiles implementation rooted in local filesystem directory."""

    def __init__(self, task_dir: str, job_id: str = "local-job", task_id: str = "local-task"):
        super().__init__(task_dir=task_dir, job_id=job_id, task_id=task_id)


def inspect_worker_skills(worker: Worker) -> list[dict[str, Any]]:
    """Returns inspection metadata for all registered skills on the worker."""
    results = []
    handlers = getattr(worker, "_skill_handlers", {})
    for skill_name, handler_data in handlers.items():
        info = handler_data.get("info")
        results.append(
            {
                "name": skill_name,
                "type": getattr(info, "type", None) or skill_name,
                "version": getattr(info, "version", None),
                "risk": getattr(info, "risk", "low"),
                "permissions": getattr(info, "permissions", None) or [],
                "description": getattr(info, "description", None),
                "input_schema": getattr(info, "input_schema", None),
                "output_schema": getattr(info, "output_schema", None),
            }
        )
    return results


async def execute_local_skill(
    worker: Worker,
    skill_name: str,
    params: dict[str, Any] | None = None,
    task_id: str | None = None,
    local_dir: str = "./.holarchy/local_tasks",
) -> dict[str, Any]:
    """Executes a registered skill locally with mock environment and TaskFiles."""
    handlers = getattr(worker, "_skill_handlers", {})
    if skill_name not in handlers:
        return {
            "status": "failure",
            "skill": skill_name,
            "error": f"Skill '{skill_name}' is not registered on this worker.",
        }

    handler_data = handlers[skill_name]
    func = handler_data["func"]
    tid = task_id or f"local-{uuid4().hex[:8]}"
    job_id = f"job-{uuid4().hex[:8]}"

    task_dir = path_join(local_dir, tid)
    task_files = LocalMockTaskFiles(task_dir=task_dir, job_id=job_id, task_id=tid)

    raw_params = params or {}
    try:
        call_params = (
            worker._prepare_task_params(func, raw_params) if hasattr(worker, "_prepare_task_params") else raw_params
        )
    except Exception as exc:
        return {
            "status": "failure",
            "task_id": tid,
            "skill": skill_name,
            "error": f"Parameter validation error: {exc}",
            "traceback": format_exc(),
            "duration_ms": 0.0,
        }

    async def dummy_send_progress(*args: Any, **kwargs: Any) -> None:
        pass

    async def dummy_send_event(*args: Any, **kwargs: Any) -> None:
        pass

    obs = getattr(worker, "_observability", None) or ObservabilityManager(enabled=False)
    mock_orchestrator_client = OrchestratorClient(client=cast(Any, None), worker=worker)

    sig = signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        try:
            hints = get_annotations(func)
        except Exception:
            hints = getattr(func, "__annotations__", {})

    def _matches_type(hint_val: Any, target_types: tuple[type, ...]) -> bool:
        if hint_val in target_types:
            return True
        if isinstance(hint_val, str):
            names = {t.__name__ for t in target_types}
            if hint_val in names or hint_val.split(".")[-1] in names:
                return True
        return False

    available = {
        "params": call_params,
        "task_files": task_files,
        "files": task_files,
        "task_id": tid,
        "job_id": job_id,
        "orchestrator_client": mock_orchestrator_client,
        "client": mock_orchestrator_client,
        "obs": obs,
        "observability": obs,
        "send_progress": dummy_send_progress,
        "send_event": dummy_send_event,
        "add_to_hot_skills": getattr(worker, "add_to_hot_skills", lambda _: None),
        "remove_from_hot_skills": getattr(worker, "remove_from_hot_skills", lambda _: None),
    }

    call_kwargs = {}
    for p_name, param in sig.parameters.items():
        if p_name in available:
            call_kwargs[p_name] = available[p_name]
        elif p_name in hints and _matches_type(hints[p_name], (TaskFiles, LocalMockTaskFiles)):
            call_kwargs[p_name] = task_files
        elif p_name in hints and _matches_type(hints[p_name], (ObservabilityManager,)):
            call_kwargs[p_name] = obs
        elif p_name in hints and _matches_type(hints[p_name], (OrchestratorClient,)):
            call_kwargs[p_name] = mock_orchestrator_client
        elif isinstance(call_params, dict) and p_name in call_params:
            call_kwargs[p_name] = call_params[p_name]
        elif param.default is not Parameter.empty:
            continue

    start_t = perf_counter()
    try:
        if iscoroutinefunction(func):
            res = await func(**call_kwargs)
        else:
            res = func(**call_kwargs)
        duration = round((perf_counter() - start_t) * 1000, 2)
        return {
            "status": "success",
            "task_id": tid,
            "skill": skill_name,
            "result": _serialize_result_val(res),
            "duration_ms": duration,
        }
    except Exception as exc:
        duration = round((perf_counter() - start_t) * 1000, 2)
        return {
            "status": "failure",
            "task_id": tid,
            "skill": skill_name,
            "error": str(exc),
            "traceback": format_exc(),
            "duration_ms": duration,
        }


HTML_TESTBENCH = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Holonode Dev Testbench</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0; padding: 20px; background: #0f172a; color: #f8fafc;
        }
        .container {
            max-width: 900px; margin: 0 auto; background: #1e293b;
            padding: 24px; border-radius: 8px; border: 1px solid #334155;
        }
        h1 { margin-top: 0; font-size: 22px; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
        label {
            font-size: 13px; font-weight: 600; color: #94a3b8;
            display: block; margin-top: 14px; margin-bottom: 4px;
        }
        select, textarea, button {
            width: 100%; box-sizing: border-box; border-radius: 6px;
            border: 1px solid #475569; background: #0f172a; color: #f8fafc;
            padding: 10px; font-size: 14px;
        }
        select { cursor: pointer; }
        textarea { font-family: monospace; min-height: 120px; }
        button {
            margin-top: 18px; background: #0284c7; color: white;
            font-weight: 600; cursor: pointer; border: none; transition: background 0.2s;
        }
        button:hover { background: #0369a1; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .risk-low { background: #065f46; color: #34d399; }
        .risk-medium { background: #854d0e; color: #fde047; }
        .risk-high { background: #991b1b; color: #f87171; }
        .info-box { background: #0f172a; padding: 12px; border-radius: 6px; margin-top: 12px; font-size: 13px; }
        pre {
            background: #020617; padding: 12px; border-radius: 6px;
            overflow-x: auto; color: #38bdf8; font-size: 13px;
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🛠️ Holonode Dev Testbench</h1>
    <label for="skill-select">Select Skill to Test</label>
    <select id="skill-select" onchange="onSkillChange()"></select>

    <div id="skill-details" class="info-box">
        <div>
            <strong>Type:</strong> <span id="skill-type">-</span> |
            <strong>Risk:</strong> <span id="skill-risk" class="badge risk-low">LOW</span>
        </div>
        <div style="margin-top: 6px;"><strong>Description:</strong> <span id="skill-desc">-</span></div>
    </div>

    <label for="params-input">Input Parameters (JSON)</label>
    <textarea id="params-input">{}</textarea>

    <button onclick="runSkill()">🚀 Execute Skill</button>

    <label>Execution Output</label>
    <pre id="output-box">// Results will appear here...</pre>
</div>

<script>
let skills = [];

async function loadSkills() {
    const res = await fetch('/api/skills');
    skills = await res.json();
    const sel = document.getElementById('skill-select');
    sel.innerHTML = '';
    skills.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.name;
        opt.textContent = `${s.name} [risk: ${s.risk}]`;
        sel.appendChild(opt);
    });
    if (skills.length > 0) onSkillChange();
}

function onSkillChange() {
    const sel = document.getElementById('skill-select');
    const skill = skills.find(s => s.name === sel.value);
    if (!skill) return;
    document.getElementById('skill-type').textContent = skill.type || skill.name;
    const rEl = document.getElementById('skill-risk');
    rEl.textContent = (skill.risk || 'low').toUpperCase();
    rEl.className = 'badge risk-' + (skill.risk || 'low');
    document.getElementById('skill-desc').textContent = skill.description || 'No description provided.';
}

async function runSkill() {
    const sel = document.getElementById('skill-select');
    const skillName = sel.value;
    const out = document.getElementById('output-box');
    out.textContent = "Executing...";
    let params = {};
    try {
        params = JSON.parse(document.getElementById('params-input').value || '{}');
    } catch(e) {
        out.textContent = "JSON parse error: " + e.message;
        return;
    }
    try {
        const res = await fetch('/api/exec/' + encodeURIComponent(skillName), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        const data = await res.json();
        out.textContent = JSON.stringify(data, null, 2);
    } catch(e) {
        out.textContent = "Execution request failed: " + e.message;
    }
}

window.onload = loadSkills;
</script>
</body>
</html>
"""


def create_dev_app(worker: Worker, local_dir: str = "./.holarchy/local_tasks") -> web.Application:
    """Creates a local developer aiohttp application with testbench UI and REST endpoints."""
    app = web.Application()

    async def handle_index(_req: web.Request) -> web.Response:
        return web.Response(text=HTML_TESTBENCH, content_type="text/html")

    async def handle_get_skills(_req: web.Request) -> web.Response:
        skills = inspect_worker_skills(worker)
        return web.Response(body=orjson_dumps(skills), content_type="application/json")

    async def handle_get_skill_schema(req: web.Request) -> web.Response:
        skill_name = req.match_info["name"]
        schema = worker.get_skill_schema(skill_name) if hasattr(worker, "get_skill_schema") else None
        if schema is None:
            return web.Response(status=404, text=f"Skill '{skill_name}' not found")
        return web.Response(body=orjson_dumps(schema), content_type="application/json")

    async def handle_exec_skill(req: web.Request) -> web.Response:
        skill_name = req.match_info["name"]
        try:
            body_bytes = await req.read()
            params = orjson_loads(body_bytes) if body_bytes else {}
        except Exception as e:
            return web.Response(
                status=400,
                body=orjson_dumps({"error": f"Invalid JSON payload: {e}"}),
                content_type="application/json",
            )

        res = await execute_local_skill(worker, skill_name, params=params, local_dir=local_dir)
        return web.Response(body=orjson_dumps(res), content_type="application/json")

    app.router.add_get("/", handle_index)
    app.router.add_get("/api/skills", handle_get_skills)
    app.router.add_get("/api/skills/{name}", handle_get_skill_schema)
    app.router.add_post("/api/exec/{name}", handle_exec_skill)

    return app


__all__ = [
    "LocalMockTaskFiles",
    "inspect_worker_skills",
    "execute_local_skill",
    "create_dev_app",
]
