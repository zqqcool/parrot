# Backend Instructions

These rules extend the repository root `AGENTS.md` for `backend/`.

## Boundaries

- Use `core / infrastructure / modules / api` boundaries.
- API routers parse requests, invoke one application service, and build responses. They do not query SQLAlchemy directly.
- Services own authorization-sensitive use cases and transaction boundaries.
- Repositories own SQLAlchemy statements and persistence mapping. Raw SQL is limited to migrations, RLS setup, and reviewed repository queries.
- Pydantic request/response models are separate from SQLAlchemy models.
- Shared infrastructure must not import domain modules. Modules may depend on stable core and infrastructure ports.

## Security And Tenancy

- Resolve a typed principal and tenant context before tenant-owned data access.
- Repository methods for tenant-owned data require `tenant_id`; optional tenant scope is prohibited.
- PostgreSQL RLS and application predicates are both required for tenant isolation.
- Store only hashes of opaque session and CSRF secrets. Use Argon2id for passwords.
- Mutations require CSRF and Origin validation for browser sessions.
- User disablement, password changes, and permission reduction revoke affected sessions.
- Never log passwords, cookies, CSRF values, credentials, raw private prompts, or full model outputs.

## Configuration And Persistence

- The application starts with an explicit `--config <path>` TOML selection.
- Do not call `os.getenv` or load `.env` files.
- PostgreSQL is the source of truth. Redis is for rate limits, queues, locks, and caches with TTL.
- All schema changes use additive Alembic migrations. Do not edit an applied revision.
- Database timestamps are UTC and API timestamps are ISO 8601.

## Quality

- Run Ruff format/check, Pyright strict, file-size checks, and Pytest.
- Core IAM, tenancy, and RBAC behavior targets at least 95% branch coverage; backend overall targets 85%.
- Integration tests must prove tenant isolation, permission denial, session revocation, CSRF rejection, and migration viability.
