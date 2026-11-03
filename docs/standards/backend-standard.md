# Backend Standard

## Request Flow

```pseudo
router(request):
    context = resolve_request_context(request)
    command = request_schema.validate(request.body)
    result = service.execute(context, command)
    return api_response(result, context.request_id)
```

- Routers own protocol parsing, dependencies, status codes, and response models.
- Services own use cases, authorization-sensitive behavior, and transactions.
- Repositories own SQLAlchemy queries and persistence mapping.
- Pydantic schemas do not expose password hashes, session hashes, raw provider data, or ORM internals.

## Transaction And Tenant Context

```pseudo
with transaction() as session:
    set_local_tenant(session, principal.tenant_id)
    authorize(principal, required_permission)
    result = repository.mutate(session, tenant_id=principal.tenant_id)
    append_audit_event(session, principal, result)
    commit
```

- A mutation and its audit event commit atomically.
- Tenant-owned repositories require `tenant_id` as a non-optional argument.
- `SET LOCAL` tenant context resets at every commit. A caller that reuses a session after invoking a
  service that commits must call `set_tenant` again before its next tenant-scoped repository access.
- Platform-wide operations use a separate privileged repository path and database role.
- Use UTC timestamps and database constraints for invariants.
- The declarative `Base` maps every Python `datetime` annotation to
  `DateTime(timezone=True)`. Individual models must not weaken this mapping; metadata tests reject
  timezone-naive persisted columns.
- Time-dependent lease, expiry, retry, and scheduling decisions use the shared application `Clock`.
  Long-running workers accept an injected clock for deterministic tests; production uses the UTC
  system clock.

```pseudo
worker.claim(clock):
    now = clock.now()
    claim rows whose lease is absent or older than now
    persist lease_until = now + lease_duration
```

## Configuration

- Start the application and CLI with an explicit TOML path.
- Configuration is validated into typed immutable models at startup.
- Do not read environment variables or `.env` files.
- `config/dev.toml`, `config/sit.toml`, and `config/prod.toml` are independent, complete deployment
  configurations. The loader never overlays a second secrets file. Container images copy the selected
  file to the same explicit, read-only path used by every entrypoint.
- A schedule's omitted timezone is resolved by `schedules.default_timezone`; it is independent from
  `runtime.default_timezone` so schedule policy can change without changing runtime time-tool behavior.
- Tracked TOMLs contain only public `test-only-` values and explicit replacement placeholders, never
  live provider accounts or deployment root keys. The tracked production file must fail validation.
  Provision one complete, repository-external TOML at deployment; do not overlay a second file or
  read environment variables. Private local copies are ignored and excluded from Docker builds.
  Never pass live deployment credentials through Docker build arguments or image layers.
- Before replacing a historically committed credential, revoke or rotate it at its issuing service.
  Session pepper replacement invalidates sessions; credential-encryption key replacement requires an
  explicit decrypt-and-reencrypt operation before the old key is removed. Repository redaction does
  not revoke credentials or erase earlier commits, tags, forks, caches or deployed image layers.
- `ai.debug_log_prompts` is a dev/SIT diagnostic switch, defaulting to `false`. When explicitly
  enabled, the model client writes the provider-ready JSON payload to the process terminal for a
  debugging session; it must never include the authorization header or credential value. The `prod`
  environment rejects this switch because prompts can contain private user, Agent, history, and tool data.
- `ai.debug_capture_prompts` is an independent dev/SIT switch, defaulting to `false`. When
  enabled, the runtime persists provider-request snapshots in tenant-scoped diagnostic traces for the
  management Run view. It inherits transcript expiry and follows the same `prod` rejection and
  credential exclusion rules as terminal prompt logging.
- Third-party LLM and MCP account values are not configured as external reference maps. They are
  entered through authorized management use cases and stored as authenticated ciphertext. Deployment
  root material such as `security.credential_encryption_key` must be provided by the repository-external selected configuration;
  rotating that key requires an explicit decrypt-and-reencrypt operation before the old key is removed.
- Deployment TOML owns only system-level model services such as Memory embedding and capability-index
  embedding, plus endpoint allowlists, timeouts, and vector infrastructure. Agent LLM, Knowledge
  Embedding, and reranker identities and credentials are tenant-owned database configuration selected
  through authorized management use cases. Startup must never rewrite those records from TOML.
