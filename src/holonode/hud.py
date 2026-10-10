# Copyright (c) 2026 Dmitry Gagarin aka madgagarin
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

from dataclasses import dataclass, field
from sys import stdout
from time import time


@dataclass
class WorkerHUD:
    """Statusline TUI HUD for monitoring worker status and load in real time."""

    worker_id: str = "worker-local"
    status: str = "idle"
    active_tasks: dict[str, str] = field(default_factory=dict)
    completed_count: int = 0
    failed_count: int = 0
    start_time: float = field(default_factory=time)
    hot_skills: set[str] = field(default_factory=set)
    enabled: bool = False

    def update_status(self, status: str) -> None:
        self.status = status

    def task_started(self, task_id: str, skill_name: str) -> None:
        self.active_tasks[task_id] = skill_name
        self.status = "busy"

    def task_finished(self, task_id: str, success: bool = True) -> None:
        self.active_tasks.pop(task_id, None)
        if success:
            self.completed_count += 1
        else:
            self.failed_count += 1
        if not self.active_tasks:
            self.status = "idle"

    def render_line(self) -> str:
        """Renders single-line HUD statusline with ANSI colors."""
        uptime = int(time() - self.start_time)
        uptime_str = f"{uptime // 60:02d}:{uptime % 60:02d}"
        active = len(self.active_tasks)
        status_color = "\033[92m" if self.status == "idle" else ("\033[93m" if self.status == "busy" else "\033[91m")
        reset = "\033[0m"
        cyan = "\033[96m"
        magenta = "\033[95m"

        return (
            f"[{cyan}{self.worker_id}{reset}] "
            f"Status: {status_color}{self.status.upper()}{reset} | "
            f"Active: {cyan}{active}{reset} | "
            f"Done: \033[92m{self.completed_count}{reset} | "
            f"Failed: \033[91m{self.failed_count}{reset} | "
            f"Hot: {magenta}{len(self.hot_skills)}{reset} | "
            f"Uptime: {uptime_str}"
        )

    def render_box(self) -> str:
        """Renders multi-line boxed HUD card for inspect/CLI."""
        uptime = int(time() - self.start_time)
        active = len(self.active_tasks)
        active_items = [f"{k[:8]}:{v}" for k, v in list(self.active_tasks.items())[:3]]
        active_str = ", ".join(active_items) if active_items else "none"
        hot_str = ", ".join(sorted(self.hot_skills)) if self.hot_skills else "none"

        return (
            "╭─────────────────────────────────────────────────────────────╮\n"
            f"│  🛠️  HOLARCHY WORKER HUD: {self.worker_id:<32}│\n"
            "├─────────────────────────────────────────────────────────────┤\n"
            f"│  Status:    {self.status.upper():<16} Uptime: {uptime}s{' ':<18}│\n"
            f"│  Active:    {active:<16} Done:   {self.completed_count:<18}│\n"
            f"│  Failed:    {self.failed_count:<16} Hot:    {len(self.hot_skills):<18}│\n"
            f"│  Running:   {active_str[:47]:<48}│\n"
            f"│  Hot list:  {hot_str[:47]:<48}│\n"
            "╰─────────────────────────────────────────────────────────────╯"
        )

    def print_statusline(self) -> None:
        """Prints statusline to stdout if enabled."""
        if not self.enabled:
            return
        stdout.write(f"\r{self.render_line()}")
        stdout.flush()


__all__ = ["WorkerHUD"]
