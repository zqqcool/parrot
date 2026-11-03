# ADR 0001: Integrate Skyler Through a Runtime Port

## Status

Superseded by ADR 0002 on 2026-07-13. This document is retained only as historical context for the
former remote-adapter boundary; it must not be used for new implementation or operations.

## Context

Parrot owns identity, tenancy, agent publication, interactions, and browser-facing protocols.
Skyler owns planner, agent-loop, capability, tool, skill, and subagent execution. Importing
Skyler repositories or exposing its private HTTP schemas would couple the platform to runtime
storage and would bypass Parrot authorization.

The H5 client needs incremental output, reconnect recovery, and one protocol shared with the
backend. A live WebSocket connection alone is not durable and Redis is not a source of truth.

## Decision

- Parrot remains the control plane and protocol owner.
- Skyler is integrated behind the public `AgentRuntimePort`; Parrot modules must not import
  Skyler persistence or private application modules.
- The first adapter may run in process, but it must only use an explicit Skyler compatibility
  facade. The port remains suitable for a later remote runtime adapter.
- Parrot `interaction_id` and Skyler `run_id` are different identifiers and are mapped explicitly.
- Interaction events are persisted in PostgreSQL before live publication. Redis may distribute
  committed events between instances but cannot be the durable event store.
- HTTP creates and queries interactions. WebSocket is the IM real-time subscription and control
  channel. Both expose the same versioned `ai.*` event vocabulary.
- OpenAPI owns HTTP contracts. AsyncAPI owns the WebSocket channel. Shared payload schemas are
  generated or compatibility-tested; frontend features must not maintain handwritten variants.
- Authentication, tenant isolation, rate limits, execution policy, and resource visibility are
  resolved by Parrot. Runtime-supplied identity headers are never trusted.

## Runtime boundary

```pseudo
interface AgentRuntimePort:
    start(principal, runtime_request, event_sink) -> execution_reference
    cancel(principal, execution_reference) -> void
    steer(principal, execution_reference, message) -> void

interface RuntimeEventSink:
    append(interaction_id, runtime_event) -> persisted_event
```

The adapter maps runtime-specific state into the stable interaction events. Raw prompts,
credentials, internal addresses, stack traces, and unrestricted tool arguments are never copied
into browser-visible event data.

## Delivery invariant

```pseudo
transaction:
    append interaction_event with monotonically increasing sequence
    append outbox record referencing interaction_event
commit

publisher:
    publish committed event
    mark outbox record delivered

subscriber(last_sequence):
    read durable events after last_sequence
    attach live subscription
    read durable events once more to close the race window
    deduplicate by event_id
```

The WebSocket gateway subscribes to an interaction-specific Redis channel. A notification only
wakes the gateway; it never carries the authoritative event payload. The gateway then reads all
rows after its last durable sequence. A periodic database scan closes notification-loss and Redis
outage gaps.

Delivery is at least once. Clients deduplicate by `event_id` and order events by `sequence` within
one interaction.

## Consequences

- The integration adds a port and event mapping layer, but protects platform security and permits
  independent runtime scaling later.
- WebSocket reconnect can recover from PostgreSQL instead of relying on connection lifetime.
- A transactional outbox and an additional migration are required before multi-instance live
  delivery is production-ready.
- Direct imports from `skyler.apps.*` remain prohibited. The only permitted future dependency is
  an explicitly reviewed compatibility package or remote adapter.

## Replacement condition

Move from the in-process adapter to a separately deployed runtime when independent scaling,
failure isolation, sandboxing, or release ownership is required. The public port and protocol do
not change during that migration.