- LLM thinking mode is an explicit tenant configuration, disabled by default and snapshotted into
  each runtime profile. It declares the upstream endpoint's actual behavior; the baseline
  OpenAI-compatible adapter must not infer it from provider/model names or translate it into
  unverified vendor fields. A declared or observed reasoning run uses compatible automatic tool
  choice while server-owned completion gates continue to enforce required workflow terminals.
- Skill packages are ZIP archives stored under the explicitly configured `skills.package_directory`.
  Production uses durable shared storage outside the repository; the database stores package metadata,
  never an absolute host filesystem path.
- Local configuration resolves Skill packages and artifacts under `backend/.runtime/`; deployment TOML
  may instead point those directories at a durable mounted NAS path without changing application code.
- Production startup rejects insecure cookies, placeholder credentials, and missing required material.
- Browser file uploads use Qiniu upload tokens. A token is authorized against one tenant resource,
  expires within 15 minutes, limits content type and maximum size, and permits only one staging object
  key. The browser never receives account credentials. The service re-reads and validates the staged
  object, moves it to a
  server-owned canonical key, and deletes the staging key before associating it with a record.
- Provider-detected MIME aliases are narrowly allowlisted only when the provider cannot identify an
  otherwise supported format. Markdown may permit Qiniu's `application/octet-stream` detection
  fallback; the exact key and size limits still apply, and backend content validation remains
  mandatory before the staged object can be associated with a record.
- Object-storage buckets remain private. Application reads pass through an authorized backend route;
  bucket CORS allows only configured frontend origins and the bucket lifecycle expires abandoned
  `staging/` objects within 24 hours.

## Skill Versions And Editing

- A tenant-owned Skill has one optional mutable draft and zero or more immutable published versions.
  The current runtime version is an explicit pointer; rollback changes only that pointer and never
  overwrites historical package content.
- Skill file reads and writes authorize both `tenant_id` and Skill ownership. Only draft packages are
  editable. Saves include the previously observed package checksum and return `409` on a stale draft,
  preventing lost updates between administrators.
- Publishing atomically freezes the draft as a new version, advances the current-version pointer,
  clears the draft pointer, and appends an audit record. A draft created from a historical version
  retains its source version ID for traceability.
- Deleting a Skill removes its mutable draft and immutable version history only when no Agent binds
  it. The deletion must append an audit record and the database must reject a concurrent binding,
  rather than silently cascading a capability change into an Agent.
- Skill list responses include each bound Agent's safe management reference through one tenant-scoped
  aggregate query. The reference is available only to callers that also hold `agents.read`; other
  callers receive `null`, rather than an empty list, so an unavailable association is not confused
  with an unbound Skill.
- MCP server list responses follow the same tenant-scoped aggregate and `agents.read` disclosure
  rule for their bound Agent references.
- Agent type behavior is owned by one server-side policy catalog keyed by the system Agent type
  catalog. Runtime and authorization code consume policy capabilities rather than comparing type
  literals. Management APIs expose only the capabilities needed by the frontend; clients must not
  infer behavior from type keys. A database type without a matching runtime policy fails closed.
- Management capability recall validation is an Agent-scoped read. The Skill branch requires both
  `agents.read` and `skills.read`; the MCP Tool branch requires both `agents.read` and
  `mcp_servers.read`. Both reuse the runtime capability ranker and return at most the same two
  branch candidates exposed by `capability_search`. Skill validation uses currently eligible,
  published bindings without loading instructions or discovering MCP. MCP Tool validation performs
  live discovery only against the Agent's active bindings, applies the current Agent type and
  server-owned Tool Policy filters, and never executes a Tool. For a Knowledge Agent, the MCP branch
  includes current non-forbidden remote Tool Policies, including actions that would require approval
  during a real Root interaction. Neither branch invokes an LLM, and
  query text is sent in a CSRF-protected POST body rather than a URL.
