"""A Python SDK for creating workers for the Py-Orchestrator."""

from importlib.metadata import PackageNotFoundError, version

from .task_files import TaskFiles
from .worker import Worker

__all__ = ["Worker", "TaskFiles"]

try:
    __version__ = version("holonode")
except PackageNotFoundError:
    __version__ = "unknown"
