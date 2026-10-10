# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Dmitry Gagarin aka madgagarin

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from asyncio import run as asyncio_run
from importlib import import_module
from os import getcwd
from pathlib import Path
from subprocess import Popen
from sys import executable
from sys import exit as sys_exit
from sys import path as sys_path
from time import sleep
from typing import Any

from aiohttp import web
from orjson import OPT_INDENT_2
from orjson import dumps as orjson_dumps
from orjson import loads as orjson_loads

from holonode.local_runner import create_dev_app, execute_local_skill, inspect_worker_skills
from holonode.worker import Worker

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:
    FileSystemEventHandler: Any = object  # type: ignore[no-redef]
    Observer = None
    _HAS_WATCHDOG = False


def import_string(import_name: str) -> Any:
    """Imports an object by its string path (e.g. 'module.submodule:attribute')."""
    try:
        module_path, obj_name = import_name.split(":")
    except ValueError:
        raise ImportError(f"Invalid format '{import_name}'. Use 'module:attribute'.") from None

    module = import_module(module_path)
    try:
        return getattr(module, obj_name)
    except AttributeError:
        raise ImportError(f"Module '{module_path}' has no attribute '{obj_name}'.") from None


def _load_worker(app_spec: str) -> Worker:
    sys_path.insert(0, getcwd())
    try:
        worker = import_string(app_spec)
    except ImportError as e:
        print(f"Error importing worker: {e}")
        sys_exit(1)

    if not isinstance(worker, Worker):
        print(f"Error: Object '{app_spec}' is not an instance of holonode.Worker")
        sys_exit(1)

    return worker


def run_worker(args: Namespace) -> None:
    worker = _load_worker(args.app)

    if getattr(args, "port", None) is not None:
        worker._config.WORKER_PORT = args.port

    if getattr(args, "hud", False):
        worker.hud.enabled = True

    if args.health_check:
        worker.run_with_health_check()
    else:
        worker.run()


def exec_worker(args: Namespace) -> None:
    worker = _load_worker(args.app)
    raw_params = args.params or "{}"
    if raw_params.startswith("@"):
        param_file = Path(raw_params[1:])
        if not param_file.exists():
            print(f"Error: Parameter file '{param_file}' does not exist.")
            sys_exit(1)
        try:
            params_dict = orjson_loads(param_file.read_bytes())
        except Exception as e:
            print(f"Error parsing JSON in parameter file '{param_file}': {e}")
            sys_exit(1)
    else:
        try:
            params_dict = orjson_loads(raw_params)
        except Exception as e:
            print(f"Error parsing JSON params: {e}")
            sys_exit(1)

    result = asyncio_run(
        execute_local_skill(
            worker=worker,
            skill_name=args.skill,
            params=params_dict,
            task_id=args.task_id,
            local_dir=args.local_dir,
        )
    )

    print(orjson_dumps(result, option=OPT_INDENT_2, default=str).decode())
    if result.get("status") != "success":
        sys_exit(1)


def inspect_worker(args: Namespace) -> None:
    worker = _load_worker(args.app)

    if getattr(args, "skill", None):
        schema = worker.get_skill_schema(args.skill)
        if not schema:
            print(f"Skill '{args.skill}' not found.")
            sys_exit(1)
        print(orjson_dumps(schema, option=OPT_INDENT_2).decode())
        return

    skills = inspect_worker_skills(worker)
    if getattr(args, "json", False):
        print(orjson_dumps(skills, option=OPT_INDENT_2).decode())
        return

    print("═══════════════════════════════════════════════════════════════════════════════")
    print(f" 🛠️  REGISTERED SKILLS ON WORKER: {worker._config.WORKER_ID} ({len(skills)} skills)")
    print("═══════════════════════════════════════════════════════════════════════════════")
    for s in skills:
        risk = (s.get("risk") or "low").upper()
        risk_color = "\033[92m" if risk == "LOW" else ("\033[93m" if risk == "MEDIUM" else "\033[91m")
        reset = "\033[0m"
        perms = ", ".join(s.get("permissions") or []) or "none"
        print(f" • \033[1m{s.get('name')}\033[0m (type: {s.get('type')}, v{s.get('version') or '1.0'})")
        print(f"   Risk: {risk_color}{risk}{reset} | Permissions: {perms}")
        if s.get("description"):
            print(f"   Description: {s.get('description')}")
    print("═══════════════════════════════════════════════════════════════════════════════")


