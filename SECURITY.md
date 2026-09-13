**EN** | [ES](https://github.com/madgagarin/holonode/blob/main/docs/es/SECURITY.md) | [RU](https://github.com/madgagarin/holonode/blob/main/docs/ru/SECURITY.md)

# Security Policy

## Reporting a Vulnerability

If you discover a potential security vulnerability in the Worker SDK, please do not open a public issue. Instead, send an email to madgagarin@gmail.com.

## Security Model

The Worker SDK is a core execution node in the **Holarchical Logic Network (HLN)** and the Holarchy ecosystem, designed with Zero Trust and security-first principles:

1. **Mutual TLS (mTLS)**: Supports client certificates for secure, authenticated communication with the Orchestrator.
2. **Dynamic Token Rotation**: Automatically handles refreshing STS (Security Token Service) access tokens without worker restarts.
3. **Strict Isolation**: Each task operates in its own isolated temporary directory (`TASK_FILES_DIR`). Data from one task cannot be accessed by another.
4. **Path Traversal Protection**: Enforces containment within task directories preventing path traversal attacks.
5. **Automatic Cleanup**: Temporary task data and `.tmp_*` files are securely wiped immediately after task completion or failure to prevent data lingering.
6. **Sensitive Data Protection**: S3 credentials and orchestrator tokens are handled exclusively via environment variables or secure configuration objects, never logged.
7. **Message Integrity (HMAC-SHA256)**: The worker automatically signs all outbound messages (heartbeats, results, events) with its token, preventing data tampering in transit.
8. **Incoming Task Signature Verification**: Validates HMAC-SHA256 signatures (`sig` / `orchestrator_signature`) on incoming tasks using `ORCHESTRATOR_SECRET_KEY`.
9. **Execution Policy Enforcement**: Validates that incoming tasks comply with `allowed_skills` execution policies.
10. **Replay Protection**: All signed messages contain an integer `timestamp`. The orchestrator rejects expired or replayed packets.

See the full [RXON / HLN Security Model](https://github.com/madgagarin/rxon/blob/main/SECURITY.md) and [Holarchy Security Policy](https://github.com/madgagarin/holarchy/blob/main/SECURITY.md) for ecosystem-wide details.
