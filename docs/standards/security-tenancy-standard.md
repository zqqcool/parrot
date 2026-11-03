# Security And Tenancy Standard

## Identity Model

- A user is a global identity.
- Tenant membership grants access to one tenant.
- Groups, roles, agent publications, interactions, and audit scope are tenant-owned.
- External identities map provider subjects such as Skyler `union_id` to a user; provider IDs are not platform primary keys.
- Anonymous visitors are pseudonymous subjects, not platform users.

## Principal Context

```pseudo
PrincipalContext:
    tenant_id
    subject_type  # user | anonymous | system
    subject_id
    permissions
    request_id
```

Every tenant operation receives this context. Missing tenant context is an error, not a platform-wide fallback.

## Authorization

```pseudo
authorize(principal, permission, resource):
    if principal.tenant_id != resource.tenant_id:
        return not_found
    if permission not in principal.permissions:
        return forbidden
    return allowed
```

- Permission keys are code-owned and synchronized idempotently.
- Roles are configurable collections of permission keys.
- Roles are primarily assigned to groups; direct membership assignments are allowed for exceptional access.
- Frontend permission checks do not replace backend authorization.

## Session And CSRF

- Session tokens are random opaque values; persist only their hash.
- Cookies are HttpOnly, SameSite=Lax, Path=/, and Secure in production.
- Absolute lifetime is 8 hours; idle lifetime is 30 minutes.
- Session response returns a CSRF token bound to the session. Mutations require the token and allowed Origin.
- Logout, password changes, disablement, and permission reduction revoke affected sessions.
- Login is rate-limited by normalized username and source address without permanent lockout.

## Tenant Isolation

- Tenant tables use non-null `tenant_id`, tenant-prefixed unique constraints, and composite foreign keys where practical.
- Application queries include tenant predicates and PostgreSQL RLS provides defense in depth.
- Use `SET LOCAL` within the transaction; never reuse tenant state across pooled connections.
- Invisible cross-tenant resources return 404.
- User avatars are global-identity metadata, but every managed read or mutation is scoped through an active tenant membership and the corresponding `tenant.users.*` permission. The self-service `/auth/profile` endpoints accept no target user ID and authorize only the authenticated subject in its active tenant. User avatars are never publicly readable.

## Anonymous Access

- Only active, published agents with `allow_anonymous=true` are public.
- Anonymous sessions use a random HttpOnly visitor cookie and default to 30-day retention.
- Anonymous reads require the same visitor, tenant, and interaction ownership.
- Rate limits combine tenant, agent, visitor, and source address.
- User prompts, transcripts, and model outputs are sensitive and excluded from routine logs. The
  explicit dev/SIT `ai.debug_log_prompts` switch may write the provider-ready JSON payload to the
  terminal, while `ai.debug_capture_prompts` may persist the same request snapshot for the management
  Run view. Both are default-off, rejected when `app.environment = "prod"`, inherit transcript
  expiry, and must not emit credentials or authorization headers.
- Management Run diagnostics are a separate, tenant-scoped persistence surface, not a log or a
  public interaction event. They expose metadata only (phase, attempt, provider/model identity,
  counts, roles, tool names, status, and stable code) to an authenticated operator with
  `interactions.read.any`. The only exception is a local `ai.debug_capture_prompts` provider-request
  snapshot; it may contain the exact messages and tool definitions submitted to the model. It must
  never contain credentials, authorization values, cookies, provider endpoints, or raw MCP transport
  data. Diagnostic records inherit transcript expiry.

## Integrated Agent Runtime

- The in-process agent runtime receives only a resolved Parrot principal and non-null tenant ID.
- Root interactions are the only actor-visible interaction resources. Subagent interactions retain
  the Parent tenant/actor for auditing and settlement, but actor-owned reads, public event streams,
  conversation-message persistence, approval, and user-input tools require `runtime_depth=0`.
- A Child profile is derived server-side from the persisted Parent profile. Loop-origin
  `capability_scope` may only select bound, version-matched instruction Skills and MCP Tools whose
  server-owned policy is `effect=read` plus `approval=automatic`; omitted or invalid capabilities
  never expand to the Parent's full profile. Planner-origin compatibility is restricted to the same
  safe read subset.