- Each Agent owns a server-defaulted `capability_relevance_threshold` in the inclusive range
  `[0, 1]`. Runtime profiles snapshot it, and the shared Skill/MCP capability ranker rejects every
  hybrid candidate below it before RRF, including weak lexical overlaps. When semantic retrieval is
  unavailable, the existing explicit BM25 fallback remains available. The capability vector index
  uses COSINE so the persisted threshold has one stable meaning. A management recall request may
  supply a temporary threshold for comparison, but changing the Agent requires the audited
  `agents.manage` update path and must not occur as a side effect of the read-only test.
- Skill package runtime contracts follow `docs/standards/skill-manifest-standard.md`. A validated
  draft ZIP can be published directly and becomes immutable. Runtime prefers a matching optional
  build artifact, then falls back to that published ZIP; it never installs dependencies during an
  interaction. Dependency prebuilds are delivered through the unified TaskIQ worker.

## Database And Redis

- PostgreSQL is the durable source of truth.
- Redis Streams plus TaskIQ own asynchronous delivery, acknowledgement recovery, delayed delivery,
  and durable schedules. Redis must have persistence and production availability protections; it is
  not the only copy of durable business state.
- Application code must not implement polling consumers, tenant scans, or bespoke retry queues.
  A TaskIQ task carries only tenant-scoped identifiers; its handler reloads state from PostgreSQL,
  re-applies tenant/RLS scope, and treats stale or deleted records as no-ops.
- A data-retention task may be a narrowly scoped exception: the singleton scheduler can run one
  platform-owned, bounded discovery query through the privileged database role, then each deletion
  must re-enter a tenant-scoped session, lock and revalidate the record, and append a system audit
  event. It never retries business work or iterates tenants.
- Operation tables may expose status, audit, version fencing, and idempotency, but they are not
  queue consumers. An interaction that is committed and ready to execute is published directly to
  TaskIQ; its handler-side lease and state validation make duplicate delivery harmless. Use the
  TaskIQ scheduler only for an explicit due time or a bounded delayed retry.
- All schema changes use new Alembic revisions.
- Sort fields are allowlisted, lists are paginated, and indexes match tenant and query predicates.

## Agent Type Catalog

- Agent types are a system-owned, globally readable catalog. Every agent publication stores a
  non-null `agent_type_key` foreign key. Exactly one catalog row is marked `is_default`; the
  creation service resolves omitted API values through that row. `knowledge` is the seeded default
  for compatibility, not a frontend-owned policy.
- Schema migration may seed code-owned Agent type catalog rows. `bootstrap-admin` creates only the
  initial identity, tenant context, membership, credentials, and required role assignments; it must
  not create an Agent publication or any tenant-owned LLM, Skill, MCP, or Knowledge content.
- A type controls its declared interaction profile only. Runtime sandbox provisioning and voice
  processing must be enforced by the runtime policy; a UI label or catalog row must not grant those
  capabilities by itself.

## API

- Prefix: `/api/v1`.
- Success: `{ code, message, data, request_id }`.
- Error: `{ code, message, details, request_id }`.
- A management list exposed through a search control accepts an optional `query` parameter with a
  maximum length of 300 characters. The service normalizes whitespace, and the repository applies
  tenant-scoped matching against an explicit allowlist of display fields before ordering, limiting,
  or paginating the result. SQL wildcard input is escaped; search must never be implemented by
  filtering an already limited result set.
- Use 401 for missing/invalid authentication, 403 for visible forbidden actions, 404 for invisible tenant resources, 409 for state conflicts, and 422 for schema validation.
- OpenAPI is the wire contract source.
- Every API error `message` is a reviewed, user-facing Chinese explanation owned by the backend error-code catalog. Services may retain English diagnostic text in `AppError`, but exception handlers must never return it directly. Each literal `AppError` code must have a catalog entry, enforced by a regression test; unknown codes return one safe Chinese fallback with the request ID available for support.
- Model-configuration connection tests are CSRF-protected `llm_configs.manage` operations. They
  may accept either a tenant-owned saved configuration ID or a typed draft containing only the
  provider, endpoint, model, provider options, and a write-only credential. Draft fields are checked
  against the server-owned provider capability catalog and endpoint policy, then one fixed
  non-sensitive probe is issued through the same typed provider adapter used at runtime. The browser
  cannot choose the prompt, documents, or probe payload. Draft credentials exist only in request and
  provider-call memory and are never persisted, audited, logged, or returned. Probes are bounded to
  30 seconds. A failed probe may return only structured, bounded diagnostics needed by the tenant
  administrator: upstream HTTP status, documented provider error code/type/message, provider request
  ID, network error class, and local expected/actual response dimensions or counts. Never return a
  raw response body, arbitrary headers, endpoint URL, stack trace, exception text, request payload,
  credential, or vector/model output; known credential patterns in provider messages are redacted.
