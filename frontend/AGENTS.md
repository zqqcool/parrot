# Frontend Instructions

These rules extend the repository root `AGENTS.md` for `frontend/`.

## Boundaries

- `app/` owns routing and providers; `features/` owns user workflows; `shared/` owns reusable transport and UI primitives.
- Components call typed feature APIs. Only `shared/http` may call `fetch`.
- Server state uses TanStack Query. Authentication/tenant bootstrap uses a focused provider; do not create an unbounded global store.
- Route and button permission checks improve UX only. Never encode backend authorization decisions in the browser.
- Text and voice entry components/routes keep independent local state and call the same typed interaction API family.

## HTTP And Session

- Requests use `credentials: "include"` and the shared HTTP client.
- The client adds request ID, CSRF for mutations, timeout/cancellation, and stable error normalization.
- Never read the HttpOnly session cookie or persist authentication tokens.
- A 401 clears session state and routes to login; 403 shows a permission result; errors preserve request ID.
- API paths and wire types come from the OpenAPI contract, not component literals.

## Components

- Use Ant Design controls and the shared IconPark wrapper.
- Provide loading, empty, error, disabled, and success states for primary workflows.
- Destructive or high-impact operations require confirmation.
- Keep pages/components below 250 lines when practical and split by behavior before reaching 600 lines.

## Quality

- Run ESLint, Prettier, TypeScript strict checks, Vitest, and the production build.
- Use Testing Library and MSW for session, permission, form, and request behavior.
- Authentication and permission routing target 90% coverage; frontend overall targets 80%.
