import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { McpServersPage } from "@/features/admin/McpServersPage";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const mcpServers = [
  {
    id: "mcp_docs",
    tenant_id: "tenant_test",
    name: "Docs MCP",
    transport: "streamable_http",
    endpoint: "https://mcp.example.test",
    arguments: [],
    credentials: [],
    status: "active",
    bound_agents: [{ id: "agent_docs", name: "Docs Assistant" }],
  },
  {
    id: "mcp_ops",
    tenant_id: "tenant_test",
    name: "Operations MCP",
    transport: "streamable_http",
    endpoint: "https://ops.example.test/mcp",
    arguments: [],
    credentials: [],
    status: "active",
    bound_agents: [],
  },
  {
    id: "mcp_private",
    tenant_id: "tenant_test",
    name: "Private MCP",
    transport: "streamable_http",
    endpoint: "https://private.example.test/mcp",
    arguments: [],
    credentials: [],
    status: "active",
    bound_agents: null,
  },
];

const authValue: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "user_test",
      username: "admin",
      display_name: "Administrator",
      avatar_present: false,
      permissions: ["mcp_servers.read", "agents.read", "agents.manage"],
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
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
  switchTenant: vi.fn(),
  hasPermission: (permission) =>
    ["mcp_servers.read", "agents.read", "agents.manage"].includes(permission),
};

function renderMcpServersPage(auth: AuthContextValue = authValue) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <McpServersPage />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("McpServersPage", () => {
  it("shows each MCP server's backend-provided Agent associations", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/mcp-servers", () =>
        HttpResponse.json({ code: "OK", message: "success", data: mcpServers, request_id: "req" }),
      ),
    );
    renderMcpServersPage();

    const docsRow = (await screen.findByText("Docs MCP")).closest("tr");
    if (!(docsRow instanceof HTMLTableRowElement)) throw new Error("Expected Docs MCP table row");
    expect(
      within(docsRow).getByRole("link", { name: "查看关联 Agent Docs Assistant" }),
    ).toHaveAttribute("href", "/admin/agents/agent_docs");
    expect(screen.getByText("暂无关联")).toBeInTheDocument();
    expect(screen.getByText("无查看权限")).toBeInTheDocument();
  });

  it("validates bound MCP tool recall through the Agent runtime ranking contract", async () => {
    const user = userEvent.setup();
    let recallBody: unknown;
    let agentUpdateBody: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/mcp-servers", () =>
        HttpResponse.json({ code: "OK", message: "success", data: mcpServers, request_id: "req" }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [
            {
              id: "agent_docs",
              tenant_id: "tenant_test",
              runtime_agent_id: "docs",
              slug: "docs",
              name: "Docs Assistant",
              description: "",
              system_prompt: "",
              capability_relevance_threshold: 0.4,
              status: "active",
              agent_type_key: "knowledge",
              published: true,
              allow_anonymous: false,
              avatar_present: false,
            },
          ],
          request_id: "req_agents",
        }),
      ),
      http.post(
        "/api/v1/admin/tenants/tenant_test/agents/agent_docs/mcp-tools:search",
        async ({ request }) => {
          recallBody = await request.json();
          return HttpResponse.json({
            code: "OK",
            message: "success",
            data: {
              agent_id: "agent_docs",
              agent_type_key: "knowledge",
              query: "查询当前订单状态",
              retrieval_method: "hybrid",
              eligible_server_count: 1,
              eligible_tool_count: 3,
              configured_relevance_threshold: 0.4,
              applied_relevance_threshold: 0.6,
              candidates: [
                {
                  id: "mcp:mcp_docs:search_docs",
                  server_id: "mcp_docs",
                  server_name: "Docs MCP",
                  name: "search_docs",
                  description: "Search current documentation",
                  rank: 1,
                  relevance_score: 0.83,
                },
              ],
            },
            request_id: "req_recall",
          });
        },
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_docs", async ({ request }) => {
        agentUpdateBody = await request.json();
        return HttpResponse.json({
          code: "OK",
          message: "success",
          data: {
            id: "agent_docs",
            tenant_id: "tenant_test",
            runtime_agent_id: "docs",
            slug: "docs",
            name: "Docs Assistant",
            description: "",
            system_prompt: "",
            capability_relevance_threshold: 0.6,
            status: "active",
            agent_type_key: "knowledge",
            published: true,
            allow_anonymous: false,
            avatar_present: false,
          },
          request_id: "req_update",
        });
      }),
    );
    renderMcpServersPage();

    const recallButton = await screen.findByRole("button", { name: "召回验证" });
    expect(recallButton).toHaveClass("ant-btn-color-primary", "ant-btn-variant-outlined");
    await user.click(recallButton);
    const dialog = screen.getByRole("dialog", { name: "MCP 工具召回验证" });
    await user.click(
      within(dialog).getByRole("combobox", { name: "选择用于 MCP 工具召回验证的 Agent" }),
    );
    await user.click(
      await screen.findByText("Docs Assistant", {
        selector: ".ant-select-item-option-content",
      }),
    );
    const thresholdInput = within(dialog).getByRole("spinbutton", {
      name: "设置 Agent 能力召回最低相关度",
    });
    expect(thresholdInput).toHaveValue("0.40");
    await user.clear(thresholdInput);
    await user.type(thresholdInput, "0.6");
    await user.type(
      within(dialog).getByRole("textbox", {
        name: "输入用于 MCP 工具召回验证的用户问题",
      }),
      "查询当前订单状态",
    );
    await user.click(within(dialog).getByRole("button", { name: "开始召回" }));

    await waitFor(() =>
      expect(recallBody).toEqual({ query: "查询当前订单状态", relevance_threshold: 0.6 }),
    );
    expect(await within(dialog).findByText("召回方式：BM25 + 向量融合")).toBeVisible();
    expect(within(dialog).getByText("search_docs")).toBeVisible();
    expect(within(dialog).getByText("相关度 0.830")).toBeVisible();
    expect(within(dialog).getByText("第 1 位")).toBeVisible();

    await user.click(within(dialog).getByRole("button", { name: "应用到 Agent" }));
    await waitFor(() => expect(agentUpdateBody).toEqual({ capability_relevance_threshold: 0.6 }));
    expect(within(dialog).getByText("已应用到 Agent 后续召回")).toBeVisible();
  });

  it("hides recall validation without Agent read permission", async () => {
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/mcp-servers", () =>
        HttpResponse.json({ code: "OK", message: "success", data: [], request_id: "req" }),
      ),
    );
    renderMcpServersPage({
      ...authValue,
      hasPermission: (permission) => permission === "mcp_servers.read",
    });

    expect(await screen.findByRole("heading", { name: "MCP 配置" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "召回验证" })).not.toBeInTheDocument();
  });
});
