# Coding Standard

## Purpose

This standard keeps source code reviewable, typed, testable, and resistant to accidental coupling. Metrics are guardrails, not substitutes for cohesive design.

## Size And Complexity

- Production source: soft limit 400 lines, hard limit 600 lines.
- React page/component: soft limit 250 lines.
- Function: soft limit 60 lines.
- Class: soft limit 300 lines.
- Cyclomatic complexity: maximum 10 unless explicitly reviewed.
- Generated files are exempt. Other exceptions belong in `file-size-exceptions.txt` with owner, reason, and removal condition.

Split by responsibility:

```pseudo
if file owns HTTP parsing and business rules and database statements:
    move HTTP parsing to router
    move use-case and transaction to service
    move persistence query to repository
```

Do not split a cohesive function into forwarding wrappers solely to satisfy a metric.

## Naming And Types

- Code identifiers, error codes, and comments use English.
- Prefer domain terms over generic names such as `data`, `handler`, or `manager` when ownership is known.
- Public functions, service methods, repository methods, and component props are typed.
- `Any`, unchecked casts, and unstructured dictionaries are limited to external boundaries and normalized immediately.
- Units appear in names: `timeout_seconds`, `size_bytes`, `duration_ms`.

## Dependencies

- Use the repository's existing library before adding an overlapping dependency.
- New dependencies require a clear owner, active maintenance, compatible license, and locked version.
- Backend dependencies are declared once in `pyproject.toml` and locked.
- Frontend dependencies are declared in `package.json` and locked in `package-lock.json`.

## Errors And Logging

- Domain errors use stable machine-readable codes.
- Unexpected exceptions are logged with request and tenant context, then mapped to a safe generic response.
- Never expose stack traces, internal addresses, SQL, credentials, cookies, tokens, or private content.
- Empty `except` blocks and broad catch-and-ignore behavior are prohibited.

```pseudo
try:
    result = service.execute(command)
except KnownDomainError as error:
    return mapped_error(error)
except Exception:
    logger.exception("unexpected failure", request_id, tenant_id)
    return internal_error(request_id)
```

## Comments And Documentation

- Comments explain constraints, tradeoffs, or non-obvious invariants.
- Do not narrate assignments or restate function names.
- Architecture and security decisions must be reflected in standards or an ADR.
- Bug fixes include a regression test unless technically impossible and documented.