- Subagent results are bounded reference data. Child reasoning and Tool traces are not copied to the
  Parent; only the versioned task status, content, optional validated structured output, and stable
  error code return through the Parent's original Tool Call.
- Runtime completion uses server-classified Tool observations. Instruction content, control-plane
  discovery, and external-action receipts remain distinct; model text cannot upgrade an instruction
  or failed action into a successful side effect. Relevant failures may only support an honest
  limitation response, not a completed external-action claim.
- Former Skyler `union_id` values may be stored as external identities but never authorize a call.
- Runtime modules use the same PostgreSQL RLS, audit, request ID, and configuration boundaries.
- Remote MCP annotations such as `readOnlyHint` are advisory and never authorize execution. Automatic
  execution requires a same-tenant, Agent-bound, server-owned Tool Policy whose canonical JSON Schema
  hash still matches live discovery and whose classification is exactly `effect=read` plus
  `approval=automatic`. Missing, stale, invalid, or conflicting policy fails closed.
- Parallel MCP execution is a separate server-owned opt-in. `parallel_safe=true` is accepted only for
  `effect=read` plus `approval=automatic`, defaults to false for legacy or missing policies, and is
  rechecked against live discovery before a Root Tool batch executes. Child tasks sharing any MCP
  capability not explicitly marked safe are serialized; unknown capability IDs fail closed.
- Side-effect Tool approval is an actor-bound durable action, not natural-language consent. The private
  record includes the exact capability, arguments, policy/hash, expiry, status and bounded resume
  snapshot. Public events expose only an opaque action ID/hash/version and approve/reject choices.
  Resolution must recheck tenant, actor, interaction state, hash, version and expiry before commit;
  execution must recheck the live Tool and schema again. Child/schedule entrypoints cannot approve.
- A Root WebSocket Knowledge Agent may discover remote MCP Tools with a current, non-forbidden
  server-owned policy. `read + automatic` may execute directly; `approval=required`, including
  side-effect Tools, must enter the same durable approval flow as a Functional Agent. Non-interactive
  Knowledge entrypoints expose only automatic read Tools, and Knowledge Agents still exclude local
  process MCP and executable Skill packages.
- Once a side-effect action reaches `executing`, worker loss produces an uncertain partial result and
  never an automatic retry unless a future Tool-specific idempotency contract is explicitly added.
- Tenant LLM, MCP, Embedding and reranker account credentials are encrypted before persistence with
  AES-256-GCM. Embedding and reranker configurations use independent tenant tables and distinct
  authenticated contexts; no retrieval credential extends or reuses an LLM record. The context binds
  ciphertext to its resource ID, injection target and field name where applicable, so ciphertext
  cannot be copied between records. API schemas expose only configured state and MCP injection
  metadata, never plaintext or ciphertext. If a future provider requires a multi-field credential
  such as an IAM AK/SK pair, it is serialized as one versioned, typed payload inside that authenticated
  envelope; partial pairs, credential reuse across provider types, and independent plaintext columns
  are prohibited.
- The credential-encryption key is an independent 32-byte deployment root key supplied in the one
  explicitly selected, repository-external configuration. It must not share material with the
  session pepper or be stored in the same database as credential ciphertext. Tracked TOMLs use
  recognizable public test values; production rejects those values, including the decoded public
  encryption key. Replacing an existing encryption key requires explicit credential re-encryption.
- Credential plaintext may exist only in the request-validation and provider-call memory paths. It is
  excluded from audit metadata, events, logs, browser responses, and runtime tool observations.
- Tool observation compaction recognizes API keys, access keys, cookies and authorization fields
  regardless of case or separators, and redacts credential patterns in nested string values before
  truncation. Preserve non-secret evidence URLs. Use the shared core redaction policy:

  ```pseudo
  if sensitive_key(field): return REDACTED
  if string(value): return truncate(redact(value))
  if structured(value): return compact_each_child(value)
  ```
