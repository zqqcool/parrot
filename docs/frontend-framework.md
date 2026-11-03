# Frontend Framework

## Runtime

The frontend uses React, React Router, TanStack Query, Ant Design, and IconPark with TypeScript strict mode.

```text
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. The backend process is managed independently.

## Structure

```text
src/app/                 route composition and global styles
src/layouts/             public and administration shells
src/features/admin/      tenant IAM and publication pages
src/features/auth/       login and forced password change
src/features/public-agents/ public Agent routes
src/features/ai-text-entry/ independent text state
src/shared/auth/         session restoration and route guards
src/shared/http/         the only fetch boundary
src/shared/api/          generated types and domain API facade
```

## Session

`AuthProvider` restores `/api/v1/auth/session` on startup. It stores session metadata and CSRF in memory only. JavaScript does not read the HttpOnly cookie and does not persist an access token.

```pseudo
onApplicationStart:
    session = authApi.session()
    httpClient.setCsrfToken(session.csrf_token)

onUnauthorized:
    clearSessionState()
    navigateToLogin()
```

## HTTP

Components call `authApi`, `adminApi`, or `publicApi`; direct `fetch` is prohibited outside `shared/http`.

The shared client provides:

- `credentials: include`
- request IDs
- CSRF headers for modifying requests
- timeout and cancellation
- idempotency keys
- one retry for GET or explicitly idempotent requests
- normalized 401/403/backend errors

## Routes

Public routes:

```text
/
/agents/:slug
/agents/:slug/text
```

Administration routes:

```text
/admin/login
/admin/change-password
/admin/tenants
/admin/users
/admin/groups
/admin/roles
/admin/agents
/admin/audit
```

Frontend permission guards improve navigation only; backend authorization remains final.

## Brand And Icons

All logo usage goes through `shared/brand/ParrotLogo`. Application icons are re-exported from `shared/icons`; feature code does not import IconPark directly.

## Quality

```text
npm run format:check
npm run api:check
npm run lint
npm run typecheck
npm run test
npm run build
```
