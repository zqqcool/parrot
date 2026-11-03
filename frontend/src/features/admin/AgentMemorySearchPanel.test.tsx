import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { AgentMemorySearchPanel } from "@/features/admin/AgentMemorySearchPanel";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

const authValue: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "operator_test",
      username: "operator",
      display_name: "Operator",
      avatar_present: false,
      permissions: ["agents.read", "tenant.users.read"],
      tenants: [{ id: "tenant_test", slug: "test", name: "Test Tenant" }],
      must_change_password: false,
      request_id: "req_test",
    },
    csrf_token: "csrf_test",
    expires_at: "2027-07-12T20:00:00Z",
    password_min_length: 12,
    default_schedule_timezone: "Asia/Shanghai",
  },
  loading: false,
  login: () => Promise.resolve(),
  logout: () => Promise.resolve(),
  refreshSession: () => Promise.resolve(),
  switchTenant: () => Promise.resolve(),
  hasPermission: (permission) => authValue.session!.principal.permissions.includes(permission),
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthContext.Provider value={authValue}>
        <AgentMemorySearchPanel tenantId="tenant_test" />
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("AgentMemorySearchPanel", () => {
  it("browses visible memory without a keyword and applies subsequent keyword searches", async () => {
    const user = userEvent.setup();
    const searches: URL[] = [];
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () =>
        ok([
          {
            id: "agent_test",
            tenant_id: "tenant_test",
            runtime_agent_id: "runtime_test",
            slug: "memory-agent",
            name: "Memory Agent",
            description: "",
            system_prompt: "",
            status: "active",
            agent_type_key: "knowledge",
            published: true,
            allow_anonymous: false,
            avatar_present: false,
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/users", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/memory/agent-view", ({ request }) => {
        const url = new URL(request.url);
        searches.push(url);
        return ok({
          items: [
            {
              id: "memory_test",
              tenant_id: "tenant_test",
              agent_id: "agent_test",
              scope_type: "agent",
              scope_id: "agent_test",
              key: "release_policy",
              content: "Use staged rollout",
              memory_type: "project_convention",
              retention_policy: "user_managed",
              status: "active",
              version: 1,
              created_by: null,
              created_at: "2026-07-15T00:00:00Z",
              updated_at: "2026-07-15T00:00:00Z",
            },
          ],
          total: 1,
          offset: 0,
          limit: 20,
          mode: url.searchParams.has("query") ? "window" : "browse",
          anchor_id: url.searchParams.has("query") ? "memory_test" : null,
          retrieval_method: url.searchParams.has("query") ? "hybrid" : "browse",
          degradation_reason: null,
        });
      }),
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "更多筛选" }));
    await user.click(await screen.findByRole("combobox", { name: "选择 Agent" }));
    await user.click(await screen.findByText("Memory Agent"));
    await waitFor(() => expect(searches).toHaveLength(1));
    expect(searches[0].searchParams.get("query")).toBeNull();
    expect(searches[0].searchParams.get("agent_id")).toBe("agent_test");
    expect(await screen.findByText("release_policy")).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("输入关键词；留空则展示该 Agent 可见的全部记忆"),
      "release",
    );
    await waitFor(() => expect(searches).toHaveLength(2));
    expect(searches[1].searchParams.get("query")).toBe("release");
    expect(await screen.findByText(/混合检索：锚点：release_policy/)).toBeInTheDocument();
  });
});