- A model-configuration draft connection test may receive a write-only credential only on a
  CSRF-protected `llm_configs.manage` route. The draft is never inserted or audited; a blank credential
  on an edit may resolve only the same tenant-owned saved record's encrypted credential. Provider,
  capability, endpoint, and fixed probe validation remain server-owned. Failure diagnostics are
  limited to an allowlisted, length-bounded structure and redact credential patterns; raw provider
  bodies, arbitrary headers, exception strings, request payloads, endpoints, and credentials never
  cross the API boundary.
- No remote runtime adapter is permitted. Runtime recovery uses only Parrot's persisted interaction,
  lease, event, TaskBoard, transcript, and configuration records.

## Operations Access

- Run, memory, schedule, and schedule-execution records always carry a non-null `tenant_id` and
  are protected by PostgreSQL RLS in addition to application predicates.
- Knowledge spaces are tenant-owned security boundaries. A document, version, chunk, Agent binding,
  user grant, and group grant must all carry the same non-null `tenant_id`; a document does not use
  an ACL broader than its containing space. Runtime retrieval is authorized by the current Agent's
  same-tenant bindings plus active Agent, space, document, and version state. User/group grants
  protect management-plane access to spaces, documents, search, and citation expansion; they do not
  filter Agent responses.
- Knowledge retrieval rechecks the live Agent binding and document/version status before returning a
  chunk. PostgreSQL RLS provides tenant defense in depth; cache, full-text, vector, or citation
  identifiers are never authority. A published knowledge Agent with `allow_anonymous=true` may
  disclose its bound knowledge through answers, so binding changes are security-sensitive.
- Knowledge vectors use a collection, credentials, durable index jobs, and reference rows independent
  from Memory. ANN filters are generated from the current tenant and Agent-bound spaces before search,
  and every candidate is reauthorized in PostgreSQL before text is loaded. Source downloads repeat the
  management-plane space-grant check and bind to an immutable document version; object keys are never
  browser authorization.
- Knowledge text preprocessing is a server-owned, versioned local transformation. It may modify only
  the version text subsequently indexed; the authorized private source object remains unchanged, and
  changing a space default never mutates already published evidence.
- A knowledge-space may send document chunks or query text to an Embedding provider only when its
  administrator selects an active tenant-owned Embedding configuration; selecting that configuration
  is the explicit processing authorization. Reranking may send query and candidate text only when an
  active tenant-owned reranker configuration is selected. Enabling a tenant-level cross-space rerank
  setting is explicit authorization for candidate text from current and future Agent-bound spaces in
  that tenant; the management UI must disclose this scope, and restricted spaces still require the
  tenant's compliance approval. Provider endpoints are allowlisted in production. Disabling a
  configuration referenced by either a space or tenant merge setting is rejected; vector/index
  references include its configuration and index revision.
- Run visibility requires `interactions.read.any`; memory and schedule reads/writes use their own
  `*.read` and `*.manage` permissions.
- An Agent-view memory query is a `memory.read` management-plane operation that directly reuses the
  runtime visibility and hybrid-retrieval service; it does not invoke an LLM or return conversation
  messages. The Agent must belong to the current tenant, an optional user context must be a current
  tenant member, and an omitted user context is limited to tenant- and Agent-scoped memory. Vector
  candidates and chronological context rows are both reauthorized in PostgreSQL before content loads.
- Automatic Agent Memory injection uses the same tenant, Agent, actor and conversation visibility
  predicates. Pre-loop pinned memory and query-aware `memory` tool retrieval accept only active,
  confirmed and unexpired records; a retrieved vector or prompt-provided ID is never authorization
  proof.
- Run requester aggregates derive only from tenant-scoped interaction actors. They expose the actor
  type, opaque actor ID, and a safe display label; scheduled system work is excluded from requester
  views and anonymous visitors are never represented as tenant user accounts.
- Management WebSocket handshakes authenticate the same HttpOnly Web session as HTTP management
  APIs. The browser never reads or stores the session token.
- Schedule executions use a system actor bound to the tenant and schedule ID. A schedule payload
  cannot supply an arbitrary principal or tenant.
