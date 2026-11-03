# ADR 0002: Merge Skyler Into the Parrot Modular Monolith

## Status

Accepted on 2026-07-13. This decision supersedes the deployment boundary in ADR 0001.
The stable interaction event protocol and durable event-store decisions from ADR 0001 remain.

## Context

Running Parrot and Skyler as separate applications duplicates identity, configuration, database,
deployment, and observability concerns. Skyler also assumes a separate user model, MySQL,
environment-variable configuration, and service-to-service authentication. Those assumptions are
incompatible with Parrot's tenant isolation and browser session security.

Copying Skyler as one package would create a second application inside the repository. Instead,
its capabilities are migrated by domain into Parrot's existing modular-monolith boundaries.

## Decision

- Parrot is the only deployable application and `/api/v1` is the only public API root.
- Identity, tenancy, sessions, authorization, PostgreSQL, Redis, configuration, audit, request IDs,
  OpenAPI, and WebSocket protocols are shared platform capabilities.
- Skyler functionality is split into `agents`, `llm_configs`, `skills`, `mcp_servers`,
  `agent_runtime`, `interactions`, `memory`, and `schedules` modules.
- Routers translate HTTP/WebSocket only. Each module owns schemas, service use cases, repository
  behavior, and tenant-owned persistence.
- Cross-module calls use typed ports. Modules do not query another module's private tables.
- `RuntimePort` accepts and snapshots an interaction, then sends its tenant-scoped identifier to
  the unified TaskIQ Redis Stream. A TaskIQ task holds the PostgreSQL execution lease, renews it
  during execution, and runs the in-process agent loop. TaskIQ also delivers schedules, memory and
  knowledge indexing, ingestion, and Skill builds; no module owns a polling worker or bespoke
  queue. There is no remote Skyler runtime adapter.
- `ExternalIdentity` can map a legacy provider subject during an explicitly authorized data import.
  It never becomes a second authorization system and is not trusted by runtime requests.
- Model and MCP account credentials are authenticated ciphertext in Parrot-owned database records;
  the independent encryption root key remains repository-external. API responses expose neither
  plaintext nor ciphertext.
- Runtime memory uses PostgreSQL as the authorization source of truth and a durable Milvus outbox
  for semantic retrieval. Vector candidates never bypass relational tenant, actor, Agent, thread,
  confirmation, or expiry checks.

## Module ownership

| Module | Owns |
| --- | --- |
| `agents` | Agent definition, publication, and bindings |
| `llm_configs` | Provider/model metadata and encrypted account credentials |
| `skills` | Draft, version, manifest, instructions, publication |
| `mcp_servers` | Server configuration, encrypted account credentials, tool refresh state |
| `agent_runtime` | Planner, agent loop, capability execution, tool policy |
| `interactions` | User-facing execution, durable stream events, cancellation, steering |
| `memory` | Tenant-scoped memory commands and retrieval |
| `schedules` | Scheduled execution definitions and histories |

## Agent capability and publication contract

Agent configuration is owned by `agents`; provider and capability lifecycle rules stay in their
owning catalogs. Cross-module validation uses typed ports instead of querying another module's
tables.

```pseudo
replaceAgentLlmBindings(tenantId, agentId, ids, defaultId):
    require defaultId in ids
    llmCatalog.requireActive(tenantId, ids)
    replace tenant-scoped bindings atomically

publishAgent(tenantId, agentId):
    require permission("agents.publish")
    require one bound default active LLM
    skillCatalog.requirePublished(tenantId, boundSkillIds)
    mark published and append audit record
```

- Every binding carries `tenant_id` and uses composite foreign keys to prevent cross-tenant links.
- A partial unique index allows at most one default LLM per agent.
- Agents are created as drafts. The management UI follows the same create, configure, validate,
  publish sequence as the backend contract.
- Existing published records are not silently unpublished by the schema migration. They must be
  backfilled with valid bindings and checked before switching to the in-process runtime.

## Migration order

1. Introduce tenant-owned LLM, skill, and MCP modules and API contracts.
2. Move agent bindings and capability resolution to those modules.
3. Move planner, agent loop, taskboard, and tool execution into `agent_runtime`.
4. Move memory, schedules, text/WebSocket interaction delivery, and tool policy.
5. Switch `RuntimePort` to the in-process runtime and delete the remote adapter. Any legacy data
   import is a separately authorized, idempotent administrative operation.

The runtime migration is complete for the approved scope: text interactions and WebSocket event
delivery. Voice and third-party IM provider adapters are deliberately excluded, not dormant runtime
fallbacks. The retained `skyler/` tree remains read-only source material for future behavior
comparison, not a deployable fallback.

Every phase must preserve the public interaction protocol and include tenant-isolation tests.
