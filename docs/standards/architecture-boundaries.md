# Architecture Boundaries

## Repository Boundary

Parrot is a modular monolith and the only deployable application. Skyler capabilities are migrated
into Parrot by domain according to ADR 0002. The retained `skyler/` tree is migration source
material only: production code must not import `skyler.apps.*`, access its database, or mount its
routers. Migrated behavior must use Parrot authentication, tenancy, configuration, persistence,
observability, and API contracts.

## Backend Dependency Direction

```text
api -> modules -> core ports
modules -> infrastructure ports
infrastructure -> core
core -> standard library / stable framework primitives
```

Forbidden dependencies:

- `core` importing a business module.
- Router importing SQLAlchemy models or constructing database statements.
- Repository deciding HTTP status codes.
- One module importing another module's private repository.
- Parrot importing `skyler.apps.*` or mounting Skyler routers directly.
- A migrated module retaining a second user, tenant, database, or configuration system.
- A runtime adapter accepting identity or tenant authority from Skyler headers.

Use an explicit application port for cross-module behavior:

```pseudo
interface RuntimePort:
    execute(principal_context, harness_request) -> harness_result

interaction_service(runtime: RuntimePort):
    authorize(principal_context)
    persist_accepted_interaction()
    return runtime.execute(principal_context, request)
```

Operational modules follow the same rule:

```pseudo
runs(interactionRepository, agentCatalogPort):
    interactions = interactionRepository.list(tenantId)
    names = agentCatalogPort.names(tenantId, interactions.agentIds)
    return composeRunViews(interactions, names)

schedules(agentCatalogPort, interactionService):
    target = agentCatalogPort.getPublished(tenantId, agentId)
    return interactionService.submit(target, scheduleInput)
```

- `runs` reads interaction-owned persistence and must not create a duplicate run table.
- `memory` and `schedules` own only their tables; Agent validation uses the public agent catalog
  port instead of querying `agent_publications` directly.
- TaskIQ workers and the singleton TaskIQ scheduler may call module services, but must not import
  HTTP routers or start inside the Web application lifespan. Domain modules submit work only through
  the `TaskDispatcher` port; they do not scan database job tables or implement consumer loops.

## Frontend Dependency Direction

```text
app -> pages/features -> entities/shared
features -> shared api/http/ui
shared -> framework and utility dependencies only
```

Forbidden dependencies:

- `shared` importing a feature.
- Feature components importing another feature's private component or state.
- Pages calling `fetch` or embedding API paths.
- UI role-name checks such as `role === "admin"`; use permission keys.

## Change Rules

- Prefer a modular monolith until independent scaling or ownership justifies a service boundary.
- Cross-module calls use typed service interfaces, not database joins from unrelated repositories.
- Public contracts are versioned and compatibility-tested.
- Do not add empty layers. A new abstraction must remove real coupling or protect a stable boundary.
