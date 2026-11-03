# Frontend Standard

## Structure

- `app/`: router, providers, layout, global error boundaries.
- `features/`: complete user workflows.
- `shared/http/`: transport, cookies, CSRF, timeout, request IDs, normalized errors.
- `shared/api/`: generated contract types and typed API functions.
- `shared/ui/`: reusable presentation primitives.

## Session Bootstrap

```pseudo
onApplicationStart:
    state = "loading"
    try:
        session = authApi.getSession(credentials="include")
        csrfStore.set(session.csrf_token)
        state = authenticated(session.principal)
    catch Unauthorized:
        state = anonymous
```

- Do not read cookies or store authentication tokens.
- Keep CSRF state in memory and refresh it through the session endpoint.
- A protected route waits for bootstrap before redirecting.
- Permission gates use permission keys from the session, never hard-coded roles.
- Form validation and defaults that mirror server policy use the non-secret bootstrap values from the
  generated session contract; the backend remains the final enforcement point.

## HTTP

```pseudo
http.request(method, path, body):
    headers.request_id = new_request_id()
    if method mutates state:
        headers.csrf = csrf_store.current()
    response = fetch(path, credentials="include", timeout, abort_signal)
    return normalize(response)
```

- Only `shared/http` calls `fetch`.
- `shared/uploads` is the sole exception for direct object upload. It accepts an API-issued,
  short-lived Qiniu exact-key upload token, keeps it in memory, and must be called through a feature
  mutation; components must not construct storage clients or persist credentials.
- Retries are limited to idempotent reads or explicitly idempotent commands.
- 401 clears authenticated state; 403 renders a permission result; errors display request ID.
- API paths and types come from OpenAPI generation.
- The shared request-error notifier is the only presentation boundary for React Query failures. It
  shows one Ant Design `message` toast containing the API response `message` and request ID; do not
  render a second page-level error `Alert` for the same failure. The backend owns the reviewed
  Chinese response message, while the frontend uses a Chinese fallback only for network failures or
  malformed responses. Do not display stack traces, provider output, raw non-HTTP errors, or English
  internal text to end users. Error codes remain stable for clients and diagnostics.
- A model connection-test modal is the narrow exception to toast-only mutation errors. It suppresses
  the global toast and renders the backend's structured, redacted provider diagnostics inline next
  to the tested draft, including both provider and Parrot request IDs when present. It must not parse
  or render raw provider bodies or infer diagnostic text from arbitrary frontend exceptions.
- Model configuration forms derive provider availability, defaults, descriptions, and credential
  shape from the backend provider catalog. A capability that declares an AK/SK pair renders both as
  write-only password inputs; both are required for create, both blank retain the saved pair on edit,
  and changing providers clears every transient credential field before testing or saving.

## Server State And Forms

- TanStack Query owns server cache, loading, error, invalidation, and mutation state.
- Local component state owns transient UI behavior.
- Resource search controls query the backend source of truth after a short debounce. The normalized
  search term is part of the query key, and changing it resets table pagination. Do not filter only
  the records already rendered on the current page. A local filter is allowed only for presentation
  facets over a complete, unpaginated backend result; limited or paginated facets belong in the API.
- Use Ant Design Form for management forms and map 422 details to fields.
- Confirm destructive or access-changing operations.

## UI Requirements

- Public and management shells are separate.
- Text entry uses its own route/component and state machine. A future voice entry must be introduced
  as a separate route/component and must not share mutable UI state with text.
- Primary flows implement loading, empty, error, disabled, success, and permission states.
- Use the shared IconPark adapter and shared brand component.
- Render API timestamps and durations through `shared/time`; feature components do not choose their
  own locale, invalid-value fallback, or 12/24-hour behavior. Domain-specific schedule parsing may
  compose those shared conversion helpers.
- Components should be below 250 lines and must remain below 600 lines.
