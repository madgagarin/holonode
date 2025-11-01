"""A Python SDK for creating workers for the Py-Orchestrator."""

from importlib.metadata import PackageNotFoundError, version

from .worker import Worker

__all__ = ["Worker"]

try:
    __version__ = version("holonode")
except PackageNotFoundError:
    __version__ = "unknown"