def dev_worker(args: Namespace) -> None:
    worker = _load_worker(args.app)
    app = create_dev_app(worker=worker, local_dir=args.local_dir)
    print(f"🚀 Starting Holonode Dev Testbench at http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port)


def main() -> None:
    parser = ArgumentParser(description="Holonode CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    run_parser = subparsers.add_parser("run", help="Run a worker instance")
    run_parser.add_argument("--app", required=True, help="Path to the worker instance (e.g. 'my_module:worker')")
    run_parser.add_argument(
        "--health-check", action="store_true", default=True, help="Enable health check server (default: True)"
    )
    run_parser.add_argument(
        "--no-health-check", action="store_false", dest="health_check", help="Disable health check server"
    )
    run_parser.add_argument(
        "--port", type=int, default=None, help="Port for the health check server (overrides WORKER_PORT)"
    )
    run_parser.add_argument("--hud", action="store_true", default=False, help="Enable statusline TUI HUD in terminal")
    run_parser.add_argument(
        "--reload", action="store_true", help="Restart worker on code changes (requires 'watchdog')"
    )

    exec_parser = subparsers.add_parser("exec", help="Execute a single skill locally on mock task files")
    exec_parser.add_argument("--app", required=True, help="Path to worker instance (e.g. 'my_module:worker')")
    exec_parser.add_argument("--skill", required=True, help="Name of skill to execute")
    exec_parser.add_argument("--params", default="{}", help="Input params JSON string or @params.json file path")
    exec_parser.add_argument("--task-id", default=None, help="Custom task ID for the local mock task")
    exec_parser.add_argument(
        "--local-dir", default="./.holarchy/local_tasks", help="Base directory for local mock task files"
    )

    inspect_parser = subparsers.add_parser("inspect", help="Inspect registered skills, risks, and permissions")
    inspect_parser.add_argument("--app", required=True, help="Path to worker instance (e.g. 'my_module:worker')")
    inspect_parser.add_argument("--skill", default=None, help="Inspect specific skill schema")
    inspect_parser.add_argument("--json", action="store_true", help="Output skills catalog as JSON")

    dev_parser = subparsers.add_parser("dev", help="Start local web testbench for skills debugging")
    dev_parser.add_argument("--app", required=True, help="Path to worker instance (e.g. 'my_module:worker')")
    dev_parser.add_argument("--host", default="127.0.0.1", help="Host to bind dev testbench (default: 127.0.0.1)")
    dev_parser.add_argument("--port", type=int, default=8088, help="Port to bind dev testbench (default: 8088)")
    dev_parser.add_argument(
        "--local-dir", default="./.holarchy/local_tasks", help="Base directory for local mock task files"
    )

    args = parser.parse_args()

    if args.command == "run":
        if args.reload:
            if not _HAS_WATCHDOG:
                print(
                    "Error: '--reload' requires the 'watchdog' package. "
                    "Install it with 'pip install watchdog' or 'pip install holonode[dev]'"
                )
                sys_exit(1)

            print(f"Watching for changes in {getcwd()}...")

            class ReloadHandler(FileSystemEventHandler):
                def __init__(self, cmd_args: Namespace) -> None:
                    self.cmd_args = cmd_args
                    self.process: Popen[bytes] | None = None
                    self.start_worker()

                def start_worker(self) -> None:
                    if self.process:
                        self.process.terminate()
                        self.process.wait()

                    new_args = [executable, "-m", "holonode", "run", "--app", self.cmd_args.app]
                    if self.cmd_args.health_check:
                        new_args.append("--health-check")
                    else:
                        new_args.append("--no-health-check")
                    if getattr(self.cmd_args, "port", None) is not None:
                        new_args.extend(["--port", str(self.cmd_args.port)])
                    if getattr(self.cmd_args, "hud", False):
                        new_args.append("--hud")

                    self.process = Popen(new_args)

                def on_any_event(self, event: Any) -> None:
                    if event.is_directory or not getattr(event, "src_path", "").endswith(".py"):
                        return
                    print(f"Change detected in {event.src_path}. Restarting...")
                    self.start_worker()

            handler = ReloadHandler(args)
            if Observer:
                observer = Observer()
                observer.schedule(handler, path=getcwd(), recursive=True)
                observer.start()
                try:
                    while True:
                        sleep(1)
                except KeyboardInterrupt:
                    observer.stop()
                    if handler.process:
                        handler.process.terminate()
                observer.join()
        else:
            run_worker(args)
    elif args.command == "exec":
        exec_worker(args)
    elif args.command == "inspect":
        inspect_worker(args)
    elif args.command == "dev":
        dev_worker(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
