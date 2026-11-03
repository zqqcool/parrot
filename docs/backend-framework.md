# Backend Framework

## Runtime

Parrot uses Python 3.13, FastAPI, SQLAlchemy 2 Async, Alembic, PostgreSQL, and Redis. The root
Docker Compose file supports both dependency-only host development and a SIT full stack with
separate backend and frontend images.

```text
docker compose up -d postgres redis
cd backend
.venv/bin/parrot db-upgrade --config config/dev.toml
.venv/bin/parrot bootstrap-admin --config config/dev.toml --password-file /path/outside/repository
.venv/bin/parrot serve --config config/dev.toml
```

Do not start or stop an existing backend process as part of routine validation.

For the containerized SIT stack, run `docker compose up -d --build`. The backend image contains the
complete `backend/config/sit.toml` as read-only `/etc/parrot/config.toml`. The migration container runs
`db-upgrade` and `sync-permissions` before the API. It does not create or rewrite tenant business
records. Worker containers stay in Compose profiles because the Web process must not own their loops.

## Configuration

Every command requires an explicit TOML path. The application does not read implicit environment variables.
The supported environment values are exactly `dev`, `sit`, and `prod`; `dev` and `sit` share the
same validation policy, while `prod` enables the production checks.

```text
config/dev.toml  # host development
config/sit.toml  # Docker Compose and shared test environment
config/prod.toml # production process configuration
```

Each file is complete; the loader does not merge a second secrets file. The embedded account values
are a temporary MVP exception and must remain disposable test credentials.

Database identities are separated:

```text
database.url           ordinary app role, RLS enforced
database.platform_url  controlled CLI role, BYPASSRLS
database.migration_url schema owner/migration role
```

Production requires three distinct database URLs and explicit HTTPS origins. Before real production
traffic or paid provider usage, replace the current test-only credentials, rotate every exposed value,
and restore repository-external secret delivery.

## Administration

The bootstrap command creates the initial tenant context, administrator, Argon2id credential,
membership, and required system-role assignments with `must_change_password=true`; no fixed password
exists in source or config. It does not create Agents, LLM configurations, Skills, MCP servers, or
Knowledge spaces.

```text
POST /api/v1/auth/login
GET  /api/v1/auth/session
POST /api/v1/auth/logout
POST /api/v1/auth/password
PUT  /api/v1/auth/session/tenant
```

The browser receives an opaque HttpOnly session cookie. Modifying requests require Origin and `X-CSRF-Token` validation. Session tokens are hashed before database storage.

## Database

Migrations are immutable:

```text
backend/alembic/versions/0001_platform_foundation.py
backend/alembic/versions/0002_tenant_row_level_security.py
```

Tenant assignment tables use composite foreign keys. PostgreSQL RLS reads transaction-local `app.current_tenant_id`; authenticated membership discovery additionally uses `app.current_user_id`.

## Health

```text
GET /api/v1/health/live   # process is alive
GET /api/v1/health/ready  # PostgreSQL and Redis are reachable
```

## Contracts

Generate OpenAPI and frontend types:

```text
backend/.venv/bin/python scripts/generate_openapi.py --config backend/config/dev.toml
npm --prefix frontend run generate:api
```

`backend/openapi/openapi.json` is the only wire-contract source. `frontend/src/shared/api/generated/schema.ts` is generated and must not be manually edited.

## Scope

Included: IAM, tenant membership, RBAC, groups, audit, sessions, CSRF, RLS, public Agent publication,
anonymous visitor sessions, WebSocket text interactions, idempotency, rate limiting, and a durable
in-process Runtime Port.

Excluded: direct Skyler imports. Production uses the in-process runtime with explicit model-host,
MCP-host, sandbox, credential-reference, and vector-store configuration. The local Compose setup is
not a production TLS or sandbox-executor topology.
