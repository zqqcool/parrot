# Parrot Repository Instructions

## Decision Standard

- Correctness, security, maintainability, observability, and testability take priority over delivery speed.
- When a request conflicts with established best practice or creates material risk, state the risk clearly and recommend a safer alternative before implementation.
- Do not accept a temporary workaround as a permanent design. Record its boundary and replacement condition.

## Required Reading

Before changing code, read the scoped `AGENTS.md` and the relevant standards under `docs/standards/`.

- Backend work: `backend/AGENTS.md`, `docs/standards/backend-standard.md`, and `docs/standards/security-tenancy-standard.md`.
- Frontend work: `frontend/AGENTS.md` and `docs/standards/frontend-standard.md`.
- Cross-cutting work: `docs/standards/architecture-boundaries.md`, `docs/standards/coding-standard.md`, and `docs/standards/testing-standard.md`.
- AI entry work: `docs/ai-interaction/`.

## Hard Constraints

- Production source files should remain below 400 lines and must not exceed 600 lines. Generated files are exempt. Any other exception must be recorded in `docs/standards/file-size-exceptions.txt`.
- Avoid god files. Split by ownership and behavior, not by arbitrary line chunks.
- Functions should remain below 60 lines, classes below 300 lines, and React pages/components below 250 lines unless a documented reason exists.
- Do not bypass module boundaries. HTTP routers translate protocols, services own use cases and transactions, and repositories own persistence.
- Do not put business logic in routers or ORM access in frontend/API schemas.
- Do not swallow exceptions. Log unexpected failures with request context without exposing secrets or stack traces to clients.
- Every tenant-owned record and operation must carry a non-null `tenant_id`. Backend authorization and data isolation are final; frontend checks are presentation only.
- Web management authentication uses an opaque HttpOnly session and CSRF protection. Never store authentication tokens in `localStorage` or expose session cookies to JavaScript.
- Application configuration is loaded from exactly one explicitly selected `dev.toml`, `sit.toml`, or `prod.toml`; do not implicitly read environment variables or overlay a second file. The tracked files may contain only disposable MVP test credentials. Before real user data, paid resources, or real production accounts are introduced, rotate every embedded value and restore repository-external secret delivery or an approved KMS integration.
- Docker Compose is only for local dependencies such as PostgreSQL and Redis. Do not add an application image without an explicit architecture decision.
- Text and voice entry routes and UI state remain independent. Both must adapt into the same backend AI harness.
- `skyler/` is retained as migration source material. Do not import its internal modules at runtime, mount its routers, change its files, discard its untracked files, or trust its `union-id` header as authentication. Migrate behavior into Parrot domain modules under ADR 0002.
- OpenAPI is the source of truth for frontend/backend contracts. Do not maintain a second hand-written wire schema.
- Feature components must use the shared HTTP/API layer. Direct `fetch` calls outside `frontend/src/shared/http/` are prohibited.
- New core behavior and bug fixes require tests. If automated coverage is impossible, document why and provide a reproducible manual check.
- Vector database work is out of scope until explicitly approved.

## Engineering Workflow

1. Inspect existing code and dependency impact before editing.
2. State material risks or contract changes.
3. Keep changes scoped and preserve unrelated user work.
4. Add or update tests and standards with behavior changes.
5. Run the root quality checks before handoff.

## Stable Contracts

- API prefix: `/api/v1`.
- JSON response: `{ code, message, data, request_id }`; errors use `{ code, message, details, request_id }`.
- Request ID: `X-Request-Id` is propagated through responses, logs, jobs, and events.
- Tenant-private resources return 404 when invisible to prevent existence disclosure.
- Executed Alembic migrations are immutable; schema changes require new migrations.

## Documentation

- Code identifiers and comments use English. Standards may use Chinese.
- Standard documents describe reusable engineering behavior rather than business stories and include pseudocode for non-trivial contracts.
- Architecture, authentication, tenancy, API, or deployment changes must update the relevant standard in the same change.
