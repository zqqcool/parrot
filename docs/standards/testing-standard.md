# Testing Standard

## Test Layers

- Unit tests: pure policy, schema, password/session helpers, and adapters.
- Service tests: use cases with repository fakes and explicit authorization outcomes.
- Integration tests: PostgreSQL constraints/RLS, Redis limits, migrations, and API transactions.
- Frontend component tests: session, permissions, forms, HTTP errors, and state transitions.
- E2E tests: complete public and management workflows.

## Required Security Cases

```pseudo
for each tenant_resource_endpoint:
    assert same_tenant_with_permission succeeds
    assert same_tenant_without_permission is forbidden
    assert other_tenant_is_not_found
    assert missing_session_is_unauthorized
```

Also verify:

- Session cookie attributes and token hashing.
- CSRF rejection and allowed Origin behavior.
- Session revocation after logout, password change, disablement, and permission reduction.
- Group-derived and direct role permissions.
- RLS behavior when an application predicate is accidentally omitted.
- Anonymous agent publication rules, ownership, retention, rate limiting, and idempotency.
- Text adapter, interaction replay, and WebSocket subscription share the stable harness contract.
  When voice is enabled, its adapter must add equivalent contract coverage before release.

## Frontend Cases

```pseudo
bootstrap pending -> no protected page is rendered
bootstrap unauthorized -> public/login route
bootstrap authenticated -> tenant-aware console
permission missing -> no protected request and permission result
```

- Mock the network with MSW at the HTTP boundary.
- Query and mutation tests assert loading, error, success, and cache invalidation.
- E2E covers tenant creation, user/group/role management, tenant switching, agent publication, and
  anonymous text interaction. Voice E2E coverage is a release gate when that entry is enabled.

## Coverage And Quality

- Backend overall: 85% minimum; IAM, tenancy, and RBAC: 95%.
- Frontend overall: 80% minimum; authentication and permission routing: 90%.
- A coverage target does not justify low-value assertions or testing implementation details.
- Bug fixes add a regression test. If impossible, record the reason and reproducible manual verification.
- Tests use dependency containers only and never require the user's running backend process.
