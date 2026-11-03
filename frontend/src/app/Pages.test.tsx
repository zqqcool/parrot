import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { AuthProvider } from "@/shared/auth/AuthProvider";
import { formatDateTime } from "@/shared/time";
import { agentTypes } from "@/test/agentTypes";
import { server } from "@/test/server";

const ok = (data: unknown) =>
  HttpResponse.json({ code: "OK", message: "success", data, request_id: "req_test" });
const session = {
  principal: {
    tenant_id: "tenant_test",
    subject_type: "user",
    subject_id: "user_test",
    username: "admin",
    display_name: "Administrator",
    permissions: [
      "platform.tenants.manage",
      "tenant.users.read",
      "tenant.groups.read",
      "tenant.roles.read",
      "agents.read",
      "agents.manage",
      "agents.publish",
      "llm_configs.read",
      "skills.read",
      "skills.manage",
      "mcp_servers.read",
      "interactions.read.any",
      "memory.read",
      "memory.manage",
      "schedules.read",
      "schedules.manage",
      "audit.read",
    ],
    tenants: [{ id: "tenant_test", slug: "test", name: "Test Tenant" }],
    must_change_password: false,
    request_id: "req_test",
  },
  csrf_token: "csrf_test",
  expires_at: "2027-07-12T20:00:00Z",
  password_min_length: 12,
  default_schedule_timezone: "Asia/Shanghai",
};
const modelProviders = [
  {
    key: "openai",
    name: "OpenAI",
    capabilities: [
      {
        kind: "llm",
        description: "OpenAI Chat Completions",
        credential_type: "api_key",
        default_base_url: "https://api.openai.com/v1",
        default_model: null,
        default_embedding_dimension: null,
        base_url_placeholder: null,
        model_placeholder: "例如：gpt-4.1-mini",
      },
    ],
  },
];

