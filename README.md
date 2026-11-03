# Parrot

Parrot is a multi-tenant AI interaction platform with a WebSocket text entry backed by one durable
runtime harness. Voice is intentionally not exposed in the current release. The repository contains
a FastAPI administration/API service, a React console and public experience, dependency-only Docker
Compose, and engineering standards enforced by `AGENTS.md` files.

生产部署、服务拓扑、systemd 服务、Nginx 配置和发布检查见
[docs/deployment.md](docs/deployment.md)。

## Layout

```text
backend/          FastAPI, SQLAlchemy Async, Alembic, IAM, tenancy and interactions
frontend/         React Router, TanStack Query, Ant Design and shared HTTP client
docs/standards/   mandatory engineering, security and testing standards
docs/ai-interaction/ independent entry and shared harness contract
docker/           PostgreSQL dependency initialization
scripts/          root quality and OpenAPI checks
skyler/           retained external history; excluded from this implementation
```

## Local Dependencies

For local development that runs applications directly on the host, Docker provides only PostgreSQL
and Redis:

```bash
docker compose up -d postgres redis
```

The PostgreSQL role bootstrap runs only when the data volume is first created. For an existing volume, provision `parrot_app` and `parrot_platform` explicitly before migration.

## SIT Docker Compose

The root Compose file runs the `sit` environment as a full stack. It builds separate backend and
frontend images, runs migrations and permission synchronization before the API starts, and publishes
only the frontend at `http://127.0.0.1:8080`. PostgreSQL and Redis remain bound to loopback for local
diagnostics; the API is reachable only through the frontend reverse proxy.

```bash
make compose-up
```

`backend/config/sit.toml` is the complete `sit` configuration, including public test placeholders. The backend image copies that file to `/etc/parrot/config.toml`; Compose does not mount a
second configuration or secrets file. Migration startup updates schema and permission catalogs only;
it does not create or rewrite tenant-owned LLM, Agent, Skill, MCP, or Knowledge records.

The default stack deliberately excludes TaskIQ. Start the unified worker and its singleton scheduler
when background delivery is required:

```bash
make compose-workers
```

The Compose configuration is not a production deployment: it uses HTTP and disables secure cookies.
Production uses `backend/config/prod.toml`, terminates TLS before the frontend, and supervises every
worker independently. Do not enable untrusted Skill execution in generic Docker Compose; Bubblewrap
inside a container needs a dedicated, hardened runtime policy rather than relaxed container privileges.

## Backend

Use Python 3.13 and an explicit TOML path for every command.

The only supported environment values are `dev`, `sit`, and `prod`. Host development uses
`backend/config/dev.toml`, Docker Compose builds `backend/config/sit.toml` into the image, and
production uses `backend/config/prod.toml`. Each file is complete and is loaded independently.

```bash
cd backend
uv sync --extra dev
.venv/bin/parrot db-upgrade --config config/dev.toml
.venv/bin/parrot sync-permissions --config config/dev.toml
.venv/bin/parrot bootstrap-admin --config config/dev.toml --password-file /path/outside/repository
.venv/bin/parrot serve --config config/dev.toml
```

From the repository root, use `make backend-serve` for a normal process or `make backend-dev` for
local Python/config hot reload. Do not run `uvicorn backend.app.main:app`: there is intentionally no
module-level ASGI application because importing one would require an implicit configuration source.
The Web process never starts durable workers. Locally, start all background work with one command:

```bash
make backend-taskiq
```

This starts the native TaskIQ worker and scheduler containers together. It processes Agent runtime
execution, schedules, memory indexing, document ingestion, knowledge-vector indexing, and Skill builds.
For a non-container local run, use native TaskIQ commands in separate terminals:

```bash
cd backend
.venv/bin/taskiq worker --workers 1 --max-async-tasks 16 --ack-type when_executed app.modules.taskiq_entrypoints:local_broker
.venv/bin/taskiq scheduler --update-interval 1 --loop-interval 1 app.modules.taskiq_entrypoints:local_scheduler
```

Production supervises the worker and singleton scheduler as separate processes.

Skill 草稿保存后可以直接发布。运行时优先使用可选的构建 artifact；没有 artifact 时执行已发布
ZIP 包。运行时不会安装第三方依赖，带依赖的 Skill 构建由统一 TaskIQ worker 异步完成；不应通过
放宽 Bubblewrap 沙箱来执行不受信任的包。

The committed TOMLs contain public `test-only-` credentials and invalid example service addresses.
`prod.toml` deliberately fails validation until deployment credentials replace its placeholders in a
complete file outside Git. Select exactly one such file with `--config`; there is no environment
fallback or secrets overlay. Never embed real deployment files in Docker image layers.

Original local configuration, when retained, belongs under ignored `backend/.local-config/` (0700
folder, 0600 files), which is also excluded from Docker builds. It is never loaded automatically.
Changing public test database passwords does not alter an existing PostgreSQL volume: update the
local roles explicitly or select a matching private configuration; do not delete a data volume.
Tenant LLM and MCP account values remain management inputs stored as authenticated ciphertext.

Before publishing, run `python3 scripts/quality/check_secrets.py`. It scans publishable files and ZIP
members for common credential patterns and requires public placeholders in deployment TOMLs. It is
a heuristic guard, not a guarantee or a Git-history cleaner. See
[the security review](docs/security-review.md) for findings, verification and credential rotation.

## Frontend

Use Node.js 20.9 or newer within major version 20.

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to the independently managed backend at `127.0.0.1:8000`.

## Contracts And Quality

OpenAPI is the only wire contract. Generate both artifacts after an API change:

```bash
make api-generate
make check
```

`make check` enforces file size, formatting, lint, strict types, architecture boundaries, migration heads, OpenAPI drift, coverage thresholds, frontend tests, and the production build.

## Scope Boundary

The production runtime is Parrot's in-process worker with explicit model, sandbox, MCP, and vector
memory configuration. Docker images provide a deployable process boundary, not a second runtime or
an alternative configuration system. See `AGENTS.md` and `docs/standards/` before changing architecture
or security behavior.
