"""A Python SDK for creating workers for the Holarchy Orchestrator."""

from importlib.metadata import PackageNotFoundError, version

from .logging import setup_logging
from .task_files import TaskFiles
from .worker import Worker

__all__ = ["Worker", "TaskFiles", "setup_logging"]

try:
    __version__ = version("holonode")
except PackageNotFoundError:
    __version__ = "unknown"
