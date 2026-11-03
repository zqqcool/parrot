import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AgentWorkspacePage } from "@/features/admin/AgentWorkspacePage";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });

const agent = {
  id: "agent_test",
  tenant_id: "tenant_test",
  runtime_agent_id: "runtime_test",
  slug: "demo-agent",
  name: "Demo Agent",
  description: "Demo",
  system_prompt: "You are a concise assistant.",
  status: "active",
  agent_type_key: "knowledge",
  published: true,
  allow_anonymous: true,
  avatar_present: false,
};
const authValue: AuthContextValue = {
  session: {
    principal: {
      tenant_id: "tenant_test",
      subject_type: "user",
      subject_id: "user_test",
      username: "admin",
      display_name: "Administrator",
      avatar_present: false,
      permissions: [
        "agents.read",
        "agents.manage",
        "agents.publish",
        "schedules.manage",
        "mcp_servers.read",
        "knowledge.spaces.read",
      ],
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

function renderWorkspace(initialEntry = "/admin/agents/agent_test?tab=llm") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/admin/agents/:agentId" element={<AgentWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("AgentWorkspacePage", () => {
  it("groups basic data, guarded access controls, and configuration tabs", async () => {
    const user = userEvent.setup();
    let llmPayload: unknown;
    let mcpPayload: unknown;
    let schedulePayload: unknown;
    let statusPayload: unknown;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () => ok([agent])),
      http.get("/api/v1/admin/agent-types", () =>
        ok([
          {
            key: "knowledge",
            name: "知识型",
            description: "使用知识库回答问题。",
            is_default: true,
            uses_knowledge: true,
            restricts_executable_skills: true,
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        ok([
          { id: "llm_test", name: "Demo", model: "demo", status: "active" },
          { id: "llm_fallback", name: "Fallback", model: "fallback", status: "active" },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/llm-configs", () =>
        ok({ ids: ["llm_test"], default_id: "llm_test" }),
      ),
      http.put(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/llm-configs",
        async ({ request }) => {
          llmPayload = await request.json();
          return ok({ ids: ["llm_fallback"], default_id: "llm_fallback" });
        },
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/skills", () => ok({ ids: [] })),
      http.get("/api/v1/admin/tenants/tenant_test/mcp-servers", () =>
        ok([
          {
            id: "mcp_test",
            tenant_id: "tenant_test",
            name: "Knowledge MCP",
            transport: "streamable_http",
            endpoint: "https://mcp.example.test",
            credentials: [],
            status: "active",
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/mcp-servers", () =>
        ok({ ids: ["mcp_test"] }),
      ),
      http.put(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/mcp-servers",
        async ({ request }) => {
          mcpPayload = await request.json();
          return ok(mcpPayload);
        },
      ),
      http.get("/api/v1/admin/tenants/tenant_test/knowledge/spaces", () =>
        ok([
          {
            id: "space_test",
            tenant_id: "tenant_test",
            slug: "engineering",
            name: "Engineering",
            classification: "standard",
            status: "active",
            access_revision: 1,
            created_at: "2026-07-14T01:00:00Z",
            updated_at: "2026-07-14T01:00:00Z",
          },
          {
            id: "space_release",
            tenant_id: "tenant_test",
            slug: "release",
            name: "Release notes",
            classification: "standard",
            status: "active",
            access_revision: 1,
            created_at: "2026-07-14T01:00:00Z",
            updated_at: "2026-07-14T01:00:00Z",
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/knowledge-spaces", () =>
        ok({ space_ids: ["space_test"] }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/im/channels", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/im/channel-types", () =>
        ok([
          {
            key: "websocket",
            label: "WebSocket",
            enabled: true,
            description: "Browser WebSocket channel",
          },
          { key: "feishu", label: "飞书", enabled: false, description: "Adapter not installed" },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/im-bindings", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/schedules", () =>
        ok([
          {
            id: "schedule_test",
            tenant_id: "tenant_test",
            agent_id: "agent_test",
            creator: { id: "user_test", display_name: "Administrator", avatar_present: false },
            title: "Daily summary",
            input_text: "Summarize",
            schedule_type: "recurring",
            cron_expr: "0 9 * * 1-5",
            run_at: null,
            timezone: "Asia/Shanghai",
            status: "enabled",
            next_trigger_at: "2026-07-14T01:00:00Z",
            last_triggered_at: null,
            created_at: "2026-07-13T08:00:00Z",
            updated_at: "2026-07-13T08:00:00Z",
          },
        ]),
      ),
      http.post("/api/v1/admin/tenants/tenant_test/schedules", async ({ request }) => {
        schedulePayload = await request.json();
        return ok({ id: "schedule_new" });
      }),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_test", async ({ request }) => {
        statusPayload = await request.json();
        return ok({ ...agent, status: "disabled" });
      }),
    );
    renderWorkspace();

    expect(await screen.findByRole("tab", { name: "模型配置" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByRole("button", { name: "保存模型配置" })).not.toBeInTheDocument();
    const fallbackRow = (await screen.findByText("Fallback")).closest("tr");
    if (!(fallbackRow instanceof HTMLTableRowElement)) throw new Error("Expected LLM table row");
    await user.click(within(fallbackRow).getByRole("button", { name: "使用此模型" }));
    await waitFor(() =>
      expect(llmPayload).toEqual({ ids: ["llm_fallback"], default_id: "llm_fallback" }),
    );
    expect(within(fallbackRow).getByRole("button", { name: "当前模型" })).toBeDisabled();
    expect(screen.getByLabelText("智能体状态")).toHaveTextContent("已发布");
    const runtimeDetails = screen.getByLabelText("智能体运行信息");
    expect(runtimeDetails).toHaveTextContent("公开标识");
    expect(runtimeDetails).toHaveTextContent("demo-agent");
    expect(runtimeDetails).toHaveTextContent("runtime_test");
    expect(runtimeDetails).toHaveTextContent("knowledge");
    for (const label of ["基础设定", "Skill", "定时任务", "MCP", "知识库", "集成信息"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("tab", { name: "发布管理" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "基础设定" }));
    const basicDetails = await screen.findByLabelText("智能体基本资料");
    expect(basicDetails).toHaveTextContent("Demo Agent");
    expect(basicDetails).toHaveTextContent("demo-agent");
    expect(basicDetails).toHaveTextContent("runtime_test");
    expect(await screen.findByLabelText("Agent 系统提示词")).toHaveTextContent(
      "You are a concise assistant.",
    );
    expect(screen.getByRole("heading", { name: "访问与发布" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "定时任务" }));
    expect(await screen.findByText("Daily summary")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "刷新" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建定时任务" }));
    const dialog = await screen.findByRole("dialog", { name: "新建定时任务" });
    await user.type(within(dialog).getByRole("textbox", { name: "任务名称" }), "Agent nightly");
    await user.type(
      within(dialog).getByRole("textbox", { name: "Cron（分 时 日 月 星期）" }),
      "0 20 * * *",
    );
    await user.type(within(dialog).getByRole("textbox", { name: "执行指令" }), "Create summary");
    await user.click(within(dialog).getByRole("button", { name: "OK" }));

    await waitFor(() =>
      expect(schedulePayload).toEqual({
        agent_id: "agent_test",
        title: "Agent nightly",
        input_text: "Create summary",
        schedule_type: "recurring",
        cron_expr: "0 20 * * *",
        run_at: null,
        timezone: "Asia/Shanghai",
      }),
    );

    await user.click(screen.getByRole("tab", { name: "MCP" }));
    expect(await screen.findByText("Knowledge MCP")).toBeInTheDocument();
    expect(screen.getByText(/系统 MCP 服务由平台管理员/)).toBeInTheDocument();
    expect(screen.getAllByText("已绑定").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "保存 MCP 配置" })).not.toBeInTheDocument();
    const mcpRow = screen.getByText("Knowledge MCP").closest("tr");
    if (!(mcpRow instanceof HTMLTableRowElement)) throw new Error("Expected MCP table row");
    await user.click(within(mcpRow).getByRole("button", { name: "取消关联" }));
    await user.click(await screen.findByRole("button", { name: "确认取消" }));
    await waitFor(() => expect(mcpPayload).toEqual({ ids: [] }));
    await user.click(within(mcpRow).getByRole("button", { name: "关联 MCP" }));
    await waitFor(() => expect(mcpPayload).toEqual({ ids: ["mcp_test"] }));
    await user.click(screen.getByRole("tab", { name: "集成信息" }));
    expect(await screen.findByText("当前 Agent 尚未绑定渠道")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "创建渠道" }));
    const channelDialog = await screen.findByRole("dialog", { name: "创建渠道" });
    expect(within(channelDialog).getByText(/Origin 必须精确匹配/)).toBeInTheDocument();
    await user.click(within(channelDialog).getByLabelText("渠道类型"));
    expect(
      (await screen.findByText("飞书（未接入）")).closest(".ant-select-item-option"),
    ).toHaveClass("ant-select-item-option-disabled");

    await user.click(screen.getByRole("tab", { name: "知识库" }));
    expect(await screen.findByRole("heading", { name: "知识库绑定" })).toBeInTheDocument();
    expect(screen.getByText(/绑定的知识空间可被匿名访客/)).toBeInTheDocument();
    expect(screen.queryByText("Release notes")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存知识库绑定" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "搜索并选择要绑定的知识库" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "基础设定" }));
    await user.click(screen.getByRole("button", { name: "停用运行" }));
    await user.click(await screen.findByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(statusPayload).toEqual({ status: "disabled" }));
  }, 20_000);

  it("uses scoped editors for basic details, the system prompt, and anonymous access", async () => {
    const user = userEvent.setup();
    const payloads: Record<string, unknown>[] = [];
    let currentAgent: Record<string, unknown> = agent;
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () => ok([currentAgent])),
      http.get("/api/v1/admin/agent-types", () =>
        ok([
          {
            key: "knowledge",
            name: "知识型",
            description: "使用知识库回答问题。",
            is_default: true,
            uses_knowledge: true,
            restricts_executable_skills: true,
          },
        ]),
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_test", async ({ request }) => {
        const payload = (await request.json()) as Record<string, unknown>;
        payloads.push(payload);
        currentAgent = { ...currentAgent, ...payload };
        return ok(currentAgent);
      }),
    );
    renderWorkspace("/admin/agents/agent_test?tab=basic");

    const editBasic = await screen.findByRole("button", { name: "编辑基本资料" });
    const tryAgent = screen.getByRole("button", { name: "体验智能体" });
    expect(editBasic).toHaveClass("ant-btn-primary");
    expect(editBasic.querySelector('[data-icon="EditTwo"]')).toBeInTheDocument();
    expect(tryAgent.querySelector('[data-icon="ArrowRight"]')).toBeInTheDocument();

    await user.click(editBasic);
    const basicEditor = await screen.findByRole("dialog", { name: "编辑基本资料" });
    expect(within(basicEditor).getByRole("textbox", { name: "名称" })).toBeInTheDocument();
    expect(
      within(basicEditor).queryByRole("textbox", { name: "系统提示词" }),
    ).not.toBeInTheDocument();
    expect(
      within(basicEditor).queryByRole("checkbox", { name: "允许匿名访问" }),
    ).not.toBeInTheDocument();
    await user.click(within(basicEditor).getByRole("button", { name: /取\s*消/ }));

    await user.click(screen.getByRole("button", { name: "编辑提示词" }));
    const promptEditor = await screen.findByRole("dialog", { name: "编辑系统提示词" });
    const promptInput = within(promptEditor).getByRole("textbox", { name: "系统提示词" });
    expect(promptInput).toHaveValue("You are a concise assistant.");
    await user.clear(promptInput);
    await user.type(promptInput, "Updated prompt");
    await user.click(within(promptEditor).getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => expect(payloads[0]).toEqual({ system_prompt: "Updated prompt" }));

    await user.click(screen.getByRole("button", { name: "调整访问范围" }));
    const accessEditor = await screen.findByRole("dialog", { name: "调整匿名访问" });
    const anonymousAccess = within(accessEditor).getByRole("checkbox", {
      name: "允许匿名访问",
    });
    expect(anonymousAccess).toBeChecked();
    await user.click(anonymousAccess);
    await user.click(within(accessEditor).getByRole("button", { name: /确认保存/ }));
    await waitFor(() => expect(payloads[1]).toEqual({ allow_anonymous: false }));
  });
});