- Model provider choices, supported capability kinds, defaults, and trusted provider hosts are
  server-owned catalog data. The catalog also declares the capability's credential shape, such as a
  single API Key or an AK/SK pair. Frontends consume this catalog and must not infer protocol,
  defaults, or credential shape from provider keys. Runtime services call the common LLM, Embedding,
  or reranker provider interface; only the provider adapter owns SDK, signing, batching, or
  wire-protocol differences. OpenAI's official API does not define a standalone reranker resource;
  a provider's `/reranks` endpoint is therefore a provider-owned extension even when its official
  documentation demonstrates the OpenAI SDK. The Bailian text-reranker adapter owns its
  workspace-scoped `/compatible-api/v1/reranks` contract and must not make that route available under
  the OpenAI or Volcengine Ark provider keys.
- Session bootstrap may expose non-secret UI policy values, such as password minimum length and the
  default schedule timezone. Clients must consume those values rather than duplicating policy literals.
- Avatar and authorized knowledge-source retrieval are the narrow exceptions to the JSON envelope. Agent avatars require tenant or public-visibility authorization. Managed user avatars require both current-tenant membership and `tenant.users.read`; the `/auth/profile/avatar` self endpoint instead authorizes only the authenticated subject in its active tenant. A knowledge-source response reauthorizes tenant, permission, space grant, document and immutable version for every request. These binary responses use `nosniff` and `no-store`; object-storage keys and permanent URLs are never returned.
- Knowledge management exposes a tenant- and space-scoped, paginated source-activity list so every
  upload grant remains observable before and after document creation. The management UI merges an
  unassociated source into its single document list as a provisional row, and merges a source already
  associated with a document into that document's processing state; it must not render a completed
  source as a duplicate document. The list includes lifecycle status, safe file metadata, processing
  attempts, stable error codes, an optional resulting document ID, and the shared safe
  `UserReference` for the creator/changer when that user remains an active tenant member. A display
  name may be retained only as a historical fallback when the safe reference is unavailable; it never
  exposes staging keys,
  canonical object keys, upload tokens, credentials, or provider response bodies.

## Observability

- Structured logs include request ID, tenant ID, subject ID/type, route, status, and duration.
- Both text and JSON formatters apply credential-pattern redaction. Unexpected exception logs retain
  exception types and filename/line/function frames, excluding exception messages, source statements,
  local variables and cached raw traceback text. Operators correlate failures by request ID.
- Diagnostic fields are redacted before length truncation. Every upstream string, including error
  codes and request IDs, is untrusted; provider endpoints are removed. Custom diagnostics use a fixed
  field allowlist. Pattern matching is defense in depth, not permission to log private content.
- Audit logs capture security-relevant mutations and outcomes.
- Liveness checks process health; readiness checks PostgreSQL and Redis.
- Provider-ready model prompts, tool arguments, tool schemas, and tool observations are never
  emitted to ordinary logs or public `ai.*` interaction events. The management-only Run diagnostic
  trace may persist only bounded metadata (phase, attempt, model identity, counts, roles, names,
  status, and stable code) for an authorized `interactions.read.any` operator, except for the
  explicit dev/SIT `ai.debug_capture_prompts` provider-request snapshot. It inherits the
  interaction transcript expiry and remains unavailable from public/WebSocket replay APIs.
- Automatic Memory context is a tenant-authorized reference path. Before the unified Agent Loop it
  may include only active, confirmed, unexpired `user_preference`, `project_convention`, and
  `conversation_summary` items within a 400-token ceiling. Query-aware retrieval is performed only
  through the scoped `memory` tool when the Loop needs it; there is no separate knowledge interpreter
  or automatic post-interpreter recall. Pending, archived, stale, expired, or cross-scope records
  never enter either path.
