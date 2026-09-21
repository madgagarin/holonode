**EN** | [ES](https://github.com/madgagarin/holonode/blob/main/docs/es/README.md) | [RU](https://github.com/madgagarin/holonode/blob/main/docs/ru/README.md)

# Holonode SDK

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![PyPI Version](https://img.shields.io/pypi/v/holonode.svg)](https://pypi.org/project/holonode/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/release/python-3110/)

**Holonode SDK** is the official high-performance Python SDK for building distributed execution nodes (Workers / Holons) compatible with the **Holarchy** orchestrator. It serves as an execution node (**Shell**) in a **Holarchical Logic Network (HLN)**, coordinating with the orchestrator (**Ghost**) via the **RXON** (Reverse Axon Protocol).

The SDK automates all low-level communication concerns: task polling, dynamic registration, heartbeats, S3 payload management, Zero Trust authentication, and graceful shutdown.

## 🚀 Key Features

- **Language:** Python 3.11+
- **Protocol:** Native support for **RXON** (Reverse Axon Protocol) for **HLN** (Holarchical Logic Network).
- **Communication Model:**
  - **PULL:** Workers poll tasks from orchestrators (operates securely behind NAT/Firewall without public incoming ports).
  - **WebSocket:** Optional real-time bidirectional command channel (task cancellation, custom runtime commands).
- **Zero Trust Security & Policy Enforcement:**
  - Mandatory HMAC-SHA256 signing for all worker messages using `WORKER_TOKEN`.
  - Cryptographic verification of `orchestrator_signature` (`sig`) on incoming tasks via `ORCHESTRATOR_SECRET_KEY`.
  - Strict enforcement of `allowed_skills` task execution policies.
  - Automatic collection and reporting of task execution cost metrics (`costs`).
  - Identity Chain and Origin Worker ID support for provenance tracking across infinite holarchy layers.
  - Replay protection with timestamp validation.
- **Traffic & Performance Optimization:**
  - **Telemetry Throttling (Heartbeat Deadband):** Hardware telemetry (CPU/RAM/GPU) is only sent when a value changes by >5% or after a 60s forced interval, drastically saving network bandwidth.
  - **ETag-Based Blob Caching:** Heavy assets (e.g. AI model weights) are downloaded only once from S3, cached locally with ETag validation, and symlinked to task workspaces.
  - **Async Results Uploader:** Task results are queued via non-blocking `asyncio.Queue` with automatic retries and exponential backoff, instantly freeing the worker for the next task.
  - **3-Tier Skill Lifecycle:** _Supported_ (catalog), _Available_ (dynamic limits), and _Hot_ (cached in memory/VRAM).
  - **Stable Hashing:** Sends full skill catalog only when changed, using `skills_hash` for ultra-light heartbeats.
- **S3 Streaming:** High-performance payload streaming using `obstore`. Zero OOM on large files.
- **AI-Agent Support:** Supports Chain of Thought and Tool Use via `OrchestratorClient` dependency injection for subtask delegation.
- **Hardware Awareness:** Built-in monitoring for CPU, RAM, and NVIDIA GPUs (via `psutil` and `GPUtil`).
- **Modern Observability:**
  - Native distributed tracing and metrics with **OpenTelemetry**.
  - Automatic **Trace Context Propagation**: Extracts `trace_id` from tasks and propagates it to all events and child spans.
  - OTLP metrics push export via `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Table of Contents

- [Core Concept: Holarchy, Ghost, and Shell](#core-concept-holarchy-ghost-and-shell)
- [Ecosystem](#ecosystem)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Usage as a Library](#usage-as-a-library)
  - [CLI Usage](#cli-usage)
- [Configuration Reference](#configuration-reference)
- [Resilience & Connectivity](#resilience--connectivity)
- [Observability](#observability)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Core Concept: Holarchy, Ghost, and Shell

The Holarchy architecture follows the principles of a **Holarchical Logic Network (HLN)**:

- **Orchestrator (The Ghost / Director):** Manages high-level workflow state machines (Blueprints), tracks execution states, and coordinates jobs. It never initiates outbound network connections to workers.
- **Worker (The Shell / Muscle):** A specialized, autonomous execution unit (**Holon**). It connects to the Orchestrator from the bottom up via **RXON**, polls tasks, executes them in isolated environments, and returns results.
- **Shell-Stacking (Matryoshka):** Because workers and orchestrators adhere to standardized interfaces, an entire Orchestrator can be wrapped inside a Worker Shell. This enables the construction of recursive, self-similar fractal networks (**Holarchies**) of arbitrary depth.

## Ecosystem

Holonode SDK is an integral part of the Holarchy distributed ecosystem:

- **[Holarchy Orchestrator](https://github.com/madgagarin/holarchy)**: High-performance state-machine workflow engine coordinating tasks and distributed blueprints.
- **[RXON Protocol](https://github.com/madgagarin/rxon)**: Shared lightweight reverse-connection protocol powering inter-node communication across the HLN ecosystem.
- **[HLN (Holarchical Logic Network)](https://github.com/madgagarin/hln)**: Architectural pattern, manifesto, and design specification for self-similar holarchies.
- **[Holonode SDK](https://github.com/madgagarin/holonode)**: The official Python SDK for building execution workers (this repository).
- **[Full Example](https://github.com/madgagarin/holarchy-full-example)**: Reference project demonstrating the orchestrator and workers in action.

## Installation

- **Install the core SDK only:**

  ```bash
  pip install holonode
  ```

- **Install with S3 payload offloading support:**

  ```bash
  pip install "holonode[s3]"
  ```

- **Install with Pydantic v2 schema inference support:**

  ```bash
  pip install "holonode[pydantic]"
  ```

- **Install with OpenTelemetry metrics and tracing:**

  ```bash
  pip install "holonode[metrics]"
  ```

- **Install all production features (Recommended):**

  ```bash
  pip install "holonode[s3,pydantic,metrics]"
  ```

- **Install for development:**

  ```bash
  pip install -e ".[dev]"
  ```

## Quick Start

### Usage as a Library

```python
from pydantic import BaseModel, Field
from holonode import OrchestratorClient, TaskFiles, Worker


class GreetingParams(BaseModel):
    name: str = Field(default="World", description="Name to greet")


worker = Worker(worker_type="greeter-service")


@worker.skill("hello_world", risk="low", permissions=["greetings:write"])
async def my_skill(params: GreetingParams, files: TaskFiles):
    """The SDK validates incoming task data directly into GreetingParams."""
    return {"message": f"Hello, {params.name}!"}


@worker.skill("ai_agent_reasoning", risk="medium", permissions=["ai:reason"])
async def agent_skill(params: dict, orchestrator_client: OrchestratorClient):
    """AI agent skill delegating a subtask (tool use) via OrchestratorClient."""
    search_result = await orchestrator_client.call_skill("web_search", {"query": params["search_query"]})
    return {"result": f"Based on web search: {search_result['data']}"}


@worker.on_command("reboot")
async def handle_reboot(command: dict):
    """Custom command received over the real-time WebSocket channel."""
    print("Rebooting worker...")


if __name__ == "__main__":
    worker.run()
```

> For step-by-step guidance, see the [Local Worker Development Cookbook](https://github.com/madgagarin/holarchy/blob/main/docs/cookbook/local_worker_development.md).

### CLI Usage

The SDK includes a built-in CLI tool for managing worker lifecycles, health probes, and live-reload during development:

```bash
# Run the worker with health-check server on port 8083 (default)
worker run --app my_worker:worker

# Run in development mode with automatic reload on code changes
worker run --app my_worker:worker --reload

# Run on a custom port without the health-check server
worker run --app my_worker:worker --port 9000 --no-health-check
```

## Configuration Reference

All settings can be configured via environment variables:

| Variable | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `ORCHESTRATOR_URL` | String | `http://localhost:8080` | Fallback URL when connecting to a single orchestrator |
| `ORCHESTRATORS_CONFIG` | JSON String | `None` | JSON list of orchestrator configs (`url`, `priority`, `weight`) |
| `MULTI_ORCHESTRATOR_MODE` | String | `WATERFALL` | Polling strategy: `WATERFALL` (priority order) or `ROUND_ROBIN` |
| `WORKER_ID` | String | Auto-generated | Unique identifier for the worker instance |
| `WORKER_TYPE` | String | `generic-cpu-worker` | Type tag for skill matching and targeting |
| `WORKER_PORT` | Integer | `8083` | Port for the built-in HTTP health check probe (`/health`) |
| `WORKER_TOKEN` | String | `None` | Secret token used for HMAC-SHA256 message signing (Zero Trust) |
| `ORCHESTRATOR_SECRET_KEY` | String | `None` | Secret key used to verify incoming task signatures (`sig`) |
| `REQUIRE_TASK_SIGNATURE` | Boolean | `True` | Enforce signature verification when `ORCHESTRATOR_SECRET_KEY` is set |
| `COST_PER_SKILL` | JSON String | `None` | JSON mapping of skill execution tariffs (e.g. `'{"render": 0.05}'`) |
| `MAX_CONCURRENT_TASKS` | Integer | `None` | Global concurrency limit for parallel task executions |
| `WORKER_ENABLE_WEBSOCKETS` | Boolean | `True` | Enable real-time WebSocket connection for commands and cancellation |
| `S3_ENDPOINT_URL` | String | `None` | S3-compatible storage endpoint URL for payload offloading |
| `S3_ACCESS_KEY` | String | `None` | S3 access key ID |
| `S3_SECRET_KEY` | String | `None` | S3 secret access key |
| `S3_DEFAULT_BUCKET` | String | `None` | Default S3 bucket for task file transfers |
| `WORKER_BLOB_CACHE_DIR` | String | `/tmp/holarchy_cache` | Local directory for caching S3 blobs with ETag validation |
| `TASK_FILES_DIR` | String | `/tmp/payloads` | Local base directory for isolated task workspace files |
| `WORKER_TELEMETRY_DEADBAND` | Float | `5.0` | Percentage change threshold for emitting hardware telemetry |
| `WORKER_TELEMETRY_FORCE_INTERVAL` | Float | `60.0` | Maximum interval (seconds) before telemetry is forcefully emitted |
| `POLL_BACKOFF_INITIAL` | Float | `1.0` | Initial delay (seconds) after network error or 429 response |
| `POLL_BACKOFF_MAX` | Float | `60.0` | Maximum backoff delay (seconds) |
| `POLL_BACKOFF_FACTOR` | Float | `2.0` | Multiplier for exponential backoff calculations |
| `STRICT_EVENT_VALIDATION` | Boolean | `True` | Validate emitted events against protocol schemas before dispatch |
| `LOG_LEVEL` | String | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## Resilience & Connectivity

- **Independent Orchestrator Managers:** Each orchestrator connection is handled by an isolated background task. Outages or rate limits on one orchestrator never block others.
- **Smart Backoff & Retry Storm Protection:** Unified exponential backoff honors the HTTP `Retry-After` header (seconds or HTTP date). Errors with status 429 without `Retry-After` enforce a mandatory 30-second safety floor to prevent retry storms.
- **Heartbeat Debouncing:** Throttles heartbeats to a maximum of once every 2 seconds. State updates during the cooldown are coalesced and dispatched cleanly.
- **Graceful Shutdown:** Handles `SIGINT` and `SIGTERM` cleanly, awaiting active task completion and notifying orchestrators prior to process exit.

## Observability

Holonode SDK provides first-class observability using **OpenTelemetry**:

- **Distributed Tracing:** Workers extract `trace_id` from tasks and create child spans (`task.{type}`). All emitted events and S3 operations share the same trace.
- **Push Metrics (OTLP):** When `OTEL_EXPORTER_OTLP_ENDPOINT` is configured, metrics are automatically exported via OTLP.
- **ObservabilityManager Injection:** Handlers can accept `obs: ObservabilityManager` to create custom sub-spans and attach diagnostic metadata.

## Security

Security is foundational to the Holarchy ecosystem:

- See the full [RXON / HLN Security Model](https://github.com/madgagarin/rxon/blob/main/SECURITY.md).
- See the [Holarchy Security Policy](https://github.com/madgagarin/holarchy/blob/main/SECURITY.md).
- Detailed worker security policies are documented in [SECURITY.md](https://github.com/madgagarin/holonode/blob/main/SECURITY.md).

## Contributing

We welcome contributions! Please review our [Contributor Guide](https://github.com/madgagarin/holonode/blob/main/CONTRIBUTING.md) and [Development Guide](https://github.com/madgagarin/holonode/blob/main/docs/DEVELOPMENT.md) for environment setup and testing instructions.

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL 2.0)**.