function renderAdmin(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <AuthProvider>
            <App />
          </AuthProvider>
        ),
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  server.use(
    http.get("/api/v1/auth/session", () => ok(session)),
    http.get("/api/v1/admin/tenants", () =>
      ok([{ id: "tenant_test", slug: "test", name: "Test Tenant", status: "active" }]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/dashboard", () =>
      ok({
        agents: { value: 1, supported: true },
        llm_configs: { value: 2, supported: true },
        skills: { value: 3, supported: true },
        mcp_servers: { value: 1, supported: true },
        im_entries: { value: 1, supported: true },
        runs: { value: 8, supported: true },
        active_runs: 2,
        service: {
          health: "healthy",
          database: "available",
          redis: "available",
          runtime: "in_process",
          environment: "test",
        },
        dependency_warnings: [],
      }),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/users", () =>
      ok([
        {
          id: "user_two",
          username: "alex",
          email: null,
          display_name: "Alex Chen",
          status: "active",
          must_change_password: false,
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/groups", () =>
      ok([
        {
          id: "group_test",
          name: "Operators",
          description: "Ops",
          status: "active",
          is_system: false,
          member_count: 2,
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/roles", () =>
      ok([
        {
          id: "role_test",
          key: "viewer",
          name: "Viewer",
          description: "",
          status: "active",
          is_system: true,
          permissions: ["agents.read"],
        },
      ]),
    ),
    http.get("/api/v1/admin/permissions", () =>
      ok([{ key: "agents.read", description: "查看当前租户智能体配置" }]),
    ),
    http.get("/api/v1/admin/agent-types", () => ok(agentTypes)),
    http.get("/api/v1/admin/tenants/tenant_test/agents", () =>
      ok([
        {
          id: "agent_test",
          tenant_id: "tenant_test",
          runtime_agent_id: "runtime_test",
          slug: "demo",
          name: "Demo Agent",
          description: "Demo",
          status: "active",
          agent_type_key: "knowledge",
          published: true,
          allow_anonymous: true,
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/llm-configs", () =>
      ok({ ids: [], default_id: null }),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/skills", () => ok({ ids: [] })),
    http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
      ok([
        {
          id: "llm_test",
          tenant_id: "tenant_test",
          name: "Primary Model",
          provider: "openai-compatible",
          model: "model-test",
          base_url: null,
          credential_configured: true,
          temperature: 0.2,
          max_tokens: 4096,
          status: "active",
          is_default: true,
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
      ok([
        {
          id: "skill_test",
          tenant_id: "tenant_test",
          name: "Web Search",
          description: "Search published sources",
          status: "published",
          version: 1,
          manifest: {},
          instructions: "Search before answering",
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/skills/skill_test/versions", () => ok([])),
    http.get("/api/v1/admin/tenants/tenant_test/audit-logs", () =>
      ok([
        {
          id: "audit_test",
          action: "user.create",
          resource_type: "user",
          resource_id: "user_two",
          actor_type: "user",
          actor: { id: "user_test", display_name: "Administrator", avatar_present: false },
          request_id: "req_audit",
          created_at: "2026-07-12T10:00:00Z",
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs", () =>
      ok([
        {
          id: "interaction_test",
          tenant_id: "tenant_test",
          agent_id: "agent_test",
          agent_name: "Demo Agent",
          actor_type: "anonymous",
          requester: {
            actor_type: "anonymous",
            actor_id: "visitor_12345678",
            display_name: "匿名访客 · 12345678",
          },
          entry_type: "text",
          input_type: "text",
          input_summary: "Hello Parrot",
          status: "completed",
          runtime_execution_id: "run_test",
          created_at: "2026-07-13T08:00:00Z",
          updated_at: "2026-07-13T08:00:02Z",
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs/requesters", () =>
      ok([
        {
          actor_type: "anonymous",
          actor_id: "visitor_12345678",
          display_name: "匿名访客 · 12345678",
          run_count: 1,
          active_run_count: 0,
          latest_run_at: "2026-07-13T08:00:00Z",
        },
      ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs/conversations", () =>
      ok([
        {
          conversation_id: "conversation_test",
          agent_id: "agent_test",
          agent_name: "Demo Agent",
          message_count: 2,
          active_run_count: 0,
          latest_message_at: "2026-07-13T08:00:02Z",
        },
      ]),
    ),
    http.get(
      "/api/v1/admin/tenants/tenant_test/runs/conversations/conversation_test/messages",
      () =>
        ok([
          {
            id: "message_user",
            interaction_id: "interaction_test",
            role: "user",
            content: "Hello Parrot",
            run_status: "completed",
            created_at: "2026-07-13T08:00:00Z",
          },
          {
            id: "message_assistant",
            interaction_id: "interaction_test",
            role: "assistant",
            content: "Hello!",
            run_status: "completed",
            created_at: "2026-07-13T08:00:02Z",
          },
          {
            id: "message_empty",
            interaction_id: "interaction_test",
            role: "assistant",
            content: "   ",
            run_status: "completed",
            created_at: "2026-07-13T08:00:03Z",
          },
        ]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs/interaction_test", () =>
      ok({
        id: "interaction_test",
        tenant_id: "tenant_test",
        agent_id: "agent_test",
        agent_name: "Demo Agent",
        actor_type: "anonymous",
        requester: {
          actor_type: "anonymous",
          actor_id: "visitor_12345678",
          display_name: "匿名访客 · 12345678",
        },
        entry_type: "text",
        input_type: "text",
        input_summary: "Hello Parrot",
        status: "completed",
        runtime_execution_id: "run_test",
        created_at: "2026-07-13T08:00:00Z",
        updated_at: "2026-07-13T08:00:02Z",
      }),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs/interaction_test/events", () => ok([])),
    http.get("/api/v1/admin/tenants/tenant_test/runs/interaction_test/diagnostic-traces", () =>
      ok([]),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/runs/interaction_test/task-board", () =>
      ok({ id: null, status: "not_generated", tasks: [] }),
    ),
    http.get("/api/v1/admin/tenants/tenant_test/memory", () =>
      ok([
        {
          id: "memory_test",
          tenant_id: "tenant_test",
          agent_id: "agent_test",
          agent_name: "Support Agent",
          scope_type: "tenant",
          scope_id: "tenant_test",
          key: "release-policy",
          content: "Use staged rollout",
          memory_type: "project_convention",
          retention_policy: "user_managed",
          status: "active",
          version: 1,
          created_by_actor_id: "user_test",
          created_by: { id: "user_test", display_name: "Administrator", avatar_present: false },
          created_at: "2026-07-13T08:00:00Z",
          updated_at: "2026-07-13T08:00:00Z",
        },
        {
          id: "memory_visitor",
          tenant_id: "tenant_test",
          agent_id: "agent_test",
          agent_name: "Support Agent",
          scope_type: "user",
          scope_id: "visitor_test",
          key: "visitor-note",
          content: "Anonymous visitor memory",
          memory_type: "long_term_fact",
          retention_policy: "user_managed",
          status: "active",
          version: 2,
          created_by_actor_id: "visitor_test",
          created_by: null,
          created_at: "2026-07-13T09:00:00Z",
          updated_at: "2026-07-13T09:05:00Z",
        },
      ]),
    ),
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
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("management pages", () => {
  it("renders backend-backed Parrot overview metrics", async () => {
    renderAdmin("/admin");

    expect(await screen.findByRole("heading", { name: "智能体平台总览" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("parrot-runtime / in_process")).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText("暂无依赖异常")).toBeInTheDocument());
    expect(screen.queryByText("未开放")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "刷新" })).not.toBeInTheDocument();
  });

  it("opens and saves the current user's profile from the header", async () => {
    const user = userEvent.setup();
    let profilePayload: unknown;
    server.use(
      http.patch("/api/v1/auth/profile", async ({ request }) => {
        profilePayload = await request.json();
        return ok({ updated: true });
      }),
    );
    renderAdmin("/admin");

    await screen.findByRole("heading", { name: "智能体平台总览" });
    await user.click(screen.getByRole("button", { name: "打开用户菜单" }));
    expect(await screen.findByRole("menuitem", { name: "退出登录" })).toBeInTheDocument();
    await user.click(await screen.findByRole("menuitem", { name: "个人资料" }));
    const dialog = await screen.findByRole("dialog", { name: "个人资料" });
    const displayName = within(dialog).getByRole("textbox", { name: "显示名称" });
    await user.clear(displayName);
    await user.type(displayName, "New display name");
    await user.click(within(dialog).getByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(profilePayload).toEqual({ display_name: "New display name" }));
  });

  it("changes the password from the current-user security tab and clears the session", async () => {
    const user = userEvent.setup();
    let passwordPayload: unknown;
    server.use(
      http.post("/api/v1/auth/password", async ({ request }) => {
        passwordPayload = await request.json();
        return ok({ changed: true });
      }),
      http.post("/api/v1/auth/logout", () => ok({ revoked: true })),
    );
    renderAdmin("/admin");

    await screen.findByRole("heading", { name: "智能体平台总览" });
    await user.click(screen.getByRole("button", { name: "打开用户菜单" }));
    await user.click(await screen.findByRole("menuitem", { name: "个人资料" }));
    const dialog = await screen.findByRole("dialog", { name: "个人资料" });
    await user.click(within(dialog).getByRole("tab", { name: "安全设置" }));
    await user.type(within(dialog).getByLabelText("当前密码"), "old-password");
    await user.type(within(dialog).getByLabelText("新密码"), "new-password");
    await user.type(within(dialog).getByLabelText("确认新密码"), "new-password");
    await user.click(within(dialog).getByRole("button", { name: "修改密码并退出登录" }));

    await waitFor(() =>
      expect(passwordPayload).toEqual({
        current_password: "old-password",
        new_password: "new-password",
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("用户名")).toBeInTheDocument());
  });

  it("navigates through tenant administration resources", async () => {
    const router = renderAdmin("/admin/tenants");
    await waitFor(() => expect(screen.getByText("Test Tenant")).toBeInTheDocument());

    for (const [path, heading, row] of [
      ["/admin/users", "用户管理", "Alex Chen"],
      ["/admin/groups", "用户组", "Operators"],
      ["/admin/roles", "角色权限", "只读成员"],
      ["/admin/agents", "智能体管理", "Demo Agent"],
      ["/admin/audit", "审计日志", "user.create"],
    ]) {
      await router.navigate(path);
      await waitFor(() =>
        expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument(),
      );
      await waitFor(() => expect(screen.getByText(row)).toBeInTheDocument());
    }
  });

  it("shows readable permission descriptions with their stable codes", async () => {
    const user = userEvent.setup();
    renderAdmin("/admin/roles");

    expect(await screen.findByText("查看当前租户智能体配置（agents.read）")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建" }));
    const dialog = await screen.findByRole("dialog", { name: "新建角色" });
    const selectAllPermissions = within(dialog).getByRole("button", { name: "全选全部权限" });
    await user.click(selectAllPermissions);
    expect(within(dialog).getByText("已选 1 / 1 项")).toBeInTheDocument();
    expect(selectAllPermissions).toBeDisabled();
    const clearPermissions = within(dialog).getByRole("button", { name: "清空权限" });
    expect(clearPermissions).toBeEnabled();
    await user.click(clearPermissions);
    expect(within(dialog).getByText("已选 0 / 1 项")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("combobox"));
    expect(
      await screen.findByRole("option", { name: "查看当前租户智能体配置（agents.read）" }),
    ).toBeInTheDocument();
  });

  it("persists local LLM runtime parameters without a DataCenter dependency", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.get("/api/v1/auth/session", () =>
        ok({
          ...session,
          principal: {
            ...session.principal,
            permissions: [...session.principal.permissions, "llm_configs.manage"],
          },
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () => ok([])),
      http.get("/api/v1/admin/tenants/tenant_test/model-providers", () => ok(modelProviders)),
      http.post("/api/v1/admin/tenants/tenant_test/llm-configs", async ({ request }) => {
        payload = await request.json();
        return ok({
          id: "llm_new",
          tenant_id: "tenant_test",
          ...(payload as Record<string, unknown>),
          status: "active",
        });
      }),
    );
    renderAdmin("/admin/llm-configs");

    expect(await screen.findByRole("heading", { name: "模型配置" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "LLM" }).closest(".model-config-tabs")).toHaveClass(
      "ant-tabs-small",
    );
    await user.click(await screen.findByRole("button", { name: "新建" }));
    const dialog = await screen.findByRole("dialog", { name: "新建模型配置" });
    expect(within(dialog).getByText(/凭据将加密保存且不会回显/)).toBeInTheDocument();
    expect(within(dialog).getByRole("spinbutton", { name: "温度" })).toHaveValue("0.2");
    expect(within(dialog).getByRole("spinbutton", { name: "Max Tokens" })).toHaveValue("4096");
    expect(within(dialog).getByRole("switch", { name: "启用模型思考模式" })).not.toBeChecked();
    expect(within(dialog).getByText("OpenAI")).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "服务地址" })).toHaveValue(
      "https://api.openai.com/v1",
    );
    await user.type(within(dialog).getByRole("textbox", { name: "名称" }), "OpenAI");
    await user.type(within(dialog).getByRole("textbox", { name: "模型" }), "gpt-4.1-mini");
    await user.type(within(dialog).getByLabelText("API Key"), "openai-secret");
    await user.click(within(dialog).getByRole("button", { name: /确\s*定/ }));

    await waitFor(() =>
      expect(payload).toEqual({
        name: "OpenAI",
        provider: "openai",
        model: "gpt-4.1-mini",
        base_url: "https://api.openai.com/v1",
        api_key: "openai-secret",
        temperature: 0.2,
        max_tokens: 4096,
        thinking_enabled: false,
        prompt_cache_enabled: false,
        is_default: false,
      }),
    );
  }, 10_000);

  it("renders integrated runs, memory, and schedules modules", async () => {
    const user = userEvent.setup();
    const router = renderAdmin("/admin/runs");
    expect(await screen.findByRole("heading", { name: "运行进度" })).toBeInTheDocument();
    expect(await screen.findByText("匿名访客 · 12345678")).toBeInTheDocument();

    await router.navigate("/admin/memory");
    expect(await screen.findByRole("heading", { name: "记忆管理" })).toBeInTheDocument();
    expect(await screen.findByText("release-policy")).toBeInTheDocument();
    const memoryTable = screen.getByRole("table");
    expect(within(memoryTable).queryByText("Support Agent")).not.toBeInTheDocument();
    const expandButtons = within(memoryTable).getAllByRole("button", { name: "Expand row" });
    expect(expandButtons).toHaveLength(2);
    await user.click(expandButtons[0]);
    expect(within(memoryTable).getByText("Support Agent")).toBeInTheDocument();
    expect(within(memoryTable).getByText("Administrator")).toBeInTheDocument();
    expect(within(memoryTable).getAllByText(formatDateTime("2026-07-13T08:00:00Z"))).toHaveLength(
      2,
    );
    await user.click(within(memoryTable).getByRole("button", { name: "Expand row" }));
    expect(within(memoryTable).getByText("匿名访客")).toBeInTheDocument();
    expect(within(memoryTable).getByText("visitor_test")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "新建" }));
    await user.click(screen.getByRole("combobox", { name: "范围类型" }));
    expect(await screen.findByText("conversation")).toBeInTheDocument();
    expect(screen.queryByText("thread")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/复用运行时 memory 工具的可见性/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Agent 视角检索" }));
    expect(await screen.findByText(/复用运行时 memory 工具的可见性/)).toBeInTheDocument();

    await router.navigate("/admin/schedules");
    expect(await screen.findByRole("heading", { name: "定时任务" })).toBeInTheDocument();
    expect(await screen.findByText("Daily summary")).toBeInTheDocument();
  });

  it("opens a Run detail drawer from a user's conversation without changing the route", async () => {
    const user = userEvent.setup();
    const router = renderAdmin("/admin/runs");

    await user.click(await screen.findByRole("button", { name: "查看运行" }, { timeout: 5_000 }));
    expect(await screen.findByRole("heading", { name: "用户对话" })).toBeInTheDocument();
    expect(screen.getByText("运行进度", { selector: ".ant-breadcrumb a" })).toHaveAttribute(
      "href",
      "/admin/runs",
    );
    expect(await screen.findByText("Hello Parrot")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "返回提问用户" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "查看此用户输入产生的任务" }));

    expect(await screen.findByRole("dialog", { name: "Run 详情" })).toBeInTheDocument();
    expect(screen.getByText("interaction_test")).toBeInTheDocument();
    expect(await screen.findByText("本轮未生成子任务")).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/^\/admin\/runs\/requesters\//);

    await user.click(screen.getByRole("button", { name: "关闭 Run 详情" }));
    expect(screen.queryByRole("dialog", { name: "Run 详情" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "用户对话" })).toBeInTheDocument();
  });

  it("keeps a single conversation compact and omits empty transcript records", async () => {
    renderAdmin("/admin/runs/requesters/anonymous/visitor_12345678?conversation=conversation_test");

    expect(await screen.findByText("Hello Parrot")).toBeInTheDocument();
    const workspace = document.querySelector(".conversation-workspace--single");
    expect(workspace).toBeInTheDocument();
    expect(getComputedStyle(workspace as Element).minHeight).toBe("560px");
    expect(getComputedStyle(workspace as Element).maxHeight).toBe("");
    expect(screen.queryByLabelText("会话列表")).not.toBeInTheDocument();
    expect(document.querySelectorAll(".conversation-message")).toHaveLength(2);
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
  });

  it("does not show message loading when the requester has no conversations", async () => {
    server.use(http.get("/api/v1/admin/tenants/tenant_test/runs/conversations", () => ok([])));
    renderAdmin("/admin/runs/requesters/anonymous/visitor_without_transcript");

    expect(await screen.findByText("暂无可展示的对话")).toBeInTheDocument();
    expect(screen.getByText("选择一段对话以查看消息")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "loading" })).not.toBeInTheDocument();
  });

  it("updates schedule fields without changing its target Agent", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.put("/api/v1/admin/tenants/tenant_test/schedules/schedule_test", async ({ request }) => {
        payload = await request.json();
        return ok({ id: "schedule_test" });
      }),
    );
    renderAdmin("/admin/schedules");

    expect(await screen.findByText("Daily summary")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const dialog = await screen.findByRole("dialog", { name: "编辑定时任务" });
    expect(within(dialog).getByRole("combobox", { name: "Agent" })).toBeDisabled();
    await user.clear(within(dialog).getByRole("textbox", { name: "任务名称" }));
    await user.type(within(dialog).getByRole("textbox", { name: "任务名称" }), "Updated summary");
    await user.click(within(dialog).getByRole("button", { name: "OK" }));

    await waitFor(() =>
      expect(payload).toEqual({
        title: "Updated summary",
        input_text: "Summarize",
        schedule_type: "recurring",
        cron_expr: "0 9 * * 1-5",
        run_at: null,
        timezone: "Asia/Shanghai",
      }),
    );
  });

  it("enters an agent workspace from the management card", async () => {
    const user = userEvent.setup();
    const router = renderAdmin("/admin/agents");

    expect(await screen.findByRole("heading", { name: "智能体管理" })).toBeInTheDocument();
    const agentCard = await screen.findByRole("article", { name: "智能体 Demo Agent" });
    expect(agentCard).toHaveTextContent("runtime_test");
    expect(agentCard).toHaveTextContent("知识型");
    expect(agentCard).toHaveTextContent("支持匿名访问");
    expect(agentCard).toHaveTextContent("运行中");
    expect(screen.queryByLabelText("智能体概览")).not.toBeInTheDocument();
    expect(document.querySelector(".ant-table-wrapper")).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "总览" })).not.toHaveClass(
      "ant-menu-item-selected",
    );
    expect(screen.queryByRole("menuitem", { name: "智能体" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "在线体验" })).toHaveAttribute("href", "/agents/demo");
    expect(screen.getByRole("link", { name: "工作台" })).toHaveAttribute("href", "/admin");
    await user.click(screen.getByRole("button", { name: "管理配置" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/agents/agent_test"));
    const workspaceHeading = await screen.findByRole("heading", { level: 1, name: "智能体详情" });
    expect(workspaceHeading.closest(".agent-workspace-header")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Demo Agent" })).toBeInTheDocument();
    expect(screen.getByLabelText("智能体运行信息")).toHaveTextContent("runtime_test");
    expect(screen.queryByText("已接入")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "编辑基本资料" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "返回列表" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "智能体详情" })).not.toBeInTheDocument();
  });

  it("renders the global back control in a Skill detail page", async () => {
    renderAdmin("/admin/skills/skill_test");

    await screen.findByRole("heading", { level: 1, name: "Web Search" });
    expect(screen.queryByRole("button", { name: "返回列表" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Skill 启用状态" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Skill 启用状态" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "返回上一页" })).toBeInTheDocument();
  });

  it("opens the current draft from the Skill version history", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/skills", () =>
        ok([
          {
            id: "skill_test",
            tenant_id: "tenant_test",
            name: "Web Search",
            description: "Search published sources",
            status: "draft",
            version: 2,
            manifest: {},
            instructions: "Search before answering",
            current_version_id: "version_one",
            draft_version_id: "version_two",
            has_draft: true,
          },
        ]),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/skills/skill_test/versions", () =>
        ok([
          {
            id: "version_two",
            tenant_id: "tenant_test",
            skill_id: "skill_test",
            version: 2,
            status: "draft",
            description: "Search published sources",
            manifest: {},
            instructions: "Search before answering",
            package_filename: "web-search.zip",
            package_size_bytes: 128,
            package_sha256: "a".repeat(64),
            source_version_id: "version_one",
            created_by_user: {
              id: "user_test",
              display_name: "Administrator",
              avatar_present: false,
            },
            published_by_user: null,
            published_at: null,
            created_at: "2026-07-13T08:00:00Z",
            updated_at: "2026-07-13T08:00:00Z",
          },
        ]),
      ),
    );
    const router = renderAdmin("/admin/skills/skill_test");

    expect(
      await screen.findByRole("button", { name: "编辑草稿" }, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("未发布")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编辑草稿" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/admin/skills/skill_test/edit"),
    );
  });

  it("uses the backend type catalog and its default in the creation form", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/admin/agent-types", () =>
        ok([
          {
            key: "research",
            name: "研究型",
            description: "面向结构化研究与证据整合。",
            is_default: true,
          },
        ]),
      ),
    );
    renderAdmin("/admin/agents");

    await screen.findByRole("heading", { name: "智能体管理" });
    await user.click(screen.getByRole("button", { name: "新建" }));
    const dialog = await screen.findByRole("dialog", { name: "新建智能体发布" });
    const researchType = await within(dialog).findByRole("radio", { name: /研究型/ });

    expect(researchType).toBeChecked();
    expect(researchType.closest(".agent-type-option")).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: /知识型/ })).not.toBeInTheDocument();
  });

  it("edits the supported agent fields from the workspace", async () => {
    const user = userEvent.setup();
    let payload: unknown;
    server.use(
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_test", async ({ request }) => {
        payload = await request.json();
        return ok({
          id: "agent_test",
          tenant_id: "tenant_test",
          runtime_agent_id: "runtime_test",
          slug: "demo",
          name: "Updated Agent",
          description: "Updated description",
          status: "active",
          agent_type_key: "knowledge",
          published: true,
          allow_anonymous: false,
        });
      }),
    );
    renderAdmin("/admin/agents/agent_test");

    await screen.findByRole("heading", { level: 1, name: "智能体详情" });
    await user.click(screen.getByRole("button", { name: "编辑基本资料" }));
    const editor = await screen.findByRole("dialog", { name: "编辑基本资料" });
    await user.clear(within(editor).getByRole("textbox", { name: "名称" }));
    await user.type(within(editor).getByRole("textbox", { name: "名称" }), "Updated Agent");
    await user.clear(within(editor).getByRole("textbox", { name: "说明" }));
    await user.type(within(editor).getByRole("textbox", { name: "说明" }), "Updated description");
    const functionalType = within(editor).getByRole("radio", { name: /功能型/ });
    await user.click(functionalType);
    expect(functionalType).toBeChecked();
    expect(
      within(editor).queryByRole("checkbox", { name: "允许匿名访问" }),
    ).not.toBeInTheDocument();
    expect(within(editor).queryByRole("textbox", { name: "系统提示词" })).not.toBeInTheDocument();
    await user.click(within(editor).getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(payload).toEqual({
        name: "Updated Agent",
        description: "Updated description",
        agent_type_key: "functional",
      }),
    );
    expect(await screen.findByText("智能体基本信息已保存")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Updated Agent" })).toBeInTheDocument();
  });

  it("configures capabilities and publishes a draft agent", async () => {
    const user = userEvent.setup();
    let skillPayload: unknown;
    let agentPayload: unknown;
    const draftAgent = {
      id: "agent_test",
      tenant_id: "tenant_test",
      runtime_agent_id: "runtime_test",
      slug: "demo",
      name: "Demo Agent",
      description: "Demo",
      status: "active",
      agent_type_key: "knowledge",
      published: false,
      allow_anonymous: true,
    };
    server.use(
      http.get("/api/v1/admin/tenants/tenant_test/agents", () => ok([draftAgent])),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/llm-configs", () =>
        ok({ ids: ["llm_test"], default_id: "llm_test" }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/agents/agent_test/skills", () =>
        ok({ ids: ["skill_test"] }),
      ),
      http.put(
        "/api/v1/admin/tenants/tenant_test/agents/agent_test/skills",
        async ({ request }) => {
          skillPayload = await request.json();
          return ok(skillPayload);
        },
      ),
      http.patch("/api/v1/admin/tenants/tenant_test/agents/agent_test", async ({ request }) => {
        agentPayload = await request.json();
        return ok({ ...draftAgent, published: true });
      }),
    );
    const router = renderAdmin("/admin/agents");

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/agents"));
    await screen.findByRole("heading", { name: "智能体管理" });
    const viewButton = await screen.findByRole("button", { name: "管理配置" });
    expect(screen.queryByRole("button", { name: "配置" })).not.toBeInTheDocument();
    await user.click(viewButton);
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/agents/agent_test"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "智能体详情" }),
    ).toBeInTheDocument();
    const workspaceLlmTab = () => {
      const workspaceTabs = document.querySelector<HTMLElement>(".agent-workspace-tabs");
      if (!workspaceTabs) throw new Error("Agent workspace tabs are missing");
      return within(workspaceTabs).getByRole("tab", { name: "模型配置" });
    };
    await user.click(workspaceLlmTab());
    await waitFor(() => expect(workspaceLlmTab()).toHaveAttribute("aria-selected", "true"));
    expect(screen.queryByRole("button", { name: "保存模型配置" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Skill" }));
    expect(await screen.findByText(/系统 Skill 自动可用/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "取消授权 Web Search" }));
    await waitFor(() => expect(skillPayload).toEqual({ ids: [] }));
    expect(screen.getByRole("button", { name: "授权 Web Search" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "基础设定" }));
    await user.click(screen.getByRole("button", { name: /发\s*布/ }));
    await user.click(await screen.findByRole("button", { name: "确认发布" }));
    await waitFor(() => expect(agentPayload).toEqual({ published: true }));
    expect(await screen.findByText("智能体已发布")).toBeInTheDocument();
    expect(screen.getByLabelText("智能体状态")).toHaveTextContent("已发布");
  }, 10_000);
});

describe("public agent pages", () => {
  it("renders the directory and detail entry choices", async () => {
    const user = userEvent.setup();
    const agent = {
      id: "agent_test",
      tenant_id: "tenant_test",
      runtime_agent_id: "runtime_test",
      slug: "demo",
      name: "Demo Agent",
      description: "Demo",
      status: "active",
      published: true,
      allow_anonymous: true,
    };
    server.use(
      http.get("/api/v1/public/agents", ({ request }) =>
        ok(new URL(request.url).searchParams.has("search") ? [] : [agent]),
      ),
      http.get("/api/v1/public/agents/demo", () => ok(agent)),
      http.get("/api/v1/public/agents/demo/channels", () =>
        ok([{ channel_key: "channel_demo", channel_type: "websocket", name: "测试渠道" }]),
      ),
    );
    const directoryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const directory = render(
      <QueryClientProvider client={directoryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Demo Agent")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "搜索智能体" }), "不存在");
    expect(screen.getByText("未找到匹配的智能体")).toBeInTheDocument();
    directory.unmount();
    const detailClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={detailClient}>
        <MemoryRouter initialEntries={["/agents/demo"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "WebSocket 渠道接入" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /测试渠道.*进入测试/ })).toHaveAttribute(
      "href",
      "/im/websocket/channel_demo",
    );
    expect(screen.queryByRole("heading", { name: "语音交互" })).not.toBeInTheDocument();
  });

  it("loads public agent cards in batches of 15 while scrolling", async () => {
    let onIntersect: IntersectionObserverCallback | undefined;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: IntersectionObserverCallback) {
          onIntersect = callback;
        }
        observe() {}
        disconnect() {}
        unobserve() {}
        takeRecords() {
          return [];
        }
        root = null;
        rootMargin = "0px";
        thresholds = [0];
      },
    );
    const agents = Array.from({ length: 16 }, (_, index) => ({
      id: `agent_${index + 1}`,
      tenant_id: "tenant_test",
      runtime_agent_id: `runtime_${index + 1}`,
      slug: `demo-${index + 1}`,
      name: `Demo Agent ${index + 1}`,
      description: "Demo",
      status: "active",
      published: true,
      allow_anonymous: true,
    }));
    const requestedOffsets: string[] = [];
    server.use(
      http.get("/api/v1/public/agents", ({ request }) => {
        const params = new URL(request.url).searchParams;
        requestedOffsets.push(params.get("offset") ?? "");
        const offset = Number(params.get("offset"));
        return ok(agents.slice(offset, offset + Number(params.get("limit"))));
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Demo Agent 15")).toBeInTheDocument();
    expect(screen.queryByText("Demo Agent 16")).not.toBeInTheDocument();
    onIntersect?.(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
    expect(await screen.findByText("Demo Agent 16")).toBeInTheDocument();
    expect(requestedOffsets).toEqual(["0", "15"]);
  });
});
