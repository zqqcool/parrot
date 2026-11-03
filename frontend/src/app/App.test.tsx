import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { AuthProvider } from "@/shared/auth/AuthProvider";
import { server } from "@/test/server";

function renderApp(path: string) {
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
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function renderPublicApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const session = {
  principal: {
    tenant_id: "tenant_test",
    subject_type: "user",
    subject_id: "user_test",
    username: "admin",
    display_name: "Administrator",
    permissions: [
      "tenant.users.read",
      "tenant.groups.read",
      "tenant.roles.read",
      "agents.read",
      "llm_configs.read",
      "skills.read",
      "mcp_servers.read",
      "audit.read",
    ],
    tenants: [{ id: "tenant_test", slug: "test", name: "Test Tenant" }],
    must_change_password: false,
    request_id: "req_session",
  },
  csrf_token: "csrf_test",
  expires_at: "2027-07-12T20:00:00Z",
  password_min_length: 12,
  default_schedule_timezone: "Asia/Shanghai",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function sessionResponse(data: typeof session) {
  return HttpResponse.json({
    code: "OK",
    message: "success",
    data,
    request_id: "req_session",
  });
}

describe("application routes", () => {
  it("restores the session and renders the backend-backed dashboard", async () => {
    server.use(
      http.get("/api/v1/auth/session", () => sessionResponse(session)),
      http.get("/api/v1/admin/tenants/tenant_test/users", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [],
          request_id: "req_users",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/dashboard", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: {
            agents: { value: 0, supported: true },
            llm_configs: { value: 0, supported: true },
            skills: { value: 0, supported: true },
            mcp_servers: { value: 0, supported: true },
            im_entries: { value: 0, supported: true },
            runs: { value: 0, supported: true },
            active_runs: 0,
            service: {
              health: "healthy",
              database: "available",
              redis: "available",
              runtime: "local",
              environment: "test",
            },
            dependency_warnings: [],
          },
          request_id: "req_dashboard",
        }),
      ),
    );
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "智能体平台总览" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("parrot-runtime / local")).toBeInTheDocument());
    expect(screen.getByRole("navigation", { name: "后台管理" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByText("当前租户")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Skyler 工作台" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "重新加载当前页面" })).toHaveLength(1);
  });

  it("blocks direct navigation when the permission is missing", async () => {
    server.use(
      http.get("/api/v1/auth/session", () =>
        sessionResponse({
          ...session,
          principal: { ...session.principal, permissions: [] },
        }),
      ),
    );
    renderApp("/admin/users");
    await waitFor(() => expect(screen.getByText("无权访问")).toBeInTheDocument());
  });

  it("renders Agent workspace links in a persistent sidebar", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/auth/session", () => sessionResponse(session)),
      http.get("/api/v1/admin/tenants/tenant_test/llm-configs", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [],
          request_id: "req_llm_configs",
        }),
      ),
      http.get("/api/v1/admin/tenants/tenant_test/model-providers", () =>
        HttpResponse.json({
          code: "OK",
          message: "success",
          data: [],
          request_id: "req_model_providers",
        }),
      ),
    );

    renderApp("/admin/llm-configs");

    const agentNavigation = await screen.findByRole("navigation", { name: "Agent 工作台" });
    expect(within(agentNavigation).getByRole("menuitem", { name: "模型配置" })).toHaveClass(
      "ant-menu-item-selected",
    );
    expect(screen.getByRole("button", { name: "收起 Agent 导航" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Agent" })).not.toHaveAttribute("aria-haspopup");

    await user.click(screen.getByRole("button", { name: "收起 Agent 导航" }));

    expect(agentNavigation).toHaveClass("admin-side-navigation-collapsed");
    expect(screen.getByRole("button", { name: "展开 Agent 导航" })).toBeInTheDocument();
  });

  it("uses streaming chat for a manually configured WebSocket channel", async () => {
    vi.stubGlobal("WebSocket", TestWebSocket);
    renderPublicApp("/im/websocket/channel_demo");
    expect(await screen.findByRole("heading", { name: "Parrot Agent" })).toBeInTheDocument();
    expect(document.querySelector(".site-shell-chat")).toBeInTheDocument();
    expect(document.querySelector(".site-content-chat")).toBeInTheDocument();
  });

  it("renders a recoverable not-found page for unknown routes", async () => {
    renderPublicApp("/missing-page");

    expect(await screen.findByRole("heading", { name: "页面未找到" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回智能体广场" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往管理控制台" })).toHaveAttribute(
      "href",
      "/admin/login",
    );
    expect(screen.getByText("错误代码：HTTP 404")).toBeInTheDocument();
  });

  it("redirects an expired admin session to login", async () => {
    server.use(
      http.get("/api/v1/auth/session", () =>
        HttpResponse.json(
          {
            code: "UNAUTHORIZED",
            message: "Authentication required",
            details: [],
            request_id: "req_401",
          },
          { status: 401 },
        ),
      ),
    );
    renderApp("/admin/users");
    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeInTheDocument();
  });
});

class TestWebSocket {
  static readonly OPEN = 1;
  readyState = TestWebSocket.OPEN;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string, protocols?: string | string[]) {
    void url;
    void protocols;
  }

  close(): void {
    this.readyState = 3;
  }

  send(value: string): void {
    void value;
  }
}
